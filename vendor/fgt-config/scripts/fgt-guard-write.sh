#!/bin/bash
# fgt-guard-write.sh — PreToolUse hook for Write|Edit.
#
# Blocks file writes when PWD is inside an un-scaffolded project
# under ~/projects/. Claude Code does not pass file_path to hooks,
# so we use PWD as a proxy for which project is active.
#
# Opt-out: create a non-empty .fgt-exempt file in the project root.
#   echo "throwaway experiment" > ~/projects/myproject/.fgt-exempt
#
# Install: Add to ~/.claude/settings.json PreToolUse hooks (matcher: Write|Edit).
set -euo pipefail

GUARD_LOG="$HOME/.claude/fgt/guard.log"

# --- Only enforce when PWD is under ~/projects/<something> ---
case "$PWD" in
    "$HOME/projects/"*) ;;
    *) exit 0 ;;
esac

# --- Extract project directory (first dir under ~/projects/) ---
REL="${PWD#$HOME/projects/}"
PROJECT_NAME="${REL%%/*}"

if [ -z "$PROJECT_NAME" ]; then
    # PWD is ~/projects/ itself, not a subdirectory — allow
    exit 0
fi

PROJECT_DIR="$HOME/projects/$PROJECT_NAME"

# --- Skip if project has opted out of FGT (non-empty .fgt-exempt required) ---
if [ -f "$PROJECT_DIR/.fgt-exempt" ] && [ -s "$PROJECT_DIR/.fgt-exempt" ]; then
    exit 0
fi

# --- Skip if already FGT-bootstrapped ---
if [ -f "$PROJECT_DIR/FGT.md" ] || [ -L "$PROJECT_DIR/FGT.md" ]; then
    exit 0
fi

# --- Skip if CLAUDE.md mentions FGT ---
if [ -f "$PROJECT_DIR/CLAUDE.md" ] && grep -q "FGT\|Bug Abstraction\|Prevention Principles" "$PROJECT_DIR/CLAUDE.md" 2>/dev/null; then
    exit 0
fi

# --- BLOCK ---
echo "[$(date -Is)] BLOCKED Write/Edit in $PROJECT_DIR (PWD=$PWD)" >> "$GUARD_LOG"
echo "[FGT] BLOCKED: $PROJECT_DIR has no FGT.md and no .fgt-exempt file." >&2
echo "" >&2
echo "Principle 10: Scaffold Before Building." >&2
echo "Run:  ~/.claude/fgt/scripts/new-project.sh $PROJECT_DIR <DOMAIN> --lang py|ts" >&2
echo "Or opt out (reason required):" >&2
echo "  echo 'throwaway experiment' > $PROJECT_DIR/.fgt-exempt" >&2
exit 2
