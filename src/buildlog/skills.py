"""Generate agent-consumable skills from distilled patterns."""

from __future__ import annotations

__all__ = [
    "Skill",
    "SkillSet",
    "generate_skills",
    "format_skills",
]

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, Literal, TypedDict

from buildlog.distill import CATEGORIES, PatternDict, distill_all
from buildlog.embeddings import EmbeddingBackend, get_backend, get_default_backend

logger = logging.getLogger(__name__)

# Configuration constants
MIN_SIMILARITY_THRESHOLD: Final[float] = 0.7
HIGH_CONFIDENCE_FREQUENCY: Final[int] = 3
HIGH_CONFIDENCE_RECENCY_DAYS: Final[int] = 30
MEDIUM_CONFIDENCE_FREQUENCY: Final[int] = 2

# Type definitions
OutputFormat = Literal["yaml", "json", "markdown", "rules", "settings"]
ConfidenceLevel = Literal["high", "medium", "low"]


class SkillDict(TypedDict):
    """Type for skill dictionary representation."""

    id: str
    category: str
    rule: str
    frequency: int
    confidence: ConfidenceLevel
    sources: list[str]
    tags: list[str]


class SkillSetDict(TypedDict):
    """Type for full skill set dictionary."""

    generated_at: str
    source_entries: int
    total_skills: int
    skills: dict[str, list[SkillDict]]


@dataclass
class Skill:
    """A codified learning from buildlog patterns.

    Represents a single actionable rule derived from one or more
    similar insights across buildlog entries.
    """

    id: str
    category: str
    rule: str
    frequency: int
    confidence: ConfidenceLevel
    sources: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> SkillDict:
        """Convert to dictionary for serialization."""
        return SkillDict(
            id=self.id,
            category=self.category,
            rule=self.rule,
            frequency=self.frequency,
            confidence=self.confidence,
            sources=self.sources,
            tags=self.tags,
        )


@dataclass
class SkillSet:
    """Collection of skills with metadata."""

    generated_at: str
    source_entries: int
    skills: dict[str, list[Skill]] = field(default_factory=dict)

    @property
    def total_skills(self) -> int:
        """Total number of skills across all categories."""
        return sum(len(skills) for skills in self.skills.values())

    def to_dict(self) -> SkillSetDict:
        """Convert to dictionary for serialization."""
        return SkillSetDict(
            generated_at=self.generated_at,
            source_entries=self.source_entries,
            total_skills=self.total_skills,
            skills={
                cat: [s.to_dict() for s in skills]
                for cat, skills in self.skills.items()
            },
        )


def _generate_skill_id(category: str, rule: str) -> str:
    """Generate a stable ID for a skill.

    The ID is deterministic - same category+rule always produces same ID.
    Uses SHA-256 (truncated to 10 chars = 40 bits) for collision resistance.
    At 40 bits, collision probability is ~0.5 after ~1 million unique rules.
    """
    prefix_map = {
        "architectural": "arch",
        "workflow": "wf",
        "tool_usage": "tool",
        "domain_knowledge": "dk",
    }
    prefix = prefix_map.get(category, "sk")
    # SHA-256 is more robust than MD5; 10 chars provides good collision resistance
    rule_hash = hashlib.sha256(rule.lower().encode()).hexdigest()[:10]
    return f"{prefix}-{rule_hash}"




def _calculate_confidence(
    frequency: int,
    most_recent_date: date | None,
    reference_date: date | None = None,
) -> ConfidenceLevel:
    """Calculate confidence level based on frequency and recency.

    Args:
        frequency: How many times this pattern was seen.
        most_recent_date: Date of most recent occurrence.
        reference_date: Date to calculate recency from. Defaults to today.
            Pass explicitly for deterministic testing.

    Returns:
        Confidence level: high, medium, or low.

    Confidence is determined by:
        - high: frequency >= 3 AND seen within last 30 days
        - medium: frequency >= 2
        - low: frequency < 2 or no frequency data
    """
    if reference_date is None:
        reference_date = date.today()

    recency_days = float("inf")
    if most_recent_date:
        recency_days = (reference_date - most_recent_date).days

    if frequency >= HIGH_CONFIDENCE_FREQUENCY and recency_days < HIGH_CONFIDENCE_RECENCY_DAYS:
        return "high"
    elif frequency >= MEDIUM_CONFIDENCE_FREQUENCY:
        return "medium"
    else:
        return "low"


def _extract_tags(rule: str) -> list[str]:
    """Extract potential tags from a rule.

    Looks for technology names, common keywords, etc.
    """
    # Common tech/concept terms to extract as tags
    known_tags = {
        "api", "http", "json", "yaml", "sql", "database", "cache",
        "redis", "supabase", "postgres", "mongodb", "git", "docker",
        "kubernetes", "aws", "gcp", "azure", "react", "python",
        "typescript", "javascript", "rust", "go", "test", "testing",
        "ci", "cd", "deploy", "error", "retry", "timeout", "auth",
        "jwt", "oauth", "plugin", "middleware", "async", "sync",
    }

    # Word variants that map to canonical tags
    tag_variants = {
        "caching": "cache",
        "cached": "cache",
        "databases": "database",
        "tests": "test",
        "tested": "test",
        "pytest": "test",
        "unittest": "test",
        "deploying": "deploy",
        "deployed": "deploy",
        "deployment": "deploy",
        "errors": "error",
        "retries": "retry",
        "retrying": "retry",
    }

    words = set(rule.lower().replace("-", " ").replace("_", " ").split())

    tags = set()
    for word in words:
        if word in known_tags:
            tags.add(word)
        elif word in tag_variants:
            tags.add(tag_variants[word])

    return sorted(tags)


def _deduplicate_insights(
    patterns: list[PatternDict],
    threshold: float = MIN_SIMILARITY_THRESHOLD,
    backend: EmbeddingBackend | None = None,
) -> list[tuple[str, int, list[str], date | None]]:
    """Deduplicate similar insights into merged rules.

    Args:
        patterns: List of pattern dictionaries from distill.
        threshold: Minimum similarity ratio to consider duplicates.
        backend: Embedding backend for similarity computation.

    Returns:
        List of (rule, frequency, sources, most_recent_date) tuples.
    """
    if not patterns:
        return []

    if backend is None:
        backend = get_default_backend()

    # Group similar insights
    groups: list[list[PatternDict]] = []

    for pattern in patterns:
        insight = pattern["insight"]
        matched = False

        for group in groups:
            # Compare against first item in group (representative)
            sim = backend.similarity(insight, group[0]["insight"])
            if sim >= threshold:
                group.append(pattern)
                matched = True
                break

        if not matched:
            groups.append([pattern])

    # Convert groups to deduplicated rules
    results: list[tuple[str, int, list[str], date | None]] = []

    for group in groups:
        # Use the shortest insight as the canonical rule (often cleaner)
        canonical = min(group, key=lambda p: len(p["insight"]))
        rule = canonical["insight"]
        frequency = len(group)
        sources = sorted(set(p["source"] for p in group))

        # Find most recent date
        dates: list[date] = []
        for p in group:
            try:
                dates.append(date.fromisoformat(p["date"]))
            except (ValueError, KeyError):
                pass

        most_recent = max(dates) if dates else None
        results.append((rule, frequency, sources, most_recent))

    return results


def generate_skills(
    buildlog_dir: Path,
    min_frequency: int = 1,
    since_date: date | None = None,
    embedding_backend: str | None = None,
) -> SkillSet:
    """Generate skills from buildlog patterns.

    Args:
        buildlog_dir: Path to the buildlog directory.
        min_frequency: Minimum frequency to include a skill.
        since_date: Only include patterns from this date onward.
        embedding_backend: Name of embedding backend for deduplication.
            Options: "token" (default), "sentence-transformers", "openai".

    Returns:
        SkillSet with generated skills.
    """
    # Get distilled patterns
    result = distill_all(buildlog_dir, since=since_date)

    # Get embedding backend
    backend = get_backend(embedding_backend) if embedding_backend else get_default_backend()
    logger.info("Using embedding backend: %s", backend.name)

    skills_by_category: dict[str, list[Skill]] = {}

    for category in CATEGORIES:
        patterns = result.patterns.get(category, [])
        deduplicated = _deduplicate_insights(patterns, backend=backend)

        skills: list[Skill] = []
        for rule, frequency, sources, most_recent in deduplicated:
            if frequency < min_frequency:
                continue

            skill = Skill(
                id=_generate_skill_id(category, rule),
                category=category,
                rule=rule,
                frequency=frequency,
                confidence=_calculate_confidence(frequency, most_recent),
                sources=sources,
                tags=_extract_tags(rule),
            )
            skills.append(skill)

        # Sort by frequency (descending), then by rule (for stability)
        skills.sort(key=lambda s: (-s.frequency, s.rule))
        skills_by_category[category] = skills

    return SkillSet(
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        source_entries=result.entry_count,
        skills=skills_by_category,
    )


def _format_yaml(skill_set: SkillSet) -> str:
    """Format skills as YAML."""
    try:
        import yaml
    except ImportError as e:
        raise ImportError(
            "PyYAML is required for YAML output. Install with: pip install pyyaml"
        ) from e

    data = skill_set.to_dict()
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _format_json(skill_set: SkillSet) -> str:
    """Format skills as JSON."""
    return json.dumps(skill_set.to_dict(), indent=2, ensure_ascii=False)


def _format_markdown(skill_set: SkillSet) -> str:
    """Format skills as Markdown for CLAUDE.md injection."""
    lines: list[str] = []

    lines.append("## Learned Skills")
    lines.append("")
    lines.append(f"Based on {skill_set.source_entries} buildlog entries, "
                 f"{skill_set.total_skills} actionable skills have emerged:")
    lines.append("")

    category_titles = {
        "architectural": "Architectural",
        "workflow": "Workflow",
        "tool_usage": "Tool Usage",
        "domain_knowledge": "Domain Knowledge",
    }

    for category, skills in skill_set.skills.items():
        if not skills:
            continue

        title = category_titles.get(category, category.replace("_", " ").title())
        lines.append(f"### {title} ({len(skills)} skills)")
        lines.append("")

        for skill in skills:
            confidence_badge = {"high": "🟢", "medium": "🟡", "low": "⚪"}.get(
                skill.confidence, ""
            )
            freq_text = f"seen {skill.frequency}x" if skill.frequency > 1 else "seen once"
            lines.append(f"- {confidence_badge} **{skill.rule}** ({freq_text})")

        lines.append("")

    lines.append("---")
    lines.append(f"*Generated: {skill_set.generated_at}*")

    return "\n".join(lines)


def _format_rules(skill_set: SkillSet) -> str:
    """Format skills as CLAUDE.md-ready rules.

    Transforms skills into imperative rules grouped by confidence level.
    High-confidence rules become "Always/Never" imperatives.
    """
    lines: list[str] = []

    lines.append("# Project Rules")
    lines.append("")
    lines.append(f"*Auto-generated from {skill_set.source_entries} buildlog entries. "
                 f"{skill_set.total_skills} rules extracted.*")
    lines.append("")

    # Collect all skills, sort by confidence then frequency
    all_skills: list[Skill] = []
    for skills in skill_set.skills.values():
        all_skills.extend(skills)

    high_conf = [s for s in all_skills if s.confidence == "high"]
    med_conf = [s for s in all_skills if s.confidence == "medium"]
    low_conf = [s for s in all_skills if s.confidence == "low"]

    if high_conf:
        lines.append("## Core Rules (High Confidence)")
        lines.append("")
        lines.append("These patterns have been reinforced multiple times recently.")
        lines.append("")
        for skill in sorted(high_conf, key=lambda s: -s.frequency):
            lines.append(f"- {skill.rule}")
        lines.append("")

    if med_conf:
        lines.append("## Established Patterns (Medium Confidence)")
        lines.append("")
        lines.append("These patterns appear consistently across sessions.")
        lines.append("")
        for skill in sorted(med_conf, key=lambda s: -s.frequency):
            lines.append(f"- {skill.rule}")
        lines.append("")

    if low_conf:
        lines.append("## Emerging Insights (Low Confidence)")
        lines.append("")
        lines.append("Recently observed patterns that may become rules.")
        lines.append("")
        for skill in sorted(low_conf, key=lambda s: -s.frequency):
            lines.append(f"- {skill.rule}")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated: {skill_set.generated_at}*")

    return "\n".join(lines)


def _format_settings(skill_set: SkillSet) -> str:
    """Format skills as .claude/settings.json compatible rules array.

    Only includes high and medium confidence rules by default,
    as these are established enough to influence agent behavior.
    """
    rules: list[str] = []

    for skills in skill_set.skills.values():
        for skill in skills:
            # Only include high/medium confidence as agent rules
            if skill.confidence in ("high", "medium"):
                rules.append(skill.rule)

    # Sort by frequency (embedded in skill order)
    output = {
        "_comment": f"Auto-generated from {skill_set.source_entries} buildlog entries",
        "_generated": skill_set.generated_at,
        "rules": rules,
    }

    return json.dumps(output, indent=2, ensure_ascii=False)


def format_skills(skill_set: SkillSet, fmt: OutputFormat = "yaml") -> str:
    """Format skills in the specified format.

    Args:
        skill_set: The SkillSet to format.
        fmt: Output format - yaml, json, or markdown.

    Returns:
        Formatted string.

    Raises:
        ValueError: If format is not recognized.
    """
    formatters = {
        "yaml": _format_yaml,
        "json": _format_json,
        "markdown": _format_markdown,
        "rules": _format_rules,
        "settings": _format_settings,
    }

    formatter = formatters.get(fmt)
    if formatter is None:
        raise ValueError(f"Unknown format: {fmt}. Must be one of: {list(formatters.keys())}")

    return formatter(skill_set)
