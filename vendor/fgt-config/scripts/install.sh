#!/bin/bash
# install.sh — Deploy fgt-config methodology files to ~/.claude/fgt/
#
# Model: copy-based install target, NOT a git clone. Mirrors the existing
# install-ocd.sh pattern. Makes ~/.claude/fgt/ a pure artifact of this
# script — any edits made there will be overwritten on the next run.
# Canonical source of truth lives in this repository only.
#
# What gets deployed:
#   ~/.claude/fgt/FGT.md                             (methodology)
#   ~/.claude/fgt/METHODOLOGY_LOG.md                 (evolution history)
#   ~/.claude/fgt/FGT_NEW_PROJECT_CHECKLIST.md       (bootstrap guide)
#   ~/.claude/fgt/fgt_cross_project_retrospective_v2.md  (CP-XXX evidence)
#   ~/.claude/fgt/README.md                          (orientation; includes For Claude Web Projects)
#   ~/.claude/fgt/scripts/*                          (executable helpers)
#   ~/.claude/fgt/templates/                         (generic project templates)
#
# What gets preserved across re-runs:
#   ~/.claude/fgt/guard.log                          (runtime output)
#
# What does NOT get deployed:
#   Repo dev files (.git, .github, .githooks, .gitignore, node_modules,
#   package.json, package-lock.json, BACKLOG.md, TASKS.md, .markdownlint*)

set -euo pipefail

# Resolve repo root from script location (scripts/install.sh -> repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="$HOME/.claude/fgt"

# Sanity: require the source to look like fgt-config
if [ ! -f "$REPO_ROOT/FGT.md" ] || [ ! -d "$REPO_ROOT/templates" ]; then
    echo "ERROR: $REPO_ROOT does not look like fgt-config (missing FGT.md or templates/)" >&2
    exit 1
fi

echo "Installing fgt-config → $TARGET"
echo "Source: $REPO_ROOT"

# Preserve runtime log across re-installs
TMPLOG=""
if [ -f "$TARGET/guard.log" ]; then
    TMPLOG="$(mktemp)"
    cp "$TARGET/guard.log" "$TMPLOG"
    echo "  preserved: guard.log ($(wc -l < "$TMPLOG") line(s))"
fi

# Nuke any existing install target — install.sh OWNS this directory
rm -rf "$TARGET"
mkdir -p "$TARGET/scripts" "$TARGET/templates"

# Copy methodology documents
for doc in FGT.md METHODOLOGY_LOG.md FGT_NEW_PROJECT_CHECKLIST.md \
           fgt_cross_project_retrospective_v2.md README.md; do
    if [ -f "$REPO_ROOT/$doc" ]; then
        cp "$REPO_ROOT/$doc" "$TARGET/$doc"
    fi
done

# Copy scripts, preserve executability
cp "$REPO_ROOT/scripts/"* "$TARGET/scripts/"
chmod +x "$TARGET/scripts/"*.sh 2>/dev/null || true

# Copy templates (includes the scaffold/ subtree)
cp -r "$REPO_ROOT/templates/"* "$TARGET/templates/"

# Restore runtime log
if [ -n "$TMPLOG" ] && [ -f "$TMPLOG" ]; then
    cp "$TMPLOG" "$TARGET/guard.log"
    rm -f "$TMPLOG"
fi

echo "  methodology + scripts + templates installed."

# --- Chain install-ocd.sh for Stop-hook deployment ---
# install-ocd.sh deploys ocd-sweep.sh to ~/.claude/scripts/ (the path the
# global Stop hook in settings.json references) and ensures the hook is
# wired. Chaining here means a single `bash install.sh` delivers the full
# methodology + operational surface in one step.
if [ -x "$REPO_ROOT/scripts/install-ocd.sh" ]; then
    echo ""
    echo "Chaining install-ocd.sh for Stop-hook deployment..."
    bash "$REPO_ROOT/scripts/install-ocd.sh"
fi

echo ""
echo "Install complete."
echo ""
echo "Verify deployment:"
echo "  test -f $TARGET/FGT.md && echo '  FGT.md OK'"
echo "  test -x $TARGET/scripts/new-project.sh && echo '  new-project.sh OK'"
echo "  test -x $TARGET/scripts/ocd-sweep.sh && echo '  ocd-sweep.sh OK'"
echo "  test -x $TARGET/scripts/fgt-guard-write.sh && echo '  fgt-guard-write.sh OK'"
echo "  test -x $HOME/.claude/scripts/ocd-sweep.sh && echo '  Stop-hook ocd-sweep OK'"
