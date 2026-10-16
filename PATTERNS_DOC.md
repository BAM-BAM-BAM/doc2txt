# doc2txt Code Patterns

Project-specific implementation patterns for document text extraction.
Supplements the generic methodology in [FGT.md](FGT.md).

This file does NOT contain: Generic FGT methodology (see `FGT.md`),
domain rules (see `FGT_DOMAIN_DOC.md`), review triggers (see `REVIEWS_DOC.md`).

---

## Single Source of Truth (Registry)

### Supported Format Registry

The canonical set of supported extensions lives in one place:

```python
# doc2txt_models.py (top-level constant)
SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.rtf', '.odt'}
```

**Rules:**
- All format discovery (`find_documents`) filters against this set
- All dispatch logic (`extract_text`) routes based on this set
- Adding a new format means: add to this set + add extractor + add tests
- No hardcoded extension checks elsewhere in the codebase

**Enforcement:** `INV-001` test verifies that every extension in
`SUPPORTED_EXTENSIONS` has a handler in `extract_text()`.

---

## Format Dispatch Pattern

Route by file extension at two chokepoints. All extractors return the
same type (`list[str]`), keeping the downstream pipeline format-agnostic.

```python
def extract_text(path: Path, **ocr_params) -> list[str]:
    """Dispatch extraction by file extension. Returns list of text sections."""
    ext = path.suffix.lower()
    if ext == '.pdf':
        return extract_text_from_pdf(path, **ocr_params)
    elif ext == '.docx':
        return extract_text_from_docx(path)
    elif ext in ('.doc', '.rtf', '.odt'):
        return extract_text_via_libreoffice(path)
    else:
        raise ValueError(f"Unsupported format: {ext}")
```

**Key decisions:**
- Single dispatch function, no class hierarchy (complexity proportional to problem)
- OCR params pass through harmlessly to non-PDF extractors
- LibreOffice is optional (only needed for legacy formats)
- ~95% of the pipeline (quality scoring, parallel processing, HUD) is format-agnostic

---

## Error Collection Pattern

Process all documents and collect results rather than aborting on first failure.
Users see ALL issues at once instead of fix-one-rerun cycles.

```python
def process_batch(documents: list[Path]) -> tuple[list[Result], list[Error]]:
    successes, errors = [], []
    for doc in documents:
        try:
            result = process_document(doc)
            successes.append(result)
        except Exception as e:
            errors.append((doc, e))
    return successes, errors
```

**When to apply:** Any pipeline where items are independent and partial
results are useful. doc2txt processes each document independently -- one
corrupted file shouldn't block the rest.

---

## OCR Fallback Pattern

OCR is inherently fragile. Multiple engines with graceful degradation:

```
Primary: Surya (GPU-accelerated, highest accuracy)
  -> Fallback: PaddleOCR (alternative GPU engine)
       -> Fallback: CPU mode (--cpu flag)
            -> Fallback: Skip OCR (text-only extraction)
```

**GPU memory management:**
- Check available VRAM before loading models
- Auto-tune batch size based on available memory
- `--force-ocr` flag: OCR all pages regardless of text detection
- `--cpu` flag: force CPU mode when GPU is unavailable or OOM
- Always clear GPU memory after OCR batch completes

**Lesson learned:** The `page_needs_ocr()` heuristic was modified 7 times
across 12 commits before being simplified. Simple approach (OCR images,
extract text from text layers) beats clever detection. See FGT.md
Heuristic Complexity Review trigger.

---

## Testing Patterns

### Golden File Tests

Save known-good extraction output as fixtures:

```
tests/
  fixtures/
    sample.pdf          # Known input
    sample_expected.md  # Expected output
```

Test that `extract_text(sample.pdf)` produces output matching the fixture.
When extraction logic changes, update fixtures deliberately (not silently).

### Three-Tier Strategy

1. **Unit tests:** Individual extractor functions with fixture files
2. **Integration tests:** Full `process_document()` pipeline end-to-end
3. **Quality tests (QUAL-*):** Output values are correct, not just non-empty

### Proactive Detection (PRO-*)

A PRO test scans the source of every `doc2txt*.py` module for a structural
anti-pattern and must be able to fail: `test_pro_001` (module size, see Module
Size Enforcement below), `test_pro_003` (discovery only through
`iter_documents`), `test_pro_004` (no substring status checks). A scan that can
only warn is not a defense; PRO-002 did that and was removed (BUG-010 PR).

---

## Module Size Enforcement

Flat modules, one concern each (lines as of 2026-10-16):

| Module | Lines | Holds |
|--------|-------|-------|
| `doc2txt.py` | 996 | CLI: argument parsing, progress lines, result counting, the four runners, `main` |
| `doc2txt_learning.py` | 974 | `AdaptiveLearner` (OCR skip decisions) |
| `doc2txt_ocr.py` | 845 | OCR engines, GPU management, per-page PDF extraction |
| `doc2txt_extractors.py` | 636 | Discovery, status labels, per-format extractors, `process_document` and its worker |
| `doc2txt_watcher.py` | 488 | Nightly folder watcher |
| `doc2txt_hud.py` | 274 | Curses progress display |
| `doc2txt_models.py` | 192 | Data models, `SUPPORTED_EXTENSIONS`, `parse_formats` |
| `doc2txt_quality.py` | 130 | Text quality scoring |

`doc2txt.py` imports `doc2txt_extractors.py` and `doc2txt_ocr.py`, and
`doc2txt_extractors.py` imports `doc2txt_ocr.py`. No module imports the CLI: the
watcher uses `doc2txt_extractors.py`.

**PRO-001** caps every module at 1,200 lines, about 20% above the largest. It stops a
monolith regrowing; a module that reaches it is split along a concern, not trimmed.
