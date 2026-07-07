# Backlog

Items from expert reviews, user feedback, and identified improvements.
Every item must be tracked here until resolved.

**FGT Principle 10: Findings Must Be Tracked.**
If it's not in this file, it doesn't exist.

## Open

### Architecture
- [ ] Further split doc2txt.py (2,278 lines) into extractors.py + ocr.py + cli.py -- source: PATTERNS_DOC.md target structure

### Documentation
- [ ] Expand FGT_DOMAIN_DOC.md with additional bug patterns as discovered -- source: FGT methodology

### FGT/OCD standards review (2026-07-07)
- [ ] Commit the watcher CLI entrypoint (doc2txt_watcher.py `main()`/argparse, dirty since 2026-05-13) -- nightly 02:00 cron runs this uncommitted code; a checkout/clone silently breaks production
- [ ] Run Bug Abstraction Protocol on watcher crashes: 20 of 44 nightly runs died on uncaught OSError (unmounted /mnt/g x18, OneDrive I/O error x2); one bad path aborts the entire scan -- add BUG-XXX entry + per-path error handling + BOUND-* test
- [ ] Add tests for the watcher CLI (`main`/`_build_arg_parser` have zero coverage) -- source: pre-commit verification protocol in CLAUDE.md
- [ ] Add sweep.sh check for recent tracebacks in watcher.log -- crash class observed 20x, meets Principle 1 bar; SWEEP arrays currently empty

## Resolved

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
