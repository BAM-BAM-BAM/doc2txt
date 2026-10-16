# Backlog

Items from expert reviews, user feedback, and identified improvements.
Every item must be tracked here until resolved.

**FGT Principle 10: Findings Must Be Tracked.**
If it's not in this file, it doesn't exist.

## Open

### Estate review #1 findings (2026-10-16)

From the quarterly estate review (fgt-config METHODOLOGY_LOG, 2026-10-16).

- [ ] **Documents that share a stem share one output, and the second is lost
      silently.** Reproduced at 93f5133: `Report.docx` and `Report.pdf` in one
      folder → `Created: Report.md`, `Skipped (exists)`, then "Single scan:
      0 files" on the next run. In the watched OneDrive tree (counts only):
      157 folder/stem groups collide and 150 documents have no markdown.
      FGT_DOMAIN_DOC INV-004 (output keeps the input's stem) forces the
      collision; needs a naming decision.
- [ ] **Four tests cannot fail** (each mutation-confirmed; a fifth,
      `test_pro_002`, was deleted with BUG-010):
      `test_eval_uncertainty_highest_at_half` (recomputes the
      formula inline); `test_eval_shuffle_produces_different_order` and
      `test_int_shuffle` (pass with the shuffle removed);
      `test_inv_thresholds_cover_all_cases` (re-implements the partition);
      `test_inv_contains_*` (assert a constant's own value).
- [ ] **The watcher skips `/mnt/g/Shared drives`:** the Google drive has not
      been mounted since the 2026-10-15 boot (`systemctl status mnt-g.mount`:
      "special device G: does not exist"). Same cause as tierras' 47 t1 test
      failures.
- [ ] **Unread:** `gpu_log.csv` (4.8 MB); 11 of 19 files in
      `vendor/fgt-config/scripts`; the second half of `clear_gpu_memory()`
      (probes PIDs, kills none, though its docstring says it kills); the
      `--learn` path (no `learning.db`, no `--learn` in the crontab line).
- [ ] **Stale refs:** 8 remote-tracking refs whose branches are gone
      (`git remote prune origin --dry-run`); local `fgt-catchup-2026-09-28`
      (squash-merged as #2).

### OCR follow-ups (BUG-010, 2026-10-16)
- [ ] **Regenerate the outputs on `/mnt/g` once it is mounted.** Its 4,142 PDF rows could not be classified or regenerated; run the BUG-010 regeneration job's classification and `run.py` over them (`~/.doc2txt/revalidate-ocr-2026-10-16/`). Depends on the `/mnt/g` item above.
- [ ] **CLI outputs outside the watch folders were made without image OCR**, including the Personal Vault run of 2026-10-16. Nothing records them. Rerun with `./doc2txt.py -r -f <dir>` (for the vault: mount it as in `.claude/CLAUDE.md`, then run on `~/mnt/vault`).
- [ ] **17 one-page PDFs hold 61–609 words drawn as vector outlines** (about 11 distinct documents) and produce empty outputs: no text layer and no image, so only full-page OCR (`--force-ocr`) reads them. Decide whether a page with no text and no image should get full-page OCR.
- [ ] **The watcher has no time limit for very large image regions.** 3 documents have regions over 50 Mpx; a synthetic 41-Mpx strip did not finish OCR in 45 minutes. A new document like that would stall a nightly run.

## Resolved

### OCR (2026-10-16, BUG-010)
- [x] Scanned PDFs converted to empty `.md` files and were recorded as processed -- Tesseract region OCR fixed (`pdfocr_tobytes`), rotated pages, zero-area images and duplicate text-layer words handled, one engine table (`OCR_FALLBACKS`) for the CLI and the watcher, OCR errors fail the document; test_qual_004, test_bound_020, test_bound_021, test_bound_022, test_contract_ocr_engine_resolution; `scripts/ocr_canary.py` run daily by the sweep. Regeneration of the 5,071 affected outputs is tracked by the sweep
- [x] PRO-002 could not fail (it only warned) -- deleted; PATTERNS_DOC's PRO example now lists the PRO tests that can fail

### Architecture (2026-10-16)
- [x] Further split doc2txt.py (2,447 lines) into extractors.py + ocr.py + cli.py -- `doc2txt_ocr.py` (845), `doc2txt_extractors.py` (636, with discovery and status labels so the watcher never imports the CLI), `doc2txt.py` stays the CLI (996); code moved unchanged (AST check), aliases `process_pdf`/`process_pdf_worker` deleted; PRO-001 limit 3,800 → 1,200; PRO-002 and PRO-004 scan every `doc2txt*.py`

### Backlog cleanup (2026-10-16)
- [x] `FileReadinessChecker.is_ready`'s `CLOUD_SYNC_TEMP_PATTERNS` check could not match anything `scan_once` passes it -- deleted with `_matches_pattern` and `test_bound_temp_file_not_ready`; `test_int_scan_finds_ready_files` already asserts a non-document name is never scanned
- [x] fgt-config template `fgt_stop_check.sh.tmpl:54` and lang-app's copy ended `changed_in_session` with `grep -qE` under `pipefail` -- fixed in fgt-config #57 (merged: template, `examples/demo-py`, a `test-new-project.sh` assertion) and lang-app #3 (merged by the owner, 7982c3e; the sweep check that tracked it was removed once it passed). The five older project copies and two `fgt-sync.sh` pipelines are tracked in fgt-config's BACKLOG
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
