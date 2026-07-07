# Project Instructions

<!-- FGT-enabled CLAUDE.md template. Replace {{placeholders}} with your values. -->

## FGT Domain Files (MANDATORY)

FGT domain files (`PATTERNS_{{DOMAIN}}.md`, `REVIEWS_{{DOMAIN}}.md`, `FGT_DOMAIN_{{DOMAIN}}.md`,
`BUG_PATTERNS_{{DOMAIN}}.md`) must be **written from scratch** for this project's domain.
Copying from another project is an anti-pattern — it provides false confidence and the
wrong domain content will never be consulted. If a file contains patterns, review triggers,
or domain knowledge from a different project, it is worse than an empty file.

## Pre-Commit Verification (MANDATORY)

Before EVERY commit, run:

```bash
{{TEST_COMMAND}}    # ALL tests must pass
{{BUILD_COMMAND}}   # Clean build required
```

NEVER trust stale test results from previous sessions or compacted context. Re-run every time.

## Bug Abstraction Protocol (MANDATORY for every bug fix)

When fixing ANY bug, you MUST complete ALL steps before committing:

1. **Fix the instance** — resolve the specific reported problem
2. **Abstract to class** — identify the bug CATEGORY using the principles in `{{BUG_PATTERNS_PATH}}`
3. **Add BUG-XXX entry** — document in `{{BUG_PATTERNS_PATH}}` with: Symptom, Root Cause, Fix, Principle Violated
4. **Add prevention test** — write a test that catches the CLASS of error, not just this instance (see "Which test to write" below)
5. **Search for siblings** — grep the codebase for the same pattern in other files
6. **Revalidate existing data** — if the fix changes ANY logic that determines how data is classified, filtered, displayed, or acted upon, re-run the fixed logic on all existing data
7. **Persist the pattern** — update memory/docs for future sessions

## Which Test to Write

When adding a test, choose the category by what you're protecting against:

| You want to ensure... | Write a... | Prefix |
|----------------------|-----------|--------|
| A domain rule always holds (e.g., total = sum of parts) | Invariant test | `INV-*` |
| Module A's reference to Module B stays correct | Contract test | `CONTRACT-*` |
| A structural anti-pattern doesn't exist in the codebase | Proactive test | `PRO-*` |
| A displayed/reported value matches the authoritative computation | Cross-validation test | `XVAL-*` |
| Changing input X actually changes output Y | Sensitivity test | `SENS-*` |
| A specific formula/algorithm is correct | Evaluation test | `EVAL-*` |
| An edge case is handled (zero, null, negative, overflow) | Boundary test | `BOUND-*` |
| A structure has required fields/headers/shape | Schema test | `SCHEMA-*` |
| An end-to-end workflow produces expected results | Integration test | `INT-*` |
| The actual output values users see are correct | Output quality test | `QUAL-*` |
| A domain expert would approve this deliverable | Expert review test | `REV-*` |
| A specific recurring bug pattern doesn't recur | Preventive measure test | `PM-*` |
| User-facing content meets compliance/quality rules | Quality gate test | `QG-*` |

**After a bug fix**, the most common choices are:
- `PRO-*` if the bug was a structural anti-pattern that could exist elsewhere (hardcoded refs, duplicated logic, stale defaults)
- `XVAL-*` if the bug was a displayed value not matching the computed value
- `QUAL-*` if the bug was a wrong output value that passed all pipeline/plumbing tests
- `INV-*` if the bug violated a domain rule that should always hold
- `CONTRACT-*` if the bug was a broken cross-module reference
- `REV-*` if the bug would have been caught by a domain expert reviewing the output
- `QG-*` if the bug was non-compliant content in user-facing output

## Satellite State Prevention (MANDATORY)

Any value computed independently in multiple places WILL drift. Before writing ANY
calculation, ask:

1. Does a single source of truth already compute this? → USE it.
2. Is there a named constant/config for this? → REFERENCE it.
3. Am I duplicating logic from another module? → IMPORT it.

## Session Protocol

At session end or before context compaction, persist important decisions, bug fixes,
and patterns to project files. Specifically update:

- `{{BUG_PATTERNS_PATH}}` — if any bugs were fixed
- Memory files — if any reusable patterns were learned

At session start:
- Read memory files and `{{BUG_PATTERNS_PATH}}` before acting
- Run tests to verify current state — never trust "it was passing before"

## Prevention Principles

When a bug escapes, identify which principle was violated. The 11
principles and their enforcement planes are defined in
[FGT.md](FGT.md) § Prevention Principles (symlinked into every project
by `new-project.sh`). Do not duplicate them here — that's a Principle 3
violation waiting to happen.

<!-- Add project-specific instructions below this line -->
