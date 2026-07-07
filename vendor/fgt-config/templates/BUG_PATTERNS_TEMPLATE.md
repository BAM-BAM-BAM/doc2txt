# {{PROJECT}} Bug Patterns

Bug catalog for escaped bugs. Each entry links to the prevention principle it violated
(see [FGT.md](FGT.md) § Prevention Principles).

## Bug Catalog

### BUG-001: [Title]

| Field | Value |
|-------|-------|
| **Symptom** | What the user observed |
| **Root Cause** | Why it happened |
| **Fix** | What was changed |
| **Principle Violated** | Which principle (1-10) from FGT.md |
| **Prevention Test** | Test ID (e.g., PRO-001) that catches this class |
| **Siblings** | Were similar bugs found elsewhere? |
| **Data Revalidation** | Was existing data affected? If so, was it revalidated? (Bug Abstraction step 6) |

---

## Example Entries

The following examples illustrate common bug patterns. Replace or remove them
as real bugs are cataloged.

### BUG-EXAMPLE-001: [Placeholder for first real bug]

_Replace this with your first real bug entry using the template above._

### BUG-EXAMPLE-002: Tolerance Trap

| Field | Value |
|-------|-------|
| **Symptom** | All cross-validation tests pass, but displayed values are visibly wrong (e.g., IRR off by 300+ basis points, dollar amounts off by 10%+) |
| **Root Cause** | Test tolerances were set too generously (e.g., `rel=0.15` for dollar amounts, 300bps for IRR). Canceling errors — where one value is too high and another too low — can net out within generous bounds while each individual value is significantly wrong |
| **Fix** | Tighten tolerances to operationally meaningful levels: 20-50 basis points for IRR/rates, 0.1-2% (`rel=0.001` to `rel=0.02`) for dollar amounts. A test that cannot fail is not a test |
| **Principle Violated** | #4 (Invariants Must Be Tested) — a test with a tolerance so generous it cannot fail provides no protection |
| **Prevention Test** | Review all `pytest.approx()` calls; flag any with `rel > 0.05` or `abs > X` where X exceeds operational significance. Consider a `PRO-*` test that scans for overly generous tolerances |
| **Siblings** | Any test using `pytest.approx()` with `rel=0.10` or higher. Common in early-stage projects where "close enough" tolerances are set before precise values are known, then never tightened |
| **Data Revalidation** | N/A — test-only fix, no data affected |

**Pattern:** When first writing cross-validation tests, developers often use generous
tolerances because exact values aren't yet known. Once the engine stabilizes,
these tolerances must be tightened. A good practice: after the first successful
run with known-good values, reduce tolerance to 2x the observed difference.
If the test passes at `rel=0.001`, don't leave it at `rel=0.15`.

### BUG-EXAMPLE-003: Untested Feature Addition

| Field | Value |
|-------|-------|
| **Symptom** | All tests pass despite new feature having zero test coverage |
| **Root Cause** | Adding a new column/section/formula triggers reference-shift updates to existing tests, which feel complete ("I fixed the references") but only preserve old contracts — they don't establish new ones for the new feature |
| **Fix** | When adding any new feature, add at minimum: (1) existence test (header/structure present), (2) correctness test (formula references expected dependencies), (3) consistency test (new values reconcile with related totals) |
| **Principle Violated** | #1 (Explicit Contracts), #4 (Invariants Must Be Tested) |
| **Prevention Test** | SCHEMA-\* for existence, EVAL-\* for correctness, INV-\* for consistency |
| **Siblings** | Any feature addition where only existing tests were modified, none added |
| **Data Revalidation** | N/A — new feature, no existing data affected |

**Pattern:** When a structural change (column insert, schema migration) triggers
reference updates, the "all tests pass" signal creates false confidence. The new
feature itself has zero coverage. Ask: "If I deleted this new feature entirely,
would any test fail?" If the answer is no, you have an untested feature.
