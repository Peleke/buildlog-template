"""Tests for _init_mcp helper and init-mcp command."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from buildlog.cli import main


class TestInitMcp:
    """Tests for _init_mcp() and the init-mcp command."""

    def test_creates_config_from_scratch(self, tmp_path, monkeypatch):
        """Should create .claude/settings.json from scratch."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        runner.invoke(main, ["init-mcp", "-y"])

        settings = tmp_path / ".claude" / "settings.json"
        assert settings.exists()
        data = json.loads(settings.read_text())
        assert "buildlog" in data["mcpServers"]
        # Command can be bare name or full path depending on environment
        assert "buildlog-mcp" in data["mcpServers"]["buildlog"]["command"]

    def test_updates_existing_config(self, tmp_path, monkeypatch):
        """Should add buildlog to existing mcpServers, preserve others."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {
            "mcpServers": {"other-server": {"command": "other-cmd", "args": []}},
            "customKey": True,
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        runner = CliRunner()
        runner.invoke(main, ["init-mcp", "-y"])

        data = json.loads((claude_dir / "settings.json").read_text())
        assert "buildlog" in data["mcpServers"]
        assert "other-server" in data["mcpServers"]
        assert data["customKey"] is True

    def test_idempotent(self, tmp_path, monkeypatch):
        """Running twice should produce same result."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        runner.invoke(main, ["init-mcp", "-y"])
        runner.invoke(main, ["init-mcp", "-y"])

        settings = tmp_path / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        assert "buildlog" in data["mcpServers"]
        # Should only appear once
        assert len(data["mcpServers"]) == 1

    def test_handles_corrupt_json(self, tmp_path, monkeypatch):
        """Should warn and not crash on corrupt JSON."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{invalid json")

        runner = CliRunner()
        result = runner.invoke(main, ["init-mcp", "-y"])
        assert "malformed" in result.output or "Warning" in result.output

    def test_preserves_non_mcp_keys(self, tmp_path, monkeypatch):
        """Should preserve keys outside mcpServers."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {"apiKey": "secret", "theme": "dark"}
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        runner = CliRunner()
        runner.invoke(main, ["init-mcp", "-y"])

        data = json.loads((claude_dir / "settings.json").read_text())
        assert data["apiKey"] == "secret"
        assert data["theme"] == "dark"
        assert "buildlog" in data["mcpServers"]


class TestInitCallsMcp:
    """Tests that buildlog init integrates MCP registration."""

    def test_init_no_mcp_flag_skips(self, tmp_path, monkeypatch):
        """--no-mcp should skip MCP registration."""
        monkeypatch.chdir(tmp_path)
        # Create a minimal buildlog setup so init doesn't fail
        # We need to mock copier to avoid actually running it
        buildlog_dir = tmp_path / "buildlog"

        with patch("buildlog.cli.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0})()
            # Simulate copier creating the directory
            buildlog_dir.mkdir()

            runner = CliRunner()
            runner.invoke(main, ["init", "--defaults", "--no-mcp"])

        settings = tmp_path / ".claude" / "settings.json"
        assert not settings.exists()
