"""Tests for buildlog stats functionality."""

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.stats import (
    BuildlogStats,
    calculate_stats,
    calculate_streak,
    format_dashboard,
    format_json,
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


class TestCalculateStreakWithMockedDate:
    """Tests for streak calculation with controlled dates (no flakiness)."""

    def test_consecutive_days_with_mocked_today(self):
        """Should count consecutive days correctly with mocked date."""
        # Fix "today" to 2026-01-15 to avoid midnight flakiness
        fixed_today = date(2026, 1, 15)
        dates = [fixed_today - timedelta(days=i) for i in range(5)]

        with patch("buildlog.stats.date") as mock_date:
            mock_date.today.return_value = fixed_today
            mock_date.fromisoformat = date.fromisoformat
            current, longest = calculate_streak(dates)

        assert current == 5
        assert longest == 5

    def test_old_entries_no_current_streak_with_mocked_today(self):
        """Old entries should have no current streak."""
        fixed_today = date(2026, 1, 15)
        # Entries from a week ago - no current streak
        dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]

        with patch("buildlog.stats.date") as mock_date:
            mock_date.today.return_value = fixed_today
            mock_date.fromisoformat = date.fromisoformat
            current, longest = calculate_streak(dates)

        assert current == 0  # Too old for current streak
        assert longest == 3  # But still the longest run

    def test_yesterday_counts_as_current(self):
        """Entry from yesterday should count toward current streak."""
        fixed_today = date(2026, 1, 15)
        dates = [date(2026, 1, 14)]  # Just yesterday

        with patch("buildlog.stats.date") as mock_date:
            mock_date.today.return_value = fixed_today
            mock_date.fromisoformat = date.fromisoformat
            current, longest = calculate_streak(dates)

        assert current == 1  # Yesterday counts
        assert longest == 1


class TestFormatDashboardDetailed:
    """Tests for format_dashboard with detailed=True."""

    def test_detailed_includes_top_sources(self, fixtures_dir):
        """Detailed mode should show top sources."""
        stats = calculate_stats(fixtures_dir)
        output = format_dashboard(stats, detailed=True)
        assert "Top Sources:" in output
        assert "2026-01-01-test-entry.md" in output

    def test_detailed_includes_warnings(self, fixtures_dir):
        """Detailed mode should show quality warnings."""
        stats = calculate_stats(fixtures_dir)
        output = format_dashboard(stats, detailed=True)
        assert "Quality Warnings:" in output


class TestErrorHandling:
    """Tests for error handling edge cases."""

    def test_nonexistent_directory_raises(self):
        """Non-existent directory should raise an error or return empty."""
        nonexistent = Path("/nonexistent/path/that/does/not/exist")
        # The glob will return empty, not raise, so we get empty stats
        stats = calculate_stats(nonexistent)
        assert stats.entries.total == 0
        assert "No buildlog entries found" in stats.warnings

    def test_handles_invalid_utf8_file(self, tmp_path):
        """Should skip files with invalid UTF-8 gracefully."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Create a valid entry
        valid_file = buildlog_dir / "2026-01-01-valid.md"
        valid_file.write_text(
            "# Build Journal: Valid\n\n## Improvements\n\n### Architectural\n\n- Valid insight"
        )

        # Create a file with invalid UTF-8 bytes
        invalid_file = buildlog_dir / "2026-01-02-invalid-utf8.md"
        invalid_file.write_bytes(
            b"# Build Journal: Invalid\n\n\xff\xfe Invalid UTF-8 bytes"
        )

        stats = calculate_stats(buildlog_dir)
        # Should process the valid file and skip the invalid one
        assert stats.entries.total == 1

    def test_handles_invalid_date_in_filename(self, tmp_path):
        """Should skip files with invalid dates in filename."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Create a valid entry
        valid_file = buildlog_dir / "2026-01-15-valid.md"
        valid_file.write_text(
            "# Build Journal: Valid\n\n## Improvements\n\n### Architectural\n\n- Insight"
        )

        # Create a file with impossible date (matches glob but fails fromisoformat)
        invalid_date_file = buildlog_dir / "2026-99-99-impossible-date.md"
        invalid_date_file.write_text("# Build Journal: Invalid Date\n\nContent")

        stats = calculate_stats(buildlog_dir)
        # Should only count the valid entry
        assert stats.entries.total == 1

    def test_since_date_in_future(self, fixtures_dir):
        """Future since_date should return no entries with warning."""
        future_date = date(2099, 1, 1)
        stats = calculate_stats(fixtures_dir, since_date=future_date)
        assert stats.entries.total == 0
        assert any("No entries found since" in w for w in stats.warnings)
