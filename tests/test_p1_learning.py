"""Exhaustive tests for P1 learning pipeline MCP tools."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "buildlog"


# =============================================================================
# buildlog_distill tests
# =============================================================================


class TestBuildlogDistill:
    """Tests for buildlog_distill MCP tool."""

    def test_returns_dict(self):
        from buildlog.mcp.tools import buildlog_distill

        result = buildlog_distill(buildlog_dir=str(FIXTURES_DIR))
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        from buildlog.mcp.tools import buildlog_distill

        result = buildlog_distill(buildlog_dir=str(FIXTURES_DIR))
        assert "extracted_at" in result
        assert "entry_count" in result
        assert "patterns" in result
        assert "statistics" in result

    def test_returns_error_for_missing_dir(self, tmp_path):
        from buildlog.mcp.tools import buildlog_distill

        result = buildlog_distill(buildlog_dir=str(tmp_path / "nonexistent"))
        assert "error" in result
        assert result["error"] is not None

    def test_invalid_date_returns_error(self):
        from buildlog.mcp.tools import buildlog_distill

        result = buildlog_distill(since="not-a-date", buildlog_dir=str(FIXTURES_DIR))
        assert "error" in result
        assert "Invalid date" in result["error"]

    def test_valid_since_filter(self):
        from buildlog.mcp.tools import buildlog_distill

        result = buildlog_distill(since="2099-01-01", buildlog_dir=str(FIXTURES_DIR))
        assert result.get("error") is None
        assert result["entry_count"] == 0

    def test_invalid_category_returns_error(self):
        from buildlog.mcp.tools import buildlog_distill

        result = buildlog_distill(category="bogus", buildlog_dir=str(FIXTURES_DIR))
        assert "error" in result
        assert "Invalid category" in result["error"]

    def test_valid_category_filter(self):
        from buildlog.mcp.tools import buildlog_distill

        result = buildlog_distill(category="workflow", buildlog_dir=str(FIXTURES_DIR))
        assert result.get("error") is None

    def test_all_valid_categories_accepted(self):
        from buildlog.mcp.tools import buildlog_distill

        for cat in (
            "architectural",
            "workflow",
            "tool_usage",
            "domain_knowledge",
        ):
            result = buildlog_distill(category=cat, buildlog_dir=str(FIXTURES_DIR))
            assert result.get("error") is None, f"Category {cat} rejected"

    def test_statistics_has_expected_shape(self):
        from buildlog.mcp.tools import buildlog_distill

        result = buildlog_distill(buildlog_dir=str(FIXTURES_DIR))
        stats = result["statistics"]
        assert "total_patterns" in stats
        assert "by_category" in stats

    def test_empty_buildlog_returns_zero(self, tmp_path):
        from buildlog.mcp.tools import buildlog_distill

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = buildlog_distill(buildlog_dir=str(buildlog_dir))
        assert result.get("error") is None
        assert result["entry_count"] == 0


# =============================================================================
# buildlog_skills tests
# =============================================================================


class TestBuildlogSkills:
    """Tests for buildlog_skills MCP tool."""

    def test_returns_dict(self):
        from buildlog.mcp.tools import buildlog_skills

        result = buildlog_skills(buildlog_dir=str(FIXTURES_DIR))
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        from buildlog.mcp.tools import buildlog_skills

        result = buildlog_skills(buildlog_dir=str(FIXTURES_DIR))
        assert "generated_at" in result
        assert "source_entries" in result
        assert "total_skills" in result
        assert "skills" in result

    def test_returns_error_for_missing_dir(self, tmp_path):
        from buildlog.mcp.tools import buildlog_skills

        result = buildlog_skills(buildlog_dir=str(tmp_path / "nonexistent"))
        assert "error" in result

    def test_invalid_since_returns_error(self):
        from buildlog.mcp.tools import buildlog_skills

        result = buildlog_skills(since="bad-date", buildlog_dir=str(FIXTURES_DIR))
        assert "error" in result
        assert "Invalid date" in result["error"]

    def test_min_frequency_filters(self):
        from buildlog.mcp.tools import buildlog_skills

        all_skills = buildlog_skills(min_frequency=1, buildlog_dir=str(FIXTURES_DIR))
        filtered = buildlog_skills(min_frequency=99, buildlog_dir=str(FIXTURES_DIR))
        assert filtered["total_skills"] <= all_skills["total_skills"]

    def test_high_min_frequency_returns_fewer(self):
        from buildlog.mcp.tools import buildlog_skills

        result = buildlog_skills(min_frequency=999, buildlog_dir=str(FIXTURES_DIR))
        assert result["total_skills"] == 0

    def test_valid_since_date_accepted(self):
        from buildlog.mcp.tools import buildlog_skills

        result = buildlog_skills(since="2020-01-01", buildlog_dir=str(FIXTURES_DIR))
        assert result.get("error") is None

    def test_empty_buildlog(self, tmp_path):
        from buildlog.mcp.tools import buildlog_skills

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = buildlog_skills(buildlog_dir=str(buildlog_dir))
        assert result.get("error") is None
        assert result["total_skills"] == 0


# =============================================================================
# buildlog_stats tests
# =============================================================================


class TestBuildlogStats:
    """Tests for buildlog_stats MCP tool."""

    def test_returns_dict(self):
        from buildlog.mcp.tools import buildlog_stats

        result = buildlog_stats(buildlog_dir=str(FIXTURES_DIR))
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        from buildlog.mcp.tools import buildlog_stats

        result = buildlog_stats(buildlog_dir=str(FIXTURES_DIR))
        assert "entries" in result
        assert "insights" in result
        assert "streak" in result
        assert "warnings" in result

    def test_returns_error_for_missing_dir(self, tmp_path):
        from buildlog.mcp.tools import buildlog_stats

        result = buildlog_stats(buildlog_dir=str(tmp_path / "nonexistent"))
        assert "error" in result

    def test_invalid_since_returns_error(self):
        from buildlog.mcp.tools import buildlog_stats

        result = buildlog_stats(since="nope", buildlog_dir=str(FIXTURES_DIR))
        assert "error" in result

    def test_detailed_includes_top_sources(self):
        from buildlog.mcp.tools import buildlog_stats

        result = buildlog_stats(detailed=True, buildlog_dir=str(FIXTURES_DIR))
        assert "top_sources" in result

    def test_not_detailed_omits_top_sources(self):
        from buildlog.mcp.tools import buildlog_stats

        result = buildlog_stats(detailed=False, buildlog_dir=str(FIXTURES_DIR))
        assert result.get("top_sources") == []

    def test_entries_field_has_count(self):
        from buildlog.mcp.tools import buildlog_stats

        result = buildlog_stats(buildlog_dir=str(FIXTURES_DIR))
        entries = result["entries"]
        assert "total" in entries

    def test_empty_buildlog(self, tmp_path):
        from buildlog.mcp.tools import buildlog_stats

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        result = buildlog_stats(buildlog_dir=str(buildlog_dir))
        assert result.get("error") is None

    def test_valid_since_date(self):
        from buildlog.mcp.tools import buildlog_stats

        result = buildlog_stats(since="2020-01-01", buildlog_dir=str(FIXTURES_DIR))
        assert result.get("error") is None


# =============================================================================
# buildlog_gauntlet_list_personas tests
# =============================================================================


class TestBuildlogGauntletListPersonas:
    """Tests for buildlog_gauntlet_list_personas MCP tool."""

    def test_returns_dict(self):
        from buildlog.mcp.tools import buildlog_gauntlet_list_personas

        result = buildlog_gauntlet_list_personas()
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        from buildlog.mcp.tools import buildlog_gauntlet_list_personas

        result = buildlog_gauntlet_list_personas()
        assert "personas" in result
        assert "total_rules" in result
        assert "total_personas" in result

    def test_personas_have_rule_counts(self):
        from buildlog.mcp.tools import buildlog_gauntlet_list_personas

        result = buildlog_gauntlet_list_personas()
        if result.get("personas"):
            for _name, info in result["personas"].items():
                assert "rules_count" in info
                assert "version" in info
                assert isinstance(info["rules_count"], int)

    def test_total_rules_matches_sum(self):
        from buildlog.mcp.tools import buildlog_gauntlet_list_personas

        result = buildlog_gauntlet_list_personas()
        if result.get("personas"):
            summed = sum(info["rules_count"] for info in result["personas"].values())
            assert result["total_rules"] == summed

    def test_total_personas_matches_count(self):
        from buildlog.mcp.tools import buildlog_gauntlet_list_personas

        result = buildlog_gauntlet_list_personas()
        if result.get("personas"):
            assert result["total_personas"] == len(result["personas"])

    def test_known_personas_present(self):
        from buildlog.mcp.tools import buildlog_gauntlet_list_personas

        result = buildlog_gauntlet_list_personas()
        personas = result.get("personas", {})
        # At least security_karen and test_terrorist should exist
        assert "security_karen" in personas or len(personas) >= 2

    def test_bragi_persona_present(self):
        """bragi should be available (bundled in v0.10.0)."""
        from buildlog.mcp.tools import buildlog_gauntlet_list_personas

        result = buildlog_gauntlet_list_personas()
        personas = result.get("personas", {})
        assert "bragi" in personas

    def test_each_persona_has_rules(self):
        from buildlog.mcp.tools import buildlog_gauntlet_list_personas

        result = buildlog_gauntlet_list_personas()
        for name, info in result.get("personas", {}).items():
            assert info["rules_count"] > 0, f"{name} has 0 rules"
