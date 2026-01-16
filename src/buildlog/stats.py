"""Statistics and analytics for buildlog entries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from buildlog.distill import (
    CATEGORIES,
    iter_buildlog_entries,
    parse_improvements,
    extract_title_and_context,
)


@dataclass
class EntryStats:
    """Statistics about buildlog entries."""

    total: int = 0
    this_week: int = 0
    this_month: int = 0
    with_improvements: int = 0
    coverage_percent: int = 0


@dataclass
class InsightStats:
    """Statistics about insights/learnings."""

    total: int = 0
    by_category: dict[str, int] = field(default_factory=dict)


@dataclass
class StreakStats:
    """Statistics about entry streaks."""

    current: int = 0
    longest: int = 0


@dataclass
class PipelineStats:
    """Statistics about the knowledge pipeline."""

    last_distill: str | None = None
    last_skills: str | None = None
    last_export: str | None = None


@dataclass
class ParsedEntry:
    """A parsed buildlog entry."""

    path: Path
    name: str
    date: date | None
    title: str
    has_improvements: bool
    insights: dict[str, list[str]]

    @property
    def insight_count(self) -> int:
        """Total number of insights in this entry."""
        return sum(len(items) for items in self.insights.values())


@dataclass
class BuildlogStats:
    """Complete statistics for a buildlog directory."""

    generated_at: str
    entries: EntryStats
    insights: InsightStats
    top_sources: list[dict[str, Any]]
    pipeline: PipelineStats
    streak: StreakStats
    warnings: list[str]


def parse_date_from_string(date_str: str) -> date | None:
    """Parse a date string like '2026-01-15' into a date object."""
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None


def parse_entry(path: Path, date_str: str) -> ParsedEntry:
    """Parse a buildlog entry file.

    Args:
        path: Path to the entry file.
        date_str: Date string extracted from filename (YYYY-MM-DD).
    """
    content = path.read_text(encoding="utf-8")

    # Extract title using distill module's function
    title = extract_title_and_context(content)
    if not title:
        title = "(untitled)"

    # Parse improvements using distill module's function
    insights = parse_improvements(content)

    # Check if any insights were found
    has_improvements = any(len(items) > 0 for items in insights.values())

    return ParsedEntry(
        path=path,
        name=path.name,
        date=parse_date_from_string(date_str),
        title=title,
        has_improvements=has_improvements,
        insights=insights,
    )


def calculate_streak(entry_dates: list[date]) -> tuple[int, int]:
    """
    Calculate current and longest streak of consecutive days with entries.

    Returns:
        Tuple of (current_streak, longest_streak)
    """
    if not entry_dates:
        return 0, 0

    # Remove duplicates and sort descending (most recent first)
    unique_dates = sorted(set(entry_dates), reverse=True)

    if not unique_dates:
        return 0, 0

    today = date.today()

    # Calculate current streak (must include today or yesterday to count)
    current_streak = 0
    if unique_dates[0] >= today - timedelta(days=1):
        current_streak = 1
        for i in range(1, len(unique_dates)):
            if unique_dates[i - 1] - unique_dates[i] == timedelta(days=1):
                current_streak += 1
            else:
                break

    # Calculate longest streak
    longest_streak = 1
    current_run = 1

    # Sort ascending for longest streak calculation
    sorted_dates = sorted(unique_dates)
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
            current_run += 1
            longest_streak = max(longest_streak, current_run)
        else:
            current_run = 1

    return current_streak, longest_streak


def check_quality(entries: list[ParsedEntry]) -> list[str]:
    """Generate quality warnings for entries."""
    warnings = []

    # Check for entries without improvements
    empty_improvements = [e for e in entries if not e.has_improvements]
    if empty_improvements:
        warnings.append(f"{len(empty_improvements)} entries have empty Improvements sections")

    # Check for no recent entries
    if entries:
        entry_dates = [e.date for e in entries if e.date]
        if entry_dates:
            most_recent = max(entry_dates)
            days_since = (date.today() - most_recent).days
            if days_since > 7:
                warnings.append(f"No entries in last 7 days (last entry: {days_since} days ago)")

    return warnings


def calculate_stats(
    buildlog_dir: Path, since_date: date | None = None
) -> BuildlogStats:
    """Calculate all statistics for a buildlog directory."""
    # Parse all entries using the distill module's iterator
    entries: list[ParsedEntry] = []

    for entry_path, date_str in iter_buildlog_entries(buildlog_dir, since=since_date):
        try:
            parsed = parse_entry(entry_path, date_str)
            entries.append(parsed)
        except Exception:
            # Skip entries that fail to parse
            continue

    # Calculate date-based stats
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)

    entry_dates = [e.date for e in entries if e.date]

    this_week = sum(1 for d in entry_dates if d and d >= week_ago)
    this_month = sum(1 for d in entry_dates if d and d >= month_start)

    with_improvements = sum(1 for e in entries if e.has_improvements)
    coverage_percent = int((with_improvements / len(entries) * 100) if entries else 0)

    # Calculate insight stats
    insight_totals: dict[str, int] = {cat: 0 for cat in CATEGORIES}

    for entry in entries:
        for category, items in entry.insights.items():
            if category in insight_totals:
                insight_totals[category] += len(items)

    total_insights = sum(insight_totals.values())

    # Calculate top sources
    entries_with_insights = [(e, e.insight_count) for e in entries if e.insight_count > 0]
    entries_with_insights.sort(key=lambda x: x[1], reverse=True)
    top_sources = [
        {"name": e.name, "insights": count}
        for e, count in entries_with_insights[:5]
    ]

    # Calculate streaks
    current_streak, longest_streak = calculate_streak(entry_dates)

    # Generate warnings
    warnings = check_quality(entries)

    # Check for empty buildlog
    if not entries:
        if since_date:
            warnings.insert(0, f"No entries found since {since_date}")
        else:
            warnings.insert(0, "No buildlog entries found")

    return BuildlogStats(
        generated_at=datetime.utcnow().isoformat() + "Z",
        entries=EntryStats(
            total=len(entries),
            this_week=this_week,
            this_month=this_month,
            with_improvements=with_improvements,
            coverage_percent=coverage_percent,
        ),
        insights=InsightStats(
            total=total_insights,
            by_category=insight_totals,
        ),
        top_sources=top_sources,
        pipeline=PipelineStats(),  # Pipeline stats would require additional file checks
        streak=StreakStats(
            current=current_streak,
            longest=longest_streak,
        ),
        warnings=warnings,
    )


def format_dashboard(stats: BuildlogStats, detailed: bool = False) -> str:
    """Format stats as a terminal dashboard."""
    lines = []

    lines.append("Buildlog Statistics")
    lines.append("=" * 50)
    lines.append("")

    # Entry stats
    e = stats.entries
    lines.append(f"Entries: {e.total} total ({e.this_week} this week, {e.this_month} this month)")
    lines.append(f"Coverage: {e.coverage_percent}% have Improvements filled out")
    lines.append("")

    # Insights by category
    lines.append("By Category:")
    i = stats.insights
    for category, count in i.by_category.items():
        # Format category name for display
        display_name = category.replace("_", " ").title()
        lines.append(f"  {display_name:<20} {count:>3} insights")

    lines.append("  " + "-" * 26)
    lines.append(f"  {'Total':<20} {i.total:>3} insights")
    lines.append("")

    # Top sources (if detailed or there are sources)
    if detailed and stats.top_sources:
        lines.append("Top Sources:")
        for idx, source in enumerate(stats.top_sources, 1):
            lines.append(f"  {idx}. {source['name']} ({source['insights']} insights)")
        lines.append("")

    # Quality warnings
    if stats.warnings:
        lines.append("Quality Warnings:")
        for warning in stats.warnings:
            lines.append(f"  - {warning}")
        lines.append("")

    # Streak
    s = stats.streak
    lines.append(f"Streak: {s.current} days (longest: {s.longest} days)")

    return "\n".join(lines)


def stats_to_dict(stats: BuildlogStats) -> dict[str, Any]:
    """Convert BuildlogStats to a JSON-serializable dictionary."""
    return {
        "generated_at": stats.generated_at,
        "entries": {
            "total": stats.entries.total,
            "this_week": stats.entries.this_week,
            "this_month": stats.entries.this_month,
            "with_improvements": stats.entries.with_improvements,
            "coverage_percent": stats.entries.coverage_percent,
        },
        "insights": {
            "total": stats.insights.total,
            "by_category": stats.insights.by_category,
        },
        "top_sources": stats.top_sources,
        "pipeline": {
            "last_distill": stats.pipeline.last_distill,
            "last_skills": stats.pipeline.last_skills,
            "last_export": stats.pipeline.last_export,
        },
        "streak": {
            "current": stats.streak.current,
            "longest": stats.streak.longest,
        },
        "warnings": stats.warnings,
    }


def format_json(stats: BuildlogStats) -> str:
    """Format stats as JSON."""
    return json.dumps(stats_to_dict(stats), indent=2)
