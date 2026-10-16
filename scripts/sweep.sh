#!/bin/bash
# DOC2TXT — OCD project-specific sweep checks.
#
# Sourced by ~/.claude/scripts/ocd-sweep.sh (the generic runner).
# See ~/.claude/fgt/templates/SWEEP_TEMPLATE.sh for the format spec.
#
# Per Principle 1 (Every Addition Must Justify Its Keep), add project-
# specific SWEEP_PROCESSES / SWEEP_DATA_CHECKS entries only when a bug
# class has been observed >=2 times and a sweep check is the right
# enforcement plane for it. Empty arrays here are intentional; the
# generic runner handles git, BACKLOG, .env perms automatically.

SWEEP_PROCESSES=()
SWEEP_DATA_CHECKS=()
SWEEP_DB=""

# --- watcher.log health (inline checks) ---
#
# Justification (Principle 1, >=2 observed instances): 20 of 44 nightly
# cron runs in May-June 2026 died with uncaught OSError tracebacks
# (unmounted /mnt/g x18, OneDrive I/O error x2 — BUG-004). The crashes
# went unnoticed for weeks because nothing watched the log. Two checks:
#
# 1. watcher-tracebacks: WARN if any traceback in watcher.log is dated
#    within the last 7 days. Window chosen so the pre-fix May/June
#    crashes age out and PASS reflects current health (last traceback
#    2026-06-24; fix landed 2026-07-07). A traceback has no timestamp
#    of its own, so it inherits the last dated log line before it;
#    tracebacks before any dated line are unknown-age and not counted.
#
# 2. watcher-freshness: WARN if the last dated watcher.log line is
#    older than 72h. Catches silent cron death (same evidence class:
#    the crash streak went unnoticed because absence of output looks
#    like success). 72h, not 48h: the log shows benign 1-2 night gaps
#    when the WSL host is off; 48h would WARN on routine host-off days.
#
# 3. watcher-dirs: WARN if the most recent scan logged a watch directory
#    missing or unreachable (check 2 covers a log with no recent scan).
#    Since BUG-004 a dead mount logs a WARNING
#    and the run carries on, so the directory is silently not watched:
#    /mnt/g was missing in 56 runs (2026-07..10, every October run)
#    before anyone noticed, after 18 crashes for the same cause earlier.
#    Its failed documents are only retried on a run that reaches it.
#
# Sunsetting: if neither check has WARNed for 6 months after 2026-07-07,
# fold them into a single freshness check.
WATCHER_LOG="$PROJECT_DIR/watcher.log"
if [ -f "$WATCHER_LOG" ]; then
    TB_CUTOFF=$(date -d "-7 days" '+%Y-%m-%d')
    RECENT_TB=$(awk -v cutoff="$TB_CUTOFF" '
        /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] / { last = $1 }
        /^Traceback \(most recent call last\)/ { if (last != "" && last >= cutoff) n++ }
        END { print n + 0 }
    ' "$WATCHER_LOG")
    if [ "$RECENT_TB" -gt 0 ]; then
        warn "watcher — $RECENT_TB traceback(s) in watcher.log within 7 days (BUG-004 class)"
    else
        pass "watcher — no tracebacks in watcher.log within 7 days"
    fi

    LAST_RUN=$(grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}' "$WATCHER_LOG" | tail -1)
    if [ -n "$LAST_RUN" ]; then
        LAST_EPOCH=$(date -d "$LAST_RUN" +%s 2>/dev/null || echo 0)
        AGE_HOURS=$(( ($(date +%s) - LAST_EPOCH) / 3600 ))
        if [ "$LAST_EPOCH" -eq 0 ]; then
            warn "watcher — cannot parse last run timestamp from watcher.log"
        elif [ "$AGE_HOURS" -gt 72 ]; then
            warn "watcher — last nightly run ${AGE_HOURS}h ago (>72h; cron dead or host off too long?)"
        else
            pass "watcher — last nightly run ${AGE_HOURS}h ago (<=72h)"
        fi
    else
        warn "watcher — no dated log lines found in watcher.log"
    fi

    # A scan logs its missing dirs, then "Single scan:" (--once) or
    # "Found N files" / "No new or modified files found" (polling loop).
    MISSING_DIRS=$(awk '
        /Watch directory (does not exist|unreachable, skipping): / {
            d = $0
            sub(/.*Watch directory (does not exist|unreachable, skipping): /, "", d)
            if ($0 ~ /unreachable, skipping: /) sub(/ \(\[Errno.*$/, "", d)
            pending = pending (pending == "" ? "" : "; ") d
        }
        /Single scan: |Found [0-9]+ files: |No new or modified files found/ { last = pending; pending = "" }
        END { print last }
    ' "$WATCHER_LOG")
    if [ -n "$MISSING_DIRS" ]; then
        warn "watcher — last scan could not reach watch dir(s): $MISSING_DIRS (not scanned; mount it)"
    else
        pass "watcher — last scan reached every watch dir"
    fi
else
    warn "watcher — watcher.log not found (nightly cron output missing)"
fi
