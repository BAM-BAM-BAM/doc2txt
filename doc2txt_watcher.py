"""Folder watcher for automatic document processing.

Monitors directories for new/modified documents and processes them
using the existing doc2txt pipeline. Designed for low-cost background
operation with cross-filesystem support (WSL2 + Windows drives).

Key design decisions:
- Polling-based (inotify doesn't work on WSL2 /mnt/ paths)
- 30-minute poll interval by default (configurable)
- 10-minute cooldown from last mtime before processing
- Multiple heuristics to avoid processing files being edited
- SQLite tracker to avoid reprocessing unchanged files
"""

import fcntl
import hashlib
import logging
import signal
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from doc2txt_models import SUPPORTED_EXTENSIONS

logger = logging.getLogger("doc2txt.watcher")


@dataclass
class WatchConfig:
    """Configuration for folder watching."""
    watch_dirs: list[Path]
    poll_interval_minutes: int = 30
    cooldown_minutes: int = 10
    formats: set[str] = field(default_factory=lambda: set(SUPPORTED_EXTENSIONS))
    recursive: bool = True
    db_path: Path = field(default_factory=lambda: Path.home() / ".doc2txt" / "watcher.db")
    min_file_size: int = 100  # Skip files smaller than this (likely placeholders)
    overwrite: bool = False
    dry_run: bool = False
    use_ocr: bool = True
    ocr_engine: str = "auto"
    force_ocr: bool = False
    verbose: bool = False


# Lock file patterns created by editors and office suites
EDITOR_LOCK_PATTERNS = [
    ".~lock.*#",        # LibreOffice
    "~$*",              # Microsoft Office (Word, Excel, PowerPoint)
    "*.swp",            # Vim swap
    "*.swo",            # Vim swap overflow
    "*~",               # Emacs backup
    ".*.kate-swp",      # Kate editor
    "*.lck",            # Generic lock files
]

# Temp file patterns from cloud sync tools
CLOUD_SYNC_TEMP_PATTERNS = [
    "*.gstmp",          # Google Drive temp
    "*.tmp",            # Generic temp
    "*.crdownload",     # Chrome download in progress
    "*.part",           # Partial download
    "desktop.ini",      # Windows folder metadata
    "thumbs.db",        # Windows thumbnails
    ".ds_store",        # macOS metadata
]


class FileReadinessChecker:
    """Determine if a file is ready for processing.

    A file is NOT ready if any of these conditions hold:
    1. Modified less than cooldown_minutes ago (still being edited)
    2. Has a sibling editor lock file (open in an editor/office suite)
    3. Cannot acquire a shared file lock (another process has exclusive lock)
    4. Is smaller than min_file_size (likely a cloud placeholder)
    5. Matches a known temp/sync file pattern
    6. Size changed between two checks 1 second apart (actively being written)
    """

    def __init__(self, cooldown_minutes: int = 10, min_file_size: int = 100):
        self.cooldown_minutes = cooldown_minutes
        self.min_file_size = min_file_size

    def is_ready(self, path: Path) -> tuple[bool, str]:
        """Check if file is ready for processing.

        Returns (ready: bool, reason: str).
        """
        if not path.exists():
            return False, "file does not exist"

        if not path.is_file():
            return False, "not a regular file"

        # Check temp/sync file patterns
        name_lower = path.name.lower()
        for pattern in CLOUD_SYNC_TEMP_PATTERNS:
            if self._matches_pattern(name_lower, pattern.lower()):
                return False, f"matches temp pattern: {pattern}"

        # Check file size (placeholder detection)
        try:
            stat = path.stat()
        except OSError as e:
            return False, f"cannot stat: {e}"

        if stat.st_size < self.min_file_size:
            return False, f"too small ({stat.st_size} bytes, min {self.min_file_size})"

        # Check mtime cooldown
        age_seconds = time.time() - stat.st_mtime
        cooldown_seconds = self.cooldown_minutes * 60
        if age_seconds < cooldown_seconds:
            remaining = cooldown_seconds - age_seconds
            return False, f"modified {age_seconds:.0f}s ago (cooldown: {remaining:.0f}s remaining)"

        # Check for editor lock files
        lock_reason = self._check_editor_locks(path)
        if lock_reason:
            return False, lock_reason

        # Try to acquire shared lock (non-blocking)
        lock_reason = self._check_file_lock(path)
        if lock_reason:
            return False, lock_reason

        # Size stability check (catch active writes)
        size_reason = self._check_size_stability(path, stat.st_size)
        if size_reason:
            return False, size_reason

        return True, "ready"

    def _matches_pattern(self, name: str, pattern: str) -> bool:
        """Simple glob-style pattern matching."""
        if pattern.startswith("*."):
            return name.endswith(pattern[1:])
        if pattern.startswith(".") and pattern.endswith("*"):
            return name.startswith(pattern[:-1])
        if pattern.startswith("~$"):
            return name.startswith("~$")
        return name == pattern

    def _check_editor_locks(self, path: Path) -> str | None:
        """Check if sibling editor lock files exist."""
        parent = path.parent
        stem = path.stem
        name = path.name

        # LibreOffice: .~lock.FILENAME#
        lo_lock = parent / f".~lock.{name}#"
        if lo_lock.exists():
            return f"LibreOffice lock file exists: {lo_lock.name}"

        # Microsoft Office: ~$FILENAME.docx
        ms_lock = parent / f"~${name}"
        if ms_lock.exists():
            return f"Office lock file exists: {ms_lock.name}"

        # Also check ~$STEM.docx pattern (Word uses first 6 chars)
        if len(stem) > 6:
            ms_lock2 = parent / f"~${stem[:6]}{path.suffix}"
            if ms_lock2.exists():
                return f"Office lock file exists: {ms_lock2.name}"

        # Vim: .FILENAME.swp
        vim_lock = parent / f".{name}.swp"
        if vim_lock.exists():
            return f"Vim swap file exists: {vim_lock.name}"

        return None

    def _check_file_lock(self, path: Path) -> str | None:
        """Try to acquire a shared lock to detect exclusive locks."""
        try:
            with open(path, "rb") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except BlockingIOError:
            return "file is locked by another process"
        except OSError:
            # flock may not be supported on all filesystems (9P)
            # Don't block processing — the mtime cooldown is the primary guard
            pass
        return None

    def _check_size_stability(self, path: Path, initial_size: int) -> str | None:
        """Check if file size is stable (not actively being written)."""
        time.sleep(0.5)
        try:
            current_size = path.stat().st_size
        except OSError:
            return "file disappeared during stability check"

        if current_size != initial_size:
            return f"size changed during check ({initial_size} -> {current_size})"
        return None


class ProcessedTracker:
    """Track which files have been processed using SQLite.

    A file is considered "already processed" if its path, mtime, and size
    match a previous processing record. If the file has been modified since
    last processing (different mtime or size), it will be reprocessed.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed (
                path TEXT PRIMARY KEY,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                file_hash TEXT,
                processed_at REAL NOT NULL,
                output_path TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_processed_mtime ON processed(mtime);
        """)
        self._conn.commit()

    def needs_processing(self, path: Path) -> bool:
        """Check if file needs processing (new or modified since last run)."""
        try:
            stat = path.stat()
        except OSError:
            return False

        row = self._conn.execute(
            "SELECT mtime, size FROM processed WHERE path = ?",
            (str(path.resolve()),)
        ).fetchone()

        if row is None:
            return True  # Never processed

        # Reprocess if mtime or size changed
        return row["mtime"] != stat.st_mtime or row["size"] != stat.st_size

    def mark_processed(self, path: Path, output_path: Path | None = None):
        """Record that a file has been processed."""
        stat = path.stat()

        # Compute hash for change detection
        file_hash = self._compute_hash(path)

        self._conn.execute("""
            INSERT OR REPLACE INTO processed (path, mtime, size, file_hash, processed_at, output_path)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(path.resolve()),
            stat.st_mtime,
            stat.st_size,
            file_hash,
            time.time(),
            str(output_path) if output_path else None,
        ))
        self._conn.commit()

    def _compute_hash(self, path: Path) -> str:
        """Compute MD5 hash of file content."""
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def get_stats(self) -> dict:
        """Get tracking statistics."""
        row = self._conn.execute("SELECT COUNT(*) as total FROM processed").fetchone()
        return {"total_tracked": row["total"]}

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


class FolderWatcher:
    """Watch folders for new/modified documents and process them.

    Uses polling (compatible with WSL2 /mnt/ paths where inotify
    doesn't work). Processes files only after they've been stable
    for the cooldown period with no editor locks detected.
    """

    def __init__(self, config: WatchConfig):
        self.config = config
        self.checker = FileReadinessChecker(
            cooldown_minutes=config.cooldown_minutes,
            min_file_size=config.min_file_size,
        )
        self.tracker = ProcessedTracker(config.db_path)
        self._running = False

    def scan_once(self) -> list[tuple[Path, str]]:
        """Scan all watched dirs. Returns list of (path, skip_reason|'ready')."""
        results = []

        for watch_dir in self.config.watch_dirs:
            if not watch_dir.exists():
                logger.warning("Watch directory does not exist: %s", watch_dir)
                continue

            # Find all supported documents
            pattern_func = watch_dir.rglob if self.config.recursive else watch_dir.glob
            for path in sorted(pattern_func("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in self.config.formats:
                    continue

                # Skip if already processed and unchanged
                if not self.tracker.needs_processing(path):
                    continue

                # Check readiness
                ready, reason = self.checker.is_ready(path)
                results.append((path, reason))

        return results

    def process_ready_files(self, scan_results: list[tuple[Path, str]]) -> dict:
        """Process all ready files from a scan. Returns summary stats."""
        from doc2txt import process_document

        ready = [(p, r) for p, r in scan_results if r == "ready"]
        skipped = [(p, r) for p, r in scan_results if r != "ready"]

        stats = {"processed": 0, "failed": 0, "skipped": len(skipped)}

        for path, _ in ready:
            try:
                success, message, _ = process_document(
                    path,
                    overwrite=self.config.overwrite,
                    dry_run=self.config.dry_run,
                    use_ocr=self.config.use_ocr,
                    ocr_engine=self.config.ocr_engine,
                    force_ocr=self.config.force_ocr,
                )

                if success:
                    output_path = path.with_suffix(".md")
                    self.tracker.mark_processed(path, output_path)
                    stats["processed"] += 1
                    logger.info("Processed: %s -> %s", path, message)
                else:
                    # "Skipped" by process_document (e.g., .md already exists)
                    # Still mark as processed so we don't retry every cycle
                    self.tracker.mark_processed(path)
                    stats["skipped"] += 1
                    logger.info("Skipped: %s -> %s", path, message)

            except Exception as e:
                stats["failed"] += 1
                logger.error("Failed: %s -> %s", path, e)

        return stats

    def run(self):
        """Main watch loop. Runs until interrupted (Ctrl+C / SIGTERM)."""
        self._running = True

        def _handle_signal(signum, frame):
            logger.info("Received signal %s, stopping...", signum)
            self._running = False

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        dirs_str = ", ".join(str(d) for d in self.config.watch_dirs)
        logger.info(
            "Watching %d directories (poll: %dm, cooldown: %dm): %s",
            len(self.config.watch_dirs),
            self.config.poll_interval_minutes,
            self.config.cooldown_minutes,
            dirs_str,
        )

        cycle = 0
        while self._running:
            cycle += 1
            logger.info("--- Scan cycle %d ---", cycle)

            scan_results = self.scan_once()
            ready_count = sum(1 for _, r in scan_results if r == "ready")
            pending_count = sum(1 for _, r in scan_results if r != "ready")

            if scan_results:
                logger.info(
                    "Found %d files: %d ready, %d pending",
                    len(scan_results), ready_count, pending_count,
                )

                # Log pending reasons (verbose)
                for path, reason in scan_results:
                    if reason != "ready":
                        logger.debug("  Pending: %s (%s)", path.name, reason)

                if ready_count > 0:
                    stats = self.process_ready_files(scan_results)
                    logger.info(
                        "Cycle %d complete: %d processed, %d skipped, %d failed",
                        cycle, stats["processed"], stats["skipped"], stats["failed"],
                    )
            else:
                logger.info("No new or modified files found")

            # Sleep in small increments to allow signal handling
            if self._running:
                sleep_seconds = self.config.poll_interval_minutes * 60
                logger.info("Next scan in %d minutes", self.config.poll_interval_minutes)
                wake_time = time.time() + sleep_seconds
                while self._running and time.time() < wake_time:
                    time.sleep(min(5, wake_time - time.time()))

        logger.info("Watcher stopped")
        self.tracker.close()

    def close(self):
        self.tracker.close()
