"""Tests for bug fixes identified in review."""

from pathlib import Path
import json

import pytest

from buildlog.core.operations import status, promote, reject
from buildlog.render.claude_md import ClaudeMdRenderer
from buildlog.render.settings_json import SettingsJsonRenderer
from buildlog.mcp.tools import _validate_skill_ids, buildlog_promote, buildlog_reject
from buildlog.skills import Skill


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "buildlog"


def make_skill(id: str = "arch-123", rule: str = "Test rule", confidence: str = "high") -> Skill:
    """Factory for test skills."""
    return Skill(
        id=id,
        category="architectural",
        rule=rule,
        frequency=3,
        confidence=confidence,
        sources=["test.md"],
        tags=[],
    )


class TestTotalSkillsCalculation:
    """Tests for correct total_skills calculation in status()."""

    def test_total_skills_with_stale_rejected_ids(self, tmp_path):
        """total_skills should not be affected by stale rejected IDs."""
        # Setup buildlog
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Add a stale rejected ID (doesn't exist in current skills)
        reject_file = buildlog_dir / ".buildlog" / "rejected.json"
        reject_file.parent.mkdir(parents=True)
        reject_file.write_text(json.dumps({
            "skill_ids": ["stale-nonexistent-id-12345"],
            "rejected_at": {},
        }))

        # Get status
        result = status(buildlog_dir)

        # total_skills should equal sum of by_confidence (actual skills found)
        assert result.total_skills == sum(result.by_confidence.values())
        # Should NOT have subtracted the stale ID
        assert result.error is None


class TestBuildlogMetadataAccumulation:
    """Tests for _buildlog metadata accumulation in settings.json."""

    def test_metadata_accumulates_across_promotions(self, tmp_path):
        """_buildlog.promoted_skill_ids should accumulate, not replace."""
        settings_file = tmp_path / "settings.json"

        renderer = SettingsJsonRenderer(
            path=settings_file,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )

        # First promotion
        skill1 = make_skill(id="arch-111", rule="Rule one")
        renderer.render([skill1])

        data1 = json.loads(settings_file.read_text())
        assert "arch-111" in data1["_buildlog"]["promoted_skill_ids"]

        # Second promotion (different skill)
        skill2 = make_skill(id="arch-222", rule="Rule two")
        renderer.render([skill2])

        data2 = json.loads(settings_file.read_text())
        # Both should be present
        assert "arch-111" in data2["_buildlog"]["promoted_skill_ids"]
        assert "arch-222" in data2["_buildlog"]["promoted_skill_ids"]


class TestCorruptJsonHandling:
    """Tests for handling corrupt JSON files."""

    def test_claude_md_renderer_handles_corrupt_tracking(self, tmp_path):
        """ClaudeMdRenderer should handle corrupt promoted.json gracefully."""
        claude_md = tmp_path / "CLAUDE.md"
        tracking_path = tmp_path / ".buildlog" / "promoted.json"
        tracking_path.parent.mkdir(parents=True)
        tracking_path.write_text("not valid json {{{")

        renderer = ClaudeMdRenderer(path=claude_md, tracking_path=tracking_path)
        skill = make_skill()

        # Should not raise
        result = renderer.render([skill])

        assert "rules" in result
        # Should have created valid tracking file
        data = json.loads(tracking_path.read_text())
        assert skill.id in data["skill_ids"]

    def test_settings_json_renderer_handles_corrupt_tracking(self, tmp_path):
        """SettingsJsonRenderer should handle corrupt promoted.json gracefully."""
        settings_file = tmp_path / "settings.json"
        tracking_path = tmp_path / ".buildlog" / "promoted.json"
        tracking_path.parent.mkdir(parents=True)
        tracking_path.write_text("corrupted content")

        renderer = SettingsJsonRenderer(path=settings_file, tracking_path=tracking_path)
        skill = make_skill()

        # Should not raise
        result = renderer.render([skill])

        assert "rules" in result
        # Should have created valid tracking file
        data = json.loads(tracking_path.read_text())
        assert skill.id in data["skill_ids"]

    def test_operations_handles_corrupt_rejected_json(self, tmp_path):
        """Core operations should handle corrupt rejected.json."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Create corrupt rejected.json
        reject_file = buildlog_dir / ".buildlog" / "rejected.json"
        reject_file.parent.mkdir(parents=True)
        reject_file.write_text("{invalid json")

        # reject() should recover gracefully
        result = reject(buildlog_dir, ["arch-123"])

        assert result.error is None
        assert "arch-123" in result.rejected_ids

        # File should now be valid
        data = json.loads(reject_file.read_text())
        assert "arch-123" in data["skill_ids"]


class TestInputValidation:
    """Tests for input validation in MCP tools."""

    def test_validate_skill_ids_filters_empty_strings(self):
        """Should filter out empty strings."""
        result = _validate_skill_ids(["arch-123", "", "wf-456"])
        assert result == ["arch-123", "wf-456"]

    def test_validate_skill_ids_filters_whitespace(self):
        """Should filter out whitespace-only strings."""
        result = _validate_skill_ids(["arch-123", "   ", "\t", "wf-456"])
        assert result == ["arch-123", "wf-456"]

    def test_validate_skill_ids_filters_none(self):
        """Should filter out None values."""
        result = _validate_skill_ids(["arch-123", None, "wf-456"])  # type: ignore
        assert result == ["arch-123", "wf-456"]

    def test_validate_skill_ids_filters_non_strings(self):
        """Should filter out non-string values."""
        result = _validate_skill_ids(["arch-123", 123, ["list"], "wf-456"])  # type: ignore
        assert result == ["arch-123", "wf-456"]

    def test_buildlog_promote_validates_input(self, tmp_path):
        """buildlog_promote should validate skill_ids."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Empty strings should be filtered, resulting in error
        result = buildlog_promote(
            skill_ids=["", "   "],
            buildlog_dir=str(buildlog_dir),
        )

        assert result["error"] == "No skill IDs provided"

    def test_buildlog_reject_validates_input(self, tmp_path):
        """buildlog_reject should validate skill_ids."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Empty strings should be filtered, resulting in error
        result = buildlog_reject(
            skill_ids=["", None],  # type: ignore
            buildlog_dir=str(buildlog_dir),
        )

        assert result["error"] == "No skill IDs provided"
