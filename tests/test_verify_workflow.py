"""Tests for verify_workflow() and workflow section injection."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

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
