# FGT Domain Knowledge: PDF Processing

This file contains domain-specific knowledge for PDF text extraction.
It supplements the generic FGT methodology defined in [FGT.md](FGT.md).

---

## Domain Expert Perspectives

| Perspective | Role | Focus Areas | Key Questions |
|-------------|------|-------------|---------------|
| **Document Analyst** | Content extraction | Text fidelity, structure | "Is all text captured? Is structure preserved?" |
| **OCR Specialist** | Image-to-text | Recognition accuracy | "Are scanned pages handled? What about fonts?" |
| **Data Engineer** | Pipeline design | Performance, errors | "Does it scale? How are failures handled?" |

---

## Domain-Specific Rules

### Text Extraction
- Preserve reading order (columns, tables)
- Handle embedded fonts correctly
- Extract metadata (title, author, dates)

### Error Handling
- Corrupted PDFs should fail gracefully
- Password-protected files need clear error messages
- Large files need progress indication

---

## Domain-Specific Bug Patterns

(Add patterns as discovered during development)

---

## Integration with Generic FGT

1. Use Software Architect perspective for code structure
2. Use QA Engineer perspective for edge cases (malformed PDFs)
3. Add domain-specific invariants here as discovered
