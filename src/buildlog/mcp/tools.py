"""MCP tool implementations for buildlog.

These are thin wrappers around core operations.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Literal

from buildlog.core import (
    diff,
    end_session,
    get_experiment_report,
    get_rewards,
    get_session_metrics,
    learn_from_review,
    log_mistake,
    log_reward,
    promote,
    reject,
    start_session,
    status,
)


def _validate_skill_ids(skill_ids: list[str]) -> list[str]:
    """Filter out invalid skill IDs (empty strings, None, whitespace)."""
    return [sid for sid in skill_ids if sid and isinstance(sid, str) and sid.strip()]


def buildlog_status(
    buildlog_dir: str = "buildlog",
    min_confidence: Literal["low", "medium", "high"] = "low",
) -> dict:
    """Get current skills extracted from buildlog entries.

    Returns skills grouped by category with confidence scores.
    Use this to see what patterns have emerged from your work.

    Args:
        buildlog_dir: Path to buildlog directory (default: ./buildlog)
        min_confidence: Minimum confidence level to include

    Returns:
        Dictionary with skills by category and summary statistics
    """
    result = status(Path(buildlog_dir), min_confidence)
    return asdict(result)


def buildlog_promote(
    skill_ids: list[str],
    target: Literal["claude_md", "settings_json", "skill"] = "claude_md",
    buildlog_dir: str = "buildlog",
) -> dict:
    """Promote skills to your agent's rules.

    Writes selected skills to CLAUDE.md, .claude/settings.json, or
    .claude/skills/buildlog-learned/SKILL.md (Anthropic Agent Skills format).

    Args:
        skill_ids: List of skill IDs to promote (e.g., ["arch-b0fcb62a1e"])
        target: Where to write rules ("claude_md", "settings_json", or "skill")
        buildlog_dir: Path to buildlog directory

    Returns:
        Confirmation with promoted skills
    """
    validated_ids = _validate_skill_ids(skill_ids)
    result = promote(Path(buildlog_dir), validated_ids, target)
    return asdict(result)


def buildlog_reject(
    skill_ids: list[str],
    buildlog_dir: str = "buildlog",
) -> dict:
    """Mark skills as rejected so they won't be suggested again.

    Rejected skills are stored in .buildlog/rejected.json

    Args:
        skill_ids: List of skill IDs to reject
        buildlog_dir: Path to buildlog directory

    Returns:
        Confirmation with rejected skill IDs
    """
    validated_ids = _validate_skill_ids(skill_ids)
    result = reject(Path(buildlog_dir), validated_ids)
    return asdict(result)


def buildlog_diff(
    buildlog_dir: str = "buildlog",
) -> dict:
    """Show skills that haven't been promoted or rejected yet.

    Useful for seeing what's new since your last review.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dictionary with pending skills and counts
    """
    result = diff(Path(buildlog_dir))
    return asdict(result)


def buildlog_learn_from_review(
    issues: list[dict],
    source: str | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Capture learnings from code review feedback.

    Call this after a review loop completes to persist learnings.
    Each issue's rule_learned becomes a tracked learning that gains
    confidence through reinforcement.

    Args:
        issues: List of issues with structure:
            {
                "severity": "critical|major|minor|nitpick",
                "category": "architectural|workflow|tool_usage|domain_knowledge",
                "description": "What's wrong",
                "rule_learned": "Generalizable rule",
                "location": "file:line (optional)",
                "why_it_matters": "Why this matters (optional)",
                "functional_principle": "FP principle (optional)"
            }
        source: Optional identifier (e.g., "PR#13")
        buildlog_dir: Path to buildlog directory

    Returns:
        Result with new_learnings, reinforced_learnings, total processed

    Example:
        buildlog_learn_from_review(
            issues=[
                {
                    "severity": "critical",
                    "category": "architectural",
                    "description": "Score bounds not validated",
                    "rule_learned": "Validate invariants at function boundaries"
                }
            ],
            source="PR#13"
        )
    """
    result = learn_from_review(Path(buildlog_dir), issues, source)
    return asdict(result)


def buildlog_log_reward(
    outcome: str,
    rules_active: list[str] | None = None,
    revision_distance: float | None = None,
    error_class: str | None = None,
    notes: str | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Log a reward signal for bandit learning.

    Call this after agent work to provide feedback on the outcome.
    This enables learning which rules are effective in which contexts.

    Args:
        outcome: Type of feedback:
            - "accepted": Work was accepted as-is (reward=1.0)
            - "revision": Work needed changes (reward=1-distance)
            - "rejected": Work was rejected entirely (reward=0.0)
        rules_active: List of rule IDs that were in context during the work
        revision_distance: How much correction was needed (0-1, 0=minor tweak, 1=complete redo)
        error_class: Category of error if applicable (e.g., "missing_test", "validation_boundary")
        notes: Optional notes about the feedback
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with reward_id, reward_value, total_events

    Example:
        # Work was accepted
        buildlog_log_reward(outcome="accepted", rules_active=["arch-123", "wf-456"])

        # Work needed revision
        buildlog_log_reward(
            outcome="revision",
            revision_distance=0.3,
            error_class="missing_test",
            notes="Forgot to test error path"
        )

        # Work was rejected
        buildlog_log_reward(outcome="rejected", notes="Completely wrong approach")
    """
    # Validate outcome
    if outcome not in ("accepted", "revision", "rejected"):
        return {
            "reward_id": "",
            "reward_value": 0.0,
            "total_events": 0,
            "message": "",
            "error": f"Invalid outcome: {outcome}. Must be 'accepted', 'revision', or 'rejected'",
        }

    result = log_reward(
        Path(buildlog_dir),
        outcome=outcome,  # type: ignore[arg-type]
        rules_active=rules_active,
        revision_distance=revision_distance,
        error_class=error_class,
        notes=notes,
        source="mcp",
    )
    return asdict(result)


def buildlog_rewards(
    limit: int | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Get reward events with summary statistics.

    Returns recent reward events and aggregate statistics useful for
    understanding learning progress.

    Args:
        limit: Maximum number of events to return (most recent first)
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with:
            - total_events: Total count of reward events
            - accepted: Count of accepted outcomes
            - revisions: Count of revision outcomes
            - rejected: Count of rejected outcomes
            - mean_reward: Average reward value
            - events: List of recent events (limited)

    Example:
        buildlog_rewards(limit=10)  # Get 10 most recent events with stats
    """
    result = get_rewards(Path(buildlog_dir), limit)

    # Convert events to dicts
    return {
        "total_events": result.total_events,
        "accepted": result.accepted,
        "revisions": result.revisions,
        "rejected": result.rejected,
        "mean_reward": result.mean_reward,
        "events": [e.to_dict() for e in result.events],
    }


# -----------------------------------------------------------------------------
# Session Tracking MCP Tools (Experiment Infrastructure)
# -----------------------------------------------------------------------------


def buildlog_start_session(
    error_class: str | None = None,
    notes: str | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Start a new experiment session.

    Begins tracking for a learning experiment. Captures the current
    set of active rules to measure learning over time.

    Args:
        error_class: Error class being targeted (e.g., "missing_test")
        notes: Notes about this session
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with session_id, error_class, rules_count, message

    Example:
        buildlog_start_session(error_class="missing_test")
    """
    result = start_session(
        Path(buildlog_dir),
        error_class=error_class,
        notes=notes,
    )
    return asdict(result)


def buildlog_end_session(
    entry_file: str | None = None,
    notes: str | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """End the current experiment session.

    Finalizes the session and calculates metrics including:
    - Total mistakes logged
    - Repeated mistakes (from prior sessions)
    - Rules added during session

    Args:
        entry_file: Corresponding buildlog entry file, if any
        notes: Additional notes to append
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with session_id, duration_minutes, mistakes_logged,
        repeated_mistakes, rules_at_start, rules_at_end, message

    Example:
        buildlog_end_session(entry_file="2026-01-21.md")
    """
    result = end_session(
        Path(buildlog_dir),
        entry_file=entry_file,
        notes=notes,
    )
    return asdict(result)


def buildlog_log_mistake(
    error_class: str,
    description: str,
    corrected_by_rule: str | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Log a mistake during the current session.

    Records the mistake and checks if it's a repeat of a prior mistake
    (from earlier sessions). This enables measuring repeated-mistake rates.

    Args:
        error_class: Category of error (e.g., "missing_test")
        description: Description of the mistake
        corrected_by_rule: Rule ID that should have prevented this
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with mistake_id, session_id, was_repeat, similar_prior, message

    Example:
        buildlog_log_mistake(
            error_class="missing_test",
            description="Forgot to add unit tests for new helper function"
        )
    """
    result = log_mistake(
        Path(buildlog_dir),
        error_class=error_class,
        description=description,
        corrected_by_rule=corrected_by_rule,
    )
    return asdict(result)


def buildlog_session_metrics(
    session_id: str | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Get metrics for a session or all sessions.

    Returns mistake rates and rule changes for analysis.

    Args:
        session_id: Specific session ID, or None for aggregate metrics
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with session_id, total_mistakes, repeated_mistakes,
        repeated_mistake_rate, rules_at_start, rules_at_end, rules_added

    Example:
        buildlog_session_metrics()  # Aggregate metrics
        buildlog_session_metrics(session_id="session-20260121-140000")
    """
    result = get_session_metrics(
        Path(buildlog_dir),
        session_id=session_id,
    )
    return asdict(result)


def buildlog_experiment_report(
    buildlog_dir: str = "buildlog",
) -> dict:
    """Generate a comprehensive experiment report.

    Returns summary statistics, per-session breakdown, and error class analysis.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with:
            - summary: Overall statistics
            - sessions: Per-session breakdown
            - error_classes: Breakdown by error class

    Example:
        buildlog_experiment_report()
    """
    return get_experiment_report(Path(buildlog_dir))
