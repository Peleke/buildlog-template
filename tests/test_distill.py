"""Tests for buildlog.distill module."""

import json
from datetime import date
from pathlib import Path

import pytest

from buildlog.distill import (
    CATEGORIES,
    distill_all,
    extract_title_and_context,
    format_output,
    parse_date_from_filename,
    parse_improvements,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "buildlog"


class TestParseImprovements:
    """Tests for parse_improvements function."""

    def test_parses_all_categories(self):
        """Should parse all four improvement categories."""
        content = """
## Improvements

### Architectural

- Use composition over inheritance
- Keep modules loosely coupled

### Workflow

- Write tests first

### Tool Usage

- Use IDE shortcuts

### Domain Knowledge

- HTTP 204 returns no body
"""
        result = parse_improvements(content)

        assert len(result["architectural"]) == 2
        assert len(result["workflow"]) == 1
        assert len(result["tool_usage"]) == 1
        assert len(result["domain_knowledge"]) == 1
        assert "Use composition over inheritance" in result["architectural"]

    def test_handles_missing_categories(self):
        """Should return empty lists for missing categories."""
        content = """
## Improvements

### Architectural

- One architectural insight

### Domain Knowledge

- One domain fact
"""
        result = parse_improvements(content)

        assert len(result["architectural"]) == 1
        assert len(result["workflow"]) == 0
        assert len(result["tool_usage"]) == 0
        assert len(result["domain_knowledge"]) == 1

    def test_handles_empty_improvements(self):
        """Should handle empty Improvements section."""
        content = """
## Improvements

### Architectural

### Workflow

### Tool Usage

### Domain Knowledge
"""
        result = parse_improvements(content)

        for cat in CATEGORIES:
            assert result[cat] == []

    def test_handles_no_improvements_section(self):
        """Should return empty when no Improvements section exists."""
        content = """
## The Goal

Build something.

## What We Built

Something.
"""
        result = parse_improvements(content)

        for cat in CATEGORIES:
            assert result[cat] == []

    def test_ignores_placeholder_text(self):
        """Should skip placeholder bullet points."""
        content = """
## Improvements

### Architectural

- [e.g., "Should have used a plugin architecture"]
- Real insight here

### Workflow

- e.g., "Run tests first"
- Another real insight
"""
        result = parse_improvements(content)

        assert len(result["architectural"]) == 1
        assert "Real insight here" in result["architectural"]
        assert len(result["workflow"]) == 1
        assert "Another real insight" in result["workflow"]

    def test_handles_tool_usage_with_space(self):
        """Should handle 'Tool Usage' heading with space."""
        content = """
## Improvements

### Tool Usage

- Use grep with context flag
"""
        result = parse_improvements(content)
        assert len(result["tool_usage"]) == 1

    def test_handles_domain_knowledge_with_space(self):
        """Should handle 'Domain Knowledge' heading with space."""
        content = """
## Improvements

### Domain Knowledge

- HTTP status codes matter
"""
        result = parse_improvements(content)
        assert len(result["domain_knowledge"]) == 1


class TestParseDateFromFilename:
    """Tests for parse_date_from_filename function."""

    def test_extracts_valid_date(self):
        """Should extract date from valid filename."""
        assert parse_date_from_filename("2026-01-15-my-entry.md") == "2026-01-15"
        assert parse_date_from_filename("2025-12-01-another.md") == "2025-12-01"

    def test_returns_none_for_invalid_filename(self):
        """Should return None for invalid filenames."""
        assert parse_date_from_filename("invalid.md") is None
        assert parse_date_from_filename("_TEMPLATE.md") is None
        assert parse_date_from_filename("2026-1-1-bad-date.md") is None


class TestExtractTitleAndContext:
    """Tests for extract_title_and_context function."""

    def test_extracts_title(self):
        """Should extract title from Build Journal header."""
        content = "# Build Journal: User Authentication API\n\nMore content..."
        assert extract_title_and_context(content) == "User Authentication API"

    def test_returns_empty_for_placeholder(self):
        """Should return empty string for placeholder title."""
        content = "# Build Journal: [TITLE]\n\nMore content..."
        assert extract_title_and_context(content) == ""

    def test_returns_empty_for_missing_title(self):
        """Should return empty string when no title found."""
        content = "# Some Other Header\n\nMore content..."
        assert extract_title_and_context(content) == ""


class TestDistillAll:
    """Tests for distill_all function."""

    def test_parses_well_formed_entry(self):
        """Should correctly parse a well-formed entry."""
        result = distill_all(FIXTURES_DIR)

        # Should find all entries
        assert result.entry_count >= 4

        # Should have patterns from all categories
        assert len(result.patterns["architectural"]) >= 3
        assert len(result.patterns["workflow"]) >= 2
        assert len(result.patterns["tool_usage"]) >= 2
        assert len(result.patterns["domain_knowledge"]) >= 3

    def test_filters_by_date(self):
        """Should filter entries by since date."""
        # Only include entries from February 2026 onward
        since = date(2026, 2, 1)
        result = distill_all(FIXTURES_DIR, since=since)

        # Should only include the February entry
        assert result.entry_count == 1
        assert len(result.patterns["architectural"]) == 1
        assert "Event sourcing is overkill" in result.patterns["architectural"][0]["insight"]

    def test_filters_by_category(self):
        """Should filter to specific category."""
        result = distill_all(FIXTURES_DIR, category_filter="architectural")

        # Should only have architectural patterns
        assert "architectural" in result.patterns
        assert len(result.patterns) == 1
        assert len(result.patterns["architectural"]) >= 3

    def test_tracks_source_and_date(self):
        """Should track source file and date for each pattern."""
        result = distill_all(FIXTURES_DIR)

        for category, patterns in result.patterns.items():
            for pattern in patterns:
                assert "source" in pattern
                assert "date" in pattern
                assert "insight" in pattern
                assert pattern["date"].startswith("202")

    def test_calculates_statistics(self):
        """Should calculate accurate statistics."""
        result = distill_all(FIXTURES_DIR)

        assert "by_category" in result.statistics
        assert "by_month" in result.statistics
        assert "total_patterns" in result.statistics

        # Total should be sum of categories
        total = sum(result.statistics["by_category"].values())
        assert result.statistics["total_patterns"] == total


class TestFormatOutput:
    """Tests for format_output function."""

    def test_json_output(self):
        """Should produce valid JSON."""
        result = distill_all(FIXTURES_DIR)
        output = format_output(result, "json")

        # Should be valid JSON
        data = json.loads(output)
        assert "extracted_at" in data
        assert "patterns" in data
        assert "statistics" in data

    def test_yaml_output(self):
        """Should produce valid YAML."""
        import yaml

        result = distill_all(FIXTURES_DIR)
        output = format_output(result, "yaml")

        # Should be valid YAML
        data = yaml.safe_load(output)
        assert "extracted_at" in data
        assert "patterns" in data
        assert "statistics" in data

    def test_invalid_format_raises(self):
        """Should raise ValueError for invalid format."""
        result = distill_all(FIXTURES_DIR)

        with pytest.raises(ValueError, match="Unknown format"):
            format_output(result, "xml")
