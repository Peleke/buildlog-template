"""Core operations for buildlog skill management.

This module contains the business logic that can be exposed via
MCP, CLI, HTTP, or any other interface.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from buildlog.core.report import ImprovementsReportData

from buildlog.confidence import ConfidenceMetrics, merge_confidence_metrics
from buildlog.core.learning import get_learning_backend
from buildlog.render import get_renderer
from buildlog.skills import Skill, SkillSet, generate_skills
from buildlog.storage import StorageBackend, get_backend

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
    # Entry & overview operations
    "GauntletRulesResult",
    "OverviewResult",
    "CreateEntryResult",
    "ListEntriesResult",
    "get_gauntlet_rules",
    "get_overview",
    "create_entry",
    "list_entries",
    # P0: Gauntlet loop
    "CommitResult",
    "GauntletPromptResult",
    "GauntletLoopConfigResult",
    "commit",
    "generate_gauntlet_prompt",
    "gauntlet_loop_config",
    # P2: Nice-to-have
    "GauntletGenerateResult",
    "InitResult",
    "UpdateResult",
    "gauntlet_generate",
    "init_buildlog",
    "update_buildlog",
]


# CI width below which a bandit arm is considered "converging".
# With Beta(a, b), 95% CI width ≈ 3.92 * sqrt(ab / ((a+b)^2 * (a+b+1))).
# 0.2 corresponds to roughly 25+ observations with moderate success rate.
_CONVERGENCE_CI_WIDTH = 0.2


def _get_storage(buildlog_dir: Path) -> tuple[StorageBackend, str]:
    """Resolve the storage backend for the project containing *buildlog_dir*.

    The project root is assumed to be ``buildlog_dir.parent`` (e.g.
    ``/my-project/buildlog`` → ``/my-project``).
    """
    project_root = (
        buildlog_dir.parent if buildlog_dir.name == "buildlog" else buildlog_dir.parent
    )
    return get_backend(buildlog_dir, project_root=project_root)


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

    message: str = ""
    """Human-readable summary."""

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

    message: str = ""
    """Human-readable summary."""

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

    message: str = ""
    """Human-readable summary."""

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
    session_id: str | None


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
    session_id: str | None = None

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
        if self.session_id is not None:
            result["session_id"] = self.session_id
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
            session_id=data.get("session_id"),
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
    backend, project_id = _get_storage(buildlog_dir)
    rejected_ids = backend.load_id_set(project_id, "rejected")

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

    parts = [f"{actual_total} skills from {skill_set.source_entries} entries"]
    if promotable:
        parts.append(f"{len(promotable)} ready to promote")
    return StatusResult(
        skills=filtered,
        total_entries=skill_set.source_entries,
        total_skills=actual_total,
        by_confidence=by_confidence,
        promotable_ids=promotable,
        message=" | ".join(parts),
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

    # Persist promoted IDs to storage backend
    backend, project_id = _get_storage(buildlog_dir)
    existing = backend.load_id_set(project_id, "promoted")
    now = datetime.now(timezone.utc).isoformat()
    new_ids = existing | {s.id for s in found_skills}
    metadata = {s.id: now for s in found_skills}
    backend.save_id_set(project_id, "promoted", new_ids, metadata)  # type: ignore[arg-type]

    # =========================================================================
    # UNIFICATION: Insert promoted skills into gauntlet_rules table.
    #
    # Skills and gauntlet rules are the same concept — actionable rules that
    # get selected by the bandit and reviewed by the gauntlet. Without this,
    # promoted skills feed the bandit but never enter the gauntlet review loop.
    # =========================================================================
    try:
        gauntlet_rows = []
        for s in found_skills:
            provenance = json.dumps(
                {
                    "source": "skill_promotion",
                    "skill_id": s.id,
                    "category": s.category,
                    "confidence": getattr(s, "confidence_score", None),
                    "confidence_tier": getattr(s, "confidence_tier", None),
                    "frequency": s.frequency,
                    "sources": s.sources[:5] if s.sources else [],
                    "derivation": "learned",
                }
            )
            gauntlet_rows.append(
                {
                    "rule_id": s.id,
                    "persona": "learned",
                    "rule": s.rule,
                    "category": s.category,
                    "context": getattr(s, "context", "") or "",
                    "antipattern": getattr(s, "antipattern", "") or "",
                    "rationale": getattr(s, "rationale", "") or "",
                    "tags": json.dumps(s.tags if s.tags else []),
                    "refs": "[]",
                    "provenance": provenance,
                    "version": 1,
                    "active": 1,
                }
            )
        if gauntlet_rows:
            backend.save_gauntlet_rules_batch(
                gauntlet_rows,
                seed_file_hash=None,
                seed_filename="skill_promotion",
            )
    except Exception:
        logging.getLogger(__name__).debug(
            "Failed to insert promoted skills into gauntlet_rules", exc_info=True
        )

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
            message="No skill IDs provided",
            error="No skill IDs provided",
        )

    backend, project_id = _get_storage(buildlog_dir)

    # Load existing rejections
    existing_ids = backend.load_id_set(project_id, "rejected")

    # Add new rejections
    now = datetime.now(timezone.utc).isoformat()
    newly_rejected: list[str] = []
    metadata: dict[str, str] = {}
    for skill_id in skill_ids:
        if skill_id not in existing_ids:
            existing_ids.add(skill_id)
            metadata[skill_id] = now
            newly_rejected.append(skill_id)

    backend.save_id_set(
        project_id, "rejected", existing_ids, metadata if metadata else None
    )

    return RejectResult(
        rejected_ids=newly_rejected,
        total_rejected=len(existing_ids),
        message=f"Rejected {len(newly_rejected)} skill(s), {len(existing_ids)} total rejected",
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
            message="No buildlog directory found",
            error=f"No buildlog directory found at {buildlog_dir}",
        )

    skill_set = generate_skills(buildlog_dir)

    # Load rejected and promoted IDs
    backend, project_id = _get_storage(buildlog_dir)
    rejected_ids = backend.load_id_set(project_id, "rejected")
    promoted_ids = backend.load_id_set(project_id, "promoted")

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
        message=f"{total_pending} pending | {len(promoted_ids)} promoted | {len(rejected_ids)} rejected",
    )


# -----------------------------------------------------------------------------
# Review Learning Operations
# -----------------------------------------------------------------------------


def _get_learnings_path(buildlog_dir: Path) -> Path:
    """Get path to review_learnings.json file."""
    return buildlog_dir / ".buildlog" / "review_learnings.json"


def _generate_learning_id(category: str, rule: str) -> str:
    """Generate deterministic ID for a learning.

    ALIGNED with skills._generate_skill_id() so that review learnings
    can be merged with distilled skills by ID match in generate_skills().
    """
    from buildlog.skills import _generate_skill_id

    return _generate_skill_id(category, rule)


def migrate_learning_ids(buildlog_dir: Path) -> dict[str, int]:
    """Re-key review_learnings rows whose IDs were generated by the old hash.

    The old ``_generate_learning_id`` included category in the hash input
    and used different prefix mappings (``"dom"`` vs ``"dk"``), producing
    IDs that never matched ``_generate_skill_id``.  This migration
    recomputes each ID using the canonical ``_generate_skill_id`` and
    re-inserts any rows whose key has changed.

    Collision handling: if two old IDs collapse to the same new ID,
    the row with the highest ``reinforcement_count`` wins.

    Returns:
        ``{"migrated": N, "skipped": N, "collisions": N}``
    """
    from buildlog.skills import _generate_skill_id

    backend, project_id = _get_storage(buildlog_dir)
    data = backend.load_learnings(project_id)
    learnings: dict[str, dict] = data.get("learnings", {})

    if not learnings:
        return {"migrated": 0, "skipped": 0, "collisions": 0}

    migrated = 0
    skipped = 0
    collisions = 0
    new_learnings: dict[str, dict] = {}

    for old_id, ld in learnings.items():
        category = ld.get("category", "workflow")
        rule = ld.get("rule", "")
        new_id = _generate_skill_id(category, rule)

        if new_id == old_id:
            # Already correct
            new_learnings[old_id] = ld
            skipped += 1
            continue

        # Check for collision with an already-migrated row
        if new_id in new_learnings:
            existing_count = new_learnings[new_id].get("reinforcement_count", 1)
            incoming_count = ld.get("reinforcement_count", 1)
            if incoming_count > existing_count:
                new_learnings[new_id] = {**ld, "id": new_id}
            collisions += 1
        else:
            new_learnings[new_id] = {**ld, "id": new_id}

        migrated += 1

    if migrated > 0:
        # Delete old rows that were re-keyed, then save the new data.
        # save_learnings only upserts; it won't remove orphaned old-ID rows.
        old_ids_to_delete = set(learnings.keys()) - set(new_learnings.keys())
        if old_ids_to_delete and hasattr(backend, "conn"):
            for old_id in old_ids_to_delete:
                backend.conn.execute(
                    "DELETE FROM review_learnings WHERE project_id = ? AND id = ?",
                    (project_id, old_id),
                )

        data["learnings"] = new_learnings
        backend.save_learnings(project_id, data)

    return {"migrated": migrated, "skipped": skipped, "collisions": collisions}


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


def _learnings_to_seed(
    new_ids: list[str],
    data: dict,
    issues: list[dict],
    source: str | None,
    project_id: str,
) -> dict:
    """Transform new learnings into a qortex-compatible seed dict."""
    import importlib.metadata

    try:
        version = importlib.metadata.version("buildlog")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0-dev"

    rules = []
    for lid in new_ids:
        learning = data["learnings"].get(lid)
        if learning is None:
            continue
        rules.append(
            {
                "rule": learning["rule"],
                "category": learning["category"],
                "provenance": {
                    "id": f"bl:{lid}",
                    "domain": "experiential",
                    "derivation": "explicit",
                    "confidence": min(
                        1.0, learning.get("reinforcement_count", 1) * 0.3 + 0.4
                    ),
                },
            }
        )

    return {
        "persona": f"buildlog_{project_id}",
        "version": 1,
        "rules": rules,
        "metadata": {
            "source": "buildlog",
            "source_version": version,
            "projected_at": datetime.now(timezone.utc).isoformat(),
            "rule_count": len(rules),
        },
    }


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

    backend, project_id = _get_storage(buildlog_dir)

    # Lazy migration: re-key old-style learning IDs on first call after deploy
    try:
        migrate_learning_ids(buildlog_dir)
    except Exception:
        pass  # Best-effort, never break learn_from_review

    data = backend.load_learnings(project_id)

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
    backend.save_learnings(project_id, data)

    # =========================================================================
    # AMBIENT EMISSION: Learned rules as seed for downstream consumers
    # =========================================================================
    if new_ids:
        try:
            from buildlog.emissions import emit_artifact

            seed = _learnings_to_seed(new_ids, data, issues, source, project_id)
            emit_artifact(
                artifact=seed,
                artifact_type="learned_rules",
                project_id=project_id,
            )
        except Exception:
            pass  # Fire-and-forget

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
    session_id: str | None = None,
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

    Appends to reward_events table for analysis AND updates the bandit.

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
        session_id: Session to associate with. If None, auto-detects active session.

    Returns:
        LogRewardResult with confirmation.
    """
    now = datetime.now(timezone.utc)
    reward_id = _generate_reward_id(outcome, now)
    reward_value = _compute_reward_value(outcome, revision_distance)

    backend, project_id = _get_storage(buildlog_dir)

    # Try to get rules and context from active session if not provided
    session_data = backend.load_active_session(project_id)
    if session_data is not None:
        if session_id is None:
            session_id = session_data.get("id")
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
        session_id=session_id,
    )

    # Append reward event
    backend.append_event(project_id, "rewards", event.to_dict())  # type: ignore[arg-type]

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
        bandit = get_learning_backend(buildlog_dir)

        bandit.batch_update(
            rule_ids=rules_active,
            reward=reward_value,
            context=error_class or "general",
        )

    # Count total events
    total_events = backend.count_events(project_id, "rewards")

    # =========================================================================
    # EMISSION: Fire-and-forget reward signal for downstream consumers
    # =========================================================================
    try:
        from buildlog.emissions import emit_artifact

        gauntlet_map = _build_skill_to_gauntlet_map(buildlog_dir)
        emit_artifact(
            artifact=_reward_to_emission(event, project_id, gauntlet_map=gauntlet_map),
            artifact_type="reward_signal",
            project_id=project_id,
        )
    except Exception:
        logging.getLogger(__name__).debug("Reward emission failed", exc_info=True)

    rules_count = len(rules_active) if rules_active else 0
    message = f"Logged {outcome} (reward={reward_value:.2f})"
    if rules_count > 0:
        message += f" | Updated bandit: {rules_count} rules"
    if session_id:
        message += f" | Session: {session_id}"

    return LogRewardResult(
        reward_id=reward_id,
        reward_value=reward_value,
        total_events=total_events,
        message=message,
    )


# =============================================================================
# Skill → Gauntlet Rule ID mapping for emission edge enrichment
# =============================================================================


def _build_skill_to_gauntlet_map(buildlog_dir: Path) -> dict[str, str]:
    """Build mapping from promoted skill IDs to gauntlet rule IDs.

    Both IDs are deterministic content hashes of rule text:
    - Skill ID: ``{prefix}-{sha256(rule.lower())[:10]}``
    - Gauntlet rule ID: ``{persona}:{sha256(rule)[:8]}``

    Returns dict mapping ``skill_id -> gauntlet_rule:{rule_id}``.
    """
    import sqlite3

    from buildlog.skills import _generate_skill_id

    db_path = buildlog_dir / ".buildlog" / "buildlog.db"
    if not db_path.exists():
        return {}

    mapping: dict[str, str] = {}
    try:
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        cursor = db.execute(
            "SELECT rule_id, rule, category, active FROM gauntlet_rules WHERE active = 1"
        )
        for row in cursor:
            rule_id = row["rule_id"]
            rule_text = row["rule"]
            category = row["category"] or "general"

            # Compute what the skill ID would be for this rule
            skill_id = _generate_skill_id(category, rule_text)
            mapping[skill_id] = f"gauntlet_rule:{rule_id}"
        db.close()
    except Exception:
        logging.getLogger(__name__).debug(
            "Failed to build skill→gauntlet map", exc_info=True
        )
    return mapping


def _resolve_rule_target(rule_id: str, gauntlet_map: dict[str, str]) -> str:
    """Resolve a rule ID to its gauntlet_rule:{id} form if possible."""
    if not gauntlet_map:
        return rule_id
    return gauntlet_map.get(rule_id, rule_id)


def _reward_to_emission(
    event: RewardEvent,
    project_id: str,
    gauntlet_map: dict[str, str] | None = None,
) -> dict:
    """Build a reward signal emission for downstream consumers."""
    source_id = f"buildlog:{project_id}"
    reward_node_id = f"reward:{event.id}"
    gmap = gauntlet_map or {}

    edges: list[dict] = []
    for rule_id in event.rules_active:
        target = _resolve_rule_target(rule_id, gmap)
        # SUPPORTS if accepted (rule helped), CHALLENGES if rejected (rule failed)
        relation = "supports" if event.outcome == "accepted" else "challenges"
        if event.outcome == "revision":
            # Partial: supports if reward > 0.5, challenges otherwise
            relation = "supports" if event.reward_value > 0.5 else "challenges"
        edges.append(
            {
                "source_id": reward_node_id,
                "target_id": target,
                "relation_type": relation,
                "properties": {
                    "outcome": event.outcome,
                    "reward_value": event.reward_value,
                },
                "confidence": abs(event.reward_value - 0.5) * 2,  # 0-1 scale
            }
        )

    # Link reward to session if available
    if event.session_id:
        edges.append(
            {
                "source_id": reward_node_id,
                "target_id": f"session:{event.session_id}",
                "relation_type": "part_of",
                "properties": {"type": "reward_in_session"},
                "confidence": 1.0,
            }
        )

    props: dict = {
        "outcome": event.outcome,
        "reward_value": event.reward_value,
        "timestamp": event.timestamp.isoformat(),
    }
    if event.error_class:
        props["error_class"] = event.error_class
    if event.session_id:
        props["session_id"] = event.session_id

    return {
        "source_id": source_id,
        "domain": "experiential",
        "concepts": [
            {
                "name": reward_node_id,
                "domain": "experiential",
                "properties": props,
                "source_id": source_id,
            }
        ],
        "edges": edges,
        "rules": [],
        "metadata": {
            "source": "buildlog",
            "emitted_at": event.timestamp.isoformat(),
            "project_id": project_id,
            "reward_id": event.id,
            "session_id": event.session_id,
        },
    }


def _session_to_emission(
    session: Session,
    session_mistakes: list[Mistake],
    duration: float,
    repeated: int,
    auto_outcome: str,
    project_id: str,
    gauntlet_map: dict[str, str] | None = None,
) -> dict:
    """Build a session summary emission for downstream consumers."""
    source_id = f"buildlog:{project_id}"
    session_node_id = f"session:{session.id}"
    gmap = gauntlet_map or {}

    edges: list[dict] = []

    # Session → rule (used) edges
    for rule_id in session.selected_rules:
        target = _resolve_rule_target(rule_id, gmap)
        edges.append(
            {
                "source_id": session_node_id,
                "target_id": target,
                "relation_type": "uses",
                "properties": {"type": "rule_in_session"},
                "confidence": 1.0,
            }
        )

    # Session → mistake (contains) edges
    for mistake in session_mistakes:
        edges.append(
            {
                "source_id": session_node_id,
                "target_id": f"mistake:{mistake.id}",
                "relation_type": "contains",
                "properties": {
                    "error_class": mistake.error_class,
                    "was_repeat": mistake.was_repeat,
                },
                "confidence": 1.0,
            }
        )

    props: dict = {
        "started_at": session.started_at.isoformat(),
        "duration_minutes": round(duration, 1),
        "mistakes_logged": len(session_mistakes),
        "repeated_mistakes": repeated,
        "outcome": auto_outcome,
        "rules_count": len(session.selected_rules),
    }
    if session.ended_at:
        props["ended_at"] = session.ended_at.isoformat()
    if session.error_class:
        props["error_class"] = session.error_class

    return {
        "source_id": source_id,
        "domain": "experiential",
        "concepts": [
            {
                "name": session_node_id,
                "domain": "experiential",
                "properties": props,
                "source_id": source_id,
            }
        ],
        "edges": edges,
        "rules": [],
        "metadata": {
            "source": "buildlog",
            "emitted_at": (session.ended_at or session.started_at).isoformat(),
            "project_id": project_id,
            "session_id": session.id,
        },
    }


def get_rewards(
    buildlog_dir: Path,
    limit: int | None = None,
    session_id: str | None = None,
) -> RewardSummary:
    """Get reward events with summary statistics.

    Args:
        buildlog_dir: Path to buildlog directory.
        limit: Maximum number of events to return (most recent first).
        session_id: If provided, only return events for this session.

    Returns:
        RewardSummary with events and statistics.
    """
    backend, project_id = _get_storage(buildlog_dir)

    # Load all events via backend
    raw_events = backend.load_events(project_id, "rewards")

    # Filter by session_id if requested
    if session_id is not None:
        raw_events = [e for e in raw_events if e.get("session_id") == session_id]

    if not raw_events:
        return RewardSummary(
            total_events=0,
            accepted=0,
            revisions=0,
            rejected=0,
            mean_reward=0.0,
            events=[],
        )

    # Parse into dataclasses
    events: list[RewardEvent] = []
    for data in raw_events:
        try:
            events.append(RewardEvent.from_dict(data))  # type: ignore[arg-type]
        except (KeyError, ValueError):
            continue

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
    related_concepts: list[str] | None
    relation_to_prior: dict | None  # {"id": str, "type": str}
    resolution_action: str | None
    context: str | None
    severity: str | None


@dataclass
class Mistake:
    """A logged mistake during a session.

    Tracks mistakes to measure repeated-mistake rate. Carries graph-ready
    metadata for emission to downstream consumers (e.g. qortex).

    Attributes:
        id: Unique identifier for this mistake.
        session_id: Session in which this mistake occurred.
        timestamp: When the mistake was logged.
        error_class: Category of error (e.g., "missing_test").
        description: Description of the mistake.
        semantic_hash: Hash of description for similarity matching.
        was_repeat: Whether this was a repeat of a prior mistake.
        corrected_by_rule: Rule ID that should have prevented this, if any.
        related_concepts: Concept names involved in this mistake.
        relation_to_prior: Link to a prior mistake (id + type).
        resolution_action: What fixed the mistake.
        context: What the agent was doing when it made the mistake.
        severity: low|medium|high|critical.
    """

    id: str
    session_id: str
    timestamp: datetime
    error_class: str
    description: str
    semantic_hash: str
    was_repeat: bool = False
    corrected_by_rule: str | None = None
    related_concepts: list[str] | None = None
    relation_to_prior: dict | None = None
    resolution_action: str | None = None
    context: str | None = None
    severity: str | None = None

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
        if self.related_concepts is not None:
            result["related_concepts"] = self.related_concepts
        if self.relation_to_prior is not None:
            result["relation_to_prior"] = self.relation_to_prior
        if self.resolution_action is not None:
            result["resolution_action"] = self.resolution_action
        if self.context is not None:
            result["context"] = self.context
        if self.severity is not None:
            result["severity"] = self.severity
        return result

    @classmethod
    def from_dict(cls, data: MistakeDict) -> "Mistake":
        """Reconstruct from serialized dictionary."""
        timestamp = datetime.fromisoformat(data["timestamp"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Deserialize JSON strings from SQLite if needed
        related_concepts = data.get("related_concepts")
        if isinstance(related_concepts, str):
            related_concepts = json.loads(related_concepts)

        relation_to_prior = data.get("relation_to_prior")
        if isinstance(relation_to_prior, str):
            relation_to_prior = json.loads(relation_to_prior)

        return cls(
            id=data["id"],
            session_id=data["session_id"],
            timestamp=timestamp,
            error_class=data["error_class"],
            description=data["description"],
            semantic_hash=data["semantic_hash"],
            was_repeat=data.get("was_repeat", False),
            corrected_by_rule=data.get("corrected_by_rule"),
            related_concepts=related_concepts,
            relation_to_prior=relation_to_prior,
            resolution_action=data.get("resolution_action"),
            context=data.get("context"),
            severity=data.get("severity"),
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
    entry_path: str | None = None
    report_appended: bool = False
    distill_count: int = 0
    skills_count: int = 0
    emissions_consumed: int = 0
    edges_stored: int = 0
    pending_emissions: int = 0


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
    """Get list of current rule IDs — promoted skills + active gauntlet rules.

    Returns the UNIFIED pool of rules for bandit selection:
    - Promoted skill IDs (from skill_decisions)
    - Active gauntlet rule IDs (from gauntlet_rules WHERE active = 1)

    This ensures the bandit selects from ALL rules, whether they came
    from journal extraction (skills) or YAML seed import (gauntlet rules).
    """
    backend, project_id = _get_storage(buildlog_dir)
    promoted = backend.load_id_set(project_id, "promoted")

    # Also include active gauntlet rules
    gauntlet_ids: set[str] = set()
    try:
        rows = backend.load_gauntlet_rules(active_only=True)
        gauntlet_ids = {r["rule_id"] for r in rows}
    except Exception:
        pass

    return sorted(promoted | gauntlet_ids)


def _get_seed_rule_ids(buildlog_dir: Path) -> tuple[set[str], dict[str, float]]:
    """Get IDs of rules that come from seed personas plus confidence map.

    Seed rules get boosted priors (Beta(3,1)) in the bandit because they
    represent curated, expert knowledge.

    Two sources are checked:
    1. Skills with non-empty ``persona_tags`` (from journal extraction)
    2. Gauntlet rules with ``persona != 'learned'`` (YAML seed imports)

    Source 2 is critical because YAML seeds go directly to gauntlet_rules
    and never become Skills — without it, all 102 seed rules lose their
    boosted priors.

    Returns:
        Tuple of (seed_ids, confidence_map) where confidence_map maps
        rule IDs to provenance confidence values for weighted boosting.
    """
    seed_ids: set[str] = set()
    confidence_map: dict[str, float] = {}

    # Source 1: Skills with persona_tags (existing logic)
    try:
        skill_set = generate_skills(buildlog_dir)
        for category_skills in skill_set.skills.values():
            for skill in category_skills:
                if skill.persona_tags:  # Non-empty means it's from a seed
                    seed_ids.add(skill.id)
                    # Extract confidence from provenance if available
                    if (
                        skill.provenance is not None
                        and "confidence" in skill.provenance
                    ):
                        try:
                            confidence_map[skill.id] = float(
                                skill.provenance["confidence"]
                            )
                        except (ValueError, TypeError):
                            pass
    except Exception:
        pass  # Still check gauntlet_rules below

    # Source 2: Gauntlet rules with persona != 'learned' (YAML seed imports)
    try:
        backend, _project_id = _get_storage(buildlog_dir)
        rows = backend.load_gauntlet_rules(active_only=True)
        for row in rows:
            persona = row.get("persona", "")
            if persona and persona != "learned":
                rule_id = row["rule_id"]
                seed_ids.add(rule_id)
                # Parse confidence from provenance JSON
                prov_str = row.get("provenance")
                if prov_str:
                    try:
                        prov = (
                            json.loads(prov_str)
                            if isinstance(prov_str, str)
                            else prov_str
                        )
                        if isinstance(prov, dict) and "confidence" in prov:
                            confidence_map.setdefault(
                                rule_id, float(prov["confidence"])
                            )
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
    except Exception:
        pass  # Best-effort

    return seed_ids, confidence_map


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
        bandit = get_learning_backend(buildlog_dir)

        # Identify seed rules (those with persona_tags from gauntlet)
        # Seeds get boosted priors - we believe curated rules are good
        seed_rule_ids, seed_confidence_map = _get_seed_rule_ids(buildlog_dir)

        # SELECT: Sample from Beta distributions, pick top-k
        selected_rules = bandit.select(
            candidates=current_rules,
            context=error_class or "general",
            k=min(select_k, len(current_rules)),
            seed_rule_ids=seed_rule_ids,
            seed_confidence_map=seed_confidence_map or None,
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
    backend, project_id = _get_storage(buildlog_dir)
    backend.save_active_session(project_id, session.to_dict())  # type: ignore[arg-type]

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


# -----------------------------------------------------------------------------
# Improvements Report Helpers (I/O shell + pure computation)
# -----------------------------------------------------------------------------


def _load_improvements_inputs(
    buildlog_dir: Path,
    backend: object,
    project_id: str,
    session: "Session",
) -> dict:
    """I/O shell: load all data needed for the improvements report.

    Returns a dict of raw data for ``_compute_improvements_data``.
    """
    # Learning backend stats
    stats: dict[str, dict] = {}
    try:
        lb = get_learning_backend(buildlog_dir)
        stats = lb.get_stats(session.error_class)
    except Exception:
        pass

    # Prior session: load all ended sessions, find the one before current
    raw_sessions = backend.load_events(project_id, "sessions")  # type: ignore[attr-defined]
    prior_session = None
    prior_mistakes: list["Mistake"] = []
    prior_reward_summary = None

    ended_sessions = []
    for s in raw_sessions:
        try:
            sess = Session.from_dict(s)  # type: ignore[arg-type]
            if sess.ended_at is not None and sess.id != session.id:
                ended_sessions.append(sess)
        except (KeyError, ValueError):
            continue

    if ended_sessions:
        ended_sessions.sort(
            key=lambda s: s.ended_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        prior_session = ended_sessions[0]

        # Load prior session mistakes
        raw_mistakes = backend.load_events(project_id, "mistakes")  # type: ignore[attr-defined]
        all_mistakes = [Mistake.from_dict(m) for m in raw_mistakes]  # type: ignore[arg-type]
        prior_mistakes = [m for m in all_mistakes if m.session_id == prior_session.id]

        # Load prior session rewards
        prior_reward_summary = get_rewards(buildlog_dir, session_id=prior_session.id)

    # Current session rewards
    current_reward_summary = get_rewards(buildlog_dir, session_id=session.id)

    return {
        "stats": stats,
        "prior_session": prior_session,
        "prior_mistakes": prior_mistakes,
        "prior_reward_summary": prior_reward_summary,
        "current_reward_summary": current_reward_summary,
    }


def _compute_improvements_data(
    session: "Session",
    duration: float,
    session_mistakes: list["Mistake"],
    stats: dict[str, dict],
    prior_session: "Session | None",
    prior_mistakes: list["Mistake"],
    prior_reward_summary: "RewardSummary | None",
    current_reward_summary: "RewardSummary",
) -> "ImprovementsReportData":
    """Pure computation: assemble ImprovementsReportData from loaded inputs."""
    from buildlog.core.report import ImprovementsReportData, RuleStatus, classify_rule

    # Classify rules
    rule_statuses = []
    for rule_id, rule_stats in stats.items():
        mean = rule_stats.get("mean", 0.5)
        observations = int(rule_stats.get("total_observations", 0))
        status = classify_rule(mean, observations)
        rule_statuses.append(
            RuleStatus(
                rule_id=rule_id,
                mean=mean,
                observations=observations,
                status=status,
            )
        )

    # Mean reward: None if no events
    mean_reward: float | None = None
    if current_reward_summary.total_events > 0:
        mean_reward = current_reward_summary.mean_reward

    # Prior session metrics
    prior_mistakes_count: int | None = None
    prior_repeats: int | None = None
    prior_rules_start: int | None = None
    prior_rules_end: int | None = None
    prior_mean_reward: float | None = None

    if prior_session is not None:
        prior_mistakes_count = len(prior_mistakes)
        prior_repeats = sum(1 for m in prior_mistakes if m.was_repeat)
        prior_rules_start = len(prior_session.rules_at_start)
        prior_rules_end = len(prior_session.rules_at_end)
        if prior_reward_summary and prior_reward_summary.total_events > 0:
            prior_mean_reward = prior_reward_summary.mean_reward

    repeated = sum(1 for m in session_mistakes if m.was_repeat)

    return ImprovementsReportData(
        session_id=session.id,
        duration_minutes=round(duration, 1),
        error_class=session.error_class,
        mistakes_caught=len(session_mistakes),
        repeated_mistakes=repeated,
        rules_at_start=len(session.rules_at_start),
        rules_at_end=len(session.rules_at_end),
        mean_reward=mean_reward,
        rule_statuses=rule_statuses,
        prior_mistakes=prior_mistakes_count,
        prior_repeats=prior_repeats,
        prior_rules_start=prior_rules_start,
        prior_rules_end=prior_rules_end,
        prior_mean_reward=prior_mean_reward,
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
    backend, project_id = _get_storage(buildlog_dir)

    session_data = backend.load_active_session(project_id)
    if session_data is None:
        raise ValueError("No active session to end")

    # Load active session
    session = Session.from_dict(session_data)  # type: ignore[arg-type]

    # Update session with end info
    now = datetime.now(timezone.utc)
    session.ended_at = now
    session.rules_at_end = _get_current_rules(buildlog_dir)
    if entry_file:
        session.entry_file = entry_file
    if notes:
        session.notes = f"{session.notes or ''}\n{notes}".strip()

    # Append to sessions log
    backend.append_event(project_id, "sessions", session.to_dict())  # type: ignore[arg-type]

    # Remove active session marker
    backend.delete_active_session(project_id)

    # Calculate session metrics
    raw_mistakes = backend.load_events(project_id, "mistakes")
    all_mistakes = [Mistake.from_dict(m) for m in raw_mistakes]  # type: ignore[arg-type]
    session_mistakes = [m for m in all_mistakes if m.session_id == session.id]
    repeated = sum(1 for m in session_mistakes if m.was_repeat)

    duration = (session.ended_at - session.started_at).total_seconds() / 60

    # --- Improvements report (best-effort) ---
    entry_path_str: str | None = None
    report_appended = False
    try:
        from buildlog.core.report import (
            inject_improvements_into_entry,
            render_improvements_narrative,
            render_improvements_table,
            should_emit_report,
        )

        inputs = _load_improvements_inputs(buildlog_dir, backend, project_id, session)
        data = _compute_improvements_data(
            session,
            duration,
            session_mistakes,
            stats=inputs["stats"],
            prior_session=inputs["prior_session"],
            prior_mistakes=inputs["prior_mistakes"],
            prior_reward_summary=inputs["prior_reward_summary"],
            current_reward_summary=inputs["current_reward_summary"],
        )
        if should_emit_report(data):
            narrative = render_improvements_narrative(data)
            table = render_improvements_table(data)
            report = narrative + "\n\n" + table

            # Resolve entry path
            today_str = date.today().isoformat()
            entry_path = entry_file
            if entry_path and not Path(entry_path).is_absolute():
                entry_path = str(buildlog_dir / entry_path)
            resolved = _resolve_entry_path_core(
                buildlog_dir, today_str, None, entry_path
            )
            if resolved.exists():
                content = resolved.read_text()
                content = inject_improvements_into_entry(content, report)
                resolved.write_text(content)
                entry_path_str = str(resolved)
                report_appended = True
    except Exception:
        pass  # Never break end_session()

    # --- Auto-reward: close the feedback loop automatically ---
    # Without this, the bandit never learns because manual log_reward()
    # calls are forgotten ~100% of the time.  Outcome logic:
    #   - 0 repeated mistakes -> "accepted" (rules worked)
    #   - any repeated mistakes -> "revision" (rules partially failed)
    #
    # IMPORTANT: Pass rules_active explicitly. The active session was
    # already deleted above (line ~2032), so log_reward() can't look
    # it up. Without explicit rules, the bandit never updates.
    auto_outcome = "accepted" if repeated == 0 else "revision"
    try:
        log_reward(
            buildlog_dir=buildlog_dir,
            outcome=auto_outcome,  # type: ignore[arg-type]
            rules_active=session.selected_rules,
            error_class=session.error_class,
            session_id=session.id,
            source="auto:end_session",
            notes=f"auto: {len(session_mistakes)} mistakes, {repeated} repeats",
        )
    except Exception:
        pass  # Never break end_session()

    # --- Auto-distill: extract insights from entries ---
    distill_count = 0
    try:
        from buildlog.distill import distill_all

        distill_result = distill_all(buildlog_dir)
        distill_count = distill_result.statistics.get("total_patterns", 0)
    except Exception:
        pass  # Never break end_session()

    # --- Auto-skills: extract actionable skills from insights ---
    skills_count = 0
    try:
        skill_set = generate_skills(buildlog_dir)
        skills_count = skill_set.total_skills
    except Exception:
        pass  # Never break end_session()

    # --- Session emission: fire-and-forget session summary ---
    try:
        from buildlog.emissions import emit_artifact

        gauntlet_map = _build_skill_to_gauntlet_map(buildlog_dir)
        emit_artifact(
            artifact=_session_to_emission(
                session,
                session_mistakes,
                duration,
                repeated,
                auto_outcome,
                project_id,
                gauntlet_map=gauntlet_map,
            ),
            artifact_type="session_summary",
            project_id=project_id,
        )
    except Exception:
        pass  # Never break end_session()

    # --- Consume pending emissions: process backlog ---
    emissions_consumed = 0
    edges_stored = 0
    pending_emissions = 0
    try:
        from buildlog.emissions.consumer import consume_pending_emissions

        consumption = consume_pending_emissions(backend=backend)
        emissions_consumed = consumption.consumed
        edges_stored = consumption.edges_stored
        try:
            from buildlog.emissions import list_pending

            pending_emissions = len(list_pending())
        except Exception:
            pass
    except Exception:
        pass  # Never break end_session()

    return EndSessionResult(
        session_id=session.id,
        duration_minutes=round(duration, 1),
        mistakes_logged=len(session_mistakes),
        repeated_mistakes=repeated,
        rules_at_start=len(session.rules_at_start),
        rules_at_end=len(session.rules_at_end),
        message=f"Ended session {session.id} ({duration:.1f}min, {len(session_mistakes)} mistakes, {repeated} repeats)",
        entry_path=entry_path_str,
        report_appended=report_appended,
        distill_count=distill_count,
        skills_count=skills_count,
        emissions_consumed=emissions_consumed,
        edges_stored=edges_stored,
        pending_emissions=pending_emissions,
    )


def log_mistake(
    buildlog_dir: Path,
    error_class: str,
    description: str,
    corrected_by_rule: str | None = None,
    related_concepts: list[str] | None = None,
    relation_to_prior: dict | None = None,
    resolution_action: str | None = None,
    context: str | None = None,
    severity: str | None = None,
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
        related_concepts: Concept names involved in the mistake.
        relation_to_prior: Link to prior mistake {"id": str, "type": str}.
        resolution_action: What fixed the mistake.
        context: What the agent was doing when the mistake occurred.
        severity: low|medium|high|critical.

    Returns:
        LogMistakeResult indicating if this was a repeat.

    Raises:
        ValueError: If severity or relation_to_prior.type is invalid.
    """
    # -- Input validation --
    _VALID_SEVERITIES = {"low", "medium", "high", "critical"}
    if severity is not None and severity not in _VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. Must be one of: {', '.join(sorted(_VALID_SEVERITIES))}"
        )

    _VALID_CHAIN_TYPES = {
        "escalation",
        "same_pattern",
        "regression",
        "caused_by",
        "part_of",
    }
    if relation_to_prior is not None:
        if not isinstance(relation_to_prior, dict):
            raise ValueError(
                "relation_to_prior must be a dict with 'id' and 'type' keys"
            )
        if "id" not in relation_to_prior or "type" not in relation_to_prior:
            raise ValueError("relation_to_prior must have 'id' and 'type' keys")
        chain_type = relation_to_prior.get("type")
        if chain_type not in _VALID_CHAIN_TYPES:
            raise ValueError(
                f"Invalid relation_to_prior type '{chain_type}'. "
                f"Must be one of: {', '.join(sorted(_VALID_CHAIN_TYPES))}"
            )

    backend, project_id = _get_storage(buildlog_dir)

    session_data = backend.load_active_session(project_id)
    if session_data is None:
        raise ValueError(
            "No active session - start one with 'buildlog experiment start'"
        )

    # Get current session
    session_id = session_data["id"]

    now = datetime.now(timezone.utc)
    mistake_id = _generate_mistake_id(error_class, now)

    # Check for similar prior mistakes
    raw_mistakes = backend.load_events(project_id, "mistakes")
    all_mistakes = [Mistake.from_dict(m) for m in raw_mistakes]  # type: ignore[arg-type]
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
        related_concepts=related_concepts,
        relation_to_prior=relation_to_prior,
        resolution_action=resolution_action,
        context=context,
        severity=severity,
    )

    # Append to mistakes log
    backend.append_event(project_id, "mistakes", mistake.to_dict())  # type: ignore[arg-type]

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
        bandit = get_learning_backend(buildlog_dir)

        # Use session's error_class as context, not the mistake's
        # (they should match, but session context is authoritative)
        bandit_context = session_data.get("error_class") or "general"

        bandit.batch_update(
            rule_ids=selected_rules,
            reward=0.0,  # Failure: rules didn't prevent mistake
            context=bandit_context,
        )

    # =========================================================================
    # AMBIENT EMISSION: Fire-and-forget artifact for downstream consumers
    # =========================================================================
    try:
        from buildlog.emissions import emit_artifact
        from buildlog.emissions.mappers import DEFAULT_REGISTRY, _mistake_to_manifest

        gauntlet_map = _build_skill_to_gauntlet_map(buildlog_dir)
        manifest = _mistake_to_manifest(
            mistake=mistake,
            session_data=session_data,
            selected_rules=selected_rules,
            project_id=project_id,
            registry=DEFAULT_REGISTRY,
            gauntlet_map=gauntlet_map,
        )
        emit_artifact(
            artifact=manifest,
            artifact_type="mistake_manifest",
            project_id=project_id,
        )
    except Exception:
        pass  # Fire-and-forget: emission failure must never break primary op

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
    backend, project_id = _get_storage(buildlog_dir)
    sessions = [
        Session.from_dict(s) for s in backend.load_events(project_id, "sessions")  # type: ignore[arg-type]
    ]
    mistakes = [
        Mistake.from_dict(m) for m in backend.load_events(project_id, "mistakes")  # type: ignore[arg-type]
    ]

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
    backend, project_id = _get_storage(buildlog_dir)
    sessions = [
        Session.from_dict(s) for s in backend.load_events(project_id, "sessions")  # type: ignore[arg-type]
    ]
    mistakes = [
        Mistake.from_dict(m) for m in backend.load_events(project_id, "mistakes")  # type: ignore[arg-type]
    ]

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
    bandit = get_learning_backend(buildlog_dir)

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

    # Health: count arms with narrow confidence intervals (converging)
    converging = 0
    for ctx_rules in contexts.values():
        for arm in ctx_rules:
            ci = arm.get("confidence_interval")
            if (
                isinstance(ci, (list, tuple))
                and len(ci) >= 2
                and (ci[1] - ci[0]) < _CONVERGENCE_CI_WIDTH
            ):
                converging += 1

    # Human-readable health summary
    if total_observations == 0:
        health = "no observations yet"
    else:
        parts = [f"{total_observations} obs across {total_arms} arms"]
        if converging:
            parts.append(f"{converging} converging")
        health = " | ".join(parts)

    return {
        "summary": {
            "total_contexts": len(contexts),
            "total_arms": total_arms,
            "total_observations": total_observations,
            "backend": bandit.backend_name,
        },
        "message": health,
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
        rules_credited: Validated rule IDs cited across all issues
        citation_stats: Validation stats (total/valid/hallucinated citations)
    """

    action: Literal["fix_criticals", "checkpoint_majors", "checkpoint_minors", "clean"]
    criticals: list[dict]
    majors: list[dict]
    minors: list[dict]
    iteration: int
    learnings_persisted: int
    message: str
    rules_credited: list[str] = field(default_factory=list)
    citation_stats: dict = field(default_factory=dict)


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
    valid_rule_ids: set[str] | None = None,
) -> GauntletLoopResult:
    """Process gauntlet issues and determine next action.

    Categorizes issues by severity, persists learnings, validates
    rule citations, and returns the appropriate next action for
    the gauntlet loop.

    Args:
        buildlog_dir: Path to buildlog directory.
        issues: List of issues from the gauntlet review.
        iteration: Current iteration number (for tracking).
        source: Optional source identifier for learnings.
        valid_rule_ids: Set of valid rule IDs for citation validation.
            When provided, hallucinated IDs are stripped from issues
            and logged as mistakes.

    Returns:
        GauntletLoopResult with categorized issues and next action.
    """
    # --- Citation validation ---
    credited_rules: set[str] = set()
    citation_stats: dict = {
        "total_citations": 0,
        "valid_citations": 0,
        "hallucinated_citations": 0,
        "issues_with_citations": 0,
        "issues_without_citations": 0,
    }

    for issue in issues:
        consulted = issue.get("rules_consulted")
        if not consulted or not isinstance(consulted, list):
            citation_stats["issues_without_citations"] += 1
            continue

        citation_stats["issues_with_citations"] += 1
        citation_stats["total_citations"] += len(consulted)

        if valid_rule_ids is not None:
            valid_ids = [rid for rid in consulted if rid in valid_rule_ids]
            hallucinated_ids = [rid for rid in consulted if rid not in valid_rule_ids]

            citation_stats["valid_citations"] += len(valid_ids)
            citation_stats["hallucinated_citations"] += len(hallucinated_ids)

            # Strip hallucinated IDs from the issue
            issue["rules_consulted"] = valid_ids
            if "rule_reasoning" in issue and isinstance(issue["rule_reasoning"], dict):
                for hid in hallucinated_ids:
                    issue["rule_reasoning"].pop(hid, None)

            # Log hallucinated citations as mistakes
            if hallucinated_ids:
                try:
                    log_mistake(
                        buildlog_dir,
                        error_class="citation_hallucination",
                        description=(
                            f"Hallucinated rule IDs in gauntlet review: "
                            f"{', '.join(hallucinated_ids)}"
                        ),
                        severity="minor",
                    )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "Failed to log citation hallucination", exc_info=True
                    )

            credited_rules.update(valid_ids)
        else:
            # No validation — trust all citations
            citation_stats["valid_citations"] += len(consulted)
            credited_rules.update(consulted)

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

    # --- Bandit update with per-rule credit (Touch 3) ---
    # Context=None → bandit default ("general"). Selection also uses None,
    # so credits and selections always hit the same arm partition.
    if credited_rules:
        try:
            bandit = get_learning_backend(buildlog_dir)
            for rule_id in credited_rules:
                bandit.update(rule_id, reward=1.0, context=None)
        except Exception:
            logging.getLogger(__name__).debug(
                "Bandit credit update failed", exc_info=True
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
        rules_credited=sorted(credited_rules),
        citation_stats=citation_stats,
    )


def _sanitize_for_gh(text: str, max_len: int = 256) -> str:
    """Sanitize text for GitHub issue fields.

    Defense-in-depth: we use list args (not shell=True) for subprocess,
    but sanitize anyway to prevent injection via gh's argument parsing.
    """
    sanitized = text.replace("\n", " ").replace("\r", " ")
    if len(sanitized) > max_len:
        sanitized = sanitized[: max_len - 3] + "..."
    return sanitized.strip()


def gauntlet_accept_risk(
    remaining_issues: list[dict],
    create_github_issues: bool = False,
    repo: str | None = None,
    cwd: str | None = None,
) -> GauntletAcceptRiskResult:
    """Accept risk for remaining issues, optionally creating GitHub issues.

    Args:
        remaining_issues: Issues being accepted as risk.
        create_github_issues: Whether to create GitHub issues for tracking.
        repo: Repository for GitHub issues (uses current repo if None).
        cwd: Working directory for subprocess calls.

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

            run_kwargs: dict = {"cwd": cwd} if cwd else {}
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                    **run_kwargs,
                )
                # gh issue create outputs the URL
                url = result.stdout.strip()
                if url:
                    github_urls.append(url)
            except subprocess.CalledProcessError as e:
                # Don't fail entirely, just note the error
                error = f"Failed to create some GitHub issues: {e.stderr}"
            except subprocess.TimeoutExpired:
                error = "GitHub issue creation timed out (30s limit)."
                break
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


# =============================================================================
# Entry & Overview Operations
# =============================================================================


@dataclass
class GauntletRulesResult:
    """Result of loading gauntlet reviewer rules."""

    formatted: str
    format: str
    total_rules: int
    personas: list[str]
    message: str = ""
    error: str | None = None


@dataclass
class OverviewResult:
    """Result of getting buildlog overview."""

    entries: int
    skills: dict
    active_session: str | None
    render_targets: list[str]
    workflow_ok: bool = True
    workflow_issues: list[str] | None = None
    message: str = ""
    pending_emissions: int = 0
    total_emission_edges: int = 0


@dataclass
class CreateEntryResult:
    """Result of creating a new entry."""

    entry_path: str
    entry_name: str
    date_str: str
    template_used: str
    message: str
    error: str | None = None


@dataclass
class ListEntriesResult:
    """Result of listing entries."""

    entries: list[dict]
    count: int
    message: str = ""


def get_gauntlet_rules(
    persona: str | None = None,
    format: str = "json",
    compact: bool = True,
) -> GauntletRulesResult:
    """Load gauntlet reviewer rules.

    Args:
        persona: Filter to a specific persona, or None for all.
        format: Output format (json, yaml, markdown).
        compact: If True (default), return only rule_id, rule, and
            category per rule. Set False for full fields (context,
            antipattern, rationale, tags).

    Returns:
        GauntletRulesResult with formatted rules.
    """
    from buildlog.seeds import load_rules
    from buildlog.storage import get_backend

    # Resolve backend for DB-backed rules
    try:
        backend, _ = get_backend()
    except Exception:
        backend = None

    seeds = load_rules(backend=backend, persona=persona)
    if not seeds:
        # Distinguish "unknown persona" from "no rules at all"
        if persona is not None:
            all_seeds = load_rules(backend=backend)
            if all_seeds:
                available = ", ".join(all_seeds.keys())
                return GauntletRulesResult(
                    formatted="",
                    format=format,
                    total_rules=0,
                    personas=[],
                    message=f"Unknown persona: {persona}",
                    error=f"Unknown persona: {persona}. Available: {available}",
                )
        return GauntletRulesResult(
            formatted="",
            format=format,
            total_rules=0,
            personas=[],
            message="No rules found",
            error="No rules found. Check your buildlog installation.",
        )

    from buildlog.seeds import get_rule_id

    # Build data structure
    data: dict = {}
    total_rules = 0
    for name, sf in seeds.items():
        rules_list: list[dict[str, Any]] = []
        for i, r in enumerate(sf.rules):
            rid = get_rule_id(r, name, i)
            if compact:
                rules_list.append({"id": rid, "rule": r.rule, "category": r.category})
            else:
                rules_list.append(
                    {
                        "id": rid,
                        "rule": r.rule,
                        "category": r.category,
                        "context": r.context,
                        "antipattern": r.antipattern,
                        "rationale": r.rationale,
                        "tags": r.tags,
                    }
                )
        data[name] = {"version": sf.version, "rules": rules_list}
        total_rules += len(sf.rules)

    # Format output
    if format == "json":
        formatted = json.dumps(data, indent=2)
    elif format == "yaml":
        import yaml

        formatted = yaml.dump(data, default_flow_style=False, sort_keys=False)
    elif format == "markdown":
        lines = ["# Review Gauntlet Rules\n"]
        for name, sf in seeds.items():
            lines.append(f"## {name.replace('_', ' ').title()}\n")
            lines.append(f"*{len(sf.rules)} rules, v{sf.version}*\n")
            for i, r in enumerate(sf.rules):
                rid = get_rule_id(r, name, i)
                lines.append(f"- [{rid}] **{r.rule}** ({r.category})")
                if not compact:
                    if r.context:
                        lines.append(f"  - When: {r.context}")
                    if r.antipattern:
                        lines.append(f"  - Antipattern: {r.antipattern}")
                    if r.rationale:
                        lines.append(f"  - Why: {r.rationale}")
            lines.append("")
        formatted = "\n".join(lines)
    else:
        formatted = json.dumps(data, indent=2)

    return GauntletRulesResult(
        formatted=formatted,
        format=format,
        total_rules=total_rules,
        personas=list(seeds.keys()),
        message=f"{total_rules} rules across {len(seeds)} persona(s)",
    )


def _quick_workflow_check(buildlog_dir: Path) -> dict:
    """Lightweight workflow check for overview. Returns dict with workflow_ok and workflow_issues."""
    from buildlog.constants import _WORKFLOW_SECTION_START

    issues: list[str] = []
    project_dir = buildlog_dir.parent

    claude_md = project_dir / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        if _WORKFLOW_SECTION_START not in content:
            issues.append("CLAUDE.md missing workflow section")
    else:
        issues.append("CLAUDE.md not found")

    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip() in ("main", "master"):
            issues.append(
                f"On branch '{result.stdout.strip()}' — create a feature branch"
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {
        "workflow_ok": len(issues) == 0,
        "workflow_issues": issues if issues else None,
    }


def get_overview(
    buildlog_dir: Path,
) -> OverviewResult:
    """Get project buildlog state at a glance.

    Args:
        buildlog_dir: Path to buildlog directory.

    Returns:
        OverviewResult with entries, skills, session, and targets.
    """
    from buildlog.render import RENDERERS

    # Count entries
    entries = sorted(buildlog_dir.glob("20??-??-??-*.md"))

    # Skills
    try:
        skill_set = generate_skills(buildlog_dir)
        total_skills = skill_set.total_skills
        by_confidence: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for cat_skills in skill_set.skills.values():
            for s in cat_skills:
                by_confidence[s.confidence] += 1
    except Exception:
        total_skills = 0
        by_confidence = {"high": 0, "medium": 0, "low": 0}

    # Promoted/rejected
    backend, project_id = _get_storage(buildlog_dir)
    promoted_count = len(backend.load_id_set(project_id, "promoted"))
    rejected_count = len(backend.load_id_set(project_id, "rejected"))

    # Active session
    active_session = None
    active_data = backend.load_active_session(project_id)
    if active_data is not None:
        active_session = active_data.get("id")

    pending_count = total_skills - promoted_count - rejected_count

    # Emission health
    pending_emissions_count = 0
    total_edges = 0
    try:
        from buildlog.emissions import list_pending

        pending_emissions_count = len(list_pending())
    except Exception:
        pass
    try:
        total_edges = backend.count_emission_edges()
    except Exception:
        pass

    session_note = f" | session: {active_session}" if active_session else ""
    return OverviewResult(
        entries=len(entries),
        skills={
            "total": total_skills,
            "by_confidence": by_confidence,
            "promoted": promoted_count,
            "rejected": rejected_count,
            "pending": pending_count,
        },
        active_session=active_session,
        render_targets=list(RENDERERS.keys()),
        message=f"{len(entries)} entries, {total_skills} skills ({pending_count} pending){session_note}",
        pending_emissions=pending_emissions_count,
        total_emission_edges=total_edges,
        **_quick_workflow_check(buildlog_dir),
    )


def _ensure_template(buildlog_dir: Path, template_name: str) -> Path | None:
    """Copy a template from bundled sources if missing from buildlog_dir.

    Checks editable install paths, repo root, and installed wheel shared-data.
    Returns the target path on success, or None if no source found.
    """
    import shutil
    import sysconfig

    target = buildlog_dir / template_name

    pkg_dir = Path(__file__).resolve().parent.parent  # src/buildlog/
    candidates = [
        pkg_dir.parent.parent / "template" / "buildlog" / template_name,
        pkg_dir.parent / "template" / "buildlog" / template_name,
    ]

    data_dir = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "buildlog"
        / "template"
        / "buildlog"
    )
    candidates.append(data_dir / template_name)

    for candidate in candidates:
        if candidate.exists():
            shutil.copy2(candidate, target)
            return target
    return None


def create_entry(
    buildlog_dir: Path,
    slug: str,
    entry_date: str | None = None,
    quick: bool = False,
) -> CreateEntryResult:
    """Create a new buildlog journal entry.

    Args:
        buildlog_dir: Path to buildlog directory.
        slug: Short identifier for the entry.
        entry_date: Date in YYYY-MM-DD format, or None for today.
        quick: Use short template if True.

    Returns:
        CreateEntryResult with path and metadata.
    """
    import shutil
    from datetime import date as date_cls
    from datetime import datetime as dt_cls

    if not buildlog_dir.exists():
        return CreateEntryResult(
            entry_path="",
            entry_name="",
            date_str="",
            template_used="",
            message="",
            error=f"No buildlog directory found at {buildlog_dir}",
        )

    # Template selection
    template_name = "_TEMPLATE_QUICK.md" if quick else "_TEMPLATE.md"
    template_file = buildlog_dir / template_name
    if quick and not template_file.exists():
        template_file = buildlog_dir / "_TEMPLATE.md"
        template_name = "_TEMPLATE.md"

    if not template_file.exists():
        # Self-healing: copy from bundled template sources
        provisioned = _ensure_template(buildlog_dir, template_name)
        if provisioned is not None:
            template_file = provisioned

    if not template_file.exists():
        return CreateEntryResult(
            entry_path="",
            entry_name="",
            date_str="",
            template_used="",
            message="",
            error=f"No {template_name} found in {buildlog_dir}",
        )

    # Date
    if entry_date:
        try:
            parsed = dt_cls.strptime(entry_date, "%Y-%m-%d").date()
            date_str = parsed.isoformat()
        except ValueError:
            return CreateEntryResult(
                entry_path="",
                entry_name="",
                date_str="",
                template_used="",
                message="",
                error=f"Invalid date: {entry_date}. Use YYYY-MM-DD.",
            )
    else:
        date_str = date_cls.today().isoformat()

    # Sanitize slug
    safe_slug = slug.lower().replace(" ", "-").replace("_", "-")
    safe_slug = "".join(c for c in safe_slug if c.isalnum() or c == "-")

    # Create entry
    entry_name = f"{date_str}-{safe_slug}.md"
    entry_path = buildlog_dir / entry_name

    if entry_path.exists():
        return CreateEntryResult(
            entry_path=str(entry_path),
            entry_name=entry_name,
            date_str=date_str,
            template_used=template_name,
            message="",
            error=f"Entry already exists: {entry_path}",
        )

    shutil.copy(template_file, entry_path)

    # Replace date placeholder
    content = entry_path.read_text()
    content = content.replace("[YYYY-MM-DD]", date_str)
    entry_path.write_text(content)

    return CreateEntryResult(
        entry_path=str(entry_path),
        entry_name=entry_name,
        date_str=date_str,
        template_used=template_name,
        message=f"Created {entry_path}",
    )


def list_entries(
    buildlog_dir: Path,
) -> ListEntriesResult:
    """List all buildlog journal entries, most recent first.

    Args:
        buildlog_dir: Path to buildlog directory.

    Returns:
        ListEntriesResult with entry list.
    """
    if not buildlog_dir.exists():
        return ListEntriesResult(
            entries=[],
            count=0,
            message=f"No buildlog directory found at {buildlog_dir}",
        )

    entry_paths = sorted(
        buildlog_dir.glob("20??-??-??-*.md"),
        reverse=True,
    )

    entries: list[dict] = []
    for ep in entry_paths:
        try:
            first_line = ep.read_text().split("\n")[0]
            title = (
                first_line.replace("# Build Journal: ", "").replace("# ", "").strip()
            )
            if title == "[TITLE]":
                title = "(untitled)"
        except Exception:
            title = "(unreadable)"
        entries.append({"name": ep.name, "title": title})

    message = ""
    if not entries:
        message = "No entries yet. Create one with: buildlog new my-feature"
    else:
        message = f"{len(entries)} entries"

    return ListEntriesResult(
        entries=entries,
        count=len(entries),
        message=message,
    )


# =============================================================================
# P0: Gauntlet loop operations
# =============================================================================


@dataclass
class CommitResult:
    """Result of a commit operation."""

    commit_hash: str
    commit_message: str
    files_changed: list[str]
    entry_path: str | None
    entry_updated: bool
    message: str
    error: str | None = None


@dataclass
class GauntletPromptResult:
    """Result of generating a gauntlet review prompt."""

    prompt: str
    target: str
    personas: list[str]
    total_rules: int
    message: str
    error: str | None = None


@dataclass
class GauntletLoopConfigResult:
    """Configuration and instructions for running the gauntlet loop."""

    target: str
    personas: list[str]
    max_iterations: int
    stop_at: str
    auto_gh_issues: bool
    rules_by_persona: dict[str, list[dict]]
    instructions: list[str]
    issue_format: dict[str, str]
    prompt: str
    message: str
    error: str | None = None
    rule_id_index: dict[str, dict] = field(default_factory=dict)


def _resolve_entry_path_core(
    buildlog_dir: Path,
    today: str,
    slug: str | None,
    explicit: str | None,
    cwd: str | None = None,
) -> Path:
    """Find or create the entry path for today."""
    import subprocess

    if explicit:
        return Path(explicit)

    existing = list(buildlog_dir.glob(f"{today}-*.md"))
    if existing:
        return existing[0]

    if slug is None:
        try:
            run_kwargs: dict = {"cwd": cwd} if cwd else {}
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True,
                **run_kwargs,
            ).stdout.strip()
            slug = branch.split("/")[-1].lower().replace("_", "-")
            slug = "".join(c for c in slug if c.isalnum() or c == "-")
        except subprocess.CalledProcessError:
            slug = "session"

    if not slug:
        slug = "session"

    return buildlog_dir / f"{today}-{slug}.md"


def commit(
    buildlog_dir: Path,
    git_args: list[str],
    slug: str | None = None,
    entry: str | None = None,
    no_entry: bool = False,
    cwd: str | None = None,
) -> CommitResult:
    """Run git commit and append commit block to today's buildlog entry.

    Args:
        buildlog_dir: Path to buildlog directory.
        git_args: Arguments to pass to git commit (e.g., ["-m", "feat: thing"]).
        slug: Entry slug (default: derived from branch name).
        entry: Explicit entry file path to append to.
        no_entry: Skip buildlog entry update.
        cwd: Working directory for git commands.

    Returns:
        CommitResult with commit info and entry update status.
    """
    import subprocess
    from datetime import date

    run_kwargs: dict = {"cwd": cwd} if cwd else {}

    git_cmd = ["git", "commit", *git_args]
    env = {**__import__("os").environ, "BUILDLOG_COMMIT": "1"}
    result = subprocess.run(
        git_cmd, capture_output=True, text=True, env=env, **run_kwargs
    )

    if result.returncode != 0:
        return CommitResult(
            commit_hash="",
            commit_message="",
            files_changed=[],
            entry_path=None,
            entry_updated=False,
            message="",
            error=f"git commit failed: {result.stderr.strip()}",
        )

    try:
        commit_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            **run_kwargs,
        ).stdout.strip()
        commit_msg = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            capture_output=True,
            text=True,
            check=True,
            **run_kwargs,
        ).stdout.strip()
        diff_result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            capture_output=True,
            text=True,
            **run_kwargs,
        )
        if diff_result.returncode == 0 and diff_result.stdout.strip():
            files_changed = diff_result.stdout.strip().split("\n")
        else:
            # Root commit fallback
            ls_result = subprocess.run(
                ["git", "ls-tree", "--name-only", "-r", "HEAD"],
                capture_output=True,
                text=True,
                **run_kwargs,
            )
            if ls_result.returncode == 0 and ls_result.stdout.strip():
                files_changed = ls_result.stdout.strip().split("\n")
            else:
                files_changed = []
    except subprocess.CalledProcessError:
        return CommitResult(
            commit_hash="",
            commit_message="",
            files_changed=[],
            entry_path=None,
            entry_updated=False,
            message="",
            error="git commit succeeded but could not read commit info",
        )

    entry_path_str = None
    entry_updated = False

    if not no_entry and buildlog_dir.exists():
        today_str = date.today().isoformat()
        resolved = _resolve_entry_path_core(buildlog_dir, today_str, slug, entry, cwd)

        commit_block = f"\n### `{commit_hash}` — {commit_msg}\n\n"
        if files_changed:
            commit_block += "Files:\n"
            for f in files_changed[:20]:
                commit_block += f"- `{f}`\n"
            if len(files_changed) > 20:
                commit_block += f"- ...and {len(files_changed) - 20} more\n"
        commit_block += "\n"

        if resolved.exists():
            content = resolved.read_text()
            if "## Commits" not in content:
                content = content.rstrip() + "\n\n## Commits\n"
            content += commit_block
        else:
            content = f"# {today_str}\n\n## Commits\n{commit_block}"

        resolved.write_text(content)
        entry_path_str = str(resolved)
        entry_updated = True

    return CommitResult(
        commit_hash=commit_hash,
        commit_message=commit_msg,
        files_changed=files_changed,
        entry_path=entry_path_str,
        entry_updated=entry_updated,
        message=f"Committed {commit_hash}: {commit_msg}",
    )


def select_gauntlet_rules(
    buildlog_dir: Path,
    seeds: dict,
    select_k: int | None = None,
) -> dict:
    """Filter and rank gauntlet rules through the learning backend.

    When ``select_k`` is None, returns all rules unranked (flat mode).
    When set, uses Thompson Sampling to pick the top-k rules per persona,
    biased toward rules that have been cited in past gauntlet reviews.

    Args:
        buildlog_dir: Path to buildlog directory (for bandit state).
        seeds: Dict mapping persona name to SeedFile (from ``load_all_seeds``).
        select_k: Max rules to select per persona, or None for all.

    Returns:
        Filtered ``seeds`` dict with the same structure — SeedFiles with
        a (possibly reduced) rules list.
    """
    if select_k is None:
        return seeds

    from buildlog.seeds import SeedFile, SeedRule, get_rule_id

    backend = get_learning_backend(buildlog_dir)

    filtered: dict = {}
    for persona_name, sf in seeds.items():
        if len(sf.rules) <= select_k:
            filtered[persona_name] = sf
            continue

        # Build ID → rule index mapping
        id_to_idx: dict[str, int] = {}
        all_ids: list[str] = []
        seed_rule_ids: set[str] = set()
        for i, rule in enumerate(sf.rules):
            rule_id = get_rule_id(rule, persona_name, i)
            id_to_idx[rule_id] = i
            all_ids.append(rule_id)
            seed_rule_ids.add(rule_id)

        selected_ids = backend.select(
            candidates=all_ids,
            context=None,
            k=select_k,
            seed_rule_ids=seed_rule_ids,
        )

        # Rebuild SeedFile with only selected rules
        selected_rules: list[SeedRule] = []
        for rid in selected_ids:
            idx = id_to_idx.get(rid)
            if idx is not None:
                selected_rules.append(sf.rules[idx])

        # Fallback: if selection returned empty, keep all
        if not selected_rules:
            filtered[persona_name] = sf
        else:
            filtered[persona_name] = SeedFile(
                persona=sf.persona,
                version=sf.version,
                rules=selected_rules,
            )

    return filtered


def generate_gauntlet_prompt(
    target: str,
    personas: list[str] | None = None,
    buildlog_dir: Path | None = None,
    select_k: int | None = None,
) -> GauntletPromptResult:
    """Generate a review prompt combining gauntlet rules with target info.

    Args:
        target: Path to target code (file or directory).
        personas: List of persona names to include, or None for all.

    Returns:
        GauntletPromptResult with the formatted prompt.
    """
    from buildlog.seeds import get_rule_id, load_rules
    from buildlog.storage import get_backend

    try:
        backend, _ = get_backend()
    except Exception:
        backend = None

    seeds = load_rules(backend=backend)
    if not seeds:
        return GauntletPromptResult(
            prompt="",
            target=target,
            personas=[],
            total_rules=0,
            message="",
            error="No rules found. Check your buildlog installation.",
        )

    if personas:
        filtered = {k: v for k, v in seeds.items() if k in personas}
        if not filtered:
            available = ", ".join(seeds.keys())
            return GauntletPromptResult(
                prompt="",
                target=target,
                personas=[],
                total_rules=0,
                message="",
                error=(
                    f"No matching personas: {', '.join(personas)}."
                    f" Available: {available}"
                ),
            )
        seeds = filtered

    # Rank/filter rules through the learning backend when select_k is set
    total_before = sum(len(sf.rules) for sf in seeds.values())
    if select_k is not None and buildlog_dir is not None:
        seeds = select_gauntlet_rules(buildlog_dir, seeds, select_k)
    total_after = sum(len(sf.rules) for sf in seeds.values())

    lines = [
        "# Review Gauntlet Prompt\n",
        "You are running the Review Gauntlet." " Apply these rules ruthlessly.\n",
        "## Target\n",
        f"Review: `{target}`\n",
        "## Reviewers and Rules\n",
    ]

    total_rules = 0
    for name, sf in seeds.items():
        persona_name = name.replace("_", " ").title()
        lines.append(f"### {persona_name}\n")
        for i, r in enumerate(sf.rules):
            rule_id = get_rule_id(r, name, i)
            lines.append(f"- [{rule_id}] **{r.rule}**")
            if r.antipattern:
                lines.append(f"  - Antipattern: {r.antipattern}")
        lines.append("")
        total_rules += len(sf.rules)

    lines.extend(
        [
            "## Output Format\n",
            "For each issue found, output:\n",
            "```json",
            "{",
            '  "reviewer": "<persona>",',
            '  "severity": "critical|major|minor|nitpick",',
            '  "category": "<category>",',
            '  "location": "<file:line>",',
            '  "description": "<what is wrong>",',
            '  "rule_learned": "<generalizable rule>",',
            '  "rules_consulted": ["<rule_id>", "..."],',
            '  "rule_reasoning": {',
            '    "<rule_id>": "<HOW this rule applies to the specific violation>"',
            "  }",
            "}",
            "```\n",
            "## Instructions\n",
            "1. Read the target code thoroughly",
            "2. Apply each rule from each reviewer",
            "3. Report ALL violations found",
            "4. Be ruthless - this is the gauntlet",
            "5. Cite specific rule IDs you applied in `rules_consulted`",
            "6. In `rule_reasoning`, explain HOW each cited rule applies"
            " to the specific violation",
            "7. Do NOT carpet-cite — only cite rules you actually applied",
            "",
        ]
    )

    formatted = "\n".join(lines)

    msg = f"Generated prompt with {total_rules} rules from {len(seeds)} personas"
    if select_k is not None and total_before > total_after:
        msg += f" (selected {total_after}/{total_before} via learning backend)"

    return GauntletPromptResult(
        prompt=formatted,
        target=target,
        personas=list(seeds.keys()),
        total_rules=total_rules,
        message=msg,
    )


def gauntlet_loop_config(
    target: str,
    personas: list[str] | None = None,
    max_iterations: int = 10,
    stop_at: str = "minors",
    auto_gh_issues: bool = False,
    buildlog_dir: Path | None = None,
    select_k: int | None = None,
) -> GauntletLoopConfigResult:
    """Generate gauntlet loop configuration for an agent.

    Args:
        target: Path to target code.
        personas: Persona names to include, or None for all.
        max_iterations: Max loop iterations (default: 10).
        stop_at: Severity level to stop at (criticals/majors/minors).
        auto_gh_issues: Create GitHub issues for accepted risk items.

    Returns:
        GauntletLoopConfigResult with full loop configuration.
    """
    from buildlog.seeds import build_rule_id_index, get_rule_id, load_rules
    from buildlog.storage import get_backend

    try:
        backend, _ = get_backend()
    except Exception:
        backend = None

    _empty = GauntletLoopConfigResult(
        target=target,
        personas=[],
        max_iterations=max_iterations,
        stop_at=stop_at,
        auto_gh_issues=auto_gh_issues,
        rules_by_persona={},
        instructions=[],
        issue_format={},
        prompt="",
        message="",
    )

    seeds = load_rules(backend=backend)
    if not seeds:
        _empty.error = "No rules found. Check your buildlog installation."
        return _empty

    if personas:
        filtered = {k: v for k, v in seeds.items() if k in personas}
        if not filtered:
            available = ", ".join(seeds.keys())
            _empty.error = f"No matching personas. Available: {available}"
            return _empty
        seeds = filtered

    # Rank/filter rules through the learning backend
    if select_k is not None and buildlog_dir is not None:
        seeds = select_gauntlet_rules(buildlog_dir, seeds, select_k)

    rules_by_persona: dict[str, list[dict]] = {}
    for name, sf in seeds.items():
        rules_by_persona[name] = [
            {
                "rule": r.rule,
                "antipattern": r.antipattern,
                "category": r.category,
                "provenance_id": get_rule_id(r, name, i),
            }
            for i, r in enumerate(sf.rules)
        ]

    rule_id_index = build_rule_id_index(seeds)

    prompt_result = generate_gauntlet_prompt(
        target=target,
        personas=list(seeds.keys()),
        buildlog_dir=buildlog_dir,
        select_k=select_k,
    )
    prompt = prompt_result.prompt if not prompt_result.error else ""

    instructions = [
        "1. Review the target code using the rules from each persona",
        "2. Report all violations as JSON issues with: severity,"
        " category, description, rule_learned, location,"
        " rules_consulted, rule_reasoning",
        "3. In `rules_consulted`, cite the specific rule IDs"
        " (shown in brackets in the prompt) that informed this finding",
        "4. In `rule_reasoning`, explain HOW each cited rule applies",
        "5. Do NOT carpet-cite — only cite rules you actually applied",
        "6. Call `buildlog_gauntlet_issues` with the issues list"
        " and `valid_rule_ids` to determine next action",
        "7. If action='fix_criticals': Fix critical+major issues,"
        " then re-run gauntlet",
        "8. If action='checkpoint_majors': Ask user whether to"
        " continue fixing majors",
        "9. If action='checkpoint_minors': Ask user whether to"
        " accept risk or continue",
        "10. If user accepts risk and auto_gh_issues: Call"
        " `buildlog_gauntlet_accept_risk` with remaining issues",
        "11. Repeat until action='clean' or max_iterations reached",
    ]

    issue_format = {
        "severity": "critical|major|minor|nitpick",
        "category": "security|testing|architectural|workflow|...",
        "description": "Concrete description of what's wrong",
        "rule_learned": "Generalizable rule for the future",
        "location": "file:line (optional)",
        "rules_consulted": "[list of rule IDs from the prompt]",
        "rule_reasoning": "{rule_id: 'HOW this rule applies'}",
    }

    return GauntletLoopConfigResult(
        target=target,
        personas=list(seeds.keys()),
        max_iterations=max_iterations,
        stop_at=stop_at,
        auto_gh_issues=auto_gh_issues,
        rules_by_persona=rules_by_persona,
        instructions=instructions,
        issue_format=issue_format,
        prompt=prompt,
        message=(
            f"Gauntlet loop ready: {len(seeds)} personas,"
            f" max {max_iterations} iterations"
        ),
        rule_id_index=rule_id_index,
    )


# =============================================================================
# P2: Nice-to-have operations
# =============================================================================


@dataclass
class GauntletGenerateResult:
    """Result of generating seed rules from source text."""

    persona: str
    rule_count: int
    source_count: int
    output_path: str | None
    preview: dict | None
    message: str
    error: str | None = None


@dataclass
class InitResult:
    """Result of initializing buildlog in a project."""

    initialized: bool
    buildlog_dir: str
    claude_md_updated: bool
    mcp_registered: bool
    message: str
    hooks_installed: bool = False
    error: str | None = None


@dataclass
class UpdateResult:
    """Result of updating buildlog templates."""

    updated: bool
    message: str
    error: str | None = None


@dataclass
class VerifyCheck:
    """A single verification check result."""

    name: str
    status: str  # "passed" | "warning" | "failed"
    message: str


@dataclass
class VerifyResult:
    """Result of verifying buildlog workflow setup."""

    passed: list[VerifyCheck]
    warnings: list[VerifyCheck]
    failed: list[VerifyCheck]
    ok: bool
    summary: str
    message: str = ""


def gauntlet_generate(
    source_text: str,
    persona: str,
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> GauntletGenerateResult:
    """Generate seed rules from source text using LLM extraction.

    Args:
        source_text: The text content to extract rules from.
        persona: Persona name for the seed file.
        output_dir: Output directory for seed YAML.
        dry_run: Preview without writing to disk.

    Returns:
        GauntletGenerateResult with generation info.
    """
    if not source_text.strip():
        return GauntletGenerateResult(
            persona=persona,
            rule_count=0,
            source_count=0,
            output_path=None,
            preview=None,
            message="",
            error="Empty source text provided.",
        )

    try:
        from buildlog.seed_engine import Pipeline
    except ImportError:
        return GauntletGenerateResult(
            persona=persona,
            rule_count=0,
            source_count=0,
            output_path=None,
            preview=None,
            message="",
            error="Seed engine not available. Check installation.",
        )

    if output_dir is None:
        output_dir = Path("buildlog/.buildlog/seeds")

    # Get LLM backend
    try:
        from buildlog.llm import get_llm_backend

        backend = get_llm_backend()
    except Exception:
        backend = None

    if backend is None:
        return GauntletGenerateResult(
            persona=persona,
            rule_count=0,
            source_count=1,
            output_path=None,
            preview=None,
            message="",
            error=(
                "No LLM backend available. Set ANTHROPIC_API_KEY" " or install Ollama."
            ),
        )

    source_content = {"inline": source_text}

    try:
        from buildlog.seed_engine.models import Source, SourceType

        sources = [
            Source(
                name="inline",
                url="mcp://inline",
                source_type=SourceType.REFERENCE_DOC,
                domain="general",
            )
        ]
    except ImportError:
        return GauntletGenerateResult(
            persona=persona,
            rule_count=0,
            source_count=1,
            output_path=None,
            preview=None,
            message="",
            error="Seed engine models not available.",
        )

    try:
        pipeline = Pipeline.with_llm(
            persona=persona,
            backend=backend,
            source_content=source_content,
        )
    except Exception as e:
        return GauntletGenerateResult(
            persona=persona,
            rule_count=0,
            source_count=1,
            output_path=None,
            preview=None,
            message="",
            error=f"Failed to initialize pipeline: {e}",
        )

    try:
        if dry_run:
            preview = pipeline.dry_run(sources)
            return GauntletGenerateResult(
                persona=persona,
                rule_count=preview.get("rule_count", 0),
                source_count=1,
                output_path=None,
                preview=preview,
                message="Dry run complete (no files written).",
            )
        else:
            pipe_result = pipeline.run(sources, output_dir=output_dir)
            output_path_str = str(output_dir / f"{persona}.yaml")
            return GauntletGenerateResult(
                persona=persona,
                rule_count=pipe_result.rule_count,
                source_count=1,
                output_path=output_path_str,
                preview=None,
                message=f"Generated seed file: {output_path_str}",
            )
    except Exception as e:
        return GauntletGenerateResult(
            persona=persona,
            rule_count=0,
            source_count=1,
            output_path=None,
            preview=None,
            message="",
            error=f"Pipeline execution failed: {e}",
        )


def init_buildlog(
    project_dir: Path,
    defaults: bool = True,
    no_claude_md: bool = False,
    no_mcp: bool = False,
) -> InitResult:
    """Initialize buildlog in a project directory.

    Args:
        project_dir: Project root directory.
        defaults: Use default values (non-interactive).
        no_claude_md: Skip CLAUDE.md update.
        no_mcp: Skip MCP server registration.

    Returns:
        InitResult with initialization status.
    """
    import subprocess
    import sys

    buildlog_dir = project_dir / "buildlog"
    if buildlog_dir.exists():
        return InitResult(
            initialized=False,
            buildlog_dir=str(buildlog_dir),
            claude_md_updated=False,
            mcp_registered=False,
            message="",
            error=f"buildlog/ already exists at {buildlog_dir}",
        )

    # Find template directory
    template_src = None
    # Check for local template
    here = Path(__file__).resolve().parent.parent
    local_template = here / "template"
    if not local_template.exists():
        local_template = here.parent / "template"
    if local_template.exists():
        template_src = str(local_template)
    else:
        template_src = "gh:Peleke/buildlog-template"

    cmd = [
        sys.executable,
        "-m",
        "copier",
        "copy",
        "--trust",
    ]
    if defaults:
        cmd.append("--defaults")
    cmd.extend([template_src, str(project_dir)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return InitResult(
                initialized=False,
                buildlog_dir=str(buildlog_dir),
                claude_md_updated=False,
                mcp_registered=False,
                message="",
                error=f"copier failed: {result.stderr.strip()}",
            )
    except FileNotFoundError:
        return InitResult(
            initialized=False,
            buildlog_dir=str(buildlog_dir),
            claude_md_updated=False,
            mcp_registered=False,
            message="",
            error="copier not found. Install with: pip install copier",
        )
    except subprocess.TimeoutExpired:
        return InitResult(
            initialized=False,
            buildlog_dir=str(buildlog_dir),
            claude_md_updated=False,
            mcp_registered=False,
            message="",
            error="copier timed out after 60 seconds",
        )

    # Create .buildlog directories (copier skips dot-prefixed paths)
    dot_buildlog = buildlog_dir / ".buildlog"
    dot_buildlog.mkdir(exist_ok=True)
    (dot_buildlog / "seeds").mkdir(exist_ok=True)

    claude_md_updated = False
    if not no_claude_md:
        claude_md = project_dir / "CLAUDE.md"
        if claude_md.exists():
            try:
                from buildlog.constants import CLAUDE_MD_BUILDLOG_SECTION

                content = claude_md.read_text()
                if "## buildlog Integration" not in content:
                    content = content.rstrip() + "\n\n" + CLAUDE_MD_BUILDLOG_SECTION
                    claude_md.write_text(content)
                    claude_md_updated = True
            except ImportError:
                pass

    mcp_registered = False
    if not no_mcp:
        try:
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir(exist_ok=True)
            settings_path = claude_dir / "settings.json"
            settings: dict = {}
            if settings_path.exists():
                try:
                    settings = json.loads(settings_path.read_text())
                except json.JSONDecodeError:
                    pass
            if "mcpServers" not in settings:
                settings["mcpServers"] = {}
            if "buildlog" not in settings["mcpServers"]:
                settings["mcpServers"]["buildlog"] = {
                    "command": "buildlog-mcp",
                    "args": [],
                }
                settings_path.write_text(json.dumps(settings, indent=2) + "\n")
            mcp_registered = True
        except Exception:
            pass

    # Install git hooks (pre-commit enforcement + post-commit nudge)
    hooks_installed = False
    try:
        from buildlog.hooks import install_hooks

        install_hooks(project_dir)
        hooks_installed = True
    except Exception:
        pass

    return InitResult(
        initialized=True,
        buildlog_dir=str(buildlog_dir),
        claude_md_updated=claude_md_updated,
        mcp_registered=mcp_registered,
        hooks_installed=hooks_installed,
        message="buildlog initialized successfully.",
    )


def update_buildlog(
    project_dir: Path,
) -> UpdateResult:
    """Update buildlog templates to the latest version.

    Args:
        project_dir: Project root directory.

    Returns:
        UpdateResult with update status.
    """
    import subprocess
    import sys

    try:
        result = subprocess.run(
            [sys.executable, "-m", "copier", "update", "--trust"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=120,
        )
        if result.returncode != 0:
            return UpdateResult(
                updated=False,
                message="",
                error=f"copier update failed: {result.stderr.strip()}",
            )
    except FileNotFoundError:
        return UpdateResult(
            updated=False,
            message="",
            error="copier not found. Install with: pip install copier",
        )
    except subprocess.TimeoutExpired:
        return UpdateResult(
            updated=False,
            message="",
            error="copier update timed out after 120 seconds",
        )

    return UpdateResult(
        updated=True,
        message="buildlog templates updated successfully.",
    )


def verify_workflow(
    project_dir: Path,
    buildlog_dir: Path | None = None,
) -> VerifyResult:
    """Verify that the buildlog workflow is correctly set up.

    Checks: buildlog/ exists, CLAUDE.md has workflow section, MCP registered,
    not on main branch, pre-commit hook installed.

    Args:
        project_dir: Project root directory.
        buildlog_dir: Path to buildlog directory. Defaults to project_dir / "buildlog".

    Returns:
        VerifyResult with passed/warnings/failed checks.
    """
    import subprocess

    from buildlog.constants import _WORKFLOW_SECTION_END, _WORKFLOW_SECTION_START

    if buildlog_dir is None:
        buildlog_dir = project_dir / "buildlog"

    passed: list[VerifyCheck] = []
    warnings: list[VerifyCheck] = []
    failed: list[VerifyCheck] = []

    # Check 1: buildlog/ directory exists
    if buildlog_dir.exists() and buildlog_dir.is_dir():
        passed.append(VerifyCheck("buildlog_dir", "passed", f"{buildlog_dir} exists"))
    else:
        failed.append(
            VerifyCheck(
                "buildlog_dir",
                "failed",
                f"{buildlog_dir} not found. Run: buildlog init",
            )
        )

    # Check 2: .buildlog/ metadata directory
    dot_buildlog = buildlog_dir / ".buildlog"
    if dot_buildlog.exists():
        passed.append(
            VerifyCheck("metadata_dir", "passed", ".buildlog/ metadata dir exists")
        )
    else:
        warnings.append(
            VerifyCheck(
                "metadata_dir",
                "warning",
                ".buildlog/ metadata dir missing. Run: buildlog init",
            )
        )

    # Check 3: CLAUDE.md has workflow section
    claude_md = project_dir / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        if _WORKFLOW_SECTION_START in content and _WORKFLOW_SECTION_END in content:
            passed.append(
                VerifyCheck(
                    "workflow_section", "passed", "CLAUDE.md has workflow section"
                )
            )
        elif "## buildlog Integration" in content:
            warnings.append(
                VerifyCheck(
                    "workflow_section",
                    "warning",
                    "CLAUDE.md has buildlog section but missing workflow markers. "
                    "Run: buildlog update",
                )
            )
        else:
            failed.append(
                VerifyCheck(
                    "workflow_section",
                    "failed",
                    "CLAUDE.md missing workflow section. Run: buildlog init",
                )
            )
    else:
        failed.append(
            VerifyCheck(
                "workflow_section",
                "failed",
                "CLAUDE.md not found. Run: buildlog init",
            )
        )

    # Check 4: MCP server registered
    mcp_settings = Path.home() / ".claude.json"
    # Traversal protection: resolve symlinks, verify path stays under $HOME
    _mcp_safe = True
    try:
        resolved_settings = mcp_settings.resolve()
        resolved_home = Path.home().resolve()
        if not (
            resolved_settings == resolved_home / ".claude.json"
            or resolved_settings.is_relative_to(resolved_home)
        ):
            _mcp_safe = False
            warnings.append(
                VerifyCheck(
                    "mcp_registered",
                    "warning",
                    "~/.claude.json resolves outside home directory",
                )
            )
    except (OSError, RuntimeError):
        _mcp_safe = False
        warnings.append(
            VerifyCheck(
                "mcp_registered",
                "warning",
                "Could not resolve ~/.claude.json path",
            )
        )

    if _mcp_safe and mcp_settings.exists():
        try:
            import json

            settings = json.loads(mcp_settings.read_text())
            mcp_servers = settings.get("mcpServers", {})
            if "buildlog" in mcp_servers:
                passed.append(
                    VerifyCheck("mcp_registered", "passed", "MCP server registered")
                )
            else:
                warnings.append(
                    VerifyCheck(
                        "mcp_registered",
                        "warning",
                        "MCP server not registered. Run: buildlog init-mcp --global",
                    )
                )
        except (json.JSONDecodeError, OSError):
            warnings.append(
                VerifyCheck(
                    "mcp_registered",
                    "warning",
                    "Could not read ~/.claude.json",
                )
            )
    elif _mcp_safe:
        warnings.append(
            VerifyCheck(
                "mcp_registered",
                "warning",
                "~/.claude.json not found. Run: buildlog init-mcp --global",
            )
        )

    # Check 5: Not on main branch
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch in ("main", "master"):
                warnings.append(
                    VerifyCheck(
                        "not_on_main",
                        "warning",
                        f"On branch '{branch}'. Create a feature branch before committing.",
                    )
                )
            else:
                passed.append(
                    VerifyCheck(
                        "not_on_main", "passed", f"On branch '{branch}' (not main)"
                    )
                )
        else:
            # Not a git repo — skip this check
            pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check 6: Pre-commit hook for branch protection
    git_hooks_dir = project_dir / ".git" / "hooks"
    pre_commit_hook = git_hooks_dir / "pre-commit"
    pre_commit_config = project_dir / ".pre-commit-config.yaml"

    if pre_commit_config.exists():
        # Check if config has branch protection
        config_text = pre_commit_config.read_text()
        if (
            "prevent-commit-to-main" in config_text
            or "no-commit-to-branch" in config_text
        ):
            passed.append(
                VerifyCheck(
                    "branch_protection",
                    "passed",
                    "Branch protection configured in .pre-commit-config.yaml",
                )
            )
        else:
            warnings.append(
                VerifyCheck(
                    "branch_protection",
                    "warning",
                    "No branch protection hook in .pre-commit-config.yaml",
                )
            )
    elif pre_commit_hook.exists():
        hook_text = pre_commit_hook.read_text()
        if "main" in hook_text or "master" in hook_text:
            passed.append(
                VerifyCheck(
                    "branch_protection",
                    "passed",
                    "Branch protection in .git/hooks/pre-commit",
                )
            )
        else:
            warnings.append(
                VerifyCheck(
                    "branch_protection",
                    "warning",
                    "Pre-commit hook exists but may not protect main branch",
                )
            )
    else:
        warnings.append(
            VerifyCheck(
                "branch_protection",
                "warning",
                "No pre-commit branch protection. Will be added by buildlog init (Tier 2).",
            )
        )

    ok = len(failed) == 0
    total = len(passed) + len(warnings) + len(failed)
    summary = (
        f"{len(passed)}/{total} checks passed"
        f"{f', {len(warnings)} warnings' if warnings else ''}"
        f"{f', {len(failed)} failed' if failed else ''}"
    )

    return VerifyResult(
        passed=passed,
        warnings=warnings,
        failed=failed,
        ok=ok,
        summary=summary,
        message=summary,
    )
