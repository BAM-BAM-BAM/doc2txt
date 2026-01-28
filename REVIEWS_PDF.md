# VE Review Checklists

## Purpose & Authority

This file is the **authoritative source** for:
- Review type definitions and triggers for VE
- Detailed review checklists
- VE-specific validation criteria

**Other files reference this for**: "What reviews to run" and "How to run them."

**This file does NOT contain**: Generic FGT methodology (see `FGT.md`), domain rules (see `FGT_DOMAIN_CRE.md`), task tracking (see `VE_TASKS.md`).

---

## Overview

This document defines **iterative review checkpoints** as part of the **Francis Galton Technique (FGT)**. See [FGT.md](FGT.md) for the methodology foundation.

> **Key Principle (FGT)**: Multiple independent expert perspectives > Any single expert review

---

## Review Triggers

### When to Run Each Review

| Review Type | Trigger | Time Budget |
|-------------|---------|-------------|
| Config Schema | After modifying any YAML schema | 10 min |
| DSL Parsing | After modifying DSL parser | 15 min |
| Domain Model | After modifying entity/edge logic | 15 min |
| React Flow | After modifying graph rendering | 10 min |
| UI/UX | After adding any UI component | 10 min |
| Calculation | After modifying any calculation | 10 min |
| Optimizer | After modifying optimization logic | 15 min |
| Architecture | Every 5 tasks or end of phase | 20 min |
| New Feature Smoke Test | After implementing entity CRUD features | 15 min |
| Component Null Safety | After creating/modifying components with entity props | 10 min |
| Calculation Implementation | After implementing any calculation function | 10 min |
| Data Flow | After connecting UI to data source | 10 min |
| UI Consistency | After adding/modifying any UI component | 10 min |

---

## Review Type 1: Config Schema Review

**Trigger:** After adding/modifying any config file or schema

### Checklist

**Syntax & Structure:**
- [ ] YAML file parses without error
- [ ] All required fields are present
- [ ] Field types match schema (string, number, array, etc.)
- [ ] Enums only contain valid values

**Cross-References:**
- [ ] All `*_ref` fields resolve to valid paths
- [ ] All node IDs referenced in edges exist
- [ ] All param names referenced exist
- [ ] No circular references

**Completeness:**
- [ ] Version field present and correct
- [ ] All new fields documented in VE_CONFIG_SPEC.md
- [ ] Default values specified where appropriate
- [ ] Validation constraints defined

**Backward Compatibility:**
- [ ] Old config files still parse
- [ ] Migration path documented if breaking
- [ ] Version bump if schema changes

### Common Failures

| Failure | Symptom | Fix |
|---------|---------|-----|
| Missing field | `undefined` in loaded config | Add required field to schema |
| Type mismatch | Runtime type error | Check field type in schema |
| Invalid reference | "Reference not found" error | Verify ID exists |
| Circular dependency | Stack overflow | Check load order |

---

## Review Type 2: DSL Parsing Review

**Trigger:** After adding/modifying DSL parser or DSL syntax

### Checklist

**Node Parsing:**
- [ ] All node types recognized
- [ ] Unknown type produces clear error
- [ ] Required fields validated (id, type)
- [ ] Optional fields have correct defaults
- [ ] Container `contains` references validated

**Edge Parsing:**
- [ ] All edge types recognized
- [ ] Exactly one destination type (to, to_split, to_conditional)
- [ ] Split targets validated
- [ ] Conditional param validated
- [ ] Self-loops prevented

**Validation:**
- [ ] Duplicate IDs detected
- [ ] Missing references detected
- [ ] All errors collected (not fail-fast)
- [ ] Errors include line numbers where possible

**Recovery:**
- [ ] Invalid nodes marked but included
- [ ] Invalid edges marked but included
- [ ] Partial results returned with error list

### Test Cases to Verify

```
Parse valid graph           -> No errors, correct structure
Parse missing required ID   -> Error with field name
Parse invalid node type     -> Error with type name
Parse self-loop edge        -> Error caught
Parse split edge            -> Targets parsed correctly
Parse conditional edge      -> Param and values parsed
Parse duplicate ID          -> Error caught
Parse missing reference     -> Error caught
```

---

## Review Type 3: Domain Model Review

**Trigger:** After modifying entity, edge, or model logic

### Checklist

**Entity Creation:**
- [ ] Entity created from ParsedNode correctly
- [ ] Params loaded from scenario config
- [ ] Default values applied for missing params
- [ ] Computed values calculated

**Edge Resolution:**
- [ ] Simple edges resolve to correct target
- [ ] Split edges calculate percentages
- [ ] Conditional edges evaluate param
- [ ] Zero-flow edges handled

**State Updates:**
- [ ] Parameter updates are immutable
- [ ] Updates trigger recalculation
- [ ] Dependent values update
- [ ] No stale data after update

**Variant Switching:**
- [ ] Variant params applied
- [ ] Affected flows recalculated
- [ ] UI reflects new variant

### Invariants to Verify

- Entity ID is unique
- Edge source and target exist
- Split percentages sum to constraint (if specified)
- Param values within bounds (if specified)

---

## Review Type 4: React Flow Review

**Trigger:** After modifying graph rendering, nodes, or edges

### Checklist

**Node Rendering:**
- [ ] All node types render
- [ ] Styling matches node_rendering.yaml
- [ ] Expand/collapse works for containers
- [ ] Summary fields display correctly
- [ ] Handles positioned correctly

**Edge Rendering:**
- [ ] All edge types render
- [ ] Styling matches edge_rendering.yaml
- [ ] Flow amount label displays
- [ ] Zero-flow styling applied
- [ ] Animation works (if specified)

**Layout:**
- [ ] Explicit positions honored
- [ ] Auto-layout applied for missing positions
- [ ] Container children grouped
- [ ] No overlapping nodes

**Interaction:**
- [ ] Node click opens config panel
- [ ] Node drag updates position
- [ ] Minimap reflects current state
- [ ] Zoom and pan work

### Visual Regression Checks

After ANY graph change:
- [ ] All nodes visible and styled
- [ ] All edges connect correctly
- [ ] Labels readable
- [ ] No visual artifacts
- [ ] Responsive to zoom

---

## Review Type 5: UI/UX Review

**Trigger:** After adding any UI component or interaction

### Checklist

**Visual Consistency:**
- [ ] Colors match theme
- [ ] Typography consistent
- [ ] Spacing consistent
- [ ] Icons appropriate

**Interaction:**
- [ ] Click targets large enough (44x44px min)
- [ ] Hover states visible
- [ ] Focus states visible
- [ ] Loading states shown

**Accessibility:**
- [ ] Keyboard navigable
- [ ] ARIA labels on custom elements
- [ ] Color not sole indicator
- [ ] Screen reader friendly

**Error Handling:**
- [ ] Invalid input shows error
- [ ] Error message helpful
- [ ] Recovery path clear
- [ ] No unhandled exceptions

### Config-Driven UI Checks

- [ ] Field labels from field_display.yaml
- [ ] Tooltips from config
- [ ] Format applied correctly
- [ ] Validation from config

---

## Review Type 6: Calculation Review

**Trigger:** After modifying any calculation or formula

### Checklist

**Correctness:**
- [ ] Formula matches specification
- [ ] Units correct (dollars, percent, etc.)
- [ ] Sign correct (positive/negative)
- [ ] Boundary conditions handled

**Domain Accuracy:**
- [ ] Matches IRS rules (for tax)
- [ ] Matches industry standards (for fees)
- [ ] Sources documented

**Integration:**
- [ ] Input values from correct source
- [ ] Output used by correct consumers
- [ ] No double-counting
- [ ] No missing components

**Golden Test:**
- [ ] Known inputs produce expected outputs
- [ ] Edge cases tested (zero, max, negative)

### Domain Expert Questions

**Tax Calculations:**
- Is the bracket lookup correct?
- Is the rate applied to correct portion?
- Are deductions in correct order?

**Fee Calculations:**
- Is the fee base correct (NOI, value, etc.)?
- Is the percentage in industry range?
- Are caps/floors applied?

**Retirement Calculations:**
- Are limits correct for age?
- Is catch-up handled?
- Are combined limits enforced?

---

## Review Type 7: Optimizer Review

**Trigger:** After modifying optimization logic

### Checklist

**Parameter Handling:**
- [ ] Locked params excluded
- [ ] Unlocked params included
- [ ] Bounds respected
- [ ] Types handled (continuous, discrete, categorical)

**Grid Search:**
- [ ] Combinations generated correctly
- [ ] Binary-only uses min/max
- [ ] No duplicate combinations
- [ ] Progress reported

**Constraints:**
- [ ] Hard constraints enforced
- [ ] Invalid combinations rejected
- [ ] Constraint violations reported

**Results:**
- [ ] Sorted by objective (NEB75)
- [ ] All components included
- [ ] Optimal marked
- [ ] Apply works

### Test Cases

```
0 unlocked params  -> 1 result (current config)
1 binary param     -> 2 results
2 binary params    -> 4 results
Constraint violation -> Result excluded
```

---

## Review Type 8: Architecture Review

**Trigger:** Every 5 tasks or end of phase

### Checklist

**Separation of Concerns:**
- [ ] Config files don't contain code logic
- [ ] UI components don't contain business logic
- [ ] Calculations don't depend on UI
- [ ] Domain model is source of truth

**Config-Driven:**
- [ ] New features use config where possible
- [ ] Hardcoded values minimized
- [ ] Config changes don't require code changes

**Testability:**
- [ ] Functions are pure where possible
- [ ] Dependencies injectable
- [ ] Side effects isolated
- [ ] Test coverage adequate

**Performance:**
- [ ] No unnecessary recalculations
- [ ] Large datasets handled
- [ ] Memory not leaking
- [ ] UI responsive

### Smell Detection

| Smell | Indicator | Fix |
|-------|-----------|-----|
| Hardcoded values | Magic numbers in code | Move to config |
| Mixed concerns | UI doing calculations | Extract to domain |
| God component | Component > 300 lines | Split by concern |
| Prop drilling | Props passed > 3 levels | Use context |
| Duplicate logic | Same code in 2+ places | Extract helper |

---

## Review Type 9: New Feature Smoke Test

**Trigger:** After implementing ANY new feature that creates/modifies/deletes entities

### Checklist

**Create Flow:**
- [ ] Entity can be created (form opens, fields render)
- [ ] Required fields validated before save
- [ ] Entity appears in graph after creation
- [ ] Entity can be selected in graph
- [ ] Entity can be edited (ConfigPanel opens with data)
- [ ] Changes persist after save
- [ ] Changes survive page refresh

**Modify Flow:**
- [ ] Existing entity can be selected
- [ ] Current values display correctly
- [ ] Changes apply to graph immediately (or after save)
- [ ] Calculations update based on changes
- [ ] Related entities/flows update correctly

**Delete Flow (if applicable):**
- [ ] Entity can be deleted
- [ ] Confirmation prompt shown (if destructive)
- [ ] Entity removed from graph
- [ ] Related edges cleaned up
- [ ] No orphan references remain

### Integration Path Verification

For any entity CRUD operation, verify the complete data flow:

```
User Action → Form State → Domain Model → React Flow → Graph Display
```

Each step must correctly handle:
- Null/undefined values
- Empty objects
- Newly-created (sparse) entities
- Entities with all optional fields

### Common Failure Patterns

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Entity created but not visible | Missing React Flow sync effect | Add useEffect to sync nodes |
| ConfigPanel crashes on new entity | Null/undefined param access | Add null guards in component |
| Changes don't persist | State not saved to domain model | Verify save handler updates model |
| Graph shows stale data | Derived state not recalculated | Trigger recalc after model update |

---

## Review Type 10: Component Null Safety

**Trigger:** After creating/modifying components that receive entity/data props

### Checklist

**Prop Handling:**
- [ ] Component handles null entity prop
- [ ] Component handles undefined entity prop
- [ ] Component handles empty params object `{}`
- [ ] Component handles newly-created (sparse) entity
- [ ] Component handles entity with all optional fields missing

**Type Safety:**
- [ ] No bare `typeof x === 'object'` checks (use `x !== null && typeof x === 'object'`)
- [ ] Optional chaining used for nested access
- [ ] Nullish coalescing provides defaults
- [ ] useMemo hooks have internal guards

**Test Cases Required:**

```javascript
// For component that takes entity prop:
describe('MyComponent', () => {
  it('renders without error when entity is null', () => {
    render(<MyComponent entity={null} />);
    // Should render empty or placeholder, not crash
  });

  it('renders without error when entity has empty params', () => {
    render(<MyComponent entity={{ id: 'test', params: {} }} />);
  });

  it('renders without error when entity param values are null', () => {
    render(<MyComponent entity={{
      id: 'test',
      params: { value: null, rate: null }
    }} />);
  });

  it('renders correctly with complete entity', () => {
    render(<MyComponent entity={completeTestEntity} />);
    // Verify correct display
  });
});
```

### JavaScript Gotchas to Check

| Pattern | Bug | Fix |
|---------|-----|-----|
| `typeof x === 'object'` | Returns true for null | `x !== null && typeof x === 'object'` |
| `value.property` | Crashes if value is null/undefined | `value?.property` |
| `obj[key].nested` | Crashes if obj[key] is undefined | `obj[key]?.nested` |
| useMemo before guard | Hook runs with null data | Add guard inside useMemo |

---

## Review Type 11: Calculation Implementation Review

**Trigger:** After implementing any calculation function

**Source:** FGT Retrospective v5.9.2-v5.14.2 - 53% of bugs were from missing automated tests on calculations

### Checklist

**Completeness:**
- [ ] Function uses ALL relevant inputs (no unused parameters)
- [ ] Function returns non-trivial values (not empty array/object)
- [ ] No TODO/FIXME comments marking incomplete work
- [ ] No hardcoded test values in return statements

**Correctness:**
- [ ] Formula matches domain specification (tax rules, financial formulas)
- [ ] Units are correct (dollars, percent as decimal 0-1, dates as YYYYMM)
- [ ] Sign is correct (positive/negative where expected)
- [ ] Boundary conditions handled (zero, max, negative inputs)

**Testing:**
- [ ] Golden file test exists for this calculation
- [ ] Edge cases tested (zero inputs, missing inputs, boundary values)
- [ ] Invariant added to validate-domain.mjs for non-trivial output

**Integration:**
- [ ] Input values from correct source
- [ ] Output used by correct consumers
- [ ] No double-counting between calculations

### Stub Code Red Flags

Before marking complete, verify NONE of these exist:

```javascript
// RED FLAG: Empty return
return [];
return {};

// RED FLAG: Unused parameter (b not used)
function calculate(a, b) { return a * 2; }

// RED FLAG: Single hardcoded iteration
for (const year of [2026]) { ... }

// RED FLAG: Hardcoded test values
return { debtService: 0, noi: 12345 };
```

### Related Invariants

- INV-CALC-001: Debt service non-zero when asset has tranches
- INV-CALC-002: Annual data spans full analysis period
- INV-CALC-003: Funding gap includes all cost components

---

## Review Type 12: Data Flow Review

**Trigger:** After connecting UI component to data source

**Source:** FGT Retrospective v5.9.2-v5.14.2 - Data flow disconnection caused 13% of bugs

### Checklist

**Source of Truth:**
- [ ] Data flows from source of truth (not cached/stale copy)
- [ ] No local state duplicating source state
- [ ] Changes to source trigger UI update
- [ ] No derived state that could get out of sync

**React State Sync:**
- [ ] useNodesState/useEdgesState has sync effect (see PATTERNS_VE.md)
- [ ] useState with initialValue has sync useEffect
- [ ] useMemo correctly lists all dependencies
- [ ] useEffect doesn't have stale closure issues

**Data Transformation:**
- [ ] Transform function is pure (same input → same output)
- [ ] Transform is called on every source change
- [ ] Memoization doesn't prevent updates

### Integration Test Required

For any data flow change, verify the complete path:

```
User Action → Form State → Domain Model → Transform → UI Display
```

**Test steps:**
1. Make change in source (e.g., edit entity parameter)
2. Verify intermediate state updates (e.g., domain model)
3. Verify final display updates (e.g., graph node shows new value)
4. Repeat for different entities to ensure no stale data

### Common Failure Patterns

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| UI shows stale data after edit | Derived state not synced | Add useEffect sync |
| New entity not visible | React Flow state not synced | Add setNodes(initialNodes) effect |
| Panel shows wrong entity | Stale closure in callback | Add dependency or use ref |
| Changes lost on re-render | Local state overwritten | Derive from props, don't copy |

### Related Patterns

- See PATTERNS_VE.md: "Derived State Sync Pattern"
- See PATTERNS_VE.md: "React Flow State Sync Pattern"

---

## Review Type 13: UI Consistency Review

**Trigger:** After adding or modifying any UI component

**Source:** FGT Principle 6 - UI Consistency (CLAUDE.md)

### Checklist

**Input Field Consistency:**
- [ ] All numeric inputs use same type (`type="number"` with spinners OR `type="text"` without)
- [ ] All percentage inputs display/parse identically (stored as decimal, displayed as whole number with %)
- [ ] All currency inputs have same formatting (prefix $, thousand separators)
- [ ] All date inputs use same format (YYYYMM)
- [ ] Step values appropriate for field type (e.g., 0.01 for percentages, 1 for counts)

**Component Reuse:**
- [ ] New field uses existing field component (FieldEditor, CascadeField, TableInput)
- [ ] If new component created, documented why existing components insufficient
- [ ] Props match existing usage patterns for same field type

**Visual Consistency:**
- [ ] Same field type has same width across panels
- [ ] Labels positioned consistently (above, beside, or placeholder)
- [ ] Error messages styled identically
- [ ] Focus/hover states match existing components
- [ ] Disabled state appearance consistent

**Behavioral Consistency:**
- [ ] Tab order logical and consistent
- [ ] Enter key behavior same across similar inputs
- [ ] Blur validation behavior consistent
- [ ] Keyboard shortcuts work uniformly

### Field Type Audit

Run this audit periodically (during Architecture Review) to catch drift:

```bash
# Find all input type="number" usages
grep -rn 'type="number"' src/components/

# Find all input type="text" with numeric inputMode
grep -rn 'inputMode="decimal"' src/components/

# Find all input type="text" without inputMode (potential inconsistency)
grep -rn 'type="text"' src/components/ | grep -v inputMode
```

**Expected outcome:** All numeric fields should use the SAME pattern project-wide.

### Current Project Standard

**Canonical numeric input pattern** (to be enforced):

```jsx
// ALL numeric inputs should use type="number" with appropriate step
<input
  type="number"
  value={displayValue}
  step={getStepForFormat(format)}  // 0.1 for percent, 1 for currency, etc.
  min={field.min}
  max={field.max}
  onChange={handleChange}
  className="..."
/>
```

**If spinners are undesirable** for UX reasons, use CSS to hide them consistently:

```css
/* Hide spinners globally for cleaner look (if desired) */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
input[type="number"] {
  -moz-appearance: textfield;
}
```

### Inconsistency Red Flags

| Symptom | Indicates |
|---------|-----------|
| Some inputs have spinners, some don't | Mixed `type="number"` and `type="text"` |
| Percentage displays as "0.85" in one place, "85%" in another | Inconsistent format handling |
| Different validation messages for same error | Multiple validation implementations |
| Tab skips some fields | Inconsistent tabIndex or DOM order |

### Related Principles

- See CLAUDE.md: "Principle 6: UI Consistency"
- See PATTERNS_VE.md: "Numeric Input Pattern"

---

## Pre-Implementation Checklist

Before starting ANY task:

**Config Check:**
- [ ] Does this feature belong in config?
- [ ] Which config file(s) affected?
- [ ] Is schema update needed?

**Existing Code Check:**
- [ ] Does similar functionality exist?
- [ ] Can existing code be extended?
- [ ] Is there a pattern to follow?

**Dependency Check:**
- [ ] What depends on code being changed?
- [ ] What does code being changed depend on?
- [ ] Are there breaking changes?

---

## Post-Implementation Checklist

After completing ANY task:

**Build:**
- [ ] `npm run build` succeeds
- [ ] No TypeScript errors
- [ ] No linting errors

**Test:**
- [ ] Existing tests pass
- [ ] New tests added (if applicable)
- [ ] Manual testing done

**Config:**
- [ ] Config files parse
- [ ] Cross-references valid
- [ ] Documentation updated

**Visual:**
- [ ] UI renders correctly
- [ ] Interactions work
- [ ] No console errors

---

## Review History Template

Track reviews performed:

| Date | Review Type | Scope | Issues Found | Tasks Created |
|------|-------------|-------|--------------|---------------|
| YYYY-MM-DD | Type | Scope | N issues | VE.X.Y |

---

## Appendix: VE-Specific Checklist Items

### Config File Checklist

When adding/modifying config:

1. **Schema defined** - JSON Schema exists for file
2. **Types documented** - VE_CONFIG_SPEC.md updated
3. **Defaults specified** - Missing values have sensible defaults
4. **Validation added** - Invalid values caught
5. **Hot-reload tested** - Changes detected in dev

### DSL Addition Checklist

When adding new DSL syntax:

1. **Spec updated** - VE_DSL_SPEC.md has syntax
2. **Parser handles** - New syntax parsed
3. **Validation added** - Invalid syntax caught
4. **Example added** - entity_graph.dsl.yaml shows usage
5. **Tests added** - Parse test covers new syntax

### UI Component Checklist

When adding new component:

1. **Config-driven** - Uses field_display.yaml
2. **Accessible** - Keyboard + screen reader
3. **Responsive** - Works at different sizes
4. **Error states** - Handles invalid data
5. **Loading states** - Shows during async
6. **Null safety** - Handles null/undefined entity props (see Review Type 10)
7. **useMemo guards** - Guards inside hooks, not just before render
