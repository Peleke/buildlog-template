"""Tests for buildlog.core.operations module."""

import json
from pathlib import Path

import pytest

from buildlog.core.operations import (
    DiffResult,
    LogRewardResult,
    Mistake,
    PromoteResult,
    RejectResult,
    RewardEvent,
    RewardSummary,
    StatusResult,
    diff,
    find_skills_by_ids,
    get_rewards,
    learn_from_review,
    log_mistake,
    log_reward,
    promote,
    reject,
    start_session,
    status,
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
            s["id"] for cat_skills in after_reject.skills.values() for s in cat_skills
        ]
        assert skill_id not in all_ids

    def test_promotable_ids_only_high_confidence(self):
        """promotable_ids should only contain high-confidence skills."""
        result = status(FIXTURES_DIR)

        # The fixture may or may not have high-confidence skills
        # What we're testing is that the count matches and all promotable IDs are high confidence

        # Count should always match
        assert result.by_confidence["high"] == len(result.promotable_ids)

        # If there are any high-confidence skills, verify the mapping
        if result.promotable_ids:
            high_conf_ids = set()
            for cat_skills in result.skills.values():
                for skill in cat_skills:
                    if skill.get("confidence") == "high":
                        high_conf_ids.add(skill["id"])

            for skill_id in result.promotable_ids:
                assert (
                    skill_id in high_conf_ids
                ), f"{skill_id} not in high-confidence set"

        # Also verify that low-confidence skills are NOT in promotable_ids
        for cat_skills in result.skills.values():
            for skill in cat_skills:
                if skill.get("confidence") in ("low", "medium"):
                    assert (
                        skill["id"] not in result.promotable_ids
                    ), f"Non-high confidence skill {skill['id']} should not be promotable"


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
        """Should persist rejected IDs across calls."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        reject(buildlog_dir, ["arch-123"])

        # Verify persistence: second reject should accumulate
        result2 = reject(buildlog_dir, ["wf-456"])
        assert "arch-123" in result2.rejected_ids or result2.total_rejected == 2
        assert result2.total_rejected == 2

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
        all_ids = [s.id for cat_skills in skill_set.skills.values() for s in cat_skills]

        # Fixture must have skills - fail fast if precondition not met
        assert all_ids, "Fixture should contain skills for this test"

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
        all_ids = [s.id for cat_skills in skill_set.skills.values() for s in cat_skills]

        # Fixture must have skills - fail fast if precondition not met
        assert all_ids, "Fixture should contain skills for this test"

        found, not_found = find_skills_by_ids(skill_set, [all_ids[0], "fake-id"])
        assert len(found) == 1
        assert "fake-id" in not_found


class TestRewardLogging:
    """Tests for reward signal logging operations."""

    def test_log_accepted_reward(self, tmp_path):
        """Should log an accepted reward with reward_value=1.0."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = log_reward(buildlog_dir, outcome="accepted")

        assert result.error is None
        assert result.reward_value == 1.0
        assert result.total_events == 1
        assert result.reward_id.startswith("rew-")

    def test_log_rejected_reward(self, tmp_path):
        """Should log a rejected reward with reward_value=0.0."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = log_reward(buildlog_dir, outcome="rejected")

        assert result.error is None
        assert result.reward_value == 0.0
        assert result.total_events == 1

    def test_log_revision_reward_with_distance(self, tmp_path):
        """Should compute reward_value from revision_distance."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = log_reward(
            buildlog_dir,
            outcome="revision",
            revision_distance=0.3,
        )

        assert result.error is None
        assert result.reward_value == pytest.approx(0.7, rel=0.01)
        assert result.total_events == 1

    def test_log_revision_reward_default_distance(self, tmp_path):
        """Should use default distance of 0.5 for revision without distance."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = log_reward(buildlog_dir, outcome="revision")

        assert result.reward_value == pytest.approx(0.5, rel=0.01)

    def test_appends_to_existing_file(self, tmp_path):
        """Should append to existing reward_events.jsonl."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        log_reward(buildlog_dir, outcome="accepted")
        result = log_reward(buildlog_dir, outcome="rejected")

        assert result.total_events == 2

    def test_stores_rules_active(self, tmp_path):
        """Should store rules_active in the event."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        log_reward(
            buildlog_dir,
            outcome="accepted",
            rules_active=["arch-123", "wf-456"],
        )

        summary = get_rewards(buildlog_dir)
        assert len(summary.events) == 1
        assert "arch-123" in summary.events[0].rules_active
        assert "wf-456" in summary.events[0].rules_active

    def test_stores_error_class(self, tmp_path):
        """Should store error_class in the event."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        log_reward(
            buildlog_dir,
            outcome="revision",
            error_class="missing_test",
        )

        summary = get_rewards(buildlog_dir)
        assert summary.events[0].error_class == "missing_test"

    def test_stores_notes(self, tmp_path):
        """Should store notes in the event."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        log_reward(
            buildlog_dir,
            outcome="rejected",
            notes="Completely wrong approach",
        )

        summary = get_rewards(buildlog_dir)
        assert summary.events[0].notes == "Completely wrong approach"

    def test_creates_buildlog_directory(self, tmp_path):
        """Should persist reward even without .buildlog dir."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        log_reward(buildlog_dir, outcome="accepted")

        result = get_rewards(buildlog_dir)
        assert result.total_events == 1


class TestGetRewards:
    """Tests for get_rewards() operation."""

    def test_returns_empty_for_no_events(self, tmp_path):
        """Should return empty summary when no events exist."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        summary = get_rewards(buildlog_dir)

        assert summary.total_events == 0
        assert summary.accepted == 0
        assert summary.revisions == 0
        assert summary.rejected == 0
        assert summary.mean_reward == 0.0
        assert summary.events == []

    def test_calculates_correct_statistics(self, tmp_path):
        """Should calculate correct statistics from events."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Log various outcomes
        log_reward(buildlog_dir, outcome="accepted")  # 1.0
        log_reward(buildlog_dir, outcome="accepted")  # 1.0
        log_reward(buildlog_dir, outcome="revision", revision_distance=0.4)  # 0.6
        log_reward(buildlog_dir, outcome="rejected")  # 0.0

        summary = get_rewards(buildlog_dir)

        assert summary.total_events == 4
        assert summary.accepted == 2
        assert summary.revisions == 1
        assert summary.rejected == 1
        # Mean = (1.0 + 1.0 + 0.6 + 0.0) / 4 = 0.65
        assert summary.mean_reward == pytest.approx(0.65, rel=0.01)

    def test_respects_limit(self, tmp_path):
        """Should respect limit parameter."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Log 5 events
        for _ in range(5):
            log_reward(buildlog_dir, outcome="accepted")

        summary = get_rewards(buildlog_dir, limit=2)

        # Stats should reflect all 5
        assert summary.total_events == 5
        # But only 2 events returned
        assert len(summary.events) == 2

    def test_returns_events_most_recent_first(self, tmp_path):
        """Should return events sorted by timestamp, most recent first."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        log_reward(buildlog_dir, outcome="accepted", notes="first")
        log_reward(buildlog_dir, outcome="revision", notes="second")
        log_reward(buildlog_dir, outcome="rejected", notes="third")

        summary = get_rewards(buildlog_dir)

        # Most recent should be first
        assert summary.events[0].notes == "third"
        assert summary.events[1].notes == "second"
        assert summary.events[2].notes == "first"


class TestRewardEvent:
    """Tests for RewardEvent dataclass."""

    def test_to_dict_and_from_dict_roundtrip(self):
        """Should serialize and deserialize correctly."""
        from datetime import datetime, timezone

        event = RewardEvent(
            id="rew-abc123",
            timestamp=datetime(2026, 1, 21, 10, 0, 0, tzinfo=timezone.utc),
            outcome="revision",
            reward_value=0.7,
            rules_active=["arch-123"],
            revision_distance=0.3,
            error_class="missing_test",
            notes="Test notes",
            source="manual",
        )

        # Round-trip
        data = event.to_dict()
        restored = RewardEvent.from_dict(data)

        assert restored.id == event.id
        assert restored.timestamp == event.timestamp
        assert restored.outcome == event.outcome
        assert restored.reward_value == event.reward_value
        assert restored.rules_active == event.rules_active
        assert restored.revision_distance == event.revision_distance
        assert restored.error_class == event.error_class
        assert restored.notes == event.notes
        assert restored.source == event.source

    def test_from_dict_handles_missing_optional_fields(self):
        """Should handle missing optional fields gracefully."""
        data = {
            "id": "rew-abc123",
            "timestamp": "2026-01-21T10:00:00+00:00",
            "outcome": "accepted",
            "reward_value": 1.0,
        }

        event = RewardEvent.from_dict(data)

        assert event.rules_active == []
        assert event.revision_distance is None
        assert event.error_class is None
        assert event.notes is None
        assert event.source is None


# -----------------------------------------------------------------------------
# Session Tracking Tests
# -----------------------------------------------------------------------------


class TestStartSession:
    """Tests for start_session operation."""

    def test_creates_active_session(self, tmp_path: Path):
        """Should create an active session marker."""
        from buildlog.core import start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = start_session(buildlog_dir, error_class="missing_test")

        assert result.session_id.startswith("session-")
        assert result.error_class == "missing_test"
        assert result.rules_count == 0  # No promoted rules yet

    def test_captures_current_rules(self, tmp_path: Path):
        """Should capture rules active at session start."""
        from buildlog.core import start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Create some promoted rules
        promoted_path = buildlog_dir / ".buildlog" / "promoted.json"
        promoted_path.parent.mkdir(parents=True, exist_ok=True)
        promoted_path.write_text('{"skill_ids": ["arch-123", "wf-456"]}')

        result = start_session(buildlog_dir)

        assert result.rules_count == 2


class TestEndSession:
    """Tests for end_session operation."""

    def test_ends_active_session(self, tmp_path: Path):
        """Should end an active session and record it."""
        from buildlog.core import end_session, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Start a session
        start_result = start_session(buildlog_dir, error_class="missing_test")

        # End it
        end_result = end_session(buildlog_dir)

        assert end_result.session_id == start_result.session_id
        assert end_result.duration_minutes >= 0
        assert end_result.mistakes_logged == 0
        assert end_result.repeated_mistakes == 0

        # Session should be recorded — verify via metrics
        from buildlog.core import get_session_metrics

        metrics = get_session_metrics(buildlog_dir, session_id=start_result.session_id)
        assert metrics is not None

    def test_raises_error_if_no_active_session(self, tmp_path: Path):
        """Should raise ValueError if no active session."""
        from buildlog.core import end_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        with pytest.raises(ValueError, match="No active session"):
            end_session(buildlog_dir)


class TestLogMistake:
    """Tests for log_mistake operation."""

    def test_logs_mistake_in_active_session(self, tmp_path: Path):
        """Should log a mistake during an active session."""
        from buildlog.core import log_mistake, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="missing_test")

        result = log_mistake(
            buildlog_dir,
            error_class="missing_test",
            description="Forgot to add unit tests for helper function",
        )

        assert result.mistake_id.startswith("mistake-")
        assert not result.was_repeat
        assert result.similar_prior is None

    def test_detects_repeat_mistakes(self, tmp_path: Path):
        """Should detect repeated mistakes across sessions."""
        from buildlog.core import end_session, log_mistake, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # First session with a mistake
        start_session(buildlog_dir, error_class="missing_test")
        log_mistake(
            buildlog_dir,
            error_class="missing_test",
            description="Forgot to add unit tests for helper function",
        )
        end_session(buildlog_dir)

        # Second session with same mistake
        start_session(buildlog_dir, error_class="missing_test")
        result = log_mistake(
            buildlog_dir,
            error_class="missing_test",
            description="Forgot to add unit tests for helper function",
        )

        assert result.was_repeat
        assert result.similar_prior is not None

    def test_auto_creates_session_if_none_exists(self, tmp_path: Path):
        """log_mistake auto-creates a session via _require_active_session."""
        from buildlog.core import log_mistake

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = log_mistake(
            buildlog_dir,
            error_class="missing_test",
            description="Some mistake",
        )
        # Should succeed and have a real session ID
        assert result.session_id.startswith("session-")
        assert not result.session_id.startswith("no-session-")


class TestLogMistakeValidation:
    """Tests for log_mistake input validation."""

    def test_invalid_severity_rejected(self, tmp_path: Path):
        """Should reject invalid severity values."""
        from buildlog.core import log_mistake, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        start_session(buildlog_dir, error_class="test")

        with pytest.raises(ValueError, match="Invalid severity"):
            log_mistake(
                buildlog_dir,
                error_class="test",
                description="test",
                severity="urgent",
            )

    def test_valid_severities_accepted(self, tmp_path: Path):
        """Should accept all valid severity values."""
        from buildlog.core import end_session, log_mistake, start_session

        for sev in ("low", "medium", "high", "critical"):
            buildlog_dir = tmp_path / f"buildlog-{sev}"
            buildlog_dir.mkdir()
            start_session(buildlog_dir, error_class="test")
            result = log_mistake(
                buildlog_dir,
                error_class="test",
                description="test",
                severity=sev,
            )
            assert result.mistake_id.startswith("mistake-")
            end_session(buildlog_dir)

    def test_none_severity_accepted(self, tmp_path: Path):
        """Should accept None severity (backwards compat)."""
        from buildlog.core import log_mistake, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        start_session(buildlog_dir, error_class="test")

        result = log_mistake(
            buildlog_dir,
            error_class="test",
            description="test",
            severity=None,
        )
        assert result.mistake_id.startswith("mistake-")

    def test_invalid_chain_type_rejected(self, tmp_path: Path):
        """Should reject invalid relation_to_prior type."""
        from buildlog.core import log_mistake, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        start_session(buildlog_dir, error_class="test")

        with pytest.raises(ValueError, match="Invalid relation_to_prior type"):
            log_mistake(
                buildlog_dir,
                error_class="test",
                description="test",
                relation_to_prior={"id": "prior-1", "type": "unknown_type"},
            )

    def test_valid_chain_types_accepted(self, tmp_path: Path):
        """Should accept all valid chain types."""
        from buildlog.core import end_session, log_mistake, start_session

        for chain in (
            "escalation",
            "same_pattern",
            "regression",
            "caused_by",
            "part_of",
        ):
            buildlog_dir = tmp_path / f"buildlog-{chain}"
            buildlog_dir.mkdir()
            start_session(buildlog_dir, error_class="test")
            result = log_mistake(
                buildlog_dir,
                error_class="test",
                description="test",
                relation_to_prior={"id": "prior-1", "type": chain},
            )
            assert result.mistake_id.startswith("mistake-")
            end_session(buildlog_dir)

    def test_relation_to_prior_missing_keys_rejected(self, tmp_path: Path):
        """Should reject relation_to_prior without required keys."""
        from buildlog.core import log_mistake, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        start_session(buildlog_dir, error_class="test")

        with pytest.raises(ValueError, match="must have 'id' and 'type' keys"):
            log_mistake(
                buildlog_dir,
                error_class="test",
                description="test",
                relation_to_prior={"id": "prior-1"},  # missing 'type'
            )

    def test_relation_to_prior_not_dict_rejected(self, tmp_path: Path):
        """Should reject non-dict relation_to_prior."""
        from buildlog.core import log_mistake, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        start_session(buildlog_dir, error_class="test")

        with pytest.raises(ValueError, match="must be a dict"):
            log_mistake(
                buildlog_dir,
                error_class="test",
                description="test",
                relation_to_prior="not-a-dict",  # type: ignore[arg-type]
            )


class TestGetSessionMetrics:
    """Tests for get_session_metrics operation."""

    def test_returns_aggregate_metrics(self, tmp_path: Path):
        """Should return aggregate metrics across all sessions."""
        from buildlog.core import (
            end_session,
            get_session_metrics,
            log_mistake,
            start_session,
        )

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Session 1
        start_session(buildlog_dir)
        log_mistake(buildlog_dir, "missing_test", "Mistake 1")
        end_session(buildlog_dir)

        # Session 2
        start_session(buildlog_dir)
        log_mistake(buildlog_dir, "missing_test", "Mistake 2")
        log_mistake(buildlog_dir, "missing_test", "Mistake 1")  # Repeat
        end_session(buildlog_dir)

        metrics = get_session_metrics(buildlog_dir)

        assert metrics.session_id == "aggregate"
        assert metrics.total_mistakes == 3
        assert metrics.repeated_mistakes == 1
        assert 0 < metrics.repeated_mistake_rate < 1

    def test_returns_session_specific_metrics(self, tmp_path: Path):
        """Should return metrics for a specific session."""
        from buildlog.core import (
            end_session,
            get_session_metrics,
            log_mistake,
            start_session,
        )

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = start_session(buildlog_dir)
        session_id = result.session_id

        log_mistake(buildlog_dir, "missing_test", "Mistake 1")
        log_mistake(buildlog_dir, "validation", "Mistake 2")
        end_session(buildlog_dir)

        metrics = get_session_metrics(buildlog_dir, session_id=session_id)

        assert metrics.session_id == session_id
        assert metrics.total_mistakes == 2
        assert metrics.repeated_mistakes == 0


class TestGetExperimentReport:
    """Tests for get_experiment_report operation."""

    def test_returns_comprehensive_report(self, tmp_path: Path):
        """Should return a comprehensive experiment report."""
        from buildlog.core import (
            end_session,
            get_experiment_report,
            log_mistake,
            start_session,
        )

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Run some sessions
        start_session(buildlog_dir, error_class="missing_test")
        log_mistake(buildlog_dir, "missing_test", "Forgot tests")
        end_session(buildlog_dir)

        report = get_experiment_report(buildlog_dir)

        assert "summary" in report
        assert report["summary"]["total_sessions"] == 1
        assert report["summary"]["total_mistakes"] == 1
        assert "sessions" in report
        assert "error_classes" in report
        assert "missing_test" in report["error_classes"]


class TestSession:
    """Tests for Session dataclass."""

    def test_to_dict_and_from_dict_roundtrip(self):
        """Should serialize and deserialize correctly."""
        from datetime import datetime, timezone

        from buildlog.core import Session

        session = Session(
            id="session-20260121-100000",
            started_at=datetime(2026, 1, 21, 10, 0, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 1, 21, 11, 0, 0, tzinfo=timezone.utc),
            entry_file="2026-01-21.md",
            rules_at_start=["arch-123"],
            rules_at_end=["arch-123", "wf-456"],
            error_class="missing_test",
            notes="Test session",
        )

        data = session.to_dict()
        restored = Session.from_dict(data)

        assert restored.id == session.id
        assert restored.started_at == session.started_at
        assert restored.ended_at == session.ended_at
        assert restored.entry_file == session.entry_file
        assert restored.rules_at_start == session.rules_at_start
        assert restored.rules_at_end == session.rules_at_end
        assert restored.error_class == session.error_class
        assert restored.notes == session.notes


class TestMistake:
    """Tests for Mistake dataclass."""

    def test_to_dict_and_from_dict_roundtrip(self):
        """Should serialize and deserialize correctly."""
        from datetime import datetime, timezone

        from buildlog.core import Mistake

        mistake = Mistake(
            id="mistake-test-20260121-100000",
            session_id="session-20260121-100000",
            timestamp=datetime(2026, 1, 21, 10, 30, 0, tzinfo=timezone.utc),
            error_class="missing_test",
            description="Forgot to add tests",
            semantic_hash="abc123def456",
            was_repeat=True,
            corrected_by_rule="test-123",
        )

        data = mistake.to_dict()
        restored = Mistake.from_dict(data)

        assert restored.id == mistake.id
        assert restored.session_id == mistake.session_id
        assert restored.timestamp == mistake.timestamp
        assert restored.error_class == mistake.error_class
        assert restored.description == mistake.description
        assert restored.semantic_hash == mistake.semantic_hash
        assert restored.was_repeat == mistake.was_repeat
        assert restored.corrected_by_rule == mistake.corrected_by_rule


class TestMalformedJsonHandling:
    """Tests for handling malformed JSON in JSONL files."""

    def test_get_rewards_handles_malformed_lines(self, tmp_path):
        """Should skip malformed JSON lines and continue processing."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        bl_dir = buildlog_dir / ".buildlog"
        bl_dir.mkdir()

        # Write a file with some valid and some invalid lines
        # Note: RewardEvent uses 'id' not 'reward_id', and requires 'rules_active'
        rewards_file = bl_dir / "reward_events.jsonl"
        valid_1 = (
            '{"id": "rew-1", "outcome": "accepted", "reward_value": 1.0, '
            '"timestamp": "2026-01-21T10:00:00+00:00", "rules_active": []}'
        )
        valid_2 = (
            '{"id": "rew-2", "outcome": "rejected", "reward_value": 0.0, '
            '"timestamp": "2026-01-21T11:00:00+00:00", "rules_active": []}'
        )
        rewards_file.write_text(f"{valid_1}\nnot valid json\n{valid_2}\n")

        result = get_rewards(buildlog_dir, limit=10)

        # Should have loaded 2 valid events, skipped the malformed one
        assert result.total_events == 2
        assert result.accepted == 1
        assert result.rejected == 1

    def test_log_reward_creates_directory_if_missing(self, tmp_path):
        """Should persist reward if no .buildlog dir exists."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        # Note: .buildlog directory does NOT exist

        result = log_reward(buildlog_dir, outcome="accepted")

        assert result.error is None
        rewards = get_rewards(buildlog_dir)
        assert rewards.total_events == 1


class TestFileIOEdgeCases:
    """Tests for file I/O edge cases."""

    def test_get_rewards_handles_empty_file(self, tmp_path):
        """Should handle empty reward events file."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        bl_dir = buildlog_dir / ".buildlog"
        bl_dir.mkdir()

        # Create empty file
        (bl_dir / "reward_events.jsonl").write_text("")

        result = get_rewards(buildlog_dir)

        assert result.total_events == 0
        assert result.mean_reward == 0.0

    def test_get_rewards_handles_missing_file(self, tmp_path):
        """Should handle missing reward events file gracefully."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        # Note: reward_events.jsonl does NOT exist

        result = get_rewards(buildlog_dir)

        assert result.total_events == 0
        assert len(result.events) == 0

    def test_learn_from_review_handles_missing_learnings_file(self, tmp_path):
        """Should handle missing learnings file gracefully."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        # Note: review_learnings.json does NOT exist

        issues = [
            {
                "severity": "major",
                "category": "security",
                "description": "Test issue",
                "rule_learned": "Test rule",
            }
        ]

        result = learn_from_review(buildlog_dir, issues)

        assert result.error is None
        assert len(result.new_learnings) == 1

    def test_status_handles_empty_buildlog(self, tmp_path):
        """Should handle buildlog directory with no entries."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = status(buildlog_dir)

        assert result.total_entries == 0
        assert result.total_skills == 0


class TestSimilarityHeuristicEdgeCases:
    """Tests for word overlap similarity heuristic edge cases.

    Note: Similarity detection only works across DIFFERENT sessions,
    not within the same session. This is by design - we want to detect
    repeated mistakes across sessions, not duplicates within a session.
    """

    def test_find_similar_mistake_handles_empty_description(self, tmp_path):
        """Should handle empty descriptions without crashing."""
        from buildlog.core.operations import end_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        bl_dir = buildlog_dir / ".buildlog"
        bl_dir.mkdir()

        # Session 1: log mistake with empty description
        start_session(buildlog_dir, error_class="test")
        log_mistake(buildlog_dir, error_class="test", description="")
        end_session(buildlog_dir)

        # Session 2: log another empty description - should not crash
        start_session(buildlog_dir, error_class="test")
        result = log_mistake(buildlog_dir, error_class="test", description="")

        # Empty descriptions have the same semantic hash, so they DO match
        # This is expected behavior - two empty mistakes are semantically identical
        assert result.was_repeat

    def test_find_similar_mistake_across_sessions(self, tmp_path):
        """Should detect similar mistakes across different sessions."""
        from buildlog.core.operations import end_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        bl_dir = buildlog_dir / ".buildlog"
        bl_dir.mkdir()

        # Session 1: log a mistake
        start_session(buildlog_dir, error_class="test")
        log_mistake(
            buildlog_dir,
            error_class="test",
            description="forgot to add unit tests for helper function",
        )
        end_session(buildlog_dir)

        # Session 2: log a similar mistake
        start_session(buildlog_dir, error_class="test")
        result = log_mistake(
            buildlog_dir,
            error_class="test",
            description="forgot to add unit tests for helper function",
        )

        # Same description should be detected as repeat
        assert result.was_repeat

    def test_find_similar_mistake_boundary_overlap(self, tmp_path):
        """Test above the 0.7 overlap threshold across sessions."""
        from buildlog.core.operations import end_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        bl_dir = buildlog_dir / ".buildlog"
        bl_dir.mkdir()

        # Session 1: 10 distinct words
        start_session(buildlog_dir, error_class="test")
        words = [
            "word1",
            "word2",
            "word3",
            "word4",
            "word5",
            "word6",
            "word7",
            "word8",
            "word9",
            "word10",
        ]
        log_mistake(buildlog_dir, error_class="test", description=" ".join(words))
        end_session(buildlog_dir)

        # Session 2: 8 matching words + 2 different (80% overlap, above threshold)
        # Note: threshold is > 0.7, so 7/10 (70%) doesn't match, need 8/10 (80%)
        start_session(buildlog_dir, error_class="test")
        similar_words = words[:8] + ["different1", "different2"]
        result = log_mistake(
            buildlog_dir, error_class="test", description=" ".join(similar_words)
        )

        # Above 0.7 threshold, 8/10 matching words should be detected
        assert result.was_repeat

    def test_find_similar_mistake_below_threshold(self, tmp_path):
        """Test below the 0.7 overlap threshold - should NOT be detected."""
        from buildlog.core.operations import end_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        bl_dir = buildlog_dir / ".buildlog"
        bl_dir.mkdir()

        # Session 1: 10 distinct words
        start_session(buildlog_dir, error_class="test")
        words = [
            "word1",
            "word2",
            "word3",
            "word4",
            "word5",
            "word6",
            "word7",
            "word8",
            "word9",
            "word10",
        ]
        log_mistake(buildlog_dir, error_class="test", description=" ".join(words))
        end_session(buildlog_dir)

        # Session 2: only 6 matching words (60% overlap, below 0.7 threshold)
        start_session(buildlog_dir, error_class="test")
        different_words = words[:6] + ["diff1", "diff2", "diff3", "diff4"]
        result = log_mistake(
            buildlog_dir, error_class="test", description=" ".join(different_words)
        )

        # Below threshold, should NOT be detected as repeat
        assert not result.was_repeat

    def test_find_similar_mistake_different_error_class(self, tmp_path):
        """Similar description with different error_class should NOT match."""
        from buildlog.core.operations import end_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        bl_dir = buildlog_dir / ".buildlog"
        bl_dir.mkdir()

        # Session 1: error class "test"
        start_session(buildlog_dir, error_class="test")
        log_mistake(buildlog_dir, error_class="test", description="forgot to add tests")
        end_session(buildlog_dir)

        # Session 2: same description but different error class
        start_session(buildlog_dir, error_class="security")
        result = log_mistake(
            buildlog_dir, error_class="security", description="forgot to add tests"
        )

        # Different error class means it's a different type of mistake
        assert not result.was_repeat
