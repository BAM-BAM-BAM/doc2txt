"""OCR engines (Tesseract, PaddleOCR, Surya), GPU management, and per-page PDF text extraction."""

import os
import re

from doc2txt_models import ImageFeature
from doc2txt_learning import AdaptiveLearner


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


# Engines tried, in order, for each name the CLI and the watcher accept. PaddleOCR runs
# only when named: PaddlePaddle 3.3 on this CPU raises NotImplementedError (oneDNN), and
# MemoryError with oneDNN off, so it must never be picked as a fallback.
OCR_FALLBACKS = {
    "auto": ["surya", "tesseract"],
    "surya": ["surya", "tesseract"],
    "paddle": ["paddle"],
    "tesseract": ["tesseract"],
}


def resolve_ocr_engine(requested: str, use_ocr: bool = True) -> tuple[bool, str, list[str]]:
    """Resolve which OCR engine to use with fallback chain.

    Args:
        requested: A key of OCR_FALLBACKS, or "none"
        use_ocr: Whether OCR is enabled

    Returns:
        Tuple of (ocr_available, actual_engine, log_messages)
    """
    log_msgs = []

    if not use_ocr or requested == "none":
        return False, "none", ["OCR: disabled"]

    engines = OCR_FALLBACKS[requested]
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

    import pymupdf
    region = pymupdf.Rect(bbox[0], bbox[1], bbox[2], bbox[3])

    # Render just this region at the specified DPI. Image rects are in unrotated page
    # space; get_pixmap clips in rotated space.
    mat = pymupdf.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, clip=region * page.rotation_matrix)

    # Skip tiny images (likely decorative). This also skips a region with no area on the
    # page (off the page, or a sliver along its edge), whose zero-sized pixmap would make
    # tobytes() raise.
    if pix.width < 20 or pix.height < 10:
        return "", False

    img = Image.open(io.BytesIO(pix.tobytes("png")))

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
        ocr_pdf = pymupdf.open("pdf", pix.pdfocr_tobytes(language="eng"))
        text = ocr_pdf[0].get_text().strip()

    if _repeats_text_layer(text, page, region):
        text = ""

    # Record outcome for learning
    if learner and features:
        learner.record_outcome(features, pdf_path, page_num, image_index, True, text, is_exploration, ocr_reason)

    return text, True


def _repeats_text_layer(ocr_text: str, page, region) -> bool:
    """True when most OCR words already sit in the page's text layer inside region.

    Scanned PDFs often carry an invisible OCR text layer over the page image, so OCRing
    the image again would print its words twice. Text-layer words are in unrotated page
    space, like region.
    """
    ocr_words = [w for w in re.findall(r"[a-z0-9]+", ocr_text.lower()) if len(w) >= 2]
    if not ocr_words:
        return False
    layer_text = " ".join(w[4] for w in page.get_text("words", clip=region)).lower()
    layer_words = set(re.findall(r"[a-z0-9]+", layer_text))
    return sum(w in layer_words for w in ocr_words) >= 0.8 * len(ocr_words)


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
    # Text blocks with positions: (x0, y0, x1, y1, text, block_no, block_type).
    # Without TEXT_PRESERVE_IMAGES there are no image blocks; images come from get_images().
    blocks = page.get_text("blocks")

    content_blocks = []  # (y0, text, is_ocr)

    ocr_regions = 0
    ocr_chars = 0
    skipped_regions = 0
    image_index = 0

    processed_rects = []

    for block in blocks:
        x0, y0, x1, y1, content, block_no, block_type = block
        text = content.strip()
        if text:
            content_blocks.append((y0, text, False))

    for img_info in page.get_images(full=True):
        xref = img_info[0]
        for rect in page.get_image_rects(xref):
            # Skip an area already OCR'd (the same image placed twice)
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
        ocr_engine: Resolved OCR engine ("surya", "paddle", "tesseract", or "none");
            see resolve_ocr_engine. OCR errors propagate: a document whose image
            cannot be OCR'd fails rather than losing that image's text.
        force_ocr: Force full-page OCR regardless of content
        suppress_output: Suppress stdout/stderr during processing
        learner: Optional AdaptiveLearner for image skip decisions
        pdf_path: PDF file path for learning
        page_num: Page number for learning

    Returns:
        Tuple of (text, used_ocr, ocr_chars, log_message)
    """
    if ocr_engine == "none":
        with SuppressOutputFD(suppress=suppress_output):
            text = page.get_text().strip()
        return text, False, 0, ""

    has_images = len(page.get_images(full=False)) > 0

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
