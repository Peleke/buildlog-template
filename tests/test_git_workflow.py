"""Tests for git workflow enforcement."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from buildlog.cli import (
    _get_current_git_branch,
    _is_protected_branch,
    _slug_from_message,
    main,
)


class TestIsProtectedBranch:
    """Tests for _is_protected_branch."""

    def test_main_is_protected(self):
        assert _is_protected_branch("main") is True

    def test_master_is_protected(self):
        assert _is_protected_branch("master") is True

    def test_case_insensitive(self):
        assert _is_protected_branch("Main") is True
        assert _is_protected_branch("MASTER") is True
        assert _is_protected_branch("MAIN") is True

    def test_feature_branch_not_protected(self):
        assert _is_protected_branch("feat/my-feature") is False
        assert _is_protected_branch("develop") is False
        assert _is_protected_branch("fix/bug") is False


class TestGetCurrentGitBranch:
    """Tests for _get_current_git_branch."""

    @patch("buildlog.cli.subprocess.run")
    def test_returns_branch_name(self, mock_run):
        mock_run.return_value = MagicMock(stdout="feat/my-branch\n", returncode=0)
        assert _get_current_git_branch() == "feat/my-branch"

    @patch("buildlog.cli.subprocess.run")
    def test_returns_none_on_detached_head(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(128, "git")
        assert _get_current_git_branch() is None

    @patch("buildlog.cli.subprocess.run")
    def test_returns_none_when_no_git(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        assert _get_current_git_branch() is None


class TestSlugFromMessage:
    """Tests for _slug_from_message."""

    def test_strips_conventional_prefix(self):
        assert _slug_from_message("feat: add login") == "add-login"

    def test_handles_plain_message(self):
        assert _slug_from_message("add login page") == "add-login-page"

    def test_handles_empty(self):
        assert _slug_from_message("") == "feature"


class TestCommitBranchProtection:
    """Tests for buildlog commit branch protection."""

    @patch("buildlog.cli._get_current_git_branch", return_value="main")
    @patch("buildlog.cli.subprocess.run")
    def test_commit_on_main_blocked_without_force(self, mock_run, mock_branch):
        runner = CliRunner()
        # Simulate user declining branch creation
        result = runner.invoke(main, ["commit", "-m", "test"], input="n\n")
        assert result.exit_code != 0

    @patch("buildlog.cli._get_current_git_branch", return_value="main")
    @patch("buildlog.cli.subprocess.run")
    def test_commit_on_main_with_force_succeeds(self, mock_run, mock_branch):
        # git commit succeeds
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        runner = CliRunner()
        result = runner.invoke(main, ["commit", "--force", "-m", "test"])
        # Should proceed to git commit (may fail due to no repo, but should not block)
        # The key assertion is it doesn't prompt
        assert "You're on main" not in (result.output or "")

    @patch("buildlog.cli._get_current_git_branch", return_value="feat/my-feature")
    @patch("buildlog.cli.subprocess.run")
    def test_commit_on_feature_branch_succeeds(self, mock_run, mock_branch):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        runner = CliRunner()
        result = runner.invoke(main, ["commit", "-m", "test"])
        # Should not prompt about branch protection
        assert "You're on" not in (result.output or "")

    @patch("buildlog.cli._get_current_git_branch", return_value="main")
    @patch("buildlog.cli.subprocess.run")
    def test_branch_auto_creation(self, mock_run, mock_branch):
        # First call: git checkout -b (succeeds)
        # Second call: git commit (succeeds)
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        runner = CliRunner()
        runner.invoke(main, ["commit", "-m", "feat: add login"], input="y\n")
        # Should have tried to create the branch
        calls = mock_run.call_args_list
        checkout_calls = [c for c in calls if "checkout" in str(c)]
        assert len(checkout_calls) >= 1

    @patch("buildlog.cli._get_current_git_branch", return_value=None)
    @patch("buildlog.cli.subprocess.run")
    def test_detached_head_allows_commit(self, mock_run, mock_branch):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        runner = CliRunner()
        result = runner.invoke(main, ["commit", "-m", "test"])
        # Should not prompt
        assert "You're on" not in (result.output or "")
