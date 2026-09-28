#!/bin/bash
# FGT PreCompact / SessionEnd hook — auto-snapshots session state to disk
# before context compaction silently drops it.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$(dirname "$0")/fgt_common.sh"
SESSION_MARKER="$MEMORY_DIR/.session_start"
STAGING_FILE="$MEMORY_DIR/session_staging.md"
EVENT="${CLAUDE_HOOK_EVENT:-PreCompact}"

mkdir -p "$MEMORY_DIR"

{
    echo "# Pre-Compaction Staging (auto-captured)"
    echo "Captured at: $(date -Iseconds)"
    echo "Event: $EVENT"
    echo ""
    echo "## Git Changes This Session"
    if [ -f "$SESSION_MARKER" ]; then
        SESSION_START=$(cat "$SESSION_MARKER")
        echo "### Commits since session start ($SESSION_START):"
        git -C "$PROJECT_DIR" log --oneline --since="$SESSION_START" 2>/dev/null || echo "(none)"
    fi
    echo ""
    echo "### Working tree status:"
    git -C "$PROJECT_DIR" status --short 2>/dev/null || echo "(unavailable)"
    echo ""
    echo "## Test State"
    echo "(not captured — the suite is not run here: unbounded runtime at the"
    echo "worst moment, and no consumer of the tail was ever observed. To"
    echo "restore, add an opt-in runner under a timeout.)"
} > "$STAGING_FILE" 2>/dev/null || true

if [ "$EVENT" = "PreCompact" ]; then
    echo "CONTEXT COMPACTION IMMINENT — persist learnings to BUG_PATTERNS_DOC.md, BACKLOG.md, and memory files."
elif [ "$EVENT" = "SessionEnd" ]; then
    echo "SESSION ENDING — verify all learnings were persisted."
    echo "Check: were any decisions, bug fixes, or patterns from this session"
    echo "written to BUG_PATTERNS_DOC.md, BACKLOG.md, or memory files?"
fi
