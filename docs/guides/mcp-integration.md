# MCP Integration

buildlog ships an MCP server for Claude Code integration. MCP is now a default
dependency — no extras needed.

## Global Setup (recommended)

Register buildlog globally so it works in every project:

```bash
pipx install buildlog              # or: uv tool install buildlog
buildlog init-mcp --global -y      # register globally
```

This writes to:

- `~/.claude.json` — MCP server registration (Claude Code reads this)
- `~/.claude/CLAUDE.md` — Usage instructions so Claude knows how to use buildlog

### Verify Installation

```bash
claude mcp list           # should show: buildlog - ✓ Connected
buildlog mcp-test         # lists all 32 tools, exits 0 if correct
buildlog overview         # works anywhere (shows project state or "not initialized")
```

## Per-Project Setup

For project-specific MCP registration:

```bash
pip install buildlog
buildlog init --defaults    # scaffolds buildlog/ and registers MCP locally
```

Or just register MCP without scaffolding:

```bash
buildlog init-mcp           # register MCP in .claude/settings.json
buildlog init-mcp -y        # skip confirmation prompts
```

## Confirmation Prompts

By default, `init-mcp` prompts before modifying files:

```
Create/modify ~/.claude.json? [y/N]:
Create ~/.claude/CLAUDE.md with buildlog instructions? [y/N]:
```

Use `-y` or `--yes` to skip prompts (for scripts, CI, or automation).

## File Locations

| Mode | MCP Config | CLAUDE.md |
|------|-----------|-----------|
| Global (`--global`) | `~/.claude.json` | `~/.claude/CLAUDE.md` |
| Local (default) | `.claude/settings.json` | Not created |

Claude Code reads `~/.claude.json` for global MCP servers. The local `.claude/settings.json` is project-specific.

## Available tools

| Tool | Purpose |
|------|---------|
| `buildlog_status` | Get current skills extracted from buildlog entries |
| `buildlog_promote` | Promote selected skills to your agent's rule files |
| `buildlog_reject` | Mark skills as rejected so they won't be suggested again |
| `buildlog_diff` | Show skills pending promotion or rejection |
| `buildlog_learn_from_review` | Extract and persist learnings from code review feedback |
| `buildlog_log_reward` | Log outcome feedback for bandit learning |
| `buildlog_rewards` | Get reward events with summary statistics |
| `buildlog_experiment_start` | Start a tracked session with Thompson Sampling |
| `buildlog_experiment_end` | End the current session and calculate metrics |
| `buildlog_log_mistake` | Log a mistake during the current session for RMR tracking |
| `buildlog_experiment_metrics` | Get per-session or aggregate mistake rates |
| `buildlog_experiment_report` | Generate comprehensive report |
| `buildlog_bandit_status` | Get Thompson Sampling bandit state and rule rankings |
| `buildlog_gauntlet_issues` | Process gauntlet issues and determine next action |
| `buildlog_gauntlet_accept_risk` | Accept risk for remaining issues |
| `buildlog_gauntlet_rules` | Load gauntlet reviewer rules |
| `buildlog_gauntlet_prompt` | Generate review prompt with persona rules |
| `buildlog_gauntlet_loop` | Full gauntlet loop configuration |
| `buildlog_gauntlet_list_personas` | List available reviewer personas |
| `buildlog_gauntlet_generate` | Generate gauntlet rules from source text |
| `buildlog_commit` | Git commit with auto buildlog entry update |
| `buildlog_distill` | Extract patterns from buildlog entries |
| `buildlog_skills` | Generate skill set from entries |
| `buildlog_stats` | Buildlog statistics and insights |
| `buildlog_init` | Initialize buildlog in a project |
| `buildlog_update` | Update buildlog template to latest |
| `buildlog_overview` | Get project buildlog state at a glance |
| `buildlog_entry_new` | Create a new buildlog journal entry |
| `buildlog_entry_list` | List all buildlog journal entries |
| `buildlog_migrate` | Migrate legacy JSON/JSONL files to global SQLite database |
| `buildlog_export` | Export storage data to JSONL files (6 tables + manifest + rules join) |
| `buildlog_import_seed` | Import external seed files with version-aware bandit decay |

## Always-On Workflow

After every significant commit:

1. `buildlog_gauntlet_rules()` — load reviewer persona rules
2. Review code against rules, collect issues as JSON
3. `buildlog_gauntlet_issues(issues=[...])` — categorize and get next action
4. Fix criticals/majors, re-run until clean
5. `buildlog_gauntlet_accept_risk()` for remaining minors
6. `buildlog_log_reward(outcome="accepted")` when work is approved

This is configured automatically when `buildlog init --defaults` updates your CLAUDE.md.
