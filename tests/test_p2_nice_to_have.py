"""Exhaustive tests for P2 nice-to-have core ops and MCP tools."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from buildlog.core.operations import (
    GauntletGenerateResult,
    InitResult,
    UpdateResult,
    gauntlet_generate,
    init_buildlog,
    update_buildlog,
)

# =============================================================================
# gauntlet_generate tests
# =============================================================================


class TestGauntletGenerate:
    """Tests for gauntlet_generate() core operation."""

    def test_returns_result_type(self):
        """Should return GauntletGenerateResult (may error without LLM)."""
        result = gauntlet_generate(
            source_text="Some rules about security",
            persona="test_persona",
            dry_run=True,
        )
        assert isinstance(result, GauntletGenerateResult)
        # Without an LLM backend, this will error — that's expected
        if result.error:
            assert "LLM" in result.error or "pipeline" in result.error.lower()

    def test_empty_source_returns_error(self):
        """Empty source text should error."""
        result = gauntlet_generate(source_text="", persona="test")
        assert result.error is not None
        assert "Empty" in result.error

    def test_whitespace_only_returns_error(self):
        """Whitespace-only source should error."""
        result = gauntlet_generate(source_text="   \n\t  ", persona="test")
        assert result.error is not None

    def test_persona_preserved(self):
        """Persona name should be in result."""
        result = gauntlet_generate(source_text="test content", persona="my_persona")
        assert result.persona == "my_persona"

    def test_no_llm_backend_returns_error(self):
        """Should return error when no LLM backend is available."""
        with patch("buildlog.llm.get_llm_backend", return_value=None):
            result = gauntlet_generate(source_text="content", persona="test")
            assert isinstance(result, GauntletGenerateResult)
            assert result.error is not None
            assert "LLM" in result.error


class TestBuildlogGauntletGenerateMCP:
    """Tests for buildlog_gauntlet_generate MCP wrapper."""

    def test_returns_dict(self):
        from buildlog.mcp.tools import buildlog_gauntlet_generate

        result = buildlog_gauntlet_generate(source_text="test", persona="test")
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        from buildlog.mcp.tools import buildlog_gauntlet_generate

        result = buildlog_gauntlet_generate(source_text="test content", persona="test")
        assert "persona" in result
        assert "rule_count" in result
        assert "error" in result

    def test_empty_source_error(self):
        from buildlog.mcp.tools import buildlog_gauntlet_generate

        result = buildlog_gauntlet_generate(source_text="", persona="test")
        assert result["error"] is not None


# =============================================================================
# init_buildlog tests
# =============================================================================


class TestInitBuildlog:
    """Tests for init_buildlog() core operation."""

    def _mock_copier(self, tmp_path):
        """Create a mock that simulates copier creating buildlog/."""

        def side_effect(*args, **kwargs):
            (tmp_path / "buildlog").mkdir(exist_ok=True)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        return side_effect

    def test_returns_result_type(self, tmp_path):
        """Should return InitResult."""
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            result = init_buildlog(tmp_path)
        assert isinstance(result, InitResult)

    def test_fails_if_buildlog_exists(self, tmp_path):
        """Should error if buildlog/ already exists."""
        (tmp_path / "buildlog").mkdir()
        result = init_buildlog(tmp_path)
        assert result.error is not None
        assert "already exists" in result.error
        assert result.initialized is False

    def test_creates_dot_buildlog(self, tmp_path):
        """Should create .buildlog/ and .buildlog/seeds/."""
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            init_buildlog(tmp_path)
        assert (tmp_path / "buildlog" / ".buildlog").exists()
        assert (tmp_path / "buildlog" / ".buildlog" / "seeds").exists()

    def test_registers_mcp_by_default(self, tmp_path):
        """Should create .claude/settings.json with buildlog MCP."""
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            result = init_buildlog(tmp_path)
        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        data = json.loads(settings_path.read_text())
        assert "buildlog" in data["mcpServers"]
        assert result.mcp_registered is True

    def test_no_mcp_flag(self, tmp_path):
        """no_mcp=True should skip MCP registration."""
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            result = init_buildlog(tmp_path, no_mcp=True)
        assert not (tmp_path / ".claude" / "settings.json").exists()
        assert result.mcp_registered is False

    def test_updates_claude_md(self, tmp_path):
        """Should add buildlog section to existing CLAUDE.md."""
        (tmp_path / "CLAUDE.md").write_text("# My Project\n")
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            result = init_buildlog(tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "buildlog Integration" in content
        assert result.claude_md_updated is True

    def test_no_claude_md_flag(self, tmp_path):
        """no_claude_md=True should skip CLAUDE.md update."""
        (tmp_path / "CLAUDE.md").write_text("# My Project\n")
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            result = init_buildlog(tmp_path, no_claude_md=True)
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "buildlog Integration" not in content
        assert result.claude_md_updated is False

    def test_copier_failure(self, tmp_path):
        """Should return error if copier fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R",
                (),
                {"returncode": 1, "stdout": "", "stderr": "copier error"},
            )()
            result = init_buildlog(tmp_path)
        assert result.error is not None
        assert "copier failed" in result.error

    def test_copier_not_found(self, tmp_path):
        """Should return error if copier not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = init_buildlog(tmp_path)
        assert result.error is not None
        assert "copier not found" in result.error

    def test_copier_timeout(self, tmp_path):
        """Should return error on copier timeout."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("copier", 60),
        ):
            result = init_buildlog(tmp_path)
        assert result.error is not None
        assert "timed out" in result.error

    def test_idempotent_claude_md(self, tmp_path):
        """Running twice should not duplicate CLAUDE.md section."""
        (tmp_path / "CLAUDE.md").write_text(
            "# Project\n\n## buildlog Integration\nExisting\n"
        )
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            result = init_buildlog(tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text()
        assert content.count("## buildlog Integration") == 1
        assert result.claude_md_updated is False

    def test_preserves_existing_mcp_servers(self, tmp_path):
        """Should preserve existing MCP servers in settings.json."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {"mcpServers": {"other": {"command": "other-cmd", "args": []}}}
        (claude_dir / "settings.json").write_text(json.dumps(existing))
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            init_buildlog(tmp_path)
        data = json.loads((claude_dir / "settings.json").read_text())
        assert "other" in data["mcpServers"]
        assert "buildlog" in data["mcpServers"]


class TestBuildlogInitMCP:
    """Tests for buildlog_init MCP wrapper."""

    def _mock_copier(self, tmp_path):
        def side_effect(*args, **kwargs):
            (tmp_path / "buildlog").mkdir(exist_ok=True)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        return side_effect

    def test_returns_dict(self, tmp_path, monkeypatch):
        from buildlog.mcp.tools import buildlog_init

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            result = buildlog_init()
        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path, monkeypatch):
        from buildlog.mcp.tools import buildlog_init

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run", side_effect=self._mock_copier(tmp_path)):
            result = buildlog_init()
        assert "initialized" in result
        assert "buildlog_dir" in result
        assert "claude_md_updated" in result
        assert "mcp_registered" in result
        assert "error" in result


# =============================================================================
# update_buildlog tests
# =============================================================================


class TestUpdateBuildlog:
    """Tests for update_buildlog() core operation."""

    def test_returns_result_type(self, tmp_path):
        """Should return UpdateResult."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "", "stderr": ""}
            )()
            result = update_buildlog(tmp_path)
        assert isinstance(result, UpdateResult)

    def test_success(self, tmp_path):
        """Should return updated=True on success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "", "stderr": ""}
            )()
            result = update_buildlog(tmp_path)
        assert result.updated is True
        assert result.error is None

    def test_copier_failure(self, tmp_path):
        """Should return error on copier failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R",
                (),
                {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "update failed",
                },
            )()
            result = update_buildlog(tmp_path)
        assert result.updated is False
        assert result.error is not None

    def test_copier_not_found(self, tmp_path):
        """Should handle missing copier."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = update_buildlog(tmp_path)
        assert result.error is not None
        assert "copier not found" in result.error

    def test_copier_timeout(self, tmp_path):
        """Should handle copier timeout."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("copier", 120),
        ):
            result = update_buildlog(tmp_path)
        assert result.error is not None
        assert "timed out" in result.error

    def test_passes_cwd(self, tmp_path):
        """Should pass project_dir as cwd."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "", "stderr": ""}
            )()
            update_buildlog(tmp_path)
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["cwd"] == str(tmp_path)


class TestBuildlogUpdateMCP:
    """Tests for buildlog_update MCP wrapper."""

    def test_returns_dict(self, tmp_path, monkeypatch):
        from buildlog.mcp.tools import buildlog_update

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "", "stderr": ""}
            )()
            result = buildlog_update()
        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path, monkeypatch):
        from buildlog.mcp.tools import buildlog_update

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "", "stderr": ""}
            )()
            result = buildlog_update()
        assert "updated" in result
        assert "message" in result
        assert "error" in result


# =============================================================================
# Server registration tests for all 10 new tools
# =============================================================================


class TestAllNewToolsRegistered:
    """Verify all P0+P1+P2 tools are registered in the server."""

    @pytest.mark.asyncio
    async def test_p0_tools_registered(self):
        from buildlog.mcp.server import mcp

        tools = await mcp.list_tools()
        names = [t.name for t in tools]
        assert "buildlog_commit" in names
        assert "buildlog_gauntlet_prompt" in names
        assert "buildlog_gauntlet_loop" in names

    @pytest.mark.asyncio
    async def test_p1_tools_registered(self):
        from buildlog.mcp.server import mcp

        tools = await mcp.list_tools()
        names = [t.name for t in tools]
        assert "buildlog_distill" in names
        assert "buildlog_skills" in names
        assert "buildlog_stats" in names
        assert "buildlog_gauntlet_list_personas" in names

    @pytest.mark.asyncio
    async def test_p2_tools_registered(self):
        from buildlog.mcp.server import mcp

        tools = await mcp.list_tools()
        names = [t.name for t in tools]
        assert "buildlog_gauntlet_generate" in names
        assert "buildlog_init" in names
        assert "buildlog_update" in names

    @pytest.mark.asyncio
    async def test_total_tool_count_is_33(self):
        from buildlog.mcp.server import mcp

        tools = await mcp.list_tools()
        assert len(tools) == 33, (
            f"Expected 33 tools, got {len(tools)}: " f"{[t.name for t in tools]}"
        )

    @pytest.mark.asyncio
    async def test_all_tools_have_descriptions(self):
        from buildlog.mcp.server import mcp

        tools = await mcp.list_tools()
        for tool in tools:
            assert tool.description, f"Tool {tool.name} has no description"
            assert len(tool.description) > 10, f"Tool {tool.name} description too short"
