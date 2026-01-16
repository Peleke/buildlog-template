"""Tests for buildlog.render module."""

from pathlib import Path
import json

import pytest

from buildlog.render import ClaudeMdRenderer, SettingsJsonRenderer, SkillRenderer, get_renderer
from buildlog.skills import Skill


def make_skill(
    id: str = "arch-123456",
    category: str = "architectural",
    rule: str = "Test rule",
    frequency: int = 2,
    confidence: str = "medium",
) -> Skill:
    """Factory for test skills."""
    return Skill(
        id=id,
        category=category,
        rule=rule,
        frequency=frequency,
        confidence=confidence,
        sources=["test.md"],
        tags=["test"],
    )


class TestClaudeMdRenderer:
    """Tests for ClaudeMdRenderer."""

    def test_appends_to_existing_file(self, tmp_path):
        """Should append rules to existing CLAUDE.md."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Existing content\n\nSome rules here.\n")

        renderer = ClaudeMdRenderer(
            path=claude_md,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill()
        result = renderer.render([skill])

        content = claude_md.read_text()
        assert "# Existing content" in content
        assert "## Learned Rules" in content
        assert "1 rules" in result

    def test_creates_new_file_if_missing(self, tmp_path):
        """Should create CLAUDE.md if it doesn't exist."""
        claude_md = tmp_path / "CLAUDE.md"

        renderer = ClaudeMdRenderer(
            path=claude_md,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill()
        renderer.render([skill])

        assert claude_md.exists()
        content = claude_md.read_text()
        assert "## Learned Rules" in content

    def test_groups_by_category(self, tmp_path):
        """Should group rules by category."""
        claude_md = tmp_path / "CLAUDE.md"

        renderer = ClaudeMdRenderer(
            path=claude_md,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skills = [
            make_skill(id="arch-1", category="architectural", rule="Arch rule"),
            make_skill(id="wf-1", category="workflow", rule="Workflow rule"),
        ]
        renderer.render(skills)

        content = claude_md.read_text()
        assert "### Architectural" in content
        assert "### Workflow" in content

    def test_converts_to_imperative(self, tmp_path):
        """Should convert rules to imperative form."""
        claude_md = tmp_path / "CLAUDE.md"

        renderer = ClaudeMdRenderer(
            path=claude_md,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill(rule="use dependency injection", confidence="high")
        renderer.render([skill])

        content = claude_md.read_text()
        # High confidence should get "Always" prefix
        assert "Always" in content

    def test_tracks_promoted_ids(self, tmp_path):
        """Should track promoted skill IDs."""
        tracking_path = tmp_path / ".buildlog" / "promoted.json"

        renderer = ClaudeMdRenderer(
            path=tmp_path / "CLAUDE.md",
            tracking_path=tracking_path,
        )
        skill = make_skill(id="arch-test123")
        renderer.render([skill])

        assert tracking_path.exists()
        data = json.loads(tracking_path.read_text())
        assert "arch-test123" in data["skill_ids"]

    def test_returns_message_for_empty_list(self, tmp_path):
        """Should return early message for empty skills list."""
        renderer = ClaudeMdRenderer(
            path=tmp_path / "CLAUDE.md",
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        result = renderer.render([])

        assert "No skills to promote" in result


class TestSettingsJsonRenderer:
    """Tests for SettingsJsonRenderer."""

    def test_creates_new_settings_file(self, tmp_path):
        """Should create settings.json if it doesn't exist."""
        settings_file = tmp_path / ".claude" / "settings.json"

        renderer = SettingsJsonRenderer(
            path=settings_file,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill()
        renderer.render([skill])

        assert settings_file.exists()
        data = json.loads(settings_file.read_text())
        assert "rules" in data
        assert len(data["rules"]) >= 1

    def test_merges_with_existing_settings(self, tmp_path):
        """Should merge rules into existing settings."""
        settings_file = tmp_path / ".claude" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text(json.dumps({
            "existing_key": "existing_value",
            "rules": ["existing rule"],
        }))

        renderer = SettingsJsonRenderer(
            path=settings_file,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill(rule="new rule")
        renderer.render([skill])

        data = json.loads(settings_file.read_text())
        assert data["existing_key"] == "existing_value"
        assert "existing rule" in data["rules"]
        assert len(data["rules"]) >= 2

    def test_does_not_duplicate_rules(self, tmp_path):
        """Should not add duplicate rules."""
        settings_file = tmp_path / ".claude" / "settings.json"
        settings_file.parent.mkdir(parents=True)

        renderer = SettingsJsonRenderer(
            path=settings_file,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )

        # Render same skill twice
        skill = make_skill(rule="test rule", confidence="high")
        renderer.render([skill])
        result = renderer.render([skill])

        # Second render should report duplicates skipped
        assert "duplicates skipped" in result

        data = json.loads(settings_file.read_text())
        # Count occurrences of the rule
        rule_text = "Always test rule"  # high confidence gets "Always"
        count = data["rules"].count(rule_text)
        assert count == 1

    def test_adds_buildlog_metadata(self, tmp_path):
        """Should add _buildlog metadata section."""
        settings_file = tmp_path / ".claude" / "settings.json"

        renderer = SettingsJsonRenderer(
            path=settings_file,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill(id="arch-meta123")
        renderer.render([skill])

        data = json.loads(settings_file.read_text())
        assert "_buildlog" in data
        assert "last_updated" in data["_buildlog"]
        assert "arch-meta123" in data["_buildlog"]["promoted_skill_ids"]

    def test_tracks_promoted_ids(self, tmp_path):
        """Should track promoted skill IDs."""
        tracking_path = tmp_path / ".buildlog" / "promoted.json"

        renderer = SettingsJsonRenderer(
            path=tmp_path / ".claude" / "settings.json",
            tracking_path=tracking_path,
        )
        skill = make_skill(id="wf-track123")
        renderer.render([skill])

        assert tracking_path.exists()
        data = json.loads(tracking_path.read_text())
        assert "wf-track123" in data["skill_ids"]


class TestGetRenderer:
    """Tests for get_renderer() factory."""

    def test_returns_claude_md_renderer(self):
        """Should return ClaudeMdRenderer for 'claude_md'."""
        renderer = get_renderer("claude_md")
        assert isinstance(renderer, ClaudeMdRenderer)

    def test_returns_settings_json_renderer(self):
        """Should return SettingsJsonRenderer for 'settings_json'."""
        renderer = get_renderer("settings_json")
        assert isinstance(renderer, SettingsJsonRenderer)

    def test_returns_skill_renderer(self):
        """Should return SkillRenderer for 'skill'."""
        renderer = get_renderer("skill")
        assert isinstance(renderer, SkillRenderer)

    def test_accepts_custom_path(self, tmp_path):
        """Should accept custom path."""
        custom_path = tmp_path / "custom" / "RULES.md"
        renderer = get_renderer("claude_md", path=custom_path)
        assert renderer.path == custom_path

    def test_raises_for_unknown_target(self):
        """Should raise ValueError for unknown target."""
        with pytest.raises(ValueError, match="Unknown render target"):
            get_renderer("unknown")
