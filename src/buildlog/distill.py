"""Extract and aggregate patterns from buildlog entries."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Iterator

# Valid improvement categories (lowercase for matching)
CATEGORIES = ["architectural", "workflow", "tool_usage", "domain_knowledge"]

# Map from markdown heading to normalized category name
CATEGORY_MAP = {
    "architectural": "architectural",
    "workflow": "workflow",
    "tool usage": "tool_usage",
    "tool_usage": "tool_usage",
    "domain knowledge": "domain_knowledge",
    "domain_knowledge": "domain_knowledge",
}


@dataclass
class Pattern:
    """A single improvement pattern extracted from a buildlog entry."""

    insight: str
    source: str
    date: str
    context: str = ""


@dataclass
class DistillResult:
    """Aggregated patterns from all buildlog entries."""

    extracted_at: str
    entry_count: int
    patterns: dict[str, list[dict]] = field(default_factory=dict)
    statistics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            "extracted_at": self.extracted_at,
            "entry_count": self.entry_count,
            "patterns": self.patterns,
            "statistics": self.statistics,
        }


def extract_title_and_context(content: str) -> str:
    """Extract a context description from the entry title."""
    # Look for "# Build Journal: <title>" pattern
    match = re.search(r"^#\s+Build Journal:\s*(.+)$", content, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        if title and title != "[TITLE]":
            return title
    return ""


def parse_improvements(content: str) -> dict[str, list[str]]:
    """Extract Improvements section from buildlog markdown.

    Args:
        content: The full markdown content of a buildlog entry.

    Returns:
        Dictionary mapping category names to lists of improvement insights.
    """
    result: dict[str, list[str]] = {cat: [] for cat in CATEGORIES}

    # Find the ## Improvements section
    improvements_match = re.search(
        r"^##\s+Improvements\s*\n(.*?)(?=^##\s+[^#]|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )

    if not improvements_match:
        return result

    improvements_section = improvements_match.group(1)

    # Find each ### Category subsection
    # Pattern matches ### followed by category name, then content until next ### or end
    category_pattern = re.compile(
        r"^###\s+([^\n]+)\s*\n(.*?)(?=^###|\Z)", re.MULTILINE | re.DOTALL
    )

    for category_match in category_pattern.finditer(improvements_section):
        raw_category = category_match.group(1).strip().lower()
        category_content = category_match.group(2)

        # Normalize category name
        normalized = CATEGORY_MAP.get(raw_category)
        if not normalized:
            continue

        # Extract bullet points (lines starting with - )
        bullet_pattern = re.compile(r"^\s*-\s+(.+)$", re.MULTILINE)
        for bullet_match in bullet_pattern.finditer(category_content):
            insight = bullet_match.group(1).strip()
            # Skip placeholder text
            if insight.startswith("[") and insight.endswith("]"):
                continue
            if insight.startswith("e.g.,"):
                continue
            if insight:
                result[normalized].append(insight)

    return result


def parse_date_from_filename(filename: str) -> str | None:
    """Extract date from buildlog filename.

    Expected format: YYYY-MM-DD-slug.md
    """
    match = re.match(r"^(\d{4}-\d{2}-\d{2})-", filename)
    if match:
        return match.group(1)
    return None


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
    pattern = "20??-??-??-*.md"

    for entry_path in sorted(buildlog_dir.glob(pattern)):
        date_str = parse_date_from_filename(entry_path.name)
        if not date_str:
            continue

        if since:
            try:
                entry_date = date.fromisoformat(date_str)
                if entry_date < since:
                    continue
            except ValueError:
                warnings.warn(f"Invalid date in filename: {entry_path.name}")
                continue

        yield entry_path, date_str


def distill_all(
    buildlog_dir: Path,
    since: date | None = None,
    category_filter: str | None = None,
) -> DistillResult:
    """Parse all buildlog entries and aggregate patterns.

    Args:
        buildlog_dir: Path to the buildlog directory.
        since: If provided, only include entries from this date onward.
        category_filter: If provided, only include patterns from this category.

    Returns:
        DistillResult with aggregated patterns and statistics.
    """
    patterns: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}
    by_month: dict[str, int] = {}
    entry_count = 0

    for entry_path, date_str in iter_buildlog_entries(buildlog_dir, since):
        try:
            content = entry_path.read_text(encoding="utf-8")
        except Exception as e:
            warnings.warn(f"Failed to read {entry_path}: {e}")
            continue

        entry_count += 1
        context = extract_title_and_context(content)

        # Track by month
        month_key = date_str[:7]  # YYYY-MM
        by_month[month_key] = by_month.get(month_key, 0) + 1

        # Parse improvements
        try:
            improvements = parse_improvements(content)
        except Exception as e:
            warnings.warn(f"Failed to parse improvements in {entry_path}: {e}")
            continue

        # Add patterns with metadata
        source = str(entry_path)
        for category, insights in improvements.items():
            for insight in insights:
                patterns[category].append(
                    {
                        "insight": insight,
                        "source": source,
                        "date": date_str,
                        "context": context,
                    }
                )

    # Apply category filter if specified
    if category_filter:
        filtered_patterns = {category_filter: patterns.get(category_filter, [])}
        patterns = filtered_patterns

    # Calculate statistics
    by_category = {cat: len(items) for cat, items in patterns.items()}
    total_patterns = sum(by_category.values())

    return DistillResult(
        extracted_at=datetime.utcnow().isoformat() + "Z",
        entry_count=entry_count,
        patterns=patterns,
        statistics={
            "total_patterns": total_patterns,
            "by_category": by_category,
            "by_month": dict(sorted(by_month.items())),
        },
    )


def format_output(result: DistillResult, fmt: str = "json") -> str:
    """Format the distill result as JSON or YAML.

    Args:
        result: The DistillResult to format.
        fmt: Output format, either "json" or "yaml".

    Returns:
        Formatted string representation.
    """
    import json

    data = result.to_dict()

    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    elif fmt == "yaml":
        try:
            import yaml

            return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except ImportError:
            raise ImportError(
                "PyYAML is required for YAML output. Install it with: pip install pyyaml"
            )
    else:
        raise ValueError(f"Unknown format: {fmt}")
