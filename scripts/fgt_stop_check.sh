#!/bin/bash
# FGT Stop hook — blocks the assistant's response (exit 2) if session commits
# landed without the tracking docs moving. Detection is git-evidence-based
# (commits + working-tree content changes), not mtime: a bare `touch` produces
# no porcelain entry and satisfies nothing. Memory files live outside the repo,
# so their satisfier remains mtime — the best signal available there.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$(dirname "$0")/fgt_common.sh"
SESSION_MARKER="$MEMORY_DIR/.session_start"
BUG_PATTERNS_PATH="$PROJECT_DIR/BUG_PATTERNS_DOC.md"
BACKLOG_PATH="$PROJECT_DIR/BACKLOG.md"
DOCS_REGEX='^(BUG_PATTERNS_DOC|BACKLOG)\.md$'
COMMIT_THRESHOLD=3
CRITICAL_DIRS="src"

# Re-entry guard: when a previous exit 2 already blocked this Stop, the harness
# refires with stop_hook_active=true — blocking again would loop forever.
# jq-free fallback so the guard holds on machines without jq.
if [ ! -t 0 ]; then
    STOP_PAYLOAD="$(timeout 1 cat 2>/dev/null || true)"
    if [ -n "${STOP_PAYLOAD:-}" ]; then
        if command -v jq >/dev/null 2>&1; then
            if printf '%s' "$STOP_PAYLOAD" | jq -e '.stop_hook_active == true' >/dev/null 2>&1; then
                exit 0
            fi
        elif printf '%s' "$STOP_PAYLOAD" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
            exit 0
        fi
    fi
fi

[ -f "$SESSION_MARKER" ] || exit 0
# Unborn HEAD (scaffolded, nothing committed yet): git log exits 128 under
# pipefail and there is no session activity to police — pass silently.
git -C "$PROJECT_DIR" rev-parse --verify -q HEAD >/dev/null 2>&1 || exit 0

SESSION_START=$(cat "$SESSION_MARKER")
COMMIT_COUNT=$(git -C "$PROJECT_DIR" log --oneline --since="$SESSION_START" 2>/dev/null | wc -l)
COMMIT_COUNT=${COMMIT_COUNT:-0}

SESSION_EPOCH=$(date -d "$SESSION_START" +%s 2>/dev/null) || exit 0

# "Measure before you block" (FGT.md): every block leaves a countable record.
# Consumer: the BACKLOG evaluation item reviews line counts; sunset if ~0.
log_block() {
    echo "$(date -Iseconds) $1" >> "$MEMORY_DIR/stop_check_blocks.log" 2>/dev/null || true
}

changed_in_session() {
    git -C "$PROJECT_DIR" log --since="$SESSION_START" --name-only --pretty=format: 2>/dev/null \
        | grep -qE "$1"
}

worktree_modified() {
    [ -n "$(git -C "$PROJECT_DIR" status --porcelain -- "$@" 2>/dev/null)" ]
}

# Memory files are outside the repo: mtime is the only available signal.
is_updated_since_session() {
    local f="$1"
    [ -f "$f" ] || return 1
    local file_epoch
    file_epoch=$(stat -c '%Y' "$f" 2>/dev/null) || return 1
    [ "$file_epoch" -gt "$SESSION_EPOCH" ]
}

DOCS_TOUCHED=false
if worktree_modified "$BUG_PATTERNS_PATH" "$BACKLOG_PATH"; then
    DOCS_TOUCHED=true
elif changed_in_session "$DOCS_REGEX"; then
    DOCS_TOUCHED=true
fi

TRACKING_UPDATED=$DOCS_TOUCHED
if [ "$TRACKING_UPDATED" = false ] && [ -d "$MEMORY_DIR" ]; then
    for f in "$MEMORY_DIR"/*.md; do
        is_updated_since_session "$f" && TRACKING_UPDATED=true && break
    done
fi

# --- CHECK 1: commit volume without tracking ---
if [ "$COMMIT_COUNT" -ge "$COMMIT_THRESHOLD" ] && [ "$TRACKING_UPDATED" = false ]; then
    log_block "CHECK1 $COMMIT_COUNT commits, no tracking update"
    echo "FGT ENFORCEMENT: $COMMIT_COUNT commits without updating tracking files." >&2
    echo "Update BUG_PATTERNS_DOC.md, BACKLOG.md, or memory files." >&2
    exit 2
fi

# --- CHECK 2: critical-dir commits without tracking ---
if [ "$COMMIT_COUNT" -gt 0 ] && [ "$TRACKING_UPDATED" = false ]; then
    for dir in $CRITICAL_DIRS; do
        if changed_in_session "^$dir/"; then
            log_block "CHECK2 $dir/ committed, no tracking update"
            echo "FGT ENFORCEMENT: commit touched '$dir/' without updating tracking files." >&2
            exit 2
        fi
    done
fi

# --- CHECK 3: tests + tracking-doc abstraction ---
# Test commits without a tracking-doc change suggest Bug Abstraction step 3
# was skipped (bug-fix test, no BUG entry) or a feature test landed with no
# BACKLOG entry. Either doc satisfies; an uncommitted working-tree edit
# counts (docs typically ride the next commit — committed-only reading
# deadlocked a parked session in the field, 2026-07-17).
if [ "$COMMIT_COUNT" -gt 0 ] && changed_in_session '^tests/' && [ "$DOCS_TOUCHED" = false ]; then
    log_block "CHECK3 tests/ committed, no tracking doc"
    echo "FGT ABSTRACTION: test files modified but no tracking doc" >&2
    echo "(BUG_PATTERNS_DOC.md or BACKLOG.md) updated." >&2
    exit 2
fi

# --- CHECK 4: scope alignment (SPEC.md vs implementation) ---
# Src commits without a SPEC change block once per session. The check cannot
# tell a contract change from an internal fix, so a session that verified
# "no drift" records that instead of editing SPEC.md — the escape is an
# explicit verification, not spec churn. Marker content must equal the
# current SESSION_START; stale markers never carry over.
if [ -f "$PROJECT_DIR/SPEC.md" ] && [ "$COMMIT_COUNT" -gt 0 ] && changed_in_session '^src/'; then
    if ! changed_in_session '^SPEC\.md$' && ! worktree_modified "$PROJECT_DIR/SPEC.md"; then
        # --absolute-git-dir: correct in linked worktrees, where .git is a file
        GIT_DIR=$(git -C "$PROJECT_DIR" rev-parse --absolute-git-dir 2>/dev/null) || GIT_DIR="$PROJECT_DIR/.git"
        SPEC_VERIFIED_MARKER="$GIT_DIR/spec-drift-verified"
        if [ -f "$SPEC_VERIFIED_MARKER" ] \
            && [ "$(cat "$SPEC_VERIFIED_MARKER" 2>/dev/null)" = "$SESSION_START" ]; then
            :  # verified no-drift this session
        else
            log_block "CHECK4 src/ committed, SPEC.md unchanged, no ack"
            echo "FGT SCOPE CHECK: src/ files changed but SPEC.md not updated this session." >&2
            echo "Verify SPEC.md matches implementation, then EITHER update SPEC.md," >&2
            echo "OR record the verified no-drift for this session:" >&2
            echo "  cat '$SESSION_MARKER' > '$SPEC_VERIFIED_MARKER'" >&2
            exit 2
        fi
    fi
fi

exit 0
