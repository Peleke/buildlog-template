"""Statistics and analytics for buildlog entries."""

from __future__ import annotations

__all__ = [
    "BuildlogStats",
    "calculate_stats",
    "format_dashboard",
    "format_json",
]

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from itertools import takewhile
from pathlib import Path
from typing import Final, NamedTuple, TypedDict

from buildlog.distill import (
    CATEGORIES,
    extract_title_and_context,
    iter_buildlog_entries,
    parse_improvements,
)

logger = logging.getLogger(__name__)

# Quality thresholds
TOP_SOURCES_LIMIT: Final[int] = 5
RECENT_ENTRY_THRESHOLD_DAYS: Final[int] = 7


# TypedDict definitions for precise return types
class EntryStatsDict(TypedDict):
    """Type for entry statistics dictionary."""

    total: int
    this_week: int
    this_month: int
    with_improvements: int
    coverage_percent: int


class InsightStatsDict(TypedDict):
    """Type for insight statistics dictionary."""

    total: int
    by_category: dict[str, int]


class StreakStatsDict(TypedDict):
    """Type for streak statistics dictionary."""

    current: int
    longest: int


class PipelineStatsDict(TypedDict):
    """Type for pipeline statistics dictionary."""

    last_distill: str | None
    last_skills: str | None
    last_export: str | None


class SourceDict(TypedDict):
    """Type for source dictionary."""

    name: str
    insights: int


class BuildlogStatsDict(TypedDict):
    """Type for full buildlog stats dictionary."""

    generated_at: str
    entries: EntryStatsDict
    insights: InsightStatsDict
    top_sources: list[SourceDict]
    pipeline: PipelineStatsDict
    streak: StreakStatsDict
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class EntryStats:
    """Statistics about buildlog entries."""

    total: int = 0
    this_week: int = 0
    this_month: int = 0
    with_improvements: int = 0
    coverage_percent: int = 0


@dataclass(frozen=True, slots=True)
class InsightStats:
    """Statistics about insights/learnings.

    Note: frozen=True prevents attribute reassignment but dict contents
    are still mutable (Python limitation). Treat as immutable by convention.
    """

    total: int = 0
    by_category: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StreakStats:
    """Statistics about entry streaks."""

    current: int = 0
    longest: int = 0


@dataclass(frozen=True, slots=True)
class PipelineStats:
    """Statistics about the knowledge pipeline."""

    last_distill: str | None = None
    last_skills: str | None = None
    last_export: str | None = None


class ParsedEntry(NamedTuple):
    """An immutable parsed buildlog entry."""

    path: Path
    name: str
    entry_date: date | None
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
    top_sources: list[SourceDict]
    pipeline: PipelineStats
    streak: StreakStats
    warnings: list[str]


def parse_date_from_string(date_str: str) -> date | None:
    """Parse a date string like '2026-01-15' into a date object."""
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None


def _parse_entry(path: Path, date_str: str) -> ParsedEntry | None:
    """Parse a buildlog entry file into an immutable structure.

    Args:
        path: Path to the entry file.
        date_str: Date string extracted from filename (YYYY-MM-DD).

    Returns:
        ParsedEntry or None if parsing fails.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read %s: %s", path, e)
        return None

    title = extract_title_and_context(content)
    if not title:
        title = "(untitled)"

    insights = parse_improvements(content)
    has_improvements = any(len(items) > 0 for items in insights.values())

    return ParsedEntry(
        path=path,
        name=path.name,
        entry_date=parse_date_from_string(date_str),
        title=title,
        has_improvements=has_improvements,
        insights=insights,
    )


def calculate_streak(entry_dates: list[date]) -> tuple[int, int]:
    """Calculate current and longest streak of consecutive days with entries.

    Args:
        entry_dates: List of dates with entries.

    Returns:
        Tuple of (current_streak, longest_streak)
    """
    if not entry_dates:
        return 0, 0

    unique_dates = sorted(set(entry_dates), reverse=True)
    if not unique_dates:
        return 0, 0

    today = date.today()

    # Calculate current streak using functional approach
    current_streak = 0
    if unique_dates[0] >= today - timedelta(days=1):
        consecutive = list(
            takewhile(
                lambda pair: pair[0] == 0
                or unique_dates[pair[0] - 1] - unique_dates[pair[0]]
                == timedelta(days=1),
                enumerate(unique_dates),
            )
        )
        current_streak = len(consecutive)

    # Calculate longest streak
    sorted_dates = sorted(unique_dates)

    def streak_lengths(dates: list[date]) -> list[int]:
        """Generate lengths of consecutive date runs."""
        if not dates:
            return [0]
        lengths: list[int] = []
        current_run = 1
        for i in range(1, len(dates)):
            if dates[i] - dates[i - 1] == timedelta(days=1):
                current_run += 1
            else:
                lengths.append(current_run)
                current_run = 1
        lengths.append(current_run)
        return lengths

    longest_streak = max(streak_lengths(sorted_dates), default=1)

    return current_streak, longest_streak


def _check_quality(entries: list[ParsedEntry]) -> list[str]:
    """Generate quality warnings for entries."""
    warnings: list[str] = []

    empty_improvements = [e for e in entries if not e.has_improvements]
    if empty_improvements:
        warnings.append(
            f"{len(empty_improvements)} entries have empty Improvements sections"
        )

    if entries:
        entry_dates = [e.entry_date for e in entries if e.entry_date]
        if entry_dates:
            most_recent = max(entry_dates)
            days_since = (date.today() - most_recent).days
            if days_since > RECENT_ENTRY_THRESHOLD_DAYS:
                warnings.append(
                    f"No entries in last {RECENT_ENTRY_THRESHOLD_DAYS} days "
                    f"(last entry: {days_since} days ago)"
                )

    return warnings


def _aggregate_insights(entries: list[ParsedEntry]) -> tuple[dict[str, int], int]:
    """Aggregate insight counts from parsed entries.

    Returns:
        Tuple of (by_category dict, total count)
    """
    insight_totals: dict[str, int] = {cat: 0 for cat in CATEGORIES}

    for entry in entries:
        for category, items in entry.insights.items():
            if category in insight_totals:
                insight_totals[category] += len(items)

    total_insights = sum(insight_totals.values())
    return insight_totals, total_insights


def _compute_top_sources(entries: list[ParsedEntry]) -> list[SourceDict]:
    """Compute top sources by insight count."""
    entries_with_insights = [
        (e, e.insight_count) for e in entries if e.insight_count > 0
    ]
    entries_with_insights.sort(key=lambda x: x[1], reverse=True)
    return [
        SourceDict(name=e.name, insights=count)
        for e, count in entries_with_insights[:TOP_SOURCES_LIMIT]
    ]


def calculate_stats(
    buildlog_dir: Path, since_date: date | None = None
) -> BuildlogStats:
    """Calculate all statistics for a buildlog directory.

    Args:
        buildlog_dir: Path to the buildlog directory.
        since_date: If provided, only include entries from this date onward.

    Returns:
        BuildlogStats with aggregated statistics.
    """
    # Parse all entries using functional map/filter pattern
    parsed_or_none = [
        _parse_entry(entry_path, date_str)
        for entry_path, date_str in iter_buildlog_entries(
            buildlog_dir, since=since_date
        )
    ]
    entries = [e for e in parsed_or_none if e is not None]

    # Calculate date-based stats
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)

    entry_dates = [e.entry_date for e in entries if e.entry_date]

    this_week = sum(1 for d in entry_dates if d and d >= week_ago)  # type: ignore[misc]
    this_month = sum(1 for d in entry_dates if d and d >= month_start)  # type: ignore[misc]

    with_improvements = sum(1 for e in entries if e.has_improvements)
    coverage_percent = int((with_improvements / len(entries) * 100) if entries else 0)

    # Calculate insight stats
    insight_totals, total_insights = _aggregate_insights(entries)

    # Calculate top sources
    top_sources = _compute_top_sources(entries)

    # Calculate streaks
    current_streak, longest_streak = calculate_streak(entry_dates)

    # Generate warnings
    warnings = _check_quality(entries)

    if not entries:
        if since_date:
            warnings.insert(0, f"No entries found since {since_date}")
        else:
            warnings.insert(0, "No buildlog entries found")

    return BuildlogStats(
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
        pipeline=PipelineStats(),
        streak=StreakStats(
            current=current_streak,
            longest=longest_streak,
        ),
        warnings=warnings,
    )


def format_dashboard(stats: BuildlogStats, detailed: bool = False) -> str:
    """Format stats as a terminal dashboard.

    Args:
        stats: The BuildlogStats to format.
        detailed: If True, include more details like top sources.

    Returns:
        Formatted string for terminal output.
    """
    lines: list[str] = []

    lines.append("Buildlog Statistics")
    lines.append("=" * 50)
    lines.append("")

    # Entry stats
    e = stats.entries
    lines.append(
        f"Entries: {e.total} total ({e.this_week} this week, {e.this_month} this month)"
    )
    lines.append(f"Coverage: {e.coverage_percent}% have Improvements filled out")
    lines.append("")

    # Insights by category
    lines.append("By Category:")
    for category, count in stats.insights.by_category.items():
        display_name = category.replace("_", " ").title()
        lines.append(f"  {display_name:<20} {count:>3} insights")

    lines.append("  " + "-" * 26)
    lines.append(f"  {'Total':<20} {stats.insights.total:>3} insights")
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


def stats_to_dict(stats: BuildlogStats) -> BuildlogStatsDict:
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
    """Format stats as JSON.

    Args:
        stats: The BuildlogStats to format.

    Returns:
        JSON string.
    """
    return json.dumps(stats_to_dict(stats), indent=2)
