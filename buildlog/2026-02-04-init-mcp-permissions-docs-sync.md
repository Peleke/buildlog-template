# Build Journal: init-mcp Permission Prompts + Docs Sync + v0.10.5

**Date:** 2026-02-04
**Duration:** 4 hours

## What I Did

Added interactive permission prompts to the init-mcp command with a -y flag for non-interactive mode (#91). Fixed the init-mcp command to write global config to ~/.claude.json instead of the wrong location (#89). Synchronized all documentation with v0.10.x changes (#94). Removed obsolete tutorials and notebooks (#96). Shipped three releases: v0.10.3, v0.10.4, and v0.10.5.

## Commits

- `d5b09f7` fix(init-mcp): write global config to ~/.claude.json (#89)
- `fd4989b` chore: release v0.10.3 (#90)
- `a816957` feat(init-mcp): add permission prompts with -y flag (#91)
- `483350b` chore: release v0.10.4 (#92)
- `20e00ea` docs: sync documentation with v0.10.x changes (#94)
- `5d3be4e` chore: release v0.10.5 (#95)
- `0aa3e43` chore: remove tutorials and notebooks (#96)

## What Went Wrong

The init-mcp command was writing the global config to the wrong path. This meant users who ran `buildlog init-mcp --global` got a config file that Claude Code never read. The fix was straightforward but the bug had been live since v0.10.0. Should have tested the actual Claude Code config discovery path, not just verified the file was written.

## What I Learned

## Improvements

### Architectural

- Permission prompts with a -y flag follow the Unix convention: interactive by default, scriptable with a flag
- Removing obsolete content (tutorials, notebooks) reduces maintenance burden and prevents stale docs from confusing users

### Workflow

- Test CLI commands against the actual consumer path (Claude Code reading ~/.claude.json), not just the producer path (buildlog writing the file)
- Three point releases for config path fixes signals insufficient pre-release testing: one release with all fixes would have been cleaner

### Tool Usage

- ~/.claude.json is the canonical location for Claude Code's global MCP server configuration; ~/.claude/CLAUDE.md is for instructions
