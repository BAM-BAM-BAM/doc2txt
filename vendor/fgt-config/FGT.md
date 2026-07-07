# Francis Galton Technique (FGT)

> **Every escaped bug triggers a process improvement that becomes an automated enforcement.**

Three insights:

1. **Bugs that escape to users are process failures** — fix both the bug and the process
2. **Documentation gets skipped** — automation enforces what docs only recommend
3. **Automation is the only reliable enforcement** — voluntary compliance fails

**FGT is domain-agnostic.** Domain-specific knowledge goes in `FGT_DOMAIN_*.md` files.

---

## Bug Abstraction Protocol

**Data reports are bug reports, not patches.** When a user reports incorrect data ("event X has wrong city", "score is wrong"), the correct response is this protocol — not a raw database UPDATE. The data correction is step 1 of 7, not the whole fix. Raw patches bypass every enforcement plane (pre-commit, CI, Stop hook) because no code changes and no commit happens.

**Source:** `~/.claude/projects/-home-jprior-projects-infinevent/memory/feedback_data_issue_is_bug.md` (originSessionId: 5821ac77-2a9e-4573-8044-a2cc6446ca0b)

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

## Design Abstraction Protocol

**Designs are NOT bug fixes.** The Bug Abstraction Protocol fires when something is broken and a fix is being patched. The Design Abstraction Protocol fires when something is being **proposed** — a new feature, a new knob, a new table, an architectural choice, a refactor, or any response to "what should we do about X?" Designs have the same vulnerability to surface-matching pattern-completion as bugs — but no enforcement plane historically catches it, so design output is the most common shape for unscalable "instance-fix-disguised-as-design" proposals.

**Source:** av226 session 1c5bdc02-... (2026-05-17, "interest reserve / DS buffer" design question — first proposal pattern-matched the surface form of the user's question; only reached a sustainable design after three rounds of user pushback).

When proposing ANY design / fix / new knob / new table / new sheet / new abstraction / architecture sketch, run ALL steps in order before producing the proposal:

1. **RESTATE** — write the user's literal question verbatim in scratch. Often the question's surface form (a specific noun like "DS buffer", "rounding bug", "merge conflict") is doing all the heavy lifting in your brain; restating breaks the spell.

2. **CLASSIFY** — what general class of problem is this an instance of? Examples:
   - "Missing reserve" → class: *"model silently absorbs an invariant violation"*
   - "Rounding bug" → class: *"numerical-precision boundary mishandled"*
   - "Merge conflict" → class: *"concurrent-edit divergence on shared resource"*
   - "Slow query" → class: *"unindexed access pattern at scale"*

   If you can't name a class without using the same nouns as the user's question, you haven't classified — you've paraphrased. Classify *up* one level of abstraction at minimum.

3. **DIMENSIONS** — list the orthogonal answer-surfaces. A design question typically has 2-4 dimensions:
   - **Mechanism**: economic / presentational / detection / disclosure
   - **Funding/ownership**: who pays / who owns / who triggers
   - **Surface**: cfg knob / sheet display / sweep gate / PDF / log / sheet / dashboard
   - **Scope**: instance-fix / class-fix / framework

   Write the dimensions out. The most common design failure is collapsing dimensions — proposing options that all live on the same dimension X without naming the missing dimensions Y, Z.

4. **DESIGN-AT-CLASS** — propose at least one option that addresses the CLASS, not just the instance. If you cannot, the class was misidentified in step 2; go back. A class-level option might be a framework, a generic surface, a registration API, an invariant tracker — something that absorbs the next N similar problems for free.

5. **SUSTAINABILITY CHECK** — ask in scratch:
   - *"If 10 of these existed in 6 months, does this proposal still hold up?"*
   - *"Does the proposal scale linearly with N (e.g., N cfg knobs for N gaps) or logarithmically (one framework absorbs all N)?"*
   - *"What's the marginal cost of the 11th instance? If high → the proposal is pattern-matching disguised as design."*

   This is the single highest-leverage check. Most design failures fail here, not earlier.

6. **INSTANCE-FIX** — only after steps 1-5, derive the specific instance fix as a *specialization* of the class fix. If the instance fix doesn't actually leverage the class abstraction, you've reverted to pattern-matching.

**Skip cases** (protocol does NOT fire on):

- Typo / one-line bug fixes
- Implementation of an already-approved plan (no new design happening)
- Pure factoid / lookup answers
- Trivial reformatting / renames
- Bug fixes covered by the Bug Abstraction Protocol (use that protocol instead — it has its own class-abstraction step at step 2)

**Enforcement planes**:
- `~/.claude/patterns/SELF_CRITIQUE.md` check #10 (PATTERN-MATCH-vs-CLASS) flags responses lacking visible CLASSIFY + SUSTAINABILITY evidence
- Project sweep scripts detect *artifacts* of skipping the protocol (e.g., av226 `_av_check_cfg_proliferation` flags 2+ similarly-named cfg knobs added in one branch)
- CLAUDE.md skepticism-cue rule cross-links to this protocol — user pushback ("is this sustainable?") forces re-running from step 2

**Sustainability heuristic — N-instance proliferation**:

When a branch / PR / proposal adds N similar new fields, classes, configs, tables, or branches (N ≥ 2 sharing a substring or pattern), treat that as a *signal that one abstraction is missing*, not as N independent changes. The cheap detection: at PR-review time, count new fields with shared suffixes (e.g., `cfg_*Reserve`, `Foo*Handler`, `*_threshold`). If N ≥ 2, the reviewer (human or sweep gate) asks: *"is this N instances of one abstraction missing?"* The author either justifies the proliferation (per-scenario knobs, per-class allocations — legitimate) or refactors to the underlying abstraction.

The principle is naming-convention-independent; each project implements it with its own field-naming pattern.

---

## Prevention Principles

**This is the single source of truth for these principles.** All other files reference here.

The principles factor into a 4-tier hierarchy:

- one **meta-rule** that constrains every addition (`JUSTIFY-KEEP`)
- one **core thesis** with four nested invariant classes (`INVARIANT-TESTED` containing `EXPLICIT-CONTRACT`, `STRUCTURE-CONTENT`, `VERIFY-TRUST`, `SCAFFOLD-FIRST`)
- two **quality criteria** about how tests are written (`PROACTIVE-DETECT`, `DEFENSE-OPS`)
- three **orthogonal concerns** not shaped like tests (`SSOT`, `EXISTS-USED`, `FINDINGS-TRACKED`)

**Reference principles by slug** in new code, prose, and BUG_PATTERNS entries. Slugs are position-independent and won't break under future restructures. Numeric IDs (`P5`, `Principle 11`) remain valid as legacy anchors via the Legacy Numeric IDs table at the end of this section.

### Meta-rule (constrains every addition below)

| Slug | Principle | Meaning | Violations Produce |
|---|---|---|---|
| `JUSTIFY-KEEP` | **Every Addition Must Justify Its Keep** | Before adding any test, gate, hook, sweep stanza, template, or doc, state: (a) the ≥2 observed instances that justify it, (b) an honest estimate of its ongoing maintenance cost, and (c) an **observable** sunsetting condition that would justify removing it — a runnable check (grep / count / file existence / query), *not* prose like "eventually" or "when fewer instances." "Retire when the lint has been clean for N months" is the canonical bad form because it's the rule succeeding, not becoming unnecessary; the test of a good condition is that it names what would make the underlying bug class impossible (e.g., "retire when the `report_curation` table is dropped"), not that the guard kept working. A check that has never fired in 6+ months is a candidate for removal, not a badge of prevention. This principle constrains all others | Orphaned templates, ceremonial tests, unused hooks, "just-in-case" gates, documentation sprawl that rots faster than it's read |

**`JUSTIFY-KEEP` is a meta-principle: every artifact demanded by the principles below must also pass `JUSTIFY-KEEP`'s test.** Without it, a bug-prevention methodology accretes ceremony faster than it removes bugs. When you're about to add machinery, ask: have I seen this class ≥2 times across projects? What's the ongoing cost? Under what evidence would I remove this later? If you can't answer, the addition isn't justified yet — file the single observed instance as a PRO-\* / BOUND-\* in its home project and wait for the class to recur. The existing Heuristic Complexity Review (see below) applies the same logic retroactively; `JUSTIFY-KEEP` is the prospective generalization.

### The Core: Invariants Must Be Tested

The single load-bearing TDD claim, plus four specific invariant classes that have escaped repeatedly across projects.

| Slug | Principle | Meaning | Violations Produce |
|---|---|---|---|
| `INVARIANT-TESTED` | **Invariants Must Be Tested** | If you can state it in English, it must be a test | All bugs tests "should have caught" |
| `EXPLICIT-CONTRACT` | **Explicit Contracts** | Module dependencies must be documented and tested | Cross-reference drift, broken links |
| `STRUCTURE-CONTENT` | **Structure Implies Content** | If structure exists, it must contain data | Hollow outputs, blank fields |
| `VERIFY-TRUST` | **Verify Before Trust** | Claims from external sources must be re-verified. Internal assumptions used in calculations must be validated against empirical data when data exists | Stale data, wrong assumptions, unvalidated constants |
| `SCAFFOLD-FIRST` | **Scaffold Before Building** | Module boundaries, config structure, test framework, and domain-specific FGT files must exist before the first feature. Retroactive methodology adoption is significantly less effective. Cargo-culting files from another project is an anti-pattern — each project's domain files must be written from scratch. **Cross-process/subprocess integrations specifically:** the scaffold MUST include a real-binary integration test (XREAL-\*) AND a fixture captured from the real system — hand-composed fixtures test beliefs, not the system. See CP-013b | Retroactive rework, cargo-culted methodology, empty logs, consumer contracts that drift from reality silently |

Before writing any calculation that derives from shared data, ask:
does a source of truth already compute this? (USE it) Is there a named
constant? (REFERENCE it) Am I duplicating logic? (IMPORT it)

**Conservation Invariant (`INVARIANT-TESTED` design-time prompt):** Countable quantities — currency, percentages, identities, references, status flags, action items — must be preserved across every operation that consumes them. Two failure modes: *double-counting* (one value participates in 2+ subtractions/allocations — e.g., cost basis subtracted in two waterfall steps) and *zero-counting* (one value silently absent from a sum that should include it — e.g., a member excluded by subset renormalization to 100%). `INVARIANT-TESTED` ("invariants must be tested") states the obligation; this extension names the design-time prompt. Whenever you write a sum, distribution, allocation, identity rename, or reference handoff, write the conservation invariant test BEFORE the implementation: "what value should equal what other value?", "which identities must appear in the sum?", "which references must remain valid?". The 8 T3 bug classes (BUG-001 through BUG-008 in `tierras/CHANGELOG.md`) and the 8 T1 prevention entries (`tierras/t1/BUG_PATTERNS_T1.md` commit e86070e) are direct evidence that `INVARIANT-TESTED` alone — without this design-time prompt — fails to surface conservation invariants until after the bug ships. See CP-027 evidence in `fgt_cross_project_retrospective_v2.md`.

**Cross-Process Vocabulary (`EXPLICIT-CONTRACT` design-time architectural rule):** A string value that crosses a process boundary (RPC payload, CLI stdout, queue row, file format) with a known-finite set of valid values WILL drift silently unless it is a typed enum. The cost is silent data loss: producer writes value A, consumer filters on value B, filter matches nothing, no error is raised. Implementation: the producer promotes such vocabularies to `StrEnum` / string-literal-union, re-exports via a versioned contract module (`producer.contract.v1`) with a `SCHEMA_VERSION` constant, and *owns the typed client wrapper* — it lives in the producer repo so the producer's tests cover both sides of its own contract. During migration, consumers can rely on alias-on-read for one release. See `templates/PATTERNS_TEMPLATE.md § Cross-Process Vocabulary` and CP-013 evidence in `fgt_cross_project_retrospective_v2.md`.

### Test-quality criteria (rules about how tests are written)

| Slug | Principle | Meaning | Violations Produce |
|---|---|---|---|
| `PROACTIVE-DETECT` | **Proactive Detection** | Tests must detect bug classes, not just instances | Satellite state, stale logic |
| `DEFENSE-OPS` | **Defenses Must Be Operational** | Every validation, filter, gate, or constraint must actually perform its function with real data. A defense operating on null/empty inputs is structurally equivalent to no defense | Silent filter bypass, inert gates, hollow validation |

**Zero-Result Sentinel (`DEFENSE-OPS` runtime gate):** A data source that previously returned N>0 results now returning 0 is a WARNING, not a success. Absence is a signal, not a safe default. This applies to any function that retrieves data from an external source — scrapers, API calls, database queries, file reads. Implementation: track `last_result_count` per source; if prior count > threshold and current count is 0, emit WARNING and do not treat upstream data as stale.

### Orthogonal concerns (not testing-shaped)

These detect drift after the fact rather than enforce a property at write time.

| Slug | Principle | Meaning | Violations Produce |
|---|---|---|---|
| `SSOT` | **Single Source of Truth** | Every concept defined in exactly one place. This includes constants, algorithms, keyword lists, regex patterns, and classification rules. Any concept implemented independently in multiple locations WILL drift | Terminology drift, inconsistent values, satellite state, code duplication |
| `EXISTS-USED` | **Existence Implies Usage** | Everything that exists must be used. Applies to code AND persisted data: a database column, file field, or config key whose write sites exist but whose read sites are zero is dead data — same principle, different surface | Dead code, unused parameters, write-only DB columns, unread export fields, config keys with no consumer |
| `FINDINGS-TRACKED` | **Findings Must Be Tracked** | Every review finding, identified issue, or deferred improvement must become a tracked item (BACKLOG.md entry or BUG_PATTERNS.md entry) before the review is considered complete. Narrative findings that exist only in conversation or agent output do not survive context compaction and WILL be forgotten | Identified-but-forgotten issues, repeated rediscovery |

### Legacy Numeric IDs

Older code, prose, BUG_PATTERNS entries, sweep stanzas, and CHANGELOG entries reference principles by ordinal number. Those IDs continue to resolve via this table. **New references should use slugs**, not numbers — slugs are position-independent and won't break under future restructures.

| Numeric | Slug |
|---|---|
| P1 | `JUSTIFY-KEEP` |
| P2 | `EXPLICIT-CONTRACT` |
| P3 | `SSOT` |
| P4 | `EXISTS-USED` |
| P5 | `INVARIANT-TESTED` |
| P6 | `STRUCTURE-CONTENT` |
| P7 | `VERIFY-TRUST` |
| P8 | `PROACTIVE-DETECT` |
| P9 | `DEFENSE-OPS` |
| P10 | `FINDINGS-TRACKED` |
| P11 | `SCAFFOLD-FIRST` |

**Sunsetting condition for the numeric ID system** (per `JUSTIFY-KEEP`): the numeric IDs retire when `grep -rE '\b(P[0-9]+|Principle [0-9]+)\b' ~/projects/ ~/.claude/` returns 0 hits — observable, not calendar-based. Likely never reaches 0 (CHANGELOG entries are historical), so this table is a permanent compatibility appendix. Acceptable: 11 rows, self-contained.

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
| **Real-Integration** | Cross-process/subprocess exercises real external system (not mocks) | `XREAL-001` |
| **Expert Review** | Domain stakeholder perspective tests | `REV-001` |
| **Preventive Measure** | Targeted recurrence prevention | `PM-001` |
| **Quality Gate** | Presentation/content compliance rules | `QG-001` |
| **Security** | Invariants that defend confidentiality, integrity, or availability against classes observed ≥2× across projects | `SEC-<OWASP-TOP10>-<NNN>` e.g. `SEC-A02-001` |

**Security category promotion rule (operationalizes Principle 1):** A test becomes `SEC-*` only after the bug class has been observed in ≥2 projects. Single-instance security issues are filed as `PRO-*` / `BOUND-*` in their home project and referenced by a row in `fgt_cross_project_retrospective_v2.md`. This prevents taxonomy-first design and keeps `SEC-*` load-bearing rather than aspirational. Naming follows OWASP Top 10 (A01…A10) where a category applies; otherwise `SEC-GEN-*`.

**Key distinctions:**

- **Regression tests** catch recurrence of known bugs
- **Proactive tests** (PRO-\*) scan for structural anti-patterns that indicate an entire class of bugs, even before a specific instance is reported
- **Cross-validation tests** (XVAL-\*) verify that displayed/presented values match the authoritative computation
- **Output quality tests** (QUAL-\*) verify the actual values users see are correct — not that the pipeline ran, but that the numbers are right. Prefer data-driven assertions (output within range of its own input data) over hardcoded expected values
- **Expert Review tests** (REV-\*) encode specific domain stakeholder perspectives (e.g., investor, legal counsel, auditor, lender, QA) as automated test classes. Each class asks: "What would this expert reject?"
- **Preventive Measure tests** (PM-\*) target specific recurring bug patterns with narrow, focused tests (engine plumbing, static text vs config drift, formatting edge cases)
- **Quality Gate tests** (QG-\*) enforce content compliance for user-facing outputs (no unsourced claims, no deprecated terminology, required disclaimers, format consistency)
- **Real-Integration tests** (XREAL-\*) exercise the real external binary/API/process — never a mock. Fixtures must be captured from the real system (see CP-013b and `~/.claude/patterns/CROSS_PROCESS_INTEGRATION.md`). Unit tests with hand-composed fixtures test beliefs about the system; only XREAL tests test the system

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

Not every principle maps to a CI test. FGT recognizes the following enforcement planes:

| Plane | Mechanism | Catches | Example |
|-------|-----------|---------|---------|
| **CI** | Tests that block merge | Code bugs, structural anti-patterns | PRO-\*, INV-\*, XVAL-\*, QUAL-\* |
| **Hooks** | Session/commit hooks that block action | Process failures, memory staleness | Stop hook (Principle 10), pre-commit (version bump) |
| **Gates** | Runtime guards that suppress bad output | Data quality issues in production | Value-range checks, anomaly detection |
| **OCD** | Session sweep that blocks close-out | Operational gaps: dead processes, stale data, uncommitted work, unfinished BACKLOG items | Stop hook → `ocd-sweep.sh` |

Each principle should have enforcement on at least one plane. If a principle
has no enforcement, it is aspirational — and aspirational principles fail
(Insight #2).

For data quality, in-pipeline gates that suppress bad data BEFORE it reaches
users are more valuable than tests that detect bad data AFTER it's been
displayed. Gates run IN the pipeline; tests run AFTER. Use both, but
prioritize gates for user-facing data.

**Bulk Operation Safety Gates:** Any batch operation that modifies stored data (revalidation, cleanup, migration, dedup) must include a circuit breaker. If the operation would change >50% of affected records with total records >50, abort and require explicit confirmation. This prevents catastrophic data corruption when a logic bug in a maintenance script runs unchecked against the full dataset.

### Enforcement Reliability Ranking

The planes above describe *where* enforcement happens. This ranking describes *how reliable* each mechanism is — prefer stronger enforcement when feasible:

1. **Documentation** ("you should...") — routinely ignored
1b. **Context-loaded protocol + on-demand review** — rule injected into every session's context; reviewer invoked for major analytical deliverables. Measured 2026-06-10 (transcript audit): 454 cpd-reviewer invocations over 3 weeks, 50% FAIL rate, 118 FAIL→revise→PASS cycles; sampled FAILs include outcome-grade pre-emission catches (cleartext credential, unverified external-system claims). Demonstrates discrimination and forced verification; net effect on final decision quality unmeasured. The per-turn Stop-hook gate that enforced invocation was retired 2026-07-02: >90% of its 478 logged events (85% from the long-horizon production projects) were false positives on execution reports; artifacts archived in `~/.claude/archive/cpd-gate-retired-2026-07-02/`. Invocation is on-demand — stronger than plain docs, weaker than blocking hooks. Sunsetting: retire this row when `grep -l 'cpd-reviewer' ~/.claude/CLAUDE.md` returns nothing
2. **Scripts** (exist but require voluntary execution) — inconsistently run
3. **Pre-commit hooks** (auto-run but bypassable with `--no-verify`)
4. **CI checks** (catch after push, but multiple bad commits possible before catch)
5. **Branch protection** (structurally blocks merge until CI passes — cannot bypass)
6. **Session sweep** (runs at Stop; blocks agent response on FAIL findings — cannot bypass without killing the session)

Start at the highest enforcement level feasible for each principle. Don't rely on weaker mechanisms when stronger ones are available.

### Operational Completion Discipline (OCD)

FGT governs code correctness. OCD governs operational completeness —
the system being healthy after the code ships. Without OCD, an agent
can pass every test, commit, push, and declare "done" while the daemon
is dead, 184 events are unscored, and the BACKLOG has 5 items just
unblocked. Evidence: 4 "surprise surfacing" rounds in a single session.

**How it works:**

1. `scripts/ocd-sweep.sh` (canonical source: `fgt-config/scripts/`)
   runs generic checks (git state, BACKLOG) and sources project-specific
   checks from `<project>/scripts/sweep.sh` (process liveness, data
   health, queue depth).
2. The global Stop hook in `~/.claude/settings.json` calls
   `ocd-sweep.sh` automatically at every session end.
3. Output is `[PASS|WARN|FAIL] check — detail`. FAIL blocks the
   agent's response (exit 2). WARN is advisory.
4. The sweep **reports** but does not fix. The agent presents
   findings and recommends fix-now vs. defer. The user decides scope.

**FAIL semantics — reserve FAIL for agent-fixable state.** Because FAIL
blocks the agent's response, a check may only FAIL on conditions the
agent can resolve in-session (failing tests, drift, missing files, PII
in the tree). Conditions that resolve only by waiting on an external
system — in-flight CI, third-party outage, pending human action — must
be WARN: a FAIL on external state puts the Stop hook in a block loop the
user has to break manually. Evidence: two re_proforma incidents
(2026-05-17, ~13 identical "CI in_progress" replies; 2026-05-27,
FAIL-on-external-state loop ended only by user interrupt). Reference
implementation: re_proforma `scripts/sweep.sh` `_av_check_ci_matches_head`
— in-flight run → WARN, out-of-band auth failure → WARN, unpushed fix
queued → WARN, genuine test failure at HEAD → FAIL.

**Installation:** `bash fgt-config/scripts/install-ocd.sh` deploys
the runner + Stop hook globally. `new-project.sh` copies the
`SWEEP_TEMPLATE.sh` into each new project.

**Relationship to the cron watchdog:** OCD reports to the agent at
session boundaries. The watchdog (cron) restarts dead processes
between sessions. They don't overlap: OCD checks broader state
(git, BACKLOG, data) and surfaces it in the agent's context; the
watchdog is a silent auto-restarter.

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

When conducting expert reviews (data engineering, architecture, security, etc.). Finding-tracking discipline is `FINDINGS-TRACKED` + § Backlog Tracking — not restated here:

1. **Reviews must produce testable assertions.** "The backfill has no revalidation" → add a test that fails if stale data exists
2. **Deferred findings must have a reason.** Don't just "note for later" — record WHY it's deferred and WHAT would trigger action
3. **Re-audit after major changes.** After any migration, backfill, or matcher change, re-read the review findings and verify they're still addressed
4. **Stress-test for performative risk before approval.** Every plan proposal must name the specific past bug the proposed defense would have caught. If you cannot, do not build it. Registries, metadata, and coverage metrics that look complete but are never exercised at runtime are performative defenses. Usage gates (telemetry confirming the built thing is consumed) must precede infrastructure expansion — never the reverse. Metrics on user-curated golden sets are benchmark-gaming by construction; real golden sets come from logged query history.

**Source:** `~/.claude/projects/-home-jprior-projects-mentat-llm/memory/feedback_performative_risk.md` (originSessionId: 8c735128-a8bf-4c41-99c1-4d1673f8f02f)

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
4. If architectural decisions were made this session, update SPEC.md — decisions in conversation that aren't written to SPEC.md will be lost during compaction

**At session start:**
1. Load context — read memory/FGT files before acting
2. Read BACKLOG.md — understand what's outstanding
3. Verify state — run tests, check build. Never trust "it was passing before"

**Before every commit:**
1. Run ALL tests — never trust stale results
2. Run full build

**Before declaring "done" or "nothing needs to be done":** follow § Backlog Tracking "When answering 'what else needs to be done?'" (read BACKLOG.md + BUG_PATTERNS.md "Needs:", run tests), plus spot-check the viewer for obviously wrong displayed values

This is not optional overhead. In real-world use, failing to persist led to:
- Committing 38 files without running tests (trusted stale context)
- Documentation drifting days behind code changes
- Test counts in docs drifting 150+ behind actual

### Cross-Process Integrations

When the session's task involves a subprocess shell-out, an external API
client, or any "our code talks to another process" work (e.g., a CLI
sidecar, a headless browser, an LLM SDK), follow the Pre-Integration
Checklist before writing the first implementation line:

1. Install the external system locally.
2. Write the XREAL integration test first (`tests/test_<module>_integration.py`).
3. Capture a fixture from real system output — never hand-compose.
4. Only then write the implementation.

Full protocol, examples, and related design patterns (doctor-round-trip,
typed-enum exports, consumer-requirements docs): see
`~/.claude/patterns/CROSS_PROCESS_INTEGRATION.md`. Concrete reference
implementation: `infinevent/CLAUDE.md § Pre-Integration Checklist` and
`infinevent/tests/test_refiner_integration.py`. Cross-project evidence
for why this matters: CP-013b.

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

