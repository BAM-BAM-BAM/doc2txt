# FGT Methodology Evolution Log

History of principle additions, test category changes, and the specific bugs
that motivated them. The prescriptive methodology lives in [FGT.md](FGT.md);
this file is the evidence trail.

> **Numbering migration (2026-04-24):** Principle 1 "Every Addition Must Justify
> Its Keep" was inserted at position #1; original Principles 1–10 shifted to 2–11.
> Entries dated **on or before 2026-04-24** reference the pre-migration
> numbering (e.g., "Principle 8 added" refers to what is now Principle 9
> "Defenses Must Be Operational"). The mapping is monotonic: old N = new N+1
> for all N in 1..10. Entries AFTER 2026-04-24 use the new numbering.

---

## P4 Extension: Dead Persisted Data (2026-04-24)

Principle 4 "Existence Implies Usage" was reworded from *"Dead code, unused
parameters"* to *"Dead code, unused parameters, **dead persisted data
(columns, fields, or files that are written but have zero read sites)**"*.
CP-024 filed the precedent.

**Two observed instances** (Principle 1 `≥2` bar met):

1. **mentat_llm** — `conversations.raw_json` column (TEXT) written by
   ChatGPT/Claude/Grok parsers + `src/storage/database.py`. `grep -rn
   '\.raw_json' src/` returns two write-side hits and zero read sites.
   Cost: 1.3 GB of live SQLite, ~500 MB × 3 in rolling backup tarballs,
   plus privacy surface area (least-redacted form of user conversations
   kept speculatively). Surfaced while investigating why `data/` grew
   to 12 GB. Scrubbed 2026-04-24 — DB reclaimed 852 MB, `data/imports`
   shrank 1.2 GB → 217 MB (83.8 %).

2. **av226** — Excel columns with populated headers but blank data rows
   (`docs/BUG_PATTERNS.md` BUG-004, "Unused Columns - EM data rows blank").
   Same abstraction (scaffolded reader that never arrived), different
   surface (output-format column instead of DB column). The av226 entry
   already named Principle 4 as the violated principle, even though the
   principle's text at the time didn't technically cover output fields —
   evidence that practitioners read the principle's *spirit* but the
   wording was too narrow.

**Why the wording was inadequate:** static analysers (ruff, vulture,
TypeScript unused-var) catch dead code, but don't cross the code ↔
SQLite / code ↔ output-format boundary. A column written in Python and
read nowhere passes every static check because the Python write sites
*reference* it — the absence is on the far side of the storage layer.
Principle 4 aimed at the first half of that flow and missed the second.

**What this extension intentionally does NOT do:**

- Does not add a `COST-*` / `DENSITY-*` / `SIZE-*` test category. Two
  instances meet Principle 1's `≥2` bar for a *pattern*, not for a
  *category*. `SEC-*` was promoted only after the class appeared across
  ≥ 5 projects as part of a broader security surface; same bar applies
  here. PRO-NO-UNREAD-COLUMNS as a pattern (added to
  `templates/PATTERNS_TEMPLATE.md`) is the right grain; promote to a
  category only if a third instance appears.
- Does not add a "Complexity Has Weight" principle. The user framing
  ("complexity is the enemy") surfaced repeatedly this session.
  Principle 1 already encodes the governance side; the existing
  Heuristic Complexity Review trigger encodes the retroactive side.
  A new principle would duplicate both.
- Does not add a disk-growth / `du` sweep check. Disk cost is a lagging
  indicator — catches the symptom, not the cause. The cause is zero-reader
  columns / fields, which the PRO-* pattern catches mechanically at the
  commit plane. Enforcement hierarchy: CI > hooks > sweep > docs; the
  strongest-available plane gets this.

**Chose reference count as the enforced metric, not byte ratio.** Ref
count answers *"is this read at all?"*; byte ratio answers *"is what's
read proportional to what's stored?"*. Orthogonal properties. Ref count
is mechanical, language-agnostic, cheap, and catches the loud class —
both mentat_llm and av226 instances were zero-reader. Byte ratio needs
a domain-specific "useful" definition that drifts; right grain is a
diagnostic script (mentat_llm shipped `scripts/profile_storage.py`),
not a CI gate. If a project ever logs a referenced-but-oversized /
partial-read / sampled-read / redundant-parallel-reader instance, that
becomes a *separate second pattern* — not this one widened.

**Sunsetting condition:** if no project logs a dead-persisted-data
incident for 12 months from 2026-04-24, the Principle 4 extension wording
can be narrowed back to "dead code, unused parameters". The PRO-* pattern
in `PATTERNS_TEMPLATE.md` has its own sunsetting condition (project ships
a DB-schema lint that covers this class).

---

## P1 Addition: Every Addition Must Justify Its Keep (2026-04-24)

A security review across 14 projects surfaced 10+ findings. The tactical
fixes shipped cleanly. The proposal to codify the security-infra lessons,
however, went through three rounds of user-driven downscoping (6 items →
7 items after multi-POV critique → 3 items after "complexity is the enemy").

The meta-observation: FGT's ten original principles all *generate* machinery
(tests, hooks, gates, docs). None *constrain* that generation. Every past
methodology evolution increased surface area; no mechanism retired unused
surface. Existing "Heuristic Complexity Review" triggers retroactively
(3+ modifications) but doesn't gate initial additions.

**Evidence of drift in the portfolio:**
- 11 `*_TEMPLATE.md` files in `templates/`; none retired since inception.
- 10+ FGT-family markdown files per mature project (infinevent, mentat_llm).
- Pre-commit hooks 44–122 lines across 10 projects, significant content overlap.
- My own 6-item → 7-item → 3-item proposal trajectory — natural generation of
  speculative complexity until explicitly rejected twice.

**Response:** New Principle 1 "Every Addition Must Justify Its Keep." Meta-
principle: every artifact demanded by Principles 2–11 must also pass P1's
test (≥2 observed instances, honest ongoing-cost estimate, stated sunsetting
condition). Operationalization:
1. Bug Abstraction Protocol extended with step 5b ("state the sunsetting condition").
2. OCD sweep extended with stale-check detector (finds checks that haven't
   fired in 6+ months as removal candidates).
3. Existing Heuristic Complexity Review is the retrospective sibling; P1 is
   the prospective generalization.

**Falsification condition:** if the stale-check detector produces zero
removal candidates after 18 months of operation, P1 is ceremony — revisit
enforcement or retire the principle itself.

**Also added simultaneously:**
- `SEC-*` test category row with the same ≥2-instances promotion rule.
- `CP-021..023` in `fgt_cross_project_retrospective_v2.md` — the three
  security bug classes that cleared the ≥2 bar.
- `.env` 0600 assertion in `~/.claude/scripts/ocd-sweep.sh`.

---

## CP-013: Cross-Process String Vocabulary Drift (2026-04-16)

The claude-refiner ↔ infinevent/mentat_llm integration review (see
`claude-refiner/feedback/2026-04-15-infinevent-integration.md`) surfaced
a bug class that existing principles *named* (#1 Explicit Contracts, #2
Single Source of Truth) but did not *operationalize* for the specific
case of string vocabularies crossing a process boundary.

**Evidence:**
- G-STATUS: producer writes `status='succeeded'`; README examples said
  `'done'`. Consumer filter on `'done'` silently dropped every real
  result. Zero errors, zero logs, just missing data downstream.
- G8: `Result.external_ref` narrowly typed `str | None`. Consumers
  (infinevent, mentat_llm) with INTEGER primary keys submitted int
  `id` values; Pydantic validation crashed deep inside the worker
  instead of failing at the submit boundary. Crash loop, not refusal.
- G-PATTERN: same class repeated across `Result.status`, `Job.status`,
  `Result.backend`, future error-kind taxonomy. All stringly-typed,
  all a rename away from silent consumer breakage.
- Architectural: the mature typed wrapper lived inside the *consumer*
  (infinevent/`core/refiner_client.py`) rather than the producer. The
  second consumer (mentat_llm) couldn't import it and reinvented a
  weaker version — reaching directly into the producer's SQLite.

**What CP-011 covered, and what it didn't:** CP-011 (Canonical Data
Format Ambiguity) covered *same semantic value, multiple storage
representations* within one process (0.90 vs 90 vs "90%"). CP-013
covers the cross-process cousin: same vocabulary, no type binding the
producer's emission to the consumer's filter.

**Added:**
1. **Principle 1 extension** — "Cross-Process Vocabulary" sub-rule in
   FGT.md § Prevention Principles. Producer exposes `StrEnum` /
   string-literal-union for any known-finite string that crosses a
   boundary. Re-export from `producer.contract.v1` with a
   `SCHEMA_VERSION` constant. Producer owns the typed client wrapper.
   Alias-on-read for one release when migrating.
2. **`Cross-Process Vocabulary` pattern** added to
   `templates/PATTERNS_TEMPLATE.md` (four-step move with worked
   example).
3. **CP-013 entry** in `fgt_cross_project_retrospective_v2.md` with
   evidence and applicability table.
4. **Pre-Integration Checklist hook** (infinevent's CLAUDE.md pattern,
   inherited from NEB75 CP-006): before integrating against an
   external process API, verify the producer exposes a versioned
   typed-enum surface. If it does not, that's the first change to the
   producer, not the first line of consumer code.

**Confirmation:** claude-refiner PR #1 (`refiner/p0-p3-cross-process-contract`)
shipped all six findings (G4, G8, G-STATUS, G-PATTERN, G-DX-1, G-DX-2)
with a `claude_refiner.contract.v1` surface + producer-owned
`claude_refiner.client`. Tests: 92 passing (up from 64). CI: green.
Alias-on-read for `status='done'` → `'succeeded'` means existing
consumers needed zero code changes at the moment of release.

**Source:** `~/projects/claude-refiner/feedback/2026-04-15-infinevent-integration.md` (human-written integration review; predates the auto-memory convention)

---

## SPEC.md and Scope Alignment Automation (2026-04-12)

During bumbleup development, the user's intent evolved significantly (Bumble-only →
multi-platform with WhatsApp, IRL, identity resolution, dormant/wake sidebar) but
zero project files reflected the evolution. The user had to manually ask "review the
chats to find disconnects" — a process that should be automated.

**Root cause:** Architectural decisions live in conversation history, which gets
compacted. FGT's Session Protocol (Principle 9) requires tracking findings in
BACKLOG.md, but there was no mechanism to track *what the system should do* —
only *what needs fixing*. The gap: no spec artifact, no enforcement.

**Added:**
1. **SPEC\_TEMPLATE.md** — new template capturing system purpose, scope, architecture,
   core entities, workflows, platforms, privacy model. Added to Day 1 requirements.
2. **Stop hook CHECK 4** — warns when src/ files change without SPEC.md being updated.
   Lighter than scanning spec terms against code; enforces "did you check alignment?"
3. **Scope Alignment Review Triggers** — added to REVIEWS\_TEMPLATE.md: "requirements
   discussed in conversation → update SPEC.md" and "feature complete → audit SPEC.md
   vs code."
4. **Session Protocol step 4** — "if architectural decisions made, update SPEC.md."

**Evidence:** bumbleup had 10 critical disconnects between stated intent and project
files. All would have been caught by a SPEC.md that was kept in sync — the Stop hook
would have fired on every commit that changed src/ without updating SPEC.md.

---

## Effective vs Performative Review + Self-Audit (2026-04-12)

An external review assessed every FGT element as "effective," "performative," or "bloat."
8 recommendations were made: delete Principle 3, merge Principle 5 into 4+8, consolidate
13 test categories to 7, delete FGT\_LOG, delete module size enforcement, delete heuristic
complexity review, merge EXPERT\_REVIEWERS into FGT\_DOMAIN, and predict BACKLOG.md rot.

**Evidence-based fact-check refuted 6 of 8 recommendations:**

1. **Principle 3 retained.** av226 has 5 confirmed bugs (BUG-002, -003, -004, -007, -021)
   where parameters existed, were syntactically referenced, but had no calculation effect.
   This is *semantic* dead code that linters cannot catch — a parameter in a display formula
   is not the same as a parameter in a calculation.

2. **Principle 5 retained (distinct from 4+8).** Catches hollow structures (headers with
   blank data rows, class-specific PDFs with inherited combined data). Different bug class
   from Principle 4 (behavioral invariants) and Principle 8 (gates that fail-open).

3. **13 test categories retained.** XVAL has 10 bugs in av226, QG-001 caught BUG-005 in
   infinevent (72 contaminated rows), SENS has 3 bugs in av226. Prior disambiguation
   (2026-04-03) already resolved overlapping boundaries with clear decision criteria.
   Consolidation would lose the precision that guides developers to the right test type.

4. **FGT\_LOG retained.** infinevent: 19 active entries. NEB75: 15 entries with methodology
   evolution. Failure mode (doc2txt: empty for 24 commits) is prevented by Principle 10
   (Scaffold Before Building) which ensures FGT\_LOG is created Day 1.

5. **Heuristic Complexity Review retained.** doc2txt's `page_needs_ocr()` modified 7 times
   across 12 commits (CP-005), eventually reverted to simpler approach. Nakano\_crawler
   matcher: 1 function to 8-module package with 13 bugs. The pattern is real and recurring.

6. **BACKLOG.md not rotting.** infinevent: 121 lines, actively maintained with Process
   Triggers section. av226: 200+ lines. Both wired into Stop hooks. Load-bearing, not
   optional.

**2 recommendations accepted:**
- PATTERNS\_TEMPLATE.md framing improved (explicit "proactive design practices" framing)
- REVIEWS\_TEMPLATE.md extended with "Design Review Triggers" section (heuristic complexity,
  module growth, config drift — validated by CP-002, CP-005, CP-007, CP-011)

**Self-audit finding:** fgt-config itself violated 5 of its own principles:
- Principle 9: No BACKLOG.md (added)
- Principle 3: Dead templates never copied by new-project.sh (documented as intentionally optional)
- Principle 4: No integration test for new-project.sh (added: test-new-project.sh, 64 assertions)
- Principle 4: validate-templates.mjs didn't scan scaffold/\*.tmpl (extended)
- Principle 1: No CONTRACT test for principle references in templates (added to validate-fgt.mjs)

**Meta-lesson:** The review itself was performative — armchair reasoning without verifying
against the 94+ documented bugs. Every "delete this" recommendation assumed the element was
unused, but the evidence showed real bugs caught by every principle. The review's most
valuable contribution was not its recommendations but the self-audit it prompted.

---

## Cross-Project Retrospective (2026-04-05)

Analyzed 94+ bugs across 4 projects (nakano-crawler, av226, pdf2txt, NEB75).
12 cross-project patterns identified (CP-001 through CP-012).
See `fgt_cross_project_retrospective_v2.md` for the full analysis.

Key findings:

1. **CP-001 (Stale Data)** is the highest-cost pattern (9 occurrences in nakano-crawler alone).
   Bug Abstraction step 6 existed but lacked implementation guidance. Added: snapshot/safety-gate
   workflow, raw data retention guidance, REVALIDATION_TEMPLATE.

2. **CP-006 (Retroactive FGT)** confirmed across 3 projects. pdf2txt cargo-culted FGT files
   from another project. NEB75 built 58 features before any tests — 100% of voluntary processes
   were skipped. Added: Principle 10 (Scaffold Before Building).

3. **CP-011 (Canonical Data Format Ambiguity)** is new. NEB75 stored percentages 3 ways
   (0.90, 90, "90%"), causing a 9000% display bug. Watch crawler and pdf2txt had YAML type
   inference crashes. Added: Canonical Data Formats section in FGT_DOMAIN_TEMPLATE,
   Format Canonicalization pattern in PATTERNS_TEMPLATE.

4. **CP-012 (Enforcement Hierarchy Ranking)** is new. NEB75 empirically confirmed 100% skip
   rate for voluntary-only processes. Added: explicit Enforcement Reliability Ranking in
   Enforcement Planes section.

5. **CP-003 (Silent Failure / Hollow Defense)** extended Principle 8 with Zero-Result Sentinel:
   a data source returning 0 results after previously returning N>0 is a warning, not a success.

6. **CP-005 (Heuristic Complexity Creep)** — pdf2txt had a parsing heuristic modified 12 times.
   Added: Heuristic Complexity Review trigger (3+ modifications).

7. **CP-004 (Satellite State)** — investigation revealed FGT already covers it extensively
   (Principle 2, Provenance Registry, Satellite Elimination). Failures were CP-006 (methodology
   not applied). No changes needed.

8. **CP-010 (Bulk Operation Safety)** — nakano-crawler revalidation nearly deleted 54% of its
   database. Added: Bulk Operation Safety Gates (circuit breaker at >50% of >50 records).

9. **Error Collection pattern** added to PATTERNS_TEMPLATE from NEB75 evidence — collect all
   errors per pipeline run rather than fail-fast.

New templates: REVALIDATION_TEMPLATE, CONFIG_TEMPLATE, ENTITY_RESOLUTION_TEMPLATE.

---

## Learnings Promoted from nakano-crawler (2026-04-03)

53 bugs cataloged across a data pipeline project (web scraping, Bayesian modeling,
financial calculations). Key findings that changed FGT:

1. **Principle 8 added** — "Defenses Must Be Operational." Three separate bugs
   (BUG-032/040/042) followed the pattern: fix the code, leave 1,185 records
   processed by the old buggy logic sitting contaminated in the database.
   Standard testing didn't catch this because tests verify the new code path,
   not the existing data. Step 6 added to Bug Abstraction Protocol.

2. **Output Quality test category added** — The project had 561 tests but none
   caught a $1,855 estimate for a Rolex (actual market: $12,000). The ratio was
   ~350 plumbing tests to ~15 output quality tests. One test checking "is this
   estimate between p10 and p90 of its own observation data?" would have caught
   5 of the top 10 bugs.

3. **Gates vs Tests distinction added** — A pre-deployment invariant gate
   (suppresses estimates >5x the JP listing price) caught a bug in production
   that the equivalent test would only have caught on the next test run. For
   user-facing data, in-pipeline gates prevent harm; tests detect it afterward.

4. **Performative defense anti-pattern identified** — An assumption registry
   (15 entries with justification fields) and a feature pipeline registry
   (17 entries with status fields) both passed all tests while wrong data
   reached users. The tests checked metadata completeness ("does this entry
   have a justification?"), not runtime correctness ("is this assumption
   actually applied correctly?"). Before adding a defense mechanism, name
   the specific past bug it would have caught. If you cannot, do not build it.

5. **Warning without consequence is write-only logging** — Four separate
   mechanisms emitted warnings that nobody acted on. The fix was to either
   graduate the warning to a test failure or delete it. The middle ground of
   "warn but pass" serves nobody.

---

## Learnings Promoted from av226 (2026-03-25, 2026-04-03)

26 bugs cataloged across a financial modeling project (Excel generation, PDF
onepagers, Python engine). Key findings that changed FGT:

1. **Principle 9 added** — "Findings Must Be Tracked." An expert review identified
   issues that existed only in conversation. After context compaction, all were
   forgotten. BACKLOG.md is now mandatory.

2. **Expert Review test category added (REV-\*)** — 5 domain expert perspectives
   (LP Investor, Securities Counsel, Construction Lender, Auditor, QA Engineer)
   encoded as 35 automated tests. Catches semantic domain errors that no
   structural scan finds.

3. **Satellite Elimination pattern** — Making engine_result REQUIRED (ValueError
   if None) and deleting ~985 lines of fallback code eliminated an entire class
   of drift bugs. Not just "prefer engine" but "make satellite impossible."

4. **Tolerance Trap anti-pattern** — Generous test tolerances (300bps, 15%) hid
   canceling errors. Tightened to 20-50bps/0.1-2%. A test that cannot fail
   is not a test.

---

## Earlier Principle History

**Principle 2 was strengthened** after two rounds of code duplication consolidation
revealed that the original wording ("any value computed independently") was too narrow.
Round 1 (accessory_parser.py): 4 exact-duplicate helper functions across 3 files.
Round 2: 5 more violations — Japanese brand equivalents in 3 files,
normalise_text/normalise_ref in 2 files, sold markers in 2 files, known-brands lists
in 3 files. All were independently maintained copies that had already started to drift.
Principle 2 now explicitly covers constants, algorithms, keyword lists, regex patterns,
and classification rules.

**Bug Abstraction Protocol step 6 (Revalidate) was broadened** after "fix code, don't
fix data" occurred 3 times in one project (BUG-040/041/042). Each time: a logic fix
(matcher rules, sold-status markers, ghost-listing detection) was applied to the code
but not retroactively to existing database records. 37% of listings were ghost/sold
pages shown as active. The meta-lesson: when a principle is violated 3 times, the
principle itself needs strengthening, not just the code.

**Enforcement Planes section added** (2026-04-03) after expert review identified that
Principle 9 had no automated enforcement mechanism (only process/hooks), and that
"Gates vs Tests" introduced a runtime enforcement concept that CI-only architecture
didn't account for. The three-plane model (CI, Hooks, Gates) resolved both issues.

**Test category disambiguation table added** (2026-04-03) after expert review
identified overlapping boundaries between PM-\*/PRO-\*, QG-\*/REV-\*, and
QUAL-\*/XVAL-\*. Rather than consolidating (88 existing tests would need renaming),
clear decision criteria were added.

## 2026-05-08 — CP-025 Tier-1 fix applied to FGT.md self-drift

The Quick Reference cheat sheet at the bottom of FGT.md drifted from canonical
tables in the same file: 10-principle list omitting P1; 13-prefix Test Prefixes
omitting XREAL-\* and SEC-\*; 5-level Enforcement Ranking omitting Session
sweep. Prose counts had drifted too ("three enforcement planes" at lines 134
and 156; "10 Prevention Principles, 13 Test Categories" in README.md line 9).

Each instance was a CP-025 violation — synchronized-representation drift —
inside the methodology file written to prevent it.

Fix per CP-025's own prevention hierarchy: Tier 1 (eliminate by construction).
Deleted the Quick Reference section; removed count adjectives from prose;
canonical tables (FGT.md:58-70, 86-103, 136-141, 158-163) are the single
source of truth.

Drift class structurally eliminated. No new CP minted; CP-025 already
documented the cluster, and FGT's job here was to apply its own discipline
to itself. P1 satisfied: the Quick Reference had no sunsetting condition,
no observable maintenance, and a 60% drift rate — failure to justify keep.

## 2026-05-10 — Distillation + slug introduction (Prevention Principles)

The Prevention Principles section was restructured. Two changes shipped together:

**1. Distillation (peer-level count 11 → 6).** The 11-row monolithic table
was replaced by 4 tier-grouped tables: a meta-rule (`JUSTIFY-KEEP`); a core
thesis (`INVARIANT-TESTED`) with four nested invariant classes
(`EXPLICIT-CONTRACT`, `STRUCTURE-CONTENT`, `VERIFY-TRUST`, `SCAFFOLD-FIRST`);
two test-quality criteria (`PROACTIVE-DETECT`, `DEFENSE-OPS`); and three
orthogonal concerns (`SSOT`, `EXISTS-USED`, `FINDINGS-TRACKED`). The four
nested invariant classes were previously peer-level principles
(P2/P6/P7/P11); they are now legible as specializations of the core.

**2. Slug introduction (`P5` → `INVARIANT-TESTED`).** Stable semantic slugs
became the **primary identifier**; numeric IDs (P1–P11) moved to a Legacy
Numeric IDs table at the end of the section. Slugs are 2-word hyphenated
form (matches existing `EXISTS-USED` convention) and were verified collision-
free across `~/projects/` and `~/.claude/` (single-word forms collided
heavily — `CONTRACT` 260 hits, `STRUCTURE` 84, `VERIFY` 60).

**Why both changes shipped together.** The first three failed distillation
attempts (plan 1 = "tacking on cruft"; plan 2 = "reorganization, not
distillation"; plan 3 draft = legacy-map gymnastics) all bent themselves
around preserving the 395 cross-project references to numeric IDs. That
constraint will bind every future restructure too, locking the redundancy
in place. Slugs decouple references from position: future principle
additions, removals, or reorderings touch FGT.md (and validator) only —
≈3 files instead of 82 directories.

**Validator update (in scope, mandatory).** `scripts/validate-fgt.mjs`
`checkPrincipleReferences()` was rewritten to: (a) extract slugs from tier
tables (regex matches a backtick-quoted slug followed by a bold name),
(b) build a numberToSlug map from the Legacy Numeric IDs table, (c) resolve
template "Principle N" references via the indirection. Existing template
references remain valid; new slug-style references will validate when the
follow-on PR adds slug-side regex.

**Backwards compatibility.** All 11 numeric IDs continue to resolve to a
canonical slug via the Legacy table. 395 cross-project references
(`P5`/`Principle 11` etc.) work unchanged.

**Honest complexity accounting.** This is not a token-count reduction.
~15 lines added (Legacy table + tier framing). The wins are cognitive
(peer count 11 → 6 with visible taxonomy) and structural (future
restructure cost drops from ~395 references to ~3 files). If FGT is in
steady state forever, the slug system is overhead without payoff.

**Two observable sunsetting conditions:**

1. *For tier vocabulary adoption* — whether the distillation took with
   project authors. If
   `grep -rE "(Core|Test-quality|Orthogonal) (principles?|concerns?)" ~/projects/*/CLAUDE.md`
   returns 0 hits 6 months from now (≈ 2026-11-10), the new framing
   didn't propagate; revert to 11-as-peers.

2. *For numeric ID retirement* — whether slugs displaced numbers in
   active prose. If
   `grep -rE '\b(P[0-9]+|Principle [0-9]+)\b' ~/projects/ ~/.claude/`
   returns 0 hits, retire the Legacy Numeric IDs table. Likely never
   reaches 0 (CHANGELOG entries are historical). The table is a
   permanent compatibility appendix; that is acceptable per
   `JUSTIFY-KEEP` because the cost is ~15 lines and the benefit is
   stable cross-project reference resolution.

P1 (`JUSTIFY-KEEP`) satisfied: ≥2 observed instances are the prior failed
restructures + the 395-reference migration tax; ongoing cost is the 15-
line table + ~30-line validator update; both sunsetting conditions are
observable, not calendar-based.

---

## 2026-06-10 — Bug Abstraction step 5b removed (first measured sunset)

Step 5b ("state the sunsetting condition" per BUG entry, added 2026-05-02,
plus its symmetric deferred-item revival rule) is removed from the Bug
Abstraction Protocol. Evidence, measured 2026-06-10 by grep over all
project BUG_PATTERNS files: 169 BUG entries across 9 files, sunsetting
mentions in only 2 files (mentat_llm 8, nakano 1) — including 0 in
infinevent's 52 entries despite active post-May development. ~5%
compliance, and zero observed instances of a sunsetting condition ever
triggering an actual removal. A per-entry prose mandate at enforcement
plane 1 (documentation) with no automation behaved exactly as Insight #2
predicts.

What survives: the requirement itself lives on in `JUSTIFY-KEEP` (c) at
the machinery level — new tests/gates/hooks/templates still need an
observable sunsetting condition. What's removed is the per-bug-entry
ritual that wasn't followed. Anti-accretion at the entry level is served
by retrospective pruning (Heuristic Complexity Review; automated in
infinevent's `scripts/heuristic_complexity_watch.py`).

Removal performed instead of automating compliance because automating it
would have been machinery to enforce metadata about removing machinery —
the accretion failure mode `JUSTIFY-KEEP` exists to prevent.

---

## CPD Stop-Gate Retirement (2026-07-02)

Second measured sunset (after Bug Abstraction step 5b, 2026-06-10).
Removed: the per-turn CPD Stop-hook gate (`cpd-gate-stop.sh`) and its
three support artifacts (`cpd-gate-selftest-hook.sh`,
`cpd-exclusion-sentinel.sh`, `test-cpd-gate-stop.sh`), all of which
existed only to police the gate's own false positives. Archived in
`~/.claude/archive/cpd-gate-retired-2026-07-02/` with the full event log.

**Source:** methodology review session 2026-07-02 (this log entry's
commit). Evidence:

1. Classification of all 478 gate events (2026-05-20 → 06-30):
   >90% false positives — execution reports ("Done", "Commit landed",
   "Verification complete"), self-issued skip rationales, test
   fixtures; ~3 previews genuinely analytical. Each block forced a
   full turn regeneration.
2. 408/478 events (85%) originated in the long-horizon production
   projects (re_proforma 142, infinevent 140, av226 67, tierras 59) —
   the false-positive rate is production-axis, not benchmark, data.
3. CPD's own written sunsetting condition was measured hollow: its
   vocabulary grep matched zero memory files ever (trivially satisfied
   since the day it was written; never validated against a known-bad
   example). Replaced with a manual-judgment condition in
   `~/.claude/patterns/CAUSAL_PLAN_DISCIPLINE.md`.

Kept: the cpd-reviewer subagent, on-demand for major analytical
deliverables (plan-mode plans, requested audits/reviews/critiques,
pre-decision documents) — the component with measured discrimination
(454 invocations, 50% FAIL, 2026-06-10 audit). Grading of the 118
FAIL→revise cycles for decision-level (vs cosmetic) change remains an
open task.

Revival trigger (JUSTIFY-KEEP applied symmetrically to a removal): if
≥2 new `feedback_*.md` memories recording unsourced-claims / flat-list /
menu-loop pushback are created before 2026-10-02, the gate's function
was load-bearing — redesign enforcement (not necessarily a regex gate;
text-shape detection of reasoning quality is the failure mode that
produced the 90% FP rate).

Root-cause lesson recorded: automation-as-enforcement is reliable for
code invariants (a test can check the actual property) but not for
reasoning quality (a hook can only check text-shape proxies — trigger
words, bullet counts, length). Proxy enforcement → false positives →
escape hatches → Goodhart. Prefer on-demand review at genuine
analytical moments over per-turn gating.

---

## 2026-07-03 — First manual sunset pass (all written conditions executed)

All ~18 written sunsetting conditions across FGT.md, the retrospective,
METHODOLOGY_LOG, and `~/.claude/patterns/` were hand-run for the first
time. Prior base rate: zero conditions had ever been executed as checks;
both prior retirements (step 5b, CPD gate) came from manual audits.

**None fire today.** Healthy keeps (checks run, counts quoted):
numeric-ID table (2,552 references — permanent appendix as predicted);
rank-1b row (`cpd-reviewer` still in CLAUDE.md); IDENTIFIER_DRIVEN_TESTS
(220 position-assertions remain); WEB_INTERACTIVE_ELEMENTS (2 consumers);
CP-026 (1/3 projects adopted typed error columns); CP-028 promotion
(no second project — the av226 BUG_PATTERNS hit is re_proforma's symlink).
Prose-conditioned patterns (SECRET_SCAN_PRECOMMIT, REPRODUCIBILITY_ENVELOPE,
ENGINE_PRESENTATION_RIGOR, STRUCTURAL_SNAPSHOTS, VALIDATING_CELL_CONSTRUCTOR)
still apply: sensitive data still handled, investor Excel artifacts still
generated, no typed AST builder exists.

**Finding 1 — hollow falsification condition (P1).** The 2026-04-24 P1
entry's operationalization item 2 ("OCD sweep extended with stale-check
detector") was never implemented — `ocd-sweep.sh` has no such detector,
and no script in fgt-config carries one. The falsification condition
("if the stale-check detector produces zero removal candidates after 18
months, P1 is ceremony") therefore referenced nonexistent machinery —
same class as CPD's hollow vocabulary-grep found 2026-07-02.
**Correction (supersedes that condition):** the manual sunset pass IS the
mechanism. Re-anchored falsification: if two consecutive passes (~quarterly)
yield zero removals, zero hollow-condition findings, and zero
trending-to-fire flags, P1's pass ritual is ceremony — retire the ritual.
Today's pass already clears P1 itself: the principle has driven 2 measured
retirements and exposed 2 hollow conditions.

**Finding 2 — trending to fire.** Tier-vocabulary adoption
(2026-05-10 distillation): `grep -rE "(Core|Test-quality|Orthogonal)
(principles?|concerns?)" ~/projects/*/CLAUDE.md` = 0 hits at ~2 months.
Condition: if still 0 on 2026-11-10, the framing didn't propagate —
revert to 11-as-peers. Re-check at next pass.

Calendar conditions not yet due: CP-024 dead-data (2027-04-24),
CP-025 SRD (2027-05-05; CP-028's addition is explicitly a distinct class
and does not reset it), CP-027 conservation (2028-05-08), CPD retirement
(needs a second consecutive clean pass), CLAUDE.md gate-revival trigger
(2026-10-02).

Pass cost: ~15 minutes of greps. Per the 2026-07-02 decision, automation
of this pass is deferred until manual passes demonstrate recurring yield —
today's yield (2 findings) is the first data point.

---

## 2026-07-03 — FAIL semantics + scaffold-lite (from the 2026-07-02 methodology review)

Two additions, both JUSTIFY-KEEP-complete:

**1. OCD FAIL-semantics rule** (`FGT.md § OCD`, `SWEEP_TEMPLATE.sh`
header): FAIL is reserved for agent-fixable state; external-dependency
states (in-flight CI, third-party outage, pending human action) must be
WARN. Instances (≥2): re_proforma 2026-05-17 (~13 identical "CI
in_progress" replies) and 2026-05-27 (FAIL-on-external-state Stop-hook
loop, user interrupt required). re_proforma's sweep was already fixed
after those incidents (`_av_check_ci_matches_head` downgrades in-flight /
auth / queued-fix cases to WARN); a sweep-wide scan found no remaining
violators — this entry codifies the rule so new checks follow it.
Cost: one FGT.md paragraph + template comment. Sunsetting (observable):
retire when the Stop-hook exit-2 blocking semantic is gone —
`grep -c 'exit 2' ~/.claude/scripts/ocd-sweep.sh` returns 0.

**2. Scaffold-lite** (`new-project.sh --lite`, checklist § 0): minimal
scaffold for unproven projects — git, .gitignore, language config, src
skeleton, one QUAL-001 stub, lint/test CI, stub CLAUDE.md carrying the
upgrade trigger (~20 commits or first external consumer), `.fgt-lite`
marker (removed by a later full scaffold). Instances (≥2): five fully
scaffolded projects stalled at ≤13 commits (health 6, bumbleup 10,
NEB75 3, watches, soundscape — 2026-07-02 portfolio survey), paying
full Day-1 cost with no surviving product. SCAFFOLD-FIRST's evidence
(av226: 2h proactive = 2wk saved) is from projects that lived; lite
defers, not skips — the QUAL stub and CI keep the two cheapest
highest-value pieces. Cost: one branch in new-project.sh. Sunsetting
(observable): retire `--lite` if 12 months from 2026-07-03
`ls ~/projects/*/.fgt-lite 2>/dev/null` is empty AND no lite stub
CLAUDE.md exists (`grep -l 'scaffold-lite' ~/projects/*/CLAUDE.md`) —
the mode went unused.
