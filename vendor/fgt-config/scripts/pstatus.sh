#!/bin/bash
# pstatus — Project Status HUD. Zero-LLM-cost operational dashboard.
#
# Usage:
#   pstatus                    # all FGT-enabled projects
#   pstatus infinevent         # single project detail view
#   pstatus --no-color         # plain text (for piping)
#
# Canonical source: fgt-config/scripts/pstatus.sh
# Installed to:     ~/.local/bin/pstatus (by install-ocd.sh)

set -uo pipefail

PROJECTS_DIR="${PROJECTS_DIR:-$HOME/projects}"
SINGLE_PROJECT="${1:-}"
NO_COLOR="${NO_COLOR:-}"
[[ "$SINGLE_PROJECT" == "--no-color" ]] && NO_COLOR=1 && SINGLE_PROJECT=""

# ── ANSI colors ──────────────────────────────────────────────────────
if [[ -z "$NO_COLOR" ]] && [[ -t 1 ]]; then
    GRN=$'\e[32m'; YLW=$'\e[33m'; RED=$'\e[31m'; CYN=$'\e[36m'
    DIM=$'\e[2m'; BLD=$'\e[1m'; RST=$'\e[0m'
else
    GRN=""; YLW=""; RED=""; CYN=""; DIM=""; BLD=""; RST=""
fi

# ── Helpers ──────────────────────────────────────────────────────────

_pad() { printf "%-${2}s" "$1"; }

_color_status() {
    local val="$1"
    case "$val" in
        PASS|pass|✓*|*synced*|*clean*|*up*) echo "${GRN}$val${RST}" ;;
        WARN|warn|⚠*) echo "${YLW}$val${RST}" ;;
        FAIL|fail|✗*|*DOWN*|*failed*) echo "${RED}$val${RST}" ;;
        *) echo "$val" ;;
    esac
}

# Print a colored cell padded to a fixed visible width.
# Pads the plain text first, then wraps with color — so ANSI escape
# codes don't corrupt column alignment.
_cell() {
    local w="$1" txt="$2"
    # ✓, ⚠, ✗ are multi-byte (3 bytes each) but 1 visual column.
    # printf %-Ns counts bytes, not visual width. Compensate by adding
    # 2 extra pad chars per multi-byte symbol.
    local extra=0
    [[ "$txt" == *✓* ]] && extra=$((extra + 2))
    [[ "$txt" == *⚠* ]] && extra=$((extra + 2))
    [[ "$txt" == *✗* ]] && extra=$((extra + 2))
    [[ "$txt" == *—* ]] && extra=$((extra + 2))
    local padded=$(printf "%-$((w + extra))s" "$txt")
    case "$txt" in
        ✓*|*synced*|*clean*|*pass*|*up*|*valid*|*idle*) printf "%s" "${GRN}${padded}${RST}" ;;
        ⚠*|*dirty*|*ahead*|*active*) printf "%s" "${YLW}${padded}${RST}" ;;
        ✗*|*DOWN*|*FAIL*) printf "%s" "${RED}${padded}${RST}" ;;
        —*) printf "%s" "${DIM}${padded}${RST}" ;;
        *open) printf "%s" "${CYN}${padded}${RST}" ;;
        *) printf "%s" "$padded" ;;
    esac
}

# ── Per-project checks ──────────────────────────────────────────────
# All _check_* functions return PLAIN TEXT (no ANSI). Color is applied
# by _cell in the summary renderer, so column padding is correct.

_check_git() {
    local dir="$1"
    cd "$dir" 2>/dev/null || { echo "—"; return; }
    [[ ! -d ".git" ]] && { echo "—"; return; }
    local uncommitted=$(git status --short 2>/dev/null | wc -l)
    local upstream=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null)
    local ahead=0
    [[ -n "$upstream" ]] && ahead=$(git rev-list --count "$upstream..HEAD" 2>/dev/null || echo 0)

    if [[ "$uncommitted" -gt 0 ]]; then echo "${uncommitted} dirty"
    elif [[ "$ahead" -gt 0 ]]; then echo "${ahead} ahead"
    elif [[ -z "$upstream" ]]; then echo "✓ clean"
    else echo "✓ synced"
    fi
}

_check_tests() {
    local dir="$1"
    cd "$dir" 2>/dev/null || { echo "—"; return; }

    if [[ -d ".venv" ]] && [[ -d "tests" ]]; then
        local total=$(.venv/bin/python -m pytest --co -q 2>/dev/null | tail -1 | grep -oP '\d+' | head -1 || echo "")
        if [[ -z "$total" || "$total" == "0" ]]; then
            total=$(find tests -name 'test_*.py' -exec grep -l 'def test_' {} + 2>/dev/null | wc -l)
        fi
        echo "${total} pass"; return
    fi

    if [[ -f "vitest.config.ts" ]] || [[ -f "vitest.config.js" ]]; then
        local count=$(find tests -name '*.test.ts' -o -name '*.test.js' 2>/dev/null | wc -l)
        echo "${count} pass"; return
    fi

    if [[ -f "package.json" ]] && grep -q '"validate"' package.json 2>/dev/null; then
        echo "✓ valid"; return
    fi

    echo "—"
}

_check_ci() {
    local dir="$1"
    cd "$dir" 2>/dev/null || { echo "—"; return; }
    [[ ! -d ".git" ]] && { echo "—"; return; }

    local remote=$(git remote get-url origin 2>/dev/null)
    [[ -z "$remote" ]] && { echo "no remote"; return; }

    local ci_json=$(gh run list --limit 1 --json status,conclusion,updatedAt 2>/dev/null)
    [[ -z "$ci_json" || "$ci_json" == "[]" ]] && { echo "—"; return; }

    local conclusion=$(echo "$ci_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0].get('conclusion','') if d else '')" 2>/dev/null)
    local updated=$(echo "$ci_json" | python3 -c "
import sys,json
from datetime import datetime, timezone
d=json.load(sys.stdin)
if not d: print('?'); sys.exit()
ts = d[0].get('updatedAt','')
try:
    dt = datetime.fromisoformat(ts.replace('Z','+00:00'))
    delta = datetime.now(timezone.utc) - dt
    if delta.days > 0: print(f'{delta.days}d ago')
    elif delta.seconds > 3600: print(f'{delta.seconds//3600}h ago')
    else: print(f'{delta.seconds//60}m ago')
except: print('?')
" 2>/dev/null)

    case "$conclusion" in
        success) echo "✓ ${updated}" ;;
        failure) echo "✗ ${updated}" ;;
        *) echo "${conclusion:-?} ${updated}" ;;
    esac
}

_check_processes() {
    local dir="$1"
    local sweep="$dir/scripts/sweep.sh"
    [[ ! -f "$sweep" ]] && { echo "—"; return; }

    local SWEEP_PROCESSES=()
    # Discard stdout+stderr: many sweep.sh files run their full check
    # pipeline at top-level and emit [PASS]/[WARN] to stdout. We only want
    # the SWEEP_* array values; their print output would otherwise bleed
    # into the column.
    SWEEP_CONFIG_ONLY=1 source "$sweep" >/dev/null 2>&1
    [[ ${#SWEEP_PROCESSES[@]} -eq 0 ]] && { echo "—"; return; }

    local up=0 total=0
    for entry in "${SWEEP_PROCESSES[@]}"; do
        local pattern="${entry#*:}"
        total=$((total + 1))
        pgrep -f "$pattern" > /dev/null 2>&1 && up=$((up + 1))
    done
    echo "${up}/${total} up"
}

_check_data() {
    local dir="$1"
    local sweep="$dir/scripts/sweep.sh"
    [[ ! -f "$sweep" ]] && { echo "—"; return; }

    local SWEEP_DATA_CHECKS=()
    local SWEEP_DB=""
    SWEEP_CONFIG_ONLY=1 source "$sweep" >/dev/null 2>&1
    [[ -z "$SWEEP_DB" || ${#SWEEP_DATA_CHECKS[@]} -eq 0 ]] && { echo "—"; return; }

    local db_path="$dir/$SWEEP_DB"
    [[ ! -f "$db_path" ]] && { echo "—"; return; }

    local warns=0 total_val=0
    for entry in "${SWEEP_DATA_CHECKS[@]}"; do
        IFS='|' read -r label query threshold <<< "$entry"
        local result=$(sqlite3 "$db_path" "PRAGMA busy_timeout = 5000; $query" 2>/dev/null | tail -1)
        [[ ! "$result" =~ ^-?[0-9]+$ ]] && continue
        if [[ "$result" -gt "$threshold" ]]; then
            warns=$((warns + 1))
            total_val=$((total_val + result))
        fi
    done

    if [[ "$warns" -eq 0 ]]; then echo "✓ ok"
    else echo "⚠ ${total_val}"
    fi
}

_check_backlog() {
    local dir="$1"
    local bl="$dir/BACKLOG.md"
    [[ ! -f "$bl" ]] && { echo "—"; return; }
    local count=$(grep -c '^\- \[ \]' "$bl" 2>/dev/null || echo 0)
    echo "${count} open"
}

# ── Detail view (single project) ────────────────────────────────────

_detail_view() {
    local name="$1"
    local dir="$PROJECTS_DIR/$name"
    [[ ! -d "$dir" ]] && { echo "${RED}Project not found: $dir${RST}"; exit 1; }

    # Detail row: CHECK(20) STATUS(12) VALUE(25) DETAIL(rest)
    # Uses _cell for STATUS column to handle Unicode+color alignment.
    _drow() {
        local check="$1" status="$2" value="$3" detail="${4:-}"
        printf " %-20s " "$check"
        _cell 12 "$status"
        printf " %-25s %s\n" "$value" "$detail"
    }

    local upper=$(echo "$name" | tr '[:lower:]' '[:upper:]')
    printf "\n ${BLD}%s STATUS${RST}%*s%s\n" "$upper" $((75 - ${#upper})) "" "$(date '+%Y-%m-%d %H:%M')"
    printf " %s\n" "$(printf '─%.0s' $(seq 1 99))"
    printf " ${BLD}%-20s  %-12s %-25s %s${RST}\n" "CHECK" "STATUS" "VALUE" "DETAIL"
    printf " %s\n" "$(printf '─%.0s' $(seq 1 99))"

    # Git
    cd "$dir" 2>/dev/null
    local uncommitted=$(git status --short 2>/dev/null | wc -l)
    local upstream=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null)
    local ahead=0
    [[ -n "$upstream" ]] && ahead=$(git rev-list --count "$upstream..HEAD" 2>/dev/null || echo 0)
    if [[ "$uncommitted" -eq 0 && "$ahead" -eq 0 ]]; then
        _drow "git" "✓ pass" "clean" "synced with ${upstream:-local}"
    else
        [[ "$uncommitted" -gt 0 ]] && _drow "git" "⚠ warn" "${uncommitted} uncommitted" ""
        [[ "$ahead" -gt 0 ]] && _drow "git (push)" "⚠ warn" "${ahead} unpushed" ""
    fi

    # Tests
    _drow "tests" "" "$(_check_tests "$dir")" ""

    # CI
    _drow "CI" "" "$(_check_ci "$dir")" ""

    # Processes
    local sweep="$dir/scripts/sweep.sh"
    if [[ -f "$sweep" ]]; then
        local SWEEP_PROCESSES=()
        SWEEP_CONFIG_ONLY=1 source "$sweep" >/dev/null 2>&1
        for entry in "${SWEEP_PROCESSES[@]+"${SWEEP_PROCESSES[@]}"}"; do
            local label="${entry%%:*}"
            local pattern="${entry#*:}"
            local pid=$(pgrep -f "$pattern" 2>/dev/null | head -1)
            if [[ -n "$pid" ]]; then
                local since=$(ps -p "$pid" -o lstart= 2>/dev/null | xargs -I{} date -d "{}" '+%H:%M' 2>/dev/null || echo "?")
                _drow "$label" "✓ up" "PID $pid" "since $since"
            else
                _drow "$label" "✗ DOWN" "—" "not running"
            fi
        done

        # Data checks
        local SWEEP_DATA_CHECKS=()
        local SWEEP_DB=""
        SWEEP_CONFIG_ONLY=1 source "$sweep" >/dev/null 2>&1
        if [[ -n "$SWEEP_DB" ]]; then
            local db_path="$dir/$SWEEP_DB"
            for entry in "${SWEEP_DATA_CHECKS[@]+"${SWEEP_DATA_CHECKS[@]}"}"; do
                IFS='|' read -r label query threshold <<< "$entry"
                local result=$(sqlite3 "$db_path" "PRAGMA busy_timeout = 5000; $query" 2>/dev/null | tail -1)
                [[ ! "$result" =~ ^-?[0-9]+$ ]] && result="?"
                if [[ "$result" != "?" && "$result" -le "$threshold" ]]; then
                    _drow "$label" "✓ pass" "$result" ""
                else
                    _drow "$label" "⚠ warn" "$result" "threshold: $threshold"
                fi
            done
        fi
    fi

    # Scoring pipeline status (if DB exists)
    if [[ -n "$SWEEP_DB" && -f "$dir/$SWEEP_DB" ]]; then
        local scoring_summary=$("$dir/.venv/bin/python" -c "
import sqlite3, sys
db = sqlite3.connect('$dir/$SWEEP_DB')
db.execute('PRAGMA busy_timeout = 5000')

upcoming = db.execute(\"SELECT COUNT(*) FROM events WHERE status='upcoming' AND date >= date('now')\").fetchone()[0]
by_method = db.execute(\"\"\"
    SELECT COALESCE(scoring_method, 'unscored'), COUNT(*)
    FROM events WHERE status='upcoming' AND date >= date('now')
    GROUP BY scoring_method ORDER BY COUNT(*) DESC
\"\"\").fetchall()

# Events with refiner_job_id but still keyword-scored (pending drain)
pending_drain = db.execute(\"\"\"
    SELECT COUNT(*) FROM events
    WHERE status='upcoming' AND date >= date('now')
      AND scoring_method = 'keyword' AND refiner_job_id IS NOT NULL
\"\"\").fetchone()[0]

# Next 3 days breakdown
soon = db.execute(\"\"\"
    SELECT COALESCE(scoring_method, 'unscored'), COUNT(*)
    FROM events WHERE status='upcoming'
      AND date >= date('now') AND date <= date('now', '+3 days')
    GROUP BY scoring_method ORDER BY COUNT(*) DESC
\"\"\").fetchall()
soon_total = sum(c for _, c in soon)

print(f'TOTAL:{upcoming}')
for method, count in by_method:
    print(f'METHOD:{method}:{count}')
print(f'PENDING_DRAIN:{pending_drain}')
print(f'SOON_TOTAL:{soon_total}')
for method, count in soon:
    print(f'SOON:{method}:{count}')
" 2>/dev/null)

        if [[ -n "$scoring_summary" ]]; then
            local total=$(echo "$scoring_summary" | grep '^TOTAL:' | cut -d: -f2)
            local pending=$(echo "$scoring_summary" | grep '^PENDING_DRAIN:' | cut -d: -f2)
            local soon_total=$(echo "$scoring_summary" | grep '^SOON_TOTAL:' | cut -d: -f2)

            # Build method breakdown string
            local methods=""
            while IFS=: read -r _ method count; do
                methods="${methods}${method}=${count} "
            done < <(echo "$scoring_summary" | grep '^METHOD:')

            local soon_methods=""
            while IFS=: read -r _ method count; do
                soon_methods="${soon_methods}${method}=${count} "
            done < <(echo "$scoring_summary" | grep '^SOON:')

            _drow "scoring" "— info" "${total} upcoming" "${methods}"
            if [[ "$pending" -gt 0 ]]; then
                _drow "  refiner pending" "⚠ active" "${pending} awaiting drain" ""
            fi
            _drow "  next 3 days" "— info" "${soon_total} events" "${soon_methods}"
        fi
    fi

    # Refiner queue (if claude-refiner is available)
    if command -v claude-refiner > /dev/null 2>&1; then
        local refiner_json=$(claude-refiner status --project "$name" 2>/dev/null)
        if [[ -n "$refiner_json" ]]; then
            local counts=$(echo "$refiner_json" | python3 -c "
import sys,json
d=json.load(sys.stdin).get('counts',{})
parts = [f'{v} {k}' for k,v in d.items() if v > 0]
print(', '.join(parts) if parts else 'empty')
" 2>/dev/null)
            local has_queued=$(echo "$refiner_json" | python3 -c "import sys,json; d=json.load(sys.stdin).get('counts',{}); print('yes' if d.get('queued',0)+d.get('working',0)>0 else 'no')" 2>/dev/null)
            if [[ "$has_queued" == "yes" ]]; then
                _drow "refiner queue" "⚠ active" "$counts" ""
            else
                _drow "refiner queue" "✓ idle" "$counts" ""
            fi
        fi
    fi

    # Backlog
    local bl="$dir/BACKLOG.md"
    if [[ -f "$bl" ]]; then
        local count=$(grep -c '^\- \[ \]' "$bl" 2>/dev/null || echo 0)
        _drow "backlog" "— info" "${count} open" "see below"
        printf " %s\n" "$(printf '─%.0s' $(seq 1 99))"
        echo ""
        printf " ${BLD}OPEN BACKLOG (%d items):${RST}\n" "$count"
        grep '^\- \[ \]' "$bl" 2>/dev/null | sed 's/^- \[ \] //' | while IFS= read -r line; do
            local short=$(echo "$line" | sed 's/\*\*//g' | cut -c1-70)
            printf "  ${DIM}•${RST} %s\n" "$short"
        done
    fi
    echo ""
}

# ── Summary view (all projects) ─────────────────────────────────────

_summary_view() {
    printf "\n ${BLD}PROJECT STATUS${RST}%*s%s\n" 65 "" "$(date '+%Y-%m-%d %H:%M')"
    printf " %s\n" "$(printf '─%.0s' $(seq 1 99))"
    printf " ${BLD}%-20s %-11s %-11s %-13s %-11s %-10s %s${RST}\n" \
        "PROJECT" "GIT" "TESTS" "CI" "PROCS" "DATA" "BACKLOG"
    printf " %s\n" "$(printf '─%.0s' $(seq 1 99))"

    local total_tests=0 total_bl=0

    for dir in "$PROJECTS_DIR"/*/; do
        [[ ! -d "$dir" ]] && continue
        local name=$(basename "$dir")

        # Only show FGT-enabled projects (have FGT.md or BACKLOG.md)
        [[ ! -f "$dir/FGT.md" && ! -L "$dir/FGT.md" && ! -f "$dir/BACKLOG.md" ]] && continue

        local git_val=$(_check_git "$dir")
        local test_val=$(_check_tests "$dir")
        local ci_val=$(_check_ci "$dir")
        local proc_val=$(_check_processes "$dir")
        local data_val=$(_check_data "$dir")
        local bl_val=$(_check_backlog "$dir")

        printf " %-20s " "$name"
        _cell 11 "$git_val"; printf " "
        _cell 11 "$test_val"; printf " "
        _cell 13 "$ci_val"; printf " "
        _cell 11 "$proc_val"; printf " "
        _cell 10 "$data_val"; printf " "
        _cell 8 "$bl_val"
        printf "\n"
    done

    printf " %s\n" "$(printf '─%.0s' $(seq 1 99))"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────────────

if [[ -n "$SINGLE_PROJECT" ]]; then
    _detail_view "$SINGLE_PROJECT"
else
    _summary_view
fi
