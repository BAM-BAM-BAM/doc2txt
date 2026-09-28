#!/bin/bash
# Shared derivation for the FGT session hooks. Sourced, never executed.
#
# Claude Code names a project's memory directory after the checkout path with
# EVERY non-alphanumeric character replaced by a dash — not only the
# separators. Deriving it at runtime keeps the rule true in any clone;
# rendering it as a literal baked one developer's checkout path into the
# repository and silently wrote to the wrong directory everywhere else.
#
# Enumerating separators instead has cost two bugs in the estate: '/' and '_'
# only stranded 54 memories of one project on 2026-07-16, and adding '_'
# still left dots intact until 2026-07-29. Match the whole class, never the
# character that last broke.
#
# The sed class below must stay byte-identical to the estate's canonical
# producer (fgt-config scripts/fgt-memory-dir.sh); test-new-project.sh
# asserts the pair. Do not "fix" it here alone.

FGT_PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEMORY_DIR="$HOME/.claude/projects/$(printf '%s' "$FGT_PROJECT_DIR" | sed 's/[^a-zA-Z0-9]/-/g')/memory"
