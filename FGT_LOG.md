# FGT Development Log: doc2txt

| Date | Task ID | Summary | Lessons |
|------|---------|---------|---------|
| 2026-01-26 | PDF-001 | Initial PDF extraction with parallel processing | Format-agnostic pipeline design with ProcessPoolExecutor. Use spawn context to avoid fork/curses issues. |
| 2026-01-26 | PDF-002 | Add PaddleOCR and Surya OCR engines | Multiple OCR backends with fallback. GPU memory is a hard constraint -- always plan for CPU fallback. |
| 2026-01-27 | PDF-003 | OCR detection heuristic (page_needs_ocr) | Heuristic failed on embedded fonts after 7 iterations. Eventually removed. Heuristic complexity spiral (CP-005). |
| 2026-01-27 | PDF-004 | Adaptive ML learning system for OCR decisions | 12 commits of ML evolution (LogisticRegression -> DecisionTree, feature vectors, Thompson sampling). Over-engineered -- start simple. |
| 2026-01-28 | PDF-005 | Feature vector dimension change (12 to 14) | Broke classifier DB records. Schema changes need migration plans. Stale data after logic fix (CP-001). |
| 2026-01-28 | PDF-006 | GPU VRAM management (--force-ocr, --cpu) | Added resource guards and CPU fallback. Defenses must exist, not just be operational (Principle 9). |
| 2026-04-09 | PDF-007 | FGT files added retroactively (commit 23/24) | Cargo-culted from VE project. PATTERNS/REVIEWS contained wrong-domain content. FGT_LOG empty. Apply methodology from day 1 (CP-006). |
| 2026-04-09 | DOC-001 | Add DOCX/DOC/RTF/ODT support | Thin dispatch at two chokepoints keeps ~95% of code untouched. Format-agnostic pipeline design pays off. |

---

## Entries

### 2026-01-26: Initial PDF extraction (PDF-001)

**Change**: Built core extraction pipeline with parallel processing via ProcessPoolExecutor.

**Lessons**:
- Use `multiprocessing.get_context("spawn")` to avoid terminal/curses issues with fork
- Design the pipeline to be format-agnostic from the start -- it paid off when adding DOCX support later

### 2026-01-26: OCR engine integration (PDF-002)

**Change**: Added Surya (GPU) and PaddleOCR as OCR backends.

**Lessons**:
- GPU memory is a hard constraint, not a soft one. Systems with <8GB VRAM will OOM on large PDFs
- Always provide a CPU fallback path for GPU-dependent operations
- Pin dependency versions (transformers 5.0.0 broke surya-ocr compatibility)

### 2026-01-27: page_needs_ocr() heuristic spiral (PDF-003)

**Change**: Attempted to build a smart heuristic to decide which pages need OCR. Modified 7 times across 12 commits.

**Lessons**:
- pymupdf's `get_text("blocks")` reports false positives for embedded fonts
- The heuristic was eventually removed in favor of a simpler approach (OCR all images, extract text from text layers)
- This is CP-005 (Heuristic Complexity Spiral) -- when a heuristic has been modified 3+ times, trigger architecture review
- Simple and robust beats clever and fragile

### 2026-01-27: Adaptive ML system (PDF-004)

**Change**: Built feature extraction, Bayesian learning, K-means clustering, Thompson sampling, and skip validation for OCR decisions.

**Lessons**:
- 12 commits of incremental ML complexity that could have been avoided with a simpler approach
- LogisticRegression was replaced by DecisionTreeClassifier for better accuracy
- Never add Bayesian exploration or Thompson sampling unless you have quantitative evidence the simpler approach is insufficient
- The ML pipeline was the most complex part of the codebase but provided marginal improvement

### 2026-01-28: Feature vector dimension change (PDF-005)

**Change**: Updated ImageFeature.to_vector() from 12 to 14 elements (added log_area and interaction term). Broke existing classifier database records.

**Lessons**:
- Schema changes need migration plans before implementation
- Stored data must be validated against current schema (Principle 7: Verify Before Trust)
- This is CP-001 (Stale Data After Logic Fix) -- fix the code AND the data

### 2026-01-28: GPU VRAM management (PDF-006)

**Change**: Added --force-ocr, --cpu flags. Implemented VRAM-based batch size auto-tuning and memory cleanup.

**Lessons**:
- Resource-dependent operations need guards (check availability before loading)
- WSL may hold zombie GPU processes after crashes -- requires full WSL restart
- A defense that doesn't exist is worse than a hollow defense (Principle 9 extension)

### 2026-04-09: FGT retrofit and cargo-cult detection (PDF-007)

**Change**: FGT methodology files were added in commit 23 of 24. PATTERNS_DOC.md and REVIEWS_DOC.md were copied from the VE project without adaptation.

**Lessons**:
- Cargo-culting FGT files provides false confidence -- the wrong-domain content is never consulted
- FGT_LOG remained empty for all 24 commits, meaning the self-improvement loop never activated
- Retroactive methodology adoption is significantly less effective than proactive adoption
- This experience led to Principle 11 (Scaffold Before Building) and the cargo-cult warning in CLAUDE_MD_TEMPLATE

### 2026-04-09: Multi-format document support (DOC-001)

**Change**: Extended doc2txt to process DOCX, DOC, RTF, and ODT files alongside PDFs.

**Approach**: Added `extract_text()` dispatcher that routes by file extension. DOCX uses python-docx directly; DOC/RTF/ODT convert via LibreOffice headless to DOCX first. All extractors return `list[str]` (sections of text) -- the existing pipeline (quality scoring, parallel processing, HUD, improve mode) works unchanged.

**Key decisions**:
- Single dispatch function, no class hierarchy -- keeps complexity proportional to the problem
- OCR params pass through harmlessly to non-PDF extractors (no conditional CLI logic needed)
- LibreOffice is optional -- only required for legacy .doc/.rtf/.odt formats
- DOCX headings convert to markdown `#` syntax, tables to markdown tables

**Tests**: 34 new tests covering find_documents, DOCX extraction, dispatcher, create_markdown, process_document. All 56 tests pass (22 existing + 34 new).

**Lessons**:
- The existing pipeline was already ~95% format-agnostic -- only `find_pdfs()` and `extract_text_from_pdf()` were truly PDF-specific
- Adding format support at the extraction layer means all downstream features (parallel, HUD, quality scoring, improve mode) work automatically

### 2026-07-07: Watcher crash class fixed via Bug Abstraction Protocol (DOC-002)

**Change**: Per-path OSError containment in `FolderWatcher.scan_once()` — an unreachable watch dir (unmounted /mnt/g, ENODEV) or an I/O-erroring file (OneDrive, EIO) now logs a warning and is skipped instead of aborting the entire nightly scan. BUG-004 documented; 3 BOUND tests + 11 CLI tests added (test_watcher.py, 32 total); two watcher.log health checks added to scripts/sweep.sh (recent tracebacks within 7 days, last-run freshness <=72h).

**Evidence**: 20 of 44 nightly cron runs (May-June 2026) died with uncaught OSError tracebacks in watcher.log — unnoticed for weeks because nothing watched the log.

**Lessons**:
- Existence checks are not exception guards: on dead mounts and cloud-sync paths, `Path.exists()`/`is_file()`/`stat()` raise OSError instead of returning False (Principle 9 — the exists() guard itself crashed on the exact filesystems the watcher targets)
- Unattended loops need error containment sized to the smallest skippable unit of work (one path, not one run)
- Silent cron death is its own bug class: absence of output looks like success; a sweep freshness check is the enforcement plane

### 2026-10-16: Discovery follows links; CLI exits cleanly on unreadable paths (BUG-005)

**Change**: New `iter_documents()` walker in doc2txt.py replaces the three `rglob`/`glob` discovery sites (`find_documents`, `find_pdfs` — deleted, `FolderWatcher.scan_once`). It follows symlinked files and directories, walks each directory once by `(st_dev, st_ino)`, and reports unreadable links and directories instead of dropping them. `main()` prints one `Error: cannot read …` line instead of a traceback, and exits 1 when a directory argument cannot be listed. 12 new tests (123 total), one watcher test rewritten.

**Evidence**: `doc2txt.py -r '/mnt/d/OneDrive/Personal Vault/'` crashed with EIO. The vault is a junction to a volume with no drive letter, which WSL cannot follow; processing it needs a separate drvfs mount.

**Lessons**:
- `Path.rglob` (3.12) never descends symlinked directories and swallows listing errors; a walker whose link and error behavior matters has to be written and tested, not inherited
- One walk per tree, not one per glob pattern: on drvfs the same 12,766-file discovery went from 362.5 s (15 rglob passes) to 57.4 s, including one stat per document
- The BUG-004 decision to leave the CLI unguarded assumed a "loud failure"; the real outcome was a traceback. Check what the failure actually prints before accepting it as the error message

### 2026-10-16: `-v` progress lines show status | folder | file columns

**Change**: `progress_formatter()` renders each `-v` line as three columns: the status, the document's folder relative to the path argument, and the name from the message. On a terminal at least `status_width + 25` columns wide (41 by default), lines are fitted to the current width with a middle `...` (ASCII, so a non-UTF-8 stdout cannot raise); FAILED lines keep their full error. When stdout is not a terminal, nothing is truncated. The status column is as wide as the longest label the run can print (16 by default, 21 with `--improve`, 26 when learning), from one `_status_width()` helper. `run_simple` keeps its `Processing` pre-line in the same columns. 5 new tests (128 total); the `--improve` and learn widths were checked by mutation.

**Evidence**: On the 2,562-document vault run, `-v` printed only `Created: x.md`, so there was no way to see which folder the run had reached. In a real pty (`script` + `stty cols`) at 80 and 188 columns, no non-FAILED line exceeded `columns - 1`, and every folder started at column 18.

**Lessons**:
- `shutil.get_terminal_size()` prefers `$COLUMNS` and queries `sys.__stdout__`; `os.get_terminal_size(sys.stdout.fileno())` reads the live width of the actual stdout and raises when it is not a terminal
- `script -qec "stty cols N; …" /dev/null` gives a real terminal for checking width-dependent output from a non-interactive shell

