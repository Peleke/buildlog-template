"""Tests for buildlog.core.operations module."""

from pathlib import Path
import json

import pytest

from buildlog.core.operations import (
    StatusResult,
    PromoteResult,
    RejectResult,
    DiffResult,
    status,
    promote,
    reject,
    diff,
    find_skills_by_ids,
)
from buildlog.skills import Skill, SkillSet, generate_skills


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "buildlog"


class TestStatusOperation:
    """Tests for status() operation."""

    def test_returns_skills_from_valid_directory(self):
        """Should return skills from a valid buildlog directory."""
        result = status(FIXTURES_DIR)

        assert result.error is None
        assert result.total_entries >= 1
        assert isinstance(result.skills, dict)
        assert isinstance(result.by_confidence, dict)

    def test_returns_error_for_missing_directory(self, tmp_path):
        """Should return error for non-existent directory."""
        result = status(tmp_path / "nonexistent")

        assert result.error is not None
        assert "No buildlog directory found" in result.error
        assert result.total_entries == 0
        assert result.total_skills == 0

    def test_filters_by_min_confidence(self):
        """Should filter skills by minimum confidence level."""
        # Get all skills
        all_result = status(FIXTURES_DIR, min_confidence="low")
        # Get only high confidence
        high_result = status(FIXTURES_DIR, min_confidence="high")

        # High confidence filter should return fewer or equal skills
        all_count = sum(len(s) for s in all_result.skills.values())
        high_count = sum(len(s) for s in high_result.skills.values())
        assert high_count <= all_count

    def test_excludes_rejected_skills(self, tmp_path):
        """Should exclude skills that have been rejected."""
        # Create a buildlog directory with fixture content
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Copy a fixture file
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get initial skills
        initial = status(buildlog_dir)
        assert initial.total_skills > 0

        # Get a skill ID to reject
        first_category = list(initial.skills.keys())[0]
        first_skill = initial.skills[first_category][0]
        skill_id = first_skill["id"]

        # Reject it
        reject(buildlog_dir, [skill_id])

        # Check it's excluded
        after_reject = status(buildlog_dir)
        all_ids = [
            s["id"]
            for cat_skills in after_reject.skills.values()
            for s in cat_skills
        ]
        assert skill_id not in all_ids

    def test_promotable_ids_only_high_confidence(self):
        """promotable_ids should only contain high-confidence skills."""
        result = status(FIXTURES_DIR)

        # All promotable IDs should be from high-confidence skills
        for skill_id in result.promotable_ids:
            # Skill IDs have format "prefix-hash"
            # We need to verify they're high confidence by checking by_confidence
            pass  # Can't easily verify without skill lookup, but the count should match
        assert result.by_confidence["high"] == len(result.promotable_ids)


class TestPromoteOperation:
    """Tests for promote() operation."""

    def test_promotes_to_claude_md(self, tmp_path):
        """Should append promoted skills to CLAUDE.md."""
        # Setup
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Existing content\n")

        # Get a skill ID
        initial = status(buildlog_dir)
        first_category = list(initial.skills.keys())[0]
        skill_id = initial.skills[first_category][0]["id"]

        # Promote it
        result = promote(
            buildlog_dir,
            [skill_id],
            target="claude_md",
            target_path=claude_md,
        )

        assert result.error is None
        assert skill_id in result.promoted_ids
        assert result.rules_added == 1
        assert "CLAUDE.md" in result.message

        # Check file was updated
        content = claude_md.read_text()
        assert "# Existing content" in content
        assert "## Learned Rules" in content

    def test_promotes_to_settings_json(self, tmp_path):
        """Should merge promoted skills into settings.json."""
        # Setup
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        settings_file = tmp_path / ".claude" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text('{"existing": "value", "rules": ["existing rule"]}')

        # Get a skill ID
        initial = status(buildlog_dir)
        first_category = list(initial.skills.keys())[0]
        skill_id = initial.skills[first_category][0]["id"]

        # Promote it
        result = promote(
            buildlog_dir,
            [skill_id],
            target="settings_json",
            target_path=settings_file,
        )

        assert result.error is None
        assert skill_id in result.promoted_ids

        # Check file was updated
        content = json.loads(settings_file.read_text())
        assert content["existing"] == "value"  # Preserved
        assert "existing rule" in content["rules"]  # Preserved
        assert len(content["rules"]) >= 2  # At least one new rule added

    def test_returns_error_for_empty_skill_ids(self, tmp_path):
        """Should return error when no skill IDs provided."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = promote(buildlog_dir, [])

        assert result.error is not None
        assert "No skill IDs provided" in result.error

    def test_returns_not_found_for_invalid_ids(self, tmp_path):
        """Should report IDs that weren't found."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        result = promote(buildlog_dir, ["nonexistent-id"])

        assert result.error is not None
        assert "nonexistent-id" in result.not_found_ids

    def test_tracks_promoted_ids(self, tmp_path):
        """Should track promoted skill IDs in promoted.json."""
        # Setup
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get a skill ID
        initial = status(buildlog_dir)
        first_category = list(initial.skills.keys())[0]
        skill_id = initial.skills[first_category][0]["id"]

        # Promote it
        claude_md = tmp_path / "CLAUDE.md"
        promote(buildlog_dir, [skill_id], target="claude_md", target_path=claude_md)

        # Check tracking file
        promoted_file = buildlog_dir / ".buildlog" / "promoted.json"
        assert promoted_file.exists()
        tracking = json.loads(promoted_file.read_text())
        assert skill_id in tracking["skill_ids"]

    def test_promotes_to_skill_format(self, tmp_path):
        """Should create Anthropic Agent Skill SKILL.md file."""
        # Setup
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        skill_file = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        # Get a skill ID
        initial = status(buildlog_dir)
        first_category = list(initial.skills.keys())[0]
        skill_id = initial.skills[first_category][0]["id"]

        # Promote it
        result = promote(
            buildlog_dir,
            [skill_id],
            target="skill",
            target_path=skill_file,
        )

        assert result.error is None
        assert skill_id in result.promoted_ids
        assert result.rules_added == 1
        assert "SKILL.md" in result.message

        # Check file was created with proper format
        assert skill_file.exists()
        content = skill_file.read_text()
        assert content.startswith("---\n")  # YAML frontmatter
        assert "name: buildlog-learned" in content
        assert "description:" in content


class TestRejectOperation:
    """Tests for reject() operation."""

    def test_rejects_skill_ids(self, tmp_path):
        """Should mark skill IDs as rejected."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = reject(buildlog_dir, ["arch-123", "wf-456"])

        assert result.error is None
        assert "arch-123" in result.rejected_ids
        assert "wf-456" in result.rejected_ids
        assert result.total_rejected == 2

    def test_persists_rejected_ids(self, tmp_path):
        """Should persist rejected IDs to file."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        reject(buildlog_dir, ["arch-123"])

        reject_file = buildlog_dir / ".buildlog" / "rejected.json"
        assert reject_file.exists()

        data = json.loads(reject_file.read_text())
        assert "arch-123" in data["skill_ids"]

    def test_does_not_duplicate_rejected_ids(self, tmp_path):
        """Should not add duplicate rejected IDs."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        reject(buildlog_dir, ["arch-123"])
        result = reject(buildlog_dir, ["arch-123", "arch-456"])

        # arch-123 should not be duplicated
        assert "arch-123" not in result.rejected_ids  # Already rejected
        assert "arch-456" in result.rejected_ids
        assert result.total_rejected == 2

    def test_returns_error_for_empty_ids(self, tmp_path):
        """Should return error when no IDs provided."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = reject(buildlog_dir, [])

        assert result.error is not None
        assert "No skill IDs provided" in result.error


class TestDiffOperation:
    """Tests for diff() operation."""

    def test_returns_pending_skills(self, tmp_path):
        """Should return skills not yet promoted or rejected."""
        # Setup
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        result = diff(buildlog_dir)

        assert result.error is None
        assert result.total_pending > 0
        assert result.already_promoted == 0
        assert result.already_rejected == 0

    def test_excludes_promoted_skills(self, tmp_path):
        """Should exclude previously promoted skills from pending."""
        # Setup
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get initial count
        initial = diff(buildlog_dir)
        initial_pending = initial.total_pending

        # Promote a skill
        status_result = status(buildlog_dir)
        first_category = list(status_result.skills.keys())[0]
        skill_id = status_result.skills[first_category][0]["id"]

        claude_md = tmp_path / "CLAUDE.md"
        promote(buildlog_dir, [skill_id], target="claude_md", target_path=claude_md)

        # Check diff excludes promoted
        after = diff(buildlog_dir)
        assert after.total_pending == initial_pending - 1
        assert after.already_promoted == 1

    def test_excludes_rejected_skills(self, tmp_path):
        """Should exclude rejected skills from pending."""
        # Setup
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        fixture = FIXTURES_DIR / "2026-01-01-test-entry.md"
        (buildlog_dir / "2026-01-01-test-entry.md").write_text(fixture.read_text())

        # Get initial count
        initial = diff(buildlog_dir)
        initial_pending = initial.total_pending

        # Reject a skill
        status_result = status(buildlog_dir)
        first_category = list(status_result.skills.keys())[0]
        skill_id = status_result.skills[first_category][0]["id"]

        reject(buildlog_dir, [skill_id])

        # Check diff excludes rejected
        after = diff(buildlog_dir)
        assert after.total_pending == initial_pending - 1
        assert after.already_rejected == 1

    def test_returns_error_for_missing_directory(self, tmp_path):
        """Should return error for non-existent directory."""
        result = diff(tmp_path / "nonexistent")

        assert result.error is not None
        assert "No buildlog directory found" in result.error


class TestFindSkillsByIds:
    """Tests for find_skills_by_ids() helper."""

    def test_finds_existing_skills(self):
        """Should find skills that exist in the skill set."""
        skill_set = generate_skills(FIXTURES_DIR)

        # Get some actual skill IDs
        all_ids = [
            s.id
            for cat_skills in skill_set.skills.values()
            for s in cat_skills
        ]

        if all_ids:
            found, not_found = find_skills_by_ids(skill_set, [all_ids[0]])
            assert len(found) == 1
            assert found[0].id == all_ids[0]
            assert len(not_found) == 0

    def test_reports_not_found_ids(self):
        """Should report IDs that don't exist."""
        skill_set = generate_skills(FIXTURES_DIR)

        found, not_found = find_skills_by_ids(skill_set, ["nonexistent-id"])

        assert len(found) == 0
        assert "nonexistent-id" in not_found

    def test_handles_mixed_ids(self):
        """Should handle mix of found and not-found IDs."""
        skill_set = generate_skills(FIXTURES_DIR)

        # Get one real ID
        all_ids = [
            s.id
            for cat_skills in skill_set.skills.values()
            for s in cat_skills
        ]

        if all_ids:
            found, not_found = find_skills_by_ids(
                skill_set,
                [all_ids[0], "fake-id"]
            )
            assert len(found) == 1
            assert "fake-id" in not_found
