#!/bin/bash
# Integration test for new-project.sh — verifies the scaffold creates
# all expected files for both TypeScript and Python configurations.
#
# Usage: bash scripts/test-new-project.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PASS=0
FAIL=0

assert_file_exists() {
    local file="$1"
    local label="$2"
    if [ -f "$file" ] || [ -L "$file" ]; then
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label — $file not found"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_contains() {
    local file="$1"
    local pattern="$2"
    local label="$3"
    if grep -q "$pattern" "$file" 2>/dev/null; then
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label — '$pattern' not found in $file"
        FAIL=$((FAIL + 1))
    fi
}

assert_no_placeholder() {
    local file="$1"
    local label="$2"
    # Skip FGT.md (symlink to global which has no placeholders)
    [ "$(basename "$file")" = "FGT.md" ] && return
    # Allow {{placeholders}} only in HTML comments
    local active_placeholders
    active_placeholders=$(grep -v '<!--' "$file" 2>/dev/null | grep -c '{{' || true)
    if [ "$active_placeholders" -eq 0 ]; then
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label — $active_placeholders unreplaced placeholder(s) in $file"
        FAIL=$((FAIL + 1))
    fi
}

run_test() {
    local lang="$1"
    local test_dir="/tmp/fgt-test-${lang}-$$"
    mkdir -p "$test_dir"

    echo "=== Testing --lang $lang ==="

    GLOBAL_FGT_DIR="$ROOT_DIR" bash "$ROOT_DIR/scripts/new-project.sh" \
        "$test_dir" TESTPROJ --lang "$lang" --privacy > /dev/null 2>&1

    # --- FGT documentation files ---
    assert_file_exists "$test_dir/FGT.md" "$lang: FGT.md symlink"
    assert_file_exists "$test_dir/CLAUDE.md" "$lang: CLAUDE.md"
    assert_file_exists "$test_dir/BACKLOG.md" "$lang: BACKLOG.md"
    assert_file_exists "$test_dir/SPEC.md" "$lang: SPEC.md"
    assert_file_exists "$test_dir/BUG_PATTERNS_TESTPROJ.md" "$lang: BUG_PATTERNS"
    assert_file_exists "$test_dir/FGT_DOMAIN_TESTPROJ.md" "$lang: FGT_DOMAIN"
    assert_file_exists "$test_dir/PATTERNS_TESTPROJ.md" "$lang: PATTERNS"
    assert_file_exists "$test_dir/REVIEWS_TESTPROJ.md" "$lang: REVIEWS"
    assert_file_exists "$test_dir/EXPERT_REVIEWERS_TESTPROJ.md" "$lang: EXPERT_REVIEWERS"
    assert_file_exists "$test_dir/REVALIDATION_TESTPROJ.md" "$lang: REVALIDATION"
    assert_file_exists "$test_dir/CONFIG_TESTPROJ.md" "$lang: CONFIG"
    assert_file_exists "$test_dir/FGT_LOG.md" "$lang: FGT_LOG"

    # --- Hook scripts ---
    assert_file_exists "$test_dir/scripts/fgt_session_start.sh" "$lang: session_start hook"
    assert_file_exists "$test_dir/scripts/fgt_session_persist.sh" "$lang: session_persist hook"
    assert_file_exists "$test_dir/scripts/fgt_stop_check.sh" "$lang: stop_check hook"

    # --- Claude settings ---
    assert_file_exists "$test_dir/.claude/settings.json" "$lang: claude settings"

    # --- Git hooks ---
    assert_file_exists "$test_dir/scripts/git-hooks/pre-commit" "$lang: pre-commit hook"
    assert_file_exists "$test_dir/scripts/install-hooks.sh" "$lang: install-hooks"

    # --- CI ---
    assert_file_exists "$test_dir/scripts/ci-local.sh" "$lang: ci-local"
    assert_file_exists "$test_dir/.github/workflows/verify.yml" "$lang: CI workflow"

    # --- Language-specific files ---
    if [ "$lang" = "ts" ]; then
        assert_file_exists "$test_dir/package.json" "$lang: package.json"
        assert_file_exists "$test_dir/tsconfig.json" "$lang: tsconfig.json"
        assert_file_exists "$test_dir/eslint.config.js" "$lang: eslint.config.js"
        assert_file_exists "$test_dir/vitest.config.ts" "$lang: vitest.config.ts"
        assert_file_exists "$test_dir/src/config.ts" "$lang: src/config.ts"
        assert_file_exists "$test_dir/tests/setup.ts" "$lang: tests/setup.ts"
        assert_file_exists "$test_dir/tests/test_invariants.test.ts" "$lang: test_invariants"
        assert_file_exists "$test_dir/tests/test_proactive.test.ts" "$lang: test_proactive"
        assert_file_exists "$test_dir/tests/test_placeholder.test.ts" "$lang: test_placeholder"
    elif [ "$lang" = "py" ]; then
        assert_file_exists "$test_dir/pyproject.toml" "$lang: pyproject.toml"
        assert_file_exists "$test_dir/src/__init__.py" "$lang: src/__init__.py"
        assert_file_exists "$test_dir/src/config.py" "$lang: src/config.py"
        assert_file_exists "$test_dir/tests/conftest.py" "$lang: tests/conftest.py"
        assert_file_exists "$test_dir/tests/test_invariants.py" "$lang: test_invariants"
        assert_file_exists "$test_dir/tests/test_proactive.py" "$lang: test_proactive"
        assert_file_exists "$test_dir/tests/test_placeholder.py" "$lang: test_placeholder"
    fi

    # --- Placeholder replacement ---
    assert_file_contains "$test_dir/CLAUDE.md" "BUG_PATTERNS_TESTPROJ.md" "$lang: CLAUDE.md BUG_PATTERNS_PATH replaced"
    assert_no_placeholder "$test_dir/CLAUDE.md" "$lang: CLAUDE.md no active placeholders"
    assert_no_placeholder "$test_dir/REVALIDATION_TESTPROJ.md" "$lang: REVALIDATION no placeholders"

    # --- Privacy ---
    assert_file_contains "$test_dir/.gitignore" "data/" "$lang: .gitignore has privacy entries"

    # --- Git repo ---
    if [ -d "$test_dir/.git" ]; then
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $lang: git repo not initialized"
        FAIL=$((FAIL + 1))
    fi

    # --- Cleanup ---
    rm -rf "$test_dir"
}

echo "FGT new-project.sh Integration Test"
echo "===================================="
echo ""

run_test "ts"
echo ""
run_test "py"

echo ""
echo "===================================="
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    echo "INTEGRATION TEST FAILED"
    exit 1
else
    echo "INTEGRATION TEST PASSED"
fi
