"""Tests for buildlog stats functionality."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from buildlog.stats import (
    BuildlogStats,
    calculate_stats,
    format_dashboard,
    format_json,
    calculate_streak,
)


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures."""
    return Path(__file__).parent / "fixtures" / "buildlog"


class TestCalculateStats:
    """Tests for calculate_stats function."""

    def test_counts_total_entries(self, fixtures_dir):
        """Should count all buildlog entries."""
        stats = calculate_stats(fixtures_dir)
        assert stats.entries.total == 4

    def test_calculates_coverage(self, fixtures_dir):
        """Should calculate percentage with filled Improvements."""
        stats = calculate_stats(fixtures_dir)
        # 3 out of 4 have improvements filled
        assert stats.entries.coverage_percent == 75

    def test_counts_insights_by_category(self, fixtures_dir):
        """Should count insights per category."""
        stats = calculate_stats(fixtures_dir)
        assert stats.insights.by_category["architectural"] == 5
        assert stats.insights.by_category["workflow"] == 4
        assert stats.insights.by_category["tool_usage"] == 4
        assert stats.insights.by_category["domain_knowledge"] == 6

    def test_calculates_total_insights(self, fixtures_dir):
        """Should sum all insights."""
        stats = calculate_stats(fixtures_dir)
        assert stats.insights.total == 19

    def test_identifies_top_sources(self, fixtures_dir):
        """Should rank entries by insight count."""
        stats = calculate_stats(fixtures_dir)
        top = stats.top_sources[0]
        assert top["name"] == "2026-01-01-test-entry.md"
        assert top["insights"] == 12

    def test_generates_warnings_for_empty_improvements(self, fixtures_dir):
        """Should warn about empty Improvements sections."""
        stats = calculate_stats(fixtures_dir)
        assert any("empty" in w.lower() for w in stats.warnings)

    def test_handles_empty_directory(self, tmp_path):
        """Should handle directory with no entries."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        stats = calculate_stats(buildlog_dir)
        assert stats.entries.total == 0
        assert stats.insights.total == 0


class TestCalculateStreak:
    """Tests for streak calculation."""

    def test_consecutive_days(self):
        """Should count consecutive days correctly."""
        today = date.today()
        dates = [today - timedelta(days=i) for i in range(5)]
        current, longest = calculate_streak(dates)
        assert current == 5
        assert longest == 5

    def test_broken_streak(self):
        """Should detect gap in streak."""
        today = date.today()
        # Gap of 2 days breaks the streak
        dates = [today, today - timedelta(days=3), today - timedelta(days=4)]
        current, longest = calculate_streak(dates)
        assert current == 1
        assert longest == 2

    def test_no_entries(self):
        """Should handle empty list."""
        current, longest = calculate_streak([])
        assert current == 0
        assert longest == 0

    def test_single_entry(self):
        """Should handle single entry."""
        current, longest = calculate_streak([date.today()])
        assert current == 1
        assert longest == 1


class TestFormatDashboard:
    """Tests for terminal dashboard formatting."""

    def test_includes_entry_count(self, fixtures_dir):
        """Should show entry count."""
        stats = calculate_stats(fixtures_dir)
        output = format_dashboard(stats)
        assert "4 total" in output

    def test_includes_coverage(self, fixtures_dir):
        """Should show coverage percentage."""
        stats = calculate_stats(fixtures_dir)
        output = format_dashboard(stats)
        assert "75%" in output

    def test_includes_category_breakdown(self, fixtures_dir):
        """Should show insights by category."""
        stats = calculate_stats(fixtures_dir)
        output = format_dashboard(stats)
        assert "Architectural" in output
        assert "Workflow" in output


class TestFormatJson:
    """Tests for JSON output formatting."""

    def test_valid_json(self, fixtures_dir):
        """Should produce valid JSON."""
        stats = calculate_stats(fixtures_dir)
        output = format_json(stats)
        parsed = json.loads(output)
        assert "entries" in parsed
        assert "insights" in parsed

    def test_includes_timestamp(self, fixtures_dir):
        """Should include generation timestamp."""
        stats = calculate_stats(fixtures_dir)
        output = format_json(stats)
        parsed = json.loads(output)
        assert "generated_at" in parsed
