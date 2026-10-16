# doc2txt Bug Patterns

Bug catalog for escaped bugs. Each entry links to the prevention principle it violated
(see [FGT.md](FGT.md) Prevention Principles).

## Bug Catalog

### BUG-001: page_needs_ocr() heuristic fails on embedded fonts

| Field | Value |
|-------|-------|
| **Symptom** | PDFs with embedded fonts report text layers but contain no extractable text. Heuristic says "no OCR needed" but output is empty. |
| **Root Cause** | pymupdf's `get_text("blocks")` gives false positives for pages with embedded fonts — reports text blocks exist but extracted text is empty or gibberish |
| **Fix** | Removed heuristic after 7 iterations. Simplified to: always OCR images, extract text from text layers. Simpler approach is more robust. |
| **Principle Violated** | #4 (Invariants Must Be Tested) — heuristic was never validated against ground truth corpus |
| **Prevention Test** | QUAL-001: extraction of known scanned PDF produces non-empty, readable text |
| **Siblings** | Any PDF classification heuristic relying on pymupdf text block detection |
| **Data Revalidation** | N/A — no stored data, output regenerated on each run |

**Pattern:** Heuristic complexity spiral. The function was modified 7 times across 12
commits (CP-005). Each fix addressed one edge case but introduced others. The simple
approach (OCR all images unconditionally) was more robust than the clever one. See
FGT.md Heuristic Complexity Review trigger.

---

### BUG-002: Feature vector dimension change breaks classifier

| Field | Value |
|-------|-------|
| **Symptom** | AdaptiveLearner crashes with dimension mismatch when loading saved model after feature vector changed from 12 to 14 elements |
| **Root Cause** | `ImageFeature.to_vector()` was updated to include `log_area` and `log_area * is_body` interaction features, but existing database records stored old 12-element vectors |
| **Fix** | Added DB migration to recompute vectors. Added backward-compatible vector handling. |
| **Principle Violated** | #6 (Verify Before Trust) — assumed stored data matched current schema without validation |
| **Prevention Test** | SCHEMA-001: `ImageFeature.to_vector()` returns exactly 14 elements. INV-003: feature vector dimension matches expected constant. |
| **Siblings** | Any ML feature pipeline with persistent state — schema changes need migration plans |
| **Data Revalidation** | Yes — database records reprocessed with new 14-element vectors |

**Pattern:** Schema evolution without migration. When a data structure changes,
all stored instances of that structure must be migrated or the code must handle
both old and new formats. This is CP-001 (Stale Data After Logic Fix).

---

### BUG-003: GPU VRAM exhaustion during OCR

| Field | Value |
|-------|-------|
| **Symptom** | Process killed or hangs when OCR models exceed available GPU VRAM on systems with <8GB |
| **Root Cause** | No check of available GPU memory before loading Surya/PaddleOCR models. Large PDFs with many images could exhaust VRAM mid-batch. |
| **Fix** | Added `--cpu` flag for forced CPU mode. Added VRAM-based batch size auto-tuning. Added `clear_gpu_memory()` calls between batches. |
| **Principle Violated** | #8 (Defenses Must Be Operational) — no resource guard on GPU allocation |
| **Prevention Test** | BOUND-001: OCR gracefully falls back to CPU when GPU unavailable or VRAM insufficient |
| **Siblings** | Any GPU-dependent pipeline without resource guards |
| **Data Revalidation** | N/A — process crash prevented output generation |

**Pattern:** Resource-dependent operations without guards. The defense (GPU memory
management) didn't exist — it wasn't hollow, it was absent. Any pipeline using
GPU resources must check availability before loading and have a CPU fallback path.

---

### BUG-004: Uncaught OSError on dead mount aborts entire watcher scan

| Field | Value |
|-------|-------|
| **Symptom** | 20 of 44 nightly cron runs (May–June 2026) died with a traceback: `OSError: [Errno 19] No such device: '/mnt/g/Shared drives'` (18x, Google Drive not mounted) and `OSError: [Errno 5] Input/output error` (2x, OneDrive paths). One unreachable path aborted the whole scan — the reachable watch dirs were never processed that night. |
| **Root Cause** | `scan_once()` guarded missing dirs with `if not watch_dir.exists()`, assuming `exists()` returns False for anything unreachable. On dead mounts (ENODEV) and stalled cloud-sync paths (EIO), `os.stat()` raises instead of returning — the guard itself crashed. Same for `path.is_file()` on individual files mid-scan. |
| **Fix** | Per-path error containment in `scan_once()`: OSError on a watch dir logs a warning and continues with remaining dirs; OSError while listing or on an individual file skips that entry. Blast radius of one bad path = one skipped path, not the run. |
| **Principle Violated** | #9 (Defenses Must Be Operational) — the exists() guard was the defense against bad watch dirs, but it only covered the ENOENT case; on ENODEV/EIO the defense itself raised, so it defended against nothing on the exact filesystems (WSL2 /mnt/ drive mounts, cloud sync) the watcher was built for. |
| **Prevention Test** | test_watcher.py: `test_bound_unreachable_watch_dir_skipped` (ENODEV on one dir; scan still returns other dirs' files) and `test_bound_io_error_on_one_file_skips_file` (EIO on one file mid-scan; remaining files still scanned). Simulated via monkeypatched `Path.exists`/`Path.stat` on tmp_path fixtures — no real mounts. |
| **Siblings** | `find_pdfs()` / `find_documents()` in doc2txt.py and `main()`'s path check were left unguarded, on the theory that the interactive CLI should fail loudly. The actual failure was a traceback, and rglob dropped unreadable directories without any message — fixed in BUG-005. |
| **Data Revalidation** | N/A — scan-time behavior only; no stored classifications changed. Files missed by crashed runs were picked up by later successful runs (tracker is mtime/size-based). |

**Pattern:** Existence checks are not exception guards. On removable/network/cloud
filesystems, `exists()`, `is_file()`, and `stat()` raise OSError rather than
returning False. Any long-running or unattended loop over such paths needs
per-item OSError containment sized to the smallest unit of work it can skip.

---

### BUG-005: CLI traceback on an unreadable link; recursion never followed symlinked directories

| Field | Value |
|-------|-------|
| **Symptom** | `doc2txt.py -v -r '/mnt/d/OneDrive/Personal Vault/'` died with `OSError: [Errno 5] Input/output error` at `path.exists()` in `main()`. The vault is a Windows junction to `\??\Volume{…}\VaultData`, a volume with no drive letter; on WSL `lstat` succeeds but `stat` through the link and `readlink` return EIO. Separately, `-r` never descended a symlinked subdirectory. |
| **Root Cause** | (1) `main()` used `exists()` as a guard; EIO raises instead of returning False (BUG-004 class). (2) Discovery delegated to `Path.rglob`, whose 3.12 walk uses `follow_symlinks=False, on_error=None` (`pathlib.py:229`, `:1114`, `:1132-1150`): symlinked directories are listed as files and unlistable directories vanish silently. Nobody had specified or tested link and error behavior for discovery. |
| **Fix** | One walker, `iter_documents()` (doc2txt.py): `os.scandir` stack walk that follows symlinked files and directories, walks each directory once keyed by `(st_dev, st_ino)` so cycles terminate, stats each candidate document, and passes every unreadable link, directory or file to an `on_skip` callback. `find_documents()` and `FolderWatcher.scan_once()` both use it; `find_pdfs()` (test-only) deleted. `main()` catches OSError from the path check (and from a listing probe on a directory argument) and prints `Error: cannot read <path>: <reason>`, adding `(symbolic link; target unreadable)` for links; `is_symlink()` sits in its own try because it re-raises ENODEV/EIO (`pathlib.py:915-919`). |
| **Principle Violated** | #2 (Explicit Contracts) — discovery semantics for links and errors were inherited from a library and never tested. #9 (Defenses Must Be Operational) — the `exists()` guard raised on EIO. |
| **Prevention Test** | test_fgt_categories.py: `test_bound_007` (symlinked subdir with/without -r), `test_bound_008` (link cycle, real and linked root; regression guard — rglob never descended links), `test_bound_009` (dangling link → on_skip), `test_bound_010` (EIO on link target → on_skip), `test_bound_011` (scandir EIO on subdir → on_skip, siblings kept), `test_bound_012` (CLI on EIO link → exit 1, message), `test_bound_013` (CLI on ENODEV dead mount → exit 1), `test_bound_014` (EIO on one regular document → skipped with a warning, exit 0; previously a traceback from the size sum), `test_bound_015` (unlistable directory argument → exit 1 even with -q; previously exit 0), `test_int_001` (CLI -r through linked root and nested link writes .md), `test_pro_003` (no `.glob(`/`rglob(` in doc2txt*.py). test_watcher.py: `test_bound_symlinked_subdir_scanned`; `test_bound_unlistable_watch_dir_skipped` rewritten to patch `os.scandir` (its `Path.rglob` patch would no longer be reached). |
| **Siblings** | Three rglob/glob discovery sites, all replaced: `find_documents`, `find_pdfs`, `scan_once`. Grep for unguarded `exists()`/`is_file()`: `FileReadinessChecker.is_ready` (doc2txt_watcher.py) runs inside `scan_once`'s per-file try; doc2txt.py `md_path.exists()` calls check derived output paths. Neither changed. The runners' `p.stat().st_size` calls can still raise if a file becomes unreadable between discovery and processing; accepted, since discovery now stats every document first. |
| **Data Revalidation** | Discovery only; no stored classifications. Old and new `find_documents(/mnt/d/OneDrive, recursive=True)` return the same 12,766 files (the vault is the only symlink under OneDrive); the new walk took 57.4 s (one pass plus one stat per document) vs 362.5 s for 15 rglob passes. |

**Pattern:** A library walker is a contract you did not write. State what discovery
does with links, cycles and unreadable entries, implement it once, and test each case;
`pro_003` keeps new call sites from bypassing it. Sunset `pro_003` once discovery lives
in its own module with these tests (BACKLOG split item).

