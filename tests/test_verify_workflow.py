"""Tests for verify_workflow() and workflow section injection."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from buildlog.cli import main
from buildlog.constants import (
    _WORKFLOW_SECTION_END,
    _WORKFLOW_SECTION_START,
    CLAUDE_MD_WORKFLOW_SECTION,
)
from buildlog.core.operations import VerifyCheck, VerifyResult, verify_workflow

# =============================================================================
# verify_workflow tests
# =============================================================================


class TestVerifyWorkflow:
    """Tests for verify_workflow() core operation."""

    def test_empty_project_fails(self, tmp_path: Path):
        """Should fail when buildlog/ doesn't exist."""
        result = verify_workflow(tmp_path)
        assert not result.ok
        failed_names = [c.name for c in result.failed]
        assert "buildlog_dir" in failed_names

    def test_minimal_setup_passes_buildlog_dir(self, tmp_path: Path):
        """Should pass buildlog_dir check when dir exists."""
        (tmp_path / "buildlog").mkdir()
        result = verify_workflow(tmp_path)
        passed_names = [c.name for c in result.passed]
        assert "buildlog_dir" in passed_names

    def test_metadata_dir_warning(self, tmp_path: Path):
        """Should warn when .buildlog/ is missing."""
        (tmp_path / "buildlog").mkdir()
        result = verify_workflow(tmp_path)
        warning_names = [c.name for c in result.warnings]
        assert "metadata_dir" in warning_names

    def test_metadata_dir_passes(self, tmp_path: Path):
        """Should pass when .buildlog/ exists."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        result = verify_workflow(tmp_path)
        passed_names = [c.name for c in result.passed]
        assert "metadata_dir" in passed_names

    def test_claude_md_missing_fails(self, tmp_path: Path):
        """Should fail when CLAUDE.md doesn't exist."""
        (tmp_path / "buildlog").mkdir()
        result = verify_workflow(tmp_path)
        failed_names = [c.name for c in result.failed]
        assert "workflow_section" in failed_names

    def test_claude_md_without_workflow_fails(self, tmp_path: Path):
        """Should fail when CLAUDE.md exists but has no workflow section."""
        (tmp_path / "buildlog").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# My Project\n\nSome content.\n")
        result = verify_workflow(tmp_path)
        failed_names = [c.name for c in result.failed]
        assert "workflow_section" in failed_names

    def test_claude_md_with_buildlog_but_no_workflow_warns(self, tmp_path: Path):
        """Should warn when CLAUDE.md has buildlog section but no workflow markers."""
        (tmp_path / "buildlog").mkdir()
        (tmp_path / "CLAUDE.md").write_text(
            "# Project\n\n## buildlog Integration\n\nSome content.\n"
        )
        result = verify_workflow(tmp_path)
        warning_names = [c.name for c in result.warnings]
        assert "workflow_section" in warning_names

    def test_claude_md_with_workflow_passes(self, tmp_path: Path):
        """Should pass when CLAUDE.md has workflow markers."""
        (tmp_path / "buildlog").mkdir()
        (tmp_path / "CLAUDE.md").write_text(
            f"# Project\n\n{_WORKFLOW_SECTION_START}\n## Workflow\n{_WORKFLOW_SECTION_END}\n"
        )
        result = verify_workflow(tmp_path)
        passed_names = [c.name for c in result.passed]
        assert "workflow_section" in passed_names

    def test_not_on_main_passes(self, tmp_path: Path):
        """Should pass when on a feature branch."""
        (tmp_path / "buildlog").mkdir()
        # Mock git to return a feature branch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="feat/my-feature\n", stderr=""
            )
            result = verify_workflow(tmp_path)
            passed_names = [c.name for c in result.passed]
            assert "not_on_main" in passed_names

    def test_on_main_warns(self, tmp_path: Path):
        """Should warn when on main branch."""
        (tmp_path / "buildlog").mkdir()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="main\n", stderr=""
            )
            result = verify_workflow(tmp_path)
            warning_names = [c.name for c in result.warnings]
            assert "not_on_main" in warning_names

    def test_on_master_warns(self, tmp_path: Path):
        """Should warn when on master branch."""
        (tmp_path / "buildlog").mkdir()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="master\n", stderr=""
            )
            result = verify_workflow(tmp_path)
            warning_names = [c.name for c in result.warnings]
            assert "not_on_main" in warning_names

    def test_ok_true_when_no_failures(self, tmp_path: Path):
        """ok should be True when there are warnings but no failures."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        (tmp_path / "CLAUDE.md").write_text(
            f"# Project\n\n{_WORKFLOW_SECTION_START}\nWorkflow\n{_WORKFLOW_SECTION_END}\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="feat/test\n", stderr=""
            )
            result = verify_workflow(tmp_path)
            # May have MCP warning, but no failures
            assert len(result.failed) == 0
            assert result.ok is True

    def test_ok_false_when_failures(self, tmp_path: Path):
        """ok should be False when there are failures."""
        result = verify_workflow(tmp_path)
        assert not result.ok

    def test_summary_format(self, tmp_path: Path):
        """Summary should include check counts."""
        (tmp_path / "buildlog").mkdir()
        result = verify_workflow(tmp_path)
        assert "/" in result.summary
        assert "passed" in result.summary

    def test_pre_commit_config_detection(self, tmp_path: Path):
        """Should detect branch protection in .pre-commit-config.yaml."""
        (tmp_path / "buildlog").mkdir()
        (tmp_path / ".pre-commit-config.yaml").write_text(
            "repos:\n  - repo: local\n    hooks:\n      - id: prevent-commit-to-main\n"
        )
        result = verify_workflow(tmp_path)
        passed_names = [c.name for c in result.passed]
        assert "branch_protection" in passed_names

    def test_git_hook_detection(self, tmp_path: Path):
        """Should detect branch protection in .git/hooks/pre-commit."""
        (tmp_path / "buildlog").mkdir()
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "pre-commit").write_text(
            "#!/bin/sh\nbranch=$(git branch --show-current)\n"
            'if [ "$branch" = "main" ]; then exit 1; fi\n'
        )
        result = verify_workflow(tmp_path)
        passed_names = [c.name for c in result.passed]
        assert "branch_protection" in passed_names


# =============================================================================
# Workflow section constant tests
# =============================================================================


class TestWorkflowSection:
    """Tests for the CLAUDE_MD_WORKFLOW_SECTION constant."""

    def test_has_markers(self):
        """Should include start and end markers."""
        assert _WORKFLOW_SECTION_START in CLAUDE_MD_WORKFLOW_SECTION
        assert _WORKFLOW_SECTION_END in CLAUDE_MD_WORKFLOW_SECTION

    def test_start_before_end(self):
        """Start marker should come before end marker."""
        start_idx = CLAUDE_MD_WORKFLOW_SECTION.index(_WORKFLOW_SECTION_START)
        end_idx = CLAUDE_MD_WORKFLOW_SECTION.index(_WORKFLOW_SECTION_END)
        assert start_idx < end_idx

    def test_contains_key_steps(self):
        """Should contain the 5 workflow steps."""
        assert "Issue + Branch" in CLAUDE_MD_WORKFLOW_SECTION
        assert "Implement with Ceremony" in CLAUDE_MD_WORKFLOW_SECTION
        assert "Gauntlet Review" in CLAUDE_MD_WORKFLOW_SECTION
        assert "Pull Request" in CLAUDE_MD_WORKFLOW_SECTION
        assert "Feedback Loop" in CLAUDE_MD_WORKFLOW_SECTION

    def test_contains_key_tools(self):
        """Should reference key tools."""
        assert "buildlog_commit" in CLAUDE_MD_WORKFLOW_SECTION
        assert "buildlog_entry_new" in CLAUDE_MD_WORKFLOW_SECTION
        assert "buildlog_gauntlet_loop" in CLAUDE_MD_WORKFLOW_SECTION
        assert "buildlog_log_reward" in CLAUDE_MD_WORKFLOW_SECTION

    def test_contains_branch_protection_note(self):
        """Should mention branch protection."""
        assert "Never commit directly to main" in CLAUDE_MD_WORKFLOW_SECTION


# =============================================================================
# OverviewResult workflow_ok integration
# =============================================================================


class TestOverviewWorkflowCheck:
    """Tests for workflow_ok field in OverviewResult."""

    def test_overview_has_workflow_fields(self, tmp_path: Path):
        """OverviewResult should have workflow_ok and workflow_issues."""
        from buildlog.core import get_overview

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        result = get_overview(buildlog_dir)
        assert hasattr(result, "workflow_ok")
        assert hasattr(result, "workflow_issues")

    def test_overview_workflow_issues_when_no_claude_md(self, tmp_path: Path):
        """Should report workflow issues when CLAUDE.md missing."""
        from buildlog.core import get_overview

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        result = get_overview(buildlog_dir)
        assert not result.workflow_ok
        assert result.workflow_issues is not None
        assert any("CLAUDE.md" in issue for issue in result.workflow_issues)

    def test_overview_workflow_ok_with_markers(self, tmp_path: Path):
        """Should be ok when CLAUDE.md has workflow markers."""
        from buildlog.core import get_overview

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        (tmp_path / "CLAUDE.md").write_text(
            f"# Project\n\n{_WORKFLOW_SECTION_START}\nWorkflow\n{_WORKFLOW_SECTION_END}\n"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="feat/test\n", stderr=""
            )
            result = get_overview(buildlog_dir)
            assert result.workflow_ok
            assert result.workflow_issues is None


# =============================================================================
# VerifyResult dataclass tests
# =============================================================================


class TestVerifyResult:
    """Tests for VerifyResult and VerifyCheck dataclasses."""

    def test_verify_check_fields(self):
        check = VerifyCheck(name="test", status="passed", message="All good")
        assert check.name == "test"
        assert check.status == "passed"
        assert check.message == "All good"

    def test_verify_result_serializable(self):
        """Should be serializable to dict/JSON."""
        from dataclasses import asdict

        result = VerifyResult(
            passed=[VerifyCheck("a", "passed", "ok")],
            warnings=[],
            failed=[],
            ok=True,
            summary="1/1 passed",
        )
        d = asdict(result)
        assert d["ok"] is True
        assert len(d["passed"]) == 1
        # Should be JSON-serializable
        json.dumps(d)


# =============================================================================
# CLI integration tests
# =============================================================================


class TestVerifyCLI:
    """CLI integration tests for `buildlog verify`."""

    def test_verify_basic_output(self, tmp_path: Path, monkeypatch):
        """Should show check results in human-readable format."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "buildlog").mkdir()
        (tmp_path / "buildlog" / ".buildlog").mkdir()
        (tmp_path / "CLAUDE.md").write_text(
            f"# Dev\n\n{_WORKFLOW_SECTION_START}\nW\n{_WORKFLOW_SECTION_END}\n"
        )

        runner = CliRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="feat/test\n", stderr=""
            )
            result = runner.invoke(main, ["verify"])

        assert result.exit_code == 0, result.output
        assert "[PASS]" in result.output
        assert "buildlog verify" in result.output

    def test_verify_json_output(self, tmp_path: Path, monkeypatch):
        """--json flag should produce valid JSON."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "buildlog").mkdir()

        runner = CliRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="feat/test\n", stderr=""
            )
            result = runner.invoke(main, ["verify", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "ok" in data
        assert "passed" in data
        assert "failed" in data

    def test_verify_fix_injects_workflow(self, tmp_path: Path, monkeypatch):
        """--fix should inject workflow section into CLAUDE.md."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "buildlog").mkdir()
        (tmp_path / "buildlog" / ".buildlog").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# My Project\n")

        runner = CliRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="feat/test\n", stderr=""
            )
            result = runner.invoke(main, ["verify", "--fix"])

        assert result.exit_code == 0, result.output
        assert "[FIX]" in result.output
        content = (tmp_path / "CLAUDE.md").read_text()
        assert _WORKFLOW_SECTION_START in content
        assert _WORKFLOW_SECTION_END in content

    def test_verify_fix_creates_claude_md(self, tmp_path: Path, monkeypatch):
        """--fix should create CLAUDE.md if it doesn't exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "buildlog").mkdir()
        (tmp_path / "buildlog" / ".buildlog").mkdir()

        runner = CliRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="feat/test\n", stderr=""
            )
            result = runner.invoke(main, ["verify", "--fix"])

        assert result.exit_code == 0, result.output
        assert "[FIX]" in result.output
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert _WORKFLOW_SECTION_START in content

    def test_verify_fix_is_idempotent(self, tmp_path: Path, monkeypatch):
        """Running --fix twice should not duplicate workflow section."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "buildlog").mkdir()
        (tmp_path / "buildlog" / ".buildlog").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# My Project\n")

        runner = CliRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="feat/test\n", stderr=""
            )
            runner.invoke(main, ["verify", "--fix"])
            result = runner.invoke(main, ["verify", "--fix"])

        assert result.exit_code == 0, result.output
        content = (tmp_path / "CLAUDE.md").read_text()
        assert content.count(_WORKFLOW_SECTION_START) == 1


class TestInitHooksIntegration:
    """CLI integration tests for init command's hook + verify path."""

    @pytest.fixture
    def git_project(self, tmp_path: Path, monkeypatch):
        """Create a minimal git repo for init testing."""
        monkeypatch.chdir(tmp_path)
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        # Need an initial commit so git rev-parse works
        (tmp_path / ".gitkeep").write_text("")
        subprocess.run(
            ["git", "add", ".gitkeep"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "init", "--no-verify"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "feat/test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "CLAUDE.md").write_text("# Dev Guidelines\n")
        return tmp_path

    # Capture real subprocess.run at class definition time (before any mock)
    _real_subprocess_run = staticmethod(subprocess.run)

    def _mock_copier(self, project_dir: Path):
        """Return a side_effect that only mocks copier, passes git through."""
        real_run = self._real_subprocess_run

        def side_effect(cmd, *args, **kwargs):
            if isinstance(cmd, list) and any("copier" in str(c) for c in cmd):
                (project_dir / "buildlog").mkdir(exist_ok=True)
                (project_dir / "buildlog" / ".buildlog").mkdir(exist_ok=True)
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="", stderr=""
                )
            return real_run(cmd, *args, **kwargs)

        return side_effect

    def test_init_installs_hooks(self, git_project: Path):
        """init should install git hooks."""
        runner = CliRunner()
        with patch("buildlog.cli.subprocess.run") as mock_run:
            mock_run.side_effect = self._mock_copier(git_project)
            result = runner.invoke(main, ["init", "--defaults", "--no-mcp"])

        assert result.exit_code == 0, result.output
        pre_commit = git_project / ".git" / "hooks" / "pre-commit"
        post_commit = git_project / ".git" / "hooks" / "post-commit"
        assert pre_commit.exists()
        assert post_commit.exists()

    def test_init_no_hooks_flag(self, git_project: Path):
        """init --no-hooks should skip hook installation."""
        runner = CliRunner()
        with patch("buildlog.cli.subprocess.run") as mock_run:
            mock_run.side_effect = self._mock_copier(git_project)
            result = runner.invoke(
                main, ["init", "--defaults", "--no-mcp", "--no-hooks"]
            )

        assert result.exit_code == 0, result.output
        pre_commit = git_project / ".git" / "hooks" / "pre-commit"
        assert not pre_commit.exists()

    def test_init_runs_verify(self, git_project: Path):
        """init should run verify_workflow and show warnings."""
        runner = CliRunner()
        with patch("buildlog.cli.subprocess.run") as mock_run:
            mock_run.side_effect = self._mock_copier(git_project)
            result = runner.invoke(main, ["init", "--defaults", "--no-mcp"])

        assert result.exit_code == 0, result.output
        assert "initialized" in result.output.lower()

    def test_init_injects_workflow_section(self, git_project: Path):
        """init should inject workflow section into CLAUDE.md."""
        runner = CliRunner()
        with patch("buildlog.cli.subprocess.run") as mock_run:
            mock_run.side_effect = self._mock_copier(git_project)
            result = runner.invoke(main, ["init", "--defaults", "--no-mcp"])

        assert result.exit_code == 0, result.output
        content = (git_project / "CLAUDE.md").read_text()
        assert _WORKFLOW_SECTION_START in content


class TestTraversalProtection:
    """Tests for symlink traversal protection in verify_workflow()."""

    def test_symlink_outside_home_warns(self, tmp_path: Path):
        """Should warn when ~/.claude.json is a symlink outside home."""
        (tmp_path / "buildlog").mkdir()

        # Create a fake home with a symlink escaping to /tmp
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        target = tmp_path / "evil" / "config.json"
        target.parent.mkdir()
        target.write_text('{"mcpServers": {}}')
        (fake_home / ".claude.json").symlink_to(target)

        with patch("pathlib.Path.home", return_value=fake_home):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="feat/test\n", stderr=""
                )
                result = verify_workflow(tmp_path)

        warning_messages = [w.message for w in result.warnings]
        assert any("outside home" in m for m in warning_messages)

    def test_normal_claude_json_works(self, tmp_path: Path):
        """Should read ~/.claude.json normally when no symlink escape."""
        (tmp_path / "buildlog").mkdir()

        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        (fake_home / ".claude.json").write_text('{"mcpServers": {"buildlog": {}}}')

        with patch("pathlib.Path.home", return_value=fake_home):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="feat/test\n", stderr=""
                )
                result = verify_workflow(tmp_path)

        passed_names = [c.name for c in result.passed]
        assert "mcp_registered" in passed_names
