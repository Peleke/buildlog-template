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
    get_bandit_status,
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
    target: str = "claude_md",
    buildlog_dir: str = "buildlog",
) -> dict:
    """Promote skills to your agent's rules.

    Writes selected skills to agent-specific rule files.

    Args:
        skill_ids: List of skill IDs to promote (e.g., ["arch-b0fcb62a1e"])
        target: Where to write rules. One of: claude_md, settings_json,
            skill, cursor, copilot, windsurf, continue_dev.
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


def buildlog_experiment_start(
    error_class: str | None = None,
    notes: str | None = None,
    select_k: int = 3,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Start a new experiment session with Thompson Sampling rule selection.

    Begins tracking for a learning experiment. Uses Thompson Sampling
    to select which rules will be "active" for this session based on
    the error class context.

    The selected rules will receive feedback:
    - Negative feedback (reward=0) when log_mistake() is called
    - Explicit feedback when log_reward() is called

    This teaches the bandit which rules are effective for which contexts.

    Args:
        error_class: Error class being targeted (e.g., "missing_test").
                    This is the CONTEXT for contextual bandits.
        notes: Notes about this session
        select_k: Number of rules to select via Thompson Sampling
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with session_id, error_class, rules_count, selected_rules, message

    Example:
        buildlog_start_session(error_class="type-errors", select_k=5)
    """
    result = start_session(
        Path(buildlog_dir),
        error_class=error_class,
        notes=notes,
        select_k=select_k,
    )
    return asdict(result)


def buildlog_experiment_end(
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


def buildlog_experiment_metrics(
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


def buildlog_bandit_status(
    buildlog_dir: str = "buildlog",
    context: str | None = None,
    top_k: int = 10,
) -> dict:
    """Get Thompson Sampling bandit status and rule rankings.

    Shows the bandit's learned beliefs about which rules are effective
    for each error class context. Higher mean = bandit believes rule
    is more effective.

    The bandit uses Beta distributions to model uncertainty:
    - High variance (wide CI) = uncertain, will explore more
    - Low variance (narrow CI) = confident, will exploit

    Args:
        buildlog_dir: Path to buildlog directory
        context: Specific error class to filter by (optional)
        top_k: Number of top rules to show per context

    Returns:
        Dict with:
            - summary: Total contexts, arms, observations
            - top_rules: Best rules per context by expected value
            - all_rules: Full stats if filtering by context

    Example:
        # See all bandit state
        buildlog_bandit_status()

        # See state for specific error class
        buildlog_bandit_status(context="type-errors")
    """
    return get_bandit_status(Path(buildlog_dir), context, top_k)


# -----------------------------------------------------------------------------
# Gauntlet Loop MCP Tools
# -----------------------------------------------------------------------------


def buildlog_gauntlet_issues(
    issues: list[dict],
    iteration: int = 1,
    source: str | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Process gauntlet review issues and determine next action.

    Call this after running a gauntlet review. It categorizes issues by
    severity, persists learnings, and returns the appropriate next action.

    Args:
        issues: List of issues from the gauntlet review, each with:
            {
                "severity": "critical|major|minor|nitpick",
                "category": "security|testing|architectural|...",
                "description": "What's wrong",
                "rule_learned": "Generalizable rule",
                "location": "file:line (optional)"
            }
        iteration: Current iteration number (for tracking loops)
        source: Optional source identifier for learnings
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with:
            - action: What to do next:
                - "fix_criticals": Criticals remain, auto-fix and loop
                - "checkpoint_majors": No criticals, majors remain (ask user)
                - "checkpoint_minors": Only minors remain (ask user)
                - "clean": No issues remain
            - criticals: List of critical issues
            - majors: List of major issues
            - minors: List of minor/nitpick issues
            - iteration: Current iteration number
            - learnings_persisted: Number of learnings saved
            - message: Human-readable summary

    Example:
        # After running gauntlet review
        result = buildlog_gauntlet_issues(
            issues=[
                {"severity": "critical", "category": "security", ...},
                {"severity": "major", "category": "testing", ...},
            ],
            iteration=1
        )
        # result["action"] tells you what to do next
    """
    from buildlog.core import gauntlet_process_issues

    result = gauntlet_process_issues(
        Path(buildlog_dir),
        issues=issues,
        iteration=iteration,
        source=source,
    )
    return asdict(result)


def buildlog_gauntlet_accept_risk(
    remaining_issues: list[dict],
    create_github_issues: bool = False,
    repo: str | None = None,
) -> dict:
    """Accept risk for remaining issues, optionally creating GitHub issues.

    Call this when the user decides to accept remaining issues as risk
    (e.g., only minors remain and they want to move on).

    Args:
        remaining_issues: Issues being accepted as risk
        create_github_issues: Whether to create GitHub issues for tracking
        repo: Repository for GitHub issues (uses current repo if None)

    Returns:
        Dict with:
            - accepted_issues: Number of issues accepted
            - github_issues_created: Number of GitHub issues created
            - github_issue_urls: URLs of created issues
            - message: Human-readable summary
            - error: Error message if GitHub issue creation failed

    Example:
        # User accepts risk with minors, wants GitHub issues
        result = buildlog_gauntlet_accept_risk(
            remaining_issues=[...],
            create_github_issues=True
        )
    """
    from buildlog.core import gauntlet_accept_risk

    result = gauntlet_accept_risk(
        remaining_issues=remaining_issues,
        create_github_issues=create_github_issues,
        repo=repo,
    )
    return asdict(result)
