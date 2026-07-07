#!/usr/bin/env bash
# fgt-config dogfood sweep — apply FGT's own checks to itself.
# Per FGT P5 (Invariants Tested) + P8 (Proactive Detection).
#
# Sunsetting condition: retire when 12 months pass with no new CP-* added
# AND no project's BUG_PATTERNS_*.md cites CP-027. Observable check:
#   git log --since='12 months ago' fgt_cross_project_retrospective_v2.md  (no new CP)
#   grep -rl 'CP-027' ~/projects/*/BUG_PATTERNS*.md                        (returns 0)

SWEEP_PROCESSES=()
SWEEP_DATA_CHECKS=()
SWEEP_DB=""

# Config-only source guard: pstatus sources this just to read SWEEP_* arrays.
# Return BEFORE `set -euo pipefail` and any `exit` calls so we don't kill
# pstatus's command-substitution subshell.
[[ "${SWEEP_CONFIG_ONLY:-0}" == "1" ]] && return 0

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

errors=0
warns=0

# 1. P5: every CP-NNN reference in FGT.md / templates resolves to a defined CP
referenced=$(grep -hoE 'CP-0[0-9]{2}' FGT.md FGT_NEW_PROJECT_CHECKLIST.md templates/*.md templates/*.sh 2>/dev/null | sort -u)
for cp in $referenced; do
  if ! grep -q "^### $cp" fgt_cross_project_retrospective_v2.md; then
    echo "[FAIL] $cp referenced but not defined in retrospective"
    errors=$((errors+1))
  fi
done

# 2. P3 regression guard: no count adjectives in prose (would re-introduce CP-025 self-drift)
if drift=$(grep -nE '\b(three|four|five|ten|eleven|thirteen|fifteen) (Prevention Principles|test categories|enforcement planes|principles|categories|planes)\b' FGT.md README.md 2>/dev/null); then
  echo "[FAIL] count adjective in prose (CP-025 regression):"
  echo "$drift"
  errors=$((errors+1))
fi

# 3. P1 (forward-looking): the most recent CP must have a "Sunsetting condition" line.
# Historical CPs are grandfathered; only the newest entry is checked so future additions are forced to comply.
last_cp=$(grep -oE '^### CP-0[0-9]{2}' fgt_cross_project_retrospective_v2.md | tail -1 | grep -oE 'CP-0[0-9]{2}')
if [ -n "$last_cp" ]; then
  range=$(awk "/^### $last_cp/,/^---$/" fgt_cross_project_retrospective_v2.md)
  if ! echo "$range" | grep -qi 'sunsetting condition'; then
    echo "[WARN] $last_cp lacks 'Sunsetting condition' (P1 step 5b)"
    warns=$((warns+1))
  fi
fi

# 4. P4: TASKS.md must not exist (BACKLOG.md is canonical)
if [[ -f TASKS.md ]]; then
  echo "[FAIL] TASKS.md exists — BACKLOG.md is the canonical task tracker (P3+P4)"
  errors=$((errors+1))
fi

# 5. P4: CLAUDE_WEB.md must not exist (merged into README § For Claude Web Projects on 2026-05-08)
if [[ -f CLAUDE_WEB.md ]]; then
  echo "[FAIL] CLAUDE_WEB.md exists — content lives in README.md § For Claude Web Projects"
  errors=$((errors+1))
fi

if (( errors > 0 )); then
  echo "[sweep] FAIL — $errors error(s), $warns warning(s)"
  exit 1
fi
echo "[sweep] PASS — fgt-config dogfood — $warns warning(s)"
