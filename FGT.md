# Francis Galton Technique (FGT)

## Overview

The **Francis Galton Technique (FGT)** is a development methodology built on three insights:

1. **Bugs that escape to users are process failures** - fix both the bug and the process
2. **Documentation gets skipped** - automation enforces what docs only recommend
3. **CI is the only reliable enforcement** - voluntary compliance fails

**FGT is domain-agnostic.** Domain-specific knowledge is maintained in `FGT_DOMAIN_*.md` files.

## Core Principle

> **Every escaped bug triggers a process improvement that becomes an automated test enforced by CI.**

This creates a continuously improving system where bugs can only occur once.

---

## The Five Pillars

### Pillar 1: Concern Separation

When implementing features, think through different stakeholder concerns:

| Concern | Focus | Key Question |
|---------|-------|--------------|
| **Domain** | Industry standards, terminology | "Does this match how professionals work?" |
| **Business Logic** | Event ordering, dependencies | "What happens when X triggers Y?" |
| **End User** | Usability, clarity | "Can users accomplish their goal?" |

**Domain-specific concerns are defined in `FGT_DOMAIN_*.md`.**

This is not multi-party review—it's structured thinking about different perspectives during development.

---

### Pillar 2: Iterative Development

Reviews happen **during development**, not after:

1. **Before**: Test existing behavior, understand context
2. **During**: Write code with domain rules in mind
3. **After**: Run tests, verify, commit

---

### Pillar 3: Self-Improvement

Every bug triggers a process improvement:

```
BUG FOUND → FIX BUG → ASK "Why didn't we catch this?" → ADD AUTOMATED TEST
```

**The key question**: "Why didn't FGT prevent this?"

| Answer | Action |
|--------|--------|
| No test for this case | Add invariant test |
| Test exists but too narrow | Expand test scope |
| Subjective check was skipped | Extract objective invariant |

**Generalize lessons**: Don't add narrow fixes. Find the underlying principle.

| Bad (narrow) | Good (generalized) |
|--------------|-------------------|
| "Check date field type" | "Validate ambiguous types before operations" |
| "Verify C3 sum" | "Components must reconcile to totals" |

---

### Pillar 4: Automated Testing

> **Documentation tells you what to check. Automation checks it for you.**

**Types of automated tests:**

| Type | Purpose | Example |
|------|---------|---------|
| **Invariant tests** | Domain rules always hold | `contribution <= IRS_LIMIT` |
| **Schema validation** | Data structure is valid | `timeline dates in YYYYMM format` |
| **Golden file tests** | Calculations match expected output | `sum(components) == total` |
| **Integration tests** | Full flow works correctly | Parameter change propagates |
| **Smoke tests** | Features actually work | Button click shows results |

**Test commands:**

```bash
npm run verify:domain      # Invariant tests
npm run verify:model-schema # Schema validation
npm run test:golden        # Golden file comparison
npm run test:integration   # Flow integration tests
npm run smoke              # E2E smoke tests
npm run golden:update      # Regenerate golden files (when changes are intentional)
```

**Invariant extraction**: Convert subjective questions into objective tests.

| Subjective Question | Objective Invariant |
|---------------------|---------------------|
| "Is the cap rate reasonable?" | `0.04 <= capRate <= 0.15` |
| "Does retirement contribution follow IRS rules?" | `contribution <= 69000` |
| "Do the components add up?" | `c1 + c2 + c3 == total` |

**When to add automation**: When a bug type occurs twice, checklists aren't sufficient—automate.

---

### Pillar 5: CI Enforcement

> **If it can be skipped, it will be skipped.**

CI is the only reliable enforcement. Everything critical goes in CI:

```yaml
# .github/workflows/verify.yml
- npm run lint
- npm run test:unit           # Unit tests
- npm run test:golden         # Golden file tests
- npm run test:integration    # Integration tests
- npm run verify:domain       # Invariant tests
- npm run verify:model-schema # Schema validation
- npm run build
- npm run smoke               # E2E tests
```

**Branch protection**: Merge blocked until CI passes. No exceptions.

**PR workflow**:
```bash
git checkout -b fix/foo
# make changes
git add -A && git commit -m "Fix: description"
git push -u origin fix/foo
gh pr create --fill
# wait for CI
gh pr merge --squash
git checkout main && git pull
```

---

## File Organization

| File | Purpose |
|------|---------|
| `FGT.md` | Methodology (this file) |
| `FGT_DOMAIN_*.md` | Domain-specific knowledge and invariants |
| `scripts/validate-domain.mjs` | Automated invariant tests |
| `.github/workflows/verify.yml` | CI enforcement |

**Historical record**: Git history and PR descriptions. No separate log file.

---

## Development Cycle

### 1. Pre-Implementation
- Understand the task
- Search for existing functionality (don't duplicate)
- Review domain knowledge (`FGT_DOMAIN_*.md`)

### 2. Implementation
- Follow domain rules (constants, not magic numbers)
- Handle edge cases (null, zero, negative, boundaries)
- Write clear, self-documenting code

### 3. Verification
- Build passes
- Tests pass
- Manual verification for UI changes

### 4. Commit
- Clear commit message
- PR with description
- Wait for CI to pass

---

## Quick Reference

```
FGT Cycle:
1. UNDERSTAND  → Read task, search for existing code, load domain knowledge
2. IMPLEMENT   → Follow domain rules, handle edge cases
3. VERIFY      → Build, test, manual check
4. COMMIT      → PR, wait for CI, merge

Bug Response:
1. FIX         → Implement the fix
2. ASK         → "Why didn't FGT prevent this?"
3. AUTOMATE    → Add invariant test
4. COMMIT      → Fix + test together

Core Principles:
• Bugs escape = process failure → fix both
• Documentation gets skipped → automate
• Voluntary compliance fails → CI enforces
• Bug recurs twice → automate detection
```

---

## Why "Francis Galton"?

Francis Galton demonstrated that aggregating multiple perspectives catches more errors than any single expert. FGT applies this by:

1. **Thinking through concerns** (domain, business, user) during development
2. **Converting insights to tests** that run automatically
3. **Enforcing via CI** so nothing gets skipped

The methodology improves with every bug—each one adds a test that prevents recurrence.
