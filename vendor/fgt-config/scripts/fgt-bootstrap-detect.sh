#!/bin/bash
# fgt-bootstrap-detect.sh — Global SessionStart hook for Claude Code.
#
# Detects whether the current project directory needs FGT bootstrapping.
# Outputs instructions for Claude if bootstrapping is needed.
# Does NOT auto-run new-project.sh — Claude must do the cross-project
# analysis first (per FGT Principle 10: Scaffold Before Building).
#
# Install: Add to ~/.claude/settings.json SessionStart hooks.
# See FGT_NEW_PROJECT_CHECKLIST.md § Automatic Bootstrapping.
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# --- Guard: skip if already FGT-bootstrapped ---
if [ -f "$PROJECT_DIR/FGT.md" ] || [ -L "$PROJECT_DIR/FGT.md" ]; then
    exit 0
fi
if [ -f "$PROJECT_DIR/CLAUDE.md" ] && grep -q "FGT\|Bug Abstraction\|Prevention Principles" "$PROJECT_DIR/CLAUDE.md" 2>/dev/null; then
    exit 0
fi

# --- Guard: skip if this IS the fgt-config repo ---
if [ -d "$PROJECT_DIR/templates" ] && [ -f "$PROJECT_DIR/templates/PATTERNS_TEMPLATE.md" ]; then
    exit 0
fi

# --- Guard: only trigger for directories under ~/projects/ ---
case "$PROJECT_DIR" in
    "$HOME/projects/"*) ;;
    "$HOME/projects")
        # Parent directory — scan for un-scaffolded child projects
        UNSCAFFOLDED=""
        for child in "$HOME/projects"/*/; do
            [ -d "$child" ] || continue
            child_name=$(basename "$child")
            # Skip if FGT-bootstrapped
            [ -f "$child/FGT.md" ] || [ -L "$child/FGT.md" ] && continue
            # Skip if CLAUDE.md mentions FGT
            [ -f "$child/CLAUDE.md" ] && grep -q "FGT\|Bug Abstraction\|Prevention Principles" "$child/CLAUDE.md" 2>/dev/null && continue
            # Skip if fgt-config repo
            [ -d "$child/templates" ] && [ -f "$child/templates/PATTERNS_TEMPLATE.md" ] && continue
            # Skip if opted out
            [ -f "$child/.fgt-exempt" ] && [ -s "$child/.fgt-exempt" ] && continue
            UNSCAFFOLDED="$UNSCAFFOLDED $child_name"
        done
        if [ -z "$UNSCAFFOLDED" ]; then
            exit 0
        fi
        echo "NEW PROJECT(S) DETECTED — FGT bootstrapping required for:$UNSCAFFOLDED"
        echo ""
        echo "Per FGT Principle 10, scaffold BEFORE writing features."
        echo "Run:  ~/.claude/fgt/scripts/new-project.sh ~/projects/<name> <DOMAIN> --lang py|ts"
        echo "Or opt out:  echo 'reason' > ~/projects/<name>/.fgt-exempt"
        exit 0
        ;;
    *) exit 0 ;;
esac

# --- Output bootstrapping instructions ---
echo "NEW PROJECT DETECTED — FGT bootstrapping required."
echo ""
echo "This directory ($PROJECT_DIR) does not have FGT files."
echo "Per FGT Principle 10 (Scaffold Before Building), set up FGT"
echo "BEFORE writing the first feature."
echo ""
echo "BOOTSTRAPPING PROTOCOL:"
echo "1. Read ~/.claude/fgt/FGT.md for methodology reference"
echo "2. Read ~/.claude/fgt/fgt_cross_project_retrospective_v2.md for cross-project lessons"
echo "3. Read ~/.claude/fgt/FGT_NEW_PROJECT_CHECKLIST.md for the Day 1 checklist"
echo "4. Ask the user for the DOMAIN suffix (project name or domain keyword)"
echo "5. Run: ~/.claude/fgt/scripts/new-project.sh \$CLAUDE_PROJECT_DIR <DOMAIN>"
echo "6. Replace remaining {{placeholders}} in CLAUDE.md"
echo "7. Write domain-specific content FROM SCRATCH in FGT_DOMAIN_<DOMAIN>.md"
echo "8. Create .claude/settings.json with SessionStart/PreCompact/Stop/SessionEnd hooks"
echo "9. Create scripts/fgt_session_start.sh, fgt_session_persist.sh, fgt_stop_check.sh"
echo "10. Create test directory structure (tests/)"
echo "11. Create scripts/git-hooks/pre-commit + scripts/install-hooks.sh"
echo "12. Create package.json (or pyproject.toml) with test/lint/build scripts"
echo "13. Initial commit + run install-hooks.sh"
echo ""
echo "KEY LESSONS FROM CROSS-PROJECT ANALYSIS:"
echo "- Domain files MUST be written from scratch, NOT copied (doc2txt cargo-cult anti-pattern)"
echo "- CI steps must NOT use continue-on-error for blocking checks (av226 BUG-029: 33-day hollow defense)"
echo "- BACKLOG.md is mandatory from Day 1 (Principle 9: Findings Must Be Tracked)"
echo "- Enforcement hierarchy: branch protection > CI > hooks > scripts > docs"
echo "- All FGT files must exist BEFORE the first feature (Principle 10)"
echo "- NEB75 lesson: 'MANDATORY' in docs has 100% skip rate without automation"
echo ""
echo "See ~/.claude/CLAUDE.md § FGT Bootstrapping Protocol for full details."
