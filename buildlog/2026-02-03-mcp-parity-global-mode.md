# Build Journal: Full MCP/CLI Parity + Global Always-On Mode + v0.10.x Releases

**Date:** 2026-02-03
**Duration:** 6 hours

## What I Did

Shipped full MCP/CLI parity with 29 tools (#75), global always-on mode that writes usage instructions to ~/.claude/CLAUDE.md (#83), and three point releases (v0.10.0, v0.10.1, v0.10.2). Also fixed the npm CI environment for OIDC trusted publishing (#85).

## Commits

- `680421f` feat: full MCP/CLI parity — 29 tools (#75)
- `98dfa1a` chore: merge global always-on mode (#81)
- `a30f435` chore: release v0.10.0 (#82)
- `03fc768` feat: --global writes usage instructions to ~/.claude/CLAUDE.md (#83)
- `6d57338` chore: release v0.10.1
- `4078d7c` fix(ci): add npm environment for OIDC trusted publishing
- `20e51c8` Merge pull request #85 from Peleke/fix/npm-environment
- `abf651a` chore: release v0.10.2
- `98fdddc` Merge pull request #86 from Peleke/chore/release-v0.10.2

## What Went Wrong

The npm OIDC trusted publishing failed because the GitHub Actions environment was not configured for npm. This is a CI-only issue that does not affect users, but it blocked the release pipeline. The fix was adding the npm environment to the workflow.

## What I Learned

## Improvements

### Architectural

- MCP/CLI parity means every operation is available through both interfaces: this eliminates the "I can do it in the CLI but not via the agent" class of problems
- Global always-on mode (writing to ~/.claude/CLAUDE.md) ensures buildlog is available across all projects without per-project configuration

### Workflow

- OIDC trusted publishing eliminates the need to store npm tokens as secrets, but requires explicit environment configuration in GitHub Actions
- Three point releases in a day signals the feature was not properly scoped: should have shipped 29 tools + global mode as a single v0.10.0

### Domain Knowledge

- Writing agent instructions to ~/.claude/CLAUDE.md is the canonical way to make MCP tools auto-discoverable across all Claude Code sessions
