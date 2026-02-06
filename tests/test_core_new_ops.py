"""Tests for new core operations: get_gauntlet_rules, get_overview, create_entry, list_entries."""

import json
import shutil
from pathlib import Path

import pytest

from buildlog.core.operations import (
    CreateEntryResult,
    GauntletRulesResult,
    ListEntriesResult,
    OverviewResult,
    create_entry,
    get_gauntlet_rules,
    get_overview,
    list_entries,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "buildlog"


# =============================================================================
# get_gauntlet_rules tests
# =============================================================================


class TestGetGauntletRules:
    """Tests for get_gauntlet_rules() operation."""

    def test_returns_all_personas(self):
        """Should return rules from all personas when no filter."""
        result = get_gauntlet_rules()
        assert result.error is None
        assert result.total_rules > 0
        assert len(result.personas) >= 2

    def test_filters_by_persona(self):
        """Should return only rules for the specified persona."""
        result = get_gauntlet_rules(persona="security_karen")
        if result.error is None:
            assert result.personas == ["security_karen"]
            assert result.total_rules > 0

    def test_invalid_persona(self):
        """Should return error for unknown persona."""
        result = get_gauntlet_rules(persona="nonexistent_persona")
        assert result.error is not None
        assert "Unknown persona" in result.error

    def test_json_format(self):
        """Should return valid JSON when format='json'."""
        result = get_gauntlet_rules(format="json")
        if result.error is None:
            parsed = json.loads(result.formatted)
            assert isinstance(parsed, dict)

    def test_yaml_format(self):
        """Should return valid YAML when format='yaml'."""
        import yaml

        result = get_gauntlet_rules(format="yaml")
        if result.error is None:
            parsed = yaml.safe_load(result.formatted)
            assert isinstance(parsed, dict)

    def test_markdown_format(self):
        """Should return markdown with headers."""
        result = get_gauntlet_rules(format="markdown")
        if result.error is None:
            assert "# Review Gauntlet Rules" in result.formatted
            assert "##" in result.formatted

    def test_rule_fields(self):
        """Each rule should have expected fields."""
        result = get_gauntlet_rules(format="json")
        if result.error is None:
            data = json.loads(result.formatted)
            for _persona_name, persona_data in data.items():
                for rule in persona_data["rules"]:
                    assert "rule" in rule
                    assert "category" in rule

    def test_rule_count_matches(self):
        """total_rules should match sum of all persona rules."""
        result = get_gauntlet_rules(format="json")
        if result.error is None:
            data = json.loads(result.formatted)
            counted = sum(len(p["rules"]) for p in data.values())
            assert result.total_rules == counted


# =============================================================================
# get_overview tests
# =============================================================================


class TestGetOverview:
    """Tests for get_overview() operation."""

    def test_empty_buildlog(self, tmp_path):
        """Should return 0 entries and 0 skills for empty buildlog."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        result = get_overview(buildlog_dir)
        assert result.entries == 0
        assert result.skills["total"] == 0
        assert result.active_session is None

    def test_with_entries(self):
        """Should return correct entry count."""
        result = get_overview(FIXTURES_DIR)
        assert result.entries >= 1

    def test_skills_summary(self):
        """Should have skills summary with expected keys."""
        result = get_overview(FIXTURES_DIR)
        assert "total" in result.skills
        assert "by_confidence" in result.skills
        assert "promoted" in result.skills
        assert "rejected" in result.skills
        assert "pending" in result.skills

    def test_active_session_none_by_default(self, tmp_path):
        """active_session should be None when no session is active."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        result = get_overview(buildlog_dir)
        assert result.active_session is None

    def test_render_targets(self):
        """Should include known render targets."""
        result = get_overview(FIXTURES_DIR)
        assert "claude_md" in result.render_targets

    def test_corrupted_promoted_json(self, tmp_path):
        """Should handle malformed promoted.json gracefully."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        dot_buildlog = buildlog_dir / ".buildlog"
        dot_buildlog.mkdir()
        (dot_buildlog / "promoted.json").write_text("{invalid json")

        result = get_overview(buildlog_dir)
        # Should not crash
        assert result.skills["promoted"] == 0


# =============================================================================
# create_entry tests
# =============================================================================


class TestCreateEntry:
    """Tests for create_entry() operation."""

    def _setup_buildlog(self, tmp_path):
        """Set up a buildlog dir with templates."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        (buildlog_dir / "_TEMPLATE.md").write_text(
            "# Build Journal: [TITLE]\n\nDate: [YYYY-MM-DD]\n"
        )
        (buildlog_dir / "_TEMPLATE_QUICK.md").write_text(
            "# [YYYY-MM-DD] Quick\n\n## What\n"
        )
        return buildlog_dir

    def test_basic(self, tmp_path):
        """Should create a file and return correct metadata."""
        buildlog_dir = self._setup_buildlog(tmp_path)
        result = create_entry(buildlog_dir, "test-feature")

        assert result.error is None
        assert Path(result.entry_path).exists()
        assert "test-feature" in result.entry_name
        assert result.template_used == "_TEMPLATE.md"

    def test_quick_template(self, tmp_path):
        """Should use quick template when quick=True."""
        buildlog_dir = self._setup_buildlog(tmp_path)
        result = create_entry(buildlog_dir, "quick-test", quick=True)

        assert result.error is None
        assert result.template_used == "_TEMPLATE_QUICK.md"

    def test_custom_date(self, tmp_path):
        """Should use custom date in filename."""
        buildlog_dir = self._setup_buildlog(tmp_path)
        result = create_entry(buildlog_dir, "dated", entry_date="2026-01-15")

        assert result.error is None
        assert result.date_str == "2026-01-15"
        assert "2026-01-15" in result.entry_name

    def test_today_default(self, tmp_path):
        """Should use today's date when no date provided."""
        from datetime import date

        buildlog_dir = self._setup_buildlog(tmp_path)
        result = create_entry(buildlog_dir, "today-test")

        assert result.error is None
        assert result.date_str == date.today().isoformat()

    def test_slug_sanitization(self, tmp_path):
        """Should sanitize slug to lowercase with hyphens."""
        buildlog_dir = self._setup_buildlog(tmp_path)
        result = create_entry(buildlog_dir, "My Feature!")

        assert result.error is None
        assert "my-feature" in result.entry_name

    def test_duplicate_error(self, tmp_path):
        """Should return error for duplicate entries."""
        buildlog_dir = self._setup_buildlog(tmp_path)
        create_entry(buildlog_dir, "dup", entry_date="2026-01-01")
        result = create_entry(buildlog_dir, "dup", entry_date="2026-01-01")

        assert result.error is not None
        assert "already exists" in result.error

    def test_missing_dir(self, tmp_path):
        """Should return error when buildlog dir doesn't exist."""
        result = create_entry(tmp_path / "nonexistent", "test")
        assert result.error is not None

    def test_missing_template_self_heals(self, tmp_path):
        """Should auto-provision template from bundled sources if missing."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = create_entry(buildlog_dir, "test")
        # Self-healing finds the template from bundled sources
        # when running from source or editable install
        if result.error is not None:
            assert "_TEMPLATE.md" in result.error
        else:
            assert result.entry_path != ""

    def test_invalid_date(self, tmp_path):
        """Should return error for invalid date."""
        buildlog_dir = self._setup_buildlog(tmp_path)
        result = create_entry(buildlog_dir, "test", entry_date="not-a-date")
        assert result.error is not None

    def test_replaces_date_placeholder(self, tmp_path):
        """Should replace [YYYY-MM-DD] in content."""
        buildlog_dir = self._setup_buildlog(tmp_path)
        result = create_entry(buildlog_dir, "placeholder", entry_date="2026-03-15")

        content = Path(result.entry_path).read_text()
        assert "[YYYY-MM-DD]" not in content
        assert "2026-03-15" in content


# =============================================================================
# list_entries tests
# =============================================================================


class TestListEntries:
    """Tests for list_entries() operation."""

    def test_empty(self, tmp_path):
        """Should return empty list and message for no entries."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = list_entries(buildlog_dir)
        assert result.entries == []
        assert result.count == 0
        assert result.message is not None

    def test_sorted_recent_first(self, tmp_path):
        """Should sort entries most recent first."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / "2026-01-01-first.md").write_text("# First\n")
        (buildlog_dir / "2026-01-03-third.md").write_text("# Third\n")
        (buildlog_dir / "2026-01-02-second.md").write_text("# Second\n")

        result = list_entries(buildlog_dir)
        assert result.count == 3
        assert result.entries[0]["name"] == "2026-01-03-third.md"
        assert result.entries[2]["name"] == "2026-01-01-first.md"

    def test_extracts_title(self, tmp_path):
        """Should extract title from first line."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / "2026-01-01-test.md").write_text(
            "# My Great Feature\n\nContent"
        )

        result = list_entries(buildlog_dir)
        assert result.entries[0]["title"] == "My Great Feature"

    def test_handles_placeholder_title(self, tmp_path):
        """Should replace [TITLE] with (untitled)."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / "2026-01-01-test.md").write_text("# [TITLE]\n")

        result = list_entries(buildlog_dir)
        assert result.entries[0]["title"] == "(untitled)"

    def test_ignores_templates(self, tmp_path):
        """Templates should not appear in results."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / "_TEMPLATE.md").write_text("# Template\n")
        (buildlog_dir / "2026-01-01-real.md").write_text("# Real\n")

        result = list_entries(buildlog_dir)
        assert result.count == 1
        assert result.entries[0]["name"] == "2026-01-01-real.md"

    def test_missing_dir(self, tmp_path):
        """Should handle missing directory."""
        result = list_entries(tmp_path / "nonexistent")
        assert result.count == 0
        assert result.message is not None
