#!/usr/bin/env python3
"""Extract text from documents (PDF, DOCX, DOC, RTF, ODT) and create corresponding markdown files."""

import argparse
import curses
import multiprocessing
import os
import re
import sys
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from doc2txt_models import (
    __version__,
    SUPPORTED_EXTENSIONS,
    parse_formats,
    ProcessingStats,
    FileResult,
)
from doc2txt_learning import AdaptiveLearner
from doc2txt_hud import RetroHUD
from doc2txt_ocr import (
    OCR_FALLBACKS,
    check_tesseract_available,
    check_paddleocr_available,
    check_surya_available,
    print_gpu_debug_info,
    configure_surya_batch_sizes,
    resolve_ocr_engine,
)
from doc2txt_extractors import (
    find_documents,
    STATUS_IMPROVED,
    STATUS_KEPT,
    STATUS_SKIPPED,
    result_status,
    process_document,
    _worker_init_suppress_output,
    process_document_worker,
)

# Use spawn to avoid terminal/curses issues with fork
_mp_context = multiprocessing.get_context("spawn")


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


def _ellipsize(text: str, width: int) -> str:
    """Shorten text to width, keeping its first and last characters around '...'.

    ASCII on purpose: a stdout that cannot encode '…' would raise mid-run.
    """
    if len(text) <= width:
        return text
    head = (width - 3) // 2
    return text[:head] + "..." + text[len(text) - (width - 3 - head):]


def _status_width(improve: bool, learning: bool) -> int:
    """Width of the longest status label a run in this mode can print."""
    if learning:
        return len("Skipping (already learned)")
    if improve:
        return len(STATUS_KEPT)
    return len(STATUS_SKIPPED)


def _terminal_columns() -> int | None:
    """Current width of the terminal on stdout, or None when stdout is not one.

    Not shutil.get_terminal_size: that prefers $COLUMNS and queries
    sys.__stdout__ rather than sys.stdout.
    """
    try:
        return os.get_terminal_size(sys.stdout.fileno()).columns
    except (OSError, ValueError):
        return None


def progress_formatter(
    documents: list[Path], root: Path, status_width: int
) -> Callable[[str, Path], str]:
    """Return render(message, path) for -v lines: status | folder | file columns.

    message is "<Status>: <name>[ - <error>]"; the folder is path's parent
    relative to root. On a terminal wide enough, each line is fitted to the
    current width (FAILED lines keep their full error); otherwise nothing is
    padded past the status or truncated.
    """
    def folder_of(path: Path) -> str:
        return path.parent.relative_to(root).as_posix()

    longest = max((len(folder_of(p)) for p in documents), default=1)

    def render(message: str, path: Path) -> str:
        status, _, name = message.partition(": ")
        folder = folder_of(path)
        columns = _terminal_columns()
        avail = (columns or 0) - 1 - status_width - 4
        if columns is None or avail < 20:
            return f"{status:<{status_width}}  {folder}  {name}"
        folder_width = min(longest, avail * 3 // 5)
        if status != "FAILED":
            name = _ellipsize(name, avail - folder_width)
        return f"{status:<{status_width}}  {_ellipsize(folder, folder_width):<{folder_width}}  {name}"

    return render


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


def count_outcome(stats: ProcessingStats, success: bool, message: str, file_size: int):
    """Count one process_document result into processing stats, by its status label."""
    status = result_status(message)
    if status == STATUS_IMPROVED:
        stats.improved_files += 1
        stats.processed_files += 1
        stats.processed_bytes += file_size
    elif status == STATUS_KEPT:
        stats.kept_existing += 1
        stats.processed_files += 1
        stats.processed_bytes += file_size
    elif success:
        stats.processed_files += 1
        stats.processed_bytes += file_size
    elif status == STATUS_SKIPPED:
        stats.skipped_files += 1
    else:
        stats.failed_files += 1


def run_simple_parallel(documents: list[Path], root: Path, args, use_ocr: bool, ocr_engine: str, force_ocr: bool, max_workers: int) -> int:
    """Run processing with simple text output using parallel workers."""
    stats = ProcessingStats()
    stats.total_files = len(documents)
    stats.total_bytes = sum(p.stat().st_size for p in documents)
    improve_mode = getattr(args, 'improve', False)
    render = progress_formatter(documents, root, _status_width(improve_mode, learning=False))

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
                print(render(result.message, result.source_path))
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

            count_outcome(stats, success, message, file_size)

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
    root: Path,
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
    learning = bool(learner and learner.enabled)
    render = progress_formatter(documents, root, _status_width(improve_mode, learning))

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
                print(render(f"Skipping (already learned): {doc_path.name}", doc_path))
            stats.skipped_files += 1
            continue

        if args.verbose:
            print(render(f"Processing: {doc_path.name}", doc_path))

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
            print(render(message, doc_path))
            if improve_detail:
                print(f"     {improve_detail}")
        if getattr(args, 'debug', False) and stats.log_messages:
            for msg in stats.log_messages:
                print(f"    [DEBUG] {msg}")
            stats.log_messages.clear()

        count_outcome(stats, success, message, file_size)

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
            print("       Consider: ./doc2txt.py --learn-reset to retrain on this corpus")
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
        "path",
        help="Document file, or directory to search for documents (supports Windows paths in WSL)"
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
        choices=sorted(OCR_FALLBACKS),
        default="surya",
        help="OCR engine (default: surya, falling back to tesseract; auto is the same). "
             "paddle runs only when named: PaddleOCR 3.3 fails on CPU here."
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
        help="Custom path for learning database (default: ~/.doc2txt/learning.db)"
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

    # Watch mode arguments
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch directories for new/modified documents and process them automatically"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        metavar="MINUTES",
        help="Minutes between directory scans in watch mode (default: 30)"
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=10,
        metavar="MINUTES",
        help="Minutes since last file modification before processing (default: 10)"
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
    path = convert_windows_path(args.path)

    try:
        exists = path.exists()
        single_file = exists and path.is_file()
        if exists and not single_file:
            os.scandir(path).close()
    except OSError as e:
        try:
            link = path.is_symlink()
        except OSError:
            link = False
        note = " (symbolic link; target unreadable)" if link else ""
        print(f"Error: cannot read {path}: {e.strerror or e}{note}", file=sys.stderr)
        return 1

    if not exists:
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return 1

    if single_file and path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        print(f"Error: Unsupported file type: {path.suffix or '(none)'}", file=sys.stderr)
        print(f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}", file=sys.stderr)
        return 1

    directory = path.parent if single_file else path

    formats = None
    if args.formats is not None:
        try:
            formats = parse_formats(args.formats)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Watch mode
    if args.watch:
        if single_file:
            print("Error: --watch requires a directory, not a file", file=sys.stderr)
            return 1
        import logging
        from doc2txt_watcher import WatchConfig, FolderWatcher

        log_level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        config = WatchConfig(
            watch_dirs=[directory],
            poll_interval_minutes=args.poll_interval,
            cooldown_minutes=args.cooldown,
            formats=formats or set(SUPPORTED_EXTENSIONS),
            recursive=args.recursive,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            use_ocr=not args.no_ocr,
            ocr_engine=args.ocr_engine,
            force_ocr=getattr(args, 'force_ocr', False),
            verbose=args.verbose,
        )

        watcher = FolderWatcher(config)
        try:
            watcher.run()
        finally:
            watcher.close()
        return 0

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
        use_ocr, ocr_engine, _ = resolve_ocr_engine(args.ocr_engine)
        if not args.quiet:
            if not use_ocr:
                print("Warning: No OCR engine available. OCR disabled. Install tesseract-ocr.", file=sys.stderr)
            elif args.ocr_engine not in ("auto", ocr_engine):
                print(f"Warning: {args.ocr_engine} not available, using {ocr_engine}.", file=sys.stderr)

    # Find documents
    # Determine shuffle: default ON with --learn, unless --no-learn-shuffle
    should_shuffle = False
    if args.learn:
        should_shuffle = not args.no_learn_shuffle  # Default ON with --learn
    if args.learn_shuffle:
        should_shuffle = True  # Explicit --learn-shuffle overrides

    if single_file:
        documents = [path]
    else:
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
                result = run_simple(documents, directory, args, use_ocr, ocr_engine, force_ocr, learner=learner)
        else:
            # Parallel processing (no learner support)
            if args.hud and not args.dry_run:
                result = run_with_hud_parallel(documents, args, use_ocr, ocr_engine, force_ocr, max_workers)
            else:
                result = run_simple_parallel(documents, directory, args, use_ocr, ocr_engine, force_ocr, max_workers)

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
