# pdf2txt - Claude Code Instructions

## Project Overview
PDF text extraction tool.

## FGT Methodology

This project follows the **Francis Galton Technique (FGT)**. Before making changes:

1. **Read** `FGT.md` for the 5-pillar methodology
2. **Consult** `FGT_DOMAIN_PDF.md` for PDF-specific domain knowledge
3. **Review** `PATTERNS_PDF.md` for code patterns
4. **Check** `REVIEWS_PDF.md` for review checklists

## Development Workflow

### Before Implementation
- Understand the task
- Check if similar functionality exists
- Review domain rules in `FGT_DOMAIN_PDF.md`

### During Implementation
- Follow patterns in `PATTERNS_PDF.md`
- Apply multi-perspective review (Software Architect, QA Engineer, Document Analyst)
- Extract invariants from business logic

### After Implementation
- Run applicable reviews from `REVIEWS_PDF.md`
- Update `FGT_LOG.md` with lessons learned
- Ensure tests pass before committing

## Domain Expert Perspectives

When reviewing changes, consider:

| Expert | Key Questions |
|--------|---------------|
| **Software Architect** | Is this properly abstracted? Separation of concerns? |
| **QA Engineer** | What edge cases exist? Malformed PDFs? Empty files? |
| **Document Analyst** | Is text fidelity preserved? Reading order correct? |
| **Data Engineer** | Does it scale? How are large files handled? |

## Key Files

| File | Purpose |
|------|---------|
| `FGT.md` | Core methodology |
| `FGT_DOMAIN_PDF.md` | PDF-specific domain knowledge |
| `PATTERNS_PDF.md` | Code patterns for this project |
| `REVIEWS_PDF.md` | Review checklists |
| `FGT_LOG.md` | Development history and lessons |
| `CLAUDE_WEB_PDF.md` | For Claude web project uploads |

## Quick Reference
```
FGT Cycle:
1. UNDERSTAND  → Read task, check existing code, load domain knowledge
2. IMPLEMENT   → Follow patterns, handle edge cases
3. VERIFY      → Run reviews, test edge cases
4. COMMIT      → Update FGT_LOG if lessons learned

Bug Response:
1. FIX         → Implement the fix
2. ASK         → "Why didn't FGT prevent this?"
3. AUTOMATE    → Add test or invariant
4. DOCUMENT    → Update FGT_DOMAIN_PDF.md if domain-specific
```
