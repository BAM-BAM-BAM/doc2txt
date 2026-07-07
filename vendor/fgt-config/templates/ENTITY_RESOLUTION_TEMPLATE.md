# Entity Resolution — {{PROJECT}}

Optional template for projects that match records across multiple data sources
where the same real-world {{ENTITIES}} may appear with different names, IDs, or
attributes. Skip this template if the project does not involve cross-source
entity matching.

## Required Components (if this template applies)

### 1. Canonical Registry

Single source of truth mapping all known names/aliases to canonical IDs.

```yaml
# config/{{ENTITIES}}.yaml
{{ENTITIES}}:
  - id: "CANON-001"
    canonical_name: "Example Entity"
    aliases: ["example", "Example Co", "EXAMPLE"]
```

### 2. Normalizer Module

Dedicated module (not an inline function) mapping raw input to canonical IDs.
All lookups go through this module — no direct alias matching elsewhere.

### 3. Confidence Scoring

Every match returns a float 0.0-1.0, not a boolean. This enables the
three-outcome logic below.

### 4. Three-Outcome Logic

| Confidence | Action |
|-----------|--------|
| >= {{AUTO_THRESHOLD}} (default 0.8) | Auto-merge |
| >= {{QUARANTINE_THRESHOLD}} (default 0.5) | Quarantine for human review |
| < {{QUARANTINE_THRESHOLD}} | Treat as distinct |

### 5. Quarantine Review Queue

Ambiguous matches stored for human review. Provide a UI or CLI for resolution.
Quarantine items should not block pipeline processing.

### 6. Idempotency

Running deduplication twice produces the same result. No cumulative drift.

## Testing

| Category | What to test |
|----------|-------------|
| QUAL-\* | Known duplicates from real data are merged correctly |
| QUAL-\* | Known distinct {{ENTITIES}} are NOT merged (false positive check) |
| BOUND-\* | Empty/null entity names don't crash the normalizer |
| INV-\* | Dedup is idempotent (run twice, same result) |
| INV-\* | Quarantine queue is empty after all items resolved |
| XVAL-\* | Displayed entity name matches canonical registry |
