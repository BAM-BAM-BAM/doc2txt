# {{PROJECT}} Code Patterns

Proactive architectural patterns that prevent whole classes of design-level issues
(monolith accumulation, satellite state drift, heuristic complexity spirals,
configuration drift) **before they manifest as bugs**. These are design practices,
distinct from the reactive bug-prevention principles in FGT.md.

Generic advice belongs in FGT.md; this file is for **project-specific**
implementation patterns and architectural decisions.

---

## Cross-Process Vocabulary (Typed Enums Across a Process Boundary)

Evidence: CP-013 — claude-refiner ↔ infinevent/mentat_llm, 2026-04-15.

When a string value crosses a process boundary (RPC payload, CLI stdout,
queue row, file format) and has a **known-finite set of valid values**,
it will drift silently unless the producer exposes it as a typed enum.
Example failure: producer writes `status='succeeded'`, README example
says `status='done'`, consumer filters on `'done'`, consumer silently
drops every real result. No error, no log, just missing data.

Apply the four-step move:

1. **Promote** the vocabulary to a typed enum in the producer's source
   (`StrEnum` in Python, string-literal-union or `enum` in TS, etc.).
2. **Re-export** from a single versioned contract module
   (`{{PROJECT}}.contract.v1`) that also carries `SCHEMA_VERSION`.
3. **Producer owns the client.** Ship the typed subprocess/SDK wrapper
   in the producer repo, not in whichever consumer first builds one —
   that way the producer's tests can cover both ends of the contract.
4. **Alias-on-read for one release** when migrating an existing
   vocabulary: honor the old value on reads but never write it. Gives
   existing consumers a deprecation window without silent breakage.

```python
# producer/models.py
from enum import StrEnum

SCHEMA_VERSION = "1.0.0"

class ResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"

# producer/contract.py
from .models import SCHEMA_VERSION, ResultStatus
# ... re-export

# consumer
from producer.contract import v1
assert v1.SCHEMA_VERSION.startswith("1.")
results = v1.get_results(project="x")
for r in results:
    if r.status == v1.ResultStatus.SUCCEEDED:
        ...
```

Pre-integration checklist hook: before writing any module that imports
the producer, verify the producer exposes a `StrEnum` surface + a
versioned contract module. If it does not, that is the first change to
the producer, not the first line of consumer code.

---

## Single Source of Truth (Registry)

When a value is needed in multiple places, define it once and reference everywhere.
See FGT.md § Prevention Principles, #2 (Single Source of Truth).

Define a registry (dict, map, or const object) and reference it everywhere:

```
// registry — Single Source of Truth
COLUMNS = {
    "DATE":   { index: 2, name: "Date" },
    "AMOUNT": { index: 5, name: "Amount" },
}

// other module — reference via registry, never hardcode "2"
import { COLUMNS } from "./registry"
col = COLUMNS["DATE"].index
```

---

## Testing Patterns

### Golden File Test

**Python:**
```python
def test_output_matches_golden(build_result):
    actual = extract_values(build_result)
    expected = json.loads(Path("tests/golden/values.json").read_text())
    for key, exp_val in expected.items():
        assert actual[key] == pytest.approx(exp_val, rel=0.01)
```

**TypeScript:**
```typescript
test("output matches golden", () => {
  const actual = extractValues(buildResult);
  const expected = JSON.parse(fs.readFileSync("tests/golden/values.json", "utf-8"));
  for (const [key, exp] of Object.entries(expected)) {
    expect(actual[key]).toBeCloseTo(exp as number, 2);
  }
});
```

### Three-Tier Golden File Strategy

A single golden file conflates structure, values, and presentation. Split into
three concerns so each can change independently:

| Tier | File | Captures | Tolerance |
|------|------|----------|-----------|
| **Structure** | `golden/structure.json` | Named ranges, sheet names, column counts, headers | Exact match |
| **Values** | `golden/values.json` | Key computed outputs (totals, rates, ratios) | `pytest.approx(rel=0.001)` |
| **Formatting** | `golden/formatting.json` | Cell styles, fonts, fills, alignment | Exact match |

A formatting-only change updates `formatting.json` while `structure.json` and
`values.json` remain unchanged — confirming logic was not affected. Regenerate
with `--update-golden` flag (see conftest.py fixture pattern).

### Proactive Detection Test

Scan for structural anti-patterns that indicate bug classes:

**Python:**
```python
def test_no_hardcoded_cross_refs():
    for path in Path("src/").rglob("*.py"):
        tree = ast.parse(path.read_text())
        # Scan for hardcoded references that should use registry...
```

**TypeScript:**
```typescript
test("PRO-001: no hardcoded cross-refs", () => {
  for (const file of glob.sync("src/**/*.ts")) {
    const content = fs.readFileSync(file, "utf-8");
    // Scan for hardcoded references that should use registry...
  }
});
```

### Cross-Validation Test

Verify presentation matches source of truth:

**Python:**
```python
def test_displayed_value_matches_engine():
    computed = engine_result.total
    displayed = extract_displayed_value("total")
    assert displayed == pytest.approx(computed, rel=0.001)
```

**TypeScript:**
```typescript
test("XVAL-001: displayed total matches computed", () => {
  expect(extractDisplayedValue("total")).toBeCloseTo(engineResult.total, 3);
});
```

---

## Provenance Registry

When a presentation layer (PDF, report, dashboard) extracts and displays values
from a computation engine, every displayed field must be registered with its
lineage. This prevents satellite state — values computed independently in the
presentation layer that drift from the authoritative source.

### The Pattern

Maintain a provenance registry (Python dict, YAML, or JSON) that maps every
extracted field to:

| Attribute | Purpose |
|-----------|---------|
| `source_type` | Classification: `engine`, `config`, `project`, `computed`, `derived` |
| `source_ref` | Human-readable description of where the value comes from |
| `engine_equiv` | (If `computed`) The authoritative engine field this should match |
| `xval_test` | (If `engine_equiv` set) The XVAL-* test that validates parity |
| `satellite_risk` | (Optional) Risk level: `high` for full recomputations |

**Source type taxonomy:**
- `engine` — read directly from engine result (safe, no satellite risk)
- `config` — read from configuration (low risk)
- `project` — static project text (low risk)
- `computed` — calculated within the presentation layer (SATELLITE RISK)
- `derived` — derived from other extracted fields (moderate risk)

### Example Registry Structure

**Python:**
```python
REGISTRY = {
    "report_extract_data": {
        "total_revenue": {"source_type": "engine", "source_ref": "engine.ops.total_revenue"},
        "profit_margin": {"source_type": "computed", "engine_equiv": "engine.ops.profit_margin",
                          "xval_test": "XVAL-015", "satellite_risk": "high"},
        "tax_rate": {"source_type": "config", "source_ref": "cfg_TaxRate"},
    },
}
```

**TypeScript:**
```typescript
const REGISTRY = {
  report_extract_data: {
    total_revenue: { sourceType: "engine", sourceRef: "engine.ops.totalRevenue" },
    profit_margin: { sourceType: "computed", engineEquiv: "engine.ops.profitMargin",
                     xvalTest: "XVAL-015", satelliteRisk: "high" },
    tax_rate: { sourceType: "config", sourceRef: "cfg_TaxRate" },
  },
} as const;
```

### AST-Based Enforcement

Write a proactive test that scans extract functions and verifies all
returned keys appear in the registry:

**Python** (uses `ast.parse()` to extract dict keys):
```python
def test_all_extracted_fields_registered():
    for module, func_name in EXTRACT_FUNCTIONS:
        code_keys = ast_extract_dict_keys(module, func_name)
        unregistered = code_keys - set(REGISTRY[section].keys())
        assert not unregistered, f"{func_name} returns unregistered: {unregistered}"
```

**TypeScript** (uses regex or ts-morph to extract object keys):
```typescript
test("PRO-0XX: all extracted fields are registered", () => {
  const codeKeys = extractObjectKeys("src/extract.ts", "extractData");
  const registered = new Set(Object.keys(REGISTRY.report_extract_data));
  const unregistered = codeKeys.filter(k => !registered.has(k));
  expect(unregistered).toEqual([]);
});
```

### XVAL Coverage Rule

Every `computed` field with an `engine_equiv` MUST have an `xval_test`. A proactive
test enforces this:

**Python:**
```python
def test_computed_fields_have_xval():
    for section, fields in REGISTRY.items():
        for name, meta in fields.items():
            if meta.get("engine_equiv") and not meta.get("xval_test"):
                raise AssertionError(f"{section}.{name}: has engine_equiv but no xval_test")
```

**TypeScript:**
```typescript
test("PRO-0XX: computed fields with engineEquiv must have xvalTest", () => {
  for (const [section, fields] of Object.entries(REGISTRY)) {
    for (const [name, meta] of Object.entries(fields)) {
      if (meta.engineEquiv && !meta.xvalTest) {
        throw new Error(`${section}.${name}: has engineEquiv but no xvalTest`);
      }
    }
  }
});
```

**Why this matters:** A computed field with an engine equivalent is by definition
satellite state. Without a cross-validation test, it WILL drift silently. This
pattern was discovered after multiple bugs where presentation-layer calculations
diverged from the engine by 5-15%, hidden by generous test tolerances.

---

## Module Size Enforcement

Large modules hide satellite code, dead functions, and duplicated logic. Enforce
maximum line counts per module category via a proactive test.

### The Pattern

Define size limits by directory/category. A `PRO-*` test scans all modules and
fails if any exceed the limit:

**Python:**
```python
MODULE_LIMITS = {"src/engine/": 250, "src/docs/": 500}

def test_module_size_limits():
    violations = []
    for directory, max_lines in MODULE_LIMITS.items():
        for path in Path(directory).rglob("*.py"):
            lines = len(path.read_text().splitlines())
            if lines > max_lines:
                violations.append(f"{path}: {lines} lines (max {max_lines})")
    assert not violations, "Oversized modules:\n" + "\n".join(violations)
```

**TypeScript:**
```typescript
const MODULE_LIMITS: Record<string, number> = { "src/engine/": 250, "src/docs/": 500 };

test("PRO-0XX: modules must not exceed size limits", () => {
  const violations: string[] = [];
  for (const [dir, max] of Object.entries(MODULE_LIMITS)) {
    for (const file of glob.sync(`${dir}**/*.ts`)) {
      const lines = fs.readFileSync(file, "utf-8").split("\n").length;
      if (lines > max) violations.push(`${file}: ${lines} lines (max ${max})`);
    }
  }
  expect(violations).toEqual([]);
});
```

### Why This Works

- **Forces decomposition.** When a module hits the limit, the developer must
  split it into focused sub-modules rather than continuing to append.
- **Exposes dead code.** A module near the limit prompts review of what can
  be deleted.
- **Prevents satellite accumulation.** Large doc generators tend to accumulate
  independent calculations that should reference the engine instead.

### Choosing Limits

Start generous (500-600 lines) and tighten as the codebase matures. The limits
should be tight enough to trigger splits but loose enough to avoid artificial
fragmentation. Review violations monthly and adjust.

---

## Satellite Elimination (Required Engine Result)

When a computation engine exists and a presentation layer (PDF, report, dashboard)
displays values, the strongest defense against satellite state is making the
engine result **REQUIRED** — not optional, not fallback-able.

### The Pattern

**Python:**
```python
def extract_data(path, config, *, engine_result):
    if engine_result is None:
        raise ValueError("engine_result is required — satellite calculations removed")
    data["irr"] = engine_result.returns.irr
    data["total"] = engine_result.ops.total_revenue
```

**TypeScript:**
```typescript
function extractData(path: string, config: Config, engineResult: EngineResult): Data {
  // engineResult is required (not optional) — no satellite fallback
  return {
    irr: engineResult.returns.irr,
    total: engineResult.ops.totalRevenue,
  };
}
```

### Why This Works

- **Eliminates** hundreds of lines of fallback code that independently recalculate
- **Makes drift impossible** — there is no second computation to drift from
- **Forces the engine API to be complete** — gaps become errors, not silent fallbacks

### When To Apply

Apply when: (1) a computation engine exists, (2) presentation generators
independently recalculate values the engine already computes, and (3) the engine
always runs before document generation.

If any condition is false, use the Provenance Registry pattern with XVAL-\* tests instead.

### Enforcement

A PRO-\* test scans extract functions via AST for `engine_result=None` default
parameters and verifies each has a `ValueError` guard:

**Python:**
```python
def test_no_optional_engine_result():
    for path in extract_modules:
        tree = ast.parse(path.read_text())
        # Verify functions with engine_result default=None contain ValueError guard
```

**TypeScript** (enforce via type system — `engineResult` is not optional):
```typescript
// The type signature itself is the enforcement:
// function extractData(engineResult: EngineResult)  // OK — required
// function extractData(engineResult?: EngineResult) // PRO-* test flags this
```

---

## Error Collection (Not Fail-Fast)

For pipelines processing multiple items (scrapers, batch processors, data
importers), collect all errors per run rather than aborting on the first.
Users can see ALL issues at once instead of fix-one-rerun-find-next cycles.

### The Pattern

**Python:**
```python
@dataclass
class PipelineResult:
    successes: list[T]
    errors: list[PipelineError]
    source_health: str  # healthy, degraded, broken

def process_batch(items: list[Input]) -> PipelineResult:
    successes, errors = [], []
    for item in items:
        try:
            successes.append(process_one(item))
        except ProcessingError as e:
            errors.append(PipelineError(item=item, error=e))
    health = "healthy" if not errors else "degraded" if successes else "broken"
    return PipelineResult(successes, errors, health)
```

**TypeScript:**
```typescript
interface PipelineResult<T> {
  successes: T[];
  errors: { item: unknown; error: Error }[];
  health: "healthy" | "degraded" | "broken";
}

function processBatch<T>(items: unknown[], processFn: (item: unknown) => T): PipelineResult<T> {
  const successes: T[] = [], errors: { item: unknown; error: Error }[] = [];
  for (const item of items) {
    try { successes.push(processFn(item)); }
    catch (e) { errors.push({ item, error: e as Error }); }
  }
  const health = !errors.length ? "healthy" : successes.length ? "degraded" : "broken";
  return { successes, errors, health };
}
```

### When To Apply

Any pipeline where: (1) items are independent (one failure shouldn't block
others), (2) the user benefits from seeing all issues simultaneously, and
(3) partial results are useful.

---

## Format Canonicalization

Every data type with multiple possible representations must have ONE canonical
storage format. Define the canonical format, validate at ingestion, store in
canonical form, and convert only at display time.

### The Pattern

1. Define canonical format in `FGT_DOMAIN_*.md` § Canonical Data Formats
2. Write an `INV-*` test that asserts all stored values match canonical format
3. Validate at ingestion boundary — reject or normalize before storage
4. Convert to display format only at the presentation layer

### When To Apply

Any project handling: percentages (0.90 vs 90 vs "90%"), currency
($1,234.56 vs 1234.56), dates (ISO vs locale), identifiers (with/without
leading zeros or dashes).

---

## No Unread Columns (Principle 4 — Dead Persisted Data)

Every column, file field, or output region that is written must have at least
one read site in the codebase. A column with zero readers is dead data —
same principle as dead code, different surface — and tends to grow silently
(raw audit blobs, speculative archive fields) because nothing fails when it
accumulates.

**Catches the loud, unambiguous class:** zero readers. Does NOT catch
referenced-but-oversized, partial-read, sampled-read, or redundant-parallel-
reader bloat — those require byte-density analysis with a domain-specific
definition of "useful" and belong in a diagnostic script, not a CI gate.

### The Pattern

1. Extract the set of declared columns from the project's SQLite schema (or
   equivalent structure file). A regex over `CREATE TABLE` blocks is usually
   sufficient.
2. For each column name, `grep -rn <col>` across `src/` (excluding the
   schema declaration file itself). Zero non-INSERT references → fail.
3. Maintain a `DEPRECATED_COLUMNS` allow-list for columns kept in the schema
   for legacy `SELECT *` readers but no longer written. Each entry must carry
   a one-line justification (which PR deprecated it, when it will be dropped).
4. Maintain an `AMBIGUOUS_COLUMNS` allow-list for names that collide with
   common English words (`id`, `name`, `content`, `role`, `status`, …) where
   grep would always find a match regardless of actual usage. These are
   skipped entirely.
5. Run as a `PRO-*` test. CI is the right plane — commit-time catch, no
   sweep duplication.

### Example Implementation

```python
# tests/test_scrubber.py or tests/test_schema.py
import re
from pathlib import Path

DEPRECATED_COLUMNS = frozenset({
    "raw_json",  # deprecated 2026-04-24 (CP-024); drop after soak
})
AMBIGUOUS_COLUMNS = frozenset({
    "id", "name", "content", "role", "status", "priority", "level",
    # …any other single-common-word column names
})

def _extract_schema_columns(database_py: str) -> dict[str, list[str]]:
    tables = {}
    for m in re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\);",
        database_py, re.DOTALL,
    ):
        body = m.group(2)
        cols = [re.match(r"(\w+)", line.strip()).group(1)
                for line in body.splitlines()
                if line.strip() and re.match(r"\w+\s+", line.strip())
                and not line.strip().startswith(("FOREIGN", "PRIMARY", "CHECK"))]
        tables[m.group(1)] = cols
    return tables

def test_PRO_NO_UNREAD_COLUMNS():
    repo = Path(__file__).resolve().parent.parent
    db_py = repo / "src" / "storage" / "database.py"
    schema = _extract_schema_columns(db_py.read_text())
    offenders = []
    for table, cols in schema.items():
        for col in cols:
            if col in DEPRECATED_COLUMNS or col in AMBIGUOUS_COLUMNS:
                continue
            # grep src/ (excluding db_py) for the column name
            refs = sum(
                1 for p in (repo / "src").rglob("*.py")
                if p != db_py and re.search(rf"\b{re.escape(col)}\b", p.read_text())
            )
            if refs == 0:
                offenders.append(f"{table}.{col}")
    assert not offenders, f"Write-only columns: {offenders}"
```

### When To Apply

Any project with a persistence layer (SQLite, JSON-on-disk, config files)
where new columns / fields tend to accumulate. Minimum bar: the project has
≥ 1 table with ≥ 5 columns.

### Sunsetting Condition

If the project ships an external schema-governance tool (Alembic with
`--autogenerate` checks, a proper DB linter, etc.) that already catches
write-only columns at migration time, this PRO test becomes redundant and
can be removed.

### Precedent

CP-024 (fgt_cross_project_retrospective_v2.md) — catalogued after the
`mentat_llm.conversations.raw_json` incident (1.3 GB write-only column
across 3 parsers × 0 readers) and the av226 BUG-004 incident (Excel columns
with populated headers but blank data rows). Same abstraction, different
surface.

---

## {{DOMAIN}}-Specific Patterns

<!-- Add patterns specific to this project's domain here. -->
