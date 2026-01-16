"""Tests for buildlog.render.skill module (Anthropic Agent Skills format)."""

import json
from pathlib import Path
from typing import Literal

import pytest

from buildlog.render import SkillRenderer, get_renderer
from buildlog.skills import ConfidenceLevel, Skill


def make_skill(
    id: str = "arch-123456",
    category: str = "architectural",
    rule: str = "Test rule",
    frequency: int = 2,
    confidence: ConfidenceLevel = "medium",
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


class TestSkillRenderer:
    """Tests for SkillRenderer."""

    def test_creates_skill_directory(self, tmp_path):
        """Should create .claude/skills/buildlog-learned/ structure."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill()
        renderer.render([skill])

        assert skill_path.exists()
        assert skill_path.parent.name == "buildlog-learned"
        assert skill_path.parent.parent.name == "skills"

    def test_creates_yaml_frontmatter(self, tmp_path):
        """Should have valid YAML frontmatter with name and description."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill()
        renderer.render([skill])

        content = skill_path.read_text()

        # Check frontmatter structure
        assert content.startswith("---\n")
        assert "name: buildlog-learned" in content
        assert "description:" in content
        # Close frontmatter
        lines = content.split("\n")
        frontmatter_closes = [i for i, line in enumerate(lines) if line == "---"]
        assert len(frontmatter_closes) >= 2  # Open and close

    def test_description_includes_rule_count_and_categories(self, tmp_path):
        """Description should mention categories for better triggering."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skills = [
            make_skill(id="arch-1", category="architectural", rule="Arch rule"),
            make_skill(id="wf-1", category="workflow", rule="Workflow rule"),
        ]
        renderer.render(skills)

        content = skill_path.read_text()

        # Should mention rule count
        assert "2 rules" in content
        # Should mention categories in description
        assert "Architectural" in content
        assert "Workflow" in content

    def test_groups_by_confidence_level(self, tmp_path):
        """High confidence rules appear before medium before low."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skills = [
            make_skill(id="low-1", confidence="low", rule="Low confidence rule"),
            make_skill(id="high-1", confidence="high", rule="High confidence rule"),
            make_skill(id="med-1", confidence="medium", rule="Medium confidence rule"),
        ]
        renderer.render(skills)

        content = skill_path.read_text()

        # Find section positions
        high_pos = content.find("Must Follow")
        medium_pos = content.find("Should Consider")
        low_pos = content.find("Worth Knowing")

        # All sections should exist
        assert high_pos != -1
        assert medium_pos != -1
        assert low_pos != -1

        # Check order
        assert high_pos < medium_pos < low_pos

    def test_high_confidence_section_content(self, tmp_path):
        """High confidence section should have correct title and description."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill(confidence="high", rule="Always validate inputs")
        renderer.render([skill])

        content = skill_path.read_text()

        assert "## Must Follow (High Confidence)" in content
        assert "reinforced multiple times" in content
        assert "Always validate inputs" in content

    def test_medium_confidence_section_content(self, tmp_path):
        """Medium confidence section should have correct title and description."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill(confidence="medium", rule="Prefer dependency injection")
        renderer.render([skill])

        content = skill_path.read_text()

        assert "## Should Consider (Medium Confidence)" in content
        assert "may have exceptions" in content
        assert "Prefer dependency injection" in content

    def test_low_confidence_section_content(self, tmp_path):
        """Low confidence section should have correct title and description."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill(confidence="low", rule="Consider using TypeScript")
        renderer.render([skill])

        content = skill_path.read_text()

        assert "## Worth Knowing (Low Confidence)" in content
        assert "Emerging patterns" in content
        assert "Consider using TypeScript" in content

    def test_groups_rules_by_category_within_confidence(self, tmp_path):
        """Within each confidence level, rules should be grouped by category."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skills = [
            make_skill(id="arch-h1", category="architectural", confidence="high", rule="Arch high"),
            make_skill(id="wf-h1", category="workflow", confidence="high", rule="Workflow high"),
        ]
        renderer.render(skills)

        content = skill_path.read_text()

        # Should have category headers within high confidence section
        assert "### Architectural" in content
        assert "### Workflow" in content

    def test_does_not_add_confidence_prefix_to_rules(self, tmp_path):
        """Rules should NOT have confidence prefix since section indicates it."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill(confidence="high", rule="Validate all inputs")
        renderer.render([skill])

        content = skill_path.read_text()

        # The rule should appear as-is without "Always" prefix
        assert "- Validate all inputs" in content
        # Should NOT have "Always Validate" since section already conveys confidence
        assert "- Always Validate all inputs" not in content

    def test_tracks_promoted_ids(self, tmp_path):
        """Should track promoted skill IDs in tracking file."""
        tracking_path = tmp_path / ".buildlog" / "promoted.json"

        renderer = SkillRenderer(
            path=tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md",
            tracking_path=tracking_path,
        )
        skill = make_skill(id="arch-track123")
        renderer.render([skill])

        assert tracking_path.exists()
        data = json.loads(tracking_path.read_text())
        assert "arch-track123" in data["skill_ids"]
        assert "arch-track123" in data["promoted_at"]

    def test_returns_message_for_empty_list(self, tmp_path):
        """Should return early message for empty skills list."""
        renderer = SkillRenderer(
            path=tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md",
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        result = renderer.render([])

        assert "No skills to promote" in result

    def test_returns_confirmation_message(self, tmp_path):
        """Should return confirmation message with path."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill()
        result = renderer.render([skill])

        assert "Created skill at" in result
        assert str(skill_path) in result

    def test_custom_skill_name(self, tmp_path):
        """Should support custom skill name."""
        skill_path = tmp_path / ".claude" / "skills" / "my-custom-skill" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
            skill_name="my-custom-skill",
        )
        skill = make_skill()
        renderer.render([skill])

        content = skill_path.read_text()
        assert "name: my-custom-skill" in content

    def test_description_includes_trigger_keywords(self, tmp_path):
        """Description should include keywords that trigger skill loading."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skill = make_skill()
        renderer.render([skill])

        content = skill_path.read_text()

        # Should include trigger keywords for Claude to recognize
        assert "writing code" in content
        assert "architectural decisions" in content
        assert "reviewing PRs" in content
        assert "consistency" in content

    def test_handles_all_categories(self, tmp_path):
        """Should handle all supported categories."""
        skill_path = tmp_path / ".claude" / "skills" / "buildlog-learned" / "SKILL.md"

        renderer = SkillRenderer(
            path=skill_path,
            tracking_path=tmp_path / ".buildlog" / "promoted.json",
        )
        skills = [
            make_skill(id="arch-1", category="architectural"),
            make_skill(id="wf-1", category="workflow"),
            make_skill(id="tool-1", category="tool_usage"),
            make_skill(id="dk-1", category="domain_knowledge"),
        ]
        renderer.render(skills)

        content = skill_path.read_text()

        assert "### Architectural" in content
        assert "### Workflow" in content
        assert "### Tool Usage" in content
        assert "### Domain Knowledge" in content


class TestGetRendererSkill:
    """Tests for get_renderer() with skill target."""

    def test_returns_skill_renderer(self):
        """Should return SkillRenderer for 'skill'."""
        renderer = get_renderer("skill")
        assert isinstance(renderer, SkillRenderer)

    def test_accepts_custom_path(self, tmp_path):
        """Should accept custom path."""
        custom_path = tmp_path / "custom" / "SKILL.md"
        renderer = get_renderer("skill", path=custom_path)
        assert renderer.path == custom_path

    def test_accepts_custom_skill_name(self, tmp_path):
        """Should accept custom skill_name via kwargs."""
        renderer = get_renderer("skill", skill_name="my-skill")
        assert renderer.skill_name == "my-skill"


class TestSkillRendererSecurity:
    """Security tests for SkillRenderer."""

    def test_rejects_path_traversal_with_forward_slash(self, tmp_path):
        """Should reject skill_name with forward slashes."""
        with pytest.raises(ValueError, match="path separators"):
            SkillRenderer(
                path=tmp_path / "SKILL.md",
                skill_name="../../malicious",
            )

    def test_rejects_path_traversal_with_backslash(self, tmp_path):
        """Should reject skill_name with backslashes."""
        with pytest.raises(ValueError, match="path separators"):
            SkillRenderer(
                path=tmp_path / "SKILL.md",
                skill_name="..\\..\\malicious",
            )

    def test_rejects_path_traversal_with_double_dots(self, tmp_path):
        """Should reject skill_name with parent directory references."""
        with pytest.raises(ValueError, match="path separators"):
            SkillRenderer(
                path=tmp_path / "SKILL.md",
                skill_name="..",
            )

    def test_allows_valid_skill_name_with_hyphen(self, tmp_path):
        """Should allow valid skill names with hyphens."""
        renderer = SkillRenderer(
            path=tmp_path / "SKILL.md",
            skill_name="my-custom-skill",
        )
        assert renderer.skill_name == "my-custom-skill"

    def test_allows_valid_skill_name_with_underscore(self, tmp_path):
        """Should allow valid skill names with underscores."""
        renderer = SkillRenderer(
            path=tmp_path / "SKILL.md",
            skill_name="my_custom_skill",
        )
        assert renderer.skill_name == "my_custom_skill"


class TestTrackingWithCorruptJson:
    """Test handling of corrupt JSON in tracking file."""

    def test_recovers_from_corrupt_tracking_json(self, tmp_path):
        """Should recover gracefully from corrupt tracking JSON."""
        tracking_path = tmp_path / ".buildlog" / "promoted.json"
        tracking_path.parent.mkdir(parents=True)
        tracking_path.write_text("{ this is not valid json }")

        renderer = SkillRenderer(
            path=tmp_path / ".claude" / "skills" / "test" / "SKILL.md",
            tracking_path=tracking_path,
            skill_name="test",
        )
        skill = make_skill(id="test-123")
        renderer.render([skill])

        # Should have recovered and written valid JSON
        data = json.loads(tracking_path.read_text())
        assert "test-123" in data["skill_ids"]
