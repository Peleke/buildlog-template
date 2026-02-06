"""Exhaustive tests for the commit core operation and MCP tool."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.core.operations import CommitResult, _resolve_entry_path_core, commit


class TestResolveEntryPathCore:
    """Tests for _resolve_entry_path_core helper."""

    def test_explicit_path_returned_directly(self, tmp_path):
        """Explicit entry path should be returned as-is."""
        result = _resolve_entry_path_core(tmp_path, "2026-01-01", None, "/some/path.md")
        assert result == Path("/some/path.md")

    def test_existing_entry_found(self, tmp_path):
        """Should find existing entry matching today's date."""
        (tmp_path / "2026-01-01-existing.md").write_text("# Test\n")
        result = _resolve_entry_path_core(tmp_path, "2026-01-01", None, None)
        assert result.name == "2026-01-01-existing.md"

    def test_slug_used_when_no_existing(self, tmp_path):
        """Should use slug when no existing entry for today."""
        result = _resolve_entry_path_core(tmp_path, "2026-01-01", "my-feature", None)
        assert result == tmp_path / "2026-01-01-my-feature.md"

    def test_branch_derived_slug(self, tmp_path):
        """Should derive slug from git branch when no slug provided."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"stdout": "feat/my-branch\n", "returncode": 0}
            )()
            result = _resolve_entry_path_core(tmp_path, "2026-01-01", None, None)
            assert "my-branch" in result.name

    def test_git_failure_defaults_to_session(self, tmp_path):
        """Should use 'session' slug when git fails."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            result = _resolve_entry_path_core(tmp_path, "2026-01-01", None, None)
            assert result.name == "2026-01-01-session.md"

    def test_empty_slug_defaults_to_session(self, tmp_path):
        """Empty slug after cleaning should default to 'session'."""
        result = _resolve_entry_path_core(tmp_path, "2026-01-01", "", None)
        assert result.name == "2026-01-01-session.md"

    def test_cwd_passed_to_subprocess(self, tmp_path):
        """Should pass cwd to git subprocess."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"stdout": "main\n", "returncode": 0}
            )()
            _resolve_entry_path_core(tmp_path, "2026-01-01", None, None, cwd="/other")
            mock_run.assert_called_once()
            assert mock_run.call_args.kwargs.get("cwd") == "/other"


class TestCommitCoreOp:
    """Tests for commit() core operation."""

    def _init_git_repo(self, tmp_path):
        """Initialize a git repo with a staged file."""
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=str(tmp_path),
            capture_output=True,
        )

    def test_returns_commit_result(self, tmp_path):
        """Should return a CommitResult dataclass."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = commit(
            buildlog_dir,
            git_args=["-m", "test commit"],
            cwd=str(tmp_path),
        )
        assert isinstance(result, CommitResult)

    def test_successful_commit(self, tmp_path):
        """Should commit and return hash, message, files."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = commit(
            buildlog_dir,
            git_args=["-m", "feat: test commit"],
            cwd=str(tmp_path),
        )
        assert result.error is None
        assert result.commit_hash != ""
        assert result.commit_message == "feat: test commit"
        assert "file.txt" in result.files_changed

    def test_git_failure_returns_error(self, tmp_path):
        """Non-git dir should return error."""
        result = commit(
            tmp_path / "buildlog",
            git_args=["-m", "test"],
            cwd=str(tmp_path),
        )
        assert result.error is not None
        assert "git commit failed" in result.error

    def test_updates_entry(self, tmp_path):
        """Should append commit block to buildlog entry."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = commit(
            buildlog_dir,
            git_args=["-m", "test commit"],
            cwd=str(tmp_path),
        )
        assert result.entry_updated is True
        assert result.entry_path is not None
        content = Path(result.entry_path).read_text()
        assert "## Commits" in content
        assert result.commit_hash in content

    def test_no_entry_flag(self, tmp_path):
        """no_entry=True should skip entry update."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = commit(
            buildlog_dir,
            git_args=["-m", "test"],
            no_entry=True,
            cwd=str(tmp_path),
        )
        assert result.error is None
        assert result.entry_updated is False
        assert result.entry_path is None

    def test_creates_entry_if_missing(self, tmp_path):
        """Should create a new entry file if none exists for today."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = commit(
            buildlog_dir,
            git_args=["-m", "first commit"],
            slug="test",
            cwd=str(tmp_path),
        )
        assert result.entry_updated is True
        assert Path(result.entry_path).exists()

    def test_appends_to_existing_entry(self, tmp_path):
        """Should append commit block to existing entry."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        from datetime import date

        today = date.today().isoformat()
        entry = buildlog_dir / f"{today}-existing.md"
        entry.write_text("# Existing Entry\n\n## Commits\n")

        result = commit(
            buildlog_dir,
            git_args=["-m", "second commit"],
            cwd=str(tmp_path),
        )
        content = entry.read_text()
        assert content.count("## Commits") == 1
        assert result.commit_hash in content

    def test_adds_commits_section_if_missing(self, tmp_path):
        """Should add ## Commits section if not present."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        from datetime import date

        today = date.today().isoformat()
        entry = buildlog_dir / f"{today}-no-commits.md"
        entry.write_text("# Entry without commits section\n")

        result = commit(
            buildlog_dir,
            git_args=["-m", "add section"],
            cwd=str(tmp_path),
        )
        content = entry.read_text()
        assert "## Commits" in content
        assert result.commit_hash in content

    def test_files_changed_capped_at_20(self, tmp_path):
        """Files list should cap at 20 entries."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        # Create 25 files
        for i in range(25):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content {i}")
            subprocess.run(
                ["git", "add", f.name],
                cwd=str(tmp_path),
                capture_output=True,
            )
        result = commit(
            buildlog_dir,
            git_args=["-m", "many files"],
            cwd=str(tmp_path),
        )
        assert result.error is None
        if result.entry_path:
            content = Path(result.entry_path).read_text()
            assert "...and" in content

    def test_nonexistent_buildlog_dir_skips_entry(self, tmp_path):
        """Should skip entry update if buildlog dir doesn't exist."""
        self._init_git_repo(tmp_path)
        result = commit(
            tmp_path / "nonexistent",
            git_args=["-m", "test"],
            cwd=str(tmp_path),
        )
        assert result.error is None
        assert result.entry_updated is False

    def test_slug_parameter(self, tmp_path):
        """Slug should appear in entry filename."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = commit(
            buildlog_dir,
            git_args=["-m", "test"],
            slug="my-slug",
            cwd=str(tmp_path),
        )
        assert "my-slug" in Path(result.entry_path).name

    def test_message_field(self, tmp_path):
        """Result message should contain hash and commit msg."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = commit(
            buildlog_dir,
            git_args=["-m", "hello world"],
            cwd=str(tmp_path),
        )
        assert "hello world" in result.message
        assert result.commit_hash in result.message


class TestBuildlogCommitMCPTool:
    """Tests for the buildlog_commit MCP wrapper."""

    def _init_git_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=str(tmp_path),
            capture_output=True,
        )

    def test_returns_dict(self, tmp_path, monkeypatch):
        """Should return a dict."""
        self._init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "buildlog").mkdir()
        from buildlog.mcp.tools import buildlog_commit

        result = buildlog_commit(message="test")
        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path, monkeypatch):
        """Should have all CommitResult keys."""
        self._init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "buildlog").mkdir()
        from buildlog.mcp.tools import buildlog_commit

        result = buildlog_commit(message="test")
        assert "commit_hash" in result
        assert "commit_message" in result
        assert "files_changed" in result
        assert "entry_path" in result
        assert "entry_updated" in result
        assert "error" in result

    def test_passes_cwd_from_buildlog_dir(self, tmp_path):
        """MCP wrapper should derive cwd from buildlog_dir, not process cwd."""
        self._init_git_repo(tmp_path)
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        from buildlog.mcp.tools import buildlog_commit

        # Call with absolute buildlog_dir — should work regardless of process cwd
        result = buildlog_commit(
            message="test from absolute path",
            buildlog_dir=str(buildlog_dir),
        )
        assert result["error"] is None
        assert result["commit_hash"] != ""
        assert result["commit_message"] == "test from absolute path"

    def test_error_on_non_git_dir(self, tmp_path, monkeypatch):
        """Should return error dict for non-git directory."""
        monkeypatch.chdir(tmp_path)
        from buildlog.mcp.tools import buildlog_commit

        result = buildlog_commit(message="test")
        assert result["error"] is not None
