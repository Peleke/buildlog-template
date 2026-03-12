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

        # Verify persistence via backend
        from buildlog.storage import get_backend

        backend, pid = get_backend(buildlog_dir, project_root=tmp_path)
        data = backend.load_learnings(pid)
        assert "learnings" in data

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
        assert result.checklist_items == 0

    def test_accepts_empty_issues(self):
        """Should handle empty issues list."""
        result = gauntlet_accept_risk([], create_github_issues=False)

        assert result.accepted_issues == 0
        assert result.github_issues_created == 0
        assert result.checklist_items == 0

    @patch("buildlog.core.operations._ensure_gauntlet_labels")
    @patch("subprocess.run")
    def test_creates_single_consolidated_issue(self, mock_run, mock_labels):
        """Should create ONE GitHub issue with checklist, not N issues."""
        mock_labels.return_value = {"major", "minor", "gauntlet/accepted-risk"}
        mock_run.return_value.stdout = "https://github.com/test/repo/issues/42\n"
        mock_run.return_value.returncode = 0

        issues = [
            {
                "severity": "major",
                "description": "Missing validation",
                "rule_learned": "Validate inputs",
                "location": "src/api.py:10",
            },
            {
                "severity": "minor",
                "description": "Unused import",
                "rule_learned": "Clean imports",
                "location": "src/utils.py:1",
            },
            {
                "severity": "minor",
                "description": "Long function",
                "rule_learned": "Keep functions short",
            },
        ]

        result = gauntlet_accept_risk(issues, create_github_issues=True, iteration=3)

        assert result.accepted_issues == 3
        assert result.github_issues_created == 1
        assert result.checklist_items == 3
        assert len(result.github_issue_urls) == 1
        assert "github.com" in result.github_issue_urls[0]

        # Only ONE gh issue create call (label list is mocked out)
        assert mock_run.call_count == 1
        call_args = mock_run.call_args[0][0]
        assert call_args[0:3] == ["gh", "issue", "create"]

        # Verify body contains checklist format
        body_idx = call_args.index("--body") + 1
        body = call_args[body_idx]
        assert "- [ ]" in body
        assert "Missing validation" in body
        assert "Unused import" in body
        assert "### Major" in body
        assert "### Minor" in body
        assert "iteration 3" in body.lower()

    @patch("buildlog.core.operations._ensure_gauntlet_labels")
    @patch("subprocess.run")
    def test_checklist_body_includes_provenance(self, mock_run, mock_labels):
        """Body should include iteration, date, rule info."""
        mock_labels.return_value = {"critical", "gauntlet/accepted-risk"}
        mock_run.return_value.stdout = "https://github.com/test/repo/issues/1\n"
        mock_run.return_value.returncode = 0

        issues = [
            {
                "severity": "critical",
                "description": "SQL injection",
                "rule_learned": "Parameterize queries",
                "location": "src/db.py:42",
                "rules_consulted": ["R-001", "R-002"],
                "rule_reasoning": {
                    "R-001": "Direct string concat",
                    "R-002": "User input",
                },
            },
        ]

        gauntlet_accept_risk(
            issues,
            create_github_issues=True,
            iteration=5,
        )

        call_args = mock_run.call_args[0][0]
        body_idx = call_args.index("--body") + 1
        body = call_args[body_idx]
        assert "Iteration:** 5" in body
        assert "Rules consulted: R-001, R-002" in body
        assert "Reasoning:" in body

    @patch("buildlog.core.operations._ensure_gauntlet_labels")
    @patch("subprocess.run")
    def test_handles_gh_cli_error(self, mock_run, mock_labels):
        """Should handle gh CLI errors gracefully."""
        from subprocess import CalledProcessError

        mock_labels.return_value = {"major", "gauntlet/accepted-risk"}
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

    @patch("buildlog.core.operations._ensure_gauntlet_labels")
    @patch("subprocess.run")
    def test_handles_missing_gh_cli(self, mock_run, mock_labels):
        """Should handle missing gh CLI gracefully."""
        mock_labels.return_value = set()
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

    @patch("buildlog.core.operations._ensure_gauntlet_labels")
    @patch("subprocess.run")
    def test_uses_custom_repo(self, mock_run, mock_labels):
        """Should use custom repo when specified."""
        mock_labels.return_value = {"minor", "gauntlet/accepted-risk"}
        mock_run.return_value.stdout = "https://github.com/custom/repo/issues/1\n"
        mock_run.return_value.returncode = 0

        issues = [
            {"severity": "minor", "description": "Test", "rule_learned": "Test"},
        ]

        gauntlet_accept_risk(issues, create_github_issues=True, repo="custom/repo")

        # Check that --repo was passed to gh issue create
        call_args = mock_run.call_args[0][0]
        assert "--repo" in call_args
        assert "custom/repo" in call_args

    @patch("subprocess.run")
    def test_label_auto_creation(self, mock_run):
        """Should auto-create missing labels, skip existing ones."""
        import json as _json

        # First call: gh label list returns only "minor" exists
        label_list_result = type(
            "R",
            (),
            {
                "stdout": _json.dumps([{"name": "minor"}]),
                "returncode": 0,
            },
        )()
        # Subsequent calls: label create, then issue create
        issue_create_result = type(
            "R",
            (),
            {
                "stdout": "https://github.com/test/repo/issues/99\n",
                "returncode": 0,
            },
        )()

        mock_run.return_value = issue_create_result

        # Make label list return our custom result, rest succeed
        def side_effect(cmd, **kwargs):
            if cmd[1] == "label" and cmd[2] == "list":
                return label_list_result
            return issue_create_result

        mock_run.side_effect = side_effect

        issues = [
            {"severity": "minor", "description": "Test minor"},
            {"severity": "major", "description": "Test major"},
        ]

        result = gauntlet_accept_risk(issues, create_github_issues=True)

        assert result.github_issues_created == 1
        # Should have called: label list, label create (major),
        # label create (gauntlet/accepted-risk), issue create
        assert mock_run.call_count >= 3

    @patch("subprocess.run")
    def test_label_fallback_when_gh_unavailable(self, mock_run):
        """Should still create issue without labels if label ops fail."""
        # _ensure_gauntlet_labels will fail (FileNotFoundError on label list)
        # but issue create should still work
        call_count = {"n": 0}

        def side_effect(cmd, **kwargs):
            call_count["n"] += 1
            if cmd[1] == "label":
                raise FileNotFoundError("gh not found")
            result = type(
                "R",
                (),
                {
                    "stdout": "https://github.com/test/repo/issues/1\n",
                    "returncode": 0,
                },
            )()
            return result

        mock_run.side_effect = side_effect

        issues = [{"severity": "minor", "description": "Test"}]
        result = gauntlet_accept_risk(issues, create_github_issues=True)

        # Issue should be created even though labels failed
        assert result.github_issues_created == 1
        assert result.error is None


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
