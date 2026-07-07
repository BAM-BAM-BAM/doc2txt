#!/bin/bash
# Check FGT sync status across all projects
# Usage: fgt-status

GLOBAL_FGT="${GLOBAL_FGT:-$HOME/.claude/fgt}"
FGT_REPO="${FGT_REPO:-$HOME/projects/fgt-config}"
PROJECTS_DIR="${PROJECTS_DIR:-$HOME/projects}"

echo "============================================"
echo "FGT Status: All Projects"
echo "============================================"

# Install target status (deployed artifact, not a working copy since Phase 1)
echo ""
echo "=== Install target (~/.claude/fgt/) ==="
echo "Location: $GLOBAL_FGT"
if [ -d "$GLOBAL_FGT" ]; then
    fgt_mtime=$(stat -c %y "$GLOBAL_FGT/FGT.md" 2>/dev/null | cut -d. -f1)
    echo "Status:   ✅ Installed (FGT.md mtime: ${fgt_mtime:-unknown})"
else
    echo "Status:   ❌ Not installed — run: bash $FGT_REPO/scripts/install.sh"
fi

# Canonical working copy status (the git repo — where edits happen)
echo ""
echo "=== Canonical source (fgt-config working copy) ==="
if [ -d "$FGT_REPO/.git" ]; then
    cd "$FGT_REPO"
    echo "Location: $FGT_REPO"
    echo "Branch:   $(git branch --show-current)"
    echo "Remote:   $(git remote get-url origin 2>/dev/null || echo 'none')"

    UNCOMMITTED=$(git status --porcelain | wc -l)
    if [ "$UNCOMMITTED" -gt 0 ]; then
        echo "Status:   ⚠️  $UNCOMMITTED uncommitted changes"
    else
        echo "Status:   ✅ Clean"
    fi

    # Show sync gap: is install target stale vs. canonical?
    if [ -f "$GLOBAL_FGT/FGT.md" ]; then
        if ! diff -q "$FGT_REPO/FGT.md" "$GLOBAL_FGT/FGT.md" > /dev/null 2>&1; then
            echo "Sync:     ⚠️  Install target differs from canonical — run: bash scripts/install.sh"
        else
            echo "Sync:     ✅ Install target matches canonical"
        fi
    fi
else
    echo "Location: $FGT_REPO (not a git repo or does not exist)"
    echo "Status:   ❌ Canonical source not found"
fi

# Check each project
echo ""
echo "=== Projects ==="

for PROJECT_DIR in "$PROJECTS_DIR"/*/; do
    [ ! -d "$PROJECT_DIR" ] && continue
    PROJECT=$(basename "$PROJECT_DIR")
    
    # Check if FGT-enabled
    if [ ! -f "$PROJECT_DIR/FGT.md" ] && [ ! -L "$PROJECT_DIR/FGT.md" ]; then
        continue
    fi
    
    echo ""
    echo "--- $PROJECT ---"
    
    # Check FGT.md symlink
    if [ -L "$PROJECT_DIR/FGT.md" ]; then
        TARGET=$(readlink "$PROJECT_DIR/FGT.md")
        if [ -f "$TARGET" ]; then
            echo "  FGT.md:     ✅ Symlink OK"
        else
            echo "  FGT.md:     ❌ Broken symlink → $TARGET"
        fi
    else
        echo "  FGT.md:     ⚠️  Regular file (should be symlink)"
    fi
    
    # Check PATTERNS
    PATTERNS_FILE=$(ls "$PROJECT_DIR"/PATTERNS_*.md 2>/dev/null | grep -v CORE | head -1)
    if [ -n "$PATTERNS_FILE" ]; then
        if diff -q "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" "$PATTERNS_FILE" >/dev/null 2>&1; then
            echo "  PATTERNS:   ✅ In sync"
        else
            DIFF_LINES=$(diff "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" "$PATTERNS_FILE" 2>/dev/null | wc -l)
            echo "  PATTERNS:   ⚠️  Diverged ($DIFF_LINES lines)"
        fi
    else
        echo "  PATTERNS:   ⏭️  Not found"
    fi
    
    # Check REVIEWS
    REVIEWS_FILE=$(ls "$PROJECT_DIR"/REVIEWS_*.md 2>/dev/null | grep -v CORE | head -1)
    if [ -n "$REVIEWS_FILE" ]; then
        if diff -q "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" "$REVIEWS_FILE" >/dev/null 2>&1; then
            echo "  REVIEWS:    ✅ In sync"
        else
            DIFF_LINES=$(diff "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" "$REVIEWS_FILE" 2>/dev/null | wc -l)
            echo "  REVIEWS:    ⚠️  Diverged ($DIFF_LINES lines)"
        fi
    else
        echo "  REVIEWS:    ⏭️  Not found"
    fi
    
    # Check REVALIDATION
    REVALIDATION_FILE=$(ls "$PROJECT_DIR"/REVALIDATION_*.md 2>/dev/null | head -1)
    if [ -n "$REVALIDATION_FILE" ]; then
        if diff -q "$GLOBAL_FGT/templates/REVALIDATION_TEMPLATE.md" "$REVALIDATION_FILE" >/dev/null 2>&1; then
            echo "  REVALIDATION: ✅ In sync"
        else
            DIFF_LINES=$(diff "$GLOBAL_FGT/templates/REVALIDATION_TEMPLATE.md" "$REVALIDATION_FILE" 2>/dev/null | wc -l)
            echo "  REVALIDATION: ⚠️  Diverged ($DIFF_LINES lines)"
        fi
    else
        echo "  REVALIDATION: ⏭️  Not found"
    fi

    # Check CONFIG
    CONFIG_FILE=$(ls "$PROJECT_DIR"/CONFIG_*.md 2>/dev/null | head -1)
    if [ -n "$CONFIG_FILE" ]; then
        if diff -q "$GLOBAL_FGT/templates/CONFIG_TEMPLATE.md" "$CONFIG_FILE" >/dev/null 2>&1; then
            echo "  CONFIG:     ✅ In sync"
        else
            DIFF_LINES=$(diff "$GLOBAL_FGT/templates/CONFIG_TEMPLATE.md" "$CONFIG_FILE" 2>/dev/null | wc -l)
            echo "  CONFIG:     ⚠️  Diverged ($DIFF_LINES lines)"
        fi
    else
        echo "  CONFIG:     ⏭️  Not found"
    fi

    # Check domain file exists
    DOMAIN_FILE=$(ls "$PROJECT_DIR"/FGT_DOMAIN_*.md 2>/dev/null | head -1)
    if [ -n "$DOMAIN_FILE" ]; then
        echo "  DOMAIN:     ✅ $(basename $DOMAIN_FILE)"
    else
        echo "  DOMAIN:     ⏭️  Not found"
    fi

    # Check FGT_LOG fill rate
    FGT_LOG="$PROJECT_DIR/FGT_LOG.md"
    if [ -f "$FGT_LOG" ]; then
        ENTRY_COUNT=$(grep -c '^|' "$FGT_LOG" 2>/dev/null || echo 0)
        # Subtract header rows (table header + separator)
        ENTRY_COUNT=$((ENTRY_COUNT > 2 ? ENTRY_COUNT - 2 : 0))
        COMMIT_COUNT=$(git -C "$PROJECT_DIR" rev-list --count HEAD 2>/dev/null || echo 0)
        EXPECTED=$((COMMIT_COUNT / 5))
        if [ "$ENTRY_COUNT" -lt "$EXPECTED" ] && [ "$COMMIT_COUNT" -ge 10 ]; then
            echo "  FGT_LOG:    ⚠️  $ENTRY_COUNT entries / $COMMIT_COUNT commits (expect ~$EXPECTED)"
        else
            echo "  FGT_LOG:    ✅ $ENTRY_COUNT entries ($COMMIT_COUNT commits)"
        fi
    else
        echo "  FGT_LOG:    ❌ Not found"
    fi

    # Check BUG_PATTERNS
    BUG_PATTERNS=$(ls "$PROJECT_DIR"/BUG_PATTERNS*.md 2>/dev/null | head -1)
    if [ -n "$BUG_PATTERNS" ]; then
        echo "  BUG_PATTERNS: ✅ $(basename $BUG_PATTERNS)"
    else
        echo "  BUG_PATTERNS: ❌ Not found (required by FGT)"
    fi

    # Check BACKLOG
    if [ -f "$PROJECT_DIR/BACKLOG.md" ]; then
        echo "  BACKLOG:    ✅ Present"
    else
        echo "  BACKLOG:    ❌ Not found (required by Principle 9)"
    fi
done

echo ""
echo "============================================"
echo "Commands:"
echo "  fgt-sync <project>    - Sync global → project"
echo "  fgt-promote <project> - Promote project → global"
echo "============================================"
