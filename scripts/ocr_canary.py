"""OCR canary: convert a generated scanned PDF the way the nightly watcher does.

Run by scripts/sweep.sh with the cron's interpreter (.venv) under cron's environment,
because that environment changes without commits and CI has no tesseract.
Exit 0 and print "ok" when the .md holds the scanned words; otherwise exit 1 and print why.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402

from doc2txt_extractors import process_document  # noqa: E402

WORDS = "INVOICE 12345"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "canary.pdf"
        src = pymupdf.open()
        scan = src.new_page(width=400, height=120)
        scan.insert_text((20, 75), WORDS, fontsize=40)
        doc = pymupdf.open()
        doc.new_page(width=400, height=400).insert_image(scan.rect, pixmap=scan.get_pixmap(dpi=150))
        doc.save(pdf)

        success, message, _ = process_document(pdf, overwrite=False, dry_run=False, ocr_engine="auto")
        md = pdf.with_suffix(".md")
        text = md.read_text(encoding="utf-8") if md.exists() else ""
        if success and "12345" in text:
            print("ok")
            return 0
        print(message if not success else "OCR produced no text for a scanned page")
        return 1


if __name__ == "__main__":
    sys.exit(main())
