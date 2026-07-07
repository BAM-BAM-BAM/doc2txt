# Config Structure — {{PROJECT}}

## File Separation (from Day 1)

Split config by concern. Max 200 lines per file.

```text
config/
  settings.yaml       # Global: timeouts, rate limits, paths
  sources.yaml         # External source/integration configs
  {{DOMAIN}}.yaml      # Domain-specific constants and rules
  preferences.yaml     # User-facing preferences
```

## Typed Validation

All config loaded via typed loader (Pydantic model, dataclass, or equivalent).
Never use raw `yaml.safe_load()` dicts in application code.

```python
from pydantic import BaseModel

class {{DOMAIN}}Config(BaseModel):
    # Define typed fields here
    pass

def load_config(path: str) -> {{DOMAIN}}Config:
    import yaml
    with open(path) as f:
        return {{DOMAIN}}Config(**yaml.safe_load(f))
```

Write an `INV-*` test that loads config and asserts expected types:

```python
def test_config_types():
    """INV-0XX: Config values have correct types after loading."""
    config = load_config("config/{{DOMAIN}}.yaml")
    # Assert types, ranges, and constraints here
```

## YAML Safety Rules

- Quote all values that look numeric but are identifiers: `'5513'` not `5513`
- Quote values with trailing zeros: `'2531.80'` not `2531.80`
- Never embed credentials (use `.env` or environment variables)
- Test round-trip stability: `yaml.dump(yaml.safe_load(text)) == text`

### Common YAML Type Inference Pitfalls

| You write | YAML parses as | Fix |
|-----------|---------------|-----|
| `5513` | int 5513 | `'5513'` (quote it) |
| `2531.80` | float 2531.8 (trailing zero lost) | `'2531.80'` (quote it) |
| `yes` / `no` | boolean true/false | `'yes'` / `'no'` (quote it) |
| `1.0e3` | float 1000.0 | `'1.0e3'` (quote it if string intended) |

## {{DOMAIN}}-Specific Config Notes

<!-- Add domain-specific config patterns, required fields, or validation rules here. -->
