#!/usr/bin/env bash
# enforce-buildlog-commit.sh - Claude Code PreToolUse hook
#
# Enforces TWO things:
#   1. Blocks bare `git commit` → must use buildlog_commit()
#   2. Blocks `gh pr create` without gauntlet-cleared marker
#
# Exceptions:
#   - BUILDLOG_COMMIT=1 prefix (set by buildlog_commit() internally)
#   - git commit --amend (fixup commits are fine)
#   - BUILDLOG_ENFORCE=0 (opt-out of all enforcement)

set -euo pipefail

# Global opt-out
if [ "${BUILDLOG_ENFORCE:-1}" = "0" ]; then
  exit 0
fi

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")

if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

# --- Enforcement 1: Block bare git commit ---
if printf '%s' "$COMMAND" | grep -qE '(^|&&|\||\;)\s*git\s+commit\b'; then
  if printf '%s' "$COMMAND" | grep -qE 'BUILDLOG_COMMIT=1'; then
    exit 0
  fi
  if printf '%s' "$COMMAND" | grep -qE 'git\s+commit\s+.*--amend'; then
    exit 0
  fi
  cat <<'DENY_JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Direct `git commit` is blocked. Use buildlog_commit(message=\"...\") instead -- it commits AND logs the entry. If you need to amend, use `git commit --amend`."
  }
}
DENY_JSON
  exit 0
fi

# --- Enforcement 2: Block gh pr create without gauntlet ---
if printf '%s' "$COMMAND" | grep -qE '(^|&&|\||\;)\s*gh\s+pr\s+create\b'; then
  BUILDLOG_DIR="${CLAUDE_PROJECT_DIR:-.}/buildlog"
  MARKER="$BUILDLOG_DIR/.buildlog/gauntlet_cleared"
  if [ ! -f "$MARKER" ]; then
    cat <<'DENY_JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "PR creation blocked. Run the gauntlet first: buildlog_gauntlet_loop(target=\"src/\"). The gauntlet must pass clean (or accept risk) before creating a PR."
  }
}
DENY_JSON
    exit 0
  fi
fi

exit 0
