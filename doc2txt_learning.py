"""Adaptive OCR learning system for doc2txt."""

import math
import random
import re
import time
from pathlib import Path

from doc2txt_models import ImageFeature
from doc2txt_quality import _quality_scorer


class AdaptiveLearner:
    """Adaptive OCR learning system using supervised classification.

    Learns which image types are worth OCR'ing based on:
    - Image features (size, position, brightness, etc.)
    - Logistic regression classifier trained on OCR outcomes
    - Adaptive exploration rate (high early, decreases as confidence grows)
    """

    DEFAULT_DB_PATH = Path.home() / ".doc2txt" / "learning.db"
    MIN_SAMPLES_FOR_PREDICTION = 30  # Need enough data to train classifier
    MIN_EXPLORATION_RATE = 0.05  # Always explore at least 5%
    MAX_EXPLORATION_RATE = 0.50  # Start at 50% exploration
    EXPLORATION_HALFLIFE = 200  # Samples to halve exploration rate
    SKIP_PROBABILITY_THRESHOLD = 0.15  # Skip if P(useful) < 15%
    SKIP_VALIDATION_RATE = 0.10  # Always validate 10% of would-skip decisions
    RETRAIN_INTERVAL = 100  # Retrain every N new samples

    # Quality thresholds for usefulness and tracking
    USEFUL_QUALITY_THRESHOLD = 0.2  # Minimum quality score to be "useful"
    USEFUL_WORD_RATIO_THRESHOLD = 0.2  # Minimum real word ratio to be "useful"
    QUALITY_IMPROVED_THRESHOLD = 0.02  # Delta > this = improved
    QUALITY_REGRESSION_THRESHOLD = -0.02  # Delta < this = regressed

    def __init__(self, db_path: Path | None = None, enabled: bool = True):
        from collections import deque

        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.enabled = enabled
        self._conn = None
        self._classifier = None  # Trained DecisionTreeClassifier model
        self._total_samples = 0  # Total training samples
        self._last_train_count = 0  # Samples at last training

        # Track recent predictions for adaptive exploration rate
        # Each entry: (predicted_prob, was_actually_useful)
        self._recent_predictions: deque[tuple[float, bool]] = deque(maxlen=100)

        # Track sample counts by feature region for UCB exploration bonus
        # Keys are (size_bin, brightness_bin, region) tuples
        from collections import defaultdict
        self._region_sample_counts: dict[tuple[str, str, str], int] = defaultdict(int)

        self._stats = {
            "images_seen": 0,
            "images_skipped": 0,
            "images_ocrd": 0,
            "ocr_useful": 0,       # OCR'd and found useful text
            "ocr_empty": 0,        # OCR'd but no useful text (wasted effort)
            "exploration_ocrs": 0,
            "exploration_useful": 0,  # Exploration found useful text (would've been bad skip)
            "exploration_empty": 0,   # Exploration found nothing (confirms skip OK)
            "skip_validation_ocrs": 0,   # Images explored after "would skip" decision
            "skip_validation_useful": 0, # Skip validations that found useful text (bad skip)
            "quality_regressions": [],  # Files where quality decreased
            "files_with_existing_md": 0,  # Files that had existing .md for comparison
            "quality_improved": 0,   # Count of files where quality improved
            "quality_unchanged": 0,  # Count of files with similar quality
        }

        if self.enabled:
            self._init_db()
            self._load_classifier()

    def _init_db(self):
        """Initialize SQLite database with required tables."""
        import sqlite3

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS ocr_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                pdf_path TEXT NOT NULL,
                page_num INTEGER NOT NULL,
                image_index INTEGER NOT NULL,
                -- Features (stored individually for querying)
                width INTEGER,
                height INTEGER,
                area INTEGER,
                aspect_ratio REAL,
                page_y_center REAL,
                region TEXT,
                surrounding_text_density REAL,
                has_nearby_caption INTEGER,
                brightness_mean REAL,
                brightness_std REAL,
                is_mostly_white INTEGER,
                has_contrast INTEGER,
                -- Outcomes
                ocr_performed INTEGER NOT NULL,
                text_length INTEGER,
                word_count INTEGER,
                is_useful INTEGER,
                cluster_id INTEGER DEFAULT -1,
                -- Index for cleanup
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_ocr_outcomes_timestamp ON ocr_outcomes(timestamp);

            -- Performance indexes for classifier queries
            CREATE INDEX IF NOT EXISTS idx_ocr_outcomes_performed ON ocr_outcomes(ocr_performed);
            CREATE INDEX IF NOT EXISTS idx_ocr_outcomes_region_bins ON ocr_outcomes(ocr_performed, region, area, brightness_mean);

            CREATE TABLE IF NOT EXISTS learning_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            -- Track processed files by content hash to avoid reprocessing
            CREATE TABLE IF NOT EXISTS processed_files (
                file_hash TEXT PRIMARY KEY,
                pdf_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                page_count INTEGER NOT NULL,
                image_count INTEGER NOT NULL,
                processed_at REAL NOT NULL,
                last_seen_at REAL NOT NULL,
                -- Quality tracking columns (added for adaptive learning v2)
                quality_score REAL,
                quality_word_count INTEGER,
                previous_quality_score REAL,
                quality_delta REAL,
                extraction_mode TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_processed_files_path ON processed_files(pdf_path);
        """)

        # Migration: add quality columns to existing databases
        try:
            cursor = self._conn.execute("PRAGMA table_info(processed_files)")
            columns = {row[1] for row in cursor.fetchall()}
            migrations = [
                ("quality_score", "ALTER TABLE processed_files ADD COLUMN quality_score REAL"),
                ("quality_word_count", "ALTER TABLE processed_files ADD COLUMN quality_word_count INTEGER"),
                ("previous_quality_score", "ALTER TABLE processed_files ADD COLUMN previous_quality_score REAL"),
                ("quality_delta", "ALTER TABLE processed_files ADD COLUMN quality_delta REAL"),
                ("extraction_mode", "ALTER TABLE processed_files ADD COLUMN extraction_mode TEXT"),
            ]
            for col_name, sql in migrations:
                if col_name not in columns:
                    self._conn.execute(sql)
            self._conn.commit()
        except Exception:
            pass  # Ignore migration errors on fresh DB
        self._conn.commit()

    def _load_classifier(self):
        """Load or train the classifier from stored data."""
        if not self._conn:
            return

        # Get total sample count
        cursor = self._conn.execute(
            "SELECT COUNT(*) as count FROM ocr_outcomes WHERE ocr_performed = 1"
        )
        self._total_samples = cursor.fetchone()["count"]

        # Try to load saved classifier
        import pickle
        import base64
        cursor = self._conn.execute(
            "SELECT value FROM learning_meta WHERE key = 'classifier'"
        )
        row = cursor.fetchone()
        if row:
            try:
                self._classifier = pickle.loads(base64.b64decode(row["value"]))
                cursor = self._conn.execute(
                    "SELECT value FROM learning_meta WHERE key = 'last_train_count'"
                )
                row = cursor.fetchone()
                if row:
                    self._last_train_count = int(row["value"])
            except Exception:
                self._classifier = None

        # Load region sample counts for UCB exploration bonus
        self._load_region_sample_counts()

        # Retrain if needed
        if self._total_samples >= self.MIN_SAMPLES_FOR_PREDICTION:
            if self._classifier is None or (self._total_samples - self._last_train_count) >= self.RETRAIN_INTERVAL:
                self._train_classifier()

    def _load_region_sample_counts(self):
        """Load region sample counts from database for UCB exploration bonus."""
        if not self._conn:
            return

        # Query database to compute region sample counts
        # Bins: area -> small/medium/large, brightness -> dark/medium/bright, region
        cursor = self._conn.execute("""
            SELECT
                CASE
                    WHEN area < 10000 THEN 'small'
                    WHEN area < 50000 THEN 'medium'
                    ELSE 'large'
                END as size_bin,
                CASE
                    WHEN brightness_mean < 100 THEN 'dark'
                    WHEN brightness_mean < 200 THEN 'medium'
                    ELSE 'bright'
                END as brightness_bin,
                region,
                COUNT(*) as count
            FROM ocr_outcomes
            WHERE ocr_performed = 1
            GROUP BY size_bin, brightness_bin, region
        """)

        self._region_sample_counts.clear()
        for row in cursor:
            key = (row["size_bin"], row["brightness_bin"], row["region"])
            self._region_sample_counts[key] = row["count"]

    def _train_classifier(self):
        """Train decision tree classifier on OCR outcomes."""
        if not self._conn or self._total_samples < self.MIN_SAMPLES_FOR_PREDICTION:
            return

        try:
            from sklearn.tree import DecisionTreeClassifier
            import numpy as np
        except ImportError:
            # sklearn not available, fall back to heuristics
            return

        # Get training data
        cursor = self._conn.execute("""
            SELECT width, height, area, aspect_ratio, page_y_center, region,
                   surrounding_text_density, has_nearby_caption,
                   brightness_mean, brightness_std, is_mostly_white, has_contrast,
                   is_useful
            FROM ocr_outcomes
            WHERE ocr_performed = 1
        """)

        X = []
        y = []
        for row in cursor:
            features = ImageFeature(
                width=row["width"],
                height=row["height"],
                area=row["area"],
                aspect_ratio=row["aspect_ratio"],
                page_y_center=row["page_y_center"],
                region=row["region"],
                surrounding_text_density=row["surrounding_text_density"],
                has_nearby_caption=bool(row["has_nearby_caption"]),
                brightness_mean=row["brightness_mean"],
                brightness_std=row["brightness_std"],
                is_mostly_white=bool(row["is_mostly_white"]),
                has_contrast=bool(row["has_contrast"]),
            )
            X.append(features.to_vector())
            y.append(1 if row["is_useful"] else 0)

        if len(X) < self.MIN_SAMPLES_FOR_PREDICTION:
            return

        X = np.array(X)
        y = np.array(y)

        # Train decision tree classifier
        # Decision trees naturally handle non-linear boundaries and provide
        # well-calibrated probabilities from leaf node class distributions
        self._classifier = DecisionTreeClassifier(
            class_weight='balanced',  # Handle imbalanced classes
            max_depth=10,  # Prevent overfitting while capturing patterns
            random_state=42,
        )
        self._classifier.fit(X, y)

        self._last_train_count = len(X)

        # Save classifier to database
        self._save_classifier()

    def _save_classifier(self):
        """Save trained classifier to database."""
        if not self._conn or not self._classifier:
            return

        import pickle
        import base64
        classifier_data = base64.b64encode(pickle.dumps(self._classifier)).decode('ascii')
        self._conn.execute(
            "INSERT OR REPLACE INTO learning_meta (key, value) VALUES (?, ?)",
            ("classifier", classifier_data)
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO learning_meta (key, value) VALUES (?, ?)",
            ("last_train_count", str(self._last_train_count))
        )
        self._conn.commit()

    def _exploration_rate(self) -> float:
        """Calculate sample-based exploration rate (exponential decay)."""
        if self._total_samples < self.MIN_SAMPLES_FOR_PREDICTION:
            return self.MAX_EXPLORATION_RATE  # Explore heavily when learning
        # Exponential decay: halve every EXPLORATION_HALFLIFE samples
        decay_factor = 0.5 ** (self._total_samples / self.EXPLORATION_HALFLIFE)
        rate = self.MAX_EXPLORATION_RATE * decay_factor
        return max(self.MIN_EXPLORATION_RATE, rate)

    def _adaptive_exploration_rate(self) -> float:
        """Calculate exploration rate blending sample decay with recent accuracy.

        If classifier has been frequently wrong recently, increase exploration
        to prevent premature convergence on bad predictions.
        """
        sample_rate = self._exploration_rate()

        # Not enough recent predictions to assess accuracy
        if len(self._recent_predictions) < 20:
            return sample_rate

        # Calculate error rate: how often predictions were wrong
        # Error = predicted skip (p < 0.5) but was actually useful, or
        #         predicted useful (p >= 0.5) but was actually useless
        errors = sum(
            1 for pred_prob, actual in self._recent_predictions
            if (pred_prob < 0.5) == actual  # predicted skip but useful, or predicted keep but useless
        )
        error_rate = errors / len(self._recent_predictions)

        # Boost exploration based on error rate:
        # - Low error (< 10%): minimal boost
        # - Medium error (10-30%): moderate boost up to +15%
        # - High error (30-50%): aggressive boost up to +30%
        # - Very high error (> 50%): corpus mismatch, boost to near-max exploration
        if error_rate > 0.50:
            # Corpus mismatch detected - classifier is very wrong
            # Boost exploration aggressively to gather new training data
            boosted_rate = max(0.35, sample_rate + 0.30)
        elif error_rate > 0.30:
            # High error - significant boost
            boosted_rate = sample_rate + error_rate * 0.50
        else:
            # Normal operation - moderate boost
            boosted_rate = sample_rate + error_rate * 0.30

        return max(self.MIN_EXPLORATION_RATE, min(self.MAX_EXPLORATION_RATE, boosted_rate))

    def _adaptive_skip_validation_rate(self) -> float:
        """Calculate adaptive skip validation rate based on observed error rate.

        If the classifier is frequently wrong on skip decisions (i.e., we're
        skipping images that turn out to be useful), increase validation rate.
        If skip accuracy is high, we can reduce validation overhead.
        """
        total = self._stats.get("skip_validation_ocrs", 0)
        useful = self._stats.get("skip_validation_useful", 0)

        # Not enough data - use default rate
        if total < 20:
            return self.SKIP_VALIDATION_RATE

        error_rate = useful / total  # How often skips were wrong

        # Very high error rate (> 30%) indicates corpus mismatch
        # In this case, validate much more aggressively
        if error_rate > 0.30:
            # Corpus mismatch - validate 30-50% of skips
            return min(0.50, 0.30 + (error_rate - 0.30))

        # Target: 10% error rate on skips is acceptable
        # If errors are high, validate more; if low, validate less
        TARGET_ERROR_RATE = 0.10
        adjustment = (error_rate / TARGET_ERROR_RATE) ** 0.5 if TARGET_ERROR_RATE > 0 else 1.0

        # Clamp between 5% and 50%
        return max(0.05, min(0.50, self.SKIP_VALIDATION_RATE * adjustment))

    def _get_feature_region_key(self, features: ImageFeature) -> tuple[str, str, str]:
        """Get a binning key for feature region tracking.

        Bins images by size (small/medium/large), brightness (dark/medium/bright),
        and page region (header/body/footer/margin).
        """
        # Size bins based on area
        if features.area < 10000:
            size_bin = "small"
        elif features.area < 50000:
            size_bin = "medium"
        else:
            size_bin = "large"

        # Brightness bins
        if features.brightness_mean < 100:
            brightness_bin = "dark"
        elif features.brightness_mean < 200:
            brightness_bin = "medium"
        else:
            brightness_bin = "bright"

        return (size_bin, brightness_bin, features.region)

    def _ucb_bonus(self, features: ImageFeature) -> float:
        """Calculate UCB1 exploration bonus for under-sampled feature regions.

        Uses the UCB1 formula: sqrt(2 * ln(N) / n_i)
        where N is total samples and n_i is samples in this region.

        Returns a bonus (0 to 0.3) that increases exploration probability
        for regions with few samples.
        """
        region_key = self._get_feature_region_key(features)
        region_samples = self._region_sample_counts.get(region_key, 0)

        # Maximum bonus for completely unexplored regions
        if region_samples < 5:
            return 0.30

        # Not enough total samples for meaningful UCB calculation
        if self._total_samples < 30:
            return 0.15

        # UCB1 formula with beta=2.0 for exploration emphasis
        beta = 2.0
        ucb_value = math.sqrt(beta * math.log(self._total_samples) / region_samples)

        # Clamp to [0, 0.3] range
        return min(0.30, ucb_value)

    def _should_explore_uncertainty(self, prob_useful: float, features: ImageFeature | None = None) -> bool:
        """Determine if we should explore based on prediction uncertainty and UCB bonus.

        Explores more when:
        1. Predictions are uncertain (near 0.5)
        2. Feature region is under-sampled (UCB bonus)

        This focuses exploration budget on edge cases and unexplored regions
        rather than random images.
        """
        base_rate = self._adaptive_exploration_rate()

        # Uncertainty is highest (1.0) when prob is 0.5, lowest (0.0) at 0 or 1
        uncertainty = 1 - abs(prob_useful - 0.5) * 2

        # Add UCB bonus for under-sampled regions
        ucb_bonus = self._ucb_bonus(features) if features else 0.0

        # Combine uncertainty-scaled rate with UCB bonus
        # uncertainty * base_rate * 4 gives exploration for uncertain predictions
        # ucb_bonus adds extra exploration for under-sampled regions
        effective_rate = (uncertainty * base_rate * 4) + ucb_bonus

        return random.random() < effective_rate

    def should_ocr(self, features: ImageFeature) -> tuple[bool, str, bool]:
        """Decide whether to OCR this image.

        Returns:
            Tuple of (should_ocr, reason, is_exploration)
        """
        if not self.enabled:
            return True, "learning disabled", False

        self._stats["images_seen"] += 1

        # Not enough data yet - use heuristics with random exploration
        if self._total_samples < self.MIN_SAMPLES_FOR_PREDICTION:
            current_exploration_rate = self._exploration_rate()
            if random.random() < current_exploration_rate:
                self._stats["exploration_ocrs"] += 1
                return True, f"exploration ({current_exploration_rate:.0%})", True
            should, reason = self._heuristic_decision(features)
            return should, reason, False

        # No classifier trained yet - use heuristics with random exploration
        if self._classifier is None:
            current_exploration_rate = self._exploration_rate()
            if random.random() < current_exploration_rate:
                self._stats["exploration_ocrs"] += 1
                return True, f"exploration ({current_exploration_rate:.0%})", True
            should, reason = self._heuristic_decision(features)
            return should, reason, False

        # Use classifier to predict probability of usefulness
        try:
            import numpy as np
            feature_vector = np.array([features.to_vector()])
            prob_useful = self._classifier.predict_proba(feature_vector)[0][1]

            # Uncertainty-based exploration: explore more on edge cases and under-sampled regions
            if self._should_explore_uncertainty(prob_useful, features):
                self._stats["exploration_ocrs"] += 1
                return True, f"uncertainty exploration (p={prob_useful:.0%})", True

            # Skip only if very likely to be useless
            if prob_useful < self.SKIP_PROBABILITY_THRESHOLD:
                # Force exploration of some "would skip" decisions to validate classifier
                # This prevents the classifier from never learning when skips are wrong
                # Use adaptive rate: increase validation if skip errors are high
                skip_validation_rate = self._adaptive_skip_validation_rate()
                if random.random() < skip_validation_rate:
                    self._stats["skip_validation_ocrs"] += 1
                    return True, f"skip-validation (p={prob_useful:.0%}, rate={skip_validation_rate:.0%})", True
                self._stats["images_skipped"] += 1
                return False, f"classifier: {prob_useful:.0%} useful", False

            self._stats["images_ocrd"] += 1
            return True, f"classifier: {prob_useful:.0%} useful", False
        except Exception:
            # Fallback to heuristics if prediction fails
            should, reason = self._heuristic_decision(features)
            return should, reason, False

    def _heuristic_decision(self, features: ImageFeature) -> tuple[bool, str]:
        """Fallback heuristics when not enough learning data."""
        # Skip tiny images (likely icons/bullets)
        if features.area < 400:  # 20x20
            self._stats["images_skipped"] += 1
            return False, "heuristic: tiny image"

        # Skip small header/footer images (logos, decorations)
        # Data: header <10K = 13.6% useful, footer <10K = 7.3% useful
        if features.region in ("header", "footer") and features.area < 10000:
            self._stats["images_skipped"] += 1
            return False, "heuristic: small header/footer"

        # Skip wide decorative strips in header/footer
        # Data: wide header/footer (aspect>2) = 0% useful
        if features.region in ("header", "footer") and features.aspect_ratio > 2:
            self._stats["images_skipped"] += 1
            return False, "heuristic: wide decoration"

        # Skip very small body images
        # Data: body <2.5K = 0% useful
        if features.region == "body" and features.area < 2500:
            self._stats["images_skipped"] += 1
            return False, "heuristic: small body image"

        # Skip dark large images (photos, diagrams without text)
        # Data: brightness<150 + area>50K = only 4% useful
        if features.area > 50000 and features.brightness_mean < 150:
            self._stats["images_skipped"] += 1
            return False, "heuristic: dark large image"

        # Skip mostly-white images with no contrast (likely blank/whitespace)
        if features.is_mostly_white and not features.has_contrast:
            self._stats["images_skipped"] += 1
            return False, "heuristic: blank/white"

        # Skip margin decorations (narrow aspect ratio in margins)
        if features.region == "margin" and (features.aspect_ratio > 5 or features.aspect_ratio < 0.2):
            self._stats["images_skipped"] += 1
            return False, "heuristic: margin decoration"

        self._stats["images_ocrd"] += 1
        return True, "heuristic: worth trying"

    def record_outcome(
        self,
        features: ImageFeature,
        pdf_path: str,
        page_num: int,
        image_index: int,
        ocr_performed: bool,
        text: str,
        is_exploration: bool = False,
        reason: str = "",
    ):
        """Record the outcome of an OCR decision."""
        if not self.enabled or not self._conn:
            return

        text_length = len(text) if text else 0
        word_count = len(text.split()) if text else 0

        # Use TextQualityScorer for better usefulness determination
        # Old: is_useful = text_length > 10 and word_count >= 2
        # New: quality_score > threshold and real_word_ratio > threshold
        if text and text.strip():
            metrics = _quality_scorer.score(text)
            is_useful = (metrics.total_score > self.USEFUL_QUALITY_THRESHOLD and
                        metrics.real_word_ratio > self.USEFUL_WORD_RATIO_THRESHOLD)
        else:
            is_useful = False

        # Track accuracy metrics
        if ocr_performed:
            if is_useful:
                self._stats["ocr_useful"] += 1
            else:
                self._stats["ocr_empty"] += 1

            # Track skip validation accuracy (images that would've been skipped)
            if reason.startswith("skip-validation"):
                if is_useful:
                    self._stats["skip_validation_useful"] += 1  # Bad skip prevented
            # Track general exploration accuracy separately
            elif is_exploration:
                if is_useful:
                    self._stats["exploration_useful"] += 1  # Would've been bad to skip
                else:
                    self._stats["exploration_empty"] += 1   # Confirms skipping is OK

            # Track predictions for adaptive exploration rate
            # Extract probability from reason if it's a classifier-based decision
            # Reason formats: "classifier: X% useful", "skip-validation (p=X%...)", "uncertainty exploration (p=X%)"
            pred_prob = None
            if "classifier:" in reason:
                # "classifier: 75% useful" -> 0.75
                match = re.search(r'(\d+)%', reason)
                if match:
                    pred_prob = int(match.group(1)) / 100.0
            elif "p=" in reason:
                # "skip-validation (p=12%...)" or "uncertainty exploration (p=48%)"
                match = re.search(r'p=(\d+)%', reason)
                if match:
                    pred_prob = int(match.group(1)) / 100.0

            if pred_prob is not None:
                self._recent_predictions.append((pred_prob, is_useful))

        # Insert outcome record
        self._conn.execute("""
            INSERT INTO ocr_outcomes (
                timestamp, pdf_path, page_num, image_index,
                width, height, area, aspect_ratio, page_y_center, region,
                surrounding_text_density, has_nearby_caption,
                brightness_mean, brightness_std, is_mostly_white, has_contrast,
                ocr_performed, text_length, word_count, is_useful, cluster_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time(), pdf_path, page_num, image_index,
            features.width, features.height, features.area, features.aspect_ratio,
            features.page_y_center, features.region,
            features.surrounding_text_density, int(features.has_nearby_caption),
            features.brightness_mean, features.brightness_std,
            int(features.is_mostly_white), int(features.has_contrast),
            int(ocr_performed), text_length, word_count, int(is_useful), -1,  # cluster_id deprecated
        ))
        self._conn.commit()

        # Update sample count and potentially retrain classifier
        if ocr_performed:
            self._total_samples += 1

            # Track region sample counts for UCB exploration bonus
            region_key = self._get_feature_region_key(features)
            self._region_sample_counts[region_key] += 1

            if self._total_samples >= self.MIN_SAMPLES_FOR_PREDICTION:
                if (self._total_samples - self._last_train_count) >= self.RETRAIN_INTERVAL:
                    self._train_classifier()

    def retrain(self, force: bool = False):
        """Retrain the classifier on all outcomes.

        Called to force a classifier update.
        """
        if not self.enabled or not self._conn:
            return

        if force or self._total_samples >= self.MIN_SAMPLES_FOR_PREDICTION:
            self._train_classifier()

    @staticmethod
    def compute_file_hash(pdf_path: Path) -> str:
        """Compute MD5 hash of a PDF file for deduplication."""
        import hashlib
        hasher = hashlib.md5()
        with open(pdf_path, "rb") as f:
            # Read in chunks for memory efficiency
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def is_file_processed(self, pdf_path: Path) -> bool:
        """Check if a file has already been processed (by content hash)."""
        if not self.enabled or not self._conn:
            return False

        file_hash = self.compute_file_hash(pdf_path)
        cursor = self._conn.execute(
            "SELECT file_hash FROM processed_files WHERE file_hash = ?",
            (file_hash,)
        )
        exists = cursor.fetchone() is not None

        if exists:
            # Update last_seen_at timestamp
            self._conn.execute(
                "UPDATE processed_files SET last_seen_at = ?, pdf_path = ? WHERE file_hash = ?",
                (time.time(), str(pdf_path), file_hash)
            )
            self._conn.commit()

        return exists

    def record_file_processed(
        self,
        pdf_path: Path,
        page_count: int,
        image_count: int,
        quality_score: float | None = None,
        quality_word_count: int | None = None,
        previous_quality_score: float | None = None,
        extraction_mode: str | None = None,
    ):
        """Record that a file has been processed with quality metrics."""
        if not self.enabled or not self._conn:
            return

        file_hash = self.compute_file_hash(pdf_path)
        file_size = pdf_path.stat().st_size
        now = time.time()

        # Compute quality delta if we have both scores
        quality_delta = None
        if quality_score is not None and previous_quality_score is not None:
            quality_delta = quality_score - previous_quality_score

        self._conn.execute("""
            INSERT OR REPLACE INTO processed_files
            (file_hash, pdf_path, file_size, page_count, image_count, processed_at, last_seen_at,
             quality_score, quality_word_count, previous_quality_score, quality_delta, extraction_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (file_hash, str(pdf_path), file_size, page_count, image_count, now, now,
              quality_score, quality_word_count, previous_quality_score, quality_delta, extraction_mode))
        self._conn.commit()

        # Track quality regressions in session stats
        if quality_delta is not None and quality_delta < self.QUALITY_REGRESSION_THRESHOLD:
            self._stats["quality_regressions"].append({
                "path": str(pdf_path),
                "old_score": previous_quality_score,
                "new_score": quality_score,
                "delta": quality_delta,
            })

    def get_stats(self) -> dict:
        """Get learning statistics for display."""
        if not self.enabled or not self._conn:
            return {"enabled": False}

        cursor = self._conn.execute("SELECT COUNT(*) as total FROM ocr_outcomes")
        total_records = cursor.fetchone()["total"]

        cursor = self._conn.execute(
            "SELECT COUNT(*) as useful FROM ocr_outcomes WHERE is_useful = 1 AND ocr_performed = 1"
        )
        useful_records = cursor.fetchone()["useful"]

        cursor = self._conn.execute(
            "SELECT COUNT(*) as ocrd FROM ocr_outcomes WHERE ocr_performed = 1"
        )
        ocrd_records = cursor.fetchone()["ocrd"]

        # Get processed files stats
        cursor = self._conn.execute("SELECT COUNT(*) as count FROM processed_files")
        processed_files_count = cursor.fetchone()["count"]

        cursor = self._conn.execute(
            "SELECT SUM(page_count) as pages, SUM(image_count) as images FROM processed_files"
        )
        row = cursor.fetchone()
        total_pages = row["pages"] or 0
        total_images = row["images"] or 0

        # Classifier info
        classifier_ready = self._classifier is not None
        current_exploration_rate = self._exploration_rate()

        # Check if sklearn is available and capture any import errors
        sklearn_available = True
        sklearn_error = None
        try:
            from sklearn.tree import DecisionTreeClassifier  # noqa
        except ImportError as e:
            sklearn_available = False
            sklearn_error = str(e)

        # Quality tracking stats from database
        # Use thresholds from class constants
        imp_thresh = self.QUALITY_IMPROVED_THRESHOLD
        reg_thresh = self.QUALITY_REGRESSION_THRESHOLD
        cursor = self._conn.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN previous_quality_score IS NOT NULL THEN 1 END) as with_comparison,
                AVG(quality_score) as avg_quality,
                COUNT(CASE WHEN quality_delta > ? THEN 1 END) as improved,
                COUNT(CASE WHEN quality_delta BETWEEN ? AND ? THEN 1 END) as unchanged,
                COUNT(CASE WHEN quality_delta < ? THEN 1 END) as regressed,
                AVG(CASE WHEN quality_delta > ? THEN quality_delta END) as avg_improvement,
                AVG(CASE WHEN quality_delta < ? THEN quality_delta END) as avg_regression
            FROM processed_files
            WHERE quality_score IS NOT NULL
        """, (imp_thresh, reg_thresh, imp_thresh, reg_thresh, imp_thresh, reg_thresh))
        quality_row = cursor.fetchone()

        quality_stats = {
            "files_with_quality": quality_row["total"] or 0,
            "files_with_comparison": quality_row["with_comparison"] or 0,
            "avg_quality_score": quality_row["avg_quality"] or 0,
            "quality_improved": quality_row["improved"] or 0,
            "quality_unchanged": quality_row["unchanged"] or 0,
            "quality_regressed": quality_row["regressed"] or 0,
            "avg_improvement": quality_row["avg_improvement"] or 0,
            "avg_regression": quality_row["avg_regression"] or 0,
        }

        # Calculate skip accuracy: % of skipped images that didn't hurt quality
        # If exploration finds useful text = bad skip decision
        # Skip accuracy = 1 - (exploration_useful / exploration_total)
        exp_total = self._stats.get("exploration_useful", 0) + self._stats.get("exploration_empty", 0)
        if exp_total > 0:
            skip_accuracy = 1 - (self._stats.get("exploration_useful", 0) / exp_total)
        else:
            skip_accuracy = None

        # Skip validation stats: how often "would skip" decisions were actually useful
        skip_val_total = self._stats.get("skip_validation_ocrs", 0)
        skip_val_useful = self._stats.get("skip_validation_useful", 0)
        if skip_val_total > 0:
            skip_validation_error_rate = skip_val_useful / skip_val_total
        else:
            skip_validation_error_rate = None

        return {
            "enabled": True,
            "db_path": str(self.db_path),
            "total_records": total_records,
            "ocrd_records": ocrd_records,
            "useful_records": useful_records,
            "overall_useful_rate": useful_records / max(ocrd_records, 1),
            "classifier_ready": classifier_ready,
            "sklearn_available": sklearn_available,
            "sklearn_error": sklearn_error,
            "training_samples": self._total_samples,
            "last_train_count": self._last_train_count,
            "exploration_rate": current_exploration_rate,
            "session_stats": self._stats.copy(),
            "processed_files": processed_files_count,
            "total_pages_processed": total_pages,
            "total_images_seen": total_images,
            "quality_stats": quality_stats,
            "skip_accuracy": skip_accuracy,
            "skip_validation_total": skip_val_total,
            "skip_validation_useful": skip_val_useful,
            "skip_validation_error_rate": skip_validation_error_rate,
        }

    def reset(self):
        """Reset the learning database."""
        if self._conn:
            self._conn.close()
            self._conn = None

        if self.db_path.exists():
            self.db_path.unlink()

        self._classifier = None
        self._total_samples = 0
        self._last_train_count = 0
        self._recent_predictions.clear()
        self._region_sample_counts.clear()
        self._stats = {
            "images_seen": 0,
            "images_skipped": 0,
            "images_ocrd": 0,
            "ocr_useful": 0,
            "ocr_empty": 0,
            "exploration_ocrs": 0,
            "exploration_useful": 0,
            "exploration_empty": 0,
            "skip_validation_ocrs": 0,
            "skip_validation_useful": 0,
            "quality_regressions": [],
            "files_with_existing_md": 0,
            "quality_improved": 0,
            "quality_unchanged": 0,
        }

        if self.enabled:
            self._init_db()

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
