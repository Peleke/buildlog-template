"""Tests for accepted risk local persistence."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.core.operations import (
    AcceptedRisk,
    GauntletAcceptRiskResult,
    _get_accepted_risk_path,
    _persist_accepted_risk,
    gauntlet_accept_risk,
)


@pytest.fixture
def buildlog_dir(tmp_path):
    """Create a temporary buildlog directory."""
    d = tmp_path / "buildlog"
    d.mkdir()
    return d


class TestPersistAcceptedRisk:
    """Tests for _persist_accepted_risk helper."""

    def test_creates_jsonl_with_correct_format(self, buildlog_dir):
        issue = {
            "severity": "minor",
            "description": "test issue",
            "rule_learned": "test rule",
        }
        record = _persist_accepted_risk(buildlog_dir, issue)

        assert record.id.startswith("risk-")
        assert record.issue == issue
        assert record.timestamp

        risk_path = _get_accepted_risk_path(buildlog_dir)
        assert risk_path.exists()

        line = risk_path.read_text().strip()
        data = json.loads(line)
        assert data["id"] == record.id
        assert data["issue"] == issue

    def test_session_context_captured(self, buildlog_dir):
        issue = {"severity": "major", "description": "ctx test"}
        record = _persist_accepted_risk(
            buildlog_dir,
            issue,
            session_id="session-123",
            iteration=3,
            target="src/",
        )

        assert record.session_id == "session-123"
        assert record.iteration == 3
        assert record.target == "src/"

        data = json.loads(_get_accepted_risk_path(buildlog_dir).read_text().strip())
        assert data["session_id"] == "session-123"
        assert data["iteration"] == 3
        assert data["target"] == "src/"

    def test_github_url_included(self, buildlog_dir):
        issue = {"severity": "minor", "description": "gh test"}
        record = _persist_accepted_risk(
            buildlog_dir,
            issue,
            github_issue_url="https://github.com/org/repo/issues/42",
        )

        assert record.github_issue_url == "https://github.com/org/repo/issues/42"
        data = json.loads(_get_accepted_risk_path(buildlog_dir).read_text().strip())
        assert data["github_issue_url"] == "https://github.com/org/repo/issues/42"

    def test_multiple_risks_append(self, buildlog_dir):
        for i in range(3):
            _persist_accepted_risk(
                buildlog_dir, {"severity": "minor", "description": f"issue {i}"}
            )

        lines = _get_accepted_risk_path(buildlog_dir).read_text().strip().split("\n")
        assert len(lines) == 3
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["issue"]["description"] == f"issue {i}"

    def test_creates_missing_directory(self, tmp_path):
        buildlog_dir = tmp_path / "new_buildlog"
        # Don't create it — _persist_accepted_risk should handle it
        issue = {"severity": "minor", "description": "auto dir"}
        record = _persist_accepted_risk(buildlog_dir, issue)

        assert _get_accepted_risk_path(buildlog_dir).exists()
        assert record.id.startswith("risk-")


class TestGauntletAcceptRisk:
    """Tests for gauntlet_accept_risk with local persistence."""

    def test_persists_even_when_github_disabled(self, buildlog_dir):
        issues = [
            {"severity": "minor", "description": "issue 1"},
            {"severity": "minor", "description": "issue 2"},
        ]
        result = gauntlet_accept_risk(
            remaining_issues=issues,
            create_github_issues=False,
            buildlog_dir=buildlog_dir,
        )

        assert result.accepted_issues == 2
        assert result.github_issues_created == 0

        lines = _get_accepted_risk_path(buildlog_dir).read_text().strip().split("\n")
        assert len(lines) == 2

    @patch("subprocess.run")
    def test_persists_even_when_github_fails(self, mock_run, buildlog_dir):
        import subprocess

        mock_run.side_effect = FileNotFoundError("gh not found")

        issues = [{"severity": "minor", "description": "issue 1"}]
        result = gauntlet_accept_risk(
            remaining_issues=issues,
            create_github_issues=True,
            buildlog_dir=buildlog_dir,
        )

        assert result.error is not None
        assert result.github_issues_created == 0

        # Local persistence still happened
        lines = _get_accepted_risk_path(buildlog_dir).read_text().strip().split("\n")
        assert len(lines) == 1

    @patch("subprocess.run")
    def test_github_url_included_in_local_record(self, mock_run, buildlog_dir):
        mock_result = type(
            "Result",
            (),
            {"stdout": "https://github.com/org/repo/issues/99\n", "returncode": 0},
        )()
        mock_run.return_value = mock_result

        issues = [{"severity": "minor", "description": "issue 1"}]
        result = gauntlet_accept_risk(
            remaining_issues=issues,
            create_github_issues=True,
            buildlog_dir=buildlog_dir,
        )

        assert result.github_issues_created == 1
        data = json.loads(_get_accepted_risk_path(buildlog_dir).read_text().strip())
        assert data["github_issue_url"] == "https://github.com/org/repo/issues/99"

    def test_session_context_passed_through(self, buildlog_dir):
        issues = [{"severity": "minor", "description": "ctx issue"}]
        gauntlet_accept_risk(
            remaining_issues=issues,
            create_github_issues=False,
            buildlog_dir=buildlog_dir,
            session_id="sess-1",
            iteration=5,
            target="src/api.py",
        )

        data = json.loads(_get_accepted_risk_path(buildlog_dir).read_text().strip())
        assert data["session_id"] == "sess-1"
        assert data["iteration"] == 5
        assert data["target"] == "src/api.py"


class TestAcceptedRiskDataclass:
    """Tests for AcceptedRisk dataclass."""

    def test_to_dict_minimal(self):
        risk = AcceptedRisk(
            id="risk-1", timestamp="2026-01-31T00:00:00Z", issue={"a": 1}
        )
        d = risk.to_dict()
        assert d == {
            "id": "risk-1",
            "timestamp": "2026-01-31T00:00:00Z",
            "issue": {"a": 1},
        }

    def test_to_dict_full(self):
        risk = AcceptedRisk(
            id="risk-1",
            timestamp="2026-01-31T00:00:00Z",
            issue={"a": 1},
            session_id="s1",
            iteration=2,
            target="src/",
            github_issue_url="https://example.com/1",
        )
        d = risk.to_dict()
        assert d["session_id"] == "s1"
        assert d["iteration"] == 2
        assert d["target"] == "src/"
        assert d["github_issue_url"] == "https://example.com/1"
