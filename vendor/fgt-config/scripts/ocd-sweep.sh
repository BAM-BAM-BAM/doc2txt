#!/bin/bash
# ocd-sweep.sh — Operational Completion Discipline sweep runner.
#
# Canonical source: fgt-config/scripts/ocd-sweep.sh
# Deployed to:      ~/.claude/scripts/ocd-sweep.sh  (by install-ocd.sh)
# Called by:        Stop hook in ~/.claude/settings.json
#
# Checks operational health at session boundaries. Outputs PASS/WARN/FAIL
# per check. Exits 0 on all-PASS or WARN-only; exits 2 on any FAIL
# (blocks the agent's response via Stop hook exit-code semantics).
#
# Project-specific checks: if $CLAUDE_PROJECT_DIR/scripts/sweep.sh exists,
# it is sourced. That file may define arrays:
#   SWEEP_PROCESSES=("label:pgrep_pattern" ...)
#   SWEEP_DATA_CHECKS=("label:sql_query:threshold" ...)
#   SWEEP_DB="path/to/db"
# The generic runner handles git, BACKLOG, and delegates to those arrays.

set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
HAS_FAIL=false

# --- Output helpers ---
pass() { echo "[PASS] $1"; }
warn() { echo "[WARN] $1"; }
fail() { echo "[FAIL] $1"; echo "[FAIL] $1" >&2; HAS_FAIL=true; }

# ============================================================
# Generic checks (every project)
# ============================================================

# 1. Uncommitted files
cd "$PROJECT_DIR" 2>/dev/null || { warn "git — cannot cd to $PROJECT_DIR"; true; }
if [ -d ".git" ]; then
    UNCOMMITTED=$(git status --short 2>/dev/null | wc -l)
    if [ "$UNCOMMITTED" -gt 0 ]; then
        warn "git — $UNCOMMITTED uncommitted file(s)"
    else
        pass "git — working tree clean"
    fi

    # 2. Unpushed commits
    UPSTREAM=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null)
    if [ -n "$UPSTREAM" ]; then
        AHEAD=$(git rev-list --count "$UPSTREAM..HEAD" 2>/dev/null || echo 0)
        if [ "$AHEAD" -gt 0 ]; then
            warn "git — $AHEAD commit(s) ahead of $UPSTREAM"
        else
            pass "git — synced with $UPSTREAM"
        fi
    fi
fi

# 3. BACKLOG open items
BACKLOG="$PROJECT_DIR/BACKLOG.md"
if [ -f "$BACKLOG" ]; then
    OPEN_COUNT=$(grep -c '^\- \[ \]' "$BACKLOG" 2>/dev/null || echo 0)
    pass "backlog — $OPEN_COUNT open item(s)"
fi

# 4. Learnings gauge — surfaces memory-promotion state at every session boundary
#    Pure observation (pass/warn only, never fail). Signals when the Phase 3
#    triggers in the rosy-wishing-porcupine plan have fired.
FGT_REPO="$HOME/projects/fgt-config"
if [ -d "$FGT_REPO" ] && [ -f "$FGT_REPO/METHODOLOGY_LOG.md" ]; then
    PROMOTED=$(grep -rh '^\*\*Source:\*\*' \
        "$FGT_REPO/METHODOLOGY_LOG.md" \
        "$FGT_REPO/FGT.md" \
        "$FGT_REPO/templates/" 2>/dev/null | wc -l)
    MEMS=$(find "$HOME/.claude/projects/" -path '*/memory/*.md' \
        ! -name 'MEMORY.md' 2>/dev/null | wc -l)
    # Content-based unsourced check: walk METHODOLOGY_LOG.md, for each
    # ## CP-XXX heading check if its section (ending at ---) contains a
    # **Source:** line. Checks current state, so retroactive Source
    # additions clear the WARN as expected.
    UNSOURCED=$(awk '
        /^## CP-/ { if (cp && !has) n++; cp=1; has=0; next }
        /^\*\*Source:\*\*/ { if (cp) has=1; next }
        /^---$/ { if (cp && !has) n++; cp=0; has=0; next }
        END { if (cp && !has) n++; print n+0 }
    ' "$FGT_REPO/METHODOLOGY_LOG.md")

    if [ "$PROMOTED" -ge 5 ]; then
        pass "learnings — $PROMOTED promoted from $MEMS raw memories (Phase 3 unlocked)"
    elif [ "$MEMS" -ge 15 ] && [ "$PROMOTED" -lt 2 ]; then
        warn "learnings — $MEMS memories, only $PROMOTED promoted (convention not exercised)"
    else
        pass "learnings — $PROMOTED promoted, $MEMS raw, $UNSOURCED unsourced CP entries"
    fi
    if [ "$UNSOURCED" -gt 0 ]; then
        warn "learnings — $UNSOURCED CP-XXX entries lack Source: citation"
    fi
fi

# 5. Menu-legibility calibration — menu-legibility-stop.sh runs log-only until
#    reviewed. WARN once enough samples accumulate; clears when the user records
#    a decision (touch ~/.claude/.menu-legibility-decided).
MENU_HOOK="$HOME/.claude/scripts/menu-legibility-stop.sh"
MENU_LOG="$HOME/.claude/menu-legibility-log.txt"
MENU_DECIDED="$HOME/.claude/.menu-legibility-decided"
if [ -f "$MENU_HOOK" ] && [ ! -f "$MENU_DECIDED" ]; then
    MENU_SAMPLES=$( [ -f "$MENU_LOG" ] && wc -l < "$MENU_LOG" 2>/dev/null || echo 0 )
    MENU_SAMPLES=$(echo "$MENU_SAMPLES" | tr -d ' ')
    if [ "${MENU_SAMPLES:-0}" -ge 10 ]; then
        warn "menu-legibility — $MENU_SAMPLES flagged option(s) logged; review ~/.claude/menu-legibility-log.txt and decide on blocking, then: touch $MENU_DECIDED"
    else
        pass "menu-legibility — calibration ${MENU_SAMPLES:-0}/10 samples (log-only)"
    fi
fi

# ============================================================
# Project-specific checks (sourced from scripts/sweep.sh)
# ============================================================

SWEEP_PROCESSES=()
SWEEP_DATA_CHECKS=()
SWEEP_DB=""

PROJECT_SWEEP="$PROJECT_DIR/scripts/sweep.sh"
if [ -f "$PROJECT_SWEEP" ]; then
    # shellcheck source=/dev/null
    source "$PROJECT_SWEEP"
fi

# Process checks
for entry in "${SWEEP_PROCESSES[@]+"${SWEEP_PROCESSES[@]}"}"; do
    label="${entry%%:*}"
    pattern="${entry#*:}"
    if pgrep -f "$pattern" > /dev/null 2>&1; then
        pass "process — $label is running"
    else
        fail "process — $label is NOT running (pattern: $pattern)"
    fi
done

# Data checks (require sqlite3 + a DB path)
if [ -n "$SWEEP_DB" ] && command -v sqlite3 > /dev/null 2>&1; then
    DB_PATH="$PROJECT_DIR/$SWEEP_DB"
    if [ -f "$DB_PATH" ]; then
        for entry in "${SWEEP_DATA_CHECKS[@]+"${SWEEP_DATA_CHECKS[@]}"}"; do
            IFS='|' read -r label query threshold <<< "$entry"
            result=$(sqlite3 "$DB_PATH" "PRAGMA busy_timeout = 5000; $query" 2>/dev/null | tail -1 || echo "-1")
            # Guard: if result is empty or non-numeric, treat as failed
            if ! [[ "$result" =~ ^-?[0-9]+$ ]]; then result="-1"; fi
            if [ "$result" = "-1" ]; then
                warn "data — $label query failed"
            elif [ "$result" -gt "$threshold" ]; then
                warn "data — $label = $result (threshold: $threshold)"
            else
                pass "data — $label = $result"
            fi
        done
    else
        warn "data — DB not found: $DB_PATH"
    fi
fi

# ============================================================
# Exit
# ============================================================

if [ "$HAS_FAIL" = true ]; then
    echo ""
    echo "OCD SWEEP: FAIL findings detected. Address before declaring done."
    exit 2
fi
exit 0
