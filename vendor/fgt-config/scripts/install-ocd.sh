#!/bin/bash
# install-ocd.sh — Deploy OCD (Operational Completion Discipline) globally.
#
# Idempotent. Safe to re-run after fgt-config updates.
#
# What it does:
#   1. Copies ocd-sweep.sh → ~/.claude/scripts/ocd-sweep.sh
#   2. Patches ~/.claude/settings.json to add the Stop hook (if not present)
#
# Usage:
#   cd fgt-config && bash scripts/install-ocd.sh
#   # or from anywhere:
#   bash /path/to/fgt-config/scripts/install-ocd.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
SCRIPTS_DIR="$CLAUDE_DIR/scripts"
SETTINGS="$CLAUDE_DIR/settings.json"

echo "=== OCD Install ==="

# --- Step 1: Copy sweep runner ---
mkdir -p "$SCRIPTS_DIR"
cp "$SCRIPT_DIR/ocd-sweep.sh" "$SCRIPTS_DIR/ocd-sweep.sh"
chmod +x "$SCRIPTS_DIR/ocd-sweep.sh"
echo "[+] Copied ocd-sweep.sh → $SCRIPTS_DIR/ocd-sweep.sh"

# --- Step 2: Patch settings.json with Stop hook ---
if [ ! -f "$SETTINGS" ]; then
    echo "[-] $SETTINGS not found — creating minimal settings with Stop hook"
    cat > "$SETTINGS" << 'EOF'
{
  "hooks": {
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash $HOME/.claude/scripts/ocd-sweep.sh"
          }
        ]
      }
    ]
  }
}
EOF
    echo "[+] Created $SETTINGS with Stop hook"
else
    # Check if Stop hook already exists
    if python3 -c "
import json, sys
with open('$SETTINGS') as f:
    cfg = json.load(f)
hooks = cfg.get('hooks', {})
if 'Stop' in hooks:
    # Check if our hook is already there
    for entry in hooks['Stop']:
        for h in entry.get('hooks', []):
            if 'ocd-sweep' in h.get('command', ''):
                sys.exit(0)  # Already present
sys.exit(1)
" 2>/dev/null; then
        echo "[=] Stop hook already present in $SETTINGS"
    else
        # Add the Stop hook
        python3 -c "
import json
with open('$SETTINGS') as f:
    cfg = json.load(f)
hooks = cfg.setdefault('hooks', {})
stop_hooks = hooks.setdefault('Stop', [])
stop_hooks.append({
    'matcher': '*',
    'hooks': [{
        'type': 'command',
        'command': 'bash \$HOME/.claude/scripts/ocd-sweep.sh'
    }]
})
with open('$SETTINGS', 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
"
        echo "[+] Added Stop hook to $SETTINGS"
    fi
fi

# --- Step 3: Symlink pstatus into PATH ---
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"
PSTATUS_SRC="$SCRIPT_DIR/pstatus.sh"
PSTATUS_DST="$LOCAL_BIN/pstatus"
if [ -f "$PSTATUS_SRC" ]; then
    ln -sf "$PSTATUS_SRC" "$PSTATUS_DST"
    echo "[+] Linked pstatus → $PSTATUS_DST"
else
    echo "[-] pstatus.sh not found at $PSTATUS_SRC — skipping"
fi

echo ""
echo "=== OCD Install Complete ==="
echo "The Stop hook will run ocd-sweep.sh at every session end."
echo "Project-specific checks: create <project>/scripts/sweep.sh"
echo "(see fgt-config/templates/SWEEP_TEMPLATE.sh for the format)"
echo ""
echo "Status HUD: run 'pstatus' for all projects, 'pstatus <name>' for detail."
