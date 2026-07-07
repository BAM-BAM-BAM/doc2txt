# Revalidation Protocol — {{PROJECT}}

When any commit changes logic that determines how data is classified, filtered,
displayed, or acted upon, existing data processed by the old logic must be
revalidated. See FGT.md § Bug Abstraction Protocol step 6.

## When to Revalidate

Any commit that changes:

- [ ] Parsing / extraction logic
- [ ] Scoring / ranking logic
- [ ] Matching / deduplication logic
- [ ] Classification / categorization logic
- [ ] Normalization / canonicalization logic
- [ ] Filter / gate criteria

## Revalidation Steps

1. **Snapshot** current state: record count + status distribution of affected records
2. **Apply** the fixed logic to ALL existing records
3. **Compute delta**: how many records would change?
4. **Safety gate**: if >{{THRESHOLD_PCT}}% of >{{THRESHOLD_COUNT}} records would change, abort and require explicit confirmation (default: >50% of >50)
5. **Commit** revalidated data
6. **Log** in BUG_PATTERNS.md or METHODOLOGY_LOG: what changed, count, percentage

## Raw Data Retention

- Staging files / raw snapshots retained for **{{RETENTION_DAYS}}** days (default: 30)
- Location: `{{STAGING_PATH}}`
- Purpose: enables re-ingestion when processing logic changes

## Safety Gate Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `{{THRESHOLD_PCT}}` | 50 | Percentage of records changed that triggers abort |
| `{{THRESHOLD_COUNT}}` | 50 | Minimum record count before percentage gate applies |

## {{DOMAIN}}-Specific Revalidation Notes

<!-- Add domain-specific revalidation triggers or procedures here. -->
