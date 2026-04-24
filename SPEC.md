# SPEC (pointer)

The system purpose, scope, and architecture for doc2txt live in
`README.md`. doc2txt is a focused single-process tool
(PDF/DOCX/DOC/RTF/ODT → markdown conversion via PyMuPDF + OCR fallback
via Surya); the README covers purpose, supported formats, CLI options,
and the adaptive OCR learning system.

Additional design docs:
- `FGT_DOMAIN_DOC.md` — domain knowledge (document processing invariants)
- `PATTERNS_DOC.md` — code patterns specific to this project
- `BUG_PATTERNS_DOC.md` — bug catalog

This file exists to satisfy the FGT validator's `SPEC.md` requirement.
