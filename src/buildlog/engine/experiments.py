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
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from buildlog.core.bandit import ThompsonSamplingBandit
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
# Path helpers (duplicated from operations to avoid tight coupling)
# ---------------------------------------------------------------------------


def _get_sessions_path(buildlog_dir: Path) -> Path:
    return buildlog_dir / ".buildlog" / "sessions.jsonl"


def _get_mistakes_path(buildlog_dir: Path) -> Path:
    return buildlog_dir / ".buildlog" / "mistakes.jsonl"


def _get_active_session_path(buildlog_dir: Path) -> Path:
    return buildlog_dir / ".buildlog" / "active_session.json"


def _get_rewards_path(buildlog_dir: Path) -> Path:
    return buildlog_dir / ".buildlog" / "reward_events.jsonl"


def _get_promoted_path(buildlog_dir: Path) -> Path:
    return buildlog_dir / ".buildlog" / "promoted.json"


def _load_json_set(path: Path, key: str) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
        return set(data.get(key, []))
    except (json.JSONDecodeError, OSError):
        return set()


def _get_current_rules(buildlog_dir: Path) -> list[str]:
    promoted_path = _get_promoted_path(buildlog_dir)
    return list(_load_json_set(promoted_path, "skill_ids"))


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
    select_k: int = 3,
    available_rules: list[str] | None = None,
    seed_rule_ids: set[str] | None = None,
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

    selected_rules: list[str] = []

    if current_rules:
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)

        selected_rules = bandit.select(
            candidates=current_rules,
            context=error_class or "general",
            k=min(select_k, len(current_rules)),
            seed_rule_ids=seed_rule_ids or set(),
        )

    session = Session(
        id=session_id,
        started_at=now,
        rules_at_start=current_rules,
        selected_rules=selected_rules,
        error_class=error_class,
        notes=notes,
    )

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

    session_data = json.loads(active_path.read_text())
    session = Session.from_dict(session_data)

    now = datetime.now(timezone.utc)
    session.ended_at = now
    session.rules_at_end = _get_current_rules(buildlog_dir)
    if entry_file:
        session.entry_file = entry_file
    if notes:
        session.notes = f"{session.notes or ''}\n{notes}".strip()

    sessions_path = _get_sessions_path(buildlog_dir)
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sessions_path, "a") as f:
        f.write(json.dumps(session.to_dict()) + "\n")

    active_path.unlink()

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

    Updates the bandit with reward=0 for selected rules in the session.

    Args:
        buildlog_dir: Path to buildlog directory.
        error_class: Category of error.
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

    session_data = json.loads(active_path.read_text())
    session_id = session_data["id"]

    now = datetime.now(timezone.utc)
    mistake_id = _generate_mistake_id(error_class, now)

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

    mistakes_path = _get_mistakes_path(buildlog_dir)
    mistakes_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mistakes_path, "a") as f:
        f.write(json.dumps(mistake.to_dict()) + "\n")

    selected_rules = session_data.get("selected_rules", [])
    if selected_rules:
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)
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

    Returns:
        LogRewardResult with confirmation.
    """
    now = datetime.now(timezone.utc)
    reward_id = _generate_reward_id(outcome, now)
    reward_value = _compute_reward_value(outcome, revision_distance)

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

    rewards_path = _get_rewards_path(buildlog_dir)
    rewards_path.parent.mkdir(parents=True, exist_ok=True)
    with open(rewards_path, "a") as f:
        f.write(json.dumps(event.to_dict()) + "\n")

    if rules_active:
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.batch_update(
            rule_ids=rules_active,
            reward=reward_value,
            context=error_class or "general",
        )

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

    events: list[RewardEvent] = []
    for line in rewards_path.read_text().strip().split("\n"):
        if line:
            try:
                data = json.loads(line)
                events.append(RewardEvent.from_dict(data))
            except (json.JSONDecodeError, KeyError):
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
