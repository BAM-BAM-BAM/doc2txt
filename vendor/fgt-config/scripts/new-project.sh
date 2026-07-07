#!/bin/bash
# new-project.sh — Full FGT project scaffold with interactive Q&A.
#
# Usage:
#   new-project.sh [PROJECT_DIR] [DOMAIN] [--lang ts|py] [--privacy] [--lite]
#
# Interactive mode (no args): prompts for all values.
# Non-interactive: pass all args on command line.
#
# Creates: FGT docs, hooks, tests, CI, src skeleton, config validation,
# pre-commit hooks, .claude/settings.json — everything for Day 1 compliance.
#
# --lite: minimal scaffold for unproven projects — git, .gitignore, lang
# config, src skeleton, ONE QUAL test stub, local+remote CI, a stub
# CLAUDE.md, and a .fgt-lite marker. No FGT docs, hooks, sweep, or
# BACKLOG. Upgrade by rerunning without --lite once the project survives
# (~20 commits or first external consumer). Rationale: five fully-
# scaffolded projects stalled at <=13 commits (METHODOLOGY_LOG 2026-07-03).
set -euo pipefail

GLOBAL_FGT_DIR="${GLOBAL_FGT_DIR:-$HOME/.claude/fgt}"
SCAFFOLD_DIR="$GLOBAL_FGT_DIR/templates/scaffold"

# --- Parse args ---
PROJECT_DIR=""
DOMAIN=""
LANG=""
PRIVACY=false
LITE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --lang) LANG="$2"; shift 2 ;;
        --privacy) PRIVACY=true; shift ;;
        --lite) LITE=true; shift ;;
        *)
            if [ -z "$PROJECT_DIR" ]; then
                PROJECT_DIR="$1"
            elif [ -z "$DOMAIN" ]; then
                DOMAIN="$1"
            fi
            shift ;;
    esac
done

# --- Interactive Q&A if values missing ---
if [ -z "$PROJECT_DIR" ]; then
    read -rp "Project directory [.]: " PROJECT_DIR
    PROJECT_DIR=${PROJECT_DIR:-.}
fi

if [ -z "$DOMAIN" ]; then
    read -rp "Domain suffix (e.g., EVENTS, BUMBLEUP, DOC): " DOMAIN
    DOMAIN=${DOMAIN:-GENERIC}
fi

if [ -z "$LANG" ]; then
    echo ""
    echo "Language:"
    echo "  ts  — TypeScript (vitest, eslint, zod)"
    echo "  py  — Python (pytest, ruff, pydantic)"
    read -rp "Choose [ts/py]: " LANG
    LANG=${LANG:-ts}
fi

if [ "$PRIVACY" = false ]; then
    read -rp "Privacy-sensitive project? (extra .gitignore, no remote CI) [y/N]: " PRIV_ANS
    [[ "$PRIV_ANS" =~ ^[Yy] ]] && PRIVACY=true
fi

# --- Derived values ---
PROJECT_LOWER=$(echo "$DOMAIN" | tr '[:upper:]' '[:lower:]')
DOMAIN_UPPER=$(echo "$DOMAIN" | tr '[:lower:]' '[:upper:]')
DOMAIN="$DOMAIN_UPPER"

# Compute Claude memory dir path (dashes replace slashes in absolute path)
ABS_PROJECT_DIR=$(cd "$PROJECT_DIR" 2>/dev/null && pwd || echo "$PROJECT_DIR")
MEMORY_DIR_SUFFIX=$(echo "$ABS_PROJECT_DIR" | sed 's|^/||; s|/|-|g')
MEMORY_DIR="\$HOME/.claude/projects/-${MEMORY_DIR_SUFFIX}/memory"

if [ "$LANG" = "ts" ]; then
    TEST_CMD="npx vitest run"
    BUILD_CMD="npx tsc --noEmit"
    LINT_CMD="npx eslint src/ tests/"
    TEST_EXT=".test.ts"
    SRC_EXT=".ts"
elif [ "$LANG" = "py" ]; then
    TEST_CMD="python -m pytest tests/ -v"
    BUILD_CMD="python -m ruff check ."
    LINT_CMD="python -m ruff check ."
    TEST_EXT=".py"
    SRC_EXT=".py"
else
    echo "ERROR: --lang must be 'ts' or 'py'" >&2
    exit 1
fi

echo ""
echo "=========================================="
if [ "$LITE" = true ]; then
    echo "  FGT Scaffold-Lite (unproven project)"
else
    echo "  FGT Full Project Scaffold"
fi
echo "=========================================="
echo "  Directory:  $PROJECT_DIR"
echo "  Domain:     $DOMAIN"
echo "  Language:   $LANG"
echo "  Privacy:    $PRIVACY"
echo "=========================================="
echo ""

cd "$PROJECT_DIR"

# --- Phase 1: Git init if needed ---
if [ ! -d ".git" ]; then
    git init
    git branch -m main 2>/dev/null || true
    echo "   [+] git init (main branch)"
fi

# --- Phase 2: .gitignore ---
if [ "$LANG" = "ts" ]; then
    cat > .gitignore << 'GITEOF'
node_modules/
dist/
.env
.env.*
!.env.example
.DS_Store
GITEOF
else
    cat > .gitignore << 'GITEOF'
__pycache__/
*.pyc
.venv/
venv/
dist/
*.egg-info/
.env
.env.*
!.env.example
.DS_Store
GITEOF
fi

if [ "$PRIVACY" = true ]; then
    cat >> .gitignore << 'GITEOF'

# Privacy — sensitive data never leaves local
data/
profiles/
chats/
*.sqlite
GITEOF
fi
echo "   [+] .gitignore"

# ============================================================
# --lite path: minimal scaffold, then exit before the FGT phases.
# ============================================================
if [ "$LITE" = true ]; then
    # Language config + src skeleton (same templates as full mode)
    if [ "$LANG" = "ts" ]; then
        for TMPL in package.json.tmpl tsconfig.json.tmpl eslint.config.js.tmpl vitest.config.ts.tmpl; do
            DEST=$(echo "$TMPL" | sed 's/\.tmpl$//')
            if [ -f "$SCAFFOLD_DIR/ts/$TMPL" ]; then
                cp "$SCAFFOLD_DIR/ts/$TMPL" "$DEST"
                sed -i "s|{{PROJECT_LOWER}}|$PROJECT_LOWER|g; s|{{DOMAIN}}|$DOMAIN|g" "$DEST"
            fi
        done
        mkdir -p src
        if [ -f "$SCAFFOLD_DIR/ts/src/config.ts.tmpl" ]; then
            cp "$SCAFFOLD_DIR/ts/src/config.ts.tmpl" "src/config.ts"
            sed -i "s|{{DOMAIN}}|$DOMAIN|g" "src/config.ts"
        fi
    else
        if [ -f "$SCAFFOLD_DIR/py/pyproject.toml.tmpl" ]; then
            cp "$SCAFFOLD_DIR/py/pyproject.toml.tmpl" "pyproject.toml"
            sed -i "s|{{PROJECT_LOWER}}|$PROJECT_LOWER|g; s|{{DOMAIN}}|$DOMAIN|g" "pyproject.toml"
        fi
        mkdir -p src
        [ -f "$SCAFFOLD_DIR/py/src/__init__.py.tmpl" ] && cp "$SCAFFOLD_DIR/py/src/__init__.py.tmpl" "src/__init__.py"
        if [ -f "$SCAFFOLD_DIR/py/src/config.py.tmpl" ]; then
            cp "$SCAFFOLD_DIR/py/src/config.py.tmpl" "src/config.py"
            sed -i "s|{{DOMAIN}}|$DOMAIN|g" "src/config.py"
        fi
    fi
    echo "   [+] Language config + src skeleton"

    # One QUAL test stub — output quality from day 1 (CP-008)
    mkdir -p tests
    if [ "$LANG" = "ts" ]; then
        cat > "tests/qual.test.ts" << 'QUALEOF'
import { describe, test } from 'vitest'

describe('QUAL-001 — output quality', () => {
    // Replace with the first real assertion about a value a user sees.
    // Not "the pipeline ran" — "the number/string/artifact is right."
    test.todo('first user-facing output value is correct')
})
QUALEOF
    else
        cat > "tests/test_qual.py" << 'QUALEOF'
import pytest


def test_QUAL_001_first_output_value_is_correct():
    """Replace with the first real assertion about a value a user sees.

    Not "the pipeline ran" — "the number/string/artifact is right."
    """
    pytest.skip("QUAL-001 stub: assert your first user-facing output value")
QUALEOF
    fi
    echo "   [+] tests/ (one QUAL-001 stub)"

    # Local CI
    mkdir -p scripts
    if [ -f "$SCAFFOLD_DIR/ci/ci-local.sh.tmpl" ]; then
        cp "$SCAFFOLD_DIR/ci/ci-local.sh.tmpl" "scripts/ci-local.sh"
        sed -i "s|{{PROJECT_LOWER}}|$PROJECT_LOWER|g; s|{{LINT_CMD}}|$LINT_CMD|g; s|{{BUILD_CMD}}|$BUILD_CMD|g; s|{{TEST_CMD}}|$TEST_CMD|g" "scripts/ci-local.sh"
        chmod +x "scripts/ci-local.sh"
        echo "   [+] scripts/ci-local.sh"
    fi

    # Remote CI — lint + tests only (no FGT validation step: no FGT files yet)
    mkdir -p .github/workflows
    if [ "$LANG" = "ts" ]; then
        cat > ".github/workflows/verify.yml" << 'CIEOF'
name: Verify
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
      - run: npm ci
      - name: Lint
        run: npx eslint src/ tests/
      - name: Type check
        run: npx tsc --noEmit
      - name: Tests
        run: npx vitest run
CIEOF
    else
        cat > ".github/workflows/verify.yml" << 'CIEOF'
name: Verify
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e ".[dev]"
      - name: Lint
        run: python -m ruff check .
      - name: Tests
        run: python -m pytest tests/ -v
CIEOF
    fi
    echo "   [+] .github/workflows/verify.yml (lint + tests; no FGT step yet)"

    # Stub CLAUDE.md — mentions FGT so fgt-guard-write.sh allows writes here
    cat > "CLAUDE.md" << EOF
# ${DOMAIN} — FGT scaffold-lite

This project uses the FGT scaffold-lite (unproven-project mode): git,
CI, and one QUAL test stub. Full FGT (domain docs, BUG_PATTERNS,
BACKLOG, sweep, hooks) is deferred until the project survives.

**Upgrade trigger — whichever comes first:**
- ~20 commits of sustained work, or
- the first external consumer (another project, a user, a deployment)

**Upgrade:** rerun \`~/.claude/fgt/scripts/new-project.sh . ${DOMAIN} --lang ${LANG}\`
(without \`--lite\`), then write FGT_DOMAIN_${DOMAIN}.md from scratch.

Test: \`$TEST_CMD\` · Lint: \`$LINT_CMD\`
EOF
    echo "   [+] CLAUDE.md (lite stub with upgrade trigger)"

    date -I > .fgt-lite
    echo "   [+] .fgt-lite marker"

    echo ""
    echo "=========================================="
    echo "  Scaffold-lite complete."
    echo "=========================================="
    echo ""
    echo "  Deferred until the upgrade trigger (see CLAUDE.md):"
    echo "    FGT domain docs, BUG_PATTERNS, BACKLOG, sweep.sh, hooks"
    echo ""
    exit 0
fi

# --- Phase 3: FGT documentation files ---
# Symlink FGT.md
ln -sf "$GLOBAL_FGT_DIR/FGT.md" FGT.md
echo "   [+] FGT.md -> symlink"

# Copy and rename templates
for TMPL in PATTERNS_TEMPLATE.md REVIEWS_TEMPLATE.md FGT_DOMAIN_TEMPLATE.md \
            BUG_PATTERNS_TEMPLATE.md EXPERT_REVIEWERS_TEMPLATE.md \
            REVALIDATION_TEMPLATE.md CONFIG_TEMPLATE.md; do
    if [ -f "$GLOBAL_FGT_DIR/templates/$TMPL" ]; then
        DEST=$(echo "$TMPL" | sed "s/_TEMPLATE\.md/_${DOMAIN}.md/")
        cp "$GLOBAL_FGT_DIR/templates/$TMPL" "$DEST"
        echo "   [+] $DEST"
    fi
done

# Non-domain-suffixed files
if [ -f "$GLOBAL_FGT_DIR/templates/BACKLOG_TEMPLATE.md" ]; then
    cp "$GLOBAL_FGT_DIR/templates/BACKLOG_TEMPLATE.md" "BACKLOG.md"
    echo "   [+] BACKLOG.md"
fi

if [ -f "$GLOBAL_FGT_DIR/templates/SPEC_TEMPLATE.md" ]; then
    cp "$GLOBAL_FGT_DIR/templates/SPEC_TEMPLATE.md" "SPEC.md"
    echo "   [+] SPEC.md"
fi

if [ -f "$GLOBAL_FGT_DIR/templates/CLAUDE_MD_TEMPLATE.md" ]; then
    cp "$GLOBAL_FGT_DIR/templates/CLAUDE_MD_TEMPLATE.md" "CLAUDE.md"
    echo "   [+] CLAUDE.md"
fi

# FGT_LOG.md
cat > "FGT_LOG.md" << EOF
# FGT Development Log: ${DOMAIN}

| Date | Task ID | Summary | Lessons |
|------|---------|---------|---------|

(Add entries here)
EOF
echo "   [+] FGT_LOG.md"

# Replace placeholders in FGT docs
for f in *.md; do
    [ "$f" = "FGT.md" ] && continue
    if grep -q '{{PROJECT}}\|{{DOMAIN}}' "$f" 2>/dev/null; then
        sed -i "s/{{PROJECT}}/$DOMAIN/g; s/{{DOMAIN}}/$DOMAIN/g" "$f"
    fi
done

# Replace CLAUDE.md specific placeholders
if [ -f "CLAUDE.md" ]; then
    sed -i "s|{{TEST_COMMAND}}|$TEST_CMD|g" "CLAUDE.md"
    sed -i "s|{{BUILD_COMMAND}}|$BUILD_CMD|g" "CLAUDE.md"
    sed -i "s|{{BUG_PATTERNS_PATH}}|BUG_PATTERNS_${DOMAIN}.md|g" "CLAUDE.md"
fi
echo "   [+] Placeholders replaced"

# --- Phase 4: Hook scripts ---
mkdir -p scripts
for HOOK_TMPL in fgt_session_start.sh fgt_session_persist.sh fgt_stop_check.sh; do
    if [ -f "$SCAFFOLD_DIR/hooks/${HOOK_TMPL}.tmpl" ]; then
        cp "$SCAFFOLD_DIR/hooks/${HOOK_TMPL}.tmpl" "scripts/$HOOK_TMPL"
        sed -i "s|{{MEMORY_DIR}}|$MEMORY_DIR|g" "scripts/$HOOK_TMPL"
        sed -i "s|{{PROJECT_LOWER}}|$PROJECT_LOWER|g" "scripts/$HOOK_TMPL"
        sed -i "s|{{DOMAIN}}|$DOMAIN|g" "scripts/$HOOK_TMPL"
        # Write language-specific test runner into persist hook
        if [ "$HOOK_TMPL" = "fgt_session_persist.sh" ]; then
            if [ "$LANG" = "ts" ]; then
                cat > /tmp/_fgt_test_block << 'TSEOF'
    if [ -f "$PROJECT_DIR/node_modules/.bin/vitest" ]; then
        cd "$PROJECT_DIR" && npx vitest run 2>&1 | tail -5 || true
    else
        echo "(no node_modules — skipping test run)"
    fi
TSEOF
            else
                cat > /tmp/_fgt_test_block << 'PYEOF'
    if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
        cd "$PROJECT_DIR" && .venv/bin/python -m pytest tests/ -q 2>&1 | tail -3 || true
    else
        echo "(no .venv — skipping test run)"
    fi
PYEOF
            fi
            # Replace the placeholder line with the test block
            sed -i '/echo "(test snapshot not configured/r /tmp/_fgt_test_block' "scripts/$HOOK_TMPL"
            sed -i '/echo "(test snapshot not configured/d' "scripts/$HOOK_TMPL"
            rm -f /tmp/_fgt_test_block
        fi
        chmod +x "scripts/$HOOK_TMPL"
    fi
done
echo "   [+] Hook scripts (session_start, session_persist, stop_check)"

# --- Phase 4b: OCD sweep script ---
if [ -f "$GLOBAL_FGT_DIR/templates/SWEEP_TEMPLATE.sh" ]; then
    cp "$GLOBAL_FGT_DIR/templates/SWEEP_TEMPLATE.sh" "scripts/sweep.sh"
    sed -i "s/{{PROJECT}}/$DOMAIN/g" "scripts/sweep.sh"
    chmod +x "scripts/sweep.sh"
    echo "   [+] scripts/sweep.sh (OCD project sweep)"
fi

# --- Phase 5: .claude/settings.json ---
mkdir -p .claude
if [ -f "$SCAFFOLD_DIR/claude/settings.json.tmpl" ]; then
    cp "$SCAFFOLD_DIR/claude/settings.json.tmpl" ".claude/settings.json"
fi
echo "   [+] .claude/settings.json"

# --- Phase 6: Test structure ---
mkdir -p tests
if [ "$LANG" = "ts" ]; then
    for TMPL in setup.ts.tmpl test_invariants.test.ts.tmpl test_proactive.test.ts.tmpl test_placeholder.test.ts.tmpl; do
        DEST=$(echo "$TMPL" | sed 's/\.tmpl$//')
        if [ -f "$SCAFFOLD_DIR/ts/tests/$TMPL" ]; then
            cp "$SCAFFOLD_DIR/ts/tests/$TMPL" "tests/$DEST"
            sed -i "s|{{DOMAIN}}|$DOMAIN|g" "tests/$DEST"
        fi
    done
elif [ "$LANG" = "py" ]; then
    for TMPL in conftest.py.tmpl test_invariants.py.tmpl test_proactive.py.tmpl test_placeholder.py.tmpl; do
        DEST=$(echo "$TMPL" | sed 's/\.tmpl$//')
        if [ -f "$SCAFFOLD_DIR/py/tests/$TMPL" ]; then
            cp "$SCAFFOLD_DIR/py/tests/$TMPL" "tests/$DEST"
            sed -i "s|{{DOMAIN}}|$DOMAIN|g" "tests/$DEST"
        fi
    done
fi
echo "   [+] Test stubs"

# --- Phase 7: Project config files ---
if [ "$LANG" = "ts" ]; then
    for TMPL in package.json.tmpl tsconfig.json.tmpl eslint.config.js.tmpl vitest.config.ts.tmpl; do
        DEST=$(echo "$TMPL" | sed 's/\.tmpl$//')
        if [ -f "$SCAFFOLD_DIR/ts/$TMPL" ]; then
            cp "$SCAFFOLD_DIR/ts/$TMPL" "$DEST"
            sed -i "s|{{PROJECT_LOWER}}|$PROJECT_LOWER|g" "$DEST"
            sed -i "s|{{DOMAIN}}|$DOMAIN|g" "$DEST"
        fi
    done
    echo "   [+] package.json, tsconfig.json, eslint.config.js, vitest.config.ts"
elif [ "$LANG" = "py" ]; then
    if [ -f "$SCAFFOLD_DIR/py/pyproject.toml.tmpl" ]; then
        cp "$SCAFFOLD_DIR/py/pyproject.toml.tmpl" "pyproject.toml"
        sed -i "s|{{PROJECT_LOWER}}|$PROJECT_LOWER|g" "pyproject.toml"
        sed -i "s|{{DOMAIN}}|$DOMAIN|g" "pyproject.toml"
    fi
    echo "   [+] pyproject.toml"
fi

# --- Phase 8: Source skeleton ---
mkdir -p src
if [ "$LANG" = "ts" ]; then
    if [ -f "$SCAFFOLD_DIR/ts/src/config.ts.tmpl" ]; then
        cp "$SCAFFOLD_DIR/ts/src/config.ts.tmpl" "src/config.ts"
        sed -i "s|{{DOMAIN}}|$DOMAIN|g" "src/config.ts"
    fi
    echo "   [+] src/config.ts (Zod validated)"
elif [ "$LANG" = "py" ]; then
    if [ -f "$SCAFFOLD_DIR/py/src/__init__.py.tmpl" ]; then
        cp "$SCAFFOLD_DIR/py/src/__init__.py.tmpl" "src/__init__.py"
    fi
    if [ -f "$SCAFFOLD_DIR/py/src/config.py.tmpl" ]; then
        cp "$SCAFFOLD_DIR/py/src/config.py.tmpl" "src/config.py"
        sed -i "s|{{DOMAIN}}|$DOMAIN|g" "src/config.py"
    fi
    echo "   [+] src/__init__.py, src/config.py (Pydantic validated)"
fi

# --- Phase 9: Git hooks ---
mkdir -p scripts/git-hooks
if [ -f "$SCAFFOLD_DIR/git-hooks/pre-commit-${LANG}.tmpl" ]; then
    cp "$SCAFFOLD_DIR/git-hooks/pre-commit-${LANG}.tmpl" "scripts/git-hooks/pre-commit"
    sed -i "s|{{DOMAIN}}|$DOMAIN|g" "scripts/git-hooks/pre-commit"
    chmod +x "scripts/git-hooks/pre-commit"
fi
if [ -f "$SCAFFOLD_DIR/git-hooks/install-hooks.sh.tmpl" ]; then
    cp "$SCAFFOLD_DIR/git-hooks/install-hooks.sh.tmpl" "scripts/install-hooks.sh"
    chmod +x "scripts/install-hooks.sh"
fi
echo "   [+] Git hooks (pre-commit + install-hooks.sh)"

# --- Phase 10: Local CI ---
if [ -f "$SCAFFOLD_DIR/ci/ci-local.sh.tmpl" ]; then
    cp "$SCAFFOLD_DIR/ci/ci-local.sh.tmpl" "scripts/ci-local.sh"
    sed -i "s|{{PROJECT_LOWER}}|$PROJECT_LOWER|g" "scripts/ci-local.sh"
    sed -i "s|{{LINT_CMD}}|$LINT_CMD|g" "scripts/ci-local.sh"
    sed -i "s|{{BUILD_CMD}}|$BUILD_CMD|g" "scripts/ci-local.sh"
    sed -i "s|{{TEST_CMD}}|$TEST_CMD|g" "scripts/ci-local.sh"
    chmod +x "scripts/ci-local.sh"
fi
echo "   [+] scripts/ci-local.sh"

# --- Phase 11: GitHub Actions (template, dormant if privacy) ---
# Resolve the fgt-config commit SHA to pin the scaffolded CI against. An
# unpinned clone of fgt-config@HEAD in CI gives the upstream org arbitrary
# code execution in every build — avoid that by emitting a specific SHA.
# Prefer the canonical repo; otherwise emit a placeholder that fails loudly.
FGT_SHA=""
CANONICAL_FGT_REPO="${CANONICAL_FGT_REPO:-$HOME/projects/fgt-config}"
if [ -d "$CANONICAL_FGT_REPO/.git" ] && command -v git >/dev/null 2>&1; then
    FGT_SHA=$(git -C "$CANONICAL_FGT_REPO" rev-parse HEAD 2>/dev/null || echo "")
fi
if [ -z "$FGT_SHA" ]; then
    FGT_SHA="REPLACE_WITH_FGT_CONFIG_SHA"
    echo "   [!] Could not resolve fgt-config SHA; scaffolding with placeholder." >&2
    echo "   [!] Set FGT_SHA in .github/workflows/verify.yml before enabling CI." >&2
fi

mkdir -p .github/workflows
if [ "$LANG" = "ts" ]; then
    cat > ".github/workflows/verify.yml" << 'CIEOF'
name: Verify
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
      - run: npm ci
      - name: Lint
        run: npx eslint src/ tests/
      - name: Type check
        run: npx tsc --noEmit
      - name: Tests
        run: npx vitest run
      - name: FGT validation
        # Pin fgt-config to a specific commit SHA. Unpinned HEAD-clone lets a
        # compromise of BAM-BAM-BAM/fgt-config execute arbitrary Node code in
        # this CI job with access to job secrets. Bump FGT_SHA when
        # intentionally adopting new validator behavior.
        env:
          FGT_SHA: __FGT_SHA__
        run: |
          git clone https://github.com/BAM-BAM-BAM/fgt-config /tmp/fgt
          git -C /tmp/fgt checkout "$FGT_SHA"
          node /tmp/fgt/scripts/validate-fgt.mjs --project .
CIEOF
elif [ "$LANG" = "py" ]; then
    cat > ".github/workflows/verify.yml" << 'CIEOF'
name: Verify
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e ".[dev]"
      - name: Lint
        run: python -m ruff check .
      - name: Tests
        run: python -m pytest tests/ -v
      - name: FGT validation
        # Pin fgt-config to a specific commit SHA. Unpinned HEAD-clone lets a
        # compromise of BAM-BAM-BAM/fgt-config execute arbitrary Node code in
        # this CI job with access to job secrets. Bump FGT_SHA when
        # intentionally adopting new validator behavior.
        if: hashFiles('package.json') != ''
        env:
          FGT_SHA: __FGT_SHA__
        run: |
          git clone https://github.com/BAM-BAM-BAM/fgt-config /tmp/fgt
          git -C /tmp/fgt checkout "$FGT_SHA"
          node /tmp/fgt/scripts/validate-fgt.mjs --project .
CIEOF
fi

# Substitute the resolved SHA (or loud placeholder) into the emitted workflow.
sed -i "s|__FGT_SHA__|${FGT_SHA}|g" .github/workflows/verify.yml
if [ "$PRIVACY" = true ]; then
    echo "   [+] .github/workflows/verify.yml (DORMANT — privacy mode, no remote CI)"
else
    echo "   [+] .github/workflows/verify.yml"
fi

# --- Phase 12: Replace remaining placeholders in REVALIDATION ---
for f in REVALIDATION_*.md CONFIG_*.md; do
    [ -f "$f" ] || continue
    sed -i 's/{{THRESHOLD_PCT}}/50/g; s/{{THRESHOLD_COUNT}}/50/g' "$f"
    sed -i 's/{{RETENTION_DAYS}}/30/g; s|{{STAGING_PATH}}|data/staging/|g' "$f"
done

# Full scaffold supersedes a prior --lite scaffold
rm -f .fgt-lite

# --- Validation ---
echo ""
UNREPLACED=$(grep -rl '{{' *.md 2>/dev/null | grep -v FGT.md || true)
if [ -n "$UNREPLACED" ]; then
    echo "   [!] Files with remaining {{placeholders}}:"
    for f in $UNREPLACED; do
        PLACEHOLDERS=$(grep -oP '\{\{[^}]+\}\}' "$f" 2>/dev/null | sort -u | tr '\n' ', ')
        echo "      $f: $PLACEHOLDERS"
    done
else
    echo "   [+] All placeholders replaced"
fi

if [ -f "$GLOBAL_FGT_DIR/scripts/validate-fgt.mjs" ] && command -v node &>/dev/null; then
    echo ""
    node "$GLOBAL_FGT_DIR/scripts/validate-fgt.mjs" --project "$(pwd)" 2>&1 | sed 's/^/   /'
fi

# --- Summary ---
echo ""
echo "=========================================="
echo "  FGT scaffold complete!"
echo "=========================================="
echo ""
echo "  Files created:"
find . -maxdepth 3 -name "*.md" -o -name "*.ts" -o -name "*.js" -o -name "*.py" \
     -o -name "*.json" -o -name "*.toml" -o -name "*.yml" -o -name "*.sh" \
     -o -name ".gitignore" 2>/dev/null | grep -v node_modules | grep -v .git/ | sort | sed 's/^/    /'
echo ""
echo "  Next steps:"
echo "    1. Write domain-specific content in FGT_DOMAIN_${DOMAIN}.md (FROM SCRATCH)"
echo "    2. Write domain-specific patterns in PATTERNS_${DOMAIN}.md (FROM SCRATCH)"
if [ "$LANG" = "ts" ]; then
    echo "    3. Run: npm install --legacy-peer-deps"
fi
echo "    4. Run: git add -A && git commit -m 'feat: scaffold FGT-compliant project (Principle 10)'"
echo "    5. Run: bash scripts/install-hooks.sh"
echo ""
