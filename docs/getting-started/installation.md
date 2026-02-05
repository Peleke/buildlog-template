# Installation

## Requirements

- Python 3.10+
- A virtual environment (PEP 668 blocks system-level installs)

## Install

```bash
# Recommended: install as a global tool
pipx install buildlog
# or: uv tool install buildlog

# Alternative: install in a virtual environment
uv pip install buildlog
# or: pip install buildlog
```

## Optional extras

| Extra | What it adds | Install |
|-------|-------------|---------|
| `mcp` | MCP server (included by default since v0.10.0) | `pip install buildlog[mcp]` |
| `embeddings` | Local sentence-transformers for semantic dedup | `pip install buildlog[embeddings]` |
| `openai` | OpenAI embeddings for semantic dedup | `pip install buildlog[openai]` |
| `engine` | Documents the engine namespace (no extra deps) | `pip install buildlog[engine]` |
| `all` | Everything above | `pip install buildlog[all]` |
| `dev` | Development tools (pytest, black, mypy, etc.) | `pip install buildlog[dev]` |

## Global Always-On Mode (recommended)

Register buildlog globally so it's available in every project:

```bash
buildlog init-mcp --global -y
```

This command:

1. **Registers the MCP server** in `~/.claude.json` (Claude Code's global config)
2. **Creates `~/.claude/CLAUDE.md`** with usage instructions so Claude proactively uses buildlog tools
3. **Works immediately** in any repo, even without a local `buildlog/` directory

### Verify installation

```bash
claude mcp list              # should show: buildlog - ✓ Connected
buildlog mcp-test            # lists all 32 tools
buildlog overview            # works anywhere (shows "not initialized" if no buildlog/)
```

### Flags

| Flag | Effect |
|------|--------|
| `--global` | Write to global config (`~/.claude.json`) instead of local (`.claude/settings.json`) |
| `-y`, `--yes` | Skip confirmation prompts (non-interactive mode) |

Without `-y`, the command prompts before modifying each file. Use `-y` for scripts, CI, or when you know what you're doing.

## Per-Project Setup

For explicit per-project control:

```bash
buildlog init              # Interactive setup
buildlog init --defaults   # Non-interactive (CI-friendly)
```

This creates the `buildlog/` directory with templates and registers MCP for this project only.

New projects automatically use the **global SQLite storage backend** at `~/.buildlog/buildlog.db`. There is no per-project database setup required. If you have an existing project with legacy JSON/JSONL files in `.buildlog/`, run `buildlog migrate` to move that data into the global database. See the [Storage Architecture](../guides/storage-architecture.md) guide for details.

### Flags for `init`

| Flag | Effect |
|------|--------|
| `--defaults` | Skip prompts, use defaults (also skips MCP confirmation) |
| `--no-mcp` | Don't register MCP server |
| `--no-claude-md` | Don't update CLAUDE.md |

## Graceful Fallbacks

Commands work even without a `buildlog/` directory:

```bash
buildlog overview --json
# {"initialized": false, "entries": 0, "skills": {"total": 0}, ...}
```

This enables the "always-on" workflow: MCP tools are available globally, and they return useful empty state when no project-level buildlog exists.
