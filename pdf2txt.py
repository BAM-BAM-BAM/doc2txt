#!/usr/bin/env python3
"""Extract text from documents (PDF, DOCX, DOC, RTF, ODT) and create corresponding markdown files."""

import argparse
import curses
import multiprocessing
import os
import random
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from pdf2txt_models import (
    __version__,
    SUPPORTED_EXTENSIONS,
    QualityMetrics,  # noqa: F401 (re-exported for tests)
    ImageFeature,
    OCROutcome,  # noqa: F401 (re-exported for tests)
    ProcessingStats,
    FileResult,
)
from pdf2txt_quality import TextQualityScorer, strip_markdown_metadata, _quality_scorer  # noqa: F401 (TextQualityScorer re-exported)
from pdf2txt_learning import AdaptiveLearner
from pdf2txt_hud import RetroHUD

# Use spawn to avoid terminal/curses issues with fork
_mp_context = multiprocessing.get_context("spawn")


# ClusterStats removed - now using supervised classifier instead of clustering
# AdaptiveLearner moved to pdf2txt_learning.py
def convert_windows_path(path_str: str) -> Path:
    """Convert Windows-style path to WSL path if needed."""
    windows_pattern = r'^([A-Za-z]):[/\\](.*)$'
    match = re.match(windows_pattern, path_str)

    if match:
        drive_letter = match.group(1).lower()
        rest_of_path = match.group(2)
        rest_of_path = rest_of_path.replace('\\', '/')
        return Path(f'/mnt/{drive_letter}/{rest_of_path}')

    return Path(path_str)


def find_pdfs(
    directory: Path,
    recursive: bool = False,
    quiet: bool = False,
    shuffle: bool = False,
) -> list[Path]:
    """Find all PDF files in directory (case-insensitive).

    Args:
        directory: Directory to search
        recursive: Search subdirectories
        quiet: Suppress output
        shuffle: Randomize file order (useful for learning to avoid sequential bias)
    """
    if not quiet:
        mode = "recursively " if recursive else ""
        print(f"Searching {mode}for PDFs in: {directory}", flush=True)

    pdfs = []
    search = directory.rglob if recursive else directory.glob
    for pattern in ['*.pdf', '*.PDF', '*.Pdf']:
        pdfs.extend(search(pattern))

    result = list(set(pdfs))

    if shuffle:
        random.shuffle(result)
        if not quiet:
            print(f"Found {len(result)} PDF file(s) (shuffled for learning)", flush=True)
    else:
        if not quiet:
            print(f"Found {len(result)} PDF file(s)", flush=True)

    return result


def find_documents(
    directory: Path,
    recursive: bool = False,
    quiet: bool = False,
    shuffle: bool = False,
    formats: set[str] | None = None,
) -> list[Path]:
    """Find all supported document files in directory (case-insensitive).

    Args:
        directory: Directory to search
        recursive: Search subdirectories
        quiet: Suppress output
        shuffle: Randomize file order (useful for learning to avoid sequential bias)
        formats: Set of extensions to search for (e.g., {'.pdf', '.docx'}). None = all supported.
    """
    extensions = formats if formats else SUPPORTED_EXTENSIONS

    if not quiet:
        mode = "recursively " if recursive else ""
        fmt_list = ', '.join(ext.lstrip('.').upper() for ext in sorted(extensions))
        print(f"Searching {mode}for documents ({fmt_list}) in: {directory}", flush=True)

    docs = []
    search = directory.rglob if recursive else directory.glob
    for ext in extensions:
        bare = ext.lstrip('.')
        for pattern in [f'*.{bare.lower()}', f'*.{bare.upper()}', f'*.{bare.capitalize()}']:
            docs.extend(search(pattern))

    result = list(set(docs))

    if shuffle:
        random.shuffle(result)
        if not quiet:
            print(f"Found {len(result)} document(s) (shuffled for learning)", flush=True)
    else:
        if not quiet:
            print(f"Found {len(result)} document(s)", flush=True)

    return result


def check_libreoffice_available() -> bool:
    """Check if LibreOffice is available for .doc/.rtf/.odt conversion."""
    import shutil
    return shutil.which("libreoffice") is not None


def check_tesseract_available() -> bool:
    """Check if Tesseract OCR is available on the system."""
    import shutil
    return shutil.which("tesseract") is not None


def check_paddleocr_available() -> bool:
    """Check if PaddleOCR is available."""
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        return False


def check_surya_available() -> bool:
    """Check if Surya OCR is available."""
    try:
        # Suppress Surya's "Checking connectivity" message during import
        with SuppressOutputFD(suppress=True):
            import surya  # noqa: F401
        return True
    except ImportError:
        return False


def resolve_ocr_engine(requested: str, use_ocr: bool = True) -> tuple[bool, str, list[str]]:
    """Resolve which OCR engine to use with fallback chain.

    Args:
        requested: Requested OCR engine ("surya", "paddle", "tesseract", "none")
        use_ocr: Whether OCR is enabled

    Returns:
        Tuple of (ocr_available, actual_engine, log_messages)
    """
    log_msgs = []

    if not use_ocr or requested == "none":
        return False, "none", ["OCR: disabled"]

    # Try requested engine first, then fallbacks
    fallback_order = {
        "surya": ["surya", "paddle", "tesseract"],
        "paddle": ["paddle", "tesseract"],
        "tesseract": ["tesseract"],
    }

    engines = fallback_order.get(requested, ["tesseract"])
    checks = {
        "surya": check_surya_available,
        "paddle": check_paddleocr_available,
        "tesseract": check_tesseract_available,
    }

    for engine in engines:
        if checks[engine]():
            if engine != requested:
                log_msgs.append(f"OCR: {requested} unavailable, using {engine}")
            else:
                log_msgs.append(f"OCR: using {engine}")
            return True, engine, log_msgs

    log_msgs.append(f"OCR: no engines available ({'/'.join(engines)})")
    return False, "none", log_msgs


def get_gpu_info() -> dict:
    """Get GPU information for debugging."""
    info = {
        'cuda_available': False,
        'device_count': 0,
        'devices': [],
        'error': None,
    }

    # Try torch first for CUDA info
    torch_available = False
    try:
        import torch
        torch_available = True
        info['cuda_available'] = torch.cuda.is_available()
        if info['cuda_available']:
            info['device_count'] = torch.cuda.device_count()
            for i in range(info['device_count']):
                device_info = {
                    'index': i,
                    'name': torch.cuda.get_device_name(i),
                    'memory_total': torch.cuda.get_device_properties(i).total_memory,
                    'memory_allocated': torch.cuda.memory_allocated(i),
                    'memory_reserved': torch.cuda.memory_reserved(i),
                }
                info['devices'].append(device_info)
    except ImportError:
        pass
    except Exception as e:
        info['error'] = str(e)

    # Always try nvidia-smi for detailed/accurate info (works even without torch)
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.free,memory.used,memory.total,'
             'utilization.gpu,temperature.gpu,power.draw,display_active',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            # If we didn't get device info from torch, create entries from nvidia-smi
            if not info['devices']:
                info['cuda_available'] = True
                info['device_count'] = len(lines)
                for i, line in enumerate(lines):
                    info['devices'].append({'index': i})

            # Update each device with nvidia-smi data
            for i, line in enumerate(lines):
                if i < len(info['devices']):
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 8:
                        dev = info['devices'][i]
                        dev['name'] = parts[0]
                        dev['memory_free_mb'] = int(parts[1])
                        dev['memory_used_mb'] = int(parts[2])
                        dev['memory_total_mb'] = int(parts[3])
                        dev['gpu_util'] = parts[4]
                        dev['temperature'] = parts[5]
                        dev['power_draw'] = parts[6]
                        dev['display_active'] = parts[7]
            info['error'] = None  # Clear any torch error if nvidia-smi worked
    except FileNotFoundError:
        if not torch_available:
            info['error'] = 'torch not installed and nvidia-smi not found'
    except Exception as e:
        if not info['devices']:
            info['error'] = str(e)

    return info


def print_gpu_debug_info():
    """Print GPU debugging information."""
    info = get_gpu_info()

    print("[DEBUG] GPU Information:")
    if info['error']:
        print(f"  Error: {info['error']}")
    else:
        print(f"  CUDA available: {info['cuda_available']}")
        if info['cuda_available']:
            print(f"  Device count: {info['device_count']}")
            for dev in info['devices']:
                print(f"  Device {dev['index']}: {dev['name']}")
                if 'memory_total_mb' in dev:
                    used = dev['memory_used_mb']
                    total = dev['memory_total_mb']
                    free = dev['memory_free_mb']
                    pct = (used / total * 100) if total > 0 else 0
                    print(f"    Memory: {used:,} MB used / {total:,} MB total ({pct:.1f}% used)")
                    print(f"    Free: {free:,} MB")
                    # Display and power info
                    if 'display_active' in dev:
                        display_status = dev['display_active']
                        if display_status.lower() == 'enabled':
                            print("    Display: Active (using VRAM for framebuffer)")
                        else:
                            print(f"    Display: {display_status}")
                    if 'gpu_util' in dev:
                        print(f"    GPU Load: {dev['gpu_util']}%  |  Temp: {dev['temperature']}°C  |  Power: {dev['power_draw']}W")
                else:
                    total_mb = dev['memory_total'] / (1024 * 1024)
                    alloc_mb = dev['memory_allocated'] / (1024 * 1024)
                    reserved_mb = dev['memory_reserved'] / (1024 * 1024)
                    print(f"    Total: {total_mb:,.0f} MB")
                    print(f"    PyTorch allocated: {alloc_mb:,.0f} MB")
                    print(f"    PyTorch reserved: {reserved_mb:,.0f} MB")
        else:
            # Check if CUDA_VISIBLE_DEVICES is set (--cpu mode)
            cuda_env = os.environ.get('CUDA_VISIBLE_DEVICES', None)
            if cuda_env == '':
                print("  (CUDA disabled via --cpu flag)")
            else:
                print("  (No CUDA devices found)")
    print()


def clear_gpu_memory():
    """Clear GPU memory and attempt to kill zombie CUDA processes."""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass

    # Try to identify and kill zombie GPU processes (Linux/WSL only)
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import os
            current_pid = os.getpid()
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        pid = int(line.strip())
                        # Don't kill ourselves or parent processes
                        if pid != current_pid and pid != os.getppid():
                            # Check if process exists but is zombie/orphaned
                            try:
                                os.kill(pid, 0)  # Check if exists
                            except ProcessLookupError:
                                # Process doesn't exist but holding GPU memory - can't do much in userspace
                                pass
                    except (ValueError, ProcessLookupError, PermissionError):
                        pass
    except Exception:
        pass


# Global OCR instances (lazy-loaded)
_paddle_ocr_instance = None
_surya_ocr_instance = None


def get_paddle_ocr():
    """Get or create the global PaddleOCR instance."""
    global _paddle_ocr_instance
    if _paddle_ocr_instance is None:
        from paddleocr import PaddleOCR
        # Suppress PaddleOCR's verbose logging via Python logging module
        import logging
        logging.getLogger('ppocr').setLevel(logging.ERROR)
        logging.getLogger('paddle').setLevel(logging.ERROR)
        logging.getLogger('paddlenlp').setLevel(logging.ERROR)
        logging.getLogger('paddlex').setLevel(logging.ERROR)
        # Suppress stdout/stderr during initialization (native code spam)
        with SuppressOutputFD(suppress=True):
            # Note: PaddleOCR v3+ uses use_textline_orientation instead of use_angle_cls
            _paddle_ocr_instance = PaddleOCR(use_textline_orientation=True, lang='en')
    return _paddle_ocr_instance


def configure_surya_batch_sizes():
    """Configure Surya batch sizes based on available VRAM.

    Surya defaults:
    - RECOGNITION_BATCH_SIZE=512 (~40-50MB per item = ~20GB VRAM)
    - DETECTOR_BATCH_SIZE=default (~280MB per item)

    These must be set BEFORE importing surya modules.
    """
    # Skip if already configured or running on CPU
    if os.environ.get('RECOGNITION_BATCH_SIZE') or os.environ.get('CUDA_VISIBLE_DEVICES') == '':
        return

    # Get free VRAM
    gpu_info = get_gpu_info()
    if not gpu_info['cuda_available'] or not gpu_info['devices']:
        return

    dev = gpu_info['devices'][0]
    free_mb = dev.get('memory_free_mb', 0)

    if free_mb <= 0:
        return

    # Reserve ~4GB for models, use remaining for batching
    # Recognition: ~50MB per batch item
    # Detection: ~280MB per batch item
    available_for_batching = max(0, free_mb - 4000)  # Reserve 4GB for models

    # Calculate safe batch sizes
    rec_batch = max(4, min(64, available_for_batching // 50))
    det_batch = max(1, min(8, available_for_batching // 280))

    os.environ['RECOGNITION_BATCH_SIZE'] = str(rec_batch)
    os.environ['DETECTOR_BATCH_SIZE'] = str(det_batch)


def get_surya_ocr():
    """Get or create the global Surya OCR models."""
    global _surya_ocr_instance
    if _surya_ocr_instance is None:
        # Clear any leftover GPU memory before loading heavy models
        clear_gpu_memory()
        # Configure batch sizes based on available VRAM (must be before import)
        configure_surya_batch_sizes()
        from surya.recognition import RecognitionPredictor, FoundationPredictor
        from surya.detection import DetectionPredictor
        detection = DetectionPredictor()
        foundation = FoundationPredictor()
        recognition = RecognitionPredictor(foundation)
        _surya_ocr_instance = {
            'recognition': recognition,
            'detection': detection,
        }
    return _surya_ocr_instance


def ocr_page_with_paddle(page, dpi: int = 300, debug: bool = False) -> str:
    """Extract text from a PDF page using PaddleOCR."""
    import io
    import numpy as np
    from PIL import Image

    # Render page to image
    pix = page.get_pixmap(dpi=dpi)
    img_data = pix.tobytes("png")

    # Convert PNG bytes to numpy array (PaddleOCR needs numpy array, not raw bytes)
    img = Image.open(io.BytesIO(img_data))
    # Ensure RGB mode (PaddleOCR doesn't handle RGBA well)
    if img.mode == 'RGBA':
        img = img.convert('RGB')
    img_array = np.array(img)

    # Run PaddleOCR with output suppression (native code spams binary data)
    ocr = get_paddle_ocr()
    with SuppressOutputFD(suppress=True):
        result = ocr.ocr(img_array)

    # Extract text from results - handle multiple API versions
    if not result:
        return ""

    lines = []

    # New PaddleOCR API (v3+) returns dict with 'rec_texts'
    if isinstance(result, dict):
        if debug:
            import sys
            print(f"[DEBUG] PaddleOCR result type: dict, keys: {list(result.keys())}", file=sys.stderr)
        if 'rec_texts' in result:
            lines = [str(t) for t in result['rec_texts'] if t]
        elif 'data' in result and isinstance(result['data'], dict):
            # Another possible format
            if 'rec_texts' in result['data']:
                lines = [str(t) for t in result['data']['rec_texts'] if t]
    # Old API returns list of lists: [[[bbox, (text, conf)], ...]]
    elif isinstance(result, list):
        if debug:
            import sys
            print(f"[DEBUG] PaddleOCR result type: list, len: {len(result)}, first item type: {type(result[0]) if result else None}", file=sys.stderr)
        if not result[0]:
            return ""
        for line in result[0]:
            if line and len(line) >= 2:
                text = line[1][0] if isinstance(line[1], (list, tuple)) else line[1]
                if text:
                    lines.append(str(text))
    else:
        if debug:
            import sys
            print(f"[DEBUG] PaddleOCR result type: {type(result)}", file=sys.stderr)

    return '\n'.join(lines)


def ocr_page_with_surya(page, dpi: int = 300) -> str:
    """Extract text from a PDF page using Surya OCR."""
    import io
    from PIL import Image

    # Render page to image
    pix = page.get_pixmap(dpi=dpi)
    img_data = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_data))

    # Get OCR models
    models = get_surya_ocr()

    # Run recognition with detection (new Surya API)
    rec_results = models['recognition']([img], det_predictor=models['detection'])

    # Extract text from results
    if not rec_results or not rec_results[0]:
        return ""

    lines = []
    for text_line in rec_results[0].text_lines:
        if text_line.text:
            lines.append(text_line.text)

    return '\n'.join(lines)


def extract_image_features(
    page,
    bbox: tuple[float, float, float, float],
    img,
    text_blocks: list | None = None,
) -> ImageFeature:
    """Extract features from an image region for learning.

    Args:
        page: PyMuPDF page object
        bbox: (x0, y0, x1, y1) bounding box in page coordinates
        img: PIL Image of the region
        text_blocks: List of text blocks from page.get_text("blocks") for context

    Returns:
        ImageFeature with all extracted characteristics
    """
    import numpy as np

    x0, y0, x1, y1 = bbox
    page_rect = page.rect
    page_height = page_rect.height
    page_width = page_rect.width

    # Geometric features
    width = int(x1 - x0)
    height = int(y1 - y0)
    area = width * height
    aspect_ratio = width / max(height, 1)

    # Position features
    y_center = (y0 + y1) / 2
    page_y_center = y_center / max(page_height, 1)

    # Determine region (header/body/footer/margin)
    x_center = (x0 + x1) / 2
    if page_y_center < 0.12:
        region = "header"
    elif page_y_center > 0.88:
        region = "footer"
    elif x_center < page_width * 0.1 or x_center > page_width * 0.9:
        region = "margin"
    else:
        region = "body"

    # Context features - surrounding text density
    surrounding_text_density = 0.0
    has_nearby_caption = False

    if text_blocks:
        # Count text chars within 50 page units of this image
        search_margin = 50
        text_chars_nearby = 0
        for block in text_blocks:
            bx0, by0, bx1, by1, content, _, block_type = block
            if block_type != 0:  # Skip non-text blocks
                continue
            # Check if block is near the image
            if (bx0 < x1 + search_margin and bx1 > x0 - search_margin and
                by0 < y1 + search_margin and by1 > y0 - search_margin):
                text_chars_nearby += len(str(content))
                # Check for caption-like text below image
                if by0 > y1 and by0 < y1 + 30 and len(str(content)) < 200:
                    content_lower = str(content).lower()
                    if any(kw in content_lower for kw in ["figure", "fig.", "image", "photo", "chart", "table"]):
                        has_nearby_caption = True
        # Normalize: chars per 100 pixels of search area
        search_area = (x1 - x0 + 2 * search_margin) * (y1 - y0 + 2 * search_margin)
        surrounding_text_density = (text_chars_nearby / max(search_area, 1)) * 10000

    # Visual features from the image
    if img.mode != 'L':
        gray = img.convert('L')
    else:
        gray = img
    pixels = np.array(gray)

    brightness_mean = float(np.mean(pixels))
    brightness_std = float(np.std(pixels))
    is_mostly_white = float(np.mean(pixels > 240)) > 0.95
    has_contrast = brightness_std > 30

    return ImageFeature(
        width=width,
        height=height,
        area=area,
        aspect_ratio=aspect_ratio,
        page_y_center=page_y_center,
        region=region,
        surrounding_text_density=surrounding_text_density,
        has_nearby_caption=has_nearby_caption,
        brightness_mean=brightness_mean,
        brightness_std=brightness_std,
        is_mostly_white=is_mostly_white,
        has_contrast=has_contrast,
    )


def ocr_image_region(
    page,
    bbox,
    ocr_engine: str = "surya",
    dpi: int = 300,
    learner: AdaptiveLearner | None = None,
    pdf_path: str = "",
    page_num: int = 0,
    image_index: int = 0,
    text_blocks: list | None = None,
) -> tuple[str, bool]:
    """OCR a specific region of a page.

    Args:
        page: PyMuPDF page object
        bbox: Tuple of (x0, y0, x1, y1) defining the region
        ocr_engine: "surya", "paddle", or "tesseract"
        dpi: Resolution for rendering
        learner: Optional AdaptiveLearner for skip decisions
        pdf_path: PDF file path for logging
        page_num: Page number for logging
        image_index: Image index on page for logging
        text_blocks: Text blocks for context analysis

    Returns:
        Tuple of (extracted_text, was_ocr_performed)
    """
    import io
    from PIL import Image

    # Create a clip rect for the region
    import pymupdf
    clip = pymupdf.Rect(bbox[0], bbox[1], bbox[2], bbox[3])

    # Render just this region at the specified DPI
    mat = pymupdf.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    img_data = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_data))

    # Skip tiny images (likely decorative)
    if img.width < 20 or img.height < 10:
        return "", False

    # Extract features for learning
    features = None
    is_exploration = False
    ocr_reason = ""
    if learner:
        features = extract_image_features(page, bbox, img, text_blocks)
        do_ocr, ocr_reason, is_exploration = learner.should_ocr(features)
        if not do_ocr:
            # Record that we skipped this image (no OCR, no text)
            learner.record_outcome(features, pdf_path, page_num, image_index, False, "")
            return "", False

    # Perform OCR
    text = ""
    if ocr_engine == "surya":
        models = get_surya_ocr()
        rec_results = models['recognition']([img], det_predictor=models['detection'])
        if rec_results and rec_results[0]:
            lines = [tl.text for tl in rec_results[0].text_lines if tl.text]
            text = '\n'.join(lines)

    elif ocr_engine == "paddle":
        import numpy as np
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        img_array = np.array(img)
        ocr = get_paddle_ocr()
        with SuppressOutputFD(suppress=True):
            result = ocr.ocr(img_array)
        if result:
            lines = []
            if isinstance(result, dict) and 'rec_texts' in result:
                lines = [str(t) for t in result['rec_texts'] if t]
            elif isinstance(result, list) and result[0]:
                for line in result[0]:
                    if line and len(line) >= 2:
                        line_text = line[1][0] if isinstance(line[1], (list, tuple)) else line[1]
                        if line_text:
                            lines.append(str(line_text))
            text = '\n'.join(lines)

    else:  # tesseract
        tp = page.get_textpage_ocr(full=True, language="eng", clip=clip)
        text = page.get_text(textpage=tp, clip=clip).strip()

    # Record outcome for learning
    if learner and features:
        learner.record_outcome(features, pdf_path, page_num, image_index, True, text, is_exploration, ocr_reason)

    return text, True


def extract_page_hybrid(
    page,
    ocr_engine: str = "surya",
    dpi: int = 300,
    debug: bool = False,
    learner: AdaptiveLearner | None = None,
    pdf_path: str = "",
    page_num: int = 0,
) -> tuple[str, int, int, int]:
    """Extract text from page using hybrid approach: text extraction + OCR for images.

    Args:
        page: PyMuPDF page object
        ocr_engine: OCR engine to use for image regions
        dpi: Resolution for rendering images
        debug: Print debug info
        learner: Optional AdaptiveLearner for skip decisions
        pdf_path: PDF file path for logging
        page_num: Page number for logging

    Returns:
        Tuple of (extracted_text, ocr_regions_count, ocr_chars_count, skipped_count)
    """
    import pymupdf

    # Get all blocks with positions
    # Block format: (x0, y0, x1, y1, text_or_img, block_no, block_type)
    # block_type: 0=text, 1=image
    blocks = page.get_text("blocks")

    # Separate text and image blocks
    content_blocks = []  # (y0, text, is_ocr)

    ocr_regions = 0
    ocr_chars = 0
    skipped_regions = 0
    image_index = 0

    # Track which areas we've processed as image blocks
    processed_rects = []

    for block in blocks:
        x0, y0, x1, y1, content, block_no, block_type = block

        if block_type == 0:
            # Text block - use as-is
            text = content.strip()
            if text:
                content_blocks.append((y0, text, False))
        else:
            # Image block - OCR this region (learner may skip)
            processed_rects.append(pymupdf.Rect(x0, y0, x1, y1))
            try:
                img_text, was_ocrd = ocr_image_region(
                    page,
                    (x0, y0, x1, y1),
                    ocr_engine,
                    dpi,
                    learner=learner,
                    pdf_path=pdf_path,
                    page_num=page_num,
                    image_index=image_index,
                    text_blocks=blocks,
                )
                image_index += 1

                if not was_ocrd:
                    skipped_regions += 1
                    if debug:
                        print(f"    [DEBUG] Skipped image block at y={y0:.0f} (learning)")
                elif img_text and img_text.strip():
                    content_blocks.append((y0, img_text.strip(), True))
                    ocr_regions += 1
                    ocr_chars += len(img_text)
                    if debug:
                        print(f"    [DEBUG] OCR'd image block at y={y0:.0f}: {len(img_text)} chars")
            except Exception as e:
                if debug:
                    print(f"    [DEBUG] Failed to OCR image at y={y0:.0f}: {e}")

    # Also check for images via get_images() that weren't detected as blocks
    # This catches images that PyMuPDF doesn't return as block_type=1
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            # Get bounding box(es) for this image on the page
            img_rects = page.get_image_rects(xref)
            for rect in img_rects:
                # Skip if we already processed this area as an image block
                already_processed = any(
                    rect.intersects(pr) and rect.get_area() > 0 and
                    abs(rect.get_area() - pr.get_area()) / max(rect.get_area(), 1) < 0.5
                    for pr in processed_rects
                )
                if already_processed:
                    continue

                x0, y0, x1, y1 = rect
                processed_rects.append(rect)

                img_text, was_ocrd = ocr_image_region(
                    page,
                    (x0, y0, x1, y1),
                    ocr_engine,
                    dpi,
                    learner=learner,
                    pdf_path=pdf_path,
                    page_num=page_num,
                    image_index=image_index,
                    text_blocks=blocks,
                )
                image_index += 1

                if not was_ocrd:
                    skipped_regions += 1
                    if debug:
                        print(f"    [DEBUG] Skipped image (xref={xref}) at y={y0:.0f} (learning)")
                elif img_text and img_text.strip():
                    content_blocks.append((y0, img_text.strip(), True))
                    ocr_regions += 1
                    ocr_chars += len(img_text)
                    if debug:
                        print(f"    [DEBUG] OCR'd image (xref={xref}) at y={y0:.0f}: {len(img_text)} chars")
        except Exception as e:
            if debug:
                print(f"    [DEBUG] Failed to process image xref={xref}: {e}")

    # Sort by y-position (reading order: top to bottom)
    content_blocks.sort(key=lambda x: x[0])

    # Combine all text
    final_text = '\n\n'.join(block[1] for block in content_blocks)

    return final_text, ocr_regions, ocr_chars, skipped_regions


def extract_page_text(
    page,
    ocr_engine: str,
    force_ocr: bool = False,
    suppress_output: bool = False,
    learner: AdaptiveLearner | None = None,
    pdf_path: str = "",
    page_num: int = 0,
) -> tuple[str, bool, int, str]:
    """Extract text from a single page, using OCR as appropriate.

    Strategy:
    - force_ocr: Full page OCR (re-OCR everything, ignore extracted text)
    - has_images: Hybrid mode (extract text + OCR each image, merge by position)
    - otherwise: Just extract text (fast, no OCR needed)

    Args:
        page: PyMuPDF page object
        ocr_engine: OCR engine to use ("surya", "paddle", "tesseract", "none")
        force_ocr: Force full-page OCR regardless of content
        suppress_output: Suppress stdout/stderr during processing
        learner: Optional AdaptiveLearner for image skip decisions
        pdf_path: PDF file path for learning
        page_num: Page number for learning

    Returns:
        Tuple of (text, used_ocr, ocr_chars, log_message)
    """
    if ocr_engine == "none" and not force_ocr:
        with SuppressOutputFD(suppress=suppress_output):
            text = page.get_text().strip()
        return text, False, 0, ""

    has_images = len(page.get_images(full=False)) > 0

    try:
        if force_ocr:
            # Full page OCR: user wants everything re-OCR'd
            with SuppressOutputFD(suppress=suppress_output):
                if ocr_engine == "surya":
                    ocr_text = ocr_page_with_surya(page)
                elif ocr_engine == "paddle":
                    ocr_text = ocr_page_with_paddle(page)
                else:  # tesseract
                    tp = page.get_textpage_ocr(full=True, language="eng")
                    ocr_text = page.get_text(textpage=tp).strip()
            return ocr_text, True, len(ocr_text), f"OCR +{len(ocr_text):,} chars ({ocr_engine})"

        elif has_images:
            # Hybrid: always extract text + OCR every image, merge by position
            with SuppressOutputFD(suppress=suppress_output):
                hybrid_text, ocr_regions, ocr_chars, skipped = extract_page_hybrid(
                    page,
                    ocr_engine=ocr_engine,
                    learner=learner,
                    pdf_path=pdf_path,
                    page_num=page_num,
                )
            if ocr_regions > 0 or skipped > 0:
                msg_parts = []
                if ocr_regions > 0:
                    msg_parts.append(f"+{ocr_regions} imgs (+{ocr_chars:,} chars)")
                if skipped > 0:
                    msg_parts.append(f"skipped {skipped}")
                return hybrid_text, ocr_regions > 0, ocr_chars, ", ".join(msg_parts)
            else:
                return hybrid_text, False, 0, ""

        else:
            # No images, just extract text
            with SuppressOutputFD(suppress=suppress_output):
                text = page.get_text().strip()
            return text, False, 0, ""

    except Exception as e:
        # Fallback to basic extraction on error
        with SuppressOutputFD(suppress=suppress_output):
            text = page.get_text().strip()
        return text, False, 0, f"FAILED - {e}"


class SuppressOutputFD:
    """Context manager to suppress stdout/stderr at the OS file descriptor level.

    This catches output from native code (like PyMuPDF/Tesseract) that bypasses
    Python's sys.stdout/stderr. Curses still works because it opens /dev/tty directly.
    """

    def __init__(self, suppress: bool = True):
        self.suppress = suppress
        self._stdout_fd = None
        self._stderr_fd = None
        self._devnull_fd = None

    def __enter__(self):
        if self.suppress:
            # Save copies of the original file descriptors
            self._stdout_fd = os.dup(1)
            self._stderr_fd = os.dup(2)
            # Open /dev/null
            self._devnull_fd = os.open(os.devnull, os.O_WRONLY)
            # Redirect stdout and stderr to /dev/null
            os.dup2(self._devnull_fd, 1)
            os.dup2(self._devnull_fd, 2)
        return self

    def __exit__(self, *args):
        if self.suppress:
            # Restore original file descriptors
            os.dup2(self._stdout_fd, 1)
            os.dup2(self._stderr_fd, 2)
            # Close the saved copies
            os.close(self._stdout_fd)
            os.close(self._stderr_fd)
            os.close(self._devnull_fd)


def extract_text_from_pdf(
    pdf_path: Path,
    use_ocr: bool = True,
    ocr_engine: str = "paddle",
    force_ocr: bool = False,
    stats: ProcessingStats | None = None,
    hud: RetroHUD | None = None,
    learner: AdaptiveLearner | None = None,
) -> list[str]:
    """Extract text from PDF, returning list of page contents."""
    import pymupdf

    suppress = hud is not None

    with SuppressOutputFD(suppress=suppress):
        doc = pymupdf.open(pdf_path)

    # Resolve OCR engine with fallbacks
    ocr_available, active_engine, _ = resolve_ocr_engine(ocr_engine, use_ocr)

    total_pages = len(doc)
    if stats:
        stats.current_file_pages = total_pages
        stats.total_pages += total_pages

    pages = []
    try:
        for page_num, page in enumerate(doc, start=1):
            if stats:
                stats.current_page = page_num
                stats.current_status = f"Reading page {page_num}/{total_pages}"
                if hud:
                    hud.refresh()

            # Extract page text (with OCR if available and needed)
            engine = active_engine if ocr_available else "none"
            text, used_ocr, ocr_chars, log_msg = extract_page_text(
                page,
                engine,
                force_ocr,
                suppress_output=suppress,
                learner=learner,
                pdf_path=str(pdf_path),
                page_num=page_num,
            )

            if stats:
                if used_ocr:
                    stats.ocr_pages += 1
                    stats.ocr_chars += ocr_chars
                if log_msg:
                    stats.log(f"  p{page_num}: {log_msg}")
                stats.processed_pages += 1

            pages.append(text)

        # Record file as processed for learning (track by content hash)
        if learner and learner.enabled:
            # Count total images in the document
            total_images = sum(len(p.get_images(full=False)) for p in doc)

            # Score the new extraction
            new_text = '\n'.join(pages)
            new_metrics = _quality_scorer.score(new_text)

            # Check for existing .md file to compare quality
            md_path = pdf_path.with_suffix('.md')
            previous_score = None
            if md_path.exists():
                try:
                    existing_md = md_path.read_text(encoding='utf-8')
                    existing_text = strip_markdown_metadata(existing_md)
                    old_metrics = _quality_scorer.score(existing_text)
                    previous_score = old_metrics.total_score
                    learner._stats["files_with_existing_md"] += 1

                    # Track quality changes using consistent thresholds
                    delta = new_metrics.total_score - old_metrics.total_score
                    if delta > AdaptiveLearner.QUALITY_IMPROVED_THRESHOLD:
                        learner._stats["quality_improved"] += 1
                    elif delta >= AdaptiveLearner.QUALITY_REGRESSION_THRESHOLD:
                        learner._stats["quality_unchanged"] += 1
                    # Regressions tracked in record_file_processed
                except Exception:
                    pass  # Ignore errors reading existing file

            # Record with quality metrics
            learner.record_file_processed(
                pdf_path,
                total_pages,
                total_images,
                quality_score=new_metrics.total_score,
                quality_word_count=new_metrics.word_count,
                previous_quality_score=previous_score,
                extraction_mode="force_ocr" if force_ocr else ("ocr" if use_ocr else "text"),
            )

            # Classifier retraining is handled automatically in record_outcome()
    finally:
        doc.close()

    return pages


def _paragraph_has_page_break(paragraph) -> bool:
    """Check if a python-docx paragraph contains a page break."""
    from docx.oxml.ns import qn
    for run in paragraph.runs:
        for br in run._element.findall(qn('w:br')):
            if br.get(qn('w:type')) == 'page':
                return True
    return False


def _heading_level(style_name: str) -> int:
    """Extract heading level from a style name like 'Heading 1'."""
    match = re.search(r'\d+', style_name)
    return int(match.group()) if match else 1


def _table_to_markdown(table) -> str:
    """Convert a python-docx table to a markdown table."""
    rows = []
    for row in table.rows:
        cells = [cell.text.strip().replace('|', '\\|') for cell in row.cells]
        rows.append('| ' + ' | '.join(cells) + ' |')

    if len(rows) >= 1:
        # Add header separator after first row
        col_count = len(table.rows[0].cells)
        separator = '| ' + ' | '.join(['---'] * col_count) + ' |'
        rows.insert(1, separator)

    return '\n'.join(rows)


def extract_text_from_docx(
    doc_path: Path,
    stats: ProcessingStats | None = None,
) -> list[str]:
    """Extract text from DOCX, returning list of section contents."""
    import docx

    document = docx.Document(doc_path)

    # Build a unified list of content blocks (paragraphs and tables in order)
    # by walking the document body XML
    sections: list[str] = []
    current_section: list[str] = []

    for element in document.element.body:
        from docx.oxml.ns import qn

        if element.tag == qn('w:p'):
            # It's a paragraph
            from docx.text.paragraph import Paragraph
            paragraph = Paragraph(element, document)

            if _paragraph_has_page_break(paragraph) and current_section:
                sections.append('\n'.join(current_section))
                current_section = []

            text = paragraph.text.strip()
            if text:
                if paragraph.style and paragraph.style.name and paragraph.style.name.startswith('Heading'):
                    level = _heading_level(paragraph.style.name)
                    text = '#' * level + ' ' + text
                current_section.append(text)

        elif element.tag == qn('w:tbl'):
            # It's a table
            from docx.table import Table
            table = Table(element, document)
            md_table = _table_to_markdown(table)
            if md_table:
                current_section.append('')
                current_section.append(md_table)
                current_section.append('')

    if current_section:
        sections.append('\n'.join(current_section))

    if not sections:
        sections = ['']

    if stats:
        stats.total_pages += len(sections)
        stats.processed_pages += len(sections)

    return sections


def extract_text_via_libreoffice(
    doc_path: Path,
    stats: ProcessingStats | None = None,
) -> list[str]:
    """Extract text from .doc/.rtf/.odt by converting to .docx via LibreOffice."""
    import subprocess
    import tempfile

    if not check_libreoffice_available():
        raise RuntimeError(
            f"LibreOffice is required to process {doc_path.suffix} files. "
            "Install with: sudo apt install libreoffice-writer"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'docx', '--outdir', tmpdir, str(doc_path)],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice conversion failed for {doc_path}: {result.stderr.decode()}")

        converted = Path(tmpdir) / (doc_path.stem + '.docx')
        if not converted.exists():
            raise RuntimeError(f"LibreOffice conversion produced no output for {doc_path}")

        return extract_text_from_docx(converted, stats=stats)


def extract_text(
    source_path: Path,
    use_ocr: bool = True,
    ocr_engine: str = "paddle",
    force_ocr: bool = False,
    stats: ProcessingStats | None = None,
    hud: RetroHUD | None = None,
    learner: AdaptiveLearner | None = None,
) -> list[str]:
    """Extract text from any supported document format."""
    ext = source_path.suffix.lower()

    if ext == '.pdf':
        return extract_text_from_pdf(
            source_path, use_ocr=use_ocr, ocr_engine=ocr_engine,
            force_ocr=force_ocr, stats=stats, hud=hud, learner=learner,
        )
    elif ext == '.docx':
        return extract_text_from_docx(source_path, stats=stats)
    elif ext in ('.doc', '.rtf', '.odt'):
        return extract_text_via_libreoffice(source_path, stats=stats)
    else:
        raise ValueError(f"Unsupported format: {ext}")


def create_markdown(source_path: Path, pages: list[str], page_label: str = "Page") -> str:
    """Create markdown content from extracted text sections."""
    lines = [
        f"# {source_path.stem}",
        "",
        f"> Source: {source_path}",
        "",
        "---",
        "",
    ]

    for i, page_text in enumerate(pages, start=1):
        if i > 1:
            lines.extend(["", "---", f"*{page_label} {i}*", ""])
        lines.append(page_text)

    return '\n'.join(lines)


def process_document(
    source_path: Path,
    overwrite: bool,
    dry_run: bool,
    use_ocr: bool = True,
    ocr_engine: str = "paddle",
    force_ocr: bool = False,
    improve: bool = False,
    stats: ProcessingStats | None = None,
    hud: RetroHUD | None = None,
    learner: AdaptiveLearner | None = None,
) -> tuple[bool, str, str | None]:
    """Process a single document file.

    Returns: (success, message, improve_detail)
    - improve_detail is set when improve mode makes a decision
    """
    md_path = source_path.with_suffix('.md')
    page_label = "Page" if source_path.suffix.lower() == '.pdf' else "Section"

    # Improve mode: always extract and compare
    if improve and md_path.exists():
        if dry_run:
            return True, f"Would compare: {md_path.name}", None

        try:
            # Extract new version
            pages = extract_text(
                source_path, use_ocr=use_ocr, ocr_engine=ocr_engine,
                force_ocr=force_ocr, stats=stats, hud=hud, learner=learner,
            )
            new_markdown = create_markdown(source_path, pages, page_label=page_label)
            new_text = '\n'.join(pages)

            # Read and strip existing
            existing_markdown = md_path.read_text(encoding='utf-8')
            existing_text = strip_markdown_metadata(existing_markdown)

            # Compare quality
            is_better, old_metrics, new_metrics = _quality_scorer.compare(existing_text, new_text)

            if is_better:
                md_path.write_text(new_markdown, encoding='utf-8')
                if stats:
                    stats.md_bytes += len(new_markdown.encode('utf-8'))
                detail = f"Improved: {old_metrics.total_score:.2f} → {new_metrics.total_score:.2f}"
                return True, f"Improved: {md_path.name}", detail
            else:
                # Count existing file size for kept files
                if stats:
                    stats.md_bytes += md_path.stat().st_size
                detail = f"Kept existing: {old_metrics.total_score:.2f} > {new_metrics.total_score:.2f}"
                return False, f"Kept (better quality): {source_path.name}", detail

        except Exception as e:
            return False, f"FAILED: {source_path.name} - {e}", None

    # Standard mode: skip existing unless overwrite
    if md_path.exists() and not overwrite:
        return False, f"Skipped (exists): {source_path.name}", None

    if dry_run:
        action = "Would overwrite" if md_path.exists() else "Would create"
        return True, f"{action}: {md_path.name}", None

    try:
        pages = extract_text(
            source_path, use_ocr=use_ocr, ocr_engine=ocr_engine,
            force_ocr=force_ocr, stats=stats, hud=hud, learner=learner,
        )
        markdown_content = create_markdown(source_path, pages, page_label=page_label)
        md_path.write_text(markdown_content, encoding='utf-8')
        if stats:
            stats.md_bytes += len(markdown_content.encode('utf-8'))
        return True, f"Created: {md_path.name}", None
    except Exception as e:
        return False, f"FAILED: {source_path.name} - {e}", None


# Backward compatibility alias
process_pdf = process_document


def _worker_init_suppress_output():
    """Initializer for worker processes to suppress stdout/stderr (for HUD mode).

    Redirects at the OS file descriptor level to catch native code output.
    """
    import os
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, 1)  # redirect stdout
    os.dup2(devnull_fd, 2)  # redirect stderr
    os.close(devnull_fd)


def process_document_worker(
    source_path: Path,
    overwrite: bool,
    dry_run: bool,
    use_ocr: bool,
    ocr_engine: str,
    force_ocr: bool,
    improve: bool
) -> FileResult:
    """Process a single document in a separate process. Returns FileResult for aggregation."""
    md_path = source_path.with_suffix('.md')
    file_size = source_path.stat().st_size
    is_pdf = source_path.suffix.lower() == '.pdf'
    page_label = "Page" if is_pdf else "Section"

    result = FileResult(
        source_path=source_path,
        success=False,
        message="",
        processed_bytes=file_size
    )

    log_msgs = []

    def extract_pages() -> tuple[list[str], int, int]:
        """Extract text, returning (pages, ocr_pages, ocr_chars)."""
        if is_pdf:
            import pymupdf
            doc = pymupdf.open(source_path)

            ocr_available, active_engine, engine_logs = resolve_ocr_engine(ocr_engine, use_ocr)
            log_msgs.extend(engine_logs)

            pages = []
            ocr_pages_count = 0
            ocr_chars_count = 0
            total_pages = len(doc)

            try:
                for page_num, page in enumerate(doc, start=1):
                    engine = active_engine if ocr_available else "none"
                    text, used_ocr, ocr_chars, log_msg = extract_page_text(
                        page, engine, force_ocr, suppress_output=False
                    )

                    if used_ocr:
                        ocr_pages_count += 1
                        ocr_chars_count += ocr_chars
                    if log_msg:
                        log_msgs.append(f"  p{page_num}/{total_pages}: {log_msg}")

                    pages.append(text)
            finally:
                doc.close()

            return pages, ocr_pages_count, ocr_chars_count
        else:
            # Non-PDF: use the format dispatcher (no OCR)
            pages = extract_text(source_path)
            return pages, 0, 0

    # Improve mode: always extract and compare
    if improve and md_path.exists():
        if dry_run:
            result.success = True
            result.message = f"Would compare: {md_path.name}"
            return result

        try:
            pages, ocr_pages_count, ocr_chars_count = extract_pages()
            new_markdown = create_markdown(source_path, pages, page_label=page_label)
            new_text = '\n'.join(pages)

            existing_markdown = md_path.read_text(encoding='utf-8')
            existing_text = strip_markdown_metadata(existing_markdown)

            is_better, old_metrics, new_metrics = _quality_scorer.compare(existing_text, new_text)

            result.pages_processed = len(pages)
            result.ocr_pages = ocr_pages_count
            result.ocr_chars = ocr_chars_count
            result.log_messages = log_msgs

            if is_better:
                md_path.write_text(new_markdown, encoding='utf-8')
                result.md_bytes = len(new_markdown.encode('utf-8'))
                result.success = True
                result.was_improved = True
                result.message = f"Improved: {md_path.name}"
                result.improve_detail = f"Improved: {old_metrics.total_score:.2f} → {new_metrics.total_score:.2f}"
            else:
                result.md_bytes = md_path.stat().st_size
                result.success = False
                result.was_kept = True
                result.message = f"Kept (better quality): {source_path.name}"
                result.improve_detail = f"Kept existing: {old_metrics.total_score:.2f} > {new_metrics.total_score:.2f}"

            return result

        except Exception as e:
            result.was_failed = True
            result.message = f"FAILED: {source_path.name} - {e}"
            result.log_messages = log_msgs
            return result

    # Standard mode: skip existing unless overwrite
    if md_path.exists() and not overwrite:
        result.was_skipped = True
        result.message = f"Skipped (exists): {source_path.name}"
        result.processed_bytes = 0  # Didn't process
        return result

    if dry_run:
        action = "Would overwrite" if md_path.exists() else "Would create"
        result.success = True
        result.message = f"{action}: {md_path.name}"
        return result

    try:
        pages, ocr_pages_count, ocr_chars_count = extract_pages()
        markdown_content = create_markdown(source_path, pages, page_label=page_label)
        md_path.write_text(markdown_content, encoding='utf-8')

        result.md_bytes = len(markdown_content.encode('utf-8'))
        result.pages_processed = len(pages)
        result.ocr_pages = ocr_pages_count
        result.ocr_chars = ocr_chars_count
        result.log_messages = log_msgs
        result.success = True
        result.message = f"Created: {md_path.name}"
        return result

    except Exception as e:
        result.was_failed = True
        result.message = f"FAILED: {source_path.name} - {e}"
        result.log_messages = log_msgs
        return result


# Backward compatibility alias
process_pdf_worker = process_document_worker


def aggregate_result(stats: ProcessingStats, result: FileResult, improve_mode: bool):
    """Aggregate a worker result into processing stats."""
    stats.md_bytes += result.md_bytes
    stats.processed_pages += result.pages_processed
    stats.ocr_pages += result.ocr_pages
    stats.ocr_chars += result.ocr_chars

    if result.was_failed:
        stats.failed_files += 1
    elif result.was_skipped:
        stats.skipped_files += 1
    elif result.was_improved:
        stats.improved_files += 1
        stats.processed_files += 1
        stats.processed_bytes += result.processed_bytes
    elif result.was_kept:
        stats.kept_existing += 1
        stats.processed_files += 1
        stats.processed_bytes += result.processed_bytes
    elif result.success:
        stats.processed_files += 1
        stats.processed_bytes += result.processed_bytes


def run_simple_parallel(documents: list[Path], args, use_ocr: bool, ocr_engine: str, force_ocr: bool, max_workers: int) -> int:
    """Run processing with simple text output using parallel workers."""
    stats = ProcessingStats()
    stats.total_files = len(documents)
    stats.total_bytes = sum(p.stat().st_size for p in documents)
    improve_mode = getattr(args, 'improve', False)

    if args.verbose or args.dry_run:
        if args.dry_run:
            print("(Dry run - no files will be created)")
        if improve_mode:
            print("(Improve mode - comparing quality)")
        print(f"Using {max_workers} parallel workers")
        print(f"OCR engine: {ocr_engine}")
        print()

    with ProcessPoolExecutor(max_workers=max_workers, mp_context=_mp_context) as executor:
        futures = {
            executor.submit(
                process_document_worker,
                doc_path,
                args.overwrite,
                args.dry_run,
                use_ocr,
                ocr_engine,
                force_ocr,
                improve_mode
            ): doc_path for doc_path in sorted(documents)
        }

        for future in as_completed(futures):
            result = future.result()
            aggregate_result(stats, result, improve_mode)

            if args.verbose:
                print(f"  {result.message}")
                if result.improve_detail:
                    print(f"     {result.improve_detail}")
            if getattr(args, 'debug', False) and result.log_messages:
                for msg in result.log_messages:
                    print(f"    [DEBUG] {msg}")

    elapsed = stats.elapsed()

    if not args.quiet:
        print()
        if improve_mode:
            print(f"Summary: {stats.processed_files} processed, {stats.improved_files} improved, {stats.kept_existing} kept existing, {stats.failed_files} failed")
        else:
            print(f"Summary: {stats.processed_files} processed, {stats.skipped_files} skipped, {stats.failed_files} failed")

        if args.verbose and stats.processed_files > 0 and elapsed > 0:
            total_mb = stats.processed_bytes / (1024 * 1024)
            md_mb = stats.md_bytes / (1024 * 1024)
            files_per_min = (stats.processed_files / elapsed) * 60
            mb_per_min = (total_mb / elapsed) * 60
            ratio = (stats.md_bytes / stats.processed_bytes * 100) if stats.processed_bytes > 0 else 0

            print()
            print("Stats:")
            print(f"  Time elapsed:    {elapsed:.1f}s")
            print(f"  Workers used:    {max_workers}")
            print(f"  Input:           {total_mb:.2f} MB ({stats.processed_pages} pages)")
            print(f"  MD output:       {md_mb:.2f} MB ({ratio:.1f}% of input)")
            print(f"  Processing rate: {files_per_min:.1f} files/min, {mb_per_min:.2f} MB/min")
            print(f"  OCR stats:       {stats.ocr_pages} pages, {stats.ocr_chars:,} chars extracted")

    return 1 if stats.failed_files > 0 else 0


def run_with_hud_parallel(documents: list[Path], args, use_ocr: bool, ocr_engine: str, force_ocr: bool, max_workers: int) -> int:
    """Run processing with the retro HUD using parallel workers."""
    stats = ProcessingStats()
    stats.total_files = len(documents)
    stats.total_bytes = sum(p.stat().st_size for p in documents)
    improve_mode = getattr(args, 'improve', False)

    # Create executor BEFORE curses to avoid any startup output interfering
    # Use initializer to suppress output in worker processes
    executor = ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=_mp_context,
        initializer=_worker_init_suppress_output
    )

    # Submit all tasks before entering curses
    futures = {
        executor.submit(
            process_document_worker,
            doc_path,
            args.overwrite,
            args.dry_run,
            use_ocr,
            ocr_engine,
            force_ocr,
            improve_mode
        ): doc_path for doc_path in sorted(documents)
    }

    try:
        with RetroHUD(stats) as hud:
            stats.current_status = f"{max_workers} workers processing..."
            stats.log(f"Parallel mode: {max_workers} workers")
            hud.refresh()

            active_count = len(futures)

            for future in as_completed(futures):
                result = future.result()
                active_count -= 1

                aggregate_result(stats, result, improve_mode)

                stats.current_file = str(result.source_path)
                stats.current_status = f"Workers: {active_count} active | {stats.processed_files + stats.skipped_files + stats.failed_files}/{stats.total_files} done"
                stats.log(f"  → {result.message}")
                if result.improve_detail:
                    stats.log(f"     {result.improve_detail}")

                hud.refresh()

            # Final display
            stats.current_file = ""
            stats.current_status = "COMPLETE"
            stats.log("")
            stats.log("═" * 40)
            stats.log(f" FINISHED - {stats.processed_files} files processed")
            stats.log(f" Workers used: {max_workers}")
            if improve_mode:
                stats.log(f" Improved: {stats.improved_files} | Kept: {stats.kept_existing}")
            stats.log(f" Time: {stats.elapsed():.1f}s | OCR pages: {stats.ocr_pages}")
            stats.log("═" * 40)
            hud.refresh()

            # Wait for keypress
            hud.stdscr.nodelay(False)
            hud.stdscr.addstr(hud.stdscr.getmaxyx()[0] - 1, 2, "Press any key to exit...",
                             curses.color_pair(3) | curses.A_BLINK)
            hud.stdscr.refresh()
            hud.stdscr.getch()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return 1 if stats.failed_files > 0 else 0


def run_with_hud(
    documents: list[Path],
    args,
    use_ocr: bool,
    ocr_engine: str,
    force_ocr: bool,
    learner: AdaptiveLearner | None = None,
) -> int:
    """Run processing with the retro HUD."""
    stats = ProcessingStats()
    stats.total_files = len(documents)
    stats.total_bytes = sum(p.stat().st_size for p in documents)
    improve_mode = getattr(args, 'improve', False)

    with RetroHUD(stats, learner=learner) as hud:
        hud.refresh()

        for doc_path in sorted(documents):
            stats.current_file = str(doc_path)
            stats.current_page = 0
            stats.current_file_pages = 0
            file_size = doc_path.stat().st_size

            # Skip files already processed when learning is enabled (deduplication)
            if learner and learner.enabled and learner.is_file_processed(doc_path):
                stats.log(f"Skipping (already learned): {doc_path.name}")
                stats.skipped_files += 1
                hud.refresh()
                continue

            stats.log(f"Processing: {doc_path.name}")
            hud.refresh()

            success, message, improve_detail = process_document(
                doc_path,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                use_ocr=use_ocr,
                ocr_engine=ocr_engine,
                force_ocr=force_ocr,
                improve=improve_mode,
                stats=stats,
                hud=hud,
                learner=learner,
            )

            stats.log(f"  → {message}")
            if improve_detail:
                stats.log(f"     {improve_detail}")

            if improve_mode and "Improved:" in message:
                stats.improved_files += 1
                stats.processed_files += 1
                stats.processed_bytes += file_size
            elif improve_mode and "Kept" in message:
                stats.kept_existing += 1
                stats.processed_files += 1  # Count for throughput (we did extract)
                stats.processed_bytes += file_size
            elif success:
                stats.processed_files += 1
                stats.processed_bytes += file_size
            elif "Skipped" in message:
                stats.skipped_files += 1
            else:
                stats.failed_files += 1

            hud.refresh()

        # Final display
        stats.current_file = ""
        stats.current_status = "COMPLETE"
        stats.log("")
        stats.log("═" * 40)
        stats.log(f" FINISHED - {stats.processed_files} files processed")
        if improve_mode:
            stats.log(f" Improved: {stats.improved_files} | Kept: {stats.kept_existing}")
        stats.log(f" Time: {stats.elapsed():.1f}s | OCR pages: {stats.ocr_pages}")
        # Show learning stats if enabled
        if learner and learner.enabled:
            learn_stats = learner._stats
            if learn_stats["images_seen"] > 0:
                stats.log(f" Learning: {learn_stats['images_ocrd']} OCR'd, {learn_stats['images_skipped']} skipped")
        stats.log("═" * 40)
        hud.refresh()

        # Wait for keypress
        hud.stdscr.nodelay(False)
        hud.stdscr.addstr(hud.stdscr.getmaxyx()[0] - 1, 2, "Press any key to exit...",
                         curses.color_pair(3) | curses.A_BLINK)
        hud.stdscr.refresh()
        hud.stdscr.getch()

    return 1 if stats.failed_files > 0 else 0


def run_simple(
    documents: list[Path],
    args,
    use_ocr: bool,
    ocr_engine: str,
    force_ocr: bool,
    learner: AdaptiveLearner | None = None,
) -> int:
    """Run processing with simple text output."""
    stats = ProcessingStats()
    stats.total_files = len(documents)
    stats.total_bytes = sum(p.stat().st_size for p in documents)
    improve_mode = getattr(args, 'improve', False)

    if args.verbose or args.dry_run:
        if args.dry_run:
            print("(Dry run - no files will be created)")
        if improve_mode:
            print("(Improve mode - comparing quality)")
        if learner and learner.enabled:
            print("(Adaptive learning enabled)")
        print(f"OCR engine: {ocr_engine}")
        print()

    for doc_path in sorted(documents):
        # Skip files already processed when learning is enabled (deduplication)
        if learner and learner.enabled and learner.is_file_processed(doc_path):
            if args.verbose:
                print(f"Skipping (already learned): {doc_path}")
            stats.skipped_files += 1
            continue

        if args.verbose:
            print(f"Processing: {doc_path}")

        file_size = doc_path.stat().st_size

        success, message, improve_detail = process_document(
            doc_path,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            use_ocr=use_ocr,
            ocr_engine=ocr_engine,
            force_ocr=force_ocr,
            improve=improve_mode,
            stats=stats,
            learner=learner,
        )

        if args.verbose:
            print(f"  {message}")
            if improve_detail:
                print(f"     {improve_detail}")
        if getattr(args, 'debug', False) and stats.log_messages:
            for msg in stats.log_messages:
                print(f"    [DEBUG] {msg}")
            stats.log_messages.clear()

        if improve_mode and "Improved:" in message:
            stats.improved_files += 1
            stats.processed_files += 1
            stats.processed_bytes += file_size
        elif improve_mode and "Kept" in message:
            stats.kept_existing += 1
            stats.processed_files += 1
            stats.processed_bytes += file_size
        elif success:
            stats.processed_files += 1
            stats.processed_bytes += file_size
        elif "Skipped" in message:
            stats.skipped_files += 1
        else:
            stats.failed_files += 1

    elapsed = stats.elapsed()

    if not args.quiet:
        print()
        if improve_mode:
            print(f"Summary: {stats.processed_files} processed, {stats.improved_files} improved, {stats.kept_existing} kept existing, {stats.failed_files} failed")
        else:
            print(f"Summary: {stats.processed_files} processed, {stats.skipped_files} skipped, {stats.failed_files} failed")

        if args.verbose and stats.processed_files > 0 and elapsed > 0:
            total_mb = stats.processed_bytes / (1024 * 1024)
            md_mb = stats.md_bytes / (1024 * 1024)
            files_per_min = (stats.processed_files / elapsed) * 60
            mb_per_min = (total_mb / elapsed) * 60
            ratio = (stats.md_bytes / stats.processed_bytes * 100) if stats.processed_bytes > 0 else 0

            print()
            print("Stats:")
            print(f"  Time elapsed:    {elapsed:.1f}s")
            print(f"  Input:           {total_mb:.2f} MB ({stats.processed_pages} pages)")
            print(f"  MD output:       {md_mb:.2f} MB ({ratio:.1f}% of input)")
            print(f"  Processing rate: {files_per_min:.1f} files/min, {mb_per_min:.2f} MB/min")
            print(f"  OCR stats:       {stats.ocr_pages} pages, {stats.ocr_chars:,} chars extracted")

        # Print learning stats if enabled
        if learner and learner.enabled:
            ls = learner._stats
            if ls["images_seen"] > 0:
                print()
                print("Learning:")
                print(f"  Images seen:     {ls['images_seen']:,}")
                print(f"  Images OCR'd:    {ls['images_ocrd']:,} ({ls['ocr_useful']} useful, {ls['ocr_empty']} empty)")
                print(f"  Images skipped:  {ls['images_skipped']:,}")

                # OCR efficiency
                total_ocrd = ls['ocr_useful'] + ls['ocr_empty']
                if total_ocrd > 0:
                    ocr_eff = ls['ocr_useful'] / total_ocrd * 100
                    print(f"  OCR efficiency:  {ocr_eff:.1f}% found useful text")

                # Exploration accuracy
                exp_total = ls['exploration_useful'] + ls['exploration_empty']
                if exp_total > 0:
                    miss_rate = ls['exploration_useful'] / exp_total * 100
                    print(f"  Exploration:     {exp_total} samples, {miss_rate:.1f}% would be missed if skipped")

                # Quality tracking
                if ls.get("files_with_existing_md", 0) > 0:
                    print(f"  Quality:         {ls['files_with_existing_md']} compared, ", end="")
                    print(f"{ls['quality_improved']} improved, {ls['quality_unchanged']} same", end="")
                    if ls.get("quality_regressions"):
                        print(f", {len(ls['quality_regressions'])} regressed")
                    else:
                        print()

            # Quality regression alerts
            regressions = ls.get("quality_regressions", [])
            if regressions:
                print()
                print("⚠️  QUALITY REGRESSION ALERT")
                print("  The following files had lower quality scores than before:")
                for reg in regressions[:5]:  # Show max 5
                    print(f"    {Path(reg['path']).name}: {reg['old_score']:.2f} → {reg['new_score']:.2f} ({reg['delta']:+.2f})")
                if len(regressions) > 5:
                    print(f"    ... and {len(regressions) - 5} more")
                print("  Tip: Model may have incorrectly skipped images in these files")

    return 1 if stats.failed_files > 0 else 0


def print_learning_stats(stats: dict) -> None:
    """Print formatted learning statistics."""
    print("═" * 63)
    print("  PDF2TXT - LEARNING STATISTICS")
    print("═" * 63)
    print(f"  Files processed: {stats['processed_files']:,}", end="")
    qs = stats.get('quality_stats', {})
    if qs.get('files_with_comparison', 0) > 0:
        print(f"  ({qs['files_with_comparison']:,} with existing .md)")
    else:
        print()
    print()

    # Quality tracking section
    if qs.get('files_with_quality', 0) > 0:
        print("  Quality Tracking:")
        print(f"    Average quality score: {qs['avg_quality_score']:.2f}")
        if qs.get('files_with_comparison', 0) > 0:
            print(f"    Quality improved: {qs['quality_improved']:,} files", end="")
            if qs.get('avg_improvement', 0) > 0:
                print(f" (+{qs['avg_improvement']:.1%} avg)")
            else:
                print()
            print(f"    Quality unchanged: {qs['quality_unchanged']:,} files")
            if qs['quality_regressed'] > 0:
                print(f"    Quality regressed: {qs['quality_regressed']:,} files", end="")
                if qs.get('avg_regression', 0) < 0:
                    print(f" ({qs['avg_regression']:.1%} avg)  ⚠️")
                else:
                    print("  ⚠️")
        print()

    # OCR learning section
    print("  OCR Learning:")
    print(f"    Images in PDFs: {stats['total_images_seen']:,}")
    print(f"    OCR decisions: {stats['total_records']:,}")
    if stats['total_records'] > 0:
        skipped = stats['total_records'] - stats['ocrd_records']
        skip_pct = skipped / stats['total_records'] * 100
        print(f"    Images skipped: {skipped:,} ({skip_pct:.1f}%)")
    if stats.get('skip_accuracy') is not None:
        print(f"    Skip accuracy: {stats['skip_accuracy']:.1%} (no quality loss)")
    # Skip validation: tests of "would skip" decisions
    if stats.get('skip_validation_total', 0) > 0:
        sv_total = stats['skip_validation_total']
        sv_useful = stats['skip_validation_useful']
        sv_error = stats.get('skip_validation_error_rate', 0) or 0
        print(f"    Skip validation: {sv_total} tested, {sv_useful} useful ({sv_error:.0%} error rate)")
        # Warn about corpus mismatch when error rate is very high
        if sv_error > 0.30:
            print("    ⚠️  HIGH MISS RATE: Classifier may be trained on different document types")
            print("       Consider: ./pdf2txt.py --learn-reset to retrain on this corpus")
    print()

    # Classifier section
    print("  Classifier:")
    if not stats.get('sklearn_available', True):
        print("    ✗ scikit-learn not available (using heuristics)")
        sklearn_error = stats.get('sklearn_error')
        if sklearn_error:
            print(f"    Error: {sklearn_error}")
        else:
            print("    Install with: pip install scikit-learn")
        # Show Python environment for debugging
        import sys
        print(f"    Python: {sys.executable}")
    elif stats['classifier_ready']:
        print(f"    ✓ Trained on {stats['training_samples']:,} samples")
        print(f"    Exploration rate: {stats['exploration_rate']:.1%} (adaptive)")
        # Show calibration status
        print(f"    Last retrain at: {stats['last_train_count']:,} samples")
    else:
        needed = AdaptiveLearner.MIN_SAMPLES_FOR_PREDICTION - stats['training_samples']
        if needed > 0:
            print(f"    ✗ Not ready (need {needed} more samples)")
        else:
            print(f"    ✗ Not yet trained ({stats['training_samples']} samples available)")
        print(f"    Exploration rate: {stats['exploration_rate']:.0%} (learning mode)")
    print("═" * 63)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract text from documents (PDF, DOCX, DOC, RTF, ODT) and create markdown files."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "directory",
        help="Directory to search for documents (supports Windows paths in WSL)"
    )

    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed progress"
    )
    verbosity.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all output except errors"
    )

    parser.add_argument(
        "--hud",
        action="store_true",
        help="Show retro 80's style HUD (implies verbose)"
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="List PDFs that would be processed without creating files"
    )
    parser.add_argument(
        "-f", "--force", "--overwrite",
        action="store_true",
        dest="overwrite",
        help="Overwrite existing .md files (default: skip)"
    )
    parser.add_argument(
        "--improve",
        action="store_true",
        help="Re-extract and only overwrite if new extraction is better quality"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Search for documents recursively in subdirectories"
    )
    parser.add_argument(
        "--formats",
        type=str,
        default=None,
        metavar="FORMATS",
        help="Comma-separated formats to process (pdf,docx,doc,rtf,odt). Default: all supported"
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR for image-based pages"
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Force OCR on all pages, even those with extractable text"
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU mode for OCR (slower but avoids GPU memory issues)"
    )
    parser.add_argument(
        "--ocr-engine",
        choices=["paddle", "surya", "tesseract"],
        default="surya",
        help="OCR engine to use (default: surya). Note: PaddleOCR v3.3 has a known bug, use surya or tesseract instead."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show detailed OCR debug information"
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=None,
        metavar="N",
        help="Number of parallel workers (default: CPU count - 1, use 1 for sequential)"
    )

    # Adaptive learning options
    parser.add_argument(
        "--learn",
        action="store_true",
        help="Enable adaptive OCR learning (learns which images are worth OCR'ing)"
    )
    parser.add_argument(
        "--learn-db",
        type=str,
        metavar="PATH",
        help="Custom path for learning database (default: ~/.pdf2txt/learning.db)"
    )
    parser.add_argument(
        "--learn-stats",
        action="store_true",
        help="Print learning statistics and exit"
    )
    parser.add_argument(
        "--learn-reset",
        action="store_true",
        help="Reset the learning database and exit"
    )
    parser.add_argument(
        "--learn-retrain",
        action="store_true",
        help="Force retrain the classifier on collected data and exit"
    )
    parser.add_argument(
        "--learn-shuffle",
        action="store_true",
        default=None,
        help="Shuffle file order for diverse early learning (default: ON with --learn)"
    )
    parser.add_argument(
        "--no-learn-shuffle",
        action="store_true",
        help="Process files in sorted order even with --learn"
    )

    args = parser.parse_args()

    # Force CPU mode if requested (must be set before any CUDA imports)
    if args.cpu:
        os.environ['CUDA_VISIBLE_DEVICES'] = ''

    # Handle learning database commands early
    learn_db_path = Path(args.learn_db) if args.learn_db else None

    # --learn-stats without --learn: show stats and exit
    # --learn-stats with --learn: process files, stats shown at end
    if args.learn_stats and not args.learn:
        learner = AdaptiveLearner(db_path=learn_db_path, enabled=True)
        stats = learner.get_stats()
        if not stats["enabled"]:
            print("Learning database not found or empty.")
            return 0

        print_learning_stats(stats)
        learner.close()
        return 0

    if args.learn_reset:
        learner = AdaptiveLearner(db_path=learn_db_path, enabled=True)
        db_path = learner.db_path
        learner.reset()
        print(f"Learning database reset: {db_path}")
        learner.close()
        return 0

    if args.learn_retrain:
        learner = AdaptiveLearner(db_path=learn_db_path, enabled=True)
        print("Retraining classifier on OCR outcomes...")
        learner.retrain(force=True)
        stats = learner.get_stats()
        print(f"Trained classifier on {stats['training_samples']} samples")
        print(f"Classifier ready: {stats['classifier_ready']}")
        learner.close()
        return 0

    # Convert and validate path
    directory = convert_windows_path(args.directory)

    if not directory.exists():
        print(f"Error: Directory does not exist: {directory}", file=sys.stderr)
        return 1

    if not directory.is_dir():
        print(f"Error: Path is not a directory: {directory}", file=sys.stderr)
        return 1

    # Check OCR availability
    use_ocr = not args.no_ocr
    ocr_engine = args.ocr_engine
    force_ocr = getattr(args, 'force_ocr', False)

    if args.debug:
        print_gpu_debug_info()
        print("[DEBUG] OCR engine availability:")
        print(f"  Surya: {check_surya_available()}")
        print(f"  PaddleOCR: {check_paddleocr_available()}")
        print(f"  Tesseract: {check_tesseract_available()}")
        print(f"  Requested: {args.ocr_engine}")
        # Pre-configure and show Surya batch sizes if using surya
        if args.ocr_engine == "surya" and check_surya_available():
            configure_surya_batch_sizes()
            rec_batch = os.environ.get('RECOGNITION_BATCH_SIZE', '512 (default)')
            det_batch = os.environ.get('DETECTOR_BATCH_SIZE', 'default')
            print(f"  Surya batch sizes: recognition={rec_batch}, detection={det_batch}")
        print()

    if use_ocr:
        # Check if requested engine is available, with fallback
        if ocr_engine == "surya" and not check_surya_available():
            if not args.quiet:
                print("Warning: Surya not available, trying PaddleOCR...", file=sys.stderr)
            ocr_engine = "paddle"

        if ocr_engine == "paddle" and not check_paddleocr_available():
            if not args.quiet:
                print("Warning: PaddleOCR not available, trying Tesseract...", file=sys.stderr)
            ocr_engine = "tesseract"

        if ocr_engine == "tesseract" and not check_tesseract_available():
            if not args.quiet:
                print("Warning: No OCR engine available. OCR disabled.", file=sys.stderr)
                print("Install with: pip install paddleocr paddlepaddle", file=sys.stderr)
            use_ocr = False

    # Find documents
    # Parse --formats flag
    formats = None
    if args.formats:
        formats = {f'.{f.strip().lower().lstrip(".")}' for f in args.formats.split(',')}
        unsupported = formats - SUPPORTED_EXTENSIONS
        if unsupported:
            print(f"Error: Unsupported format(s): {', '.join(unsupported)}", file=sys.stderr)
            print(f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}", file=sys.stderr)
            return 1

    # Determine shuffle: default ON with --learn, unless --no-learn-shuffle
    should_shuffle = False
    if args.learn:
        should_shuffle = not args.no_learn_shuffle  # Default ON with --learn
    if args.learn_shuffle:
        should_shuffle = True  # Explicit --learn-shuffle overrides

    documents = find_documents(
        directory,
        recursive=args.recursive,
        quiet=args.quiet,
        shuffle=should_shuffle,
        formats=formats,
    )

    if not documents:
        return 0

    # Determine worker count
    # OCR is memory-intensive (each worker loads 1-2GB+ ML models), so limit parallelism
    # Non-PDF extraction is lightweight and can use more workers
    cpu_count = os.cpu_count() or 4
    has_pdfs = any(d.suffix.lower() == '.pdf' for d in documents)
    if use_ocr and has_pdfs:
        # OCR is memory-intensive; Surya loads large GPU models per worker
        if ocr_engine == "surya":
            # Surya requires ~4GB VRAM per worker; use single worker to avoid OOM
            default_workers = 1
        else:
            # PaddleOCR/Tesseract: max 2 workers to avoid memory exhaustion
            default_workers = min(2, cpu_count - 1)
    else:
        # Non-PDF or text-only extraction can safely use more parallelism
        default_workers = max(cpu_count - 1, 1)
    max_workers = args.jobs if args.jobs is not None else default_workers
    max_workers = max(1, max_workers)  # Ensure at least 1

    # Create learner if learning is enabled
    # Note: Learning only works in sequential mode (max_workers=1) because
    # the SQLite database doesn't work well across process boundaries
    learner = None
    if args.learn:
        if max_workers > 1:
            if not args.quiet:
                print("Note: Adaptive learning requires sequential mode (-j 1). Disabling parallelism.", file=sys.stderr)
            max_workers = 1
        learner = AdaptiveLearner(db_path=learn_db_path, enabled=True)
        if not args.quiet:
            stats = learner.get_stats()
            print(f"Adaptive learning enabled (db: {learner.db_path})")
            if stats['processed_files'] > 0:
                print(f"  History: {stats['processed_files']} files, {stats['total_images_seen']} images, {stats['overall_useful_rate']:.1%} useful")
            print()

    try:
        # Run with HUD or simple mode, sequential or parallel
        if max_workers == 1:
            # Sequential processing (original behavior)
            if args.hud and not args.dry_run:
                result = run_with_hud(documents, args, use_ocr, ocr_engine, force_ocr, learner=learner)
            else:
                result = run_simple(documents, args, use_ocr, ocr_engine, force_ocr, learner=learner)
        else:
            # Parallel processing (no learner support)
            if args.hud and not args.dry_run:
                result = run_with_hud_parallel(documents, args, use_ocr, ocr_engine, force_ocr, max_workers)
            else:
                result = run_simple_parallel(documents, args, use_ocr, ocr_engine, force_ocr, max_workers)

        # Show detailed stats if --learn-stats was requested with --learn
        if args.learn_stats and learner:
            stats = learner.get_stats()
            print()
            print_learning_stats(stats)

        return result
    finally:
        if learner:
            learner.close()


if __name__ == "__main__":
    sys.exit(main())
