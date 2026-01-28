# VE Code Patterns

## Purpose & Authority

This file is the **authoritative source** for:
- Code patterns and conventions used in VE
- Config parsing patterns
- React Flow integration patterns
- State management patterns

**Other files reference this for**: "How to implement X in this codebase."

---

## JavaScript Safety Patterns

### Null-Safe Type Checking

**CRITICAL**: JavaScript's `typeof null === 'object'` is TRUE. This is a well-known language quirk that causes frequent bugs.

```javascript
// BAD - typeof null === 'object' is TRUE, causes "Cannot read properties of null"
if (typeof value === 'object') {
  console.log(value.property);  // CRASH if value is null
}

// GOOD - explicit null check first
if (value !== null && typeof value === 'object') {
  console.log(value.property);  // Safe
}

// BETTER - use optional chaining with nullish coalescing
const v = value?.property ?? defaultValue;
```

### Safe Property Access

```javascript
// BAD - crashes if obj is null/undefined
const value = obj.property;

// BAD - still crashes if obj is null
const value = obj && obj.property;

// GOOD - optional chaining with fallback
const value = obj?.property ?? defaultValue;

// GOOD - for nested access
const deep = obj?.level1?.level2?.property ?? defaultValue;
```

### Safe useMemo with Guards

When a component has early-return guards, useMemo hooks still run unconditionally. Always add guards inside useMemo:

```javascript
// BAD - useMemo runs before guard, crashes on null entity
const fields = useMemo(() => {
  return entity.params.map(p => p.value);  // CRASH if entity is null
}, [entity]);

if (!entity) return null;  // Guard comes too late!

// GOOD - guard inside useMemo
const fields = useMemo(() => {
  if (!entity?.params) return [];  // Guard inside
  return entity.params.map(p => p.value);
}, [entity]);

if (!entity) return null;  // Component guard still useful for rendering
```

---

## Result<T> Pattern

All functions that can fail return Result<T>:

```typescript
type Result<T> = 
  | { ok: true; value: T }
  | { ok: false; error: { code: string; message: string; field?: string } };

const Ok = <T>(value: T): Result<T> => ({ ok: true, value });
const Err = (code: string, msg: string, field?: string): Result<never> => 
  ({ ok: false, error: { code, message: msg, field } });

const unwrapOr = <T>(result: Result<T>, def: T): T => 
  result.ok ? result.value : def;

const mapResult = <T, U>(result: Result<T>, fn: (v: T) => U): Result<U> =>
  result.ok ? Ok(fn(result.value)) : result;
```

---

## Config Parsing Patterns

### YAML File Loader

```typescript
import yaml from 'js-yaml';

interface ParseResult<T> {
  data: T | null;
  errors: ParseError[];
  warnings: ParseWarning[];
}

interface ParseError {
  code: string;
  message: string;
  line?: number;
  column?: number;
}

const loadYamlFile = <T>(filePath: string, schema: JSONSchema): ParseResult<T> => {
  const errors: ParseError[] = [];
  const warnings: ParseWarning[] = [];
  
  // 1. Read file
  let content: string;
  try {
    content = fs.readFileSync(filePath, 'utf-8');
  } catch (e) {
    errors.push({ code: 'FILE_NOT_FOUND', message: `Cannot read ${filePath}` });
    return { data: null, errors, warnings };
  }
  
  // 2. Parse YAML
  let parsed: unknown;
  try {
    parsed = yaml.load(content);
  } catch (e) {
    if (e instanceof yaml.YAMLException) {
      errors.push({ 
        code: 'YAML_SYNTAX', 
        message: e.message,
        line: e.mark?.line,
        column: e.mark?.column
      });
    }
    return { data: null, errors, warnings };
  }
  
  // 3. Validate schema
  const validation = validateSchema(parsed, schema);
  errors.push(...validation.errors);
  warnings.push(...validation.warnings);
  
  if (errors.length > 0) {
    return { data: null, errors, warnings };
  }
  
  return { data: parsed as T, errors, warnings };
};
```

### Config Loader with Order

```typescript
interface ConfigState {
  domain: {
    taxRules: TaxRules;
    retirementRules: RetirementRules;
    feeRanges: FeeRanges;
    depreciationRules: DepreciationRules;
  };
  topology: {
    graph: ParsedGraph;
    variants: StructuralVariants;
  };
  ui: {
    fieldDisplay: FieldDisplay;
    nodeRendering: NodeRendering;
    edgeRendering: EdgeRendering;
  };
  optimization: {
    fields: OptimizableFields;
  };
  scenario: ScenarioConfig;
}

const loadAllConfigs = async (configDir: string): Promise<Result<ConfigState>> => {
  const errors: ParseError[] = [];
  
  // Load in dependency order
  // 1. Domain rules (independent)
  const taxRules = await loadYamlFile<TaxRules>(
    `${configDir}/domain/tax_rules.yaml`,
    TAX_RULES_SCHEMA
  );
  if (!taxRules.data) errors.push(...taxRules.errors);
  
  const retirementRules = await loadYamlFile<RetirementRules>(
    `${configDir}/domain/retirement_rules.yaml`,
    RETIREMENT_RULES_SCHEMA
  );
  if (!retirementRules.data) errors.push(...retirementRules.errors);
  
  // ... continue for all files
  
  // 2. Topology (may reference domain)
  const variants = await loadYamlFile<StructuralVariants>(
    `${configDir}/topology/structural_variants.yaml`,
    VARIANTS_SCHEMA
  );
  
  const graph = await loadDSL(`${configDir}/topology/entity_graph.dsl.yaml`);
  
  // 3. Validate cross-references
  const crossRefErrors = validateCrossReferences(graph.data, variants.data);
  errors.push(...crossRefErrors);
  
  if (errors.length > 0) {
    return Err('CONFIG_LOAD_FAILED', `${errors.length} errors loading configs`);
  }
  
  return Ok({
    domain: { taxRules: taxRules.data!, /* ... */ },
    topology: { graph: graph.data!, variants: variants.data! },
    // ...
  });
};
```

---

## DSL Parsing Patterns

### Node Parser

```typescript
interface ParsedNode {
  id: string;
  type: NodeType;
  subtype?: string;
  label: string;
  contains?: string[];
  configSchema?: string;
  summaryFields?: SummaryField[];
}

const parseNode = (raw: unknown, index: number): Result<ParsedNode> => {
  if (typeof raw !== 'object' || raw === null) {
    return Err('NODE_INVALID', `Node at index ${index} is not an object`);
  }
  
  const obj = raw as Record<string, unknown>;
  
  // Required: id
  if (typeof obj.id !== 'string' || obj.id.trim() === '') {
    return Err('NODE_MISSING_ID', `Node at index ${index} missing 'id'`);
  }
  
  // Required: type
  if (typeof obj.type !== 'string') {
    return Err('NODE_MISSING_TYPE', `Node '${obj.id}' missing 'type'`);
  }
  
  if (!isValidNodeType(obj.type)) {
    return Err('NODE_INVALID_TYPE', `Node '${obj.id}' has invalid type '${obj.type}'`);
  }
  
  // Optional: label (default to id)
  const label = typeof obj.label === 'string' ? obj.label : obj.id;
  
  // Optional: contains (for containers)
  let contains: string[] | undefined;
  if (obj.contains !== undefined) {
    if (!Array.isArray(obj.contains)) {
      return Err('NODE_INVALID_CONTAINS', `Node '${obj.id}' contains must be array`);
    }
    contains = obj.contains.filter(c => typeof c === 'string');
  }
  
  return Ok({
    id: obj.id,
    type: obj.type as NodeType,
    subtype: typeof obj.subtype === 'string' ? obj.subtype : undefined,
    label,
    contains,
    configSchema: typeof obj.configSchema === 'string' ? obj.configSchema : undefined,
  });
};
```

### Edge Parser with Split/Conditional

```typescript
interface ParsedEdge {
  id: string;
  from: string;
  to?: string;
  toSplit?: SplitTarget[];
  toConditional?: ConditionalTarget;
  type: EdgeType;
  label?: string;
}

interface SplitTarget {
  target: string;
  percentParam: string;
}

interface ConditionalTarget {
  param: string;
  values: Record<string, string | null>;
}

const parseEdge = (raw: unknown, index: number): Result<ParsedEdge> => {
  if (typeof raw !== 'object' || raw === null) {
    return Err('EDGE_INVALID', `Edge at index ${index} is not an object`);
  }
  
  const obj = raw as Record<string, unknown>;
  
  // Required fields
  if (typeof obj.id !== 'string') {
    return Err('EDGE_MISSING_ID', `Edge at index ${index} missing 'id'`);
  }
  if (typeof obj.from !== 'string') {
    return Err('EDGE_MISSING_FROM', `Edge '${obj.id}' missing 'from'`);
  }
  if (typeof obj.type !== 'string' || !isValidEdgeType(obj.type)) {
    return Err('EDGE_INVALID_TYPE', `Edge '${obj.id}' has invalid type`);
  }
  
  // Destination: exactly one of to, to_split, to_conditional
  const hasTo = typeof obj.to === 'string';
  const hasSplit = obj.to_split !== undefined;
  const hasConditional = obj.to_conditional !== undefined;
  
  const destCount = [hasTo, hasSplit, hasConditional].filter(Boolean).length;
  if (destCount !== 1) {
    return Err('EDGE_DEST_AMBIGUOUS', 
      `Edge '${obj.id}' must have exactly one of: to, to_split, to_conditional`);
  }
  
  // Parse split targets
  let toSplit: SplitTarget[] | undefined;
  if (hasSplit && Array.isArray(obj.to_split)) {
    toSplit = obj.to_split.map((t: any) => ({
      target: t.target,
      percentParam: t.percent_param,
    }));
  }
  
  // Parse conditional target
  let toConditional: ConditionalTarget | undefined;
  if (hasConditional && typeof obj.to_conditional === 'object') {
    const cond = obj.to_conditional as Record<string, unknown>;
    toConditional = {
      param: cond.param as string,
      values: cond.values as Record<string, string | null>,
    };
  }
  
  return Ok({
    id: obj.id,
    from: obj.from,
    to: hasTo ? obj.to as string : undefined,
    toSplit,
    toConditional,
    type: obj.type as EdgeType,
    label: typeof obj.label === 'string' ? obj.label : undefined,
  });
};
```

---

## Domain Model Patterns

### Entity with Parameter Binding

```typescript
interface Entity {
  id: string;
  type: NodeType;
  subtype?: string;
  label: string;
  params: Map<string, ParamValue>;
  computed: Map<string, number>;
}

interface ParamValue {
  value: number | string | boolean;
  source: 'config' | 'user' | 'computed';
  locked: boolean;
}

const createEntity = (
  node: ParsedNode, 
  scenario: ScenarioConfig,
  fieldDisplay: FieldDisplay
): Entity => {
  const params = new Map<string, ParamValue>();
  
  // Load params from scenario
  const scenarioParams = scenario[node.id] || {};
  for (const [key, value] of Object.entries(scenarioParams)) {
    params.set(key, {
      value,
      source: 'user',
      locked: true, // Default locked
    });
  }
  
  return {
    id: node.id,
    type: node.type,
    subtype: node.subtype,
    label: node.label,
    params,
    computed: new Map(),
  };
};
```

### Immutable State Update

```typescript
const updateEntityParam = (
  model: DomainModel,
  entityId: string,
  paramName: string,
  value: number | string | boolean
): DomainModel => {
  const entity = model.entities.get(entityId);
  if (!entity) return model;
  
  // Create new param map
  const newParams = new Map(entity.params);
  newParams.set(paramName, {
    value,
    source: 'user',
    locked: entity.params.get(paramName)?.locked ?? true,
  });
  
  // Create new entity
  const newEntity = { ...entity, params: newParams };
  
  // Create new entities map
  const newEntities = new Map(model.entities);
  newEntities.set(entityId, newEntity);
  
  // Recalculate affected values
  return recalculateModel({ ...model, entities: newEntities });
};
```

---

## React Flow Patterns

### Domain Model to React Flow Transform

```typescript
import { Node, Edge } from 'reactflow';

interface RFNode extends Node {
  data: {
    entity: Entity;
    expanded: boolean;
    yearData: YearEntityData;
  };
}

interface RFEdge extends Edge {
  data: {
    edge: DomainEdge;
    flowAmount: number;
    yearData: YearEdgeData;
  };
}

const transformToReactFlow = (
  model: DomainModel,
  layout: Map<string, LayoutHint>,
  selectedYear: number
): { nodes: RFNode[]; edges: RFEdge[] } => {
  const nodes: RFNode[] = [];
  const edges: RFEdge[] = [];
  
  // Transform entities to nodes
  for (const [id, entity] of model.entities) {
    const hint = layout.get(id);
    const yearData = model.yearData.get(selectedYear)?.entities.get(id);
    
    nodes.push({
      id,
      type: getNodeComponent(entity.type),
      position: hint?.position ?? { x: 0, y: 0 },
      data: {
        entity,
        expanded: hint?.expanded ?? false,
        yearData: yearData ?? createEmptyYearData(),
      },
    });
  }
  
  // Transform edges
  for (const [id, edge] of model.edges) {
    const yearData = model.yearData.get(selectedYear)?.edges.get(id);
    const flowAmount = yearData?.amount ?? 0;
    
    // Skip rendering if zero flow (or render dimmed)
    edges.push({
      id,
      source: edge.from,
      target: resolveEdgeTarget(edge, model.params),
      type: getEdgeComponent(edge.type),
      animated: flowAmount > 0,
      data: {
        edge,
        flowAmount,
        yearData: yearData ?? createEmptyEdgeData(),
      },
    });
  }
  
  // Apply auto-layout for nodes without positions
  return applyAutoLayout({ nodes, edges });
};
```

### Custom Node Component

```typescript
import { Handle, Position, NodeProps } from 'reactflow';

const EntityNode: React.FC<NodeProps<RFNode['data']>> = ({ data }) => {
  const { entity, yearData } = data;
  const rendering = useNodeRendering(entity.type, entity.subtype);
  
  return (
    <div 
      className={`
        rounded-lg border p-4
        ${rendering.background}
        ${rendering.border}
      `}
      style={{ minWidth: rendering.minWidth }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <Icon name={rendering.icon} className={rendering.accentColor} />
        <span className="font-medium">{entity.label}</span>
      </div>
      
      {/* Summary fields */}
      <div className="space-y-1 text-sm">
        {yearData.summaryFields.map(field => (
          <div key={field.key} className="flex justify-between">
            <span className="text-slate-400">{field.label}</span>
            <span>{formatValue(field.value, field.format)}</span>
          </div>
        ))}
      </div>
      
      {/* Handles for connections */}
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  );
};
```

### Custom Edge Component

```typescript
import { EdgeProps, getBezierPath, EdgeLabelRenderer } from 'reactflow';

const FlowEdge: React.FC<EdgeProps<RFEdge['data']>> = ({
  id,
  sourceX, sourceY,
  targetX, targetY,
  data,
}) => {
  const { edge, flowAmount } = data;
  const rendering = useEdgeRendering(edge.type);
  
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY,
    targetX, targetY,
  });
  
  const isZeroFlow = flowAmount === 0;
  
  return (
    <>
      <path
        id={id}
        d={edgePath}
        stroke={rendering.color}
        strokeWidth={isZeroFlow ? 1 : rendering.strokeWidth}
        strokeDasharray={isZeroFlow ? '2,4' : rendering.dashArray}
        opacity={isZeroFlow ? 0.2 : 1}
        fill="none"
      />
      
      {/* Flow amount label */}
      {flowAmount > 0 && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
            className="bg-slate-900 px-2 py-1 rounded text-xs"
          >
            {formatCurrency(flowAmount)}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
};
```

---

## React Flow State Sync Pattern

**CRITICAL**: React Flow's `useNodesState` and `useEdgesState` hooks only use their initial value on mount. They do NOT automatically sync when props change.

```javascript
// BAD - nodes never update when initialNodes prop changes
const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);

// GOOD - add sync effect for external data changes
const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);

useEffect(() => {
  setNodes(initialNodes);
}, [initialNodes, setNodes]);

// Same pattern for edges
const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

useEffect(() => {
  setEdges(initialEdges);
}, [initialEdges, setEdges]);
```

**Why this matters**: When new entities are added to the domain model, the transformed `initialNodes` prop will contain the new node. But without the sync effect, React Flow's internal state never receives the update, making new nodes invisible.

**Common symptom**: "I added a new entity but it doesn't appear in the graph" - this is almost always a missing sync effect.

---

## Derived State Sync Pattern

**CRITICAL**: When component state is derived from props or context, ensure it syncs when the source changes.

```javascript
// BAD - Uses initial value only, never updates when props change
const [data, setData] = useState(props.initialData);  // Never updates!

// GOOD - Syncs when source changes
const [data, setData] = useState(props.initialData);
useEffect(() => setData(props.initialData), [props.initialData]);

// BETTER - Derive directly (no local state, no sync bugs possible)
const data = useMemo(() => transform(props.source), [props.source]);
```

**Why this matters**: State that derives from a source must update when the source changes. Using `useState` alone only captures the initial value - subsequent prop changes are ignored.

**Common symptoms**:
- "ConfigPanel shows stale entity after I clicked a different node"
- "Changes to model data don't appear in the UI"
- "Panel shows data from previously selected item"

**Best practice**: Prefer `useMemo` over `useState` + `useEffect` for derived state. The `useMemo` approach is declarative and can't have sync bugs.

---

## Stub Code Detection Pattern

**CRITICAL**: Never ship placeholder/stub code. Signs of stub code that will cause bugs:

| Red Flag | Example | Bug Pattern |
|----------|---------|-------------|
| Function returns empty array/object | `return []` unconditionally | Data appears missing |
| Unused parameters | `function calc(a, b) { return a }` | Input not used in calculation |
| TODO/FIXME comments | `// TODO: implement this` | Incomplete implementation |
| Hardcoded test values | `return { total: 12345 }` | Fake data in production |
| Single iteration | `for (year of [2026])` | Only first year calculated |

**Pre-commit check**: Before committing, search for potential stub code:

```bash
# Check for common stub patterns in staged changes
git diff --staged | grep -E "(TODO|FIXME|return \[\]|return \{\}|// implement)"
```

**The bug pattern**: Developer creates stub function intending to implement later → forgets → ships it → bug discovered much later when user notices missing/wrong data.

**Prevention**:
1. Add invariants that fail on stub output (e.g., INV-CALC-001: debt service must be non-zero)
2. Golden file tests that verify real calculated values
3. Code review specifically looking for unused parameters

---

## Numeric Input Pattern

**CRITICAL**: All numeric input fields must use the same implementation pattern for consistency.

### Canonical Pattern (with spinners)

```jsx
// STANDARD: Use type="number" for all numeric inputs
<input
  type="number"
  value={displayValue}
  step={getStepForFormat(format)}
  min={field.min}
  max={field.max}
  onChange={handleChange}
  onBlur={handleBlur}
  className="w-full px-3 py-2 border rounded..."
/>

// Step values by format type
function getStepForFormat(format) {
  switch (format) {
    case 'percent': return 0.1;    // 0.1% increments
    case 'currency': return 1000;  // $1,000 increments
    case 'acres': return 0.1;      // 0.1 acre increments
    case 'multiple': return 0.01;  // 0.01x increments
    case 'years': return 1;        // 1 year increments
    default: return 1;
  }
}
```

### If Spinners Are Undesirable

If the project decides spinners clutter the UI, hide them globally via CSS:

```css
/* In index.css - applies to ALL number inputs */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
input[type="number"] {
  -moz-appearance: textfield;
}
```

**Key point**: Still use `type="number"` for semantic correctness and mobile keyboard, just hide the spinners visually.

### Anti-Pattern: Mixed Input Types

```jsx
// BAD - Inconsistent across components
// Component A (has spinners)
<input type="number" value={price} />

// Component B (no spinners)
<input type="text" inputMode="decimal" value={rate} />
```

This inconsistency confuses users and makes maintenance harder.

### Field Component Responsibility

All numeric field rendering should go through centralized components:

| Component | Use Case | Input Type |
|-----------|----------|------------|
| `FieldEditor` | Standard form fields | `type="number"` |
| `CascadeField` | Fields with computed fallbacks | `type="number"` |
| `TableInput` | Compact table cells | `type="number"` |

**Never create ad-hoc `<input>` elements** for numeric data. Always use the field components.

---

## State Management Patterns

### Year Context

```typescript
interface YearContextValue {
  selectedYear: number;
  setSelectedYear: (year: number) => void;
  graphYear: number | null;  // Override for graph panel
  setGraphYear: (year: number | null) => void;
  timelineYear: number | null;  // Override for timeline panel
  setTimelineYear: (year: number | null) => void;
  effectiveGraphYear: number;  // graphYear ?? selectedYear
  effectiveTimelineYear: number;  // timelineYear ?? selectedYear
  syncGraphToTimeline: () => void;
  syncTimelineToGraph: () => void;
}

const YearContext = createContext<YearContextValue | null>(null);

const YearProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [selectedYear, setSelectedYear] = useState(2025);
  const [graphYear, setGraphYear] = useState<number | null>(null);
  const [timelineYear, setTimelineYear] = useState<number | null>(null);
  
  const value: YearContextValue = {
    selectedYear,
    setSelectedYear: (year) => {
      setSelectedYear(year);
      setGraphYear(null);  // Reset overrides
      setTimelineYear(null);
    },
    graphYear,
    setGraphYear,
    timelineYear,
    setTimelineYear,
    effectiveGraphYear: graphYear ?? selectedYear,
    effectiveTimelineYear: timelineYear ?? selectedYear,
    syncGraphToTimeline: () => setTimelineYear(graphYear ?? selectedYear),
    syncTimelineToGraph: () => setGraphYear(timelineYear ?? selectedYear),
  };
  
  return <YearContext.Provider value={value}>{children}</YearContext.Provider>;
};
```

### Config Context

```typescript
interface ConfigContextValue {
  config: ConfigState | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

const ConfigContext = createContext<ConfigContextValue | null>(null);

const ConfigProvider: React.FC<{ configDir: string; children: React.ReactNode }> = ({
  configDir,
  children,
}) => {
  const [config, setConfig] = useState<ConfigState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    const result = await loadAllConfigs(configDir);
    
    if (result.ok) {
      setConfig(result.value);
    } else {
      setError(result.error.message);
    }
    
    setLoading(false);
  }, [configDir]);
  
  useEffect(() => {
    load();
  }, [load]);
  
  return (
    <ConfigContext.Provider value={{ config, loading, error, reload: load }}>
      {children}
    </ConfigContext.Provider>
  );
};
```

---

## Optimizer Patterns

### Grid Search Implementation

```typescript
interface OptimizationResult {
  params: Record<string, number | string | boolean>;
  neb75: number;
  components: { c1: number; c2: number; c3: number };
}

const runGridSearch = async (
  model: DomainModel,
  unlockedParams: UnlockedParam[],
  config: ConfigState,
  onProgress?: (progress: number) => void
): Promise<OptimizationResult[]> => {
  // Generate all combinations
  const combinations = generateCombinations(unlockedParams);
  const results: OptimizationResult[] = [];
  
  for (let i = 0; i < combinations.length; i++) {
    const params = combinations[i];
    
    // Apply params to model
    let testModel = model;
    for (const [key, value] of Object.entries(params)) {
      const [entityId, paramName] = key.split('.');
      testModel = updateEntityParam(testModel, entityId, paramName, value);
    }
    
    // Calculate NEB75
    const neb75Result = calculateNEB75(testModel, config);
    if (neb75Result.ok) {
      results.push({
        params,
        neb75: neb75Result.value.total,
        components: neb75Result.value,
      });
    }
    
    // Report progress
    onProgress?.((i + 1) / combinations.length);
  }
  
  // Sort by NEB75 descending
  return results.sort((a, b) => b.neb75 - a.neb75);
};

const generateCombinations = (params: UnlockedParam[]): Record<string, any>[] => {
  if (params.length === 0) return [{}];
  
  const [first, ...rest] = params;
  const restCombinations = generateCombinations(rest);
  const result: Record<string, any>[] = [];
  
  // For binary_only: use min and max
  const values = first.type === 'continuous' && first.binaryOnly
    ? [first.min, first.max]
    : first.values;
  
  for (const value of values) {
    for (const restCombo of restCombinations) {
      result.push({ [first.key]: value, ...restCombo });
    }
  }
  
  return result;
};
```

---

## Testing Patterns

### Config Validation Test

```typescript
describe('Config Loading', () => {
  it('loads tax_rules.yaml without errors', async () => {
    const result = await loadYamlFile<TaxRules>(
      './config/domain/tax_rules.yaml',
      TAX_RULES_SCHEMA
    );
    
    expect(result.errors).toHaveLength(0);
    expect(result.data).not.toBeNull();
    expect(result.data?.federal_brackets.married_filing_jointly).toBeDefined();
  });
  
  it('validates cross-references in graph', async () => {
    const config = await loadAllConfigs('./config');
    
    expect(config.ok).toBe(true);
    if (config.ok) {
      // All node references in edges should exist
      for (const [, edge] of config.value.topology.graph.edges) {
        expect(config.value.topology.graph.nodes.has(edge.from)).toBe(true);
        if (edge.to) {
          expect(config.value.topology.graph.nodes.has(edge.to)).toBe(true);
        }
      }
    }
  });
});
```

### DSL Golden Test

```typescript
describe('DSL Parser', () => {
  it('parses Johns graph correctly', async () => {
    const result = await loadDSL('./config/topology/entity_graph.dsl.yaml');
    
    expect(result.errors).toHaveLength(0);
    expect(result.data?.nodes.size).toBe(10);  // Expected node count
    expect(result.data?.edges.size).toBe(8);   // Expected edge count
    
    // Specific node checks
    expect(result.data?.nodes.get('asset_portfolio')?.type).toBe('container');
    expect(result.data?.nodes.get('manco')?.subtype).toBe('scorp');
  });
});
```
