#!/bin/bash
# Sync global FGT updates TO a project
# Usage: fgt-sync [project_dir] [--apply|--diff|--interactive]

set -e

PROJECT_DIR=${1:-.}
MODE=${2:---interactive}
GLOBAL_FGT="$HOME/.claude/fgt"

# Resolve to absolute path
PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)
PROJECT_NAME=$(basename "$PROJECT_DIR")

echo "============================================"
echo "FGT Sync: Global → $PROJECT_NAME"
echo "============================================"

# Verify project has FGT
if [ ! -f "$PROJECT_DIR/FGT.md" ] && [ ! -L "$PROJECT_DIR/FGT.md" ]; then
    echo "❌ No FGT.md found in $PROJECT_DIR"
    echo "   Run: fgt-new-project $PROJECT_DIR"
    exit 1
fi

# Find project-specific files
PATTERNS_FILE=$(ls "$PROJECT_DIR"/PATTERNS_*.md 2>/dev/null | grep -v CORE | head -1)
REVIEWS_FILE=$(ls "$PROJECT_DIR"/REVIEWS_*.md 2>/dev/null | grep -v CORE | head -1)
REVALIDATION_FILE=$(ls "$PROJECT_DIR"/REVALIDATION_*.md 2>/dev/null | head -1)
CONFIG_FILE=$(ls "$PROJECT_DIR"/CONFIG_*.md 2>/dev/null | head -1)

# Track what needs syncing
PATTERNS_DIFF=""
REVIEWS_DIFF=""
REVALIDATION_DIFF=""
CONFIG_DIFF=""

echo ""
echo "--- PATTERNS ---"
if [ -n "$PATTERNS_FILE" ]; then
    PATTERNS_DIFF=$(diff "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" "$PATTERNS_FILE" 2>/dev/null || true)
    if [ -z "$PATTERNS_DIFF" ]; then
        echo "✅ In sync: $(basename $PATTERNS_FILE)"
    else
        DIFF_LINES=$(echo "$PATTERNS_DIFF" | wc -l)
        echo "⚠️  Diverged: $(basename $PATTERNS_FILE) ($DIFF_LINES lines differ)"
        if [ "$MODE" = "--diff" ] || [ "$MODE" = "--interactive" ]; then
            echo "$PATTERNS_DIFF" | head -30
            [ $(echo "$PATTERNS_DIFF" | wc -l) -gt 30 ] && echo "... (truncated)"
        fi
    fi
else
    echo "⏭️  No PATTERNS file found"
fi

echo ""
echo "--- REVIEWS ---"
if [ -n "$REVIEWS_FILE" ]; then
    REVIEWS_DIFF=$(diff "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" "$REVIEWS_FILE" 2>/dev/null || true)
    if [ -z "$REVIEWS_DIFF" ]; then
        echo "✅ In sync: $(basename $REVIEWS_FILE)"
    else
        DIFF_LINES=$(echo "$REVIEWS_DIFF" | wc -l)
        echo "⚠️  Diverged: $(basename $REVIEWS_FILE) ($DIFF_LINES lines differ)"
        if [ "$MODE" = "--diff" ] || [ "$MODE" = "--interactive" ]; then
            echo "$REVIEWS_DIFF" | head -30
            [ $(echo "$REVIEWS_DIFF" | wc -l) -gt 30 ] && echo "... (truncated)"
        fi
    fi
else
    echo "⏭️  No REVIEWS file found"
fi

echo ""
echo "--- REVALIDATION ---"
if [ -n "$REVALIDATION_FILE" ]; then
    REVALIDATION_DIFF=$(diff "$GLOBAL_FGT/templates/REVALIDATION_TEMPLATE.md" "$REVALIDATION_FILE" 2>/dev/null || true)
    if [ -z "$REVALIDATION_DIFF" ]; then
        echo "✅ In sync: $(basename $REVALIDATION_FILE)"
    else
        DIFF_LINES=$(echo "$REVALIDATION_DIFF" | wc -l)
        echo "⚠️  Diverged: $(basename $REVALIDATION_FILE) ($DIFF_LINES lines differ)"
        if [ "$MODE" = "--diff" ] || [ "$MODE" = "--interactive" ]; then
            echo "$REVALIDATION_DIFF" | head -30
            [ $(echo "$REVALIDATION_DIFF" | wc -l) -gt 30 ] && echo "... (truncated)"
        fi
    fi
else
    echo "⏭️  No REVALIDATION file found"
fi

echo ""
echo "--- CONFIG ---"
if [ -n "$CONFIG_FILE" ]; then
    CONFIG_DIFF=$(diff "$GLOBAL_FGT/templates/CONFIG_TEMPLATE.md" "$CONFIG_FILE" 2>/dev/null || true)
    if [ -z "$CONFIG_DIFF" ]; then
        echo "✅ In sync: $(basename $CONFIG_FILE)"
    else
        DIFF_LINES=$(echo "$CONFIG_DIFF" | wc -l)
        echo "⚠️  Diverged: $(basename $CONFIG_FILE) ($DIFF_LINES lines differ)"
        if [ "$MODE" = "--diff" ] || [ "$MODE" = "--interactive" ]; then
            echo "$CONFIG_DIFF" | head -30
            [ $(echo "$CONFIG_DIFF" | wc -l) -gt 30 ] && echo "... (truncated)"
        fi
    fi
else
    echo "⏭️  No CONFIG file found"
fi

# --- OCD sweep runner (global) ---
echo ""
echo "--- OCD SWEEP RUNNER ---"
OCD_SRC="$GLOBAL_FGT/scripts/ocd-sweep.sh"
OCD_DST="$HOME/.claude/scripts/ocd-sweep.sh"
if [ -f "$OCD_SRC" ]; then
    if [ -f "$OCD_DST" ]; then
        OCD_DIFF=$(diff "$OCD_SRC" "$OCD_DST" 2>/dev/null || true)
        if [ -z "$OCD_DIFF" ]; then
            echo "In sync: ocd-sweep.sh"
        else
            echo "Diverged: ocd-sweep.sh"
            if [ "$MODE" = "--apply" ]; then
                cp "$OCD_SRC" "$OCD_DST"
                chmod +x "$OCD_DST"
                echo "Synced: ocd-sweep.sh -> $OCD_DST"
            fi
        fi
    else
        echo "Missing: $OCD_DST"
        if [ "$MODE" = "--apply" ]; then
            mkdir -p "$(dirname "$OCD_DST")"
            cp "$OCD_SRC" "$OCD_DST"
            chmod +x "$OCD_DST"
            echo "Installed: ocd-sweep.sh -> $OCD_DST"
        fi
    fi
else
    echo "No ocd-sweep.sh in fgt-config (expected at $OCD_SRC)"
fi

# Handle modes
if [ "$MODE" = "--diff" ]; then
    exit 0
fi

if [ "$MODE" = "--apply" ]; then
    echo ""
    echo "Applying sync..."
    [ -n "$PATTERNS_FILE" ] && [ -n "$PATTERNS_DIFF" ] && cp "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" "$PATTERNS_FILE" && echo "✅ Synced: $(basename $PATTERNS_FILE)"
    [ -n "$REVIEWS_FILE" ] && [ -n "$REVIEWS_DIFF" ] && cp "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" "$REVIEWS_FILE" && echo "✅ Synced: $(basename $REVIEWS_FILE)"
    [ -n "$REVALIDATION_FILE" ] && [ -n "$REVALIDATION_DIFF" ] && cp "$GLOBAL_FGT/templates/REVALIDATION_TEMPLATE.md" "$REVALIDATION_FILE" && echo "✅ Synced: $(basename $REVALIDATION_FILE)"
    [ -n "$CONFIG_FILE" ] && [ -n "$CONFIG_DIFF" ] && cp "$GLOBAL_FGT/templates/CONFIG_TEMPLATE.md" "$CONFIG_FILE" && echo "✅ Synced: $(basename $CONFIG_FILE)"
    exit 0
fi

# Interactive mode
if [ -z "$PATTERNS_DIFF" ] && [ -z "$REVIEWS_DIFF" ] && [ -z "$REVALIDATION_DIFF" ] && [ -z "$CONFIG_DIFF" ]; then
    echo ""
    echo "✅ Everything in sync. Nothing to do."
    exit 0
fi

echo ""
echo "Options:"
echo "  [a] Apply all changes (overwrite project files with global)"
echo "  [p] Sync PATTERNS only"
echo "  [r] Sync REVIEWS only"
echo "  [v] Sync REVALIDATION only"
echo "  [c] Sync CONFIG only"
echo "  [d] View full diff in editor"
echo "  [s] Skip (no changes)"
echo ""
read -p "Choice: " CHOICE

case $CHOICE in
    a|A)
        [ -n "$PATTERNS_FILE" ] && [ -n "$PATTERNS_DIFF" ] && cp "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" "$PATTERNS_FILE" && echo "✅ Synced: $(basename $PATTERNS_FILE)"
        [ -n "$REVIEWS_FILE" ] && [ -n "$REVIEWS_DIFF" ] && cp "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" "$REVIEWS_FILE" && echo "✅ Synced: $(basename $REVIEWS_FILE)"
        [ -n "$REVALIDATION_FILE" ] && [ -n "$REVALIDATION_DIFF" ] && cp "$GLOBAL_FGT/templates/REVALIDATION_TEMPLATE.md" "$REVALIDATION_FILE" && echo "✅ Synced: $(basename $REVALIDATION_FILE)"
        [ -n "$CONFIG_FILE" ] && [ -n "$CONFIG_DIFF" ] && cp "$GLOBAL_FGT/templates/CONFIG_TEMPLATE.md" "$CONFIG_FILE" && echo "✅ Synced: $(basename $CONFIG_FILE)"
        ;;
    p|P)
        [ -n "$PATTERNS_FILE" ] && cp "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" "$PATTERNS_FILE" && echo "✅ Synced: $(basename $PATTERNS_FILE)"
        ;;
    r|R)
        [ -n "$REVIEWS_FILE" ] && cp "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" "$REVIEWS_FILE" && echo "✅ Synced: $(basename $REVIEWS_FILE)"
        ;;
    v|V)
        [ -n "$REVALIDATION_FILE" ] && cp "$GLOBAL_FGT/templates/REVALIDATION_TEMPLATE.md" "$REVALIDATION_FILE" && echo "✅ Synced: $(basename $REVALIDATION_FILE)"
        ;;
    c|C)
        [ -n "$CONFIG_FILE" ] && cp "$GLOBAL_FGT/templates/CONFIG_TEMPLATE.md" "$CONFIG_FILE" && echo "✅ Synced: $(basename $CONFIG_FILE)"
        ;;
    d|D)
        echo "Opening diffs..."
        [ -n "$PATTERNS_FILE" ] && [ -n "$PATTERNS_DIFF" ] && ${EDITOR:-nano} -d "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" "$PATTERNS_FILE" 2>/dev/null || diff "$GLOBAL_FGT/templates/PATTERNS_TEMPLATE.md" "$PATTERNS_FILE" | less
        [ -n "$REVIEWS_FILE" ] && [ -n "$REVIEWS_DIFF" ] && ${EDITOR:-nano} -d "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" "$REVIEWS_FILE" 2>/dev/null || diff "$GLOBAL_FGT/templates/REVIEWS_TEMPLATE.md" "$REVIEWS_FILE" | less
        ;;
    *)
        echo "Skipped."
        ;;
esac
