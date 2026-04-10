# Francis Galton Technique (FGT)

> **Every escaped bug triggers a process improvement that becomes an automated enforcement.**

Three insights:

1. **Bugs that escape to users are process failures** — fix both the bug and the process
2. **Documentation gets skipped** — automation enforces what docs only recommend
3. **Automation is the only reliable enforcement** — voluntary compliance fails

**FGT is domain-agnostic.** Domain-specific knowledge goes in `FGT_DOMAIN_*.md` files.

---

## Bug Abstraction Protocol

When fixing ANY bug, complete ALL steps before committing:

1. **Fix the instance** — resolve the specific problem
2. **Abstract to class** — which principle was violated?
3. **Add BUG-XXX entry** — document in `BUG_PATTERNS.md`: Symptom, Root Cause, Fix, Principle
4. **Add prevention test** — catches the CLASS of error, not just this instance
5. **Search for siblings** — grep the codebase for the same pattern elsewhere
6. **Revalidate existing data** — if the fix changes ANY logic that determines how data is classified, filtered, displayed, or acted upon, follow the revalidation protocol: snapshot current state → apply fixed logic to all existing records → safety gate (abort if >50% of >50 records would change) → commit revalidated data → log what changed. Keep raw input data for re-ingestion (default 30-day retention). See `REVALIDATION_TEMPLATE.md` for the full workflow. Code fixes that don't clean up past data are half-fixes
7. **Persist the pattern** — update memory/docs for future sessions

Don't add narrow fixes. Find the principle that prevents entire categories:

| Bad (narrow) | Good (generalized) |
|--------------|-------------------|
| "Check date field type" | "Validate ambiguous types before operations" |
| "Verify C3 sum" | "Components must reconcile to totals" |
| "Fix column R reference" | "Cross-module dependencies must be tested" |

---

## Prevention Principles

**This is the single source of truth for these principles.** All other files reference here.

When a bug escapes, identify which principle was violated:

| # | Principle | Meaning | Violations Produce |
|---|-----------|---------|-------------------|
| 1 | **Explicit Contracts** | Module dependencies must be documented and tested | Cross-reference drift, broken links |
| 2 | **Single Source of Truth** | Every concept defined in exactly one place. This includes constants, algorithms, keyword lists, regex patterns, and classification rules. Any concept implemented independently in multiple locations WILL drift | Terminology drift, inconsistent values, satellite state, code duplication |
| 3 | **Existence Implies Usage** | Everything that exists must be used | Dead code, unused parameters |
| 4 | **Invariants Must Be Tested** | If you can state it in English, it must be a test | All bugs tests "should have caught" |
| 5 | **Structure Implies Content** | If structure exists, it must contain data | Hollow outputs, blank fields |
| 6 | **Verify Before Trust** | Claims from external sources must be re-verified. Internal assumptions used in calculations must be validated against empirical data when data exists | Stale data, wrong assumptions, unvalidated constants |
| 7 | **Proactive Detection** | Tests must detect bug classes, not just instances | Satellite state, stale logic |
| 8 | **Defenses Must Be Operational** | Every validation, filter, gate, or constraint must actually perform its function with real data. A defense operating on null/empty inputs is structurally equivalent to no defense | Silent filter bypass, inert gates, hollow validation |
| 9 | **Findings Must Be Tracked** | Every review finding, identified issue, or deferred improvement must become a tracked item (BACKLOG.md entry or BUG_PATTERNS.md entry) before the review is considered complete. Narrative findings that exist only in conversation or agent output do not survive context compaction and WILL be forgotten | Identified-but-forgotten issues, repeated rediscovery |
| 10 | **Scaffold Before Building** | Module boundaries, config structure, test framework, and domain-specific FGT files must exist before the first feature. Retroactive methodology adoption is significantly less effective. Cargo-culting files from another project is an anti-pattern — each project's domain files must be written from scratch | Retroactive rework, cargo-culted methodology, empty logs |

Before writing any calculation that derives from shared data, ask:
does a source of truth already compute this? (USE it) Is there a named
constant? (REFERENCE it) Am I duplicating logic? (IMPORT it)

**Zero-Result Sentinel (Principle 8 extension):** A data source that previously returned N>0 results now returning 0 is a WARNING, not a success. Absence is a signal, not a safe default. This applies to any function that retrieves data from an external source — scrapers, API calls, database queries, file reads. Implementation: track `last_result_count` per source; if prior count > threshold and current count is 0, emit WARNING and do not treat upstream data as stale.

---

## Test Categories

| Category | Purpose | Naming |
|----------|---------|--------|
| **Invariant** | Domain rules that always hold | `INV-001` |
| **Contract** | Cross-module dependencies hold | `CONTRACT-001` |
| **Sensitivity** | Parameters affect outputs | `SENS-001` |
| **Evaluation** | Formula/algorithm logic correct | `EVAL-001` |
| **Boundary** | Edge cases handled | `BOUND-001` |
| **Schema** | Structure valid | `SCHEMA-001` |
| **Proactive** | Bug classes detected before manifestation | `PRO-001` |
| **Cross-Validation** | Source-of-truth matches presentation | `XVAL-001` |
| **Output Quality** | Output values are correct, not just computed | `QUAL-001` |
| **Integration** | End-to-end flow works | `INT-001` |
| **Expert Review** | Domain stakeholder perspective tests | `REV-001` |
| **Preventive Measure** | Targeted recurrence prevention | `PM-001` |
| **Quality Gate** | Presentation/content compliance rules | `QG-001` |

**Key distinctions:**

- **Regression tests** catch recurrence of known bugs
- **Proactive tests** (PRO-\*) scan for structural anti-patterns that indicate an entire class of bugs, even before a specific instance is reported
- **Cross-validation tests** (XVAL-\*) verify that displayed/presented values match the authoritative computation
- **Output quality tests** (QUAL-\*) verify the actual values users see are correct — not that the pipeline ran, but that the numbers are right. Prefer data-driven assertions (output within range of its own input data) over hardcoded expected values
- **Expert Review tests** (REV-\*) encode specific domain stakeholder perspectives (e.g., investor, legal counsel, auditor, lender, QA) as automated test classes. Each class asks: "What would this expert reject?"
- **Preventive Measure tests** (PM-\*) target specific recurring bug patterns with narrow, focused tests (engine plumbing, static text vs config drift, formatting edge cases)
- **Quality Gate tests** (QG-\*) enforce content compliance for user-facing outputs (no unsourced claims, no deprecated terminology, required disclaimers, format consistency)

**Choosing between overlapping categories:**

| If your test... | Use | Not |
|-----------------|-----|-----|
| Scans code structure (AST, file contents, naming) for an anti-pattern | `PRO-*` | `PM-*` |
| Validates runtime behavior against a specific known failure mode | `PM-*` | `PRO-*` |
| Checks a rule from a written standard or regulation | `QG-*` | `REV-*` |
| Embodies a specific expert's judgment or perspective | `REV-*` | `QG-*` |
| Verifies a displayed value matches its authoritative source | `XVAL-*` | `QUAL-*` |
| Verifies an output value is plausible/correct (no authoritative source) | `QUAL-*` | `XVAL-*` |

---

## Enforcement Planes

Not every principle maps to a CI test. FGT recognizes three enforcement planes:

| Plane | Mechanism | Catches | Example |
|-------|-----------|---------|---------|
| **CI** | Tests that block merge | Code bugs, structural anti-patterns | PRO-\*, INV-\*, XVAL-\*, QUAL-\* |
| **Hooks** | Session/commit hooks that block action | Process failures, memory staleness | Stop hook (Principle 9), pre-commit (version bump) |
| **Gates** | Runtime guards that suppress bad output | Data quality issues in production | Value-range checks, anomaly detection |

Each principle should have enforcement on at least one plane. If a principle
has no enforcement, it is aspirational — and aspirational principles fail
(Insight #2).

For data quality, in-pipeline gates that suppress bad data BEFORE it reaches
users are more valuable than tests that detect bad data AFTER it's been
displayed. Gates run IN the pipeline; tests run AFTER. Use both, but
prioritize gates for user-facing data.

**Bulk Operation Safety Gates:** Any batch operation that modifies stored data (revalidation, cleanup, migration, dedup) must include a circuit breaker. If the operation would change >50% of affected records with total records >50, abort and require explicit confirmation. This prevents catastrophic data corruption when a logic bug in a maintenance script runs unchecked against the full dataset.

### Enforcement Reliability Ranking

The three planes above describe *where* enforcement happens. This ranking describes *how reliable* each mechanism is — prefer stronger enforcement when feasible:

1. **Documentation** ("you should...") — routinely ignored
2. **Scripts** (exist but require voluntary execution) — inconsistently run
3. **Pre-commit hooks** (auto-run but bypassable with `--no-verify`)
4. **CI checks** (catch after push, but multiple bad commits possible before catch)
5. **Branch protection** (structurally blocks merge until CI passes — cannot bypass)

Start at the highest enforcement level feasible for each principle. Don't rely on weaker mechanisms when stronger ones are available.

---

## CI Enforcement

> **If it can be skipped, it will be skipped.**

Everything critical goes in CI. Essential steps:

1. Install dependencies
2. Run linter
3. Run all tests (invariant, contract, proactive, cross-validation, integration)
4. Build output artifacts
5. Validate output

Merge blocked until CI passes. No exceptions.

---

## Backlog Tracking

> **If it's not in BACKLOG.md, it doesn't exist.**

Every project must maintain a `BACKLOG.md` file as the single source of truth for outstanding work.
See [templates/BACKLOG_TEMPLATE.md](templates/BACKLOG_TEMPLATE.md) for the starting template.

**What goes in BACKLOG.md:**
- Every expert review finding (bugs → BUG_PATTERNS.md, improvements → BACKLOG.md)
- Every deferred user request
- Every identified-but-not-yet-fixed issue
- Every "we should also..." observation from code changes

**When to update:**
- After every expert review: all findings must be tracked BEFORE declaring the review complete
- After every bug fix: check if the fix creates new backlog items (e.g., "revalidate existing data")
- After every data migration/backfill: add "verify migrated data consistency" item
- Before declaring "nothing needs to be done": READ BACKLOG.md first

**When answering "what else needs to be done?":**
1. Read BACKLOG.md
2. Read BUG_PATTERNS.md for any "Needs:" entries
3. Run tests
4. Only THEN answer — never rely on recall alone

---

## Expert Review Protocol

When conducting expert reviews (data engineering, architecture, security, etc.):

1. **Findings are not complete until tracked.** Every finding → BACKLOG.md or BUG_PATTERNS.md entry
2. **Reviews must produce testable assertions.** "The backfill has no revalidation" → add a test that fails if stale data exists
3. **Deferred findings must have a reason.** Don't just "note for later" — record WHY it's deferred and WHAT would trigger action
4. **Re-audit after major changes.** After any migration, backfill, or matcher change, re-read the review findings and verify they're still addressed

---

## Heuristic Complexity Review

**Trigger:** A heuristic, rule, or pattern-matching function has been modified 3+ times.

When triggered, ask three questions:

1. **Is the accumulated complexity justified?** Measure the improvement the current version provides over the simplest possible version. If the improvement is marginal, the complexity is not justified.
2. **Would a fundamentally different approach be simpler?** A regex chain modified 5 times may be better replaced by a lookup table. A scoring function patched repeatedly may need a different algorithm.
3. **Should we revert to the cruder-but-robust version?** Sometimes the simple heuristic that is wrong 5% of the time is better than the complex one that is wrong 2% of the time but breaks unpredictably.

This is a process check, not a code review. The goal is to catch heuristics that have accumulated accidental complexity through incremental patches.

---

## Session Protocol (AI-Assisted Development)

AI assistants have finite context windows. Long sessions trigger compaction, which silently
drops decisions, bug fixes, and domain knowledge. Without explicit persistence, the same
mistakes recur across sessions.

**At session end / before context compaction:**
1. Persist learnings — update project files with decisions, bug fixes, patterns
2. Verify metrics — don't write stale counts; re-check actual values
3. Update BACKLOG.md — ensure all open items are tracked

**At session start:**
1. Load context — read memory/FGT files before acting
2. Read BACKLOG.md — understand what's outstanding
3. Verify state — run tests, check build. Never trust "it was passing before"

**Before every commit:**
1. Run ALL tests — never trust stale results
2. Run full build

**Before declaring "done" or "nothing needs to be done":**
1. Read BACKLOG.md — are there open items?
2. Read BUG_PATTERNS.md — any "Needs:" entries?
3. Spot-check the viewer — are there obviously wrong values displayed?
4. Only then declare done

This is not optional overhead. In real-world use, failing to persist led to:
- Committing 38 files without running tests (trusted stale context)
- Documentation drifting days behind code changes
- Test counts in docs drifting 150+ behind actual

---

## Methodology Evolution

FGT improves at two levels: bugs add tests, and patterns of bugs may reveal new principles.

After 3+ bugs that don't clearly map to existing principles, ask whether a principle
is missing, too broad, or should be split/merged. Update this file if so.

> **FGT follows FGT.** When bugs escape that FGT should have prevented, ask not just
> "what test is missing?" but "what principle is missing?"

See [METHODOLOGY_LOG.md](METHODOLOGY_LOG.md) for the history of principle additions
and the specific bugs that motivated them.

---

## File Organization

| File | Purpose |
|------|---------|
| `FGT.md` | Methodology and principles (this file — single source of truth) |
| `FGT_DOMAIN_*.md` | Domain-specific knowledge and invariants |
| `BUG_PATTERNS.md` | Bug catalog referencing principles above |
| `BACKLOG.md` | Outstanding work items — the single source of truth for "what needs to be done" |
| `METHODOLOGY_LOG.md` | History of principle additions and the bugs that motivated them |
| `.github/workflows/verify.yml` | CI enforcement |

---

## Quick Reference

```text
Bug Response:
1. FIX         → Resolve the specific problem
2. ABSTRACT    → Which principle was violated? What CLASS of bug?
3. DOCUMENT    → Add BUG-XXX to BUG_PATTERNS.md
4. PREVENT     → Add test that catches the CLASS
5. SEARCH      → Grep for siblings in CODE
6. REVALIDATE  → Check if existing DATA is contaminated
7. PERSIST     → Update memory/docs

Prevention Principles:
  1. Explicit Contracts      6. Verify Before Trust
  2. Single Source of Truth   7. Proactive Detection
  3. Existence Implies Usage  8. Defenses Must Be Operational
  4. Invariants Must Be Tested 9. Findings Must Be Tracked
  5. Structure Implies Content 10. Scaffold Before Building

Enforcement Planes:
  CI    → Tests block merge (PRO-*, INV-*, XVAL-*, QUAL-*)
  Hooks → Session/commit hooks block action (Principle 9)
  Gates → Runtime guards suppress bad output
  Ranking: Documentation < Scripts < Hooks < CI < Branch Protection

Expert Review:
1. REVIEW      → Conduct the review
2. TRACK       → Every finding → BACKLOG.md or BUG_PATTERNS.md
3. VERIFY      → Review is not complete until all findings are tracked

Heuristic Review (3+ modifications):
  Is complexity justified? Different approach simpler? Revert to crude?

Test Prefixes:
  INV-*  CONTRACT-*  SENS-*  EVAL-*  BOUND-*
  SCHEMA-*  PRO-*  XVAL-*  QUAL-*  INT-*
  REV-*  PM-*  QG-*

Session Protocol (AI-Assisted):
  End    → Persist learnings, update BACKLOG.md
  Start  → Load context, read BACKLOG.md, verify state
  Commit → Run ALL tests first
```
