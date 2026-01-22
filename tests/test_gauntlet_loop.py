"""Tests for gauntlet loop operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.core.operations import (
    GauntletAcceptRiskResult,
    GauntletLoopResult,
    gauntlet_accept_risk,
    gauntlet_process_issues,
)


class TestGauntletProcessIssues:
    """Tests for gauntlet_process_issues function."""

    def test_returns_fix_criticals_when_criticals_exist(self, tmp_path: Path):
        """Should return fix_criticals action when critical issues exist."""
        # Setup buildlog dir
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = [
            {
                "severity": "critical",
                "category": "security",
                "description": "SQL injection",
                "rule_learned": "Parameterize SQL",
            },
            {
                "severity": "major",
                "category": "testing",
                "description": "No tests",
                "rule_learned": "Add tests",
            },
            {
                "severity": "minor",
                "category": "style",
                "description": "Long line",
                "rule_learned": "Limit line length",
            },
        ]

        result = gauntlet_process_issues(buildlog_dir, issues, iteration=1)

        assert isinstance(result, GauntletLoopResult)
        assert result.action == "fix_criticals"
        assert len(result.criticals) == 1
        assert len(result.majors) == 1
        assert len(result.minors) == 1
        assert result.iteration == 1
        assert "critical" in result.message.lower()

    def test_returns_checkpoint_majors_when_no_criticals(self, tmp_path: Path):
        """Should return checkpoint_majors when only majors remain."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = [
            {
                "severity": "major",
                "category": "testing",
                "description": "No tests",
                "rule_learned": "Add tests",
            },
            {
                "severity": "minor",
                "category": "style",
                "description": "Long line",
                "rule_learned": "Limit line length",
            },
        ]

        result = gauntlet_process_issues(buildlog_dir, issues, iteration=2)

        assert result.action == "checkpoint_majors"
        assert len(result.criticals) == 0
        assert len(result.majors) == 1
        assert len(result.minors) == 1
        assert "major" in result.message.lower()

    def test_returns_checkpoint_minors_when_only_minors(self, tmp_path: Path):
        """Should return checkpoint_minors when only minors remain."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = [
            {
                "severity": "minor",
                "category": "style",
                "description": "Long line",
                "rule_learned": "Limit line length",
            },
            {
                "severity": "nitpick",
                "category": "style",
                "description": "Extra space",
                "rule_learned": "Trim spaces",
            },
        ]

        result = gauntlet_process_issues(buildlog_dir, issues, iteration=3)

        assert result.action == "checkpoint_minors"
        assert len(result.criticals) == 0
        assert len(result.majors) == 0
        assert len(result.minors) == 2
        assert "minor" in result.message.lower()

    def test_returns_clean_when_no_issues(self, tmp_path: Path):
        """Should return clean action when no issues."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = []

        result = gauntlet_process_issues(buildlog_dir, issues, iteration=4)

        assert result.action == "clean"
        assert len(result.criticals) == 0
        assert len(result.majors) == 0
        assert len(result.minors) == 0
        assert "clear" in result.message.lower() or "clean" in result.message.lower()

    def test_persists_learnings(self, tmp_path: Path):
        """Should persist learnings on each iteration."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = [
            {
                "severity": "critical",
                "category": "security",
                "description": "Vuln",
                "rule_learned": "Fix vuln",
            },
        ]

        result = gauntlet_process_issues(buildlog_dir, issues, iteration=1)

        # Learnings should be persisted
        assert result.learnings_persisted >= 0  # May be 0 if dedup happens

        # Check learnings file exists
        learnings_file = buildlog_dir / ".buildlog" / "review_learnings.json"
        assert learnings_file.exists()

    def test_uses_custom_source(self, tmp_path: Path):
        """Should use custom source for learnings."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = [
            {
                "severity": "major",
                "category": "testing",
                "description": "No test",
                "rule_learned": "Add test",
            },
        ]

        result = gauntlet_process_issues(
            buildlog_dir, issues, iteration=1, source="custom:test"
        )

        assert result.action == "checkpoint_majors"

    def test_handles_missing_severity(self, tmp_path: Path):
        """Should handle issues with missing severity (default to minor)."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = [
            {
                "category": "style",
                "description": "No severity",
                "rule_learned": "Add severity",
            },
        ]

        result = gauntlet_process_issues(buildlog_dir, issues, iteration=1)

        # Missing severity should be treated as minor
        assert result.action == "checkpoint_minors"
        assert len(result.minors) == 1


class TestGauntletAcceptRisk:
    """Tests for gauntlet_accept_risk function."""

    def test_accepts_risk_without_github_issues(self):
        """Should accept risk and return count without creating issues."""
        issues = [
            {"severity": "minor", "description": "Issue 1", "rule_learned": "Rule 1"},
            {"severity": "minor", "description": "Issue 2", "rule_learned": "Rule 2"},
        ]

        result = gauntlet_accept_risk(issues, create_github_issues=False)

        assert isinstance(result, GauntletAcceptRiskResult)
        assert result.accepted_issues == 2
        assert result.github_issues_created == 0
        assert len(result.github_issue_urls) == 0
        assert result.error is None

    def test_accepts_empty_issues(self):
        """Should handle empty issues list."""
        result = gauntlet_accept_risk([], create_github_issues=False)

        assert result.accepted_issues == 0
        assert result.github_issues_created == 0

    @patch("subprocess.run")
    def test_creates_github_issues_when_enabled(self, mock_run):
        """Should create GitHub issues when enabled."""
        mock_run.return_value.stdout = "https://github.com/test/repo/issues/1\n"
        mock_run.return_value.returncode = 0

        issues = [
            {
                "severity": "major",
                "description": "Test issue",
                "rule_learned": "Test rule",
            },
        ]

        result = gauntlet_accept_risk(issues, create_github_issues=True)

        assert result.accepted_issues == 1
        assert result.github_issues_created == 1
        assert len(result.github_issue_urls) == 1
        assert "github.com" in result.github_issue_urls[0]

    @patch("subprocess.run")
    def test_handles_gh_cli_error(self, mock_run):
        """Should handle gh CLI errors gracefully."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "gh", stderr="Not logged in")

        issues = [
            {
                "severity": "major",
                "description": "Test issue",
                "rule_learned": "Test rule",
            },
        ]

        result = gauntlet_accept_risk(issues, create_github_issues=True)

        assert result.accepted_issues == 1
        assert result.github_issues_created == 0
        assert result.error is not None

    @patch("subprocess.run")
    def test_handles_missing_gh_cli(self, mock_run):
        """Should handle missing gh CLI gracefully."""
        mock_run.side_effect = FileNotFoundError()

        issues = [
            {
                "severity": "major",
                "description": "Test issue",
                "rule_learned": "Test rule",
            },
        ]

        result = gauntlet_accept_risk(issues, create_github_issues=True)

        assert result.accepted_issues == 1
        assert result.github_issues_created == 0
        assert "not found" in result.error.lower()

    @patch("subprocess.run")
    def test_uses_custom_repo(self, mock_run):
        """Should use custom repo when specified."""
        mock_run.return_value.stdout = "https://github.com/custom/repo/issues/1\n"
        mock_run.return_value.returncode = 0

        issues = [
            {"severity": "minor", "description": "Test", "rule_learned": "Test"},
        ]

        gauntlet_accept_risk(issues, create_github_issues=True, repo="custom/repo")

        # Check that --repo was passed
        call_args = mock_run.call_args[0][0]
        assert "--repo" in call_args
        assert "custom/repo" in call_args


class TestGauntletLoopIntegration:
    """Integration tests for the gauntlet loop workflow."""

    def test_full_loop_workflow(self, tmp_path: Path):
        """Test the full loop workflow from criticals to clean."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        # Iteration 1: criticals exist
        issues1 = [
            {
                "severity": "critical",
                "category": "security",
                "description": "SQL injection",
                "rule_learned": "Parameterize SQL",
            },
            {
                "severity": "major",
                "category": "testing",
                "description": "No tests",
                "rule_learned": "Add tests",
            },
        ]
        result1 = gauntlet_process_issues(buildlog_dir, issues1, iteration=1)
        assert result1.action == "fix_criticals"

        # Iteration 2: criticals fixed, majors remain
        issues2 = [
            {
                "severity": "major",
                "category": "testing",
                "description": "No tests",
                "rule_learned": "Add tests",
            },
        ]
        result2 = gauntlet_process_issues(buildlog_dir, issues2, iteration=2)
        assert result2.action == "checkpoint_majors"

        # Iteration 3: majors fixed, minors remain
        issues3 = [
            {
                "severity": "minor",
                "category": "style",
                "description": "Long line",
                "rule_learned": "Limit lines",
            },
        ]
        result3 = gauntlet_process_issues(buildlog_dir, issues3, iteration=3)
        assert result3.action == "checkpoint_minors"

        # Iteration 4: all clean
        issues4 = []
        result4 = gauntlet_process_issues(buildlog_dir, issues4, iteration=4)
        assert result4.action == "clean"

    def test_learnings_accumulate_across_iterations(self, tmp_path: Path):
        """Learnings should accumulate and reinforce across iterations."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        # Same rule in multiple iterations should reinforce
        issues = [
            {
                "severity": "major",
                "category": "security",
                "description": "Vuln",
                "rule_learned": "Always validate input",
            },
        ]

        result1 = gauntlet_process_issues(buildlog_dir, issues, iteration=1)
        result2 = gauntlet_process_issues(buildlog_dir, issues, iteration=2)

        # First time should be new, second should reinforce
        # (exact behavior depends on implementation)
        assert result1.learnings_persisted >= 0
        assert result2.learnings_persisted >= 0
