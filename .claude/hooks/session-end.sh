#!/usr/bin/env bash
# session-end.sh - Claude Code SessionEnd hook
# Auto-ends the buildlog experiment session when Claude Code session ends.

set -euo pipefail

BUILDLOG_DIR="${CLAUDE_PROJECT_DIR:-.}/buildlog"

if [ ! -d "$BUILDLOG_DIR" ]; then
  exit 0
fi

buildlog experiment end 2>/dev/null || true
