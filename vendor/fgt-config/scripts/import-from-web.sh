#!/bin/bash
IMPORT_DIR=${1:-"$HOME/Downloads"}
GLOBAL_FGT_DIR="$HOME/.claude/fgt"
PROJECT=${2:-NEB75}
PROJECT_DIR="$HOME/projects/$PROJECT"
SUFFIX=${3:-VE}

echo "📥 Importing from: $IMPORT_DIR"
echo "   Project: $PROJECT (suffix: $SUFFIX)"

# Global files (generic)
[ -f "$IMPORT_DIR/FGT.md" ] && cp "$IMPORT_DIR/FGT.md" "$GLOBAL_FGT_DIR/" && echo "   ✅ FGT.md → global"
[ -f "$IMPORT_DIR/README.md" ] && cp "$IMPORT_DIR/README.md" "$GLOBAL_FGT_DIR/" && echo "   ✅ README.md → global (includes For Claude Web Projects)"

# Project-specific files
if [ -d "$PROJECT_DIR" ]; then
    # Domain files
    for f in "$IMPORT_DIR"/FGT_DOMAIN_*.md; do
        [ -f "$f" ] && cp "$f" "$PROJECT_DIR/" && echo "   ✅ $(basename $f) → $PROJECT"
    done
    
    # Suffixed files
    for f in CLAUDE_WEB PATTERNS REVIEWS; do
        [ -f "$IMPORT_DIR/${f}_${SUFFIX}.md" ] && cp "$IMPORT_DIR/${f}_${SUFFIX}.md" "$PROJECT_DIR/" && echo "   ✅ ${f}_${SUFFIX}.md → $PROJECT"
    done
    
    # Other files
    [ -f "$IMPORT_DIR/CLAUDE.md" ] && cp "$IMPORT_DIR/CLAUDE.md" "$PROJECT_DIR/" && echo "   ✅ CLAUDE.md → $PROJECT"
fi

echo -e "\n🔄 Commit changes:"
echo "   cd $GLOBAL_FGT_DIR && git add -A && git commit -m 'FGT update'"
echo "   cd $PROJECT_DIR && git add -A && git commit -m 'FGT update'"
