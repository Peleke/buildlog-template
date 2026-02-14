# Build Journal: v0.10.0 Prep — MCP Registration Fix + CI Publish Fix

**Date:** 2026-02-02
**Duration:** 2 hours

## What I Did

Post-release cleanup day. Fixed the MCP bandit_status tool that was missing from the registration list and added installation docs (#67). Then fixed the CI npm publish workflow that was failing when the version already existed on the registry (#69).

## Commits

- `d30e901` fix(mcp): register bandit_status tool, add installation docs (#67)
- `3ff7d7b` fix(ci): allow same npm version in publish workflow (#69)

## What Went Wrong

The bandit_status MCP tool was implemented but never registered in the server's tool list. This is a recurring pattern: implementing a feature but forgetting the wiring step. The CI publish failure was caused by npm erroring on duplicate versions instead of gracefully skipping.

## What I Learned

## Improvements

### Workflow

- Add a registration checklist to the MCP tool development workflow: implement, test, register, verify via list-tools
- CI publish workflows should be idempotent: use `--ignore-existing` or equivalent to handle re-runs gracefully

### Tool Usage

- Always verify new MCP tools appear in `buildlog_status()` output before merging
