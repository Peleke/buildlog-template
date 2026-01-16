"""Tests for buildlog.mcp.tools module.

These tests verify the thin MCP wrappers correctly delegate to core operations.
"""

import json
from pathlib import Path

import pytest

from buildlog.mcp.tools import (
    buildlog_diff,
    buildlog_promote,
    buildlog_reject,
    buildlog_status,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "buildlog"


class TestBuildlogStatus:
    """Tests for buildlog_status MCP tool."""

    def test_returns_dict(self):
        """Should return a dictionary (serializable for MCP)."""
        result = buildlog_status(buildlog_dir=str(FIXTURES_DIR))
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        """Should have all expected keys from StatusResult."""
        result = buildlog_status(buildlog_dir=str(FIXTURES_DIR))

        assert "skills" in result
        assert "total_entries" in result
        assert "total_skills" in result
        assert "by_confidence" in result
        assert "promotable_ids" in result
        assert "error" in result

    def test_returns_error_for_missing_dir(self, tmp_path):
        """Should return error field for missing directory."""
        result = buildlog_status(buildlog_dir=str(tmp_path / "nonexistent"))

        assert result["error"] is not None
        assert "No buildlog directory" in result["error"]

    def test_accepts_min_confidence(self):
        """Should accept min_confidence parameter."""
        low = buildlog_status(buildlog_dir=str(FIXTURES_DIR), min_confidence="low")
        high = buildlog_status(buildlog_dir=str(FIXTURES_DIR), min_confidence="high")

        # Both should work
        assert low["error"] is None
        assert high["error"] is None


class TestBuildlogPromote:
    """Tests for buildlog_promote MCP tool."""

    def test_returns_dict(self, tmp_path):
        """Should return a dictionary."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get a skill ID
        status = buildlog_status(buildlog_dir=str(buildlog_dir))
        first_category = list(status["skills"].keys())[0]
        skill_id = status["skills"][first_category][0]["id"]

        result = buildlog_promote(
            skill_ids=[skill_id],
            target="claude_md",
            buildlog_dir=str(buildlog_dir),
        )

        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path):
        """Should have all expected keys from PromoteResult."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = buildlog_promote(
            skill_ids=["fake-id"],
            buildlog_dir=str(buildlog_dir),
        )

        assert "promoted_ids" in result
        assert "target" in result
        assert "rules_added" in result
        assert "not_found_ids" in result
        assert "message" in result
        assert "error" in result

    def test_accepts_target_parameter(self, tmp_path):
        """Should accept target parameter."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get a skill ID
        status = buildlog_status(buildlog_dir=str(buildlog_dir))
        first_category = list(status["skills"].keys())[0]
        skill_id = status["skills"][first_category][0]["id"]

        result = buildlog_promote(
            skill_ids=[skill_id],
            target="settings_json",
            buildlog_dir=str(buildlog_dir),
        )

        assert result["target"] == "settings_json"

    def test_accepts_skill_target(self, tmp_path):
        """Should accept target='skill' for Anthropic Agent Skills format."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get a skill ID
        status = buildlog_status(buildlog_dir=str(buildlog_dir))
        first_category = list(status["skills"].keys())[0]
        skill_id = status["skills"][first_category][0]["id"]

        result = buildlog_promote(
            skill_ids=[skill_id],
            target="skill",
            buildlog_dir=str(buildlog_dir),
        )

        assert result["target"] == "skill"
        assert result["error"] is None
        assert skill_id in result["promoted_ids"]

        # Verify SKILL.md was created
        skill_file = Path(".claude/skills/buildlog-learned/SKILL.md")
        assert skill_file.exists()
        content = skill_file.read_text()
        assert "---\n" in content  # YAML frontmatter
        assert "name: buildlog-learned" in content

        # Cleanup
        import shutil

        shutil.rmtree(".claude", ignore_errors=True)


class TestBuildlogReject:
    """Tests for buildlog_reject MCP tool."""

    def test_returns_dict(self, tmp_path):
        """Should return a dictionary."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = buildlog_reject(
            skill_ids=["arch-123"],
            buildlog_dir=str(buildlog_dir),
        )

        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path):
        """Should have all expected keys from RejectResult."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = buildlog_reject(
            skill_ids=["arch-123"],
            buildlog_dir=str(buildlog_dir),
        )

        assert "rejected_ids" in result
        assert "total_rejected" in result
        assert "error" in result

    def test_rejects_skill_ids(self, tmp_path):
        """Should reject provided skill IDs."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = buildlog_reject(
            skill_ids=["arch-123", "wf-456"],
            buildlog_dir=str(buildlog_dir),
        )

        assert "arch-123" in result["rejected_ids"]
        assert "wf-456" in result["rejected_ids"]
        assert result["total_rejected"] == 2


class TestBuildlogDiff:
    """Tests for buildlog_diff MCP tool."""

    def test_returns_dict(self, tmp_path):
        """Should return a dictionary."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        result = buildlog_diff(buildlog_dir=str(buildlog_dir))

        assert isinstance(result, dict)

    def test_has_expected_keys(self, tmp_path):
        """Should have all expected keys from DiffResult."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        result = buildlog_diff(buildlog_dir=str(buildlog_dir))

        assert "pending" in result
        assert "total_pending" in result
        assert "already_promoted" in result
        assert "already_rejected" in result
        assert "error" in result

    def test_returns_pending_skills(self, tmp_path):
        """Should return skills pending review."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy fixture
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        result = buildlog_diff(buildlog_dir=str(buildlog_dir))

        assert result["total_pending"] > 0
        assert result["already_promoted"] == 0
        assert result["already_rejected"] == 0
