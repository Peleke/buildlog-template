# MCP Integration

buildlog ships an MCP server for Claude Code integration.

## Setup

```bash
pip install buildlog[mcp]
```

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "buildlog": {
      "command": "buildlog-mcp"
    }
  }
}
```

## Available tools

| Tool | Purpose |
|------|---------|
| `buildlog_status` | View rules by category and confidence |
| `buildlog_promote` | Surface rules to agent |
| `buildlog_reject` | Mark false positives |
| `buildlog_diff` | Rules pending review |
| `buildlog_learn_from_review` | Extract rules from code review |
| `buildlog_log_reward` | Record reward signal (updates bandit) |
| `buildlog_experiment_start` | Begin tracked session (bandit selects rules) |
| `buildlog_experiment_end` | End tracked session, calculate metrics |
| `buildlog_experiment_metrics` | Per-session or aggregate experiment metrics |
| `buildlog_log_mistake` | Record mistake (negative feedback to bandit) |
| `buildlog_experiment_report` | Full experiment report |
| `buildlog_bandit_status` | View Thompson Sampling bandit state |
| `buildlog_gauntlet_issues` | Report gauntlet findings, get next action |
| `buildlog_gauntlet_accept_risk` | Accept remaining issues, optionally create GH issues |
