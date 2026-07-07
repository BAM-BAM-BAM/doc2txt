#!/bin/bash
# {{PROJECT}} — OCD project-specific sweep checks.
#
# Sourced by ~/.claude/scripts/ocd-sweep.sh (the generic runner).
# Define arrays that the runner iterates over. Do NOT re-implement
# git, BACKLOG, or lint checks — those are in the generic runner.
#
# FAIL semantics (FGT.md § OCD): FAIL blocks the agent's response, so
# reserve it for agent-fixable state (failing tests, drift, missing
# files). Anything that resolves only by waiting on an external system
# (in-flight CI, third-party outage, pending human action) must be WARN
# — FAIL on external state loops the Stop hook until the user breaks it.
#
# Write domain-specific content from scratch (same principle as
# FGT_DOMAIN_*.md — no cargo-culting from another project).

# --- Process checks ---
# Each entry: "label:pgrep_pattern"
# The runner checks `pgrep -f "$pattern"` and reports PASS/FAIL.
#
# Example (data pipeline project):
#   SWEEP_PROCESSES=(
#       "scraper:run.py scrape"
#       "server:run.py serve"
#       "refiner:claude-refiner run --loop"
#   )
#
# Example (CLI tool — no daemons):
#   SWEEP_PROCESSES=()
SWEEP_PROCESSES=(
    # "{{PROCESS_LABEL}}:{{PROCESS_PATTERN}}"
)

# --- Data checks ---
# Each entry: "label|sql_query|threshold" (pipe-delimited — SQL may contain colons)
# The runner executes the query against $SWEEP_DB and reports:
#   result <= threshold → PASS
#   result >  threshold → WARN
# Query must return a single integer.
#
# Example:
#   SWEEP_DATA_CHECKS=(
#       "unscored_events|SELECT COUNT(*) FROM events WHERE status='upcoming' AND scoring_method IS NULL|0"
#       "stale_sources|SELECT COUNT(*) FROM sources WHERE enabled=1 AND last_result_count=0|0"
#   )
SWEEP_DATA_CHECKS=(
    # "{{DATA_LABEL}}|{{SQL_QUERY}}|{{THRESHOLD}}"
)

# --- DB path (relative to project root) ---
# Leave empty if no data checks.
SWEEP_DB=""

# ============================================================
# Reusable inline check functions (CP-025 SRD prevention)
# ============================================================
# These are not array-driven — call them inline in your sweep.sh when
# the relevant artifacts exist in your project. Each function names the
# specific bug class it catches and an observable sunsetting condition.

# sweep_doc_snapshot_check <dir> <ext>
#
# WARN if any "<dir>/*.<ext>" file is newer than the latest sibling
# "*.vN.<ext>" snapshot. Catches "I edited the deliverable but forgot
# to snapshot the prior version" — a CP-025 (synchronized-representation)
# observation: the snapshot is the prior representation; without it,
# changes are unrecoverable.
#
# Usage: sweep_doc_snapshot_check "$PROJECT_DIR/handoff" md
# Sunsetting: when the project drops .vN.* snapshot conventions —
# observable check: `ls <dir>/*.v[0-9]*.<ext> 2>/dev/null | wc -l` returns 0.
sweep_doc_snapshot_check() {
    local dir="$1" ext="$2"
    [ -d "$dir" ] || return 0
    while IFS= read -r path; do
        [ -z "$path" ] && continue
        local base latest_snap
        base=$(basename "$path" ".$ext")
        latest_snap=$(ls "$dir/${base}.v"*."$ext" 2>/dev/null \
            | sed "s/.*\.v\([0-9][0-9]*\)\.${ext}\$/\1 &/" \
            | sort -n | tail -1 | cut -d' ' -f2-)
        if [ -n "$latest_snap" ] && [ "$path" -nt "$latest_snap" ]; then
            warn "$(basename "$path") edited since latest snapshot ($(basename "$latest_snap")); copy current to next .vN.$ext before next edit"
        fi
    done < <(ls "$dir"/*."$ext" 2>/dev/null \
        | grep -v "\.v[0-9][0-9]*\.${ext}\$")
}

# sweep_duplicate_string_literals <src_dir> [min_length] [min_modules]
#
# WARN if any quoted string literal of >= min_length characters appears
# in min_modules or more *.py files in src_dir without a shared import.
# Catches CP-013 (cross-process vocabulary drift) and the within-codebase
# CP-025 special case where a string crosses module boundaries via
# duplication instead of a shared constant.
#
# Defaults: min_length=20, min_modules=3
#
# Usage: sweep_duplicate_string_literals "$PROJECT_DIR/scripts" 20 3
# Sunsetting: permanent — string-literal duplication across modules is
# a structural risk class as long as the project has multi-module Python.
sweep_duplicate_string_literals() {
    local src_dir="$1" min_len="${2:-20}" min_mods="${3:-3}"
    [ -d "$src_dir" ] || return 0
    command -v python3 >/dev/null 2>&1 || return 0
    local report
    report=$(python3 - "$src_dir" "$min_len" "$min_mods" <<'PYEOF' 2>/dev/null
import ast, collections, sys, pathlib
src_dir, min_len, min_mods = pathlib.Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
sites = collections.defaultdict(set)  # literal -> {file paths}
for py in src_dir.rglob("*.py"):
    try:
        tree = ast.parse(py.read_text())
    except (SyntaxError, UnicodeDecodeError):
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if len(s) >= min_len and "\n" not in s:
                sites[s].add(str(py.relative_to(src_dir)))
hits = [(s, files) for s, files in sites.items() if len(files) >= min_mods]
hits.sort(key=lambda x: -len(x[1]))
for s, files in hits[:5]:  # cap report at top 5 to avoid spam
    snippet = s if len(s) <= 60 else s[:57] + "..."
    print(f'"{snippet}" in {len(files)} modules: {", ".join(sorted(files))}')
PYEOF
    )
    if [ -n "$report" ]; then
        while IFS= read -r line; do
            warn "duplicate string literal — $line"
        done <<< "$report"
    fi
}
