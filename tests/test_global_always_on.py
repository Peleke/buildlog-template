"""Exhaustive tests for global always-on mode.

Tests cover:
1. Global MCP registration (--global flag)
2. Graceful fallbacks for all commands without buildlog/
3. Path handling edge cases
4. JSON vs terminal output consistency
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from buildlog.cli import main

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def isolated_fs(runner):
    """Run test in isolated filesystem (no buildlog/ directory)."""
    with runner.isolated_filesystem():
        yield


@pytest.fixture
def mock_home(tmp_path):
    """Mock home directory for global config tests."""
    home = tmp_path / "home"
    home.mkdir()
    with patch.object(Path, "home", return_value=home):
        yield home


# =============================================================================
# 1. Global MCP Registration Tests
# =============================================================================


class TestInitMcpGlobal:
    """Tests for buildlog init-mcp --global command."""

    def test_global_flag_creates_home_claude_dir(self, runner, mock_home):
        """--global creates ~/.claude/ directory if missing."""
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert result.exit_code == 0
        assert (mock_home / ".claude").exists()
        assert (mock_home / ".claude" / "settings.json").exists()

    def test_global_flag_writes_correct_path(self, runner, mock_home):
        """--global writes to ~/.claude/settings.json, not local."""
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert result.exit_code == 0

        # Global file should exist
        global_settings = mock_home / ".claude" / "settings.json"
        assert global_settings.exists()

        # Local file should NOT exist
        local_settings = Path(".claude") / "settings.json"
        assert not local_settings.exists()

    def test_global_flag_correct_mcp_config(self, runner, mock_home):
        """--global writes correct buildlog MCP server config."""
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert result.exit_code == 0

        settings = json.loads((mock_home / ".claude" / "settings.json").read_text())
        assert "mcpServers" in settings
        assert "buildlog" in settings["mcpServers"]
        assert settings["mcpServers"]["buildlog"]["command"] == "buildlog-mcp"
        assert settings["mcpServers"]["buildlog"]["args"] == []

    def test_global_flag_preserves_existing_servers(self, runner, mock_home):
        """--global preserves existing MCP servers in config."""
        # Pre-populate with another server
        claude_dir = mock_home / ".claude"
        claude_dir.mkdir()
        existing = {
            "mcpServers": {"other-server": {"command": "other", "args": ["-x"]}}
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        result = runner.invoke(main, ["init-mcp", "--global"])
        assert result.exit_code == 0

        settings = json.loads((claude_dir / "settings.json").read_text())
        assert "other-server" in settings["mcpServers"]
        assert "buildlog" in settings["mcpServers"]

    def test_global_flag_idempotent(self, runner, mock_home):
        """Running --global twice doesn't duplicate entry."""
        runner.invoke(main, ["init-mcp", "--global"])
        result = runner.invoke(main, ["init-mcp", "--global"])

        assert result.exit_code == 0
        assert "already registered" in result.output

        settings = json.loads((mock_home / ".claude" / "settings.json").read_text())
        assert len(settings["mcpServers"]) == 1

    def test_global_flag_shows_global_path_in_output(self, runner, mock_home):
        """--global output mentions ~/.claude/settings.json."""
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert "~/.claude/settings.json" in result.output

    def test_global_flag_shows_all_projects_message(self, runner, mock_home):
        """--global output mentions it works in all projects."""
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert "all projects" in result.output.lower()

    def test_local_mode_default(self, runner, isolated_fs):
        """Without --global, writes to local .claude/settings.json."""
        result = runner.invoke(main, ["init-mcp"])
        assert result.exit_code == 0
        assert Path(".claude/settings.json").exists()

    def test_local_mode_shows_local_path(self, runner, isolated_fs):
        """Local mode output mentions .claude/settings.json."""
        result = runner.invoke(main, ["init-mcp"])
        assert ".claude/settings.json" in result.output
        assert "~/.claude" not in result.output

    def test_global_handles_malformed_existing_json(self, runner, mock_home):
        """--global handles malformed existing settings.json gracefully."""
        claude_dir = mock_home / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{ invalid json }")

        result = runner.invoke(main, ["init-mcp", "--global"])
        assert result.exit_code == 0
        assert "malformed" in result.output.lower()


# =============================================================================
# 1b. Global CLAUDE.md Tests
# =============================================================================


class TestGlobalClaudeMd:
    """Tests for ~/.claude/CLAUDE.md creation with --global flag."""

    def test_global_creates_claude_md(self, runner, mock_home):
        """--global creates ~/.claude/CLAUDE.md with instructions."""
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert result.exit_code == 0

        claude_md = mock_home / ".claude" / "CLAUDE.md"
        assert claude_md.exists()

    def test_global_claude_md_has_buildlog_section(self, runner, mock_home):
        """--global CLAUDE.md contains buildlog section."""
        runner.invoke(main, ["init-mcp", "--global"])

        claude_md = mock_home / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "## buildlog" in content

    def test_global_claude_md_has_always_on_header(self, runner, mock_home):
        """--global CLAUDE.md mentions 'Always On'."""
        runner.invoke(main, ["init-mcp", "--global"])

        claude_md = mock_home / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "Always On" in content

    def test_global_claude_md_has_tool_instructions(self, runner, mock_home):
        """--global CLAUDE.md contains key tool instructions."""
        runner.invoke(main, ["init-mcp", "--global"])

        claude_md = mock_home / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        # Check for key tools
        assert "buildlog_overview" in content
        assert "buildlog_commit" in content
        assert "buildlog_gauntlet" in content
        assert "buildlog_log_reward" in content

    def test_global_claude_md_has_core_loop(self, runner, mock_home):
        """--global CLAUDE.md contains the core loop workflow."""
        runner.invoke(main, ["init-mcp", "--global"])

        claude_md = mock_home / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert (
            "Core Loop" in content
            or "after every significant commit" in content.lower()
        )

    def test_global_claude_md_mentions_downstream(self, runner, mock_home):
        """--global CLAUDE.md mentions downstream systems."""
        runner.invoke(main, ["init-mcp", "--global"])

        claude_md = mock_home / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "downstream" in content.lower()

    def test_global_claude_md_preserves_existing_content(self, runner, mock_home):
        """--global appends to existing CLAUDE.md without overwriting."""
        claude_dir = mock_home / ".claude"
        claude_dir.mkdir()
        existing_content = "# My Custom Instructions\n\nDo things my way.\n"
        (claude_dir / "CLAUDE.md").write_text(existing_content)

        runner.invoke(main, ["init-mcp", "--global"])

        claude_md = claude_dir / "CLAUDE.md"
        content = claude_md.read_text()
        # Original content preserved
        assert "My Custom Instructions" in content
        assert "Do things my way" in content
        # New content appended
        assert "## buildlog" in content

    def test_global_claude_md_idempotent(self, runner, mock_home):
        """Running --global twice doesn't duplicate buildlog section."""
        runner.invoke(main, ["init-mcp", "--global"])
        runner.invoke(main, ["init-mcp", "--global"])

        claude_md = mock_home / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        # Should only have one buildlog section
        assert content.count("## buildlog") == 1

    def test_global_claude_md_output_message(self, runner, mock_home):
        """--global shows message about CLAUDE.md creation."""
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert "CLAUDE.md" in result.output

    def test_global_claude_md_already_exists_message(self, runner, mock_home):
        """Running --global twice shows 'already in' message for CLAUDE.md."""
        runner.invoke(main, ["init-mcp", "--global"])
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert "already" in result.output.lower()

    def test_global_creates_header_for_new_file(self, runner, mock_home):
        """New CLAUDE.md has a header explaining it's global instructions."""
        runner.invoke(main, ["init-mcp", "--global"])

        claude_md = mock_home / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "Global" in content
        assert "all projects" in content.lower()

    def test_global_claude_md_has_outputs_section(self, runner, mock_home):
        """--global CLAUDE.md lists the output files for downstream consumption."""
        runner.invoke(main, ["init-mcp", "--global"])

        claude_md = mock_home / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "reward_events.jsonl" in content or "Outputs" in content

    def test_local_mode_does_not_create_global_claude_md(
        self, runner, mock_home, isolated_fs
    ):
        """Local init-mcp (without --global) doesn't touch ~/.claude/CLAUDE.md."""
        runner.invoke(main, ["init-mcp"])

        global_claude_md = mock_home / ".claude" / "CLAUDE.md"
        assert not global_claude_md.exists()


# =============================================================================
# 2. Graceful Fallback Tests - Overview Command
# =============================================================================


class TestOverviewFallback:
    """Tests for buildlog overview without buildlog/ directory."""

    def test_overview_no_buildlog_returns_zero_exit(self, runner, isolated_fs):
        """overview without buildlog/ returns exit code 0, not error."""
        result = runner.invoke(main, ["overview"])
        assert result.exit_code == 0

    def test_overview_no_buildlog_shows_not_initialized(self, runner, isolated_fs):
        """overview without buildlog/ shows 'not initialized' message."""
        result = runner.invoke(main, ["overview"])
        assert "not initialized" in result.output.lower()

    def test_overview_no_buildlog_suggests_init(self, runner, isolated_fs):
        """overview without buildlog/ suggests running init."""
        result = runner.invoke(main, ["overview"])
        assert "buildlog init" in result.output

    def test_overview_no_buildlog_suggests_global(self, runner, isolated_fs):
        """overview without buildlog/ suggests global mode."""
        result = runner.invoke(main, ["overview"])
        assert "init-mcp --global" in result.output

    def test_overview_no_buildlog_json_has_initialized_false(self, runner, isolated_fs):
        """overview --json without buildlog/ has initialized: false."""
        result = runner.invoke(main, ["overview", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["initialized"] is False

    def test_overview_no_buildlog_json_has_zero_entries(self, runner, isolated_fs):
        """overview --json without buildlog/ has entries: 0."""
        result = runner.invoke(main, ["overview", "--json"])
        data = json.loads(result.output)
        assert data["entries"] == 0

    def test_overview_no_buildlog_json_has_zero_skills(self, runner, isolated_fs):
        """overview --json without buildlog/ has skills.total: 0."""
        result = runner.invoke(main, ["overview", "--json"])
        data = json.loads(result.output)
        assert data["skills"]["total"] == 0

    def test_overview_no_buildlog_json_has_empty_render_targets(
        self, runner, isolated_fs
    ):
        """overview --json without buildlog/ has render_targets: []."""
        result = runner.invoke(main, ["overview", "--json"])
        data = json.loads(result.output)
        assert data["render_targets"] == []

    def test_overview_no_buildlog_json_has_message(self, runner, isolated_fs):
        """overview --json without buildlog/ has informative message."""
        result = runner.invoke(main, ["overview", "--json"])
        data = json.loads(result.output)
        assert "message" in data
        assert "init" in data["message"].lower()


# =============================================================================
# 3. Graceful Fallback Tests - Status Command
# =============================================================================


class TestStatusFallback:
    """Tests for buildlog status without buildlog/ directory."""

    def test_status_no_buildlog_returns_zero_exit(self, runner, isolated_fs):
        """status without buildlog/ returns exit code 0."""
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0

    def test_status_no_buildlog_shows_zero_skills(self, runner, isolated_fs):
        """status without buildlog/ shows 0 skills."""
        result = runner.invoke(main, ["status"])
        assert "0 total" in result.output or "Skills: 0" in result.output

    def test_status_no_buildlog_suggests_init(self, runner, isolated_fs):
        """status without buildlog/ mentions init."""
        result = runner.invoke(main, ["status"])
        assert "init" in result.output.lower()

    def test_status_no_buildlog_json_has_initialized_false(self, runner, isolated_fs):
        """status --json without buildlog/ has initialized: false."""
        result = runner.invoke(main, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["initialized"] is False

    def test_status_no_buildlog_json_has_zero_totals(self, runner, isolated_fs):
        """status --json without buildlog/ has zero total skills and entries."""
        result = runner.invoke(main, ["status", "--json"])
        data = json.loads(result.output)
        assert data["total_skills"] == 0
        assert data["total_entries"] == 0

    def test_status_no_buildlog_json_has_empty_skills(self, runner, isolated_fs):
        """status --json without buildlog/ has empty skills dict."""
        result = runner.invoke(main, ["status", "--json"])
        data = json.loads(result.output)
        assert data["skills"] == {}

    def test_status_no_buildlog_json_has_zero_confidence(self, runner, isolated_fs):
        """status --json without buildlog/ has zero confidence counts."""
        result = runner.invoke(main, ["status", "--json"])
        data = json.loads(result.output)
        assert data["by_confidence"] == {"high": 0, "medium": 0, "low": 0}


# =============================================================================
# 4. Graceful Fallback Tests - Skills Command
# =============================================================================


class TestSkillsFallback:
    """Tests for buildlog skills without buildlog/ directory."""

    def test_skills_no_buildlog_returns_zero_exit(self, runner, isolated_fs):
        """skills without buildlog/ returns exit code 0."""
        result = runner.invoke(main, ["skills"])
        assert result.exit_code == 0

    def test_skills_no_buildlog_yaml_shows_empty(self, runner, isolated_fs):
        """skills without buildlog/ (yaml format) shows empty skills."""
        result = runner.invoke(main, ["skills"])
        assert (
            "skills: {}" in result.output or "not initialized" in result.output.lower()
        )

    def test_skills_no_buildlog_json_has_initialized_false(self, runner, isolated_fs):
        """skills --format json without buildlog/ has initialized: false."""
        result = runner.invoke(main, ["skills", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["initialized"] is False

    def test_skills_no_buildlog_json_has_zero_total(self, runner, isolated_fs):
        """skills --format json without buildlog/ has total_skills: 0."""
        result = runner.invoke(main, ["skills", "--format", "json"])
        data = json.loads(result.output)
        assert data["total_skills"] == 0

    def test_skills_no_buildlog_json_has_empty_skills(self, runner, isolated_fs):
        """skills --format json without buildlog/ has empty skills dict."""
        result = runner.invoke(main, ["skills", "--format", "json"])
        data = json.loads(result.output)
        assert data["skills"] == {}

    def test_skills_no_buildlog_markdown_mentions_init(self, runner, isolated_fs):
        """skills --format markdown without buildlog/ mentions init."""
        result = runner.invoke(main, ["skills", "--format", "markdown"])
        assert result.exit_code == 0
        assert "init" in result.output.lower()


# =============================================================================
# 5. Graceful Fallback Tests - Stats Command
# =============================================================================


class TestStatsFallback:
    """Tests for buildlog stats without buildlog/ directory."""

    def test_stats_no_buildlog_returns_zero_exit(self, runner, isolated_fs):
        """stats without buildlog/ returns exit code 0."""
        result = runner.invoke(main, ["stats"])
        assert result.exit_code == 0

    def test_stats_no_buildlog_shows_not_initialized(self, runner, isolated_fs):
        """stats without buildlog/ shows 'not initialized'."""
        result = runner.invoke(main, ["stats"])
        assert "not initialized" in result.output.lower()

    def test_stats_no_buildlog_json_has_initialized_false(self, runner, isolated_fs):
        """stats --json without buildlog/ has initialized: false."""
        result = runner.invoke(main, ["stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["initialized"] is False

    def test_stats_no_buildlog_json_has_zero_entries(self, runner, isolated_fs):
        """stats --json without buildlog/ has total_entries: 0."""
        result = runner.invoke(main, ["stats", "--json"])
        data = json.loads(result.output)
        assert data["total_entries"] == 0


# =============================================================================
# 6. Graceful Fallback Tests - Diff Command
# =============================================================================


class TestDiffFallback:
    """Tests for buildlog diff without buildlog/ directory."""

    def test_diff_no_buildlog_returns_zero_exit(self, runner, isolated_fs):
        """diff without buildlog/ returns exit code 0."""
        result = runner.invoke(main, ["diff"])
        assert result.exit_code == 0

    def test_diff_no_buildlog_shows_zero_pending(self, runner, isolated_fs):
        """diff without buildlog/ shows 'Pending: 0'."""
        result = runner.invoke(main, ["diff"])
        assert "Pending: 0" in result.output

    def test_diff_no_buildlog_suggests_init(self, runner, isolated_fs):
        """diff without buildlog/ mentions init."""
        result = runner.invoke(main, ["diff"])
        assert "init" in result.output.lower()

    def test_diff_no_buildlog_json_has_initialized_false(self, runner, isolated_fs):
        """diff --json without buildlog/ has initialized: false."""
        result = runner.invoke(main, ["diff", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["initialized"] is False

    def test_diff_no_buildlog_json_has_zero_totals(self, runner, isolated_fs):
        """diff --json without buildlog/ has zero counts."""
        result = runner.invoke(main, ["diff", "--json"])
        data = json.loads(result.output)
        assert data["total_pending"] == 0
        assert data["already_promoted"] == 0
        assert data["already_rejected"] == 0

    def test_diff_no_buildlog_json_has_empty_pending(self, runner, isolated_fs):
        """diff --json without buildlog/ has empty pending dict."""
        result = runner.invoke(main, ["diff", "--json"])
        data = json.loads(result.output)
        assert data["pending"] == {}


# =============================================================================
# 7. Graceful Fallback Tests - Distill Command
# =============================================================================


class TestDistillFallback:
    """Tests for buildlog distill without buildlog/ directory."""

    def test_distill_no_buildlog_returns_zero_exit(self, runner, isolated_fs):
        """distill without buildlog/ returns exit code 0."""
        result = runner.invoke(main, ["distill"])
        assert result.exit_code == 0

    def test_distill_no_buildlog_json_has_initialized_false(self, runner, isolated_fs):
        """distill without buildlog/ (json format) has initialized: false."""
        result = runner.invoke(main, ["distill"])  # default is json
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["initialized"] is False

    def test_distill_no_buildlog_json_has_empty_patterns(self, runner, isolated_fs):
        """distill without buildlog/ has empty patterns list."""
        result = runner.invoke(main, ["distill"])
        data = json.loads(result.output)
        assert data["patterns"] == []

    def test_distill_no_buildlog_json_has_zero_statistics(self, runner, isolated_fs):
        """distill without buildlog/ has zero statistics."""
        result = runner.invoke(main, ["distill"])
        data = json.loads(result.output)
        assert data["statistics"]["total_patterns"] == 0
        assert data["statistics"]["total_entries"] == 0

    def test_distill_no_buildlog_yaml_mentions_init(self, runner, isolated_fs):
        """distill --format yaml without buildlog/ mentions init."""
        result = runner.invoke(main, ["distill", "--format", "yaml"])
        assert result.exit_code == 0
        assert "not initialized" in result.output.lower()


# =============================================================================
# 8. Commands That Should Still Work Without Init
# =============================================================================


class TestCommandsWithoutInit:
    """Tests for commands that should work without buildlog init."""

    def test_gauntlet_list_works_without_init(self, runner, isolated_fs):
        """gauntlet list works without buildlog/ (uses package data)."""
        result = runner.invoke(main, ["gauntlet", "list"])
        # Should not error - uses bundled personas
        assert result.exit_code == 0 or "No seed" in result.output

    def test_mcp_test_works_without_init(self, runner, isolated_fs):
        """mcp-test works without buildlog/ (tests package installation)."""
        result = runner.invoke(main, ["mcp-test"])
        # Should work - tests the package, not the project
        assert "tools registered" in result.output or result.exit_code in [0, 1]

    def test_version_works_without_init(self, runner, isolated_fs):
        """--version works without buildlog/."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0

    def test_help_works_without_init(self, runner, isolated_fs):
        """--help works without buildlog/."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0


# =============================================================================
# 9. Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Edge cases and error handling tests."""

    def test_overview_with_empty_buildlog_dir(self, runner, isolated_fs):
        """overview with empty buildlog/ directory works."""
        Path("buildlog").mkdir()
        result = runner.invoke(main, ["overview"])
        assert result.exit_code == 0
        assert "Entries:     0" in result.output

    def test_status_with_empty_buildlog_dir(self, runner, isolated_fs):
        """status with empty buildlog/ directory works."""
        Path("buildlog").mkdir()
        Path("buildlog/.buildlog").mkdir(parents=True)
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0

    def test_global_mcp_permission_denied(self, runner, mock_home):
        """--global handles permission denied gracefully."""
        # Make home read-only
        (mock_home / ".claude").mkdir()
        os.chmod(mock_home / ".claude", 0o444)

        try:
            result = runner.invoke(main, ["init-mcp", "--global"])
            # Should handle error gracefully
            assert (
                "could not register" in result.output.lower() or result.exit_code == 0
            )
        finally:
            os.chmod(mock_home / ".claude", 0o755)

    def test_initialized_true_when_buildlog_exists(self, runner, isolated_fs):
        """overview --json has initialized: true when buildlog/ exists."""
        Path("buildlog").mkdir()
        Path("buildlog/.buildlog").mkdir()
        result = runner.invoke(main, ["overview", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["initialized"] is True


# =============================================================================
# 10. Integration Tests
# =============================================================================


class TestGlobalWorkflowIntegration:
    """Integration tests for the full global always-on workflow."""

    def test_full_global_setup_workflow(self, runner, mock_home, isolated_fs):
        """Test complete global setup workflow."""
        # Step 1: Register MCP globally
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert result.exit_code == 0
        assert (mock_home / ".claude" / "settings.json").exists()

        # Step 2: Overview should work (shows uninitialized)
        result = runner.invoke(main, ["overview"])
        assert result.exit_code == 0
        assert "not initialized" in result.output.lower()

        # Step 3: Gauntlet should work (uses package data)
        result = runner.invoke(main, ["gauntlet", "list"])
        assert result.exit_code == 0 or "No seed" in result.output

    def test_local_then_global_setup(self, runner, mock_home, isolated_fs):
        """Local init doesn't interfere with global registration."""
        # Local init
        result = runner.invoke(main, ["init", "--defaults"])
        assert Path("buildlog").exists()

        # Global MCP registration
        result = runner.invoke(main, ["init-mcp", "--global"])
        assert result.exit_code == 0

        # Both should exist
        assert Path(".claude/settings.json").exists()
        assert (mock_home / ".claude" / "settings.json").exists()

    def test_json_output_consistency(self, runner, isolated_fs):
        """All fallback JSON outputs have consistent structure."""
        commands = [
            ["overview", "--json"],
            ["status", "--json"],
            ["diff", "--json"],
            ["distill"],  # default is json
            ["stats", "--json"],
        ]

        for cmd in commands:
            result = runner.invoke(main, cmd)
            assert result.exit_code == 0, f"Command {cmd} failed"
            data = json.loads(result.output)
            assert "initialized" in data, f"Command {cmd} missing 'initialized' key"
            assert (
                data["initialized"] is False
            ), f"Command {cmd} should show initialized=false"
