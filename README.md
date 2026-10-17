# doc2txt

Extract text from PDFs and create markdown files with OCR support and parallel processing.

## Features

- **Text Extraction**: Converts PDF files to markdown format
- **OCR for images in PDFs**: Surya when installed, otherwise Tesseract; PaddleOCR only when named
- **Parallel Processing**: Utilizes all CPU cores for faster batch processing
- **Quality Scoring**: `--improve` mode re-extracts and only overwrites if quality is better
- **Retro HUD**: Optional 80's style terminal interface with progress tracking
- **WSL Support**: Handles Windows paths transparently

## Installation

```bash
# Clone the repository
git clone https://github.com/BAM-BAM-BAM/doc2txt.git
cd doc2txt

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Tesseract does the OCR unless Surya is installed
sudo apt install tesseract-ocr

# Optional: Surya (GPU recommended); not installed on the reference machine
pip install surya-ocr
```

## OCR Engines

| `--ocr-engine` | Tries, in order | Notes |
|--------|----------|-------|
| `surya` (CLI default) | surya, tesseract | Surya needs `pip install surya-ocr`; GPU recommended |
| `auto` (watcher default) | surya, tesseract | Same as `surya` |
| `tesseract` | tesseract | System package `tesseract-ocr` |
| `paddle` | paddle | Only when named: PaddlePaddle 3.3 fails on CPU here (oneDNN) |

An OCR error fails the document (`FAILED:`); no `.md` is written, and the watcher retries it.

## Usage

```bash
# Basic usage - process all PDFs in a directory
./doc2txt.py /path/to/pdfs

# Process a single file (output .md is written beside it)
./doc2txt.py /path/to/file.pdf

# Recursive search with verbose output
./doc2txt.py -r -v /path/to/pdfs

# Use the retro HUD display
./doc2txt.py -r --hud /path/to/pdfs

# Control parallel workers (default: CPU count)
./doc2txt.py -r -j 8 /path/to/pdfs    # Use 8 workers
./doc2txt.py -r -j 1 /path/to/pdfs    # Sequential processing

# Use Surya for higher accuracy OCR
./doc2txt.py -r --ocr-engine surya /path/to/pdfs

# Re-extract and improve existing files
./doc2txt.py -r --improve /path/to/pdfs

# Dry run - show what would be processed
./doc2txt.py -r -n /path/to/pdfs

# Force overwrite existing markdown files
./doc2txt.py -r -f /path/to/pdfs

# Disable OCR
./doc2txt.py -r --no-ocr /path/to/pdfs
```

## CLI Options

| Option | Description |
|--------|-------------|
| `-r, --recursive` | Search subdirectories for PDFs |
| `-v, --verbose` | Per-document progress: status, folder, file |
| `-q, --quiet` | Suppress all output except errors |
| `--hud` | Show retro 80's style HUD |
| `-j N, --jobs N` | Number of parallel workers (default: CPU count) |
| `--ocr-engine` | `surya` (default), `auto`, `tesseract` or `paddle`; see OCR Engines |
| `-n, --dry-run` | List files without processing |
| `-f, --force` | Overwrite existing markdown files |
| `--improve` | Re-extract and only overwrite if better quality |
| `--no-ocr` | Disable OCR for image-based pages |

## Output Format

Creates a `.md` file alongside each document with:
- Title from filename
- Source path reference (absolute)
- A line recording what made the file (below)
- Page separators with page numbers
- Extracted text content

```
# invoice

> Source: /mnt/d/OneDrive/Docs/invoice.pdf
>
> Made by doc2txt d8cd76e on 2026-10-17 · pymupdf 1.27.2.3 · OCR engine: tesseract · 12 pages, 5 with images, OCR text on 3
```

| Field | Meaning |
|-------|---------|
| `d8cd76e` | git commit of the code that ran (`git rev-parse --short=7 HEAD`); `unknown` if it could not be read, e.g. a copy without `.git` |
| `2026-10-17` | local date of the conversion |
| `pymupdf 1.27.2.3` | PDF library version; it extracts the text layer, and pymupdf has Tesseract compiled in, so with `OCR engine: tesseract` it is also the OCR build |
| `OCR engine` | engine the extraction used; `none` when OCR was off or unavailable; `, every page` with `--force-ocr` |
| `12 pages, 5 with images` | OCR runs only on pages with images (or every page with `--force-ocr`) |
| `OCR text on 3` | pages where OCR produced text |

DOCX, DOC, RTF and ODT outputs end the line after the date.

- **After an OCR engine change**, OCR text can change only in outputs with pages with images or made with `--force-ocr`. A pymupdf upgrade can also change the text-layer extraction of every PDF output; select those by the `pymupdf` field.
- **Outputs without the line** were written before this feature.
- **Run bulk jobs from main.** Pull requests are squash-merged, so a branch commit never appears on main; the date orders outputs made from branches.

## Requirements

- Python 3.10+
- PyMuPDF
- Tesseract (`tesseract-ocr`), or Surya, for OCR
- Pillow

## License

MIT
