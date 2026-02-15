#!/usr/bin/env bash
# session-start.sh - Claude Code SessionStart hook
# Auto-starts a buildlog experiment session when Claude Code starts.

set -euo pipefail

BUILDLOG_DIR="${CLAUDE_PROJECT_DIR:-.}/buildlog"

if [ ! -d "$BUILDLOG_DIR" ]; then
  exit 0
fi

buildlog experiment end 2>/dev/null || true
buildlog experiment start 2>/dev/null || true
