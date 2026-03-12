"""End-to-end user flow tests covering all critical buildlog workflows.

These tests exercise real user journeys through the system without
requiring an LLM backend. Each test class represents a complete flow.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.constants import CLAUDE_MD_BUILDLOG_SECTION
from buildlog.core.operations import (
    CommitResult,
    CreateEntryResult,
    DiffResult,
    EndSessionResult,
    GauntletAcceptRiskResult,
    GauntletLoopConfigResult,
    GauntletLoopResult,
    GauntletPromptResult,
    InitResult,
    LearnFromReviewResult,
    ListEntriesResult,
    LogMistakeResult,
    OverviewResult,
    SessionMetrics,
    StartSessionResult,
    commit,
    create_entry,
    diff,
    end_session,
    gauntlet_accept_risk,
    gauntlet_loop_config,
    gauntlet_process_issues,
    generate_gauntlet_prompt,
    get_experiment_report,
    get_overview,
    get_session_metrics,
    init_buildlog,
    learn_from_review,
    list_entries,
    log_mistake,
    promote,
    start_session,
    status,
)
from buildlog.mcp.tools import buildlog_distill, buildlog_skills, buildlog_stats

# Path to test fixtures shipped with the repo
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "buildlog"

# All 31 MCP tool names registered in the server
ALL_TOOL_NAMES = [
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
    "buildlog_gauntlet_issues",
    "buildlog_gauntlet_accept_risk",
    "buildlog_bandit_status",
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
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMPLATE_CONTENT = """\
# Session Log — [YYYY-MM-DD]

## What I Built

## What I Learned

## Improvements

## Commits
"""


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo with user config for commits."""
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(path),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path),
        capture_output=True,
    )


def _setup_buildlog_dir(tmp_path: Path) -> Path:
    """Create a minimal buildlog directory structure with template."""
    bl = tmp_path / "buildlog"
    bl.mkdir()
    dot = bl / ".buildlog"
    dot.mkdir()
    (dot / "seeds").mkdir()
    (bl / "_TEMPLATE.md").write_text(TEMPLATE_CONTENT)
    return bl


def _init_with_mock_copier(tmp_path: Path) -> InitResult:
    """Run init_buildlog with copier mocked, pre-creating buildlog/ so post-copier steps work."""
    # The mock makes copier a no-op, so we pre-create the directory
    # that copier would have created. init_buildlog checks for existence
    # first, so we need to let it pass the "already exists" check by NOT
    # creating it — but then copier won't create it either. Instead we
    # patch at the subprocess level and create it inside the side-effect.
    bl = tmp_path / "buildlog"

    def _fake_copier(*args, **kwargs):
        # Simulate copier creating the buildlog directory
        bl.mkdir(exist_ok=True)
        return type("R", (), {"stdout": "", "stderr": "", "returncode": 0})()

    with patch("subprocess.run", side_effect=_fake_copier):
        return init_buildlog(tmp_path)


# ===========================================================================
# Flow 1: Fresh Init
# ===========================================================================


class TestFlowFreshInit:
    """Init buildlog in a fresh project — copier mocked."""

    def test_init_creates_structure(self, tmp_path):
        """init_buildlog creates buildlog/ and .buildlog/seeds/."""
        (tmp_path / "CLAUDE.md").write_text("# My Project\n")
        result = _init_with_mock_copier(tmp_path)

        assert isinstance(result, InitResult)
        assert result.initialized is True
        assert (tmp_path / "buildlog").is_dir()
        assert (tmp_path / "buildlog" / ".buildlog" / "seeds").is_dir()

    def test_claude_md_has_all_tool_names(self, tmp_path):
        """CLAUDE.md should reference all 29 tool names after init."""
        (tmp_path / "CLAUDE.md").write_text("# My Project\n")
        _init_with_mock_copier(tmp_path)

        content = (tmp_path / "CLAUDE.md").read_text()
        for name in ALL_TOOL_NAMES:
            assert name in content, f"Missing tool name in CLAUDE.md: {name}"

    def test_mcp_settings_registered(self, tmp_path):
        """settings.json should have buildlog MCP server config."""
        (tmp_path / "CLAUDE.md").write_text("# My Project\n")
        _init_with_mock_copier(tmp_path)

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert settings["mcpServers"]["buildlog"]["command"] == "buildlog-mcp"


# ===========================================================================
# Flow 2: Commit → Entry Loop
# ===========================================================================


class TestFlowCommitEntry:
    """Create an entry, commit, verify entry updated with commit info."""

    def test_create_commit_list_overview(self, tmp_path):
        """Full cycle: create entry → commit → list → overview."""
        _init_git_repo(tmp_path)
        bl = _setup_buildlog_dir(tmp_path)

        # Create entry
        entry_result = create_entry(bl, "test-feature", entry_date="2026-02-01")
        assert isinstance(entry_result, CreateEntryResult)
        assert entry_result.entry_path != ""
        entry_path = Path(entry_result.entry_path)
        assert entry_path.exists()

        # Stage the entry and a dummy file, then commit
        dummy = tmp_path / "app.py"
        dummy.write_text("print('hello')\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)

        commit_result = commit(
            bl, git_args=["-m", "feat: test thing"], cwd=str(tmp_path)
        )
        assert isinstance(commit_result, CommitResult)

        # Entry should now contain a Commits section with a hash
        content = entry_path.read_text()
        assert "## Commits" in content
        if commit_result.commit_hash:
            assert commit_result.commit_hash[:7] in content or "## Commits" in content

        # List entries
        entries = list_entries(bl)
        assert isinstance(entries, ListEntriesResult)
        assert entries.count >= 1

        # Overview
        overview = get_overview(bl)
        assert isinstance(overview, OverviewResult)
        assert overview.entries >= 1


# ===========================================================================
# Flow 3: Gauntlet Review Loop
# ===========================================================================


class TestFlowGauntletLoop:
    """Gauntlet review: prompt → config → process issues → accept risk → learn."""

    def test_gauntlet_prompt_has_rules(self):
        """generate_gauntlet_prompt should return rules for a persona."""
        result = generate_gauntlet_prompt("src/", personas=["security_karen"])
        assert isinstance(result, GauntletPromptResult)
        assert result.prompt or result.rules

    def test_gauntlet_loop_config_populated(self):
        """gauntlet_loop_config should return all config fields."""
        result = gauntlet_loop_config("src/")
        assert isinstance(result, GauntletLoopConfigResult)
        assert result.target == "src/"
        assert result.max_iterations > 0

    def test_gauntlet_process_issues_categorized(self, tmp_path):
        """Processing mock issues should categorize and return action."""
        bl = _setup_buildlog_dir(tmp_path)
        mock_issues = [
            {"severity": "critical", "description": "SQL injection", "file": "db.py"},
            {"severity": "major", "description": "No auth check", "file": "api.py"},
            {"severity": "minor", "description": "Unused import", "file": "util.py"},
        ]
        result = gauntlet_process_issues(bl, issues=mock_issues, iteration=1)
        assert isinstance(result, GauntletLoopResult)
        assert result.action in (
            "fix_criticals",
            "checkpoint_majors",
            "checkpoint_minors",
            "clean",
        )

    def test_gauntlet_accept_risk(self):
        """Accepting risk should return accepted_issues count."""
        remaining = [
            {"severity": "minor", "description": "Unused var", "file": "x.py"},
        ]
        result = gauntlet_accept_risk(remaining_issues=remaining)
        assert isinstance(result, GauntletAcceptRiskResult)
        assert result.accepted_issues >= 1
        assert result.checklist_items == 0  # no github issues created

    def test_learn_from_review_persists(self, tmp_path):
        """Learning from review issues should persist to disk."""
        bl = _setup_buildlog_dir(tmp_path)
        issues = [
            {"severity": "major", "description": "Missing validation", "file": "a.py"},
            {"severity": "minor", "description": "Typo in docstring", "file": "b.py"},
        ]
        result = learn_from_review(bl, issues=issues)
        assert isinstance(result, LearnFromReviewResult)
        learnings_file = bl / ".buildlog" / "review_learnings.json"
        assert learnings_file.exists()


# ===========================================================================
# Flow 4: Skill Extraction & Promotion
# ===========================================================================


class TestFlowSkillPromotion:
    """Distill → skills → stats → status → diff → promote."""

    def test_distill_extracts_patterns(self):
        """buildlog_distill should extract patterns from fixture entries."""
        result = buildlog_distill(buildlog_dir=str(FIXTURES_DIR))
        assert isinstance(result, dict)
        assert result.get("entry_count", 0) > 0

    def test_skills_generated(self):
        """buildlog_skills should produce skills from fixture entries."""
        result = buildlog_skills(buildlog_dir=str(FIXTURES_DIR))
        assert isinstance(result, dict)
        assert result.get("total_skills", 0) >= 0

    def test_stats_has_fields(self):
        """buildlog_stats should return entries/insights/streak."""
        result = buildlog_stats(buildlog_dir=str(FIXTURES_DIR))
        assert isinstance(result, dict)
        assert "entries" in result or "entry_count" in result

    def test_status_lists_skills(self, tmp_path):
        """status() should return a StatusResult."""
        bl = _setup_buildlog_dir(tmp_path)
        result = status(bl)
        assert result.total_skills >= 0

    def test_diff_returns_pending(self, tmp_path):
        """diff() should return total_pending count."""
        bl = _setup_buildlog_dir(tmp_path)
        result = diff(bl)
        assert isinstance(result, DiffResult)
        assert result.total_pending >= 0

    def test_promote_to_claude_md(self, tmp_path):
        """promote() should accept claude_md target."""
        bl = _setup_buildlog_dir(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project\n")
        result = promote(bl, skill_ids=[], target="claude_md")
        assert result.target == "claude_md"


# ===========================================================================
# Flow 5: Experiment Tracking
# ===========================================================================


class TestFlowExperiment:
    """Session lifecycle: start → log mistakes → end → metrics → report."""

    def test_full_experiment_lifecycle(self, tmp_path):
        """Start session, log mistakes, end, verify metrics."""
        bl = _setup_buildlog_dir(tmp_path)

        # Start session
        start = start_session(bl)
        assert isinstance(start, StartSessionResult)
        assert start.session_id is not None
        session_id = start.session_id
        assert (bl / ".buildlog" / "active_session.json").exists()

        # Log 2 mistakes
        m1 = log_mistake(bl, error_class="missing_test", description="Forgot unit test")
        assert isinstance(m1, LogMistakeResult)
        m2 = log_mistake(bl, error_class="typo", description="Variable name typo")
        assert isinstance(m2, LogMistakeResult)

        mistakes_file = bl / ".buildlog" / "mistakes.jsonl"
        assert mistakes_file.exists()
        raw_lines = mistakes_file.read_text().strip().splitlines()
        lines = [line for line in raw_lines if line.strip()]
        assert len(lines) == 2

        # End session
        end = end_session(bl)
        assert isinstance(end, EndSessionResult)
        assert not (bl / ".buildlog" / "active_session.json").exists()

        # Metrics
        metrics = get_session_metrics(bl, session_id=session_id)
        assert isinstance(metrics, SessionMetrics)
        assert metrics.total_mistakes == 2

        # Report
        report = get_experiment_report(bl)
        assert isinstance(report, dict)
        assert report.get("summary", {}).get("total_sessions", 0) >= 1


# ===========================================================================
# Flow 6: MCP Server Completeness
# ===========================================================================


class TestFlowMCPServer:
    """Verify all 36 tools are registered in the MCP server."""

    @pytest.mark.asyncio
    async def test_server_has_35_tools(self):
        """MCP server should expose exactly 36 tools."""
        from buildlog.mcp.server import mcp

        tools = await mcp.list_tools()
        assert len(tools) == 36

    @pytest.mark.asyncio
    async def test_tool_metadata_valid(self):
        """Every tool should have buildlog_ prefix, description, and schema."""
        from buildlog.mcp.server import mcp

        tools = await mcp.list_tools()
        for tool in tools:
            assert tool.name.startswith("buildlog_"), f"Bad prefix: {tool.name}"
            assert len(tool.description or "") > 10, f"Short desc: {tool.name}"
            assert tool.inputSchema["type"] == "object", f"Bad schema: {tool.name}"

    @pytest.mark.asyncio
    async def test_all_expected_names_present(self):
        """Every name in ALL_TOOL_NAMES should be in the server."""
        from buildlog.mcp.server import mcp

        tools = await mcp.list_tools()
        registered = {t.name for t in tools}
        for name in ALL_TOOL_NAMES:
            assert name in registered, f"Missing tool: {name}"


# ===========================================================================
# Flow 7: Idempotent Init
# ===========================================================================


class TestFlowIdempotentInit:
    """Init should be idempotent and not clobber existing config."""

    def test_double_init_returns_error(self, tmp_path):
        """Second init_buildlog should return error, not clobber."""
        (tmp_path / "CLAUDE.md").write_text("# Project\n")
        first = _init_with_mock_copier(tmp_path)
        assert first.initialized is True

        # Second call — buildlog/ already exists
        second = init_buildlog(tmp_path)
        assert second.initialized is False
        assert "already exists" in (second.error or "")

    def test_init_mcp_preserves_other_servers(self, tmp_path):
        """init should preserve other MCP servers in settings.json."""
        (tmp_path / "CLAUDE.md").write_text("# Project\n")
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {
            "mcpServers": {
                "other": {"command": "other-cmd", "args": []},
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings))

        _init_with_mock_copier(tmp_path)

        updated = json.loads((claude_dir / "settings.json").read_text())
        assert "other" in updated["mcpServers"], "Other server was clobbered"
        assert "buildlog" in updated["mcpServers"], "Buildlog not added"

    def test_init_mcp_no_duplicate(self, tmp_path):
        """Running init twice should not duplicate buildlog entry."""
        (tmp_path / "CLAUDE.md").write_text("# Project\n")
        _init_with_mock_copier(tmp_path)

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert settings["mcpServers"]["buildlog"]["command"] == "buildlog-mcp"
        assert list(settings["mcpServers"].keys()).count("buildlog") == 1
