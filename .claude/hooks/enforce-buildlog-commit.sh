#!/usr/bin/env bash
# enforce-buildlog-commit.sh — Claude Code PreToolUse hook
# Blocks bare `git commit` in Bash tool calls.
# Forces agents to use buildlog_commit() which commits AND logs.
#
# Exceptions:
#   - BUILDLOG_COMMIT=1 prefix (set by buildlog_commit() internally)
#   - git commit --amend (fixup commits are fine)
#   - git rebase (internally runs commit)

set -euo pipefail

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")

if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

# Check if it's a git commit command
if echo "$COMMAND" | grep -qE '(^|&&|\||\;)\s*git\s+commit\b'; then
  # Allow if BUILDLOG_COMMIT=1 is set (buildlog_commit() sets this)
  if echo "$COMMAND" | grep -qE 'BUILDLOG_COMMIT=1'; then
    exit 0
  fi
  # Allow --amend (fixup commits)
  if echo "$COMMAND" | grep -qE 'git\s+commit\s+.*--amend'; then
    exit 0
  fi
  # DENY
  cat <<'DENY_JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Direct `git commit` is blocked. Use buildlog_commit(message=\"...\") instead — it commits AND logs the entry. If you need to amend, use `git commit --amend`."
  }
}
DENY_JSON
  exit 0
fi

exit 0
