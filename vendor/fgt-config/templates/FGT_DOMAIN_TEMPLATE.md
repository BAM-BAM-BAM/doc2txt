# {{PROJECT}} Domain Knowledge

Domain-specific rules, terminology, and constraints for {{PROJECT}}.

This file answers: "What must always be true in this domain?" and "What terms
do we use and what do they mean?" Everything here should eventually become an
automated test (INV-\* prefix).

## Terminology

Define domain terms used in the codebase. Prevents terminology drift.

| Term | Definition |
|------|-----------|

## Invariants

Rules that must always hold, regardless of inputs. Each maps to an INV-\* test.

| ID | Rule | Constraint |
|----|------|-----------|

## Domain Constants

Values from external authority (regulations, standards). Not project-configurable.

| Constant | Value | Source |
|----------|-------|--------|

## Expert Perspectives

Stakeholder viewpoints to consider during development. Who would catch a mistake here?

## Pitfalls

Domain-specific mistakes that aren't obvious from the code.

## Canonical Data Formats

Every data type with multiple possible representations must have ONE canonical
storage format. Validate at ingestion. Convert only at display.
See PATTERNS_TEMPLATE § Format Canonicalization for the enforcement pattern.

| Data Type | Canonical Format | Example | Validation Rule |
|-----------|-----------------|---------|-----------------|
| {{DOMAIN}} percentage | | | |
| {{DOMAIN}} currency | | | |
| {{DOMAIN}} date | | | |
| {{DOMAIN}} identifier | | | |
