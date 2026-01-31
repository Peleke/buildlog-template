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
from buildlog.core.bandit import ThompsonSamplingBandit
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
    "RewardEvent",
    "LogRewardResult",
    "RewardSummary",
    # Session tracking (experiment infrastructure)
    "Session",
    "Mistake",
    "SessionMetrics",
    "StartSessionResult",
    "EndSessionResult",
    "LogMistakeResult",
    # Gauntlet loop
    "GauntletLoopResult",
    "GauntletAcceptRiskResult",
    "status",
    "promote",
    "reject",
    "diff",
    "find_skills_by_ids",
    "learn_from_review",
    "log_reward",
    "get_rewards",
    # Session tracking operations
    "start_session",
    "end_session",
    "log_mistake",
    "get_session_metrics",
    "get_experiment_report",
    "get_bandit_status",
    # Gauntlet loop operations
    "gauntlet_process_issues",
    "gauntlet_accept_risk",
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


# -----------------------------------------------------------------------------
# Reward Signal Data Structures (for Bandit Learning)
# -----------------------------------------------------------------------------


class RewardEventDict(TypedDict, total=False):
    """Serializable form of RewardEvent."""

    id: str
    timestamp: str
    outcome: str  # "accepted" | "revision" | "rejected"
    reward_value: float
    rules_active: list[str]
    revision_distance: float | None
    error_class: str | None
    notes: str | None
    source: str | None


@dataclass
class RewardEvent:
    """A single reward/feedback event for bandit learning.

    This tracks human feedback on agent work to enable learning
    which rules are effective in which contexts.

    Attributes:
        id: Unique identifier for this event.
        timestamp: When the feedback was recorded.
        outcome: The feedback type (accepted/revision/rejected).
        reward_value: Numeric reward (1.0=accepted, 0=rejected, in between for revision).
        rules_active: IDs of rules that were in context when work was done.
        revision_distance: How much correction was needed (0-1, lower is better).
        error_class: Category of error if applicable.
        notes: Optional notes about the feedback.
        source: Where this feedback came from (manual, review_loop, etc.).
    """

    id: str
    timestamp: datetime
    outcome: Literal["accepted", "revision", "rejected"]
    reward_value: float
    rules_active: list[str] = field(default_factory=list)
    revision_distance: float | None = None
    error_class: str | None = None
    notes: str | None = None
    source: str | None = None

    def to_dict(self) -> RewardEventDict:
        """Convert to serializable dictionary."""
        result: RewardEventDict = {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "outcome": self.outcome,
            "reward_value": self.reward_value,
            "rules_active": self.rules_active,
        }
        if self.revision_distance is not None:
            result["revision_distance"] = self.revision_distance
        if self.error_class is not None:
            result["error_class"] = self.error_class
        if self.notes is not None:
            result["notes"] = self.notes
        if self.source is not None:
            result["source"] = self.source
        return result

    @classmethod
    def from_dict(cls, data: RewardEventDict) -> "RewardEvent":
        """Reconstruct from serialized dictionary."""
        timestamp = datetime.fromisoformat(data["timestamp"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return cls(
            id=data["id"],
            timestamp=timestamp,
            outcome=data["outcome"],  # type: ignore[arg-type]
            reward_value=data["reward_value"],
            rules_active=data.get("rules_active", []),
            revision_distance=data.get("revision_distance"),
            error_class=data.get("error_class"),
            notes=data.get("notes"),
            source=data.get("source"),
        )


@dataclass
class LogRewardResult:
    """Result of logging a reward event.

    Attributes:
        reward_id: ID of the logged reward event.
        reward_value: The computed reward value.
        total_events: Total reward events logged so far.
        message: Human-readable confirmation.
        error: Error message if operation failed.
    """

    reward_id: str
    reward_value: float
    total_events: int
    message: str = ""
    error: str | None = None


@dataclass
class RewardSummary:
    """Summary statistics for reward events.

    Attributes:
        total_events: Total number of reward events.
        accepted: Count of accepted outcomes.
        revisions: Count of revision outcomes.
        rejected: Count of rejected outcomes.
        mean_reward: Average reward value across all events.
        events: List of reward events (limited by query).
    """

    total_events: int
    accepted: int
    revisions: int
    rejected: int
    mean_reward: float
    events: list[RewardEvent] = field(default_factory=list)


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
    target: str = "claude_md",
    target_path: Path | None = None,
) -> PromoteResult:
    """Promote skills to agent rules.

    Args:
        buildlog_dir: Path to buildlog directory.
        skill_ids: List of skill IDs to promote.
        target: Where to write rules. One of: claude_md, settings_json,
            skill, cursor, copilot, windsurf, continue_dev.
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


# -----------------------------------------------------------------------------
# Reward Signal Operations (for Bandit Learning)
# -----------------------------------------------------------------------------


def _get_rewards_path(buildlog_dir: Path) -> Path:
    """Get path to reward_events.jsonl file."""
    return buildlog_dir / ".buildlog" / "reward_events.jsonl"


def _generate_reward_id(outcome: str, timestamp: datetime) -> str:
    """Generate unique ID for a reward event.

    Uses outcome + timestamp to ensure uniqueness while allowing
    multiple events with the same outcome.
    """
    ts_str = timestamp.isoformat()
    normalized = f"{outcome}:{ts_str}"
    hash_hex = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"rew-{hash_hex}"


def _compute_reward_value(
    outcome: Literal["accepted", "revision", "rejected"],
    revision_distance: float | None,
) -> float:
    """Compute numeric reward from outcome.

    Args:
        outcome: The feedback type.
        revision_distance: How much correction needed (0-1).

    Returns:
        Reward value in [0, 1].
        - accepted: 1.0
        - rejected: 0.0
        - revision: 1.0 - distance (default distance 0.5 if not provided)
    """
    if outcome == "accepted":
        return 1.0
    elif outcome == "rejected":
        return 0.0
    else:  # revision
        distance = revision_distance if revision_distance is not None else 0.5
        return max(0.0, min(1.0, 1.0 - distance))


def log_reward(
    buildlog_dir: Path,
    outcome: Literal["accepted", "revision", "rejected"],
    rules_active: list[str] | None = None,
    revision_distance: float | None = None,
    error_class: str | None = None,
    notes: str | None = None,
    source: str | None = None,
) -> LogRewardResult:
    """Log a reward event for bandit learning.

    This is where the bandit learns from EXPLICIT feedback:

    The reward signal comes from the outcome:
        - accepted (reward=1.0): Rules helped produce good output
        - rejected (reward=0.0): Rules failed to prevent bad output
        - revision (reward=1-distance): Partial credit based on correction needed

    Unlike log_mistake() which gives implicit negative feedback, this allows
    direct positive feedback when rules DO help. This is crucial for learning
    which rules are genuinely effective, not just which ones don't fail.

    Appends to reward_events.jsonl for analysis AND updates the bandit.

    Args:
        buildlog_dir: Path to buildlog directory.
        outcome: Type of feedback (accepted/revision/rejected).
        rules_active: List of rule IDs that were in context.
                     If None, tries to use session's selected_rules.
        revision_distance: How much correction was needed (0-1, for revisions).
        error_class: Category of error if applicable.
                    If None, tries to use session's error_class.
        notes: Optional notes about the feedback.
        source: Where this feedback came from.

    Returns:
        LogRewardResult with confirmation.
    """
    now = datetime.now(timezone.utc)
    reward_id = _generate_reward_id(outcome, now)
    reward_value = _compute_reward_value(outcome, revision_distance)

    # Try to get rules and context from active session if not provided
    active_path = _get_active_session_path(buildlog_dir)
    if active_path.exists():
        session_data = json.loads(active_path.read_text())
        if rules_active is None:
            rules_active = session_data.get("selected_rules", [])
        if error_class is None:
            error_class = session_data.get("error_class")

    event = RewardEvent(
        id=reward_id,
        timestamp=now,
        outcome=outcome,
        reward_value=reward_value,
        rules_active=rules_active or [],
        revision_distance=revision_distance,
        error_class=error_class,
        notes=notes,
        source=source or "manual",
    )

    # Append to JSONL file
    rewards_path = _get_rewards_path(buildlog_dir)
    rewards_path.parent.mkdir(parents=True, exist_ok=True)

    with open(rewards_path, "a") as f:
        f.write(json.dumps(event.to_dict()) + "\n")

    # =========================================================================
    # BANDIT LEARNING: Update with explicit reward
    # =========================================================================
    #
    # For accepted (reward=1): Beta(α, β) → Beta(α + 1, β)
    #   → Distribution shifts RIGHT, increasing expected value
    #   → Rule becomes MORE likely to be selected
    #
    # For rejected (reward=0): Beta(α, β) → Beta(α, β + 1)
    #   → Distribution shifts LEFT, decreasing expected value
    #   → Rule becomes LESS likely to be selected
    #
    # For revision (0 < reward < 1): Both α and β increase proportionally
    #   → Distribution narrows (more confident) with moderate expected value
    # =========================================================================

    if rules_active:
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)

        bandit.batch_update(
            rule_ids=rules_active,
            reward=reward_value,
            context=error_class or "general",
        )

    # Count total events
    total_events = 0
    if rewards_path.exists():
        total_events = sum(
            1 for line in rewards_path.read_text().strip().split("\n") if line
        )

    rules_count = len(rules_active) if rules_active else 0
    message = f"Logged {outcome} (reward={reward_value:.2f})"
    if rules_count > 0:
        message += f" | Updated bandit: {rules_count} rules"

    return LogRewardResult(
        reward_id=reward_id,
        reward_value=reward_value,
        total_events=total_events,
        message=message,
    )


def get_rewards(
    buildlog_dir: Path,
    limit: int | None = None,
) -> RewardSummary:
    """Get reward events with summary statistics.

    Args:
        buildlog_dir: Path to buildlog directory.
        limit: Maximum number of events to return (most recent first).

    Returns:
        RewardSummary with events and statistics.
    """
    rewards_path = _get_rewards_path(buildlog_dir)

    if not rewards_path.exists():
        return RewardSummary(
            total_events=0,
            accepted=0,
            revisions=0,
            rejected=0,
            mean_reward=0.0,
            events=[],
        )

    # Parse all events
    events: list[RewardEvent] = []
    for line in rewards_path.read_text().strip().split("\n"):
        if line:
            try:
                data = json.loads(line)
                events.append(RewardEvent.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue  # Skip malformed lines

    # Calculate statistics
    total = len(events)
    accepted = sum(1 for e in events if e.outcome == "accepted")
    revisions = sum(1 for e in events if e.outcome == "revision")
    rejected = sum(1 for e in events if e.outcome == "rejected")
    mean_reward = sum(e.reward_value for e in events) / total if total > 0 else 0.0

    # Sort by timestamp (most recent first) and limit
    events.sort(key=lambda e: e.timestamp, reverse=True)
    if limit is not None:
        events = events[:limit]

    return RewardSummary(
        total_events=total,
        accepted=accepted,
        revisions=revisions,
        rejected=rejected,
        mean_reward=mean_reward,
        events=events,
    )


# -----------------------------------------------------------------------------
# Session Tracking Data Structures (for Experimental Infrastructure)
# -----------------------------------------------------------------------------


class SessionDict(TypedDict, total=False):
    """Serializable form of Session."""

    id: str
    started_at: str
    ended_at: str | None
    entry_file: str | None
    rules_at_start: list[str]
    rules_at_end: list[str]
    selected_rules: list[str]  # Bandit-selected subset for this session
    error_class: str | None
    notes: str | None


@dataclass
class Session:
    """A coding session for experiment tracking.

    Tracks the state of rules before and after a session to measure
    learning effectiveness. The bandit selects a subset of rules
    (selected_rules) to be "active" for this session based on context.

    Attributes:
        id: Unique identifier for this session.
        started_at: When the session started.
        ended_at: When the session ended (None if still active).
        entry_file: Corresponding buildlog entry file, if any.
        rules_at_start: All rule IDs available at session start.
        rules_at_end: All rule IDs available at session end.
        selected_rules: Bandit-selected subset active for this session.
        error_class: Error class being targeted (e.g., "missing_test").
        notes: Optional notes about the session.
    """

    id: str
    started_at: datetime
    ended_at: datetime | None = None
    entry_file: str | None = None
    rules_at_start: list[str] = field(default_factory=list)
    rules_at_end: list[str] = field(default_factory=list)
    selected_rules: list[str] = field(default_factory=list)
    error_class: str | None = None
    notes: str | None = None

    def to_dict(self) -> SessionDict:
        """Convert to serializable dictionary."""
        result: SessionDict = {
            "id": self.id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "rules_at_start": self.rules_at_start,
            "rules_at_end": self.rules_at_end,
        }
        if self.selected_rules:
            result["selected_rules"] = self.selected_rules
        if self.entry_file is not None:
            result["entry_file"] = self.entry_file
        if self.error_class is not None:
            result["error_class"] = self.error_class
        if self.notes is not None:
            result["notes"] = self.notes
        return result

    @classmethod
    def from_dict(cls, data: SessionDict) -> "Session":
        """Reconstruct from serialized dictionary."""
        started_at = datetime.fromisoformat(data["started_at"])
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        ended_at = None
        ended_at_str = data.get("ended_at")
        if ended_at_str:
            ended_at = datetime.fromisoformat(ended_at_str)
            if ended_at.tzinfo is None:
                ended_at = ended_at.replace(tzinfo=timezone.utc)

        return cls(
            id=data["id"],
            started_at=started_at,
            ended_at=ended_at,
            entry_file=data.get("entry_file"),
            rules_at_start=data.get("rules_at_start", []),
            rules_at_end=data.get("rules_at_end", []),
            selected_rules=data.get("selected_rules", []),
            error_class=data.get("error_class"),
            notes=data.get("notes"),
        )


class MistakeDict(TypedDict, total=False):
    """Serializable form of Mistake."""

    id: str
    session_id: str
    timestamp: str
    error_class: str
    description: str
    semantic_hash: str  # Simplified from embedding - hash of description
    was_repeat: bool
    corrected_by_rule: str | None


@dataclass
class Mistake:
    """A logged mistake during a session.

    Tracks mistakes to measure repeated-mistake rate.

    Attributes:
        id: Unique identifier for this mistake.
        session_id: Session in which this mistake occurred.
        timestamp: When the mistake was logged.
        error_class: Category of error (e.g., "missing_test").
        description: Description of the mistake.
        semantic_hash: Hash of description for similarity matching.
        was_repeat: Whether this was a repeat of a prior mistake.
        corrected_by_rule: Rule ID that should have prevented this, if any.
    """

    id: str
    session_id: str
    timestamp: datetime
    error_class: str
    description: str
    semantic_hash: str
    was_repeat: bool = False
    corrected_by_rule: str | None = None

    def to_dict(self) -> MistakeDict:
        """Convert to serializable dictionary."""
        result: MistakeDict = {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "error_class": self.error_class,
            "description": self.description,
            "semantic_hash": self.semantic_hash,
            "was_repeat": self.was_repeat,
        }
        if self.corrected_by_rule is not None:
            result["corrected_by_rule"] = self.corrected_by_rule
        return result

    @classmethod
    def from_dict(cls, data: MistakeDict) -> "Mistake":
        """Reconstruct from serialized dictionary."""
        timestamp = datetime.fromisoformat(data["timestamp"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return cls(
            id=data["id"],
            session_id=data["session_id"],
            timestamp=timestamp,
            error_class=data["error_class"],
            description=data["description"],
            semantic_hash=data["semantic_hash"],
            was_repeat=data.get("was_repeat", False),
            corrected_by_rule=data.get("corrected_by_rule"),
        )


@dataclass
class SessionMetrics:
    """Metrics for a session or aggregated across sessions.

    Attributes:
        session_id: Session ID (or "aggregate" for combined metrics).
        total_mistakes: Total mistakes in the session(s).
        repeated_mistakes: Mistakes that were repeats.
        repeated_mistake_rate: Ratio of repeated to total mistakes.
        rules_at_start: Number of rules at session start.
        rules_at_end: Number of rules at session end.
        rules_added: Net rules added during session(s).
    """

    session_id: str
    total_mistakes: int
    repeated_mistakes: int
    repeated_mistake_rate: float
    rules_at_start: int
    rules_at_end: int
    rules_added: int


@dataclass
class StartSessionResult:
    """Result of starting a new session.

    Includes both the full rule set and the bandit-selected subset.
    """

    session_id: str
    error_class: str | None
    rules_count: int
    selected_rules: list[str]  # Bandit-selected rules for this session
    message: str


@dataclass
class EndSessionResult:
    """Result of ending a session."""

    session_id: str
    duration_minutes: float
    mistakes_logged: int
    repeated_mistakes: int
    rules_at_start: int
    rules_at_end: int
    message: str


@dataclass
class LogMistakeResult:
    """Result of logging a mistake."""

    mistake_id: str
    session_id: str
    was_repeat: bool
    similar_prior: str | None  # ID of similar prior mistake if repeat
    message: str


# -----------------------------------------------------------------------------
# Session Tracking Helper Functions
# -----------------------------------------------------------------------------


def _get_sessions_path(buildlog_dir: Path) -> Path:
    """Get path to sessions JSONL file."""
    return buildlog_dir / ".buildlog" / "sessions.jsonl"


def _get_mistakes_path(buildlog_dir: Path) -> Path:
    """Get path to mistakes JSONL file."""
    return buildlog_dir / ".buildlog" / "mistakes.jsonl"


def _get_active_session_path(buildlog_dir: Path) -> Path:
    """Get path to active session marker file."""
    return buildlog_dir / ".buildlog" / "active_session.json"


def _generate_session_id(now: datetime) -> str:
    """Generate a unique session ID."""
    # Include microseconds for uniqueness when sessions are created quickly
    return f"session-{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond:06d}"


def _generate_mistake_id(error_class: str, now: datetime) -> str:
    """Generate a unique mistake ID."""
    # Include microseconds for uniqueness
    return f"mistake-{error_class[:10]}-{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond:06d}"


def _compute_semantic_hash(description: str) -> str:
    """Compute a hash for semantic similarity matching.

    This is a simplified approach - in production, you'd use embeddings.
    For now, we normalize and hash the description.
    """
    import hashlib

    # Normalize: lowercase, remove extra whitespace
    normalized = " ".join(description.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _get_current_rules(buildlog_dir: Path) -> list[str]:
    """Get list of current promoted rule IDs."""
    promoted_path = _get_promoted_path(buildlog_dir)
    return list(_load_json_set(promoted_path, "skill_ids"))


def _get_seed_rule_ids(buildlog_dir: Path) -> set[str]:
    """Get IDs of rules that come from seed personas.

    Seed rules (from gauntlet personas like Test Terrorist, Security Karen)
    have non-empty persona_tags. These rules get boosted priors in the
    bandit because they represent curated, expert knowledge.

    Returns:
        Set of rule IDs that have persona_tags.
    """
    try:
        skill_set = generate_skills(buildlog_dir)
        seed_ids: set[str] = set()

        for category_skills in skill_set.skills.values():
            for skill in category_skills:
                if skill.persona_tags:  # Non-empty means it's from a seed
                    seed_ids.add(skill.id)

        return seed_ids
    except Exception:
        # If skill generation fails, treat no rules as seeds
        return set()


def _load_sessions(buildlog_dir: Path) -> list[Session]:
    """Load all sessions from JSONL file."""
    sessions_path = _get_sessions_path(buildlog_dir)
    if not sessions_path.exists():
        return []

    sessions = []
    for line in sessions_path.read_text().strip().split("\n"):
        if line:
            try:
                data = json.loads(line)
                sessions.append(Session.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
    return sessions


def _load_mistakes(buildlog_dir: Path) -> list[Mistake]:
    """Load all mistakes from JSONL file."""
    mistakes_path = _get_mistakes_path(buildlog_dir)
    if not mistakes_path.exists():
        return []

    mistakes = []
    for line in mistakes_path.read_text().strip().split("\n"):
        if line:
            try:
                data = json.loads(line)
                mistakes.append(Mistake.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
    return mistakes


def _find_similar_prior_mistake(
    description: str,
    error_class: str,
    current_session_id: str,
    all_mistakes: list[Mistake],
) -> Mistake | None:
    """Find a similar mistake from a prior session.

    Uses semantic hash for similarity matching (simplified approach).
    """
    semantic_hash = _compute_semantic_hash(description)

    for mistake in all_mistakes:
        # Only check mistakes from prior sessions with same error class
        if (
            mistake.session_id != current_session_id
            and mistake.error_class == error_class
        ):
            # Check for semantic similarity (hash match or high description overlap)
            if mistake.semantic_hash == semantic_hash:
                return mistake
            # Also check for high word overlap
            desc_words = set(description.lower().split())
            mistake_words = set(mistake.description.lower().split())
            if len(desc_words & mistake_words) / max(len(desc_words), 1) > 0.7:
                return mistake

    return None


# -----------------------------------------------------------------------------
# Session Tracking Operations
# -----------------------------------------------------------------------------


def start_session(
    buildlog_dir: Path,
    error_class: str | None = None,
    notes: str | None = None,
    select_k: int = 3,
) -> StartSessionResult:
    """Start a new experiment session with bandit-selected rules.

    This is where Thompson Sampling kicks in:

    1. Load all available rules (candidates)
    2. Identify which rules are from seeds (get boosted priors)
    3. Use bandit to select top-k rules for this error_class context
    4. Store selected rules in session for later attribution

    The selected rules are the ones "active" for this session. When a
    mistake occurs, we'll give negative feedback to these rules (they
    didn't prevent the mistake). This teaches the bandit which rules
    are effective for which error classes.

    Args:
        buildlog_dir: Path to buildlog directory.
        error_class: Error class being targeted (e.g., "missing_test").
                    This is the CONTEXT for contextual bandits - rules
                    are evaluated per-context.
        notes: Optional notes about the session.
        select_k: Number of rules to select via Thompson Sampling.
                 Default 3 balances coverage with attribution clarity.

    Returns:
        StartSessionResult with session ID, rules count, and selected rules.
    """
    now = datetime.now(timezone.utc)
    session_id = _generate_session_id(now)
    current_rules = _get_current_rules(buildlog_dir)

    # =========================================================================
    # THOMPSON SAMPLING: Select rules for this session
    # =========================================================================
    #
    # The bandit maintains a Beta distribution for each (context, rule) pair.
    # At session start, we SAMPLE from each distribution and pick the top-k.
    #
    # Why sample instead of using the mean?
    #   - Arms we're uncertain about have high variance
    #   - High variance means occasional high samples
    #   - This causes us to explore uncertain arms
    #   - As we gather data, variance shrinks, and we exploit
    #
    # This is the elegant explore-exploit balance of Thompson Sampling.
    # =========================================================================

    selected_rules: list[str] = []

    if current_rules:
        # Initialize bandit
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)

        # Identify seed rules (those with persona_tags from gauntlet)
        # Seeds get boosted priors - we believe curated rules are good
        seed_rule_ids = _get_seed_rule_ids(buildlog_dir)

        # SELECT: Sample from Beta distributions, pick top-k
        selected_rules = bandit.select(
            candidates=current_rules,
            context=error_class or "general",
            k=min(select_k, len(current_rules)),
            seed_rule_ids=seed_rule_ids,
        )

    session = Session(
        id=session_id,
        started_at=now,
        rules_at_start=current_rules,
        selected_rules=selected_rules,
        error_class=error_class,
        notes=notes,
    )

    # Save as active session
    active_path = _get_active_session_path(buildlog_dir)
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(json.dumps(session.to_dict(), indent=2))

    return StartSessionResult(
        session_id=session_id,
        error_class=error_class,
        rules_count=len(current_rules),
        selected_rules=selected_rules,
        message=(
            f"Started session {session_id}: selected {len(selected_rules)}/"
            f"{len(current_rules)} rules via Thompson Sampling"
        ),
    )


def end_session(
    buildlog_dir: Path,
    entry_file: str | None = None,
    notes: str | None = None,
) -> EndSessionResult:
    """End the current experiment session.

    Args:
        buildlog_dir: Path to buildlog directory.
        entry_file: Corresponding buildlog entry file, if any.
        notes: Additional notes to append.

    Returns:
        EndSessionResult with session metrics.
    """
    active_path = _get_active_session_path(buildlog_dir)

    if not active_path.exists():
        raise ValueError("No active session to end")

    # Load active session
    session_data = json.loads(active_path.read_text())
    session = Session.from_dict(session_data)

    # Update session with end info
    now = datetime.now(timezone.utc)
    session.ended_at = now
    session.rules_at_end = _get_current_rules(buildlog_dir)
    if entry_file:
        session.entry_file = entry_file
    if notes:
        session.notes = f"{session.notes or ''}\n{notes}".strip()

    # Append to sessions log
    sessions_path = _get_sessions_path(buildlog_dir)
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sessions_path, "a") as f:
        f.write(json.dumps(session.to_dict()) + "\n")

    # Remove active session marker
    active_path.unlink()

    # Calculate session metrics
    all_mistakes = _load_mistakes(buildlog_dir)
    session_mistakes = [m for m in all_mistakes if m.session_id == session.id]
    repeated = sum(1 for m in session_mistakes if m.was_repeat)

    duration = (session.ended_at - session.started_at).total_seconds() / 60

    return EndSessionResult(
        session_id=session.id,
        duration_minutes=round(duration, 1),
        mistakes_logged=len(session_mistakes),
        repeated_mistakes=repeated,
        rules_at_start=len(session.rules_at_start),
        rules_at_end=len(session.rules_at_end),
        message=f"Ended session {session.id} ({duration:.1f}min, {len(session_mistakes)} mistakes, {repeated} repeats)",
    )


def log_mistake(
    buildlog_dir: Path,
    error_class: str,
    description: str,
    corrected_by_rule: str | None = None,
) -> LogMistakeResult:
    """Log a mistake during an experiment session.

    This is where the bandit learns from NEGATIVE feedback:

    When a mistake occurs, the selected rules for this session FAILED
    to prevent it. We update the bandit with reward=0 for each selected
    rule, teaching it that these rules aren't effective for this context.

    Over time, rules that consistently fail to prevent mistakes will
    have their Beta distributions shift left (lower expected value),
    and the bandit will stop selecting them.

    Args:
        buildlog_dir: Path to buildlog directory.
        error_class: Category of error (e.g., "missing_test").
        description: Description of the mistake.
        corrected_by_rule: Rule ID that should have prevented this.

    Returns:
        LogMistakeResult indicating if this was a repeat.
    """
    active_path = _get_active_session_path(buildlog_dir)

    if not active_path.exists():
        raise ValueError(
            "No active session - start one with 'buildlog experiment start'"
        )

    # Get current session
    session_data = json.loads(active_path.read_text())
    session_id = session_data["id"]

    now = datetime.now(timezone.utc)
    mistake_id = _generate_mistake_id(error_class, now)

    # Check for similar prior mistakes
    all_mistakes = _load_mistakes(buildlog_dir)
    similar = _find_similar_prior_mistake(
        description, error_class, session_id, all_mistakes
    )

    mistake = Mistake(
        id=mistake_id,
        session_id=session_id,
        timestamp=now,
        error_class=error_class,
        description=description,
        semantic_hash=_compute_semantic_hash(description),
        was_repeat=similar is not None,
        corrected_by_rule=corrected_by_rule,
    )

    # Append to mistakes log
    mistakes_path = _get_mistakes_path(buildlog_dir)
    mistakes_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mistakes_path, "a") as f:
        f.write(json.dumps(mistake.to_dict()) + "\n")

    # =========================================================================
    # BANDIT LEARNING: Negative feedback for selected rules
    # =========================================================================
    #
    # The selected rules were supposed to help prevent mistakes. A mistake
    # occurred anyway, so we give them reward=0 (failure).
    #
    # Bayesian update: Beta(α, β) → Beta(α + 0, β + 1) = Beta(α, β + 1)
    #
    # This shifts the distribution LEFT, decreasing the expected value.
    # Rules that repeatedly fail will become less likely to be selected.
    # =========================================================================

    selected_rules = session_data.get("selected_rules", [])
    if selected_rules:
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)

        # Use session's error_class as context, not the mistake's
        # (they should match, but session context is authoritative)
        context = session_data.get("error_class") or "general"

        bandit.batch_update(
            rule_ids=selected_rules,
            reward=0.0,  # Failure: rules didn't prevent mistake
            context=context,
        )

    message = f"Logged mistake: {error_class}"
    if similar:
        message += f" (REPEAT of {similar.id})"
    if selected_rules:
        message += f" | Updated bandit: {len(selected_rules)} rules got reward=0"

    return LogMistakeResult(
        mistake_id=mistake_id,
        session_id=session_id,
        was_repeat=similar is not None,
        similar_prior=similar.id if similar else None,
        message=message,
    )


def get_session_metrics(
    buildlog_dir: Path,
    session_id: str | None = None,
) -> SessionMetrics:
    """Get metrics for a session or all sessions.

    Args:
        buildlog_dir: Path to buildlog directory.
        session_id: Specific session ID, or None for aggregate metrics.

    Returns:
        SessionMetrics with mistake rates and rule changes.
    """
    sessions = _load_sessions(buildlog_dir)
    mistakes = _load_mistakes(buildlog_dir)

    if session_id:
        # Filter to specific session
        session = next((s for s in sessions if s.id == session_id), None)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        session_mistakes = [m for m in mistakes if m.session_id == session_id]
        total = len(session_mistakes)
        repeated = sum(1 for m in session_mistakes if m.was_repeat)

        return SessionMetrics(
            session_id=session_id,
            total_mistakes=total,
            repeated_mistakes=repeated,
            repeated_mistake_rate=repeated / total if total > 0 else 0.0,
            rules_at_start=len(session.rules_at_start),
            rules_at_end=len(session.rules_at_end),
            rules_added=len(session.rules_at_end) - len(session.rules_at_start),
        )
    else:
        # Aggregate across all sessions
        total = len(mistakes)
        repeated = sum(1 for m in mistakes if m.was_repeat)

        rules_start = sessions[0].rules_at_start if sessions else []
        rules_end = sessions[-1].rules_at_end if sessions else []

        return SessionMetrics(
            session_id="aggregate",
            total_mistakes=total,
            repeated_mistakes=repeated,
            repeated_mistake_rate=repeated / total if total > 0 else 0.0,
            rules_at_start=len(rules_start),
            rules_at_end=len(rules_end),
            rules_added=len(rules_end) - len(rules_start),
        )


def get_experiment_report(buildlog_dir: Path) -> dict:
    """Generate a comprehensive experiment report.

    Returns:
        Dictionary with sessions, metrics, and analysis.
    """
    sessions = _load_sessions(buildlog_dir)
    mistakes = _load_mistakes(buildlog_dir)

    # Per-session metrics
    session_metrics = []
    for session in sessions:
        session_mistakes = [m for m in mistakes if m.session_id == session.id]
        total = len(session_mistakes)
        repeated = sum(1 for m in session_mistakes if m.was_repeat)
        session_metrics.append(
            {
                "session_id": session.id,
                "started_at": session.started_at.isoformat(),
                "error_class": session.error_class,
                "total_mistakes": total,
                "repeated_mistakes": repeated,
                "repeated_mistake_rate": repeated / total if total > 0 else 0.0,
                "rules_added": len(session.rules_at_end) - len(session.rules_at_start),
            }
        )

    # Aggregate metrics
    total_mistakes = len(mistakes)
    total_repeated = sum(1 for m in mistakes if m.was_repeat)

    # Error class breakdown
    error_classes: dict[str, dict] = {}
    for mistake in mistakes:
        if mistake.error_class not in error_classes:
            error_classes[mistake.error_class] = {"total": 0, "repeated": 0}
        error_classes[mistake.error_class]["total"] += 1
        if mistake.was_repeat:
            error_classes[mistake.error_class]["repeated"] += 1

    return {
        "summary": {
            "total_sessions": len(sessions),
            "total_mistakes": total_mistakes,
            "total_repeated": total_repeated,
            "overall_repeat_rate": (
                total_repeated / total_mistakes if total_mistakes > 0 else 0.0
            ),
        },
        "sessions": session_metrics,
        "error_classes": error_classes,
    }


def get_bandit_status(
    buildlog_dir: Path,
    context: str | None = None,
    top_k: int = 10,
) -> dict:
    """Get current bandit state and statistics.

    Provides insight into the Thompson Sampling bandit's learned beliefs.
    Useful for debugging and understanding which rules are being favored.

    Args:
        buildlog_dir: Path to buildlog directory.
        context: Specific error class to show. If None, shows all contexts.
        top_k: Number of top rules to show per context.

    Returns:
        Dictionary with:
            - summary: Overall bandit statistics
            - contexts: Per-context rule rankings
            - top_rules: Top rules by expected value per context
    """
    bandit_path = buildlog_dir / "bandit_state.jsonl"
    bandit = ThompsonSamplingBandit(bandit_path)

    stats = bandit.get_stats(context)

    # Group stats by context
    contexts: dict[str, list[dict]] = {}
    for key, rule_stats in stats.items():
        ctx = rule_stats["context"]
        if ctx not in contexts:
            contexts[ctx] = []
        contexts[ctx].append(
            {
                "rule_id": key.split(":")[-1] if ":" in key else key,
                **{k: v for k, v in rule_stats.items() if k != "context"},
            }
        )

    # Sort by mean (descending) and take top_k
    top_rules: dict[str, list[dict]] = {}
    for ctx, rules in contexts.items():
        sorted_rules = sorted(rules, key=lambda x: x["mean"], reverse=True)
        top_rules[ctx] = sorted_rules[:top_k]

    # Summary stats
    total_arms = sum(len(rules) for rules in contexts.values())
    total_observations = sum(
        rule.get("total_observations", 0)
        for rules in contexts.values()
        for rule in rules
    )

    return {
        "summary": {
            "total_contexts": len(contexts),
            "total_arms": total_arms,
            "total_observations": total_observations,
            "state_file": str(bandit_path),
        },
        "top_rules": top_rules,
        "all_rules": contexts if context else None,  # Only include all if filtering
    }


# =============================================================================
# Gauntlet Loop Operations
# =============================================================================


@dataclass
class GauntletLoopResult:
    """Result of processing gauntlet issues.

    Attributes:
        action: What to do next:
            - "fix_criticals": Criticals remain, auto-fix and loop
            - "checkpoint_majors": No criticals, but majors remain (HITL)
            - "checkpoint_minors": Only minors remain (HITL)
            - "clean": No issues remain
        criticals: List of critical severity issues
        majors: List of major severity issues
        minors: List of minor/nitpick severity issues
        iteration: Current iteration number
        learnings_persisted: Number of learnings persisted this iteration
        message: Human-readable summary
    """

    action: Literal["fix_criticals", "checkpoint_majors", "checkpoint_minors", "clean"]
    criticals: list[dict]
    majors: list[dict]
    minors: list[dict]
    iteration: int
    learnings_persisted: int
    message: str


@dataclass
class GauntletAcceptRiskResult:
    """Result of accepting risk with remaining issues.

    Attributes:
        accepted_issues: Number of issues accepted as risk
        github_issues_created: Number of GitHub issues created (if enabled)
        github_issue_urls: URLs of created GitHub issues
        message: Human-readable summary
        error: Error message if operation failed
    """

    accepted_issues: int
    github_issues_created: int
    github_issue_urls: list[str]
    message: str
    error: str | None = None


def gauntlet_process_issues(
    buildlog_dir: Path,
    issues: list[dict],
    iteration: int = 1,
    source: str | None = None,
) -> GauntletLoopResult:
    """Process gauntlet issues and determine next action.

    Categorizes issues by severity, persists learnings, and returns
    the appropriate next action for the gauntlet loop.

    Args:
        buildlog_dir: Path to buildlog directory.
        issues: List of issues from the gauntlet review.
        iteration: Current iteration number (for tracking).
        source: Optional source identifier for learnings.

    Returns:
        GauntletLoopResult with categorized issues and next action.
    """
    # Categorize by severity
    criticals = [i for i in issues if i.get("severity") == "critical"]
    majors = [i for i in issues if i.get("severity") == "major"]
    minors = [i for i in issues if i.get("severity") in ("minor", "nitpick", None)]

    # Persist learnings for this iteration
    learn_source = source or f"gauntlet:iteration-{iteration}"
    learn_result = learn_from_review(buildlog_dir, issues, learn_source)
    learnings_persisted = len(learn_result.new_learnings) + len(
        learn_result.reinforced_learnings
    )

    # Determine action
    if criticals:
        action: Literal[
            "fix_criticals", "checkpoint_majors", "checkpoint_minors", "clean"
        ] = "fix_criticals"
        message = (
            f"Iteration {iteration}: {len(criticals)} critical, "
            f"{len(majors)} major, {len(minors)} minor. "
            f"Fix criticals (and majors) then re-run."
        )
    elif majors:
        action = "checkpoint_majors"
        message = (
            f"Iteration {iteration}: No criticals! "
            f"{len(majors)} major, {len(minors)} minor remain. "
            f"Continue clearing majors?"
        )
    elif minors:
        action = "checkpoint_minors"
        message = (
            f"Iteration {iteration}: Only {len(minors)} minor issues remain. "
            f"Accept risk or continue?"
        )
    else:
        action = "clean"
        message = f"Iteration {iteration}: All clear! No issues found."

    return GauntletLoopResult(
        action=action,
        criticals=criticals,
        majors=majors,
        minors=minors,
        iteration=iteration,
        learnings_persisted=learnings_persisted,
        message=message,
    )


def gauntlet_accept_risk(
    remaining_issues: list[dict],
    create_github_issues: bool = False,
    repo: str | None = None,
) -> GauntletAcceptRiskResult:
    """Accept risk for remaining issues, optionally creating GitHub issues.

    Args:
        remaining_issues: Issues being accepted as risk.
        create_github_issues: Whether to create GitHub issues for tracking.
        repo: Repository for GitHub issues (uses current repo if None).

    Returns:
        GauntletAcceptRiskResult with created issue info.
    """
    import subprocess

    github_urls: list[str] = []
    error: str | None = None

    if create_github_issues and remaining_issues:
        for issue in remaining_issues:
            severity = issue.get("severity", "minor")
            rule = issue.get("rule_learned", issue.get("description", "Unknown"))
            description = issue.get("description", "")
            location = issue.get("location", "")

            # Sanitize inputs for GitHub issue creation
            # Note: We use list args (not shell=True), so this is defense-in-depth
            def _sanitize_for_gh(text: str, max_len: int = 256) -> str:
                """Sanitize text for GitHub issue fields."""
                # Remove/replace problematic characters
                sanitized = text.replace("\n", " ").replace("\r", " ")
                # Truncate to max length
                if len(sanitized) > max_len:
                    sanitized = sanitized[: max_len - 3] + "..."
                return sanitized.strip()

            safe_severity = _sanitize_for_gh(str(severity), 20)
            safe_rule = _sanitize_for_gh(str(rule), 200)
            safe_description = _sanitize_for_gh(str(description), 1000)
            safe_location = _sanitize_for_gh(str(location), 100)

            # Build issue body
            body_parts = [
                f"**Severity:** {safe_severity}",
                f"**Rule:** {safe_rule}",
                "",
                "## Description",
                safe_description,
            ]
            if safe_location:
                body_parts.extend(["", f"**Location:** `{safe_location}`"])

            body_parts.extend(
                [
                    "",
                    "---",
                    "_Created by buildlog gauntlet loop (accepted risk)_",
                ]
            )

            body = "\n".join(body_parts)
            title = f"[Gauntlet/{safe_severity}] {safe_rule[:60]}"

            # Create GitHub issue
            cmd = [
                "gh",
                "issue",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--label",
                severity,
            ]
            if repo:
                cmd.extend(["--repo", repo])

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                # gh issue create outputs the URL
                url = result.stdout.strip()
                if url:
                    github_urls.append(url)
            except subprocess.CalledProcessError as e:
                # Don't fail entirely, just note the error
                error = f"Failed to create some GitHub issues: {e.stderr}"
            except FileNotFoundError:
                error = "gh CLI not found. Install GitHub CLI to create issues."
                break

    return GauntletAcceptRiskResult(
        accepted_issues=len(remaining_issues),
        github_issues_created=len(github_urls),
        github_issue_urls=github_urls,
        message=(
            f"Accepted {len(remaining_issues)} issues as risk. "
            f"Created {len(github_urls)} GitHub issues."
            if create_github_issues
            else f"Accepted {len(remaining_issues)} issues as risk."
        ),
        error=error,
    )
