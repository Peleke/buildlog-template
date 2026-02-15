"""Agent-agnostic experiment tracking engine.

This module contains the core session tracking, mistake logging, and reward
signal logic decoupled from any specific agent or skill generation mechanism.

The key difference from core/operations.py: functions here accept
`available_rules: list[str]` as a parameter rather than calling
`generate_skills()` internally. The caller (CLI, MCP, etc.) is responsible
for getting the rule list however it wants. The engine doesn't care where
rules come from.

Usage:
    from buildlog.engine.experiments import start_session, end_session, log_mistake
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from buildlog.core.learning import get_learning_backend
from buildlog.core.operations import (
    EndSessionResult,
    LogMistakeResult,
    LogRewardResult,
    Mistake,
    RewardEvent,
    RewardSummary,
    Session,
    SessionMetrics,
    StartSessionResult,
)
from buildlog.storage import StorageBackend, get_backend

__all__ = [
    "start_session",
    "end_session",
    "log_mistake",
    "log_reward",
    "get_rewards",
    "session_metrics",
    "experiment_report",
]


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _get_storage(buildlog_dir: Path) -> tuple[StorageBackend, str]:
    """Resolve the storage backend for the project containing *buildlog_dir*."""
    project_root = (
        buildlog_dir.parent if buildlog_dir.name == "buildlog" else buildlog_dir.parent
    )
    return get_backend(buildlog_dir, project_root=project_root)


def _get_current_rules(buildlog_dir: Path) -> list[str]:
    backend, project_id = _get_storage(buildlog_dir)
    return sorted(backend.load_id_set(project_id, "promoted"))


def _generate_session_id(now: datetime) -> str:
    return f"session-{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond:06d}"


def _generate_mistake_id(error_class: str, now: datetime) -> str:
    return f"mistake-{error_class[:10]}-{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond:06d}"


def _compute_semantic_hash(description: str) -> str:
    normalized = " ".join(description.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _generate_reward_id(outcome: str, timestamp: datetime) -> str:
    ts_str = timestamp.isoformat()
    normalized = f"{outcome}:{ts_str}"
    hash_hex = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"rew-{hash_hex}"


def _compute_reward_value(
    outcome: Literal["accepted", "revision", "rejected"],
    revision_distance: float | None,
) -> float:
    if outcome == "accepted":
        return 1.0
    elif outcome == "rejected":
        return 0.0
    else:
        distance = revision_distance if revision_distance is not None else 0.5
        return max(0.0, min(1.0, 1.0 - distance))


def _load_sessions(buildlog_dir: Path) -> list[Session]:
    backend, project_id = _get_storage(buildlog_dir)
    return [Session.from_dict(s) for s in backend.load_events(project_id, "sessions")]  # type: ignore[arg-type]


def _load_mistakes(buildlog_dir: Path) -> list[Mistake]:
    backend, project_id = _get_storage(buildlog_dir)
    return [Mistake.from_dict(m) for m in backend.load_events(project_id, "mistakes")]  # type: ignore[arg-type]


def _find_similar_prior_mistake(
    description: str,
    error_class: str,
    current_session_id: str,
    all_mistakes: list[Mistake],
) -> Mistake | None:
    semantic_hash = _compute_semantic_hash(description)
    for mistake in all_mistakes:
        if (
            mistake.session_id != current_session_id
            and mistake.error_class == error_class
        ):
            if mistake.semantic_hash == semantic_hash:
                return mistake
            desc_words = set(description.lower().split())
            mistake_words = set(mistake.description.lower().split())
            if len(desc_words & mistake_words) / max(len(desc_words), 1) > 0.7:
                return mistake
    return None


# ---------------------------------------------------------------------------
# Public API — agent-agnostic experiment functions
# ---------------------------------------------------------------------------


def start_session(
    buildlog_dir: Path,
    error_class: str | None = None,
    notes: str | None = None,
    select_k: int = 0,
    available_rules: list[str] | None = None,
    seed_rule_ids: set[str] | None = None,
    seed_confidence_map: dict[str, float] | None = None,
) -> StartSessionResult:
    """Start a new experiment session with bandit-selected rules.

    Unlike core/operations.start_session, this function accepts
    ``available_rules`` directly rather than calling generate_skills().
    If ``available_rules`` is None, falls back to reading promoted rule IDs
    from .buildlog/promoted.json.

    Args:
        buildlog_dir: Path to buildlog directory.
        error_class: Error class being targeted (context for bandits).
        notes: Optional notes about the session.
        select_k: Number of rules to select via Thompson Sampling.
                 Default 0 means auto-calculate: max(10, 10% of pool).
        available_rules: Explicit list of candidate rule IDs. If None,
            reads promoted IDs from .buildlog/promoted.json.
        seed_rule_ids: Set of rule IDs that get boosted priors.

    Returns:
        StartSessionResult with session ID, rules count, and selected rules.
    """
    now = datetime.now(timezone.utc)
    session_id = _generate_session_id(now)

    current_rules = (
        available_rules
        if available_rules is not None
        else _get_current_rules(buildlog_dir)
    )

    # Auto-calculate k if not explicitly set (select_k <= 0 means auto)
    if select_k <= 0:
        select_k = max(10, len(current_rules) // 10) if current_rules else 10

    selected_rules: list[str] = []

    if current_rules:
        bandit = get_learning_backend(buildlog_dir)

        selected_rules = bandit.select(
            candidates=current_rules,
            context=error_class or "general",
            k=min(select_k, len(current_rules)),
            seed_rule_ids=seed_rule_ids or set(),
            seed_confidence_map=seed_confidence_map,
        )

    session = Session(
        id=session_id,
        started_at=now,
        rules_at_start=current_rules,
        selected_rules=selected_rules,
        error_class=error_class,
        notes=notes,
    )

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

    session = Session.from_dict(session_data)  # type: ignore[arg-type]

    now = datetime.now(timezone.utc)
    session.ended_at = now
    session.rules_at_end = _get_current_rules(buildlog_dir)
    if entry_file:
        session.entry_file = entry_file
    if notes:
        session.notes = f"{session.notes or ''}\n{notes}".strip()

    backend.append_event(project_id, "sessions", session.to_dict())  # type: ignore[arg-type]
    backend.delete_active_session(project_id)

    all_mistakes = [
        Mistake.from_dict(m) for m in backend.load_events(project_id, "mistakes")  # type: ignore[arg-type]
    ]
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

    Updates the bandit with reward=0 for selected rules in the session.

    Args:
        buildlog_dir: Path to buildlog directory.
        error_class: Category of error.
        description: Description of the mistake.
        corrected_by_rule: Rule ID that should have prevented this.

    Returns:
        LogMistakeResult indicating if this was a repeat.
    """
    backend, project_id = _get_storage(buildlog_dir)

    session_data = backend.load_active_session(project_id)
    if session_data is None:
        raise ValueError(
            "No active session - start one with 'buildlog experiment start'"
        )

    session_id = session_data["id"]

    now = datetime.now(timezone.utc)
    mistake_id = _generate_mistake_id(error_class, now)

    all_mistakes = [
        Mistake.from_dict(m) for m in backend.load_events(project_id, "mistakes")  # type: ignore[arg-type]
    ]
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

    backend.append_event(project_id, "mistakes", mistake.to_dict())  # type: ignore[arg-type]

    selected_rules = session_data.get("selected_rules", [])
    if selected_rules:
        bandit = get_learning_backend(buildlog_dir)
        context = session_data.get("error_class") or "general"
        bandit.batch_update(
            rule_ids=selected_rules,
            reward=0.0,
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

    Args:
        buildlog_dir: Path to buildlog directory.
        outcome: Type of feedback (accepted/revision/rejected).
        rules_active: List of rule IDs in context. If None, uses session's.
        revision_distance: How much correction needed (0-1).
        error_class: Category of error if applicable.
        notes: Optional notes.
        source: Where this feedback came from.
        session_id: Session to associate with. Auto-detects active session if None.

    Returns:
        LogRewardResult with confirmation.
    """
    now = datetime.now(timezone.utc)
    reward_id = _generate_reward_id(outcome, now)
    reward_value = _compute_reward_value(outcome, revision_distance)

    backend, project_id = _get_storage(buildlog_dir)

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

    backend.append_event(project_id, "rewards", event.to_dict())  # type: ignore[arg-type]

    if rules_active:
        bandit = get_learning_backend(buildlog_dir)
        bandit.batch_update(
            rule_ids=rules_active,
            reward=reward_value,
            context=error_class or "general",
        )

    total_events = backend.count_events(project_id, "rewards")

    # Fire-and-forget emission
    try:
        from buildlog.core.operations import _reward_to_emission
        from buildlog.emissions import emit_artifact

        emit_artifact(
            artifact=_reward_to_emission(event, project_id),
            artifact_type="reward_signal",
            project_id=project_id,
        )
    except Exception:
        pass  # Fire-and-forget

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

    events: list[RewardEvent] = []
    for data in raw_events:
        try:
            events.append(RewardEvent.from_dict(data))  # type: ignore[arg-type]
        except (KeyError, ValueError):
            continue

    total = len(events)
    accepted = sum(1 for e in events if e.outcome == "accepted")
    revisions = sum(1 for e in events if e.outcome == "revision")
    rejected = sum(1 for e in events if e.outcome == "rejected")
    mean_reward = sum(e.reward_value for e in events) / total if total > 0 else 0.0

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


def session_metrics(
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


def experiment_report(buildlog_dir: Path) -> dict:
    """Generate a comprehensive experiment report.

    Returns:
        Dictionary with sessions, metrics, and analysis.
    """
    sessions = _load_sessions(buildlog_dir)
    mistakes = _load_mistakes(buildlog_dir)

    session_metrics_list = []
    for session in sessions:
        session_mistakes = [m for m in mistakes if m.session_id == session.id]
        total = len(session_mistakes)
        repeated = sum(1 for m in session_mistakes if m.was_repeat)
        session_metrics_list.append(
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

    total_mistakes = len(mistakes)
    total_repeated = sum(1 for m in mistakes if m.was_repeat)

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
        "sessions": session_metrics_list,
        "error_classes": error_classes,
    }
