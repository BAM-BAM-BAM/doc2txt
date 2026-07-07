# {{PROJECT}} Review Triggers

When to pause and think before committing. The goal is to turn review insights
into automated tests — if you find yourself checking the same thing twice,
write a test instead.

## Review Types

| Trigger | Ask | Automate As |
|---------|-----|-------------|
| Changed a calculation | Do components still reconcile to totals? Are units/signs correct? | INV-\*, EVAL-\* |
| Changed cross-module dependency | Does the contract still hold? Are references via registry? | CONTRACT-\*, PRO-\* |
| Changed config schema | Do all consumers handle the new shape? Backward compatible? | SCHEMA-\* |
| Changed output format | Does displayed data still match computed data? | XVAL-\* |
| Changed business logic | What edge cases exist? (zero, null, negative, boundary) | BOUND-\* |
| Changed data interpretation | Is existing data now contaminated by old logic? (Bug Abstraction step 6) | PRO-\*, INT-\* |
| End of feature | Does changing input X actually change output Y? Are outputs correct? | SENS-\*, QUAL-\*, INT-\* |
| Heuristic modified 3+ times | Is complexity justified? Different approach simpler? Revert to cruder-but-robust? | Architecture review (FGT.md § Heuristic Complexity Review) |

## Design Review Triggers

Proactive triggers for architectural issues — these prevent complexity debt
before it becomes bugs. Evidence: CP-002, CP-005, CP-007, CP-011 in the
cross-project retrospective.

| Trigger | Ask | Reference |
|---------|-----|-----------|
| Heuristic/matcher modified 3+ times | Is accumulated complexity justified by measured improvement? Would a fundamentally different approach be simpler? Should we revert to the cruder-but-robust version? | FGT.md § Heuristic Complexity Review, CP-005 |
| Module approaching size limit | Time to decompose? Dead code to remove? Satellite calculations to eliminate? | PATTERNS § Module Size Enforcement, CP-002 |
| Config schema expanded | All consumers handle the new shape? Types validated? Backward compatible? | CONFIG_{{DOMAIN}}.md, CP-007 |
| Same data stored in multiple formats | Canonical format defined in FGT_DOMAIN? Validated at ingestion? | FGT_DOMAIN § Canonical Data Formats, CP-011 |
| New external dependency added | Does it send telemetry by default? Requires network access? License compatible? | Manual review |
| Circular or deep dependency chain forming | Can modules be restructured? Is the dependency graph a DAG? | Architecture review |
| Requirements discussed in conversation | Were decisions captured in SPEC.md before proceeding? | FGT Session Protocol, Principle 10 |
| Feature complete or milestone reached | Does SPEC.md still match what was built? Any scope creep or dropped items? | SPEC.md vs src/ audit |

## Pre-Implementation

- Does similar functionality already exist? (Don't duplicate)
- What modules does this change affect? (Identify contracts)
- What domain rules apply? (Check `FGT_DOMAIN_*.md`)

## Post-Implementation

- Build passes
- All tests pass
- No stub code (empty returns, unused params, TODO comments)

## {{DOMAIN}}-Specific Reviews

<!-- Add domain-specific review triggers here. -->
