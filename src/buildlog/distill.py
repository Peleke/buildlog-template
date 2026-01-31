"""Extract and aggregate patterns from buildlog entries."""

from __future__ import annotations

__all__ = [
    "CATEGORIES",
    "DistillResult",
    "distill_all",
    "format_output",
    "parse_improvements",
    "parse_improvements_llm",
    "parse_date_from_filename",
    "iter_buildlog_entries",
]

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypedDict

if TYPE_CHECKING:
    from buildlog.llm import ExtractedRule, LLMBackend

logger = logging.getLogger(__name__)

# Valid improvement categories (lowercase for matching)
CATEGORIES: Final[tuple[str, ...]] = (
    "architectural",
    "workflow",
    "tool_usage",
    "domain_knowledge",
)

# Map from markdown heading to normalized category name
CATEGORY_MAP: Final[dict[str, str]] = {
    "architectural": "architectural",
    "workflow": "workflow",
    "tool usage": "tool_usage",
    "tool_usage": "tool_usage",
    "domain knowledge": "domain_knowledge",
    "domain_knowledge": "domain_knowledge",
}

# File matching pattern for buildlog entries
BUILDLOG_GLOB_PATTERN: Final[str] = "20??-??-??-*.md"

# Type definitions
OutputFormat = Literal["json", "yaml"]


class PatternDict(TypedDict):
    """Type for a single pattern dictionary."""

    insight: str
    source: str
    date: str
    context: str


class StatisticsDict(TypedDict):
    """Type for statistics dictionary."""

    total_patterns: int
    by_category: dict[str, int]
    by_month: dict[str, int]


class DistillResultDict(TypedDict):
    """Type for full distill result dictionary."""

    extracted_at: str
    entry_count: int
    patterns: dict[str, list[PatternDict]]
    statistics: StatisticsDict


@dataclass
class DistillResult:
    """Aggregated patterns from all buildlog entries."""

    extracted_at: str
    entry_count: int
    patterns: dict[str, list[PatternDict]] = field(default_factory=dict)
    statistics: StatisticsDict = field(default_factory=dict)  # type: ignore[assignment]

    def to_dict(self) -> DistillResultDict:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            "extracted_at": self.extracted_at,
            "entry_count": self.entry_count,
            "patterns": self.patterns,
            "statistics": self.statistics,
        }


def _is_valid_insight(insight: str) -> bool:
    """Filter predicate for valid insights (not placeholders)."""
    if not insight:
        return False
    if insight.startswith("[") and insight.endswith("]"):
        return False
    if insight.startswith("e.g.,"):
        return False
    return True


def extract_title_and_context(content: str) -> str:
    """Extract a context description from the entry title."""
    match = re.search(r"^#\s+Build Journal:\s*(.+)$", content, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        if title and title != "[TITLE]":
            return title
    return ""


def _parse_bullet_content(category_content: str) -> list[str]:
    """Parse bullet points from category content, handling multi-line bullets.

    A bullet can span multiple lines if continuation lines are indented.
    Example:
        - This is a long insight that
          continues on the next line

    Returns:
        List of complete bullet point texts.
    """
    bullets: list[str] = []
    current_bullet: list[str] = []

    for line in category_content.split("\n"):
        # New bullet point starts with optional whitespace, dash, space, then content
        bullet_match = re.match(r"^\s*-\s+(.+)$", line)
        if bullet_match:
            # Save previous bullet if exists
            if current_bullet:
                bullets.append(" ".join(current_bullet))
            current_bullet = [bullet_match.group(1).strip()]
        elif current_bullet and line.strip():
            # Continuation line: non-empty, not a new bullet
            # Must be indented (starts with whitespace) to be a continuation
            if line.startswith((" ", "\t")):
                current_bullet.append(line.strip())
            # Otherwise it's unrelated content, ignore it

    # Don't forget the last bullet
    if current_bullet:
        bullets.append(" ".join(current_bullet))

    return bullets


def parse_improvements(content: str) -> dict[str, list[str]]:
    """Extract Improvements section from buildlog markdown.

    Args:
        content: The full markdown content of a buildlog entry.

    Returns:
        Dictionary mapping category names to lists of improvement insights.
    """
    result: dict[str, list[str]] = {cat: [] for cat in CATEGORIES}

    # Stop at any H1 or H2 header (not H3+), or end of string
    improvements_match = re.search(
        r"^##\s+Improvements\s*\n(.*?)(?=^#{1,2}\s|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )

    if not improvements_match:
        return result

    improvements_section = improvements_match.group(1)

    # Match H3 headers but NOT H4+ (use negative lookahead for 4th #)
    category_pattern = re.compile(
        r"^###(?!#)\s+([^\n]+)\s*\n(.*?)(?=^###(?!#)|\Z)", re.MULTILINE | re.DOTALL
    )

    for category_match in category_pattern.finditer(improvements_section):
        raw_category = category_match.group(1).strip().lower()
        normalized = CATEGORY_MAP.get(raw_category)
        if not normalized:
            continue

        category_content = category_match.group(2)
        bullets = _parse_bullet_content(category_content)
        result[normalized] = list(filter(_is_valid_insight, bullets))

    return result


def parse_improvements_llm(content: str, backend: LLMBackend) -> list[ExtractedRule]:
    """Extract improvements using an LLM backend for richer extraction.

    Sends the Improvements section to the LLM for structured extraction
    of rules with severity, scope, applicability, and defensibility fields.

    Args:
        content: The full markdown content of a buildlog entry.
        backend: An LLM backend implementing the LLMBackend protocol.

    Returns:
        List of ExtractedRule objects with rich metadata.
    """
    # Extract the Improvements section
    improvements_match = re.search(
        r"^##\s+Improvements\s*\n(.*?)(?=^#{1,2}\s|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )

    if not improvements_match:
        return []

    improvements_text = improvements_match.group(1).strip()
    if not improvements_text:
        return []

    return backend.extract_rules(improvements_text)


def parse_date_from_filename(filename: str) -> str | None:
    """Extract date from buildlog filename (YYYY-MM-DD-slug.md format)."""
    match = re.match(r"^(\d{4}-\d{2}-\d{2})-", filename)
    return match.group(1) if match else None


def _extract_month_key(date_str: str) -> str:
    """Extract YYYY-MM month key from YYYY-MM-DD date string."""
    return date_str[:7]


def iter_buildlog_entries(
    buildlog_dir: Path, since: date | None = None
) -> Iterator[tuple[Path, str]]:
    """Iterate over buildlog entries, optionally filtered by date.

    Args:
        buildlog_dir: Path to the buildlog directory.
        since: If provided, only yield entries from this date onward.

    Yields:
        Tuples of (file_path, date_string) for each matching entry.
    """
    for entry_path in sorted(buildlog_dir.glob(BUILDLOG_GLOB_PATTERN)):
        date_str = parse_date_from_filename(entry_path.name)
        if not date_str:
            continue

        # Always validate the date, not just when filtering
        try:
            entry_date = date.fromisoformat(date_str)
        except ValueError:
            logger.warning("Invalid date in filename: %s", entry_path.name)
            continue

        if since and entry_date < since:
            continue

        yield entry_path, date_str


def _create_patterns_for_entry(
    improvements: dict[str, list[str]],
    source: str,
    date_str: str,
    context: str,
) -> dict[str, list[PatternDict]]:
    """Create pattern dicts from improvements - pure function."""
    return {
        category: [
            PatternDict(
                insight=insight,
                source=source,
                date=date_str,
                context=context,
            )
            for insight in insights
        ]
        for category, insights in improvements.items()
    }


def _merge_patterns(
    target: dict[str, list[PatternDict]],
    source: dict[str, list[PatternDict]],
) -> None:
    """Merge source patterns into target (mutates target)."""
    for category, patterns in source.items():
        if category in target:
            target[category].extend(patterns)


def _apply_category_filter(
    patterns: dict[str, list[PatternDict]],
    category: str | None,
) -> dict[str, list[PatternDict]]:
    """Filter patterns to single category if specified."""
    if category is None:
        return patterns
    return {category: patterns.get(category, [])}


def _compute_statistics(
    patterns: dict[str, list[PatternDict]],
    by_month: dict[str, int],
) -> StatisticsDict:
    """Compute statistics from aggregated patterns."""
    by_category = {cat: len(items) for cat, items in patterns.items()}
    return {
        "total_patterns": sum(by_category.values()),
        "by_category": by_category,
        "by_month": dict(sorted(by_month.items())),
    }


def distill_all(
    buildlog_dir: Path,
    since: date | None = None,
    category_filter: str | None = None,
    llm: bool = False,
) -> DistillResult:
    """Parse all buildlog entries and aggregate patterns.

    Args:
        buildlog_dir: Path to the buildlog directory.
        since: If provided, only include entries from this date onward.
        category_filter: If provided, only include patterns from this category.
        llm: If True and an LLM backend is available, use LLM extraction.
            Falls back to regex on failure or if no backend is available.

    Returns:
        DistillResult with aggregated patterns and statistics.
    """
    # Resolve LLM backend if requested
    llm_backend: LLMBackend | None = None
    if llm:
        from buildlog.llm import get_llm_backend

        llm_backend = get_llm_backend(buildlog_dir=buildlog_dir)
        if llm_backend is None:
            logger.warning(
                "--llm requested but no LLM provider available, using regex fallback"
            )

    patterns: dict[str, list[PatternDict]] = {cat: [] for cat in CATEGORIES}
    by_month: dict[str, int] = {}
    entry_count = 0

    for entry_path, date_str in iter_buildlog_entries(buildlog_dir, since):
        try:
            content = entry_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s: %s", entry_path, e)
            continue

        entry_count += 1
        context = extract_title_and_context(content)

        month_key = _extract_month_key(date_str)
        by_month[month_key] = by_month.get(month_key, 0) + 1

        # Try LLM extraction first, fall back to regex
        if llm_backend is not None:
            try:
                extracted = parse_improvements_llm(content, llm_backend)
                if extracted:
                    # Convert ExtractedRule objects to standard PatternDict format
                    for rule in extracted:
                        cat = (
                            rule.category
                            if rule.category in CATEGORIES
                            else "architectural"
                        )
                        if cat not in patterns:
                            patterns[cat] = []
                        patterns[cat].append(
                            PatternDict(
                                insight=rule.rule,
                                source=str(entry_path),
                                date=date_str,
                                context=context,
                            )
                        )
                    continue  # Skip regex if LLM succeeded
            except Exception as e:
                logger.warning(
                    "LLM extraction failed for %s, falling back to regex: %s",
                    entry_path,
                    e,
                )

        # Regex fallback (default behavior)
        try:
            improvements = parse_improvements(content)
        except re.error as e:
            logger.warning("Failed to parse improvements in %s: %s", entry_path, e)
            continue

        entry_patterns = _create_patterns_for_entry(
            improvements, str(entry_path), date_str, context
        )
        _merge_patterns(patterns, entry_patterns)

    patterns = _apply_category_filter(patterns, category_filter)
    statistics = _compute_statistics(patterns, by_month)

    return DistillResult(
        extracted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        entry_count=entry_count,
        patterns=patterns,
        statistics=statistics,
    )


def format_output(result: DistillResult, fmt: OutputFormat = "json") -> str:
    """Format the distill result as JSON or YAML.

    Args:
        result: The DistillResult to format.
        fmt: Output format, either "json" or "yaml".

    Returns:
        Formatted string representation.

    Raises:
        ValueError: If format is not recognized.
        ImportError: If PyYAML is required but not installed.
    """
    data = result.to_dict()

    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)

    if fmt == "yaml":
        try:
            import yaml
        except ImportError as e:
            raise ImportError(
                "PyYAML is required for YAML output. Install it with: pip install pyyaml"
            ) from e
        return yaml.dump(
            data, default_flow_style=False, allow_unicode=True, sort_keys=False
        )

    # This should be unreachable due to Literal type, but defensive coding
    raise ValueError(f"Unknown format: {fmt}")
