"""Retro HUD display for doc2txt processing."""

from __future__ import annotations

import curses
from typing import TYPE_CHECKING

from doc2txt_models import ProcessingStats, __version__

if TYPE_CHECKING:
    from doc2txt_learning import AdaptiveLearner


class RetroHUD:
    """80's style terminal HUD using curses."""

    def __init__(self, stats: ProcessingStats, learner: AdaptiveLearner | None = None):
        self.stats = stats
        self.learner = learner
        self.stdscr = None

    def __enter__(self):
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        curses.curs_set(0)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)   # Title
            curses.init_pair(2, curses.COLOR_CYAN, -1)    # Labels
            curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Values
            curses.init_pair(4, curses.COLOR_RED, -1)     # Errors
            curses.init_pair(5, curses.COLOR_MAGENTA, -1) # Progress bar
        self.stdscr.nodelay(True)
        return self

    def __exit__(self, *args):
        curses.nocbreak()
        curses.echo()
        curses.curs_set(1)
        curses.endwin()
        self.print_final_summary()

    def print_final_summary(self):
        """Print a final summary after exiting curses mode."""
        s = self.stats
        elapsed = s.elapsed()
        mb_processed = s.processed_bytes / (1024 * 1024)
        md_mb = s.md_bytes / (1024 * 1024)
        ratio = (s.md_bytes / s.processed_bytes * 100) if s.processed_bytes > 0 else 0
        files_per_min = (s.processed_files / elapsed * 60) if elapsed > 0 else 0
        mb_per_min = (mb_processed / elapsed * 60) if elapsed > 0 else 0

        print()
        print("═" * 60)
        print("  PDF2TXT - FINAL RESULTS")
        print("═" * 60)
        print(f"  Files:     {s.processed_files:,} processed, {s.skipped_files:,} skipped, {s.failed_files:,} failed")
        if s.improved_files > 0 or s.kept_existing > 0:
            print(f"  Quality:   {s.improved_files:,} improved, {s.kept_existing:,} kept existing")
        print(f"  Pages:     {s.processed_pages:,} total, {s.ocr_pages:,} OCR'd ({s.ocr_chars:,} chars)")
        print(f"  Data:      {mb_processed:.2f} MB in → {md_mb:.2f} MB out ({ratio:.1f}%)")
        print(f"  Time:      {elapsed:.1f}s ({files_per_min:.1f} files/min, {mb_per_min:.2f} MB/min)")
        print("═" * 60)
        print()

    def draw_box(self, y: int, x: int, h: int, w: int, title: str = ""):
        """Draw a retro-style box."""
        # Corners and edges
        self.stdscr.addch(y, x, curses.ACS_ULCORNER)
        self.stdscr.addch(y, x + w - 1, curses.ACS_URCORNER)
        self.stdscr.addch(y + h - 1, x, curses.ACS_LLCORNER)
        self.stdscr.addch(y + h - 1, x + w - 1, curses.ACS_LRCORNER)

        for i in range(1, w - 1):
            self.stdscr.addch(y, x + i, curses.ACS_HLINE)
            self.stdscr.addch(y + h - 1, x + i, curses.ACS_HLINE)

        for i in range(1, h - 1):
            self.stdscr.addch(y + i, x, curses.ACS_VLINE)
            self.stdscr.addch(y + i, x + w - 1, curses.ACS_VLINE)

        if title:
            title_str = f"[ {title} ]"
            self.stdscr.addstr(y, x + 2, title_str, curses.color_pair(1) | curses.A_BOLD)

    def draw_progress_bar(self, y: int, x: int, width: int, progress: float, label: str = ""):
        """Draw a retro progress bar."""
        bar_width = width - len(label) - 10
        filled = int(bar_width * progress)
        empty = bar_width - filled

        self.stdscr.addstr(y, x, label, curses.color_pair(2))
        self.stdscr.addstr(y, x + len(label), " [", curses.color_pair(5))
        self.stdscr.addstr(y, x + len(label) + 2, "█" * filled, curses.color_pair(5) | curses.A_BOLD)
        self.stdscr.addstr(y, x + len(label) + 2 + filled, "░" * empty, curses.color_pair(5))
        self.stdscr.addstr(y, x + len(label) + 2 + bar_width, "]", curses.color_pair(5))
        pct_str = f" {progress * 100:5.1f}%"
        self.stdscr.addstr(y, x + len(label) + 3 + bar_width, pct_str, curses.color_pair(3))

    def draw_stat(self, y: int, x: int, label: str, value: str):
        """Draw a labeled stat."""
        self.stdscr.addstr(y, x, label, curses.color_pair(2))
        self.stdscr.addstr(y, x + len(label), value, curses.color_pair(3) | curses.A_BOLD)

    def truncate_path(self, path: str, max_len: int) -> str:
        """Truncate path to fit display."""
        if len(path) <= max_len:
            return path
        return "..." + path[-(max_len - 3):]

    def refresh(self):
        """Refresh the HUD display."""
        try:
            self.stdscr.erase()  # erase() doesn't flash like clear()
            height, width = self.stdscr.getmaxyx()
            width = min(width, 100)  # Cap width

            # Title banner (all lines 65 chars)
            banner = [
                "╔═══════════════════════════════════════════════════════════════╗",
                "║   ██████╗ ██████╗ ███████╗██████╗ ████████╗██╗  ██╗████████╗  ║",
                "║   ██╔══██╗██╔══██╗██╔════╝╚════██╗╚══██╔══╝╚██╗██╔╝╚══██╔══╝  ║",
                "║   ██████╔╝██║  ██║█████╗   █████╔╝   ██║    ╚███╔╝    ██║     ║",
                "║   ██╔═══╝ ██║  ██║██╔══╝  ██╔═══╝    ██║    ██╔██╗    ██║     ║",
                "║   ██║     ██████╔╝██║     ███████╗   ██║   ██╔╝ ██╗   ██║     ║",
                "║   ╚═╝     ╚═════╝ ╚═╝     ╚══════╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝     ║",
                "╚═══════════════════════════════════════════════════════════════╝",
            ]

            # Simpler banner if terminal is narrow
            if width < 70:
                banner = [
                    "┌─────────────────────────┐",
                    "│     P D F 2 T X T       │",
                    "│      v" + __version__.center(17) + "│",
                    "└─────────────────────────┘",
                ]

            for i, line in enumerate(banner):
                if i < height - 1:
                    self.stdscr.addstr(i, 0, line[:width-1], curses.color_pair(1) | curses.A_BOLD)

            y_offset = len(banner) + 1

            # Main stats box
            box_height = 13
            if y_offset + box_height < height:
                self.draw_box(y_offset, 0, box_height, min(width - 1, 78), "PROCESSING STATUS")

                # Current file
                y = y_offset + 1
                current = self.truncate_path(self.stats.current_file, 55)
                self.draw_stat(y, 2, "FILE: ", current if current else "(idle)")

                # File progress
                y += 2
                file_progress = self.stats.processed_files / max(self.stats.total_files, 1)
                self.draw_progress_bar(y, 2, 74, file_progress, "FILES  ")

                # Page progress (current file)
                y += 1
                page_progress = self.stats.current_page / max(self.stats.current_file_pages, 1)
                self.draw_progress_bar(y, 2, 74, page_progress, "PAGES  ")

                # Stats row 1
                y += 2
                elapsed = self.stats.elapsed()
                self.draw_stat(y, 2, "ELAPSED: ", f"{elapsed:>8.1f}s")
                self.draw_stat(y, 24, "FILES: ", f"{self.stats.processed_files:,}/{self.stats.total_files:,}")
                self.draw_stat(y, 46, "RATE: ", f"{self.stats.files_per_min():5.1f}/min")

                # Stats row 2
                y += 1
                mb_processed = self.stats.processed_bytes / (1024 * 1024)
                mb_total = self.stats.total_bytes / (1024 * 1024)
                self.draw_stat(y, 2, "INPUT:  ", f"{mb_processed:>7.2f}/{mb_total:.2f} MB")
                self.draw_stat(y, 36, "THROUGHPUT: ", f"{self.stats.mb_per_min():6.2f} MB/min")

                # Stats row 3 - Output and compression
                y += 1
                md_mb = self.stats.md_bytes / (1024 * 1024)
                if self.stats.processed_bytes > 0:
                    ratio = (self.stats.md_bytes / self.stats.processed_bytes) * 100
                    self.draw_stat(y, 2, "MD OUT: ", f"{md_mb:>7.2f} MB")
                    self.draw_stat(y, 28, "RATIO: ", f"{ratio:5.1f}% of input")
                else:
                    self.draw_stat(y, 2, "MD OUT: ", f"{md_mb:>7.2f} MB")

                # Stats row 4 - OCR stats
                y += 2
                self.draw_stat(y, 2, "OCR PAGES: ", f"{self.stats.ocr_pages:>6,}")
                self.draw_stat(y, 24, "OCR CHARS: ", f"{self.stats.ocr_chars:>12,}")
                status = self.stats.current_status[:25] if self.stats.current_status else "Ready"
                self.draw_stat(y, 50, "STATUS: ", status)

            # Results box (taller if learning enabled)
            y_offset += box_height + 1
            has_learning = self.learner and self.learner.enabled
            results_height = 10 if has_learning else 6
            if y_offset + results_height < height:
                self.draw_box(y_offset, 0, results_height, min(width - 1, 78), "RESULTS")
                y = y_offset + 1
                self.draw_stat(y, 2, "PROCESSED: ", f"{self.stats.processed_files:4d}")
                self.draw_stat(y, 22, "SKIPPED: ", f"{self.stats.skipped_files:4d}")
                self.draw_stat(y, 42, "FAILED: ", f"{self.stats.failed_files:4d}")
                if self.stats.failed_files > 0:
                    self.stdscr.addstr(y, 50, f"{self.stats.failed_files:4d}", curses.color_pair(4) | curses.A_BOLD)

                y += 1
                if self.stats.improved_files > 0 or self.stats.kept_existing > 0:
                    self.draw_stat(y, 2, "IMPROVED: ", f"{self.stats.improved_files:4d}")
                    self.draw_stat(y, 22, "KEPT: ", f"{self.stats.kept_existing:4d}")

                y += 1
                total_pages = self.stats.processed_pages
                self.draw_stat(y, 2, "TOTAL PAGES: ", f"{total_pages:,}")

                # Learning stats
                if has_learning:
                    y += 1
                    self.stdscr.addstr(y, 2, "─" * 30, curses.color_pair(2))
                    self.stdscr.addstr(y, 34, " LEARNING ", curses.color_pair(1) | curses.A_BOLD)
                    self.stdscr.addstr(y, 44, "─" * 30, curses.color_pair(2))

                    y += 1
                    ls = self.learner._stats
                    exp_rate = self.learner._exploration_rate() * 100
                    # Use comma formatting and wider fields to prevent overflow
                    self.draw_stat(y, 2, "IMAGES: ", f"{ls['images_seen']:>7,}")
                    self.draw_stat(y, 20, "OCR'd: ", f"{ls['images_ocrd']:>6,}")
                    self.draw_stat(y, 36, "SKIP: ", f"{ls['images_skipped']:>6,}")
                    self.draw_stat(y, 52, "EXPLORE: ", f"{exp_rate:5.1f}%")

                    # OCR efficiency: what % of OCRs found useful text
                    y += 1
                    total_ocrd = ls['ocr_useful'] + ls['ocr_empty']
                    if total_ocrd > 0:
                        ocr_eff = ls['ocr_useful'] / total_ocrd * 100
                        self.draw_stat(y, 2, "OCR EFF: ", f"{ocr_eff:5.1f}%")

                    # Second row: exploration accuracy
                    y += 1
                    exp_total = ls['exploration_useful'] + ls['exploration_empty']
                    if exp_total > 0:
                        # Miss rate: exploration found useful text we would've skipped
                        miss_rate = ls['exploration_useful'] / exp_total * 100
                        self.draw_stat(y, 2, "EXPLORE: ", f"{exp_total:>6,}")
                        self.draw_stat(y, 20, "WOULD MISS: ", f"{ls['exploration_useful']:>5,}")
                        # Color code: green if low miss rate, red if high
                        miss_color = curses.color_pair(4) if miss_rate > 20 else curses.color_pair(1)
                        self.stdscr.addstr(y, 48, f"MISS RATE: {miss_rate:5.1f}%", miss_color | curses.A_BOLD)

            # Log box
            y_offset += results_height + 1
            log_height = max(5, height - y_offset - 1)
            if y_offset + log_height < height and log_height > 2:
                self.draw_box(y_offset, 0, log_height, min(width - 1, 78), "ACTIVITY LOG")

                # Show recent log messages
                visible_logs = log_height - 2
                recent_logs = self.stats.log_messages[-visible_logs:]
                for i, msg in enumerate(recent_logs):
                    if y_offset + 1 + i < height - 1:
                        truncated = msg[:74] if len(msg) > 74 else msg
                        color = curses.color_pair(4) if "FAIL" in msg or "ERROR" in msg else curses.color_pair(2)
                        self.stdscr.addstr(y_offset + 1 + i, 2, truncated, color)

            self.stdscr.refresh()
        except curses.error:
            pass  # Ignore curses errors from terminal resize


