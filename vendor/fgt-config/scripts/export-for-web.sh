#!/bin/bash
set -euo pipefail

EXPORT_DIR="$HOME/fgt-web-export"
GLOBAL_FGT_DIR="$HOME/.claude/fgt"
PROJECT=${1:-NEB75}
PROJECT_DIR="$HOME/projects/$PROJECT"
# Extract suffix from project name or use provided
SUFFIX=${2:-VE}

# Safety gate: refuse to `rm -rf` an obviously dangerous path. The default is
# "$HOME/fgt-web-export" which is safe, but this script is a tempting target
# for a future refactor that pulls EXPORT_DIR from env/argv — this guard keeps
# the rm inert if someone accidentally sets it to "/", "$HOME", or empty.
: "${EXPORT_DIR:?EXPORT_DIR must be set to a non-empty path}"
case "$EXPORT_DIR" in
    "/"|"$HOME"|"$HOME/"|"/home"|"/home/")
        echo "ERROR: refusing to rm -rf unsafe EXPORT_DIR: '$EXPORT_DIR'" >&2
        exit 1
        ;;
esac

rm -rf "$EXPORT_DIR" && mkdir -p "$EXPORT_DIR"
echo "📦 Exporting FGT files for: $PROJECT (suffix: $SUFFIX)"

# Global files (generic)
[ -f "$GLOBAL_FGT_DIR/FGT.md" ] && cp -L "$GLOBAL_FGT_DIR/FGT.md" "$EXPORT_DIR/" && echo "   ✅ FGT.md (global)"
[ -f "$GLOBAL_FGT_DIR/README.md" ] && cp -L "$GLOBAL_FGT_DIR/README.md" "$EXPORT_DIR/" && echo "   ✅ README.md (global; includes For Claude Web Projects)"

# Project-specific files with suffixes
if [ -d "$PROJECT_DIR" ]; then
    # Domain file (FGT_DOMAIN_*.md)
    for f in "$PROJECT_DIR"/FGT_DOMAIN_*.md; do
        [ -f "$f" ] && cp -L "$f" "$EXPORT_DIR/" && echo "   ✅ $(basename $f)"
    done
    
    # Project-specific files (*_${SUFFIX}.md pattern)
    for f in CLAUDE_WEB PATTERNS REVIEWS; do
        [ -f "$PROJECT_DIR/${f}_${SUFFIX}.md" ] && cp -L "$PROJECT_DIR/${f}_${SUFFIX}.md" "$EXPORT_DIR/" && echo "   ✅ ${f}_${SUFFIX}.md"
    done
    
    # Other project files
    [ -f "$PROJECT_DIR/CLAUDE.md" ] && cp -L "$PROJECT_DIR/CLAUDE.md" "$EXPORT_DIR/" && echo "   ✅ CLAUDE.md"
    [ -f "$PROJECT_DIR/FGT_LOG.md" ] && cp -L "$PROJECT_DIR/FGT_LOG.md" "$EXPORT_DIR/" && echo "   ✅ FGT_LOG.md"
fi

echo -e "\n📁 Files in: $EXPORT_DIR"
echo "🌐 Windows: \\\\wsl\$\\Ubuntu$EXPORT_DIR"
ls -la "$EXPORT_DIR"
