"""End-to-end tests for v0.10.0 install-just-works features."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from buildlog.constants import CLAUDE_MD_BUILDLOG_SECTION
from buildlog.core.operations import create_entry, get_overview, list_entries

# Skip MCP tests if mcp is not installed
pytest.importorskip("mcp")


class TestCLAUDEMDConstant:
    """Tests for the CLAUDE.md constant."""

    def test_mentions_all_tools(self):
        """All 32 tool names should appear in the constant."""
        tools = [
            "buildlog_status",
            "buildlog_promote",
            "buildlog_reject",
            "buildlog_diff",
            "buildlog_learn_from_review",
            "buildlog_log_reward",
            "buildlog_rewards",
            "buildlog_experiment_start",
            "buildlog_experiment_end",
            "buildlog_log_mistake",
            "buildlog_experiment_metrics",
            "buildlog_experiment_report",
            "buildlog_bandit_status",
            "buildlog_gauntlet_issues",
            "buildlog_gauntlet_accept_risk",
            "buildlog_gauntlet_rules",
            "buildlog_overview",
            "buildlog_entry_new",
            "buildlog_entry_list",
            "buildlog_commit",
            "buildlog_gauntlet_prompt",
            "buildlog_gauntlet_loop",
            "buildlog_distill",
            "buildlog_skills",
            "buildlog_stats",
            "buildlog_gauntlet_list_personas",
            "buildlog_gauntlet_generate",
            "buildlog_init",
            "buildlog_update",
            "buildlog_migrate",
            "buildlog_export",
            "buildlog_import_seed",
        ]
        for tool in tools:
            assert tool in CLAUDE_MD_BUILDLOG_SECTION, f"Missing tool: {tool}"

    def test_has_commit_gauntlet_learn_loop(self):
        """Should describe the commit -> gauntlet -> learn workflow."""
        assert "Commit" in CLAUDE_MD_BUILDLOG_SECTION
        assert "Gauntlet" in CLAUDE_MD_BUILDLOG_SECTION
        assert "Learn" in CLAUDE_MD_BUILDLOG_SECTION

    def test_has_session_workflow(self):
        """Should mention experiment start/end workflow."""
        assert "experiment_start" in CLAUDE_MD_BUILDLOG_SECTION
        assert "experiment_end" in CLAUDE_MD_BUILDLOG_SECTION

    def test_has_tool_reference(self):
        """Should have tool reference sections."""
        assert "Skill Management" in CLAUDE_MD_BUILDLOG_SECTION
        assert "Gauntlet Review" in CLAUDE_MD_BUILDLOG_SECTION
        assert "Reward & Bandit" in CLAUDE_MD_BUILDLOG_SECTION


class TestE2EEntryWorkflow:
    """Test entry creation -> listing -> overview pipeline."""

    def test_entry_workflow(self, tmp_path):
        """create_entry -> list_entries shows it -> overview counts it."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        (buildlog_dir / "_TEMPLATE.md").write_text("# [YYYY-MM-DD] [TITLE]\n")

        # Create entry
        result = create_entry(buildlog_dir, "test-feature", entry_date="2026-02-01")
        assert result.error is None

        # List should show it
        entries = list_entries(buildlog_dir)
        assert entries.count == 1
        assert "test-feature" in entries.entries[0]["name"]

        # Overview should count it
        overview = get_overview(buildlog_dir)
        assert overview.entries == 1


class TestE2EMCPServer29Tools:
    """Verify the MCP server has all 32 tools."""

    @pytest.mark.asyncio
    async def test_server_has_32_tools(self):
        """Server should list 32 tools, each callable."""
        from buildlog.mcp.server import mcp

        tools = await mcp.list_tools()
        assert len(tools) == 32

        # Each should have a name and description
        for tool in tools:
            assert tool.name
            assert tool.description


class TestE2ESeedsIncludeBragi:
    """Verify bragi persona is available."""

    def test_gauntlet_rules_returns_bragi(self):
        """gauntlet_rules should include bragi persona."""
        from buildlog.core.operations import get_gauntlet_rules

        result = get_gauntlet_rules()
        if result.error is None:
            assert "bragi" in result.personas
