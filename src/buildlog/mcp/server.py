"""Buildlog MCP server for Claude Code integration."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from buildlog.mcp.tools import (
    buildlog_bandit_status,
    buildlog_commit,
    buildlog_diff,
    buildlog_distill,
    buildlog_entry_list,
    buildlog_entry_new,
    buildlog_experiment_end,
    buildlog_experiment_metrics,
    buildlog_experiment_report,
    buildlog_experiment_start,
    buildlog_export,
    buildlog_gauntlet_accept_risk,
    buildlog_gauntlet_generate,
    buildlog_gauntlet_issues,
    buildlog_gauntlet_list_personas,
    buildlog_gauntlet_loop,
    buildlog_gauntlet_prompt,
    buildlog_gauntlet_rule_lookup,
    buildlog_gauntlet_rules,
    buildlog_import_seed,
    buildlog_ingest_seeds,
    buildlog_init,
    buildlog_learn_from_review,
    buildlog_log_mistake,
    buildlog_log_reward,
    buildlog_migrate,
    buildlog_overview,
    buildlog_posterior_history,
    buildlog_promote,
    buildlog_reject,
    buildlog_rewards,
    buildlog_skills,
    buildlog_stats,
    buildlog_status,
    buildlog_update,
    buildlog_verify,
)

mcp = FastMCP("buildlog")

# Register tools
mcp.tool()(buildlog_status)
mcp.tool()(buildlog_promote)
mcp.tool()(buildlog_reject)
mcp.tool()(buildlog_diff)
mcp.tool()(buildlog_learn_from_review)
mcp.tool()(buildlog_log_reward)
mcp.tool()(buildlog_rewards)

# Session tracking tools (experiment infrastructure)
mcp.tool()(buildlog_experiment_start)
mcp.tool()(buildlog_experiment_end)
mcp.tool()(buildlog_log_mistake)
mcp.tool()(buildlog_experiment_metrics)
mcp.tool()(buildlog_experiment_report)

# Gauntlet loop tools
mcp.tool()(buildlog_gauntlet_issues)
mcp.tool()(buildlog_gauntlet_accept_risk)

# Bandit tools
mcp.tool()(buildlog_bandit_status)
mcp.tool()(buildlog_posterior_history)

# Entry & overview tools
mcp.tool()(buildlog_gauntlet_rules)
mcp.tool()(buildlog_overview)
mcp.tool()(buildlog_entry_new)
mcp.tool()(buildlog_entry_list)

# P0: Gauntlet loop completion
mcp.tool()(buildlog_commit)
mcp.tool()(buildlog_gauntlet_prompt)
mcp.tool()(buildlog_gauntlet_loop)
mcp.tool()(buildlog_gauntlet_rule_lookup)

# P1: Learning pipeline
mcp.tool()(buildlog_distill)
mcp.tool()(buildlog_skills)
mcp.tool()(buildlog_stats)
mcp.tool()(buildlog_gauntlet_list_personas)

# Storage tools
mcp.tool()(buildlog_migrate)
mcp.tool()(buildlog_export)

# Seed import / interop
mcp.tool()(buildlog_import_seed)
mcp.tool()(buildlog_ingest_seeds)

# Workflow verification
mcp.tool()(buildlog_verify)

# P2: Nice-to-have
mcp.tool()(buildlog_gauntlet_generate)
mcp.tool()(buildlog_init)
mcp.tool()(buildlog_update)


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
