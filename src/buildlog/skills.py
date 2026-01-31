"""Generate agent-consumable skills from distilled patterns."""

from __future__ import annotations

__all__ = [
    "Skill",
    "SkillSet",
    "ConfidenceConfig",  # Re-exported for convenience
    "_deduplicate_insights",
    "_calculate_confidence",
    "_extract_tags",
    "_generate_skill_id",
    "_to_imperative",
    "_build_confidence_metrics",
    "generate_skills",
    "format_skills",
]

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypedDict

if TYPE_CHECKING:
    from buildlog.llm import LLMBackend

from buildlog.confidence import ConfidenceConfig, ConfidenceMetrics
from buildlog.confidence import calculate_confidence as calculate_continuous_confidence
from buildlog.confidence import get_confidence_tier
from buildlog.distill import CATEGORIES, PatternDict, distill_all
from buildlog.embeddings import EmbeddingBackend, get_backend, get_default_backend

logger = logging.getLogger(__name__)


def _load_review_learnings(buildlog_dir: Path) -> dict:
    """Load review learnings from .buildlog/review_learnings.json."""
    learnings_path = buildlog_dir / ".buildlog" / "review_learnings.json"
    if not learnings_path.exists():
        return {"learnings": {}}
    try:
        return json.loads(learnings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"learnings": {}}


# Configuration constants
MIN_SIMILARITY_THRESHOLD: Final[float] = 0.7
HIGH_CONFIDENCE_FREQUENCY: Final[int] = 3
HIGH_CONFIDENCE_RECENCY_DAYS: Final[int] = 30
MEDIUM_CONFIDENCE_FREQUENCY: Final[int] = 2

# Type definitions
OutputFormat = Literal["yaml", "json", "markdown", "rules", "settings"]
ConfidenceLevel = Literal["high", "medium", "low"]


class _SkillDictRequired(TypedDict):
    """Required fields for skill dictionary (base class)."""

    id: str
    category: str
    rule: str
    frequency: int
    confidence: ConfidenceLevel
    sources: list[str]
    tags: list[str]


class SkillDict(_SkillDictRequired, total=False):
    """Type for skill dictionary representation.

    Inherits required fields from _SkillDictRequired.
    Optional fields are only present when continuous confidence is enabled
    or when defensibility fields are populated.
    """

    confidence_score: float
    confidence_tier: str
    # Defensibility fields (from #24 - tighter schema)
    context: str  # When does this rule apply?
    antipattern: str  # What does violation look like?
    rationale: str  # Why does this matter?
    persona_tags: list[str]  # Which reviewers use this rule?
    # LLM-extracted scoring fields
    severity: str  # critical/major/minor/info
    scope: str  # global/module/function
    applicability: list[str]  # contexts where relevant


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

    Attributes:
        id: Stable identifier for the skill.
        category: Category (architectural, workflow, etc.).
        rule: The actionable rule text.
        frequency: How many times this pattern was seen.
        confidence: Discrete confidence level (high/medium/low).
        sources: List of source files where this pattern appeared.
        tags: Extracted technology/concept tags.
        confidence_score: Continuous confidence score (0-1), if calculated.
        confidence_tier: Descriptive tier (speculative/provisional/stable/entrenched).
        context: When does this rule apply? (defensibility)
        antipattern: What does violation look like? (defensibility)
        rationale: Why does this rule matter? (defensibility)
        persona_tags: Which reviewer personas use this rule?
        severity: How bad is ignoring this rule? (critical/major/minor/info)
        scope: How broadly does this rule apply? (global/module/function)
        applicability: Contexts where this rule is relevant.
    """

    id: str
    category: str
    rule: str
    frequency: int
    confidence: ConfidenceLevel
    sources: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    confidence_score: float | None = None
    confidence_tier: str | None = None
    # Defensibility fields (#24)
    context: str | None = None
    antipattern: str | None = None
    rationale: str | None = None
    persona_tags: list[str] = field(default_factory=list)
    # LLM-extracted scoring
    severity: str | None = None
    scope: str | None = None
    applicability: list[str] = field(default_factory=list)

    def to_dict(self) -> SkillDict:
        """Convert to dictionary for serialization.

        Only includes optional fields when they are set.
        """
        result = SkillDict(
            id=self.id,
            category=self.category,
            rule=self.rule,
            frequency=self.frequency,
            confidence=self.confidence,
            sources=self.sources,
            tags=self.tags,
        )
        if self.confidence_score is not None:
            result["confidence_score"] = self.confidence_score
        if self.confidence_tier is not None:
            result["confidence_tier"] = self.confidence_tier
        # Defensibility fields
        if self.context is not None:
            result["context"] = self.context
        if self.antipattern is not None:
            result["antipattern"] = self.antipattern
        if self.rationale is not None:
            result["rationale"] = self.rationale
        if self.persona_tags:
            result["persona_tags"] = self.persona_tags
        if self.severity is not None:
            result["severity"] = self.severity
        if self.scope is not None:
            result["scope"] = self.scope
        if self.applicability:
            result["applicability"] = self.applicability
        return result


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

    if (
        frequency >= HIGH_CONFIDENCE_FREQUENCY
        and recency_days < HIGH_CONFIDENCE_RECENCY_DAYS
    ):
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
        "api",
        "http",
        "json",
        "yaml",
        "sql",
        "database",
        "cache",
        "redis",
        "supabase",
        "postgres",
        "mongodb",
        "git",
        "docker",
        "kubernetes",
        "aws",
        "gcp",
        "azure",
        "react",
        "python",
        "typescript",
        "javascript",
        "rust",
        "go",
        "test",
        "testing",
        "ci",
        "cd",
        "deploy",
        "error",
        "retry",
        "timeout",
        "auth",
        "jwt",
        "oauth",
        "plugin",
        "middleware",
        "async",
        "sync",
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
    llm_backend: LLMBackend | None = None,
) -> list[tuple[str, int, list[str], date | None, date | None]]:
    """Deduplicate similar insights into merged rules.

    Args:
        patterns: List of pattern dictionaries from distill.
        threshold: Minimum similarity ratio to consider duplicates.
        backend: Embedding backend for similarity computation.

    Returns:
        List of (rule, frequency, sources, most_recent_date, earliest_date) tuples.
        Both dates can be None if no valid dates are found in the patterns.
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
    results: list[tuple[str, int, list[str], date | None, date | None]] = []

    for group in groups:
        # Use LLM to select canonical form if available and group has >1 member
        if llm_backend is not None and len(group) > 1:
            try:
                candidates = [p["insight"] for p in group]
                rule = llm_backend.select_canonical(candidates)
            except Exception:
                canonical = min(group, key=lambda p: len(p["insight"]))
                rule = canonical["insight"]
        else:
            canonical = min(group, key=lambda p: len(p["insight"]))
            rule = canonical["insight"]
        frequency = len(group)
        sources = sorted(set(p["source"] for p in group))

        # Find most recent and earliest dates
        dates: list[date] = []
        for p in group:
            try:
                dates.append(date.fromisoformat(p["date"]))
            except (ValueError, KeyError):
                pass

        most_recent = max(dates) if dates else None
        earliest = min(dates) if dates else None
        results.append((rule, frequency, sources, most_recent, earliest))

    return results


def _build_confidence_metrics(
    frequency: int,
    most_recent: date | None,
    earliest: date | None,
) -> ConfidenceMetrics:
    """Build ConfidenceMetrics from deduplication results.

    Args:
        frequency: Number of times the pattern was seen.
        most_recent: Most recent occurrence date.
        earliest: Earliest occurrence date.

    Returns:
        ConfidenceMetrics for continuous confidence calculation.
    """
    # Use midnight UTC for date-based timestamps
    now = datetime.now(timezone.utc)

    if most_recent is not None:
        last_reinforced = datetime(
            most_recent.year, most_recent.month, most_recent.day, tzinfo=timezone.utc
        )
    else:
        last_reinforced = now

    if earliest is not None:
        first_seen = datetime(
            earliest.year, earliest.month, earliest.day, tzinfo=timezone.utc
        )
    else:
        first_seen = last_reinforced

    return ConfidenceMetrics(
        reinforcement_count=frequency,
        last_reinforced=last_reinforced,
        contradiction_count=0,  # Deferred: no contradiction tracking yet
        first_seen=first_seen,
    )


def generate_skills(
    buildlog_dir: Path,
    min_frequency: int = 1,
    since_date: date | None = None,
    embedding_backend: str | None = None,
    confidence_config: ConfidenceConfig | None = None,
    include_review_learnings: bool = True,
    llm: bool = False,
) -> SkillSet:
    """Generate skills from buildlog patterns and review learnings.

    Args:
        buildlog_dir: Path to the buildlog directory.
        min_frequency: Minimum frequency to include a skill.
        since_date: Only include patterns from this date onward.
        embedding_backend: Name of embedding backend for deduplication.
            Options: "token" (default), "sentence-transformers", "openai".
        confidence_config: Configuration for continuous confidence scoring.
            If provided, skills will include confidence_score and confidence_tier.
            If None, only discrete confidence levels (high/medium/low) are computed.
        include_review_learnings: Whether to include learnings from code reviews.
            When True, loads .buildlog/review_learnings.json and merges
            review learnings into the skill set.
        llm: If True and an LLM backend is available, use LLM for extraction,
            canonical selection, and scoring. Falls back gracefully.

    Returns:
        SkillSet with generated skills.
    """
    # Resolve LLM backend if requested
    llm_backend = None
    if llm:
        from buildlog.llm import get_llm_backend

        llm_backend = get_llm_backend(buildlog_dir=buildlog_dir)

    # Get distilled patterns
    result = distill_all(buildlog_dir, since=since_date, llm=llm)

    # Get embedding backend
    backend = (
        get_backend(embedding_backend)  # type: ignore[arg-type]
        if embedding_backend
        else get_default_backend()
    )
    logger.info("Using embedding backend: %s", backend.name)

    # Capture reference time for confidence calculations
    t_now = datetime.now(timezone.utc) if confidence_config else None

    skills_by_category: dict[str, list[Skill]] = {}

    for category in CATEGORIES:
        patterns = result.patterns.get(category, [])
        deduplicated = _deduplicate_insights(
            patterns, backend=backend, llm_backend=llm_backend
        )

        skills: list[Skill] = []
        for rule, frequency, sources, most_recent, earliest in deduplicated:
            if frequency < min_frequency:
                continue

            # Calculate continuous confidence if config provided
            confidence_score: float | None = None
            confidence_tier: str | None = None
            if confidence_config is not None and t_now is not None:
                metrics = _build_confidence_metrics(frequency, most_recent, earliest)
                confidence_score = calculate_continuous_confidence(
                    metrics, confidence_config, t_now
                )
                confidence_tier = get_confidence_tier(
                    confidence_score, confidence_config
                ).value

            # LLM scoring for severity/scope/applicability
            severity: str | None = None
            scope: str | None = None
            applicability_tags: list[str] = []
            if llm_backend is not None:
                try:
                    scoring = llm_backend.score_rule(rule, category)
                    severity = scoring.severity
                    scope = scoring.scope
                    applicability_tags = scoring.applicability
                except Exception:
                    pass  # Keep defaults (None/empty)

            # Apply severity weighting to confidence score
            if confidence_score is not None and severity is not None:
                from buildlog.confidence import apply_severity_weight

                confidence_score = apply_severity_weight(confidence_score, severity)

            skill = Skill(
                id=_generate_skill_id(category, rule),
                category=category,
                rule=rule,
                frequency=frequency,
                confidence=_calculate_confidence(frequency, most_recent),
                sources=sources,
                tags=_extract_tags(rule),
                confidence_score=confidence_score,
                confidence_tier=confidence_tier,
                severity=severity,
                scope=scope,
                applicability=applicability_tags,
            )
            skills.append(skill)

        # Sort by frequency (descending), then by rule (for stability)
        skills.sort(key=lambda s: (-s.frequency, s.rule))
        skills_by_category[category] = skills

    # Merge review learnings if requested
    if include_review_learnings:
        review_data = _load_review_learnings(buildlog_dir)
        learnings = review_data.get("learnings", {})

        for learning_id, learning_dict in learnings.items():
            category = learning_dict.get("category", "workflow")
            rule = learning_dict.get("rule", "")

            if not rule:
                continue

            # Parse timestamps for confidence calculation
            first_seen_str = learning_dict.get("first_seen", "")
            last_reinforced_str = learning_dict.get("last_reinforced", "")

            try:
                first_seen = datetime.fromisoformat(first_seen_str)
                if first_seen.tzinfo is None:
                    first_seen = first_seen.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                first_seen = datetime.now(timezone.utc)

            try:
                last_reinforced = datetime.fromisoformat(last_reinforced_str)
                if last_reinforced.tzinfo is None:
                    last_reinforced = last_reinforced.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                last_reinforced = datetime.now(timezone.utc)

            # Get frequency from reinforcement count
            frequency = learning_dict.get("reinforcement_count", 1)

            # Check for duplicate rules in existing skills (by ID match)
            existing_skill = None
            if category in skills_by_category:
                for skill in skills_by_category[category]:
                    if skill.id == learning_id:
                        existing_skill = skill
                        break

            if existing_skill is not None:
                # Merge: boost the existing skill's frequency
                existing_skill = Skill(
                    id=existing_skill.id,
                    category=existing_skill.category,
                    rule=existing_skill.rule,
                    frequency=existing_skill.frequency + frequency,
                    confidence=existing_skill.confidence,
                    sources=existing_skill.sources
                    + [learning_dict.get("source", "review")],
                    tags=existing_skill.tags,
                    confidence_score=existing_skill.confidence_score,
                    confidence_tier=existing_skill.confidence_tier,
                )
                # Replace in list
                skills_by_category[category] = [
                    existing_skill if s.id == existing_skill.id else s
                    for s in skills_by_category[category]
                ]
            else:
                # Create new skill from review learning
                review_conf_score: float | None = None
                review_conf_tier: str | None = None

                if confidence_config is not None and t_now is not None:
                    metrics = ConfidenceMetrics(
                        reinforcement_count=frequency,
                        last_reinforced=last_reinforced,
                        contradiction_count=learning_dict.get("contradiction_count", 0),
                        first_seen=first_seen,
                    )
                    review_conf_score = calculate_continuous_confidence(
                        metrics, confidence_config, t_now
                    )
                    review_conf_tier = get_confidence_tier(
                        review_conf_score, confidence_config
                    ).value

                # Calculate discrete confidence from most recent date
                discrete_confidence = _calculate_confidence(
                    frequency, last_reinforced.date()
                )

                skill = Skill(
                    id=learning_id,
                    category=category,
                    rule=rule,
                    frequency=frequency,
                    confidence=discrete_confidence,
                    sources=[learning_dict.get("source", "review")],
                    tags=_extract_tags(rule),
                    confidence_score=review_conf_score,
                    confidence_tier=review_conf_tier,
                )

                # Add to category
                if category not in skills_by_category:
                    skills_by_category[category] = []
                skills_by_category[category].append(skill)

        # Re-sort categories after adding review learnings
        for category in skills_by_category:
            skills_by_category[category].sort(key=lambda s: (-s.frequency, s.rule))

    return SkillSet(
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
    return yaml.dump(
        data, default_flow_style=False, allow_unicode=True, sort_keys=False
    )


def _format_json(skill_set: SkillSet) -> str:
    """Format skills as JSON."""
    return json.dumps(skill_set.to_dict(), indent=2, ensure_ascii=False)


def _format_markdown(skill_set: SkillSet) -> str:
    """Format skills as Markdown for CLAUDE.md injection."""
    lines: list[str] = []

    lines.append("## Learned Skills")
    lines.append("")
    lines.append(
        f"Based on {skill_set.source_entries} buildlog entries, "
        f"{skill_set.total_skills} actionable skills have emerged:"
    )
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
            freq_text = (
                f"seen {skill.frequency}x" if skill.frequency > 1 else "seen once"
            )
            lines.append(f"- {confidence_badge} **{skill.rule}** ({freq_text})")

        lines.append("")

    lines.append("---")
    lines.append(f"*Generated: {skill_set.generated_at}*")

    return "\n".join(lines)


# Pre-compiled patterns for _to_imperative (module-level for efficiency)
_NEGATIVE_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"\bdon't\b",
        r"\bdo not\b",
        r"\bnever\b",
        r"\bavoid\b",
        r"\bstop\b",
        r"\bshouldn't\b",
        r"\bshould not\b",
    )
)

# Comparison patterns - intentionally narrow to avoid false positives
# "over" alone matches "all over", "game over" etc. so we require context
_COMPARISON_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"\binstead of\b",
        r"\brather than\b",
        r"\bbetter than\b",
        r"\b\w+\s+over\s+\w+\b",  # "X over Y" pattern
    )
)

# Verbs that need -ing form when following "Avoid" or bare "Prefer"
_VERB_TO_GERUND: Final[dict[str, str]] = {
    "use": "using",
    "run": "running",
    "make": "making",
    "write": "writing",
    "read": "reading",
    "put": "putting",
    "get": "getting",
    "set": "setting",
    "add": "adding",
    "create": "creating",
    "delete": "deleting",
    "call": "calling",
    "pass": "passing",
    "send": "sending",
    "store": "storing",
    "cache": "caching",
}


def _to_imperative(rule: str, confidence: ConfidenceLevel) -> str:
    """Transform a rule into imperative form.

    High confidence → "Always X" or "Never Y"
    Medium confidence → "Prefer X" or "Avoid Y"
    Low confidence → "Consider: X" (stays as observation)

    Args:
        rule: The rule text to transform.
        confidence: Must be "high", "medium", or "low".

    Returns:
        Transformed rule with appropriate confidence prefix.

    Raises:
        ValueError: If confidence is not a valid ConfidenceLevel.
    """
    # Validate confidence parameter
    valid_confidence: set[ConfidenceLevel] = {"high", "medium", "low"}
    if confidence not in valid_confidence:
        raise ValueError(
            f"Invalid confidence level: {confidence!r}. "
            f"Must be one of: {valid_confidence}"
        )

    rule = rule.strip()
    if not rule:
        return ""

    rule_lower = rule.lower()

    # Already has a confidence modifier - just capitalize and return
    confidence_modifiers = (
        "always",
        "never",
        "prefer",
        "avoid",
        "consider",
        "remember",
        "don't",
        "do not",
    )
    if any(rule_lower.startswith(word) for word in confidence_modifiers):
        return rule[0].upper() + rule[1:]

    # Detect patterns using pre-compiled regexes
    is_negative = any(pat.search(rule_lower) for pat in _NEGATIVE_PATTERNS)
    is_comparison = any(pat.search(rule_lower) for pat in _COMPARISON_PATTERNS)

    # Choose prefix based on confidence and pattern
    if confidence == "high":
        if is_negative:
            prefix = "Never"
        else:
            prefix = "Always"
    elif confidence == "medium":
        if is_negative:
            prefix = "Avoid"
        elif is_comparison:
            prefix = "Prefer"
        else:
            prefix = "Prefer to"
    else:  # low - already validated above
        return f"Consider: {rule}"

    # Clean up the rule for prefixing
    # Remove leading "should" type words (order matters - longer first)
    cleaners = [
        "you shouldn't ",
        "we shouldn't ",
        "shouldn't ",
        "you should not ",
        "we should not ",
        "should not ",
        "you should ",
        "we should ",
        "should ",
        "it's better to ",
        "it is better to ",
    ]
    cleaned = rule
    cleaned_lower = rule_lower
    for cleaner in cleaners:
        if cleaned_lower.startswith(cleaner):
            cleaned = cleaned[len(cleaner) :]
            cleaned_lower = cleaned.lower()
            break

    # If we're adding a negative prefix, remove leading "not " from cleaned
    if prefix in ("Never", "Avoid") and cleaned_lower.startswith("not "):
        cleaned = cleaned[4:]
        cleaned_lower = cleaned.lower()

    # Avoid double words: "Avoid avoid using..." -> "Avoid using..."
    prefix_lower = prefix.lower()
    if cleaned_lower.startswith(prefix_lower + " ") or cleaned_lower.startswith(
        prefix_lower + "ing "
    ):
        first_space = cleaned.find(" ")
        if first_space > 0:
            cleaned = cleaned[first_space + 1 :]
            cleaned_lower = cleaned.lower()

    # For "Avoid" and bare "Prefer", convert leading verbs to gerund form
    # "Avoid use eval" -> "Avoid using eval"
    # "Prefer use X over Y" -> "Prefer using X over Y"
    if prefix in ("Avoid", "Prefer"):
        first_word = cleaned_lower.split()[0] if cleaned_lower else ""
        if first_word in _VERB_TO_GERUND:
            gerund = _VERB_TO_GERUND[first_word]
            cleaned = gerund + cleaned[len(first_word) :]
            cleaned_lower = cleaned.lower()

    # Lowercase first char if we're adding a prefix (but not for gerunds which are already lower)
    if cleaned and cleaned[0].isupper():
        cleaned = cleaned[0].lower() + cleaned[1:]

    return f"{prefix} {cleaned}"


def _format_rules(skill_set: SkillSet) -> str:
    """Format skills as CLAUDE.md-ready rules.

    Transforms skills into imperative rules grouped by confidence level.
    High-confidence rules become "Always/Never" imperatives.
    """
    lines: list[str] = []

    lines.append("# Project Rules")
    lines.append("")
    lines.append(
        f"*Auto-generated from {skill_set.source_entries} buildlog entries. "
        f"{skill_set.total_skills} rules extracted.*"
    )
    lines.append("")

    # Collect all skills, sort by confidence then frequency
    all_skills: list[Skill] = []
    for skills in skill_set.skills.values():
        all_skills.extend(skills)

    high_conf = [s for s in all_skills if s.confidence == "high"]
    med_conf = [s for s in all_skills if s.confidence == "medium"]
    low_conf = [s for s in all_skills if s.confidence == "low"]

    if high_conf:
        lines.append("## Core Rules")
        lines.append("")
        for skill in sorted(high_conf, key=lambda s: -s.frequency):
            lines.append(f"- {_to_imperative(skill.rule, 'high')}")
        lines.append("")

    if med_conf:
        lines.append("## Established Patterns")
        lines.append("")
        for skill in sorted(med_conf, key=lambda s: -s.frequency):
            lines.append(f"- {_to_imperative(skill.rule, 'medium')}")
        lines.append("")

    if low_conf:
        lines.append("## Considerations")
        lines.append("")
        for skill in sorted(low_conf, key=lambda s: -s.frequency):
            lines.append(f"- {_to_imperative(skill.rule, 'low')}")
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
        raise ValueError(
            f"Unknown format: {fmt}. Must be one of: {list(formatters.keys())}"
        )

    return formatter(skill_set)
