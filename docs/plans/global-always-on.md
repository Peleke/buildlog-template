# Global Always-On Mode

> **Issue:** #79
> **Status:** Planning
> **Target:** v0.11.0 or v0.12.0

## Current Workflow (v0.10.0)

```bash
# Install globally
pipx install buildlog          # or: uv tool install buildlog

# Per-project setup (required)
cd my-project
buildlog init --defaults       # creates buildlog/, .claude/settings.json, updates CLAUDE.md
```

## Proposed Workflow

```bash
# One-time global setup
pipx install buildlog
buildlog init-mcp --global     # registers in ~/.claude/settings.json

# Use anywhere (no per-project init required)
cd any-project
# Claude Code already has access to all 29 buildlog tools
```

## What Changes

### 1. Global MCP Registration

```python
# cli.py
@main.command("init-mcp")
@click.option("--global", "global_", is_flag=True, help="Register globally in ~/.claude/settings.json")
def init_mcp(global_: bool):
    if global_:
        settings_path = Path.home() / ".claude" / "settings.json"
    else:
        settings_path = Path(".claude") / "settings.json"
    # ... rest of logic unchanged
```

### 2. Graceful Fallbacks

Commands that currently require `buildlog/` should handle missing directories:

```python
# Before
if not buildlog_dir.exists():
    click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
    raise SystemExit(1)

# After
if not buildlog_dir.exists():
    # Return empty/default state instead of erroring
    return EmptyResult(initialized=False, message="Run 'buildlog init' to enable full features")
```

### 3. Global State Directory

```
~/.buildlog/
├── seeds/              # Custom personas (merged with package bundled)
├── rewards.jsonl       # Optional: cross-project reward tracking
└── config.yaml         # Global preferences
```

## Migration Path

1. v0.10.0: Current per-project model (ship as-is)
2. v0.11.0: Add `--global` flag, graceful fallbacks
3. v0.12.0: Global state directory, cross-project features

## Implementation Checklist

- [ ] Add `--global` flag to `init-mcp`
- [ ] Update `_init_mcp()` to accept path parameter
- [ ] Add graceful fallbacks to: `overview`, `skills`, `status`, `stats`
- [ ] Document "always-on" workflow in installation guide
- [ ] Test with fresh system (no local buildlog/)
