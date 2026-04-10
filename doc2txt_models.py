"""Data models and constants for doc2txt."""

import math
import time
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "1.0.0"

# Supported document formats (case-insensitive matching)
SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.rtf', '.odt'}


@dataclass
class QualityMetrics:
    """Quality assessment metrics for extracted text."""
    real_word_ratio: float = 0.0
    content_score: float = 0.0
    gibberish_penalty: float = 0.0
    punctuation_score: float = 0.0
    total_score: float = 0.0
    word_count: int = 0


@dataclass
class ImageFeature:
    """Features extracted from an image region for learning."""
    # Geometric features
    width: int
    height: int
    area: int
    aspect_ratio: float

    # Position features (normalized to page dimensions)
    page_y_center: float  # 0-1, top to bottom
    region: str  # "header", "body", "footer", "margin"

    # Context features
    surrounding_text_density: float  # chars per 100px around image
    has_nearby_caption: bool

    # Visual features
    brightness_mean: float  # 0-255
    brightness_std: float  # contrast indicator
    is_mostly_white: bool  # >95% pixels above 240
    has_contrast: bool  # std > 30

    def to_vector(self) -> list[float]:
        """Convert to numeric vector for classifier.

        Uses log-scaled area as the dominant size feature since area is the
        strongest predictor of usefulness (large body images: 89% useful,
        small images: 7.7% useful).
        """
        # Log area: ranges from ~2 (100px²) to ~6 (1Mpx²)
        log_area = math.log10(max(self.area, 1))
        is_body = 1.0 if self.region == "body" else 0.0

        return [
            self.width / 1000,  # Normalize to ~0-2 range
            self.height / 1000,
            self.area / 1_000_000,  # Linear area (kept for backward compat)
            log_area / 6,  # Log area normalized 0-1, better for small/large distinction
            log_area * is_body / 6,  # Interaction: large body images are high value
            self.aspect_ratio,
            self.page_y_center,
            {"header": 0.0, "body": 0.5, "footer": 1.0, "margin": 0.25}.get(self.region, 0.5),
            self.surrounding_text_density / 100,
            1.0 if self.has_nearby_caption else 0.0,
            self.brightness_mean / 255,
            self.brightness_std / 128,
            1.0 if self.is_mostly_white else 0.0,
            1.0 if self.has_contrast else 0.0,
        ]

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "width": self.width,
            "height": self.height,
            "area": self.area,
            "aspect_ratio": self.aspect_ratio,
            "page_y_center": self.page_y_center,
            "region": self.region,
            "surrounding_text_density": self.surrounding_text_density,
            "has_nearby_caption": self.has_nearby_caption,
            "brightness_mean": self.brightness_mean,
            "brightness_std": self.brightness_std,
            "is_mostly_white": self.is_mostly_white,
            "has_contrast": self.has_contrast,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ImageFeature":
        """Create from dictionary."""
        return cls(**d)


@dataclass
class OCROutcome:
    """Record of an OCR attempt with features and results."""
    timestamp: float
    pdf_path: str
    page_num: int
    image_index: int
    features: ImageFeature
    ocr_performed: bool
    text_length: int
    word_count: int
    is_useful: bool  # text_length > 10 and word_count >= 2
    cluster_id: int = -1  # Assigned cluster (-1 = not yet clustered)


@dataclass
class ProcessingStats:
    """Track processing statistics."""
    total_files: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    improved_files: int = 0
    kept_existing: int = 0
    total_bytes: int = 0
    processed_bytes: int = 0
    md_bytes: int = 0
    total_pages: int = 0
    processed_pages: int = 0
    ocr_pages: int = 0
    ocr_chars: int = 0
    current_file: str = ""
    current_file_pages: int = 0
    current_page: int = 0
    current_status: str = ""
    start_time: float = field(default_factory=time.time)
    log_messages: list = field(default_factory=list)

    def elapsed(self) -> float:
        return time.time() - self.start_time

    def files_per_min(self) -> float:
        elapsed = self.elapsed()
        if elapsed > 0:
            return (self.processed_files / elapsed) * 60
        return 0

    def mb_per_min(self) -> float:
        elapsed = self.elapsed()
        if elapsed > 0:
            mb = self.processed_bytes / (1024 * 1024)
            return (mb / elapsed) * 60
        return 0

    def log(self, msg: str):
        self.log_messages.append(msg)
        if len(self.log_messages) > 100:
            self.log_messages.pop(0)


@dataclass
class FileResult:
    """Pickle-safe result object returned by worker processes."""
    source_path: Path
    success: bool
    message: str
    improve_detail: str | None = None
    processed_bytes: int = 0
    md_bytes: int = 0
    pages_processed: int = 0
    ocr_pages: int = 0
    ocr_chars: int = 0
    was_improved: bool = False
    was_kept: bool = False
    was_skipped: bool = False
    was_failed: bool = False
    log_messages: list = field(default_factory=list)
