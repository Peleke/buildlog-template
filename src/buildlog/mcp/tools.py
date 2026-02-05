"""MCP tool implementations for buildlog.

These are thin wrappers around core operations.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Literal

from buildlog.core import (
    commit,
    create_entry,
    diff,
    end_session,
    gauntlet_generate,
    gauntlet_loop_config,
    generate_gauntlet_prompt,
    get_bandit_status,
    get_experiment_report,
    get_gauntlet_rules,
    get_overview,
    get_rewards,
    get_session_metrics,
    init_buildlog,
    learn_from_review,
    list_entries,
    log_mistake,
    log_reward,
    promote,
    reject,
    start_session,
    status,
    update_buildlog,
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
    """Promote selected skills to your agent's rule files.

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
    """Show skills pending promotion or rejection.

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
    """Extract and persist learnings from code review feedback.

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
    """Log outcome feedback for bandit learning (accepted/revision/rejected).

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
    """Start a tracked session with Thompson Sampling rule selection.

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
    """End the current session and calculate metrics.

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
    """Log a mistake during the current session for RMR tracking.

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
    """Get per-session or aggregate mistake rates and rule changes.

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
    """Generate comprehensive report: summary, sessions, error classes.

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
    """Get Thompson Sampling bandit state and rule rankings by context.

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
    """Process gauntlet issues and determine next action (fix/checkpoint/clean).

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
    """Accept risk for remaining issues, optionally create GitHub issues.

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


# -----------------------------------------------------------------------------
# Entry & Overview MCP Tools
# -----------------------------------------------------------------------------


def buildlog_gauntlet_rules(
    persona: str | None = None,
    format: str = "json",
    buildlog_dir: str = "buildlog",
) -> dict:
    """Load gauntlet reviewer rules. Call before reviewing code to get rules.

    Returns rules from curated reviewer personas (security_karen,
    test_terrorist, bragi, etc.) in the requested format.

    Args:
        persona: Filter to a specific persona, or None for all
        format: Output format (json, yaml, markdown)
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with formatted rules, total_rules, personas list
    """
    result = get_gauntlet_rules(persona=persona, format=format)
    return asdict(result)


def buildlog_overview(
    buildlog_dir: str = "buildlog",
) -> dict:
    """Get project buildlog state at a glance. Call at session start for context.

    Returns entry count, skill summary, active session, and render targets.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with entries, skills, active_session, render_targets
    """
    result = get_overview(Path(buildlog_dir))
    return asdict(result)


def buildlog_entry_new(
    slug: str,
    entry_date: str | None = None,
    quick: bool = False,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Create a new buildlog journal entry for documenting work.

    Creates a new dated entry from the template with slug sanitization.

    Args:
        slug: Short identifier (e.g., 'auth-api', 'bugfix-login')
        entry_date: Date in YYYY-MM-DD format, or None for today
        quick: Use short template if True
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with entry_path, entry_name, date_str, template_used, message

    Example:
        buildlog_entry_new(slug="auth-api")
        buildlog_entry_new(slug="bugfix", entry_date="2026-01-15", quick=True)
    """
    result = create_entry(
        Path(buildlog_dir),
        slug=slug,
        entry_date=entry_date,
        quick=quick,
    )
    return asdict(result)


def buildlog_entry_list(
    buildlog_dir: str = "buildlog",
) -> dict:
    """List all buildlog journal entries, most recent first.

    Returns entry names and titles extracted from first lines.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with entries list [{name, title}], count, message
    """
    result = list_entries(Path(buildlog_dir))
    return asdict(result)


# =============================================================================
# P0: Gauntlet loop tools
# =============================================================================


def buildlog_commit(
    message: str,
    slug: str | None = None,
    no_entry: bool = False,
    extra_args: list[str] | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Commit code and append commit block to today's buildlog entry.

    Wraps git commit and updates the buildlog journal. Call after making
    changes to record progress.

    Args:
        message: Commit message (passed as -m to git)
        slug: Entry slug (default: derived from branch name)
        no_entry: Skip buildlog entry update (just git commit)
        extra_args: Additional git commit args (e.g., ["--amend"])
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with commit_hash, commit_message, files_changed,
        entry_path, entry_updated, message, error
    """
    git_args = ["-m", message]
    if extra_args:
        git_args.extend(extra_args)

    result = commit(
        Path(buildlog_dir),
        git_args=git_args,
        slug=slug,
        no_entry=no_entry,
    )
    return asdict(result)


def buildlog_gauntlet_prompt(
    target: str,
    personas: list[str] | None = None,
) -> dict:
    """Generate a gauntlet review prompt for target code.

    Creates a prompt combining reviewer persona rules with a target path.
    Use this to kick off a gauntlet review: read the prompt, review the
    target code, then report issues via buildlog_gauntlet_issues.

    Args:
        target: Path to target code (file or directory, e.g., "src/")
        personas: Persona names to include (default: all)

    Returns:
        Dict with prompt, target, personas, total_rules, message, error
    """
    result = generate_gauntlet_prompt(target=target, personas=personas)
    return asdict(result)


def buildlog_gauntlet_loop(
    target: str,
    personas: list[str] | None = None,
    max_iterations: int = 10,
    stop_at: str = "minors",
    auto_gh_issues: bool = False,
) -> dict:
    """Start the gauntlet review loop: get config, rules, and instructions.

    Returns everything needed to run the review-fix-repeat loop.
    Workflow: call this -> review code -> buildlog_gauntlet_issues ->
    follow action -> buildlog_commit -> repeat.

    Args:
        target: Path to target code (e.g., "src/", "src/api.py")
        personas: Persona names (default: all)
        max_iterations: Max review-fix iterations (default: 10)
        stop_at: Stop after clearing: "criticals", "majors", or "minors"
        auto_gh_issues: Create GitHub issues for accepted risk items

    Returns:
        Dict with target, personas, max_iterations, stop_at, rules_by_persona,
        instructions, issue_format, prompt, message, error
    """
    result = gauntlet_loop_config(
        target=target,
        personas=personas,
        max_iterations=max_iterations,
        stop_at=stop_at,
        auto_gh_issues=auto_gh_issues,
    )
    return asdict(result)


# =============================================================================
# P1: Learning pipeline tools
# =============================================================================


def buildlog_distill(
    since: str | None = None,
    category: str | None = None,
    llm: bool = False,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Extract patterns from all buildlog entries.

    Parses the Improvements section of each entry and aggregates
    insights by category with statistics.

    Args:
        since: Only entries from this date onward (YYYY-MM-DD)
        category: Filter to one category (architectural, workflow,
                  tool_usage, domain_knowledge)
        llm: Use LLM for richer extraction
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with extracted_at, entry_count, patterns, statistics
    """
    from datetime import date as date_cls

    from buildlog.distill import distill_all

    since_date = None
    if since:
        try:
            since_date = date_cls.fromisoformat(since)
        except ValueError:
            return {
                "extracted_at": "",
                "entry_count": 0,
                "patterns": {},
                "statistics": {
                    "total_patterns": 0,
                    "by_category": {},
                    "by_month": {},
                },
                "error": (f"Invalid date format: {since}. Use YYYY-MM-DD."),
            }

    valid_categories = (
        "architectural",
        "workflow",
        "tool_usage",
        "domain_knowledge",
    )
    if category and category not in valid_categories:
        return {
            "extracted_at": "",
            "entry_count": 0,
            "patterns": {},
            "statistics": {
                "total_patterns": 0,
                "by_category": {},
                "by_month": {},
            },
            "error": (
                f"Invalid category: {category}."
                f" Must be one of: {', '.join(valid_categories)}"
            ),
        }

    dir_path = Path(buildlog_dir)
    if not dir_path.exists():
        return {
            "extracted_at": "",
            "entry_count": 0,
            "patterns": {},
            "statistics": {
                "total_patterns": 0,
                "by_category": {},
                "by_month": {},
            },
            "error": f"No buildlog directory found at {buildlog_dir}",
        }

    result = distill_all(dir_path, since=since_date, category_filter=category, llm=llm)
    return dict(result.to_dict())


def buildlog_skills(
    min_frequency: int = 1,
    since: str | None = None,
    llm: bool = False,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Generate agent-consumable skills from buildlog patterns.

    Transforms distilled patterns into actionable rules with deduplication,
    confidence scoring, and stable IDs. Foundation for promoting rules.

    Args:
        min_frequency: Only include skills seen at least N times
        since: Only entries from this date onward (YYYY-MM-DD)
        llm: Use LLM for extraction and scoring
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with generated_at, source_entries, total_skills, skills
    """
    from datetime import date as date_cls

    from buildlog.skills import generate_skills as gen_skills

    since_date = None
    if since:
        try:
            since_date = date_cls.fromisoformat(since)
        except ValueError:
            return {
                "generated_at": "",
                "source_entries": 0,
                "total_skills": 0,
                "skills": {},
                "error": (f"Invalid date format: {since}. Use YYYY-MM-DD."),
            }

    dir_path = Path(buildlog_dir)
    if not dir_path.exists():
        return {
            "generated_at": "",
            "source_entries": 0,
            "total_skills": 0,
            "skills": {},
            "error": f"No buildlog directory found at {buildlog_dir}",
        }

    skill_set = gen_skills(
        dir_path,
        min_frequency=min_frequency,
        since_date=since_date,
        llm=llm,
    )
    return dict(skill_set.to_dict())


def buildlog_stats(
    since: str | None = None,
    detailed: bool = False,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Show buildlog statistics and analytics.

    Provides insights on entry counts, improvement coverage,
    categories, streaks, and quality warnings.

    Args:
        since: Only entries from this date onward (YYYY-MM-DD)
        detailed: Include top sources breakdown
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with entries, insights, top_sources, pipeline,
        streak, warnings
    """
    from datetime import date as date_cls

    from buildlog.stats import calculate_stats, stats_to_dict

    since_date = None
    if since:
        try:
            since_date = date_cls.fromisoformat(since)
        except ValueError:
            return {"error": (f"Invalid date format: {since}. Use YYYY-MM-DD.")}

    dir_path = Path(buildlog_dir)
    if not dir_path.exists():
        return {"error": f"No buildlog directory found at {buildlog_dir}"}

    stats_result = calculate_stats(dir_path, since_date=since_date)
    result: dict = dict(stats_to_dict(stats_result))

    if not detailed:
        result["top_sources"] = []

    return result


def buildlog_gauntlet_list_personas(
    buildlog_dir: str = "buildlog",
) -> dict:
    """List available gauntlet reviewer personas and rule counts.

    Shows all reviewer personas from seed files. Use to discover
    what review perspectives are available before running a gauntlet.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with personas, total_rules, total_personas
    """
    from buildlog.seeds import get_default_seeds_dir, load_all_seeds

    seeds_dir = get_default_seeds_dir()

    if seeds_dir is None:
        return {
            "personas": {},
            "total_rules": 0,
            "total_personas": 0,
            "error": ("No seed files found." " Check your buildlog installation."),
        }

    seeds = load_all_seeds(seeds_dir)

    if not seeds:
        return {
            "personas": {},
            "total_rules": 0,
            "total_personas": 0,
            "error": "No seed files found in seeds directory.",
        }

    personas_info = {
        name: {
            "rules_count": len(sf.rules),
            "version": sf.version,
        }
        for name, sf in seeds.items()
    }

    return {
        "personas": personas_info,
        "total_rules": sum(len(sf.rules) for sf in seeds.values()),
        "total_personas": len(seeds),
    }


# =============================================================================
# P2: Nice-to-have tools
# =============================================================================


def buildlog_gauntlet_generate(
    source_text: str,
    persona: str,
    output_dir: str | None = None,
    dry_run: bool = False,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Generate seed rules from source text using LLM extraction.

    Runs the seed engine pipeline to produce a YAML seed file
    from arbitrary source content (docs, notes, standards).

    Args:
        source_text: The text content to extract rules from
        persona: Persona name for the seed file
        output_dir: Output dir for seed YAML (default: .buildlog/seeds)
        dry_run: Preview without writing to disk
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with persona, rule_count, output_path, preview, message
    """
    out = Path(output_dir) if output_dir else Path(buildlog_dir) / ".buildlog" / "seeds"
    result = gauntlet_generate(
        source_text=source_text,
        persona=persona,
        output_dir=out,
        dry_run=dry_run,
    )
    return asdict(result)


def buildlog_migrate(
    dry_run: bool = False,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Migrate legacy JSON/JSONL files to the global SQLite database.

    Moves per-project data from buildlog/.buildlog/*.json(l) files into
    ~/.buildlog/buildlog.db.  Original files are renamed to *.migrated
    (not deleted).  Safe to run multiple times — idempotent.

    Args:
        dry_run: If True, show what would happen without writing anything.
        buildlog_dir: Path to buildlog directory.

    Returns:
        Dict with lines (migration log) and summary.

    Example:
        buildlog_migrate(dry_run=True)  # Preview
        buildlog_migrate()              # Run it
    """
    from buildlog.storage.migrate import migrate_project

    lines = migrate_project(
        Path(buildlog_dir),
        dry_run=dry_run,
    )
    return {
        "lines": lines,
        "summary": lines[-1] if lines else "Nothing to do.",
    }


def buildlog_export(
    format: str = "jsonl",
    output: str | None = None,
    project: str | None = None,
    tables: str | None = None,
    buildlog_dir: str = "buildlog",
) -> dict:
    """Export data from the storage backend to files.

    Writes event data (rewards, sessions, mistakes) to JSONL files.
    Can export a single project or all projects at once.

    Args:
        format: Output format (currently only 'jsonl').
        output: Directory to write files into.  None = return as string.
        project: Limit to a specific project ID.  None = current project
            (or all if global DB).
        tables: Comma-separated table names (e.g., "rewards,sessions").
            None = all tables.
        buildlog_dir: Path to buildlog directory.

    Returns:
        Dict with summary message and export details.

    Example:
        buildlog_export(tables="rewards,sessions")
        buildlog_export(output="./backup/")
    """
    from buildlog.storage import get_backend
    from buildlog.storage.exporters import JsonlExporter

    backend, project_id = get_backend(Path(buildlog_dir))

    table_list = [t.strip() for t in tables.split(",")] if tables else None
    output_path = Path(output) if output else None
    pid = project or project_id

    exporter = JsonlExporter()
    summary = exporter.export(
        backend, project_id=pid, output_path=output_path, tables=table_list
    )

    return {
        "format": format,
        "project_id": pid,
        "tables": table_list or ["rewards", "sessions", "mistakes"],
        "output": str(output_path) if output_path else None,
        "summary": summary,
    }


def buildlog_init(
    defaults: bool = True,
    no_claude_md: bool = False,
    no_mcp: bool = False,
) -> dict:
    """Initialize buildlog in the current project directory.

    Sets up buildlog/ with templates, optionally updates CLAUDE.md,
    and registers the MCP server. Always runs non-interactively.

    Args:
        defaults: Use default values (always True for MCP)
        no_claude_md: Don't update CLAUDE.md
        no_mcp: Don't register MCP server

    Returns:
        Dict with initialized, buildlog_dir, claude_md_updated,
        mcp_registered, message, error
    """
    result = init_buildlog(
        project_dir=Path("."),
        defaults=True,
        no_claude_md=no_claude_md,
        no_mcp=no_mcp,
    )
    return asdict(result)


def buildlog_update() -> dict:
    """Update buildlog templates to the latest version.

    Runs copier update to pull the latest template changes.
    Requires buildlog to have been initialized first.

    Returns:
        Dict with updated, message, error
    """
    result = update_buildlog(project_dir=Path("."))
    return asdict(result)
