# {{PROJECT}} Expert Reviewers

Automated tests encoding domain stakeholder perspectives. Each test class
embodies a specific expert's concerns — the tests ask "What would this
expert reject?"

See FGT.md § Test Categories (`REV-*`).

---

## Why Expert Reviewers?

Proactive tests (PRO-\*) detect **structural** anti-patterns in code.
Expert Review tests (REV-\*) validate **semantic** correctness from a domain
expert's perspective. The distinction matters:

- PRO-\* catches: hardcoded refs, dead params, satellite state
- REV-\* catches: "distributions during construction = wrong", "DSCR below
  minimum = reject", "prohibited certainty language in projections"

No structural scan finds these. They require domain knowledge encoded as tests.

---

## Choosing Reviewers

Pick 3-5 stakeholders who would review your deliverables in production:

| Reviewer Type | Example Domain | Catches |
|---------------|---------------|---------|
| **Domain Expert** | Industry analyst, subject-matter expert | Logic errors, unrealistic assumptions, missing industry standards |
| **Compliance/Legal** | Securities counsel, regulator, auditor | Prohibited language, missing disclaimers, misleading projections |
| **Operations** | End user, operator, field engineer | Usability issues, unrealistic parameters, missing edge cases |
| **Quality Assurance** | QA engineer, test lead | Coverage gaps, hardcoded shortcuts, untested invariants |
| **External Stakeholder** | Lender, investor, customer | Inconsistent totals, missing reconciliation, implausible outputs |

---

## Test Structure

```python
# test_expert_reviewers.py

class TestDomainExpertReviewer:
    """REV-DE: Domain expert perspective — catches semantic domain errors.

    Expert persona: [describe the expert's role and what they care about]
    """

    def test_rev_de_001_description(self, built_output):
        """REV-DE-001: [What the expert would check]."""
        # Validate from the expert's perspective
        assert ...

class TestComplianceReviewer:
    """REV-CL: Compliance/legal perspective — catches regulatory issues.

    Expert persona: [describe the reviewer's concerns]
    """

    def test_rev_cl_001_no_prohibited_language(self, output_text):
        """REV-CL-001: No certainty language in projections."""
        prohibited = ["guaranteed", "will achieve", "assured", "certain"]
        for term in prohibited:
            assert term.lower() not in output_text.lower(), \
                f"Prohibited term '{term}' found in output"
```

### Naming Convention

- Class: `Test<Role>Reviewer` with docstring referencing `REV-<ABBREV>`
- Method: `test_rev_<abbrev>_NNN_<description>`
- Abbreviations: 2-letter codes (DE=Domain Expert, CL=Compliance, OP=Operations, QA=Quality, XS=External Stakeholder)

---

## Building a Reviewer

For each expert, ask:

1. **What would they check first?** (the "deal-breaker" tests)
2. **What would make them reject the deliverable?** (hard failures)
3. **What would they flag as concerning?** (warnings, not failures)
4. **What cross-checks would they run?** (reconciliation, consistency)

Encode deal-breakers as `assert`. Encode concerns as `warnings.warn()`.

---

## Integration with FGT_DOMAIN

The `FGT_DOMAIN_*.md` file has an "Expert Perspectives" section (see
`FGT_DOMAIN_TEMPLATE.md`). Use it to document **what each expert cares about**
in prose. Then encode those concerns as REV-\* tests.

The domain doc is the specification; the tests are the enforcement.
