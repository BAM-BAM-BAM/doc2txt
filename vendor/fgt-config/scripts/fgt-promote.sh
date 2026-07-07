#!/bin/bash
# Promote project improvements TO global FGT
# Usage: fgt-promote [project_dir] [--apply|--diff|--interactive]

set -e

PROJECT_DIR=${1:-.}
MODE=${2:---interactive}
GLOBAL_FGT="$HOME/.claude/fgt"

# Resolve to absolute path
PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)
PROJECT_NAME=$(basename "$PROJECT_DIR")

echo "============================================"
echo "FGT Promote: $PROJECT_NAME → Global"
echo "============================================"
echo ""
echo "⚠️  This will update GLOBAL templates."
echo "   Changes affect ALL future projects."
echo ""

# Find project-specific files
PATTERNS_FILE=$(ls "$PROJECT_DIR"/PATTERNS_*.md 2>/dev/null | grep -v CORE | head -1)
REVIEWS_FILE=$(ls "$PROJECT_DIR"/REVIEWS_*.md 2>/dev/null | grep -v CORE | head -1)
REVALIDATION_FILE=$(ls "$PROJECT_DIR"/REVALIDATION_*.md 2>/dev/null | head -1)
CONFIG_FILE=$(ls "$PROJECT_DIR"/CONFIG_*.md 2>/dev/null | head -1)

PATTERNS_DIFF=""
REVIEWS_DIFF=""
REVALIDATION_DIFF=""
CONFIG_DIFF=""

# Show what would change
echo "--- PATTERNS: Project → Global ---"
if [ -n "$PATTERNS_FILE" ]; then
    PATTERNS_DIFF=$(diff "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" "$PATTERNS_FILE" 2>/dev/null || true)
    if [ -z "$PATTERNS_DIFF" ]; then
        echo "✅ Already identical"
    else
        echo "Changes to promote from $(basename $PATTERNS_FILE):"
        echo "$PATTERNS_DIFF" | head -40
        [ $(echo "$PATTERNS_DIFF" | wc -l) -gt 40 ] && echo "... (truncated)"
    fi
fi

echo ""
echo "--- REVIEWS: Project → Global ---"
if [ -n "$REVIEWS_FILE" ]; then
    REVIEWS_DIFF=$(diff "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" "$REVIEWS_FILE" 2>/dev/null || true)
    if [ -z "$REVIEWS_DIFF" ]; then
        echo "✅ Already identical"
    else
        echo "Changes to promote from $(basename $REVIEWS_FILE):"
        echo "$REVIEWS_DIFF" | head -40
        [ $(echo "$REVIEWS_DIFF" | wc -l) -gt 40 ] && echo "... (truncated)"
    fi
fi

echo ""
echo "--- REVALIDATION: Project → Global ---"
if [ -n "$REVALIDATION_FILE" ]; then
    REVALIDATION_DIFF=$(diff "$GLOBAL_FGT/templates/REVALIDATION_TEMPLATE.md" "$REVALIDATION_FILE" 2>/dev/null || true)
    if [ -z "$REVALIDATION_DIFF" ]; then
        echo "✅ Already identical"
    else
        echo "Changes to promote from $(basename $REVALIDATION_FILE):"
        echo "$REVALIDATION_DIFF" | head -40
        [ $(echo "$REVALIDATION_DIFF" | wc -l) -gt 40 ] && echo "... (truncated)"
    fi
fi

echo ""
echo "--- CONFIG: Project → Global ---"
if [ -n "$CONFIG_FILE" ]; then
    CONFIG_DIFF=$(diff "$GLOBAL_FGT/templates/CONFIG_TEMPLATE.md" "$CONFIG_FILE" 2>/dev/null || true)
    if [ -z "$CONFIG_DIFF" ]; then
        echo "✅ Already identical"
    else
        echo "Changes to promote from $(basename $CONFIG_FILE):"
        echo "$CONFIG_DIFF" | head -40
        [ $(echo "$CONFIG_DIFF" | wc -l) -gt 40 ] && echo "... (truncated)"
    fi
fi

# Check if anything to do
if [ -z "$PATTERNS_DIFF" ] && [ -z "$REVIEWS_DIFF" ] && [ -z "$REVALIDATION_DIFF" ] && [ -z "$CONFIG_DIFF" ]; then
    echo ""
    echo "✅ Nothing to promote. Files are identical."
    exit 0
fi

if [ "$MODE" = "--diff" ]; then
    exit 0
fi

echo ""
echo "Options:"
echo "  [a] Promote all (copy project files to global templates)"
echo "  [p] Promote PATTERNS only"
echo "  [r] Promote REVIEWS only"
echo "  [v] Promote REVALIDATION only"
echo "  [c] Promote CONFIG only"
echo "  [s] Skip (no changes)"
echo ""
read -p "Choice: " CHOICE

case $CHOICE in
    a|A)
        [ -n "$PATTERNS_FILE" ] && [ -n "$PATTERNS_DIFF" ] && cp "$PATTERNS_FILE" "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" && echo "✅ Promoted: PATTERNS"
        [ -n "$REVIEWS_FILE" ] && [ -n "$REVIEWS_DIFF" ] && cp "$REVIEWS_FILE" "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" && echo "✅ Promoted: REVIEWS"
        [ -n "$REVALIDATION_FILE" ] && [ -n "$REVALIDATION_DIFF" ] && cp "$REVALIDATION_FILE" "$GLOBAL_FGT/templates/REVALIDATION_TEMPLATE.md" && echo "✅ Promoted: REVALIDATION"
        [ -n "$CONFIG_FILE" ] && [ -n "$CONFIG_DIFF" ] && cp "$CONFIG_FILE" "$GLOBAL_FGT/templates/CONFIG_TEMPLATE.md" && echo "✅ Promoted: CONFIG"
        ;;
    p|P)
        [ -n "$PATTERNS_FILE" ] && cp "$PATTERNS_FILE" "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" && echo "✅ Promoted: PATTERNS"
        ;;
    r|R)
        [ -n "$REVIEWS_FILE" ] && cp "$REVIEWS_FILE" "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" && echo "✅ Promoted: REVIEWS"
        ;;
    v|V)
        [ -n "$REVALIDATION_FILE" ] && cp "$REVALIDATION_FILE" "$GLOBAL_FGT/templates/REVALIDATION_TEMPLATE.md" && echo "✅ Promoted: REVALIDATION"
        ;;
    c|C)
        [ -n "$CONFIG_FILE" ] && cp "$CONFIG_FILE" "$GLOBAL_FGT/templates/CONFIG_TEMPLATE.md" && echo "✅ Promoted: CONFIG"
        ;;
    *)
        echo "Skipped."
        exit 0
        ;;
esac

# Commit to git
echo ""
read -p "Commit to git? (y/n): " COMMIT
if [ "$COMMIT" = "y" ] || [ "$COMMIT" = "Y" ]; then
    cd "$GLOBAL_FGT"
    git add templates/
    read -p "Commit message: " MSG
    git commit -m "${MSG:-FGT: Promoted changes from $PROJECT_NAME}"
    echo "✅ Committed"
    
    read -p "Push to origin? (y/n): " PUSH
    if [ "$PUSH" = "y" ] || [ "$PUSH" = "Y" ]; then
        git push origin main && echo "✅ Pushed" || echo "⚠️  Push failed"
    fi
fi
