"""FGT-category tests for doc2txt.

New tests organized by FGT test categories:
  INV-*  : Domain invariants that must always hold
  QUAL-* : Output quality verification
  BOUND-*: Edge case / boundary handling
  INT-*  : End-to-end CLI runs
  PRO-*  : Proactive bug-class detection
"""

import errno
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from doc2txt import progress_formatter
from doc2txt_extractors import create_markdown, extract_text, find_documents, iter_documents
from doc2txt_models import SUPPORTED_EXTENSIONS, ImageFeature
from doc2txt_quality import TextQualityScorer


def _walk(root: Path, recursive: bool = True) -> tuple[list[Path], list[Path]]:
    skipped = []
    found = list(iter_documents(root, recursive, {".pdf"}, lambda p, e: skipped.append(p)))
    return sorted(found), skipped


def _progress_render(monkeypatch, columns, status_width=16, folders=("a",)):
    """progress_formatter over root/<folder>/x.pdf documents with a fixed terminal width."""
    import doc2txt
    monkeypatch.setattr(doc2txt, "_terminal_columns", lambda: columns)
    root = Path("/root")
    return root, progress_formatter([root / f / "x.pdf" for f in folders], root, status_width)


def _fail_stat(monkeypatch, bad: Path, err: int, lstat_too: bool = False) -> None:
    """Make os.stat raise err for bad: when following links, or always if lstat_too."""
    real_stat = os.stat

    def fake_stat(path, *, dir_fd=None, follow_symlinks=True):
        if os.fspath(path) == str(bad) and (follow_symlinks or lstat_too):
            raise OSError(err, os.strerror(err), str(bad))
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "stat", fake_stat)


def _scan_pdf(path: Path, sideways: bool = False, text_layer: bool = False) -> Path:
    """A one-page PDF whose page is an image of the words INVOICE 12345, as a scanner makes it.

    sideways stores the scan rotated and sets /Rotate 90 so it displays upright.
    text_layer adds the invisible OCR text a scanner lays over the image.
    Text drawn with PIL's default font OCRs as 123-46, hence pymupdf text rasterized.
    """
    import pymupdf

    text = "INVOICE 12345"
    if sideways:
        size, origin, rotate = (120, 400), (75, 380), 90
    else:
        size, origin, rotate = (400, 120), (20, 75), 0
    src = pymupdf.open()
    scan = src.new_page(width=size[0], height=size[1])
    scan.insert_text(origin, text, fontsize=40, rotate=rotate)
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=400)
    page.insert_image(scan.rect, pixmap=scan.get_pixmap(dpi=150))
    if text_layer:
        page.insert_text(origin, text, fontsize=40, rotate=rotate, render_mode=3)
    if sideways:
        page.set_rotation(90)
    doc.save(path)
    return path


class TestInvariants:
    """INV-* tests: domain rules that must always hold."""

    def test_inv_001_all_extensions_have_handlers(self, tmp_path):
        """Every extension in SUPPORTED_EXTENSIONS must have a handler in extract_text().

        If this fails, a format was added to SUPPORTED_EXTENSIONS without
        adding a corresponding extraction handler.
        """
        for ext in SUPPORTED_EXTENSIONS:
            path = tmp_path / f"test{ext}"
            path.write_bytes(b"fake content")
            try:
                extract_text(path)
            except ValueError as e:
                if "Unsupported format" in str(e):
                    pytest.fail(
                        f"Extension '{ext}' is in SUPPORTED_EXTENSIONS "
                        f"but has no handler in extract_text()"
                    )
            except Exception:
                # Other errors (e.g., invalid file content, missing LibreOffice)
                # are fine -- the handler exists, it just can't process fake data
                pass

    def test_inv_002_quality_score_range(self):
        """QualityMetrics.total_score must be in [0.0, 1.0]."""
        scorer = TextQualityScorer()
        test_inputs = [
            "",
            "   ",
            "hello",
            "The quick brown fox jumps over the lazy dog.",
            "x" * 10000,
            "abc " * 500,
            "!@#$%^&*()_+" * 50,
        ]
        for text in test_inputs:
            metrics = scorer.score(text)
            assert 0.0 <= metrics.total_score <= 1.0, (
                f"Quality score {metrics.total_score} out of range for: {text[:50]!r}"
            )

    def test_inv_003_feature_vector_dimension(self):
        """ImageFeature.to_vector() must return exactly 14 elements."""
        feature = ImageFeature(
            width=500, height=300, area=150000, aspect_ratio=1.67,
            page_y_center=0.5, region="body",
            surrounding_text_density=50.0, has_nearby_caption=True,
            brightness_mean=128.0, brightness_std=40.0,
            is_mostly_white=False, has_contrast=True,
        )
        vector = feature.to_vector()
        assert len(vector) == 14, (
            f"Feature vector has {len(vector)} elements, expected 14"
        )

    def test_inv_004_output_file_naming(self, tmp_path):
        """Output .md file must have the same stem as input document."""
        import docx
        doc = docx.Document()
        doc.add_paragraph("Test content")
        path = tmp_path / "my_document.docx"
        doc.save(str(path))

        sections = extract_text(path)
        md_content = create_markdown(path, sections)
        # The markdown header should reference the original file stem
        assert "my_document" in md_content

    def test_inv_005_extract_text_returns_nonempty_list(self, tmp_path):
        """extract_text() must return at least one section for any supported format."""
        import docx
        doc = docx.Document()
        doc.add_paragraph("Content")
        path = tmp_path / "test.docx"
        doc.save(str(path))

        result = extract_text(path)
        assert isinstance(result, list)
        assert len(result) >= 1


class TestProgressInvariants:
    """INV-* tests for -v progress lines (status | folder | file)."""

    LONG_FOLDER = "Clients/" + "/".join(["Acme Corp Holdings"] * 10) + "/2023"
    LONG_NAME = ("Statement of account " * 7)[:146] + ".pdf"

    def test_inv_006_progress_line_fits_terminal(self, monkeypatch):
        """Every non-FAILED line fits columns-1 and starts its folder at status_width+2."""
        assert len(self.LONG_FOLDER) > 200 and len(self.LONG_NAME) == 150
        folders = ["a", "b/c", self.LONG_FOLDER]
        for status_width in (16, 21, 26):
            for columns in range(status_width + 25, 201, 7):
                root, render = _progress_render(monkeypatch, columns, status_width, folders)
                for folder in folders:
                    for message in (f"Created: {self.LONG_NAME}", "Skipped (exists): x.pdf"):
                        line = render(message, root / folder / "x.pdf")
                        assert len(line) <= columns - 1, (status_width, columns, line)
                        assert line[status_width:status_width + 2] == "  "
                        assert line[status_width + 2] != " "

    def test_inv_007_progress_narrow_or_unknown_untruncated(self, monkeypatch):
        """No terminal, a 0-width report, or a too-narrow terminal prints the full folder and name."""
        for status_width in (16, 26):
            for columns in (None, 0, status_width + 24):
                root, render = _progress_render(monkeypatch, columns, status_width, [self.LONG_FOLDER])
                line = render(f"Created: {self.LONG_NAME}", root / self.LONG_FOLDER / "x.pdf")
                assert line == f"{'Created':<{status_width}}  {self.LONG_FOLDER}  {self.LONG_NAME}"


class TestOutputQuality:
    """QUAL-* tests: verify output values are correct, not just computed."""

    def test_qual_001_docx_extraction_produces_readable_text(self, tmp_path):
        """Extraction of known DOCX produces expected readable text.

        This is an output quality test -- we verify the actual text a user
        would see, not just that the pipeline ran without errors.
        """
        import docx
        doc = docx.Document()
        doc.add_heading("Project Report", level=1)
        doc.add_paragraph(
            "The quarterly results show a 15% increase in revenue. "
            "This growth was driven by expansion into new markets."
        )
        doc.add_heading("Conclusion", level=2)
        doc.add_paragraph("The outlook for next quarter remains positive.")
        path = tmp_path / "report.docx"
        doc.save(str(path))

        sections = extract_text(path)
        text = "\n".join(sections)

        # Verify key content is present and readable
        assert "Project Report" in text
        assert "15% increase" in text
        assert "Conclusion" in text
        assert "outlook" in text

        # Verify markdown formatting
        assert "# Project Report" in text
        assert "## Conclusion" in text

        # Verify quality scoring would accept this
        scorer = TextQualityScorer()
        metrics = scorer.score(text)
        assert metrics.total_score > 0.3, (
            f"Extracted text scored {metrics.total_score}, expected readable text"
        )
        assert metrics.word_count > 10


    def test_qual_002_progress_columns(self, monkeypatch):
        """Root files show '.', FAILED keeps its error, and ellipsis keeps both ends."""
        root, render = _progress_render(monkeypatch, None, folders=[".", "a"])
        assert render("Created: x.md", root / "x.pdf") == f"{'Created':<16}  .  x.md"

        error = "Cannot open broken document: " + "x" * 200
        root, render = _progress_render(monkeypatch, 80, folders=["a"])
        assert render(f"FAILED: x.pdf - {error}", root / "a" / "x.pdf").endswith(error)

        root, render = _progress_render(monkeypatch, 80, folders=["Taxes/2023/Federal/Supporting Documents/Scans"])
        line = render("Created: " + "q" * 60 + ".md", root / "Taxes/2023/Federal/Supporting Documents/Scans" / "x.pdf")
        folder_col, name_col = line[18:].split("  ", 1)
        assert folder_col.startswith("Taxes/2023/F") and folder_col.endswith("Scans") and "..." in folder_col
        assert name_col.rstrip().endswith(".md") and "..." in name_col
        assert line.isascii()

    def test_qual_003_learn_skip_line_uses_learn_status_width(self, tmp_path, capsys):
        """Learning runs pad status to 26 and print the skip line as status | folder | name."""
        from argparse import Namespace
        from types import SimpleNamespace
        from doc2txt import run_simple

        import docx

        learned, fresh = tmp_path / "a" / "x.pdf", tmp_path / "b" / "y.docx"
        learned.parent.mkdir()
        learned.touch()
        fresh.parent.mkdir()
        docx.Document().save(str(fresh))
        learner = SimpleNamespace(enabled=True, is_file_processed=lambda p: p == learned, _stats={"images_seen": 0})
        args = Namespace(verbose=True, quiet=False, dry_run=False, overwrite=False, improve=False, debug=False)

        run_simple([learned, fresh], tmp_path, args, use_ocr=False, ocr_engine="paddle", force_ocr=False, learner=learner)
        lines = capsys.readouterr().out.splitlines()
        assert f"{'Skipping (already learned)':<26}  a  x.pdf" in lines
        assert f"{'Processing':<26}  b  y.docx" in lines


    @pytest.mark.skipif(shutil.which("tesseract") is None, reason="needs the tesseract binary")
    def test_qual_004_scanned_pdf_text_reaches_markdown(self, tmp_path):
        """BUG-010: text in a page image reaches the .md exactly once, upright or on /Rotate 90.

        Without a text layer the words come from OCR; with one, OCR of the same words is
        dropped as a duplicate.
        """
        from doc2txt_extractors import process_document
        from doc2txt_quality import strip_markdown_metadata

        for sideways in (False, True):
            for text_layer in (False, True):
                pdf = _scan_pdf(tmp_path / f"scan_{sideways}_{text_layer}.pdf", sideways, text_layer)
                success, message, _ = process_document(pdf, overwrite=False, dry_run=False, ocr_engine="tesseract")
                assert (success, message) == (True, f"Created: {pdf.stem}.md")
                body = strip_markdown_metadata(pdf.with_suffix(".md").read_text())
                assert body.count("12345") == 1, (sideways, text_layer, body)


class TestBoundary:
    """BOUND-* tests: edge case handling."""

    def test_bound_001_extract_text_empty_docx(self, tmp_path):
        """Empty DOCX should not crash, should return list with empty string."""
        import docx
        doc = docx.Document()
        path = tmp_path / "empty.docx"
        doc.save(str(path))

        result = extract_text(path)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_bound_002_unsupported_format_raises(self, tmp_path):
        """Unsupported file extension raises ValueError, not silent failure."""
        path = tmp_path / "test.xyz"
        path.touch()
        with pytest.raises(ValueError, match="Unsupported format"):
            extract_text(path)

    def test_bound_005_cli_single_file_processes_only_that_file(self, tmp_path, monkeypatch):
        """A file path as the positional argument processes that file alone, not its siblings."""
        import docx
        from doc2txt import main

        for name in ("target.docx", "sibling.docx"):
            doc = docx.Document()
            doc.add_paragraph("Hello from " + name)
            doc.save(str(tmp_path / name))

        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-q", "-j", "1", "--no-ocr", str(tmp_path / "target.docx")])
        assert main() == 0
        assert (tmp_path / "target.md").exists()
        assert not (tmp_path / "sibling.md").exists()

    def test_bound_006_cli_single_file_rejects_unsupported_and_watch(self, tmp_path, monkeypatch, capsys):
        """A file path with an unsupported extension, or combined with --watch, exits 1 with a message."""
        from doc2txt import main

        bad = tmp_path / "notes.xyz"
        bad.touch()
        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-q", str(bad)])
        assert main() == 1
        assert "Unsupported file type" in capsys.readouterr().err

        good = tmp_path / "a.docx"
        good.touch()
        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-q", "--watch", str(good)])
        assert main() == 1
        assert "--watch requires a directory" in capsys.readouterr().err

    def test_bound_003_quality_scorer_handles_extremes(self):
        """Quality scorer handles extreme inputs without crash."""
        scorer = TextQualityScorer()

        # Very long input
        metrics = scorer.score("word " * 50000)
        assert 0.0 <= metrics.total_score <= 1.0

        # Single character
        metrics = scorer.score("a")
        assert 0.0 <= metrics.total_score <= 1.0

        # Only punctuation
        metrics = scorer.score("!!! ??? ... ,,, ;;; :::")
        assert 0.0 <= metrics.total_score <= 1.0

    def test_bound_004_image_feature_edge_values(self):
        """ImageFeature handles edge values without crash."""
        # Minimum values
        feature = ImageFeature(
            width=1, height=1, area=1, aspect_ratio=1.0,
            page_y_center=0.0, region="header",
            surrounding_text_density=0.0, has_nearby_caption=False,
            brightness_mean=0.0, brightness_std=0.0,
            is_mostly_white=True, has_contrast=False,
        )
        vector = feature.to_vector()
        assert len(vector) == 14
        assert all(isinstance(v, float) for v in vector)


    def test_bound_007_recursion_follows_symlinked_subdir(self, tmp_path):
        """BUG-005: a symlinked subdirectory is descended with -r, not without."""
        real, other = tmp_path / "real", tmp_path / "other"
        real.mkdir()
        other.mkdir()
        (other / "linked.pdf").touch()
        (real / "sub_link").symlink_to(other, target_is_directory=True)

        assert find_documents(real, recursive=True, quiet=True) == [real / "sub_link" / "linked.pdf"]
        assert find_documents(real, recursive=False, quiet=True) == []

    def test_bound_008_symlink_cycle_terminates_each_file_once(self, tmp_path):
        """BUG-005: sub/loop -> .. ends the walk; each file is found once, from a real or linked root."""
        real = tmp_path / "real"
        sub = real / "sub"
        sub.mkdir(parents=True)
        (real / "top.pdf").touch()
        (sub / "deep.pdf").touch()
        (sub / "loop").symlink_to("..", target_is_directory=True)
        root_link = tmp_path / "root_link"
        root_link.symlink_to(real, target_is_directory=True)

        for root in (real, root_link):
            found = find_documents(root, recursive=True, quiet=True)
            assert sorted(p.name for p in found) == ["deep.pdf", "top.pdf"]

    def test_bound_009_dangling_link_reported_and_skipped(self, tmp_path):
        """BUG-005: a dangling link goes to on_skip; the rest of the walk continues."""
        (tmp_path / "ok.pdf").touch()
        (tmp_path / "gone.pdf").symlink_to(tmp_path / "missing.pdf")

        found, skipped = _walk(tmp_path)
        assert found == [tmp_path / "ok.pdf"]
        assert skipped == [tmp_path / "gone.pdf"]

    def test_bound_010_unreadable_link_target_reported(self, tmp_path, monkeypatch):
        """BUG-005: EIO following a link (WSL junction to an unmapped volume) goes to on_skip."""
        (tmp_path / "ok.pdf").touch()
        target = tmp_path / "target"
        target.mkdir()
        (target / "hidden.pdf").touch()
        vault = tmp_path / "vault"
        vault.symlink_to(target, target_is_directory=True)
        _fail_stat(monkeypatch, vault, errno.EIO)

        found, skipped = _walk(tmp_path)
        assert tmp_path / "ok.pdf" in found
        assert skipped == [vault]

    def test_bound_011_unlistable_subdir_reported_siblings_kept(self, tmp_path, monkeypatch):
        """BUG-005: scandir EIO on one subdir goes to on_skip; sibling files are still returned."""
        (tmp_path / "ok.pdf").touch()
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "hidden.pdf").touch()
        real_scandir = os.scandir

        def fake_scandir(path="."):
            if os.fspath(path) == str(sub):
                raise OSError(errno.EIO, "Input/output error", str(sub))
            return real_scandir(path)

        monkeypatch.setattr(os, "scandir", fake_scandir)

        found, skipped = _walk(tmp_path)
        assert found == [tmp_path / "ok.pdf"]
        assert skipped == [sub]

    def test_bound_012_cli_unreadable_link_exits_cleanly(self, tmp_path, monkeypatch, capsys):
        """BUG-005: a positional link whose target raises EIO exits 1 with a message, not a traceback."""
        from doc2txt import main

        target = tmp_path / "target"
        target.mkdir()
        vault = tmp_path / "Personal Vault"
        vault.symlink_to(target, target_is_directory=True)
        _fail_stat(monkeypatch, vault, errno.EIO)

        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-q", "-r", str(vault)])
        assert main() == 1
        err = capsys.readouterr().err
        assert str(vault) in err
        assert "target unreadable" in err

    def test_bound_013_cli_dead_mount_exits_cleanly(self, tmp_path, monkeypatch, capsys):
        """BUG-005: ENODEV on both stat and lstat (unmounted drive) exits 1 with a message."""
        from doc2txt import main

        dead = tmp_path / "dead_mount"
        _fail_stat(monkeypatch, dead, errno.ENODEV, lstat_too=True)

        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-q", "-r", str(dead)])
        assert main() == 1
        err = capsys.readouterr().err
        assert f"cannot read {dead}" in err
        assert "target unreadable" not in err

    def test_bound_014_cli_unreadable_file_in_tree_skipped(self, tmp_path, monkeypatch, capsys):
        """BUG-005: EIO on one regular document (stalled cloud file) skips it; -r still exits 0."""
        from doc2txt import main

        (tmp_path / "ok.docx").touch()
        stalled = tmp_path / "stalled.pdf"
        stalled.touch()
        _fail_stat(monkeypatch, stalled, errno.EIO)

        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-n", "--no-ocr", "-j", "1", "-r", str(tmp_path)])
        assert main() == 0
        assert f"Warning: skipping {stalled}" in capsys.readouterr().err

    def test_bound_015_cli_unlistable_dir_exits_1(self, tmp_path, monkeypatch, capsys):
        """BUG-005: a positional directory that cannot be listed exits 1, even with -q."""
        from doc2txt import main

        real_scandir = os.scandir

        def fake_scandir(path="."):
            if os.fspath(path) == str(tmp_path):
                raise OSError(errno.EACCES, "Permission denied", str(tmp_path))
            return real_scandir(path)

        monkeypatch.setattr(os, "scandir", fake_scandir)
        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-q", "-r", str(tmp_path)])
        assert main() == 1
        assert f"cannot read {tmp_path}: Permission denied" in capsys.readouterr().err

    def test_bound_016_status_words_in_names_counted_by_status(self, tmp_path, monkeypatch, capsys):
        """BUG-006: a filename containing a status word does not change how its result is counted.

        Sequential and parallel runs must print the same summary and both exit 1.
        """
        import docx
        from doc2txt import main

        summaries = {
            (): "Summary: 1 processed, 0 skipped, 1 failed",
            ("--improve",): "Summary: 1 processed, 0 improved, 0 kept existing, 1 failed",
        }
        for extra, summary in summaries.items():
            for jobs in ("1", "2"):
                root = tmp_path / f"{'-'.join(extra) or 'plain'}-j{jobs}"
                root.mkdir()
                (root / "Skipped items.pdf").write_bytes(b"not a pdf " * 20)
                docx.Document().save(str(root / "Kept receipts.docx"))
                monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-r", "--no-ocr", "-j", jobs, *extra, str(root)])
                assert main() == 1, (extra, jobs)
                assert summary in capsys.readouterr().out.splitlines(), (extra, jobs)

    def test_bound_017_formats_same_in_all_entrypoints(self, tmp_path, monkeypatch):
        """BUG-008: batch mode, --watch and the watcher CLI parse and check --formats alike."""
        import doc2txt
        import doc2txt_watcher

        batch, watch = [], []

        def fake_find(directory, **kwargs):
            batch.append(kwargs["formats"])
            return []

        class StubWatcher:
            def __init__(self, config):
                watch.append(config.formats)

            def run(self):
                pass

            def scan_once(self):
                return []

            def close(self):
                pass

        monkeypatch.setattr(doc2txt, "find_documents", fake_find)
        monkeypatch.setattr(doc2txt_watcher, "FolderWatcher", StubWatcher)
        watcher_cli = ["--watch-dir", str(tmp_path), "--once", "--db-path", str(tmp_path / "w.db")]

        for mode in ([], ["--watch"]):
            monkeypatch.setattr(sys, "argv", ["doc2txt.py", *mode, "--no-ocr", "--formats", "PDF, .Docx,", str(tmp_path)])
            assert doc2txt.main() == 0, mode
        doc2txt_watcher.main([*watcher_cli, "--formats", "PDF, .Docx,"])
        assert batch + watch == [{".pdf", ".docx"}] * 3

        for bad in ("exe", ",", ""):
            for mode in ([], ["--watch"]):
                monkeypatch.setattr(sys, "argv", ["doc2txt.py", *mode, "--no-ocr", "--formats", bad, str(tmp_path)])
                assert doc2txt.main() == 1, (bad, mode)
            with pytest.raises(SystemExit):
                doc2txt_watcher.main([*watcher_cli, "--formats", bad])

    def test_bound_019_office_owner_files_not_discovered(self, tmp_path, monkeypatch, capsys):
        """BUG-009: ~$ Word owner (lock) files are not documents; -r skips them and exits 0."""
        import docx
        from doc2txt import main

        docx.Document().save(str(tmp_path / "report.docx"))
        (tmp_path / "~$report.docx").write_bytes(b"\x0bowner" + b"\0" * 155)
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "~$old.doc").write_bytes(b"\0" * 162)

        found = list(iter_documents(tmp_path, True, SUPPORTED_EXTENSIONS, lambda p, e: None))
        assert found == [tmp_path / "report.docx"]

        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-r", "--no-ocr", "-j", "1", str(tmp_path)])
        assert main() == 0
        assert "Summary: 1 processed, 0 skipped, 0 failed" in capsys.readouterr().out.splitlines()

    def test_bound_018_libreoffice_check_needs_writer(self, monkeypatch):
        """A Calc-only LibreOffice install has `libreoffice` but cannot load .doc/.rtf/.odt."""
        import shutil
        from doc2txt_extractors import check_libreoffice_available

        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/libreoffice" if name == "libreoffice" else None)
        assert check_libreoffice_available() is False


    def test_bound_020_ocr_error_fails_document(self, tmp_path, monkeypatch):
        """BUG-010: an OCR error fails the document instead of leaving a .md without the image's text."""
        import doc2txt_ocr
        from doc2txt_extractors import process_document, process_document_worker

        def broken_ocr(*args, **kwargs):
            raise RuntimeError("ocr broke")

        monkeypatch.setattr(doc2txt_ocr, "check_tesseract_available", lambda: True)
        monkeypatch.setattr(doc2txt_ocr, "ocr_image_region", broken_ocr)
        pdf = _scan_pdf(tmp_path / "scan.pdf")

        success, message, _ = process_document(pdf, overwrite=False, dry_run=False, ocr_engine="tesseract")
        assert (success, message) == (False, "FAILED: scan.pdf - ocr broke")
        assert not pdf.with_suffix(".md").exists()
        assert process_document_worker(pdf, False, False, True, "tesseract", False, False).was_failed

    def test_bound_021_zero_area_image_skipped(self, tmp_path, monkeypatch):
        """BUG-010: an image off the page, or a sliver along its edge, is skipped, not an error.

        Both render to a pixmap with a zero side, and tobytes() raises on that.
        """
        import doc2txt_ocr
        import pymupdf
        from doc2txt_extractors import process_document

        monkeypatch.setattr(doc2txt_ocr, "check_tesseract_available", lambda: True)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200), False)
        pix.clear_with(0)
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=400)
        page.insert_image(pymupdf.Rect(500, 500, 600, 600), pixmap=pix)
        page.insert_image(pymupdf.Rect(0, 400 - 0.000122, 400, 500), pixmap=pix)
        pdf = tmp_path / "edge.pdf"
        doc.save(pdf)

        assert process_document(pdf, overwrite=False, dry_run=False, ocr_engine="tesseract")[:2] == (True, "Created: edge.md")


class TestContract:
    """CONTRACT-* tests: modules that share a definition agree on it."""

    def test_contract_ocr_engine_resolution(self, tmp_path, monkeypatch):
        """BUG-010: one engine table decides the OCR engine for the CLI and the watcher."""
        import doc2txt
        import doc2txt_ocr
        import doc2txt_watcher
        import pymupdf

        for module in (doc2txt_ocr, doc2txt):
            monkeypatch.setattr(module, "check_surya_available", lambda: False, raising=False)
            monkeypatch.setattr(module, "check_paddleocr_available", lambda: True, raising=False)
            monkeypatch.setattr(module, "check_tesseract_available", lambda: True, raising=False)
        engines = []
        monkeypatch.setattr(doc2txt, "run_simple", lambda docs, root, args, use_ocr, ocr_engine, *a, **k: engines.append(ocr_engine) or 0)
        pdf = tmp_path / "x.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(pdf)

        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-q", "-j", "1", str(pdf)])
        assert doc2txt.main() == 0
        assert engines == ["tesseract"]

        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "--ocr-engine", "bogus", str(pdf)])
        with pytest.raises(SystemExit) as cli_exit:
            doc2txt.main()
        with pytest.raises(SystemExit) as watcher_exit:
            doc2txt_watcher.main(["--watch-dir", str(tmp_path), "--once", "--db-path", str(tmp_path / "w.db"), "--ocr-engine", "bogus"])
        assert (cli_exit.value.code, watcher_exit.value.code) == (2, 2)
        with pytest.raises(KeyError):
            doc2txt_ocr.resolve_ocr_engine("bogus")


class TestIntegration:
    """INT-* tests: end-to-end CLI runs."""

    def test_int_001_cli_recursion_through_linked_root_and_subdir(self, tmp_path, monkeypatch):
        """BUG-005: -r on a linked root converts a document reachable only through a nested link."""
        import docx
        from doc2txt import main

        real, other = tmp_path / "real", tmp_path / "other"
        real.mkdir()
        other.mkdir()
        doc = docx.Document()
        doc.add_paragraph("Reached through two links")
        doc.save(str(other / "linked.docx"))
        (real / "sub_link").symlink_to(other, target_is_directory=True)
        root_link = tmp_path / "root_link"
        root_link.symlink_to(real, target_is_directory=True)

        monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-q", "-j", "1", "--no-ocr", "-r", str(root_link)])
        assert main() == 0
        assert (other / "linked.md").exists()

    def test_int_002_cli_verbose_shows_folders(self, tmp_path, monkeypatch, capsys):
        """-v prints status | folder | file, sequential (with Processing lines) and parallel."""
        import docx
        from doc2txt import main

        for jobs in ("1", "2"):
            root = tmp_path / f"j{jobs}"
            for rel in ("a/x.docx", "b/c/y.docx"):
                (root / rel).parent.mkdir(parents=True)
                doc = docx.Document()
                doc.add_paragraph("Hello")
                doc.save(str(root / rel))

            monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-v", "-r", "--no-ocr", "-j", jobs, str(root)])
            assert main() == 0
            lines = set(capsys.readouterr().out.splitlines())
            assert {f"{'Created':<16}  a  x.md", f"{'Created':<16}  b/c  y.md"} <= lines
            processing = {f"{'Processing':<16}  a  x.docx", f"{'Processing':<16}  b/c  y.docx"}
            assert (processing <= lines) == (jobs == "1")

            (root / "d").mkdir()
            docx.Document().save(str(root / "d" / "z.docx"))
            monkeypatch.setattr(sys, "argv", ["doc2txt.py", "-v", "-r", "--no-ocr", "--improve", "-j", jobs, str(root)])
            main()
            improve_lines = [ln for ln in capsys.readouterr().out.splitlines()
                             if ln.startswith(("Improved ", "Kept (better quality) ", "Created "))]
            assert len(improve_lines) == 3
            assert all(ln[21:23] == "  " and ln[23] != " " for ln in improve_lines)


class TestProactive:
    """PRO-* tests: detect structural anti-patterns before they manifest as bugs."""

    def test_pro_001_module_size_enforcement(self):
        """No source file should exceed the module size limit.

        The limit sits about 20% above the largest module (doc2txt.py, 996 lines
        after the 2026-10-16 split), so it stops a monolith regrowing, not routine edits.
        """
        project_root = Path(__file__).parent.parent
        max_lines = 1200

        violations = []
        for py_file in project_root.glob("*.py"):
            if py_file.name.startswith("test_") or py_file.name.startswith("."):
                continue
            line_count = len(py_file.read_text().splitlines())
            if line_count > max_lines:
                violations.append(f"{py_file.name}: {line_count} lines (limit: {max_lines})")

        assert not violations, (
            "Module size violations:\n" + "\n".join(violations)
        )

    def test_pro_003_discovery_goes_through_iter_documents(self):
        """BUG-005: no Path.glob/rglob discovery in doc2txt*.py.

        rglob never descends symlinked directories and drops unreadable ones
        silently; three call sites used it before BUG-005.
        """
        project_root = Path(__file__).parent.parent
        violations = [
            f"{f.name}:{i}: {line.strip()}"
            for f in sorted(project_root.glob("doc2txt*.py"))
            for i, line in enumerate(f.read_text().splitlines(), 1)
            if "rglob(" in line or ".glob(" in line
        ]
        assert not violations, "Use iter_documents():\n" + "\n".join(violations)

    def test_pro_004_no_substring_status_checks(self):
        """BUG-006: results are classified by result_status(), never by a substring of the message.

        A substring test also matches the filename: "FAILED: Skipped items.pdf - ..."
        counted as skipped in run_simple and run_with_hud.
        """
        import re

        project_root = Path(__file__).parent.parent
        violations = [
            f"{f.name}:{i}: {line.strip()}"
            for f in sorted(project_root.glob("doc2txt*.py"))
            for i, line in enumerate(f.read_text().splitlines(), 1)
            if re.search(r"\bin message\b", line)
        ]
        assert not violations, "Use result_status():\n" + "\n".join(violations)
