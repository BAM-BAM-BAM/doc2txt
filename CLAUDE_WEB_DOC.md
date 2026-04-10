# FGT Project Guidelines (Claude Web)

## Purpose

This file configures Claude to follow the **Francis Galton Technique (FGT)** methodology for software development. Upload this file along with the companion methodology files to your Claude web project.

**Companion files to upload:**
- `FGT.md` - Core methodology (domain-agnostic)
- `FGT_DOMAIN_*.md` - Domain-specific knowledge
- `REVIEWS_*.md` - Review checklists
- `PATTERNS_*.md` - Code patterns and conventions

---

## Core FGT Principles

### 1. Multi-Perspective Review

Before finalizing any implementation, review from multiple expert perspectives:

| Expert | Focus | Key Questions |
|--------|-------|---------------|
| Software Architect | System design, scalability | "Is this properly abstracted? Will it scale?" |
| UX/UI Designer | Usability, accessibility | "Can users accomplish their goal easily?" |
| QA Engineer | Testing, edge cases | "What could break? Is this testable?" |
| Security Reviewer | Input validation, auth | "What could be exploited? Is data protected?" |

### 2. Config-First Development

**Never hardcode business logic that can be expressed in configuration.**

Before implementing any feature, ask:
1. Can this be expressed in a config file?
2. Does the config schema already support this?
3. Would adding to config be simpler than code?

### 3. Separation of Concerns

| Concern | Location | Example |
|---------|----------|---------|
| Business rules | Domain config | Validation rules, limits |
| Data structure | Schema config | Types, relationships |
| Display formatting | UI config | Labels, tooltips, formats |
| User settings | User config | Preferences, defaults |

**Never mix concerns.** Business rules don't care about button colors.

### 4. Percentage Storage Convention

**All percentages are stored as decimals (0.75 = 75%).**

| Storage | Display | Meaning |
|---------|---------|---------|
| `0.75` | `75%` | 75 percent |
| `0.085` | `8.5%` | 8.5 percent |
| `0.04` | `4%` | 4 percent |

### 5. Invariant Extraction

**When changing business logic, extract invariants that can be tested.**

Process:
1. Ask: "What would make this wrong? What must always be true?"
2. For each perspective, identify invariants:
   - Architect: "Components must not have circular dependencies"
   - UX: "Loading states must be shown for async operations"
   - QA: "All inputs must be validated before processing"
   - Security: "User data must be sanitized before storage"
3. Document invariants alongside implementation
4. Invariants become automated tests

---

## Task Execution Flow
```
1. Understand the task requirements
2. Identify which review types apply (see REVIEWS_*.md)
3. Load domain-specific rules (see FGT_DOMAIN_*.md)
4. PRE-IMPLEMENTATION CHECK:
   - Does this already exist?
   - Can this be config-driven?
   - What validation is needed?
5. Implement the solution
6. Run applicable reviews from each perspective
7. Extract invariants from business logic changes
8. Verify edge cases handled
```

---

## Expert Perspectives (Generic)

### Software Architect Perspective
- Verify proper separation of concerns
- Check for code duplication
- Validate abstraction levels
- Ensure scalability considerations
- Review error handling strategy

### UX/UI Designer Perspective
- Verify consistent visual patterns
- Check accessibility (keyboard nav, ARIA, color contrast)
- Validate loading and error states
- Ensure responsive behavior
- Review user feedback mechanisms

### QA Engineer Perspective
- Identify edge cases (null, empty, boundary values)
- Verify error messages are helpful
- Check that tests cover new functionality
- Validate regression risk
- Review integration points

### Security Reviewer Perspective
- Check input validation and sanitization
- Verify authentication/authorization
- Review data exposure risks
- Validate secure defaults
- Check for injection vulnerabilities

---

## Code Patterns (Quick Reference)

### Naming
- Components: PascalCase (`UserCard`, `ConfigPanel`)
- Functions: camelCase (`fetchData`, `parseConfig`)
- Constants: SCREAMING_SNAKE (`MAX_RETRIES`, `DEFAULT_TIMEOUT`)
- Config keys: snake_case (`api_endpoint`, `retry_count`)

### Data Flow
```
Config -> Parser -> Domain Model -> UI State -> Components
              |
          Validation at each step
```

### Error Handling
- Validate early, fail fast
- Provide context in error messages
- Never swallow errors silently
- Log for debugging, display for users

---

## Common Mistakes to Avoid

| Mistake | Why It's Wrong | Correct Approach |
|---------|----------------|------------------|
| Hardcoded values | Can't update without code change | Use config files |
| Mixing display and logic | Tight coupling, hard to test | Separate concerns |
| Skipping reviews | Miss bugs and edge cases | Always multi-perspective review |
| Inconsistent UI patterns | Poor UX, maintenance burden | Follow established patterns |
| Missing edge cases | Runtime errors | Test null, empty, boundary values |
| No loading states | Poor perceived performance | Show feedback for async ops |

---

## When to Escalate

Request human review when:
- Adding entirely new business rules
- Major refactor of core logic
- Uncertainty about requirements
- Multiple valid approaches with trade-offs
- Security-sensitive changes
- Breaking API changes

---

## File Reference

| File | Purpose | When to Consult |
|------|---------|-----------------|
| `FGT.md` | Core methodology | Understanding the approach |
| `FGT_DOMAIN_*.md` | Domain rules | Domain-specific logic |
| `REVIEWS_*.md` | Review checklists | Before finalizing any change |
| `PATTERNS_*.md` | Code patterns | Writing new code |
