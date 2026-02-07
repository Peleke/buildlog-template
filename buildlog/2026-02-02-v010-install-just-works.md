# 2026-02-02 — buildlog v0.10.0 "Install and Just Works"

## The Goal

`pip install buildlog` → `buildlog init` → Claude Code automatically maintains entries, runs gauntlet reviews after commits, loads/uses rules, tracks experiments. Zero manual config.

## Implementation Plan

See plan transcript for full details. Key phases:
1. Foundation: .buildlog/ template dir, bundle bragi, mcp as default dep
2. Core Operations: get_gauntlet_rules, get_overview, create_entry, list_entries
3. MCP Layer: 4 new tools, register, update docstrings
4. Init + CLAUDE.md: constants.py, _init_mcp, init-mcp, mcp-test commands
5. Docs: README, MCP guide, version bump
6. Tests: ~51 new tests
