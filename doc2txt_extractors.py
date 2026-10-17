"""Document discovery, per-format text extraction, and conversion of one document to markdown."""

import os
import random
import re
import stat
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

from doc2txt_models import (
    SUPPORTED_EXTENSIONS,
    ProcessingStats,
    FileResult,
)
from doc2txt_quality import strip_markdown_metadata, _quality_scorer
from doc2txt_learning import AdaptiveLearner
from doc2txt_hud import RetroHUD
from doc2txt_ocr import (
    resolve_ocr_engine,
    extract_page_text,
    SuppressOutputFD,
)


# Microsoft Office "owner" (lock) files: ~$ plus the document's name, same
# extension, ~162 bytes, left behind when Office crashes. Never a document.
OFFICE_OWNER_PREFIX = "~$"


def iter_documents(
    directory: Path,
    recursive: bool,
    extensions: set[str],
    on_skip: Callable[[Path, OSError], None],
) -> Iterator[Path]:
    """Yield files under directory whose lowercased suffix is in extensions,
    except Office owner files (OFFICE_OWNER_PREFIX).

    Follows symlinked files and directories. Each directory is walked once,
    keyed by (st_dev, st_ino), so link cycles terminate. Whatever cannot be
    read (dangling or unmappable link, unlistable directory, file whose stat
    fails) goes to on_skip
    and the walk continues; Path.rglob drops these silently and never
    descends symlinked directories.
    """
    try:
        root = os.stat(directory)
    except OSError as e:
        on_skip(directory, e)
        return
    visited = {(root.st_dev, root.st_ino)}
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError as e:
            on_skip(current, e)
            continue
        for entry in entries:
            path = Path(entry.path)
            wanted = path.suffix.lower() in extensions and not entry.name.startswith(OFFICE_OWNER_PREFIX)
            if not (wanted or recursive):
                continue
            try:
                if not (wanted or entry.is_symlink() or entry.is_dir(follow_symlinks=False)):
                    continue
                st = os.stat(entry.path)
            except OSError as e:
                on_skip(path, e)
                continue
            if stat.S_ISDIR(st.st_mode):
                if recursive and (st.st_dev, st.st_ino) not in visited:
                    visited.add((st.st_dev, st.st_ino))
                    pending.append(path)
            elif wanted and stat.S_ISREG(st.st_mode):
                yield path


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

    def warn(path: Path, err: OSError) -> None:
        if not quiet:
            print(f"Warning: skipping {path}: {err.strerror or err}", file=sys.stderr, flush=True)

    result = list(iter_documents(directory, recursive, extensions, warn))

    if shuffle:
        random.shuffle(result)
        if not quiet:
            print(f"Found {len(result)} document(s) (shuffled for learning)", flush=True)
    else:
        if not quiet:
            print(f"Found {len(result)} document(s)", flush=True)

    return result


# Status labels that result counters and the watcher compare against.
# A process_document message is "<status>: <name>[ - <error>]"; no label contains ": ".
STATUS_IMPROVED = "Improved"
STATUS_KEPT = "Kept (better quality)"
STATUS_SKIPPED = "Skipped (exists)"


def result_status(message: str) -> str:
    """The status label of a process_document message: the text before the first ': '."""
    return message.partition(": ")[0]


def check_libreoffice_available() -> bool:
    """Check if LibreOffice Writer is available for .doc/.rtf/.odt conversion.

    `libreoffice` alone is not enough: a Calc-only install has it, and then exits 0
    without output for every Writer document. libreoffice-writer ships `lowriter`.
    """
    import shutil
    return shutil.which("lowriter") is not None


def extract_text_from_pdf(
    pdf_path: Path,
    use_ocr: bool = True,
    ocr_engine: str = "auto",
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
    engine = active_engine if ocr_available else "none"

    total_pages = len(doc)
    if stats:
        stats.current_file_pages = total_pages
        stats.total_pages += total_pages
        stats.current_file_ocr_engine = engine
        stats.current_file_image_pages = 0
        stats.current_file_ocr_text_pages = 0

    pages = []
    try:
        for page_num, page in enumerate(doc, start=1):
            if stats:
                stats.current_page = page_num
                stats.current_status = f"Reading page {page_num}/{total_pages}"
                if hud:
                    hud.refresh()

            # Extract page text (with OCR if available and needed)
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
                stats.current_file_image_pages += bool(page.get_images(full=False))
                stats.current_file_ocr_text_pages += ocr_chars > 0

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
    ocr_engine: str = "auto",
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


def code_version() -> str:
    """Short commit of the checkout this module runs from, or "unknown"."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=5,
            # Run from another repo's git hook, GIT_DIR would name that repo's commit
            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else "unknown"


# Computed at import, so a long-running process keeps stamping the code it loaded.
CODE_VERSION = code_version()


def create_markdown(
    source_path: Path,
    pages: list[str],
    page_label: str = "Page",
    *,
    ocr: tuple[str, bool, int, int] | None,
) -> str:
    """Create markdown content from extracted text sections.

    ocr is (engine, force_ocr, image_pages, ocr_text_pages) for a PDF, None for other formats.
    """
    made_by = f"> Made by doc2txt {CODE_VERSION} on {date.today().isoformat()}"
    if ocr is not None:
        import pymupdf
        engine, force_ocr, image_pages, ocr_text_pages = ocr
        every_page = ", every page" if force_ocr and engine != "none" else ""
        made_by += (
            f" · pymupdf {pymupdf.__version__} · OCR engine: {engine}{every_page}"
            f" · {len(pages)} pages, {image_pages} with images, OCR text on {ocr_text_pages}"
        )
    lines = [
        f"# {source_path.stem}",
        "",
        f"> Source: {source_path.absolute()}",
        ">",
        made_by,
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
    ocr_engine: str = "auto",
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
    doc_stats = stats if stats is not None else ProcessingStats()

    # Improve mode: always extract and compare
    if improve and md_path.exists():
        if dry_run:
            return True, f"Would compare: {md_path.name}", None

        try:
            # Extract new version
            pages = extract_text(
                source_path, use_ocr=use_ocr, ocr_engine=ocr_engine,
                force_ocr=force_ocr, stats=doc_stats, hud=hud, learner=learner,
            )
            new_markdown = create_markdown(
                source_path, pages, page_label=page_label,
                ocr=_pdf_ocr_facts(source_path, doc_stats, force_ocr),
            )
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
                return True, f"{STATUS_IMPROVED}: {md_path.name}", detail
            else:
                # Count existing file size for kept files
                if stats:
                    stats.md_bytes += md_path.stat().st_size
                detail = f"Kept existing: {old_metrics.total_score:.2f} > {new_metrics.total_score:.2f}"
                return False, f"{STATUS_KEPT}: {source_path.name}", detail

        except Exception as e:
            return False, f"FAILED: {source_path.name} - {e}", None

    # Standard mode: skip existing unless overwrite
    if md_path.exists() and not overwrite:
        return False, f"{STATUS_SKIPPED}: {source_path.name}", None

    if dry_run:
        action = "Would overwrite" if md_path.exists() else "Would create"
        return True, f"{action}: {md_path.name}", None

    try:
        pages = extract_text(
            source_path, use_ocr=use_ocr, ocr_engine=ocr_engine,
            force_ocr=force_ocr, stats=doc_stats, hud=hud, learner=learner,
        )
        markdown_content = create_markdown(
            source_path, pages, page_label=page_label,
            ocr=_pdf_ocr_facts(source_path, doc_stats, force_ocr),
        )
        md_path.write_text(markdown_content, encoding='utf-8')
        if stats:
            stats.md_bytes += len(markdown_content.encode('utf-8'))
        return True, f"Created: {md_path.name}", None
    except Exception as e:
        return False, f"FAILED: {source_path.name} - {e}", None


def _pdf_ocr_facts(
    source_path: Path, stats: ProcessingStats, force_ocr: bool,
) -> tuple[str, bool, int, int] | None:
    """create_markdown's ocr argument, from what extract_text_from_pdf recorded on stats."""
    if source_path.suffix.lower() != '.pdf':
        return None
    return (stats.current_file_ocr_engine, force_ocr,
            stats.current_file_image_pages, stats.current_file_ocr_text_pages)


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

    def extract_pages() -> tuple[list[str], int, int, tuple[str, bool, int, int] | None]:
        """Extract text, returning (pages, ocr_pages, ocr_chars, create_markdown's ocr)."""
        if is_pdf:
            import pymupdf
            doc = pymupdf.open(source_path)

            ocr_available, active_engine, engine_logs = resolve_ocr_engine(ocr_engine, use_ocr)
            log_msgs.extend(engine_logs)
            engine = active_engine if ocr_available else "none"

            pages = []
            ocr_pages_count = 0
            ocr_chars_count = 0
            image_pages = 0
            ocr_text_pages = 0
            total_pages = len(doc)

            try:
                for page_num, page in enumerate(doc, start=1):
                    text, used_ocr, ocr_chars, log_msg = extract_page_text(
                        page, engine, force_ocr, suppress_output=False
                    )

                    if used_ocr:
                        ocr_pages_count += 1
                        ocr_chars_count += ocr_chars
                    if log_msg:
                        log_msgs.append(f"  p{page_num}/{total_pages}: {log_msg}")
                    image_pages += bool(page.get_images(full=False))
                    ocr_text_pages += ocr_chars > 0

                    pages.append(text)
            finally:
                doc.close()

            return pages, ocr_pages_count, ocr_chars_count, (engine, force_ocr, image_pages, ocr_text_pages)
        else:
            # Non-PDF: use the format dispatcher (no OCR)
            pages = extract_text(source_path)
            return pages, 0, 0, None

    # Improve mode: always extract and compare
    if improve and md_path.exists():
        if dry_run:
            result.success = True
            result.message = f"Would compare: {md_path.name}"
            return result

        try:
            pages, ocr_pages_count, ocr_chars_count, ocr = extract_pages()
            new_markdown = create_markdown(source_path, pages, page_label=page_label, ocr=ocr)
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
                result.message = f"{STATUS_IMPROVED}: {md_path.name}"
                result.improve_detail = f"Improved: {old_metrics.total_score:.2f} → {new_metrics.total_score:.2f}"
            else:
                result.md_bytes = md_path.stat().st_size
                result.success = False
                result.was_kept = True
                result.message = f"{STATUS_KEPT}: {source_path.name}"
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
        result.message = f"{STATUS_SKIPPED}: {source_path.name}"
        result.processed_bytes = 0  # Didn't process
        return result

    if dry_run:
        action = "Would overwrite" if md_path.exists() else "Would create"
        result.success = True
        result.message = f"{action}: {md_path.name}"
        return result

    try:
        pages, ocr_pages_count, ocr_chars_count, ocr = extract_pages()
        markdown_content = create_markdown(source_path, pages, page_label=page_label, ocr=ocr)
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
