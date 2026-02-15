#!/usr/bin/env bash
# post-tool-use.sh - Claude Code PostToolUse hook
# Auto-fires reward signal after successful gh pr merge.

set -euo pipefail

BUILDLOG_DIR="${CLAUDE_PROJECT_DIR:-.}/buildlog"

if [ ! -d "$BUILDLOG_DIR" ]; then
  exit 0
fi

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")

if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

if printf '%s' "$COMMAND" | grep -qE '(^|&&|\||\;)\s*gh\s+pr\s+merge\b'; then
  buildlog reward accepted 2>/dev/null || true
  rm -f "$BUILDLOG_DIR/.buildlog/gauntlet_cleared" 2>/dev/null || true
fi

exit 0
