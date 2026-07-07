#!/bin/bash
# Unit tests for fgt-sync.sh, fgt-promote.sh, fgt-status.sh, install-ocd.sh.
#
# Creates a temporary FGT project, then exercises each script in --diff
# (non-interactive) mode. Validates output contains expected markers.
#
# Usage: bash scripts/test-scripts.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PASS=0
FAIL=0
TMPDIR=""

cleanup() {
    [ -n "$TMPDIR" ] && rm -rf "$TMPDIR"
}
trap cleanup EXIT

assert_exit_code() {
    local actual="$1" expected="$2" label="$3"
    if [ "$actual" -eq "$expected" ]; then
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label — exit $actual, expected $expected"
        FAIL=$((FAIL + 1))
    fi
}

assert_output_contains() {
    local output="$1" pattern="$2" label="$3"
    if echo "$output" | grep -q "$pattern"; then
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label — '$pattern' not found in output"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_exists() {
    local file="$1" label="$2"
    if [ -f "$file" ] || [ -L "$file" ]; then
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label — $file not found"
        FAIL=$((FAIL + 1))
    fi
}

# --- Setup: scaffold a test project ---
echo "=== Setting up test project ==="
TMPDIR=$(mktemp -d)
TEST_PROJECT="$TMPDIR/test-fgt-proj"
mkdir -p "$TEST_PROJECT"

# Scaffold with new-project.sh
echo "" | GLOBAL_FGT_DIR="$ROOT_DIR" bash "$SCRIPT_DIR/new-project.sh" "$TEST_PROJECT" TESTDOMAIN --lang py 2>&1 | tail -5

# Verify scaffold worked
assert_file_exists "$TEST_PROJECT/FGT.md" "scaffold: FGT.md"
assert_file_exists "$TEST_PROJECT/PATTERNS_TESTDOMAIN.md" "scaffold: PATTERNS"
assert_file_exists "$TEST_PROJECT/BACKLOG.md" "scaffold: BACKLOG"

# ===================================================================
echo ""
echo "=== fgt-status.sh ==="
# ===================================================================

# fgt-status.sh uses $PROJECTS_DIR (default $HOME/projects).
# Override so it finds our test project.
output=$(PROJECTS_DIR="$TMPDIR" bash "$SCRIPT_DIR/fgt-status.sh" 2>&1) || true
assert_output_contains "$output" "FGT Status" "status: header present"
assert_output_contains "$output" "test-fgt-proj" "status: project name found"
assert_output_contains "$output" "PATTERNS" "status: reports PATTERNS"
assert_output_contains "$output" "BACKLOG" "status: reports BACKLOG"

# ===================================================================
echo ""
echo "=== fgt-sync.sh --diff ==="
# ===================================================================

# Modify the project PATTERNS to create a diff
echo "# Project-specific addition" >> "$TEST_PROJECT/PATTERNS_TESTDOMAIN.md"

output=$(bash "$SCRIPT_DIR/fgt-sync.sh" "$TEST_PROJECT" --diff 2>&1) || true
assert_output_contains "$output" "FGT Sync" "sync: header present"
assert_output_contains "$output" "Diverged" "sync: detects divergence"
assert_output_contains "$output" "PATTERNS" "sync: reports PATTERNS diff"

# --apply mode: should sync
output=$(bash "$SCRIPT_DIR/fgt-sync.sh" "$TEST_PROJECT" --apply 2>&1) || true
assert_output_contains "$output" "Synced" "sync-apply: synced file"

# After apply, diff mode should show in-sync
output=$(bash "$SCRIPT_DIR/fgt-sync.sh" "$TEST_PROJECT" --diff 2>&1) || true
assert_output_contains "$output" "In sync" "sync-post-apply: in sync"

# ===================================================================
echo ""
echo "=== fgt-promote.sh --diff ==="
# ===================================================================

# Re-diverge the project file
echo "# Promoted change" >> "$TEST_PROJECT/PATTERNS_TESTDOMAIN.md"

output=$(bash "$SCRIPT_DIR/fgt-promote.sh" "$TEST_PROJECT" --diff 2>&1) || true
assert_output_contains "$output" "FGT Promote" "promote: header present"
assert_output_contains "$output" "Promoted change" "promote: shows the diff"

# ===================================================================
echo ""
echo "=== install-ocd.sh ==="
# ===================================================================

# Test install to a temp HOME
export REAL_HOME="$HOME"
export HOME="$TMPDIR/fake_home"
mkdir -p "$HOME/.claude"
# Create a minimal settings.json
echo '{"hooks":{}}' > "$HOME/.claude/settings.json"

output=$(bash "$SCRIPT_DIR/install-ocd.sh" 2>&1) || true
assert_output_contains "$output" "OCD Install Complete" "ocd: completes successfully"
assert_file_exists "$HOME/.claude/scripts/ocd-sweep.sh" "ocd: sweep script deployed"

# Idempotent: run again
output=$(bash "$SCRIPT_DIR/install-ocd.sh" 2>&1) || true
assert_output_contains "$output" "already present\|Copied" "ocd: idempotent re-run"

# Restore HOME
export HOME="$REAL_HOME"

# ===================================================================
echo ""
echo "=== ocd-sweep.sh (on test project) ==="
# ===================================================================

# Init git in test project so sweep can check it
(cd "$TEST_PROJECT" && git init -q && git add -A && git commit -q -m "init" 2>/dev/null) || true

# Run sweep on test project (no processes/data expected)
output=$(CLAUDE_PROJECT_DIR="$TEST_PROJECT" bash "$ROOT_DIR/scripts/ocd-sweep.sh" 2>&1) || true
assert_output_contains "$output" "PASS.*git" "sweep: git check runs"
assert_output_contains "$output" "backlog" "sweep: backlog check runs"

# ===================================================================
echo ""
echo "=== Results ==="
# ===================================================================

TOTAL=$((PASS + FAIL))
echo "$PASS/$TOTAL passed"
if [ "$FAIL" -gt 0 ]; then
    echo "FAILED: $FAIL test(s)"
    exit 1
fi
echo "All tests passed."
