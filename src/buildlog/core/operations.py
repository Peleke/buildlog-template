"""Core operations for buildlog skill management.

This module contains the business logic that can be exposed via
MCP, CLI, HTTP, or any other interface.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

from buildlog.confidence import ConfidenceMetrics, merge_confidence_metrics
from buildlog.render import get_renderer
from buildlog.skills import Skill, SkillSet, generate_skills

__all__ = [
    "StatusResult",
    "PromoteResult",
    "RejectResult",
    "DiffResult",
    "ReviewIssue",
    "ReviewLearning",
    "LearnFromReviewResult",
    "status",
    "promote",
    "reject",
    "diff",
    "find_skills_by_ids",
    "learn_from_review",
]


@dataclass
class StatusResult:
    """Result of a status operation."""

    skills: dict[str, list[dict]]
    """Skills grouped by category."""

    total_entries: int
    """Number of buildlog entries processed."""

    total_skills: int
    """Total number of skills found."""

    by_confidence: dict[str, int]
    """Count of skills by confidence level."""

    promotable_ids: list[str]
    """IDs of high-confidence skills ready for promotion."""

    error: str | None = None
    """Error message if operation failed."""


@dataclass
class PromoteResult:
    """Result of a promote operation."""

    promoted_ids: list[str]
    """IDs of skills that were promoted."""

    target: str
    """Target format (claude_md, settings_json, or skill)."""

    rules_added: int
    """Number of rules added."""

    not_found_ids: list[str] = field(default_factory=list)
    """IDs that were not found."""

    message: str = ""
    """Confirmation message."""

    error: str | None = None
    """Error message if operation failed."""


@dataclass
class RejectResult:
    """Result of a reject operation."""

    rejected_ids: list[str]
    """IDs that were rejected."""

    total_rejected: int
    """Total number of rejected skills."""

    error: str | None = None
    """Error message if operation failed."""


@dataclass
class DiffResult:
    """Result of a diff operation."""

    pending: dict[str, list[dict]]
    """Skills pending review, grouped by category."""

    total_pending: int
    """Total number of pending skills."""

    already_promoted: int
    """Number of previously promoted skills."""

    already_rejected: int
    """Number of previously rejected skills."""

    error: str | None = None
    """Error message if operation failed."""


# -----------------------------------------------------------------------------
# Review Learning Data Structures
# -----------------------------------------------------------------------------


class ReviewIssueDict(TypedDict, total=False):
    """Serializable form of ReviewIssue."""

    severity: str
    category: str
    description: str
    rule_learned: str
    location: str | None
    why_it_matters: str | None
    functional_principle: str | None


@dataclass
class ReviewIssue:
    """A single issue identified during code review.

    Attributes:
        severity: How serious the issue is (critical/major/minor/nitpick).
        category: What kind of issue (architectural/workflow/tool_usage/domain_knowledge).
        description: What's wrong (concrete).
        rule_learned: The generalizable rule extracted from this issue.
        location: File:line where the issue was found.
        why_it_matters: Why this issue matters (consequences).
        functional_principle: Related FP principle, if applicable.
    """

    severity: Literal["critical", "major", "minor", "nitpick"]
    category: Literal["architectural", "workflow", "tool_usage", "domain_knowledge"]
    description: str
    rule_learned: str
    location: str | None = None
    why_it_matters: str | None = None
    functional_principle: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewIssue":
        """Construct from dictionary (e.g., from JSON)."""
        return cls(
            severity=data.get("severity", "minor"),
            category=data.get("category", "workflow"),
            description=data.get("description", ""),
            rule_learned=data.get("rule_learned", ""),
            location=data.get("location"),
            why_it_matters=data.get("why_it_matters"),
            functional_principle=data.get("functional_principle"),
        )


class ReviewLearningDict(TypedDict, total=False):
    """Serializable form of ReviewLearning."""

    id: str
    rule: str
    category: str
    severity: str
    source: str
    first_seen: str
    last_reinforced: str
    reinforcement_count: int
    contradiction_count: int
    functional_principle: str | None


@dataclass
class ReviewLearning:
    """A learning extracted from review, with confidence tracking.

    Attributes:
        id: Deterministic hash of rule_learned (category prefix + hash).
        rule: The generalizable rule text.
        category: Category of the learning.
        severity: Severity of the original issue.
        source: Where this learning came from (e.g., "review:PR#13").
        first_seen: When this rule was first identified.
        last_reinforced: When this rule was last seen/reinforced.
        reinforcement_count: How many times this rule has been seen.
        contradiction_count: How many times this rule was contradicted.
        functional_principle: Related FP principle, if applicable.
    """

    id: str
    rule: str
    category: str
    severity: str
    source: str
    first_seen: datetime
    last_reinforced: datetime
    reinforcement_count: int = 1
    contradiction_count: int = 0
    functional_principle: str | None = None

    def to_confidence_metrics(self) -> ConfidenceMetrics:
        """Convert to ConfidenceMetrics for scoring."""
        return ConfidenceMetrics(
            reinforcement_count=self.reinforcement_count,
            last_reinforced=self.last_reinforced,
            contradiction_count=self.contradiction_count,
            first_seen=self.first_seen,
        )

    def to_dict(self) -> ReviewLearningDict:
        """Convert to serializable dictionary."""
        result: ReviewLearningDict = {
            "id": self.id,
            "rule": self.rule,
            "category": self.category,
            "severity": self.severity,
            "source": self.source,
            "first_seen": self.first_seen.isoformat(),
            "last_reinforced": self.last_reinforced.isoformat(),
            "reinforcement_count": self.reinforcement_count,
            "contradiction_count": self.contradiction_count,
        }
        if self.functional_principle:
            result["functional_principle"] = self.functional_principle
        return result

    @classmethod
    def from_dict(cls, data: ReviewLearningDict) -> "ReviewLearning":
        """Reconstruct from serialized dictionary."""
        first_seen = datetime.fromisoformat(data["first_seen"])
        last_reinforced = datetime.fromisoformat(data["last_reinforced"])

        # Ensure timezone awareness
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        if last_reinforced.tzinfo is None:
            last_reinforced = last_reinforced.replace(tzinfo=timezone.utc)

        return cls(
            id=data["id"],
            rule=data["rule"],
            category=data["category"],
            severity=data["severity"],
            source=data["source"],
            first_seen=first_seen,
            last_reinforced=last_reinforced,
            reinforcement_count=data.get("reinforcement_count", 1),
            contradiction_count=data.get("contradiction_count", 0),
            functional_principle=data.get("functional_principle"),
        )


@dataclass
class LearnFromReviewResult:
    """Result of learning from a review.

    Attributes:
        new_learnings: IDs of newly created learnings.
        reinforced_learnings: IDs of existing learnings that were reinforced.
        total_issues_processed: Total number of issues processed.
        source: Review source identifier.
        message: Human-readable summary.
        error: Error message if operation failed.
    """

    new_learnings: list[str]
    reinforced_learnings: list[str]
    total_issues_processed: int
    source: str
    message: str = ""
    error: str | None = None


def _get_rejected_path(buildlog_dir: Path) -> Path:
    """Get path to rejected.json file."""
    return buildlog_dir / ".buildlog" / "rejected.json"


def _get_promoted_path(buildlog_dir: Path) -> Path:
    """Get path to promoted.json file."""
    return buildlog_dir / ".buildlog" / "promoted.json"


def _load_json_set(path: Path, key: str) -> set[str]:
    """Load a set of IDs from a JSON file."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
        return set(data.get(key, []))
    except (json.JSONDecodeError, OSError):
        return set()


def find_skills_by_ids(
    skill_set: SkillSet,
    skill_ids: list[str],
) -> tuple[list[Skill], list[str]]:
    """Find skills by their IDs.

    Args:
        skill_set: The SkillSet to search.
        skill_ids: List of skill IDs to find.

    Returns:
        Tuple of (found_skills, not_found_ids).
    """
    found: list[Skill] = []
    not_found: list[str] = []

    # Build lookup map
    id_to_skill: dict[str, Skill] = {}
    for category_skills in skill_set.skills.values():
        for skill in category_skills:
            id_to_skill[skill.id] = skill

    for skill_id in skill_ids:
        if skill_id in id_to_skill:
            found.append(id_to_skill[skill_id])
        else:
            not_found.append(skill_id)

    return found, not_found


def status(
    buildlog_dir: Path,
    min_confidence: Literal["low", "medium", "high"] = "low",
) -> StatusResult:
    """Get current skills extracted from buildlog entries.

    Args:
        buildlog_dir: Path to buildlog directory.
        min_confidence: Minimum confidence level to include.

    Returns:
        StatusResult with skills grouped by category and summary statistics.
    """
    if not buildlog_dir.exists():
        return StatusResult(
            skills={},
            total_entries=0,
            total_skills=0,
            by_confidence={"high": 0, "medium": 0, "low": 0},
            promotable_ids=[],
            error=f"No buildlog directory found at {buildlog_dir}",
        )

    skill_set = generate_skills(buildlog_dir)

    # Load rejected IDs to filter them out
    rejected_ids = _load_json_set(_get_rejected_path(buildlog_dir), "skill_ids")

    # Filter by confidence and exclude rejected
    confidence_order = {"low": 0, "medium": 1, "high": 2}
    min_level = confidence_order[min_confidence]

    filtered: dict[str, list[dict]] = {}  # type: ignore[type-arg]
    by_confidence = {"high": 0, "medium": 0, "low": 0}
    promotable: list[str] = []

    for category, skill_list in skill_set.skills.items():
        category_skills = []
        for skill in skill_list:
            # Skip rejected skills
            if skill.id in rejected_ids:
                continue

            # Count by confidence (before filtering)
            by_confidence[skill.confidence] += 1

            # Track promotable (high confidence, not rejected)
            if skill.confidence == "high":
                promotable.append(skill.id)

            # Apply confidence filter
            if confidence_order[skill.confidence] >= min_level:
                category_skills.append(skill.to_dict())

        if category_skills:
            filtered[category] = category_skills  # type: ignore[assignment]

    # Calculate actual total (sum of by_confidence, which excludes rejected)
    actual_total = sum(by_confidence.values())

    return StatusResult(
        skills=filtered,
        total_entries=skill_set.source_entries,
        total_skills=actual_total,
        by_confidence=by_confidence,
        promotable_ids=promotable,
    )


def promote(
    buildlog_dir: Path,
    skill_ids: list[str],
    target: Literal["claude_md", "settings_json", "skill"] = "claude_md",
    target_path: Path | None = None,
) -> PromoteResult:
    """Promote skills to agent rules.

    Args:
        buildlog_dir: Path to buildlog directory.
        skill_ids: List of skill IDs to promote.
        target: Where to write rules ("claude_md", "settings_json", or "skill").
        target_path: Optional custom path for the target file.

    Returns:
        PromoteResult with confirmation.
    """
    if not buildlog_dir.exists():
        return PromoteResult(
            promoted_ids=[],
            target=target,
            rules_added=0,
            error=f"No buildlog directory found at {buildlog_dir}",
        )

    if not skill_ids:
        return PromoteResult(
            promoted_ids=[],
            target=target,
            rules_added=0,
            error="No skill IDs provided",
        )

    skill_set = generate_skills(buildlog_dir)
    found_skills, not_found_ids = find_skills_by_ids(skill_set, skill_ids)

    if not found_skills:
        return PromoteResult(
            promoted_ids=[],
            target=target,
            rules_added=0,
            not_found_ids=not_found_ids,
            error="No valid skill IDs provided",
        )

    # Set up tracking path in buildlog directory
    tracking_path = _get_promoted_path(buildlog_dir)

    # Get renderer using the registry pattern
    renderer = get_renderer(target, path=target_path, tracking_path=tracking_path)

    message = renderer.render(found_skills)

    return PromoteResult(
        promoted_ids=[s.id for s in found_skills],
        target=target,
        rules_added=len(found_skills),
        not_found_ids=not_found_ids,
        message=message,
    )


def reject(
    buildlog_dir: Path,
    skill_ids: list[str],
) -> RejectResult:
    """Mark skills as rejected so they won't be suggested again.

    Args:
        buildlog_dir: Path to buildlog directory.
        skill_ids: List of skill IDs to reject.

    Returns:
        RejectResult with confirmation.
    """
    if not skill_ids:
        return RejectResult(
            rejected_ids=[],
            total_rejected=0,
            error="No skill IDs provided",
        )

    reject_file = _get_rejected_path(buildlog_dir)
    reject_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing rejections
    if reject_file.exists():
        try:
            rejected = json.loads(reject_file.read_text())
        except json.JSONDecodeError:
            rejected = {"rejected_at": {}, "skill_ids": []}
    else:
        rejected = {"rejected_at": {}, "skill_ids": []}

    # Add new rejections
    now = datetime.now().isoformat()
    newly_rejected: list[str] = []
    for skill_id in skill_ids:
        if skill_id not in rejected["skill_ids"]:
            rejected["skill_ids"].append(skill_id)
            rejected["rejected_at"][skill_id] = now
            newly_rejected.append(skill_id)

    reject_file.write_text(json.dumps(rejected, indent=2))

    return RejectResult(
        rejected_ids=newly_rejected,
        total_rejected=len(rejected["skill_ids"]),
    )


def diff(
    buildlog_dir: Path,
) -> DiffResult:
    """Show skills that haven't been promoted or rejected yet.

    Args:
        buildlog_dir: Path to buildlog directory.

    Returns:
        DiffResult with pending skills.
    """
    if not buildlog_dir.exists():
        return DiffResult(
            pending={},
            total_pending=0,
            already_promoted=0,
            already_rejected=0,
            error=f"No buildlog directory found at {buildlog_dir}",
        )

    skill_set = generate_skills(buildlog_dir)

    # Load rejected and promoted IDs
    rejected_ids = _load_json_set(_get_rejected_path(buildlog_dir), "skill_ids")
    promoted_ids = _load_json_set(_get_promoted_path(buildlog_dir), "skill_ids")

    # Find unpromoted, unrejected skills
    pending: dict[str, list[dict]] = {}  # type: ignore[type-arg]
    total_pending = 0

    for category, skill_list in skill_set.skills.items():
        pending_skills = [
            s.to_dict()
            for s in skill_list
            if s.id not in rejected_ids and s.id not in promoted_ids
        ]
        if pending_skills:
            pending[category] = pending_skills  # type: ignore[assignment]
            total_pending += len(pending_skills)

    return DiffResult(
        pending=pending,
        total_pending=total_pending,
        already_promoted=len(promoted_ids),
        already_rejected=len(rejected_ids),
    )


# -----------------------------------------------------------------------------
# Review Learning Operations
# -----------------------------------------------------------------------------


def _get_learnings_path(buildlog_dir: Path) -> Path:
    """Get path to review_learnings.json file."""
    return buildlog_dir / ".buildlog" / "review_learnings.json"


def _generate_learning_id(category: str, rule: str) -> str:
    """Generate deterministic ID for a learning.

    Uses category prefix + first 10 chars of SHA256 hash.
    """
    # Normalize: lowercase, strip whitespace
    normalized = rule.lower().strip()
    hash_input = f"{category}:{normalized}".encode("utf-8")
    hash_hex = hashlib.sha256(hash_input).hexdigest()[:10]

    # Category prefix mapping
    prefix_map = {
        "architectural": "arch",
        "workflow": "wf",
        "tool_usage": "tool",
        "domain_knowledge": "dom",
    }
    prefix = prefix_map.get(category, category[:4])

    return f"{prefix}-{hash_hex}"


def _load_learnings(path: Path) -> dict:
    """Load learnings from JSON file."""
    if not path.exists():
        return {"learnings": {}, "review_history": []}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"learnings": {}, "review_history": []}


def _save_learnings(path: Path, data: dict) -> None:
    """Save learnings to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def learn_from_review(
    buildlog_dir: Path,
    issues: list[dict],
    source: str | None = None,
) -> LearnFromReviewResult:
    """Capture learnings from a code review and update confidence metrics.

    For each issue:
    1. Generate deterministic ID from rule text
    2. If exists: reinforce (increment count, update timestamp)
    3. If new: create ReviewLearning with initial metrics
    4. Persist to .buildlog/review_learnings.json

    Args:
        buildlog_dir: Path to buildlog directory.
        issues: List of review issues with rule_learned field.
        source: Optional source identifier (defaults to timestamp).

    Returns:
        LearnFromReviewResult with new/reinforced learning IDs.
    """
    if not issues:
        return LearnFromReviewResult(
            new_learnings=[],
            reinforced_learnings=[],
            total_issues_processed=0,
            source=source or "",
            error="No issues provided",
        )

    # Default source to timestamp
    now = datetime.now(timezone.utc)
    if source is None:
        source = f"review:{now.isoformat()}"
    elif not source.startswith("review:"):
        source = f"review:{source}"

    learnings_path = _get_learnings_path(buildlog_dir)
    data = _load_learnings(learnings_path)

    new_ids: list[str] = []
    reinforced_ids: list[str] = []
    processed = 0

    for issue_dict in issues:
        # Skip issues without rule_learned
        rule = issue_dict.get("rule_learned", "").strip()
        if not rule:
            continue

        # Parse issue
        issue = ReviewIssue.from_dict(issue_dict)
        learning_id = _generate_learning_id(issue.category, rule)

        if learning_id in data["learnings"]:
            # Reinforce existing learning
            existing_data = data["learnings"][learning_id]
            existing = ReviewLearning.from_dict(existing_data)

            # Use merge_confidence_metrics pattern
            updated_metrics = merge_confidence_metrics(
                existing.to_confidence_metrics(), now
            )

            # Update the learning
            existing_data["last_reinforced"] = now.isoformat()
            existing_data["reinforcement_count"] = updated_metrics.reinforcement_count
            reinforced_ids.append(learning_id)
        else:
            # Create new learning
            learning = ReviewLearning(
                id=learning_id,
                rule=rule,
                category=issue.category,
                severity=issue.severity,
                source=source,
                first_seen=now,
                last_reinforced=now,
                reinforcement_count=1,
                contradiction_count=0,
                functional_principle=issue.functional_principle,
            )
            data["learnings"][learning_id] = learning.to_dict()
            new_ids.append(learning_id)

        processed += 1

    # Record in review history
    data["review_history"].append(
        {
            "timestamp": now.isoformat(),
            "source": source,
            "issues_count": processed,
            "new_learning_ids": new_ids,
            "reinforced_learning_ids": reinforced_ids,
        }
    )

    # Persist
    _save_learnings(learnings_path, data)

    # Build message
    msg_parts = []
    if new_ids:
        msg_parts.append(f"{len(new_ids)} new learning(s)")
    if reinforced_ids:
        msg_parts.append(f"{len(reinforced_ids)} reinforced")
    message = ", ".join(msg_parts) if msg_parts else "No learnings captured"

    return LearnFromReviewResult(
        new_learnings=new_ids,
        reinforced_learnings=reinforced_ids,
        total_issues_processed=processed,
        source=source,
        message=message,
    )
