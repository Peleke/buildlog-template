# MCP Integration

buildlog ships an MCP server for Claude Code integration. MCP is now a default
dependency — no extras needed.

## Setup

```bash
pip install buildlog
buildlog init --defaults    # auto-registers MCP server
```

For existing projects that already ran `buildlog init`:

```bash
buildlog init-mcp           # register MCP in .claude/settings.json
```

### Verify Installation

```bash
buildlog mcp-test           # lists all 19 tools, exits 0 if correct
```

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
| `buildlog_overview` | Get project buildlog state at a glance |
| `buildlog_entry_new` | Create a new buildlog journal entry |
| `buildlog_entry_list` | List all buildlog journal entries |

## Always-On Workflow

After every significant commit:

1. `buildlog_gauntlet_rules()` — load reviewer persona rules
2. Review code against rules, collect issues as JSON
3. `buildlog_gauntlet_issues(issues=[...])` — categorize and get next action
4. Fix criticals/majors, re-run until clean
5. `buildlog_gauntlet_accept_risk()` for remaining minors
6. `buildlog_log_reward(outcome="accepted")` when work is approved

This is configured automatically when `buildlog init --defaults` updates your CLAUDE.md.
