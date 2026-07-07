# Claude Code Hooks — Session Enforcement

Claude Code CLI supports lifecycle hooks that run shell commands at specific
events. These hooks enforce FGT session protocol automatically, preventing
the most common failure mode: context compaction silently dropping decisions,
bug fixes, and domain knowledge.

## Hook Events

| Event | When it fires | Purpose |
|-------|--------------|---------|
| **SessionStart** | New conversation begins | Load context, surface pre-compaction snapshots from prior sessions |
| **PreCompact** | Context window nearly full | Auto-snapshot git state + test results before compaction |
| **Stop** | Before each assistant response | Block response if N+ commits made without memory/FGT updates |
| **SessionEnd** | Conversation ends | Verification prompt — were all learnings persisted? |

## Hook Patterns

### SessionStart — Context Loading

Records session start time (used by Stop hook) and surfaces any staging
files left by a prior PreCompact snapshot.

```bash
#!/bin/bash
# {{PROJECT_SCRIPTS}}/fgt_session_start.sh
set -euo pipefail

MEMORY_DIR="{{MEMORY_DIR}}"
SESSION_MARKER="$MEMORY_DIR/.session_start"
STAGING_FILE="$MEMORY_DIR/session_staging.md"

# Record session start time
date -Iseconds > "$SESSION_MARKER"

# Surface pre-compaction snapshot if one exists
if [ -f "$STAGING_FILE" ]; then
    echo "RECOVERED CONTEXT from pre-compaction snapshot:"
    echo ""
    cat "$STAGING_FILE"
    rm -f "$STAGING_FILE"
fi

# Remind to load memory
echo "SESSION START — FGT Protocol Active"
echo "Read memory files before acting."
```

### PreCompact — Auto-Snapshot

This is the most critical hook. PreCompact cannot block (platform limitation),
so it takes a two-pronged approach:

1. **Active**: Writes session state to disk automatically (survives compaction)
2. **Reminder**: Outputs text telling the assistant to persist properly

```bash
#!/bin/bash
# {{PROJECT_SCRIPTS}}/fgt_session_persist.sh (PreCompact handler)
set -euo pipefail

MEMORY_DIR="{{MEMORY_DIR}}"
STAGING_FILE="$MEMORY_DIR/session_staging.md"
SESSION_MARKER="$MEMORY_DIR/.session_start"
PROJECT_DIR="{{PROJECT_DIR}}"

# --- ACTIVE: Snapshot session state to disk ---
{
    echo "# Pre-Compaction Staging (auto-captured)"
    echo "Captured at: $(date -Iseconds)"
    echo ""
    echo "## Git Changes This Session"
    if [ -f "$SESSION_MARKER" ]; then
        SESSION_START=$(cat "$SESSION_MARKER")
        echo "### Commits since session start:"
        git -C "$PROJECT_DIR" log --oneline --since="$SESSION_START" 2>/dev/null || echo "(none)"
    fi
    echo ""
    echo "## Test State"
    RESULT=$(cd "$PROJECT_DIR" && {{TEST_COMMAND}} 2>&1 | tail -1) || true
    echo "$RESULT"
} > "$STAGING_FILE" 2>/dev/null || true

# --- REMINDER ---
echo "CONTEXT COMPACTION IMMINENT — persist learnings to memory files."
```

### Stop — Enforcement Gate + OCD Sweep

Two enforcement mechanisms fire at Stop:

**1. FGT memory enforcement** — blocks if commits were made without
updating memory files. Makes session persistence non-optional.

**2. OCD operational sweep** — checks system health (git state,
processes, data, BACKLOG). Runs via the global Stop hook installed by
`install-ocd.sh`. The global hook calls `~/.claude/scripts/ocd-sweep.sh`
which auto-discovers `<project>/scripts/sweep.sh` for project-specific
checks. FAIL findings block the agent; WARN findings are advisory.

The global Stop hook is in `~/.claude/settings.json`, not in the
per-project `.claude/settings.json`. The per-project Stop hook below
handles FGT memory enforcement only — OCD is global so it works
across all projects without per-project wiring.

Blocks the assistant from responding (exit code 2) if commits were made
without updating memory files. This is the enforcement mechanism that
makes session persistence non-optional.

**Trigger conditions** (configure per project):
- N+ commits made this session without memory file updates
- Any commit touching domain-critical directories without memory updates
- Test files modified without bug pattern documentation updates

```bash
#!/bin/bash
# {{PROJECT_SCRIPTS}}/fgt_stop_check.sh
set -euo pipefail

MEMORY_DIR="{{MEMORY_DIR}}"
SESSION_MARKER="$MEMORY_DIR/.session_start"
PROJECT_DIR="{{PROJECT_DIR}}"

# Skip if no session marker
[ -f "$SESSION_MARKER" ] || exit 0

SESSION_START=$(cat "$SESSION_MARKER")
COMMIT_COUNT=$(git -C "$PROJECT_DIR" log --oneline --since="$SESSION_START" 2>/dev/null | wc -l) || 0

# Threshold: block after N commits without memory updates
COMMIT_THRESHOLD={{COMMIT_THRESHOLD:-3}}

if [ "$COMMIT_COUNT" -lt "$COMMIT_THRESHOLD" ]; then
    exit 0
fi

# Check if any memory file was updated after session start
SESSION_EPOCH=$(date -d "$SESSION_START" +%s 2>/dev/null) || exit 0
MEMORY_UPDATED=false
for f in "$MEMORY_DIR"/*.md; do
    [ -f "$f" ] || continue
    FILE_EPOCH=$(stat -c '%Y' "$f" 2>/dev/null) || continue
    if [ "$FILE_EPOCH" -gt "$SESSION_EPOCH" ]; then
        MEMORY_UPDATED=true
        break
    fi
done

if [ "$MEMORY_UPDATED" = false ]; then
    echo "FGT ENFORCEMENT: $COMMIT_COUNT commits without memory updates." >&2
    echo "Update memory files with session learnings before continuing." >&2
    exit 2  # Exit 2 = BLOCK response and send stderr to assistant
fi

# --- ENHANCED CHECK 2: Domain-critical file changes ---
# Even 1 commit touching core logic dirs should require memory updates
CRITICAL_DIRS="{{CRITICAL_DIRS}}"  # e.g., "src/engine src/sheets src/docs"
if [ -n "$CRITICAL_DIRS" ] && [ "$MEMORY_UPDATED" = false ]; then
    for dir in $CRITICAL_DIRS; do
        if git -C "$PROJECT_DIR" diff --name-only HEAD~1 2>/dev/null | grep -q "^$dir/"; then
            echo "FGT ENFORCEMENT: domain-critical file changed ($dir) without memory update." >&2
            exit 2
        fi
    done
fi

# --- ENHANCED CHECK 3: Test files changed without bug pattern docs ---
# Enforces Bug Abstraction Protocol step 3
TEST_FILES_CHANGED=$(git -C "$PROJECT_DIR" diff --name-only HEAD~1 2>/dev/null | grep -c "^tests/" || true)
if [ "$TEST_FILES_CHANGED" -gt 0 ]; then
    BUG_PATTERNS_UPDATED=false
    for f in "{{BUG_PATTERNS_PATH}}" "$MEMORY_DIR/bug_patterns.md"; do
        [ -f "$f" ] || continue
        FILE_EPOCH=$(stat -c '%Y' "$f" 2>/dev/null) || continue
        if [ "$FILE_EPOCH" -gt "$SESSION_EPOCH" ]; then
            BUG_PATTERNS_UPDATED=true
            break
        fi
    done
    if [ "$BUG_PATTERNS_UPDATED" = false ]; then
        echo "FGT ABSTRACTION: Test files modified but bug_patterns.md NOT updated." >&2
        echo "FGT requires abstracting every bug fix to a CLASS, not just fixing the instance." >&2
        exit 2
    fi
fi

exit 0
```

### SessionEnd — Verification Prompt

Simple reminder to verify all learnings were persisted. Reuses the same
script as PreCompact with a different event flag.

```bash
#!/bin/bash
# Handled by fgt_session_persist.sh with CLAUDE_HOOK_EVENT=SessionEnd
echo "SESSION ENDING — verify all learnings were persisted."
echo "Check: Were any decisions, bug fixes, or patterns discovered"
echo "this session that haven't been written to memory files?"
```

## Example `.claude/settings.json`

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash {{PROJECT_SCRIPTS}}/fgt_session_start.sh"
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "auto",
        "hooks": [
          {
            "type": "command",
            "command": "CLAUDE_HOOK_EVENT=PreCompact bash {{PROJECT_SCRIPTS}}/fgt_session_persist.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash {{PROJECT_SCRIPTS}}/fgt_stop_check.sh"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "CLAUDE_HOOK_EVENT=SessionEnd bash {{PROJECT_SCRIPTS}}/fgt_session_persist.sh"
          }
        ]
      }
    ]
  }
}
```

## Setup

1. Copy hook scripts to your project's `scripts/` directory
2. Replace `{{placeholders}}` with project-specific paths
3. Copy `settings.json` to `.claude/settings.json` (project-level) or `~/.claude/settings.json` (global)
4. Create the memory directory structure
5. Test each hook: `bash scripts/fgt_session_start.sh`

## Key Design Decisions

- **Stop hook uses exit code 2** to block the response and send stderr as feedback.
  Exit 0 = allow, exit 1 = error (shown to user), exit 2 = block and retry.
- **PreCompact cannot block** (platform limitation). It auto-snapshots AND reminds.
  The SessionStart hook surfaces any snapshots the assistant didn't act on.
- **Commit threshold is configurable.** Start with 3; lower to 2 for projects with
  domain-critical files where every commit should trigger memory review.
- **Domain-critical directory checks** are optional but recommended. When commits
  touch core logic (engine, sheets, models), even a single commit should require
  memory updates.

## Anti-Patterns

- Do not use hooks to auto-commit or auto-push. Hooks enforce human/assistant review.
- Do not set commit threshold to 1 for all projects. Only domain-critical projects
  need that level of enforcement; for general projects, 3 is a reasonable default.
- Do not skip the SessionStart hook. Without session timestamps, the Stop hook
  cannot determine which commits belong to the current session.
