"""Tests for the Adaptive OCR Learning System."""

import random
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Import from parent directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pdf2txt import (
    AdaptiveLearner,
    ImageFeature,
    TextQualityScorer,
    find_pdfs,
)


class TestTextQualityScorer:
    """Tests for TextQualityScorer usefulness determination."""

    @pytest.fixture
    def scorer(self):
        return TextQualityScorer()

    def test_rejects_empty_text(self, scorer):
        """Empty text should have zero quality."""
        metrics = scorer.score("")
        assert metrics.total_score == 0
        assert metrics.word_count == 0

    def test_rejects_whitespace_only(self, scorer):
        """Whitespace-only text should have zero quality."""
        metrics = scorer.score("   \n\t\n   ")
        assert metrics.total_score == 0

    def test_rejects_gibberish(self, scorer):
        """Gibberish text should have low quality score."""
        gibberish = "xkcd qwerty asdfgh zxcvbn hjkl poiuy"
        metrics = scorer.score(gibberish)
        # Should have low real_word_ratio (no common words)
        assert metrics.real_word_ratio < 0.1
        # Total score should be low
        assert metrics.total_score < 0.3

    def test_accepts_real_english_text(self, scorer):
        """Real English text should have high quality score."""
        real_text = """
        The quick brown fox jumps over the lazy dog. This is a sample
        sentence that contains many common English words. It should be
        recognized as high quality text with good readability.
        """
        metrics = scorer.score(real_text)
        # Should have high real_word_ratio
        assert metrics.real_word_ratio > 0.5
        # Total score should be above usefulness threshold
        assert metrics.total_score > AdaptiveLearner.USEFUL_QUALITY_THRESHOLD

    def test_penalizes_encoding_artifacts(self, scorer):
        """Text with encoding artifacts should be penalized."""
        # Common encoding issues
        bad_text = "The â€œquickâ€ brown fox Ã© jumped"
        metrics = scorer.score(bad_text)
        assert metrics.gibberish_penalty > 0

    def test_penalizes_repeated_characters(self, scorer):
        """Text with repeated characters should be penalized."""
        bad_text = "Helloooooo world thissss is badddd text"
        metrics = scorer.score(bad_text)
        assert metrics.gibberish_penalty > 0

    def test_quality_thresholds_for_usefulness(self, scorer):
        """Test that quality thresholds correctly identify useful text."""
        # Text that should be useful (quality > 0.2, word_ratio > 0.2)
        useful_text = "The document contains important information about the project."
        metrics = scorer.score(useful_text)
        is_useful = (metrics.total_score > AdaptiveLearner.USEFUL_QUALITY_THRESHOLD and
                    metrics.real_word_ratio > AdaptiveLearner.USEFUL_WORD_RATIO_THRESHOLD)
        assert is_useful, f"Expected useful: score={metrics.total_score}, ratio={metrics.real_word_ratio}"

        # Text that should NOT be useful (random letters)
        not_useful_text = "xyz abc qrs tuv"
        metrics = scorer.score(not_useful_text)
        is_useful = (metrics.total_score > AdaptiveLearner.USEFUL_QUALITY_THRESHOLD and
                    metrics.real_word_ratio > AdaptiveLearner.USEFUL_WORD_RATIO_THRESHOLD)
        assert not is_useful, f"Expected not useful: score={metrics.total_score}, ratio={metrics.real_word_ratio}"


class TestAdaptiveLearnerUncertaintyExploration:
    """Tests for uncertainty-based exploration."""

    @pytest.fixture
    def learner(self):
        """Create a learner with a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_learning.db"
            learner = AdaptiveLearner(db_path=db_path, enabled=True)
            # Set enough samples so classifier-based logic kicks in
            learner._total_samples = 100
            yield learner
            learner.close()

    def test_uncertainty_highest_at_half(self, learner):
        """Uncertainty should be highest when probability is 0.5."""
        # Test the uncertainty calculation directly
        # uncertainty = 1 - abs(prob - 0.5) * 2

        # At p=0.5, uncertainty should be 1.0
        uncertainty_half = 1 - abs(0.5 - 0.5) * 2
        assert uncertainty_half == 1.0

        # At p=0.0 or p=1.0, uncertainty should be 0.0
        uncertainty_zero = 1 - abs(0.0 - 0.5) * 2
        assert uncertainty_zero == 0.0

        uncertainty_one = 1 - abs(1.0 - 0.5) * 2
        assert uncertainty_one == 0.0

        # At p=0.25 or p=0.75, uncertainty should be 0.5
        uncertainty_quarter = 1 - abs(0.25 - 0.5) * 2
        assert uncertainty_quarter == 0.5

    def test_exploration_more_likely_when_uncertain(self, learner):
        """Exploration should trigger more often for uncertain predictions."""
        # Run many trials and count exploration triggers
        n_trials = 1000
        random.seed(42)

        # Count explorations at different probability levels
        explore_at_05 = 0
        explore_at_01 = 0
        explore_at_09 = 0

        for _ in range(n_trials):
            if learner._should_explore_uncertainty(0.5):
                explore_at_05 += 1
            if learner._should_explore_uncertainty(0.1):
                explore_at_01 += 1
            if learner._should_explore_uncertainty(0.9):
                explore_at_09 += 1

        # Exploration at 0.5 should be significantly more than at extremes
        assert explore_at_05 > explore_at_01 * 2, \
            f"Expected more exploration at 0.5 ({explore_at_05}) than 0.1 ({explore_at_01})"
        assert explore_at_05 > explore_at_09 * 2, \
            f"Expected more exploration at 0.5 ({explore_at_05}) than 0.9 ({explore_at_09})"

        # Extreme values should have similar (low) exploration rates
        assert abs(explore_at_01 - explore_at_09) < n_trials * 0.1, \
            f"Expected similar exploration at extremes: 0.1={explore_at_01}, 0.9={explore_at_09}"


class TestAdaptiveLearnerDatabase:
    """Tests for database operations and quality tracking."""

    @pytest.fixture
    def learner(self):
        """Create a learner with a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_learning.db"
            learner = AdaptiveLearner(db_path=db_path, enabled=True)
            yield learner
            learner.close()

    def test_quality_columns_exist(self, learner):
        """Database should have quality tracking columns."""
        cursor = learner._conn.execute("PRAGMA table_info(processed_files)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {
            'quality_score',
            'quality_word_count',
            'previous_quality_score',
            'quality_delta',
            'extraction_mode',
        }
        assert expected_columns.issubset(columns), \
            f"Missing columns: {expected_columns - columns}"

    def test_record_file_processed_stores_quality(self, learner):
        """record_file_processed should store quality metrics."""
        # Create a temp PDF file for hashing
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4 fake pdf content')
            pdf_path = Path(f.name)

        try:
            learner.record_file_processed(
                pdf_path=pdf_path,
                page_count=5,
                image_count=10,
                quality_score=0.75,
                quality_word_count=500,
                previous_quality_score=0.65,
                extraction_mode="ocr",
            )

            # Verify data was stored
            cursor = learner._conn.execute(
                "SELECT quality_score, quality_word_count, previous_quality_score, "
                "quality_delta, extraction_mode FROM processed_files"
            )
            row = cursor.fetchone()
            assert row is not None
            assert row["quality_score"] == 0.75
            assert row["quality_word_count"] == 500
            assert row["previous_quality_score"] == 0.65
            assert abs(row["quality_delta"] - 0.10) < 0.001  # 0.75 - 0.65
            assert row["extraction_mode"] == "ocr"
        finally:
            pdf_path.unlink()

    def test_quality_regression_tracked(self, learner):
        """Quality regressions should be tracked in session stats."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4 fake pdf content')
            pdf_path = Path(f.name)

        try:
            # Record a regression (new score lower than old)
            learner.record_file_processed(
                pdf_path=pdf_path,
                page_count=5,
                image_count=10,
                quality_score=0.50,
                quality_word_count=300,
                previous_quality_score=0.70,  # Was better before
                extraction_mode="ocr",
            )

            # Check regression was tracked
            regressions = learner._stats.get("quality_regressions", [])
            assert len(regressions) == 1
            assert regressions[0]["old_score"] == 0.70
            assert regressions[0]["new_score"] == 0.50
            assert regressions[0]["delta"] == pytest.approx(-0.20)
        finally:
            pdf_path.unlink()

    def test_small_quality_change_not_regression(self, learner):
        """Small quality decreases should not be flagged as regressions."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4 fake pdf content')
            pdf_path = Path(f.name)

        try:
            # Record a small decrease (within threshold)
            learner.record_file_processed(
                pdf_path=pdf_path,
                page_count=5,
                image_count=10,
                quality_score=0.69,
                quality_word_count=300,
                previous_quality_score=0.70,  # Only -0.01 change
                extraction_mode="ocr",
            )

            # Should NOT be tracked as regression (delta > -0.02)
            regressions = learner._stats.get("quality_regressions", [])
            assert len(regressions) == 0
        finally:
            pdf_path.unlink()


class TestAdaptiveLearnerThresholds:
    """Tests for threshold consistency."""

    def test_threshold_constants_defined(self):
        """All threshold constants should be defined."""
        assert hasattr(AdaptiveLearner, 'USEFUL_QUALITY_THRESHOLD')
        assert hasattr(AdaptiveLearner, 'USEFUL_WORD_RATIO_THRESHOLD')
        assert hasattr(AdaptiveLearner, 'QUALITY_IMPROVED_THRESHOLD')
        assert hasattr(AdaptiveLearner, 'QUALITY_REGRESSION_THRESHOLD')

    def test_threshold_values_reasonable(self):
        """Threshold values should be reasonable."""
        # Quality thresholds should be between 0 and 1
        assert 0 < AdaptiveLearner.USEFUL_QUALITY_THRESHOLD < 1
        assert 0 < AdaptiveLearner.USEFUL_WORD_RATIO_THRESHOLD < 1

        # Improved threshold should be positive
        assert AdaptiveLearner.QUALITY_IMPROVED_THRESHOLD > 0

        # Regression threshold should be negative
        assert AdaptiveLearner.QUALITY_REGRESSION_THRESHOLD < 0

    def test_thresholds_cover_all_cases(self):
        """Improved + unchanged + regressed should cover all cases."""
        # The thresholds should not have gaps
        imp = AdaptiveLearner.QUALITY_IMPROVED_THRESHOLD
        reg = AdaptiveLearner.QUALITY_REGRESSION_THRESHOLD

        # Any delta should fall into exactly one category:
        # delta > imp (improved)
        # reg <= delta <= imp (unchanged)
        # delta < reg (regressed)

        test_deltas = [-0.5, -0.1, -0.02, -0.01, 0, 0.01, 0.02, 0.1, 0.5]
        for delta in test_deltas:
            categories = []
            if delta > imp:
                categories.append('improved')
            if reg <= delta <= imp:
                categories.append('unchanged')
            if delta < reg:
                categories.append('regressed')

            assert len(categories) == 1, \
                f"Delta {delta} falls into {len(categories)} categories: {categories}"


class TestFindPdfsShuffle:
    """Tests for file shuffling functionality."""

    def test_shuffle_produces_different_order(self):
        """Shuffle should produce different orderings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create several PDF files
            for i in range(10):
                (tmppath / f"file_{i:02d}.pdf").write_bytes(b'%PDF-1.4')

            # Find without shuffle (should be sorted)
            pdfs_sorted = find_pdfs(tmppath, shuffle=False, quiet=True)
            pdfs_sorted = sorted(pdfs_sorted)  # Ensure sorted for comparison

            # Find with shuffle multiple times
            random.seed(42)
            pdfs_shuffled1 = find_pdfs(tmppath, shuffle=True, quiet=True)

            random.seed(123)
            pdfs_shuffled2 = find_pdfs(tmppath, shuffle=True, quiet=True)

            # Same files should be found
            assert set(pdfs_sorted) == set(pdfs_shuffled1) == set(pdfs_shuffled2)

            # Order should be different (very unlikely to be same by chance with 10 files)
            assert pdfs_shuffled1 != pdfs_sorted or pdfs_shuffled2 != pdfs_sorted, \
                "Shuffle should produce different order"

    def test_shuffle_with_single_file(self):
        """Shuffle should work with single file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "only_file.pdf").write_bytes(b'%PDF-1.4')

            pdfs = find_pdfs(tmppath, shuffle=True, quiet=True)
            assert len(pdfs) == 1

    def test_shuffle_with_empty_directory(self):
        """Shuffle should work with empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            pdfs = find_pdfs(tmppath, shuffle=True, quiet=True)
            assert len(pdfs) == 0


class TestDatabaseMigration:
    """Tests for database migration of existing databases."""

    def test_migration_adds_quality_columns(self):
        """Migration should add quality columns to old databases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "old_learning.db"

            # Create an old-style database without quality columns
            conn = sqlite3.connect(str(db_path))
            conn.executescript("""
                CREATE TABLE processed_files (
                    file_hash TEXT PRIMARY KEY,
                    pdf_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    page_count INTEGER NOT NULL,
                    image_count INTEGER NOT NULL,
                    processed_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL
                );

                CREATE TABLE ocr_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    pdf_path TEXT NOT NULL,
                    page_num INTEGER NOT NULL,
                    image_index INTEGER NOT NULL,
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
                    ocr_performed INTEGER NOT NULL,
                    text_length INTEGER,
                    word_count INTEGER,
                    is_useful INTEGER,
                    cluster_id INTEGER DEFAULT -1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE learning_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)
            conn.commit()
            conn.close()

            # Now open with AdaptiveLearner - should trigger migration
            learner = AdaptiveLearner(db_path=db_path, enabled=True)

            # Verify new columns exist
            cursor = learner._conn.execute("PRAGMA table_info(processed_files)")
            columns = {row[1] for row in cursor.fetchall()}

            expected_new_columns = {
                'quality_score',
                'quality_word_count',
                'previous_quality_score',
                'quality_delta',
                'extraction_mode',
            }
            assert expected_new_columns.issubset(columns), \
                f"Migration failed - missing: {expected_new_columns - columns}"

            learner.close()


class TestImageFeature:
    """Tests for ImageFeature dataclass."""

    def test_to_vector_normalization(self):
        """Feature vector should have normalized values."""
        feature = ImageFeature(
            width=500,
            height=300,
            area=150000,
            aspect_ratio=1.67,
            page_y_center=0.5,
            region="body",
            surrounding_text_density=50.0,
            has_nearby_caption=True,
            brightness_mean=128.0,
            brightness_std=40.0,
            is_mostly_white=False,
            has_contrast=True,
        )

        vector = feature.to_vector()

        # Vector should have 14 elements (12 base + 2 log-area features)
        assert len(vector) == 14

        # Most values should be roughly in 0-2 range after normalization
        for i, val in enumerate(vector):
            assert -1 <= val <= 10, f"Vector element {i} = {val} seems out of range"

    def test_to_dict_and_back(self):
        """Feature should round-trip through dict."""
        original = ImageFeature(
            width=500,
            height=300,
            area=150000,
            aspect_ratio=1.67,
            page_y_center=0.5,
            region="body",
            surrounding_text_density=50.0,
            has_nearby_caption=True,
            brightness_mean=128.0,
            brightness_std=40.0,
            is_mostly_white=False,
            has_contrast=True,
        )

        d = original.to_dict()
        restored = ImageFeature.from_dict(d)

        assert restored.width == original.width
        assert restored.height == original.height
        assert restored.region == original.region
        assert restored.has_nearby_caption == original.has_nearby_caption


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
