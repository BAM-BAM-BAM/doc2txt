# Backlog

Items from expert reviews, user feedback, and identified improvements.
Every item must be tracked here until resolved.

**FGT Principle 10: Findings Must Be Tracked.**
If it's not in this file, it doesn't exist.

## Open

### Architecture
- [ ] Further split doc2txt.py (2,278 lines) into extractors.py + ocr.py + cli.py -- source: PATTERNS_DOC.md target structure

### OCR
- [ ] **Scanned PDFs convert to empty `.md` files and are recorded as processed.** Found 2026-10-16 while reviewing the split plan.
  - Tesseract on an image region: `ocr_image_region` passes `clip=` to `page.get_textpage_ocr`, which raises TypeError in pymupdf 1.27.2.3 (`.venv`, the cron interpreter) and 1.26.7 (system). Full-page Tesseract (`--force-ocr`) works.
  - `resolve_ocr_engine` has no `"auto"` key, so the watcher's default `auto` resolves to Tesseract.
  - PaddleOCR page OCR raises NotImplementedError (`ConvertPirAttribute2RuntimeAttribute not support`); surya is not installed.
  - `extract_page_text` catches the exception and falls back to the text layer, so a scanned PDF returns `Created:` with an empty body under both `auto` and `paddle`.
  - Data: of 6,729 watcher `.md` outputs from PDFs that still exist, 932 have an empty body and 685 have under 100 non-space characters. Of the 932, 82 PDFs have images and no text layer; 850 have no image found by `get_images(full=False)` and no text layer (cause not diagnosed); 922 date from the May 2026 bulk run, 10 since June.
  - BUG-001 names QUAL-001 as its prevention test for scanned PDFs, but `test_qual_001` extracts a DOCX; no test runs OCR.
  - Fix needs data revalidation: the 932 rows are marked processed, and their `.md` files exist, so the watcher skips them even when unmarked.
  - -- source: split plan review 2026-10-16

### Testing
- [ ] PRO-002 (`test_pro_002_no_hardcoded_extensions_outside_registry`) cannot fail: it only warns, on 3 lines today (`page_label`, `is_pdf`, `has_pdfs`, all `== '.pdf'`). Making it strict means deciding which per-format checks are allowed -- source: split plan review 2026-10-16

## Resolved

### Backlog cleanup (2026-10-16)
- [x] `FileReadinessChecker.is_ready`'s `CLOUD_SYNC_TEMP_PATTERNS` check could not match anything `scan_once` passes it -- deleted with `_matches_pattern` and `test_bound_temp_file_not_ready`; `test_int_scan_finds_ready_files` already asserts a non-document name is never scanned
- [x] fgt-config template `fgt_stop_check.sh.tmpl:54` and lang-app's copy ended `changed_in_session` with `grep -qE` under `pipefail` -- fixed in fgt-config #57 (merged: template, `examples/demo-py`, a `test-new-project.sh` assertion) and lang-app #3 (open: lang-app main has no branch protection, so the owner merges it; `scripts/sweep.sh` WARNs until lang-app's checked-out hook is fixed). The five older project copies and two `fgt-sync.sh` pipelines are tracked in fgt-config's BACKLOG
- [x] Expand FGT_DOMAIN_DOC.md with additional bug patterns as discovered -- BUG-004, 005, 007 and 009 lessons added (bug patterns, constants, LibreOffice Writer); Bug Abstraction step 7 in CLAUDE.md now names FGT_DOMAIN_DOC.md, so each future bug fix carries this forward

### CLI (2026-10-16, BUG-009)
- [x] Batch discovery did not skip `~$` Word owner files, so `doc2txt.py -r` reported them FAILED and exited 1 -- `iter_documents` skips `OFFICE_OWNER_PREFIX`; watcher's unreachable duplicate removed; test_bound_019, test_bound_word_owner_file_not_scanned

### CLI (2026-10-16)
- [x] `run_simple` counters matched substrings, so a failure on `Skipped items.pdf` counted as skipped and exited 0 -- BUG-006: `result_status()` + `count_outcome()` (also `run_with_hud`), test_bound_016, test_pro_004
- [x] Watcher marked failed documents as processed, so they were never retried -- BUG-007: failures unmarked and logged as errors, dry run marks nothing, `~$` owner files filtered, Writer check; the 484 stored rows deleted (backup `~/.doc2txt/watcher.db.bak-2026-10-16`)
- [x] `--watch --formats` built extensions without `.strip().lower()` -- BUG-008: `parse_formats()` shared by batch, `--watch` and the watcher CLI, test_bound_017

### FGT/OCD standards review (2026-07-07)
- [x] Commit the watcher CLI entrypoint (doc2txt_watcher.py `main()`/argparse, dirty since 2026-05-13) -- committed as fe1a6dd
- [x] Run Bug Abstraction Protocol on watcher crashes: 20 of 44 nightly runs died on uncaught OSError (unmounted /mnt/g x18, OneDrive I/O error x2); one bad path aborts the entire scan -- BUG-004 + per-path OSError containment in scan_once() + 3 BOUND tests in test_watcher.py
- [x] Add tests for the watcher CLI (`main`/`_build_arg_parser` have zero coverage) -- TestCli in test_watcher.py: 11 tests (arg parsing, --once/loop dispatch, config wiring, format validation)
- [x] Add sweep.sh check for recent tracebacks in watcher.log -- two inline checks in scripts/sweep.sh: tracebacks within 7 days + freshness (last run <=72h, catches silent cron death)

### Architecture (2026-04-10)
- [x] Modularize doc2txt.py into separate modules -- split to doc2txt_models.py (175), doc2txt_quality.py (130), doc2txt_learning.py (904), doc2txt_hud.py (274), doc2txt.py (2,278)
- [x] Extract AdaptiveLearner into its own module -- doc2txt_learning.py
- [x] Extract TextQualityScorer to quality.py -- doc2txt_quality.py
- [x] Extract HUD/curses display to hud.py -- doc2txt_hud.py

### Testing (2026-04-10)
- [x] Add QUAL-001 test for extraction output quality -- test_fgt_categories.py
- [x] Add INV-001 test: all extensions have handlers -- test_fgt_categories.py
- [x] Add INV-003 test: feature vector dimension = 14 -- test_fgt_categories.py
- [x] Add BOUND-001 through BOUND-004 tests -- test_fgt_categories.py
- [x] Add PRO-001 test for module size enforcement -- test_fgt_categories.py
- [x] Add PRO-002 test for hardcoded extension detection -- test_fgt_categories.py
- [x] Rename existing 56 tests to FGT category prefixes -- test_adaptive_learner.py, test_document_formats.py

### Infrastructure (2026-04-10)
- [x] Add GitHub Actions CI workflow (test + lint + FGT validation) -- .github/workflows/verify.yml
- [x] Configure Claude Code hooks for FGT enforcement -- scripts/fgt_stop_check.sh
- [x] Set up branch protection on main (test + fgt-validation required) -- via gh api
