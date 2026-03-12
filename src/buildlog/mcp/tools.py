"""MCP tool implementations for buildlog.

These are thin wrappers around core operations.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Literal

from buildlog.constants import DEFAULT_BUILDLOG_DIR
from buildlog.core import (
    commit,
    create_entry,
    diff,
    end_session,
    gauntlet_generate,
    gauntlet_loop_config,
    gauntlet_rule_lookup,
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
    verify_workflow,
)


def _ensure_message(d: dict) -> dict:
    """Return a copy of *d* with a non-empty ``message`` for MCP display.

    Falls back to ``error`` when ``message`` is empty/missing.
    The error string is used as-is since MCP consumers are local agents
    (not end-user UIs), so path information is acceptable.
    """
    if not d.get("message") and d.get("error"):
        out = dict(d)
        out["message"] = out["error"]
        return out
    return d


def _project_root(buildlog_dir: str) -> Path:
    """Derive the project root from the buildlog directory path.

    The MCP server's cwd may differ from the user's project directory.
    Since ``buildlog_dir`` is always relative to or inside the project
    root, we resolve it and take its parent.
    """
    return Path(buildlog_dir).resolve().parent


def _validate_skill_ids(skill_ids: list[str]) -> list[str]:
    """Filter out invalid skill IDs (empty strings, None, whitespace)."""
    return [sid for sid in skill_ids if sid and isinstance(sid, str) and sid.strip()]


def _resolve_file_or_inline(
    inline: list[dict] | None,
    file_path: str | None,
    param_name: str,
) -> list[dict]:
    """Resolve a list[dict] param from either inline value or a JSON file.

    Exactly one of *inline* or *file_path* must be provided.

    Raises:
        ValueError: Both or neither provided, or JSON decode fails.
        FileNotFoundError: File path doesn't exist.
    """
    import json as _json

    if inline is not None and file_path is not None:
        raise ValueError(
            f"Provide either '{param_name}' or '{param_name}_file', not both."
        )
    if inline is None and file_path is None:
        raise ValueError(
            f"Provide either '{param_name}' (inline) or '{param_name}_file' (path)."
        )
    if file_path is not None:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        data = _json.loads(p.read_text())
        if not isinstance(data, list):
            raise ValueError(
                f"Expected JSON array in {file_path}, got {type(data).__name__}"
            )
        return data
    return inline  # type: ignore[return-value]


def _resolve_text_file_or_inline(
    inline: str | None,
    file_path: str | None,
    param_name: str,
) -> str:
    """Resolve a str param from either inline value or a text file.

    Exactly one of *inline* or *file_path* must be provided.

    Raises:
        ValueError: Both or neither provided.
        FileNotFoundError: File path doesn't exist.
    """
    if inline is not None and file_path is not None:
        raise ValueError(
            f"Provide either '{param_name}' or '{param_name}_file', not both."
        )
    if inline is None and file_path is None:
        raise ValueError(
            f"Provide either '{param_name}' (inline) or '{param_name}_file' (path)."
        )
    if file_path is not None:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        return p.read_text()
    return inline  # type: ignore[return-value]


def buildlog_status(
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
    min_confidence: Literal["low", "medium", "high"] = "low",
) -> dict:
    """Need to decide which learned rules to promote or reject?

    Call after buildlog_skills() has run at least once. Returns a dict
    with 4 category keys (architectural, workflow, tool_usage,
    domain_knowledge), each containing 0-20 skill objects with id, rule,
    confidence, frequency. Response: ~500-2000 tokens. If empty, no
    skills exist yet — run buildlog_skills() first.

    Args:
        buildlog_dir: Path to buildlog directory (default: ./buildlog)
        min_confidence: Minimum confidence level to include

    Returns:
        Dict with skills_by_category, promoted_ids, rejected_ids, total_skills
    """
    result = status(Path(buildlog_dir), min_confidence)
    return _ensure_message(asdict(result))


def buildlog_promote(
    skill_ids: list[str],
    target: str = "claude_md",
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """A skill scored high in buildlog_status() and you want it enforced permanently?

    Call this to write 1+ skill IDs into the agent's rule file (CLAUDE.md,
    .cursorrules, etc.). Returns a confirmation dict with skills_promoted
    count and target file path. Response: ~200 tokens. Idempotent —
    re-promoting an already-promoted skill is a no-op.

    Args:
        skill_ids: List of skill IDs to promote (e.g., ["arch-b0fcb62a1e"])
        target: Where to write rules. One of: claude_md, settings_json,
            skill, cursor, copilot, windsurf, continue_dev.
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with skills_promoted, target_path, message
    """
    validated_ids = _validate_skill_ids(skill_ids)
    result = promote(Path(buildlog_dir), validated_ids, target)
    return _ensure_message(asdict(result))


def buildlog_reject(
    skill_ids: list[str],
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """A skill from buildlog_status() is wrong or noisy and should never surface again?

    Call this with 1+ skill IDs. Writes them to .buildlog/rejected.json so
    future buildlog_skills() and buildlog_status() runs exclude them.
    Returns a dict with rejected_ids list. Response: ~100 tokens.

    Args:
        skill_ids: List of skill IDs to reject
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with rejected_ids, message
    """
    validated_ids = _validate_skill_ids(skill_ids)
    result = reject(Path(buildlog_dir), validated_ids)
    return _ensure_message(asdict(result))


def buildlog_diff(
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """After running buildlog_skills(), need to see only skills you haven't decided on?

    Call this instead of buildlog_status() to get just the pending queue.
    Returns a dict with pending_skills list (each with id, rule, category,
    confidence) and counts: pending, promoted, rejected. Response: ~200-800
    tokens. If pending is 0, all skills have been triaged.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with pending_skills, pending, promoted, rejected counts
    """
    result = diff(Path(buildlog_dir))
    return _ensure_message(asdict(result))


def buildlog_learn_from_review(
    issues: list[dict] | None = None,
    source: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
    issues_file: str | None = None,
) -> dict:
    """Got code review feedback from a non-gauntlet source (PR review, manual audit)?

    Call this after the review to persist each issue's rule_learned as a
    tracked learning. Pass 1-50 issues inline or via JSON file. Returns a
    dict with new_learnings count, reinforced_learnings count,
    total_issues_processed. Response: ~300 tokens. For gauntlet reviews,
    use buildlog_gauntlet_issues() instead — it calls this internally.

    Provide issues inline OR via a JSON file path (not both).

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
        issues_file: Path to a JSON file containing the issues array.
            Mutually exclusive with 'issues'.

    Returns:
        Dict with new_learnings, reinforced_learnings, total_issues_processed

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
        # Or via file:
        buildlog_learn_from_review(issues_file="/tmp/issues.json", source="PR#13")
    """
    try:
        resolved = _resolve_file_or_inline(issues, issues_file, "issues")
    except (ValueError, FileNotFoundError) as exc:
        return {
            "new_learnings": [],
            "reinforced_learnings": [],
            "total_issues_processed": 0,
            "source": source,
            "message": "",
            "error": str(exc),
        }

    result = learn_from_review(Path(buildlog_dir), resolved, source)
    return _ensure_message(asdict(result))


def buildlog_log_reward(
    outcome: str,
    rules_active: list[str] | None = None,
    revision_distance: float | None = None,
    error_class: str | None = None,
    notes: str | None = None,
    session_id: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """PR merged or work reviewed? Close the feedback loop.

    Call this after a gauntlet review cycle completes and the user
    approves/rejects the work. Reads gauntlet-credited rules automatically
    (from last_gauntlet_credits.json), so rules_active is usually omitted.
    Updates Thompson Sampling posteriors for credited rules. Response: ~150
    tokens with reward_id, reward_value, total_events.

    Args:
        outcome: Type of feedback:
            - "accepted": Work was accepted as-is (reward=1.0)
            - "revision": Work needed changes (reward=1-distance)
            - "rejected": Work was rejected entirely (reward=0.0)
        rules_active: List of rule IDs that were in context during the work.
            Auto-reads from gauntlet credits if omitted.
        revision_distance: How much correction was needed (0-1, 0=minor tweak, 1=complete redo)
        error_class: Category of error if applicable (e.g., "missing_test", "validation_boundary")
        notes: Optional notes about the feedback
        session_id: Session to associate this reward with. Auto-detects active session if omitted.
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with reward_id, reward_value, total_events

    Example:
        # Work was accepted
        buildlog_log_reward(outcome="accepted")

        # Work needed revision
        buildlog_log_reward(outcome="revision", revision_distance=0.3)

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
        session_id=session_id,
    )
    return _ensure_message(asdict(result))


def buildlog_rewards(
    limit: int = 50,
    session_id: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Check reward history before deciding whether to adjust rules or run another review.

    Returns recent reward events and aggregate statistics. Response: ~200-1500
    tokens depending on limit (default 50 events). Each event includes
    outcome, reward_value, rules_active, timestamp. Summary includes
    total_events, accepted/revision/rejected counts, mean_reward.

    Args:
        limit: Maximum number of events to return (most recent first).
            Defaults to 50 to stay within MCP token limits.
            Pass 0 for all events (caution: may be large).
        session_id: Filter rewards to this session only
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with total_events, accepted, revisions, rejected,
        mean_reward, events list

    Example:
        buildlog_rewards(limit=10)  # Get 10 most recent events with stats
        buildlog_rewards(session_id="2026-02-06-auth")  # Session-specific
    """
    result = get_rewards(Path(buildlog_dir), limit or None, session_id=session_id)

    # Convert events to dicts
    return _ensure_message(
        {
            "total_events": result.total_events,
            "accepted": result.accepted,
            "revisions": result.revisions,
            "rejected": result.rejected,
            "mean_reward": result.mean_reward,
            "events": [e.to_dict() for e in result.events],
            "message": f"{result.total_events} events (mean reward: {result.mean_reward:.2f})",
        }
    )


# -----------------------------------------------------------------------------
# Session Tracking MCP Tools (Experiment Infrastructure)
# -----------------------------------------------------------------------------


def buildlog_experiment_start(
    error_class: str | None = None,
    notes: str | None = None,
    select_k: int = 0,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """OPTIONAL. Beginning a focused work block to measure mistake rates?

    Call at the start of a coding session to get Thompson Sampling rule
    selection. Pass error_class (e.g., "missing_test") and select_k (e.g., 5).
    Returns session_id, selected_rules list, rules_count. Response: ~300
    tokens. Must pair with buildlog_experiment_end() to finalize metrics.

    Most workflows DON'T need this — buildlog_gauntlet_loop() and
    buildlog_log_reward() work without an active session. Only use this
    for longitudinal mistake-rate tracking.

    Args:
        error_class: Error class being targeted (e.g., "missing_test").
                    This is the CONTEXT for contextual bandits.
        notes: Notes about this session
        select_k: Number of rules to select via Thompson Sampling
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with session_id, error_class, rules_count, selected_rules, message

    Example:
        buildlog_experiment_start(error_class="type-errors", select_k=5)
    """
    result = start_session(
        Path(buildlog_dir),
        error_class=error_class,
        notes=notes,
        select_k=select_k,
    )
    return _ensure_message(asdict(result))


def buildlog_experiment_end(
    entry_file: str | None = None,
    notes: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Done with the session started by buildlog_experiment_start()?

    Call this to finalize it. Calculates duration_minutes, mistakes_logged,
    repeated_mistakes, rules_at_start vs rules_at_end. Returns a single dict.
    Response: ~250 tokens. Fails if no session is active. After this, use
    buildlog_experiment_metrics() to query stored results.

    Args:
        entry_file: Corresponding buildlog entry file, if any
        notes: Additional notes to append
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with session_id, duration_minutes, mistakes_logged,
        repeated_mistakes, rules_at_start, rules_at_end, message

    Example:
        buildlog_experiment_end(entry_file="2026-01-21.md")
    """
    result = end_session(
        Path(buildlog_dir),
        entry_file=entry_file,
        notes=notes,
    )
    return _ensure_message(asdict(result))


def buildlog_log_mistake(
    error_class: str,
    description: str,
    corrected_by_rule: str | None = None,
    related_concepts: list[str] | None = None,
    relation_to_prior: dict | None = None,
    resolution_action: str | None = None,
    context: str | None = None,
    severity: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Agent just made or caught a mistake? Log it for repeat-detection.

    Call immediately with error_class and description. Checks the mistake
    DB for prior occurrences and flags repeats. Works with or without an
    active session (generates synthetic session ID if none). Returns
    mistake_id, was_repeat (bool), similar_prior (null or prior mistake_id).
    Response: ~200 tokens.

    Args:
        error_class: Category of error (e.g., "missing_test")
        description: Description of the mistake
        corrected_by_rule: Rule ID that should have prevented this
        related_concepts: Concept names involved in this mistake
            (e.g., ["schema_migration", "backwards_compat"])
        relation_to_prior: Link to a prior mistake:
            {"id": "mistake-xxx", "type": "escalation|same_pattern|regression|caused_by|part_of"}
        resolution_action: What fixed the mistake (free text)
        context: What the agent was doing (free text)
        severity: Severity level: "low", "medium", "high", or "critical"
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with mistake_id, session_id, was_repeat, similar_prior, message

    Example:
        buildlog_log_mistake(
            error_class="missing_test",
            description="Forgot to add unit tests for new helper function",
            severity="medium",
        )
    """
    result = log_mistake(
        Path(buildlog_dir),
        error_class=error_class,
        description=description,
        corrected_by_rule=corrected_by_rule,
        related_concepts=related_concepts,
        relation_to_prior=relation_to_prior,
        resolution_action=resolution_action,
        context=context,
        severity=severity,
    )
    return _ensure_message(asdict(result))


def buildlog_experiment_metrics(
    session_id: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Need the repeated-mistake rate (RMR) for one specific session?

    Call with a session_id after buildlog_experiment_end(). Returns a single
    dict: total_mistakes, repeated_mistakes, repeated_mistake_rate (float
    0-1), rules_at_start, rules_at_end, rules_added. Response: ~200 tokens.
    For a cross-session summary with error-class breakdowns, use
    buildlog_experiment_report() instead.

    Args:
        session_id: Specific session ID, or None for aggregate metrics
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with session_id, total_mistakes, repeated_mistakes,
        repeated_mistake_rate, rules_at_start, rules_at_end, rules_added

    Example:
        buildlog_experiment_metrics(session_id="session-20260121-140000")
    """
    result = get_session_metrics(
        Path(buildlog_dir),
        session_id=session_id,
    )
    return _ensure_message(asdict(result))


def buildlog_experiment_report(
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Need a cross-session view to see if mistake rates are trending down?

    Call after 2+ sessions have been completed via buildlog_experiment_end().
    Returns a dict with 3 keys: summary (aggregate stats), sessions (list of
    per-session dicts), error_classes (dict keyed by error_class with counts).
    Response: ~500-5000 tokens depending on session count. For a single
    session, use buildlog_experiment_metrics(session_id=...) instead.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with summary, sessions list, error_classes breakdown

    Example:
        buildlog_experiment_report()
    """
    return get_experiment_report(Path(buildlog_dir))


def buildlog_bandit_status(
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
    context: str | None = None,
    top_k: int = 10,
) -> dict:
    """Which rules does the bandit consider most effective right now?

    Call before buildlog_experiment_start() or after several reward cycles
    to see learned beliefs. Returns summary (total contexts, arms,
    observations) and top_rules (top_k per context, each with mean,
    variance, alpha, beta). Response: ~500-3000 tokens depending on
    context count. Pass context="missing_test" to filter to one error class.

    Args:
        buildlog_dir: Path to buildlog directory
        context: Specific error class to filter by (optional)
        top_k: Number of top rules to show per context

    Returns:
        Dict with summary, top_rules per context, all_rules (if filtered)

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
    issues: list[dict] | None = None,
    iteration: int = 1,
    source: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
    issues_file: str | None = None,
    valid_rule_ids: list[str] | None = None,
) -> dict:
    """Just finished reviewing code against gauntlet rules? Submit findings here.

    Call after each review iteration with the issues you found. Returns
    the next action: "fix_criticals" (auto-fix and loop), "checkpoint_majors"
    (ask user), "checkpoint_minors" (ask user), or "clean" (done). Also
    persists learnings, validates rule citations, and credits rules for
    the feedback loop. Response: ~500-2000 tokens depending on issue count.

    Provide issues inline OR via a JSON file path (not both).

    Args:
        issues: List of issues from the gauntlet review, each with:
            {
                "severity": "critical|major|minor|nitpick",
                "category": "security|testing|architectural|...",
                "description": "What's wrong",
                "rule_learned": "Generalizable rule",
                "location": "file:line (optional)",
                "rules_consulted": ["rule_id", ...] (optional),
                "rule_reasoning": {"rule_id": "how it applies"} (optional)
            }
        iteration: Current iteration number (for tracking loops)
        source: Optional source identifier for learnings
        buildlog_dir: Path to buildlog directory
        issues_file: Path to a JSON file containing the issues array.
            Mutually exclusive with 'issues'.
        valid_rule_ids: List of valid rule IDs for citation validation.
            Pass the valid_rule_ids from buildlog_gauntlet_loop().
            Hallucinated IDs are stripped and logged as mistakes.

    Returns:
        Dict with action, criticals list, majors list, minors list,
        iteration, learnings_persisted, rules_credited, citation_stats

    Example:
        result = buildlog_gauntlet_issues(
            issues=[{"severity": "critical", "category": "security", ...}],
            iteration=1,
            valid_rule_ids=["security_karen:rule:0"]
        )
        # result["action"] tells you what to do next
    """
    try:
        resolved = _resolve_file_or_inline(issues, issues_file, "issues")
    except (ValueError, FileNotFoundError) as exc:
        return {
            "action": "",
            "criticals": [],
            "majors": [],
            "minors": [],
            "iteration": iteration,
            "learnings_persisted": 0,
            "rules_credited": [],
            "citation_stats": {},
            "message": "",
            "error": str(exc),
        }

    from buildlog.core import gauntlet_process_issues

    result = gauntlet_process_issues(
        Path(buildlog_dir),
        issues=resolved,
        iteration=iteration,
        source=source,
        valid_rule_ids=set(valid_rule_ids) if valid_rule_ids else None,
    )

    # --- Emit full issue detail (including rule_reasoning) for downstream ---
    # The agent doesn't need rule_reasoning in the CLI response, but qortex
    # and other consumers want it. Emit before compacting.
    try:
        from buildlog.emissions import emit_artifact
        from buildlog.storage import get_backend

        _, project_id = get_backend()
        emit_artifact(
            artifact={
                "iteration": iteration,
                "issues": resolved,
                "action": result.action,
                "rules_credited": result.rules_credited,
                "sampling_delta": result.sampling_delta,
            },
            artifact_type="gauntlet_review",
            project_id=project_id,
        )
    except Exception:
        pass  # fire-and-forget

    # --- Compact response: strip per-issue bulk, keep decision-relevant data ---
    d = asdict(result)
    for key in ("criticals", "majors", "minors"):
        d[key] = [
            {
                "severity": iss.get("severity"),
                "category": iss.get("category"),
                "description": iss.get("description", ""),
                "location": iss.get("location", ""),
            }
            for iss in d.get(key, [])
        ]

    return _ensure_message(d)


def buildlog_gauntlet_accept_risk(
    remaining_issues: list[dict] | None = None,
    create_github_issues: bool = False,
    repo: str | None = None,
    issues_file: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Gauntlet returned "checkpoint_minors" or "checkpoint_majors" and user says "ship it"?

    Call this with the remaining_issues array from the last
    buildlog_gauntlet_issues() response. This is the exit ramp from the
    gauntlet loop. Optionally set create_github_issues=True to file
    tracking issues. Returns accepted_issues count, github_issue_urls list.
    Response: ~300 tokens.

    Provide remaining_issues inline OR via a JSON file path (not both).

    Args:
        remaining_issues: Issues being accepted as risk
        create_github_issues: Whether to create GitHub issues for tracking
        repo: Repository for GitHub issues (uses current repo if None)
        issues_file: Path to a JSON file containing the issues array.
            Mutually exclusive with 'remaining_issues'.

    Returns:
        Dict with accepted_issues, github_issues_created,
        github_issue_urls, message

    Example:
        buildlog_gauntlet_accept_risk(
            remaining_issues=[...],
            create_github_issues=True
        )
    """
    try:
        resolved = _resolve_file_or_inline(
            remaining_issues, issues_file, "remaining_issues"
        )
    except (ValueError, FileNotFoundError) as exc:
        return {
            "accepted_issues": 0,
            "github_issues_created": 0,
            "github_issue_urls": [],
            "message": "",
            "error": str(exc),
        }

    from buildlog.core import gauntlet_accept_risk

    result = gauntlet_accept_risk(
        remaining_issues=resolved,
        create_github_issues=create_github_issues,
        repo=repo,
        cwd=str(_project_root(buildlog_dir)) if buildlog_dir else None,
        buildlog_dir=Path(buildlog_dir) if buildlog_dir else None,
    )
    return _ensure_message(asdict(result))


# -----------------------------------------------------------------------------
# Entry & Overview MCP Tools
# -----------------------------------------------------------------------------


def buildlog_gauntlet_rules(
    persona: str | None = None,
    format: str = "json",
    compact: bool = True,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Need the raw rule set for a manual review (not using the gauntlet loop)?

    Call before reviewing code manually. Returns formatted rules, total_rules,
    personas list. WARNING: Full response is 2000-8000 tokens with all
    personas. Use compact=True (default) and persona="security_karen" to
    constrain. For the automated loop workflow, use buildlog_gauntlet_loop()
    instead — it loads rules internally.

    Args:
        persona: Filter to a specific persona, or None for all
        format: Output format (json, yaml, markdown)
        compact: If True (default), return only id + rule + category
            per rule. Set False for full fields (context, antipattern,
            rationale, tags). Compact keeps responses under token limits.
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with formatted_rules, total_rules, personas list
    """
    result = get_gauntlet_rules(persona=persona, format=format, compact=compact)
    return _ensure_message(asdict(result))


def buildlog_overview(
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Starting a new conversation? Call this first, once, to orient.

    Returns entry_count (int), skill_count (int), active_session (null or
    session_id), render_targets (list of configured output targets).
    Response: ~200 tokens. Tells you whether a session is already active
    (don't call experiment_start again) and whether skills exist (can skip
    buildlog_skills()).

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with entry_count, skill_count, active_session, render_targets
    """
    result = get_overview(Path(buildlog_dir))
    return _ensure_message(asdict(result))


def buildlog_entry_new(
    slug: str,
    entry_date: str | None = None,
    quick: bool = False,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Starting work on a new feature? Create a journal file before your first commit.

    Call once per task with a slug (e.g., "auth-api"). Creates
    buildlog/YYYY-MM-DD-{slug}.md from template. Returns entry_path,
    entry_name. Response: ~200 tokens. Idempotent — returns existing entry
    if slug+date already exists. Use quick=True for a minimal template.

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
    return _ensure_message(asdict(result))


def buildlog_entry_list(
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Need to find a specific past entry or the full entry list?

    Returns entries (list of {name, title} objects, most recent first)
    and count. Response: ~100 tokens per entry, unbounded — 50 entries =
    ~5000 tokens. No pagination. For just the count, use
    buildlog_overview() instead.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with entries list [{name, title}], count, message
    """
    result = list_entries(Path(buildlog_dir))
    return _ensure_message(asdict(result))


# =============================================================================
# P0: Gauntlet loop tools
# =============================================================================


def buildlog_commit(
    message: str,
    slug: str | None = None,
    no_entry: bool = False,
    extra_args: list[str] | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Files staged and ready? Commit and log to today's buildlog entry.

    Call instead of raw git commit. Runs git commit -m and appends a
    commit block to today's entry (creates entry from branch slug if none
    exists). Returns commit_hash, files_changed count, entry_path.
    Response: ~300 tokens. Set no_entry=True to skip journal update.
    Fails if nothing is staged.

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
        cwd=str(_project_root(buildlog_dir)),
    )
    return _ensure_message(asdict(result))


def buildlog_gauntlet_prompt(
    target: str,
    personas: list[str] | None = None,
    select_k: int | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Need just the raw review prompt without loop infrastructure?

    Call with a target path to get the formatted prompt for pasting into
    a different agent or manual use. Returns prompt (string, typically
    8000-15000 tokens), target, total_rules. WARNING: The prompt field
    alone is 8k-15k tokens. For the standard review-fix-commit loop,
    use buildlog_gauntlet_loop() instead — it manages the full workflow.

    Args:
        target: Path to target code (file or directory, e.g., "src/")
        personas: Persona names to include (default: all)
        select_k: Max rules per persona via learning backend (None = all)
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with prompt, target, personas, total_rules, message, error
    """
    result = generate_gauntlet_prompt(
        target=target,
        personas=personas,
        buildlog_dir=Path(buildlog_dir) if select_k is not None else None,
        select_k=select_k,
    )
    return _ensure_message(asdict(result))


def buildlog_gauntlet_loop(
    target: str,
    personas: list[str] | None = None,
    max_iterations: int = 10,
    stop_at: str = "minors",
    auto_gh_issues: bool = False,
    compact: bool = True,
    select_k: int = 10,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Ready to run a full gauntlet code review? Start here.

    Call once to initialize the review loop. Pass target="src/" (file or
    directory). Returns instructions (step-by-step loop protocol),
    valid_rule_ids (for citation validation in buildlog_gauntlet_issues()),
    target, personas, stop_at, max_iterations. Response: ~1500 tokens with
    compact=True (default). After this, review the code, then call
    buildlog_gauntlet_issues() with findings. Use buildlog_gauntlet_rule_lookup()
    mid-review to hydrate specific rules by ID. Do NOT also call
    gauntlet_rules() or gauntlet_prompt() — this tool includes both.

    Args:
        target: Path to target code (e.g., "src/", "src/api.py")
        personas: Persona names (default: all)
        max_iterations: Max review-fix iterations (default: 10)
        stop_at: Stop after clearing: "criticals", "majors", or "minors"
        auto_gh_issues: Create GitHub issues for accepted risk items
        compact: Omit bulky fields (default: True). Set False for full
            prompt + rules_by_persona + rule_id_index.
        select_k: Top rules per persona via Thompson Sampling (default: 10).
            Set to 0 for all rules (large prompt). 10 per persona ≈ 80 rules.
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with target, personas, max_iterations, stop_at,
        instructions, issue_format, valid_rule_ids, message, error
    """
    result = gauntlet_loop_config(
        target=target,
        personas=personas,
        max_iterations=max_iterations,
        stop_at=stop_at,
        auto_gh_issues=auto_gh_issues,
        buildlog_dir=Path(buildlog_dir),
        select_k=select_k if select_k > 0 else None,
    )
    d = asdict(result)

    if compact:
        # The prompt already contains all rules formatted for the LLM.
        # rules_by_persona is redundant and massive with many personas.
        d.pop("rules_by_persona", None)
        # The prompt itself is ~14k tokens of re-formatted rules.
        # The caller has valid_rule_ids and instructions — prompt is
        # only useful if pasting verbatim (use compact=False for that).
        d.pop("prompt", None)

        # Caller only needs the list of valid IDs (for valid_rule_ids
        # param on buildlog_gauntlet_issues), not per-rule metadata.
        rule_id_index = d.pop("rule_id_index", {})
        d["valid_rule_ids"] = sorted(rule_id_index.keys())

    return _ensure_message(d)


def buildlog_gauntlet_rule_lookup(
    rule_ids: list[str],
) -> dict:
    """Reviewing code and need the full text of a rule behind an opaque ID?

    Pass 1-10 rule IDs (e.g., ["bragi:02959dda", "loki:a1b2c3d4"]).
    Returns each rule's full text, category, antipattern, rationale, and
    context — everything the ID hides. Response: ~150 tokens per rule.
    Call mid-review when buildlog_gauntlet_loop() gave you IDs but you
    need the actual rule content to evaluate code against it. Do NOT call
    this to get all rules — use buildlog_gauntlet_loop() for that.

    Args:
        rule_ids: List of rule IDs to look up (from valid_rule_ids)

    Returns:
        Dict with rules (list of rule details), found, missing, message
    """
    result = gauntlet_rule_lookup(rule_ids=rule_ids)
    return _ensure_message(result)


# =============================================================================
# P1: Learning pipeline tools
# =============================================================================


def buildlog_distill(
    since: str | None = None,
    category: str | None = None,
    llm: bool = False,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Step 1 of 4 in the learning pipeline (distill > skills > status > promote).

    Parses the "## Improvements" section of each buildlog entry, groups
    findings by category. Returns entry_count, patterns (dict keyed by
    category, each a list of {text, source_entry, date}), statistics
    (total_patterns, by_category, by_month). Response: ~500-5000 tokens.
    Use since="2026-01-01" to bound. Most callers should skip this and
    call buildlog_skills() directly — it runs distill internally.

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
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Step 2 of 4: refresh the skill set from recent buildlog entries.

    Call when new entries have been committed since last extraction. Runs
    distill internally, deduplicates, assigns stable IDs and confidence
    scores. Returns generated_at, source_entries count, total_skills count,
    skills (dict by category, each a list of {id, rule, confidence,
    frequency, sources}). Response: ~500-3000 tokens. After this, call
    buildlog_status() or buildlog_diff() to review, then promote/reject.

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
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Worried journal entries are missing Improvements sections or frequency dropped?

    Call for a quality audit of the buildlog corpus. Returns entries (total,
    with_improvements, coverage_pct), streak (current, longest), warnings
    (list of specific issues like "3 entries missing Improvements").
    Response: ~400 tokens. Set detailed=True for top_sources breakdown
    (~200 extra tokens). This is about JOURNAL quality — for mistake/reward
    data use buildlog_experiment_report().

    Args:
        since: Only entries from this date onward (YYYY-MM-DD)
        detailed: Include top sources breakdown
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with entries, streak, warnings, pipeline coverage
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
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Want to see which reviewer personas exist before choosing for a gauntlet?

    Call before buildlog_gauntlet_loop(personas=[...]). Returns personas
    (dict keyed by name, each with rules_count and version), total_rules,
    total_personas. Response: ~200 tokens for 5-8 personas. This is a
    lightweight lookup — for actual rules, use buildlog_gauntlet_rules().

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with personas, total_rules, total_personas
    """
    from buildlog.seeds import load_rules
    from buildlog.storage import get_backend

    try:
        backend, _ = get_backend()
    except Exception:
        backend = None

    seeds = load_rules(backend=backend)

    if not seeds:
        return {
            "personas": {},
            "total_rules": 0,
            "total_personas": 0,
            "error": "No rules found. Check your buildlog installation.",
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
    source_text: str | None = None,
    persona: str = "",
    output_dir: str | None = None,
    dry_run: bool = False,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
    source_file: str | None = None,
) -> dict:
    """Have a standards doc or style guide that should become gauntlet rules?

    Call with source text (inline or file path, typically 500-10000 chars)
    and a persona name. Makes an LLM call to extract rules, writes a YAML
    seed file to .buildlog/seeds/. Returns persona, rule_count, output_path.
    Response: ~300 tokens. Set dry_run=True to preview without writing.
    This creates NEW rules from prose — to import an existing YAML seed
    file, use buildlog_import_seed().

    Provide source_text inline OR via a file path (not both).

    Args:
        source_text: The text content to extract rules from
        persona: Persona name for the seed file
        output_dir: Output dir for seed YAML (default: .buildlog/seeds)
        dry_run: Preview without writing to disk
        buildlog_dir: Path to buildlog directory
        source_file: Path to a text file containing the source content.
            Mutually exclusive with 'source_text'.

    Returns:
        Dict with persona, rule_count, output_path, preview, message
    """
    try:
        resolved = _resolve_text_file_or_inline(source_text, source_file, "source_text")
    except (ValueError, FileNotFoundError) as exc:
        return {
            "persona": persona,
            "rule_count": 0,
            "output_path": "",
            "preview": "",
            "message": "",
            "error": str(exc),
        }

    out = Path(output_dir) if output_dir else Path(buildlog_dir) / ".buildlog" / "seeds"
    result = gauntlet_generate(
        source_text=resolved,
        persona=persona,
        output_dir=out,
        dry_run=dry_run,
    )
    return _ensure_message(asdict(result))


def buildlog_migrate(
    dry_run: bool = False,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Upgraded buildlog and seeing "legacy files detected" warnings?

    Migrates .buildlog/*.json(l) files into ~/.buildlog/buildlog.db.
    Originals renamed to *.migrated (not deleted). Returns lines (list
    of migration log strings, typically 5-20) and summary. Response: ~300
    tokens. Idempotent — safe to re-run. Set dry_run=True to preview.
    This migrates DATA — to update TEMPLATES, use buildlog_update().

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


def buildlog_import_seed(
    source: str,
    target_dir: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Have a specific YAML seed file (e.g., from qortex export) to add?

    Call with source="/path/to/file.yaml". Validates, copies to
    .buildlog/seeds/, triggers bandit decay if graph_version changed.
    Returns persona, rule_count, version_changed, decayed_rules.
    Response: ~250 tokens. This imports ONE known file. To scan a
    configured interop directory for multiple pending files, use
    buildlog_ingest_seeds().

    Args:
        source: Path to the source YAML seed file.
        target_dir: Directory to copy the seed file into.
            Defaults to .buildlog/seeds/.
        buildlog_dir: Path to buildlog directory.

    Returns:
        Dict with persona, rule_count, provenance_count, target_path,
        version_changed, decayed_rules, message.

    Example:
        buildlog_import_seed(source="qortex-rules.yaml")
    """
    from buildlog.seeds import import_seed_file

    try:
        # Resolve target_dir to prevent path traversal
        resolved_target = Path(target_dir).resolve() if target_dir else None
        if resolved_target is not None:
            cwd = Path.cwd().resolve()
            if not str(resolved_target).startswith(str(cwd)):
                return {
                    "persona": "",
                    "rule_count": 0,
                    "provenance_count": 0,
                    "target_path": "",
                    "version_changed": False,
                    "decayed_rules": 0,
                    "message": "",
                    "error": f"target_dir must be within working directory: {resolved_target}",
                }

        result = import_seed_file(
            source_path=Path(source),
            target_dir=resolved_target,
            buildlog_dir=Path(buildlog_dir),
        )
        return _ensure_message(asdict(result))
    except (FileNotFoundError, ValueError) as e:
        return {
            "persona": "",
            "rule_count": 0,
            "provenance_count": 0,
            "target_path": "",
            "version_changed": False,
            "decayed_rules": 0,
            "message": "",
            "error": str(e),
        }


def buildlog_export(
    format: str = "jsonl",
    output: str | None = None,
    project: str | None = None,
    tables: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
    include_manifest: bool = True,
    include_rules_join: bool = True,
) -> dict:
    """Need to back up buildlog data or feed it to an external system?

    Writes JSONL files to output directory (default: temp dir). Use
    tables="rewards,sessions" to limit scope (6 tables available:
    rewards, sessions, mistakes, bandit_state, learnings, skill_decisions).
    Returns format, project_id, tables, output path, summary with per-table
    row counts. Response: ~300 tokens. Output files can be large — use
    tables param to limit. Always writes to disk to avoid token blowout.

    Args:
        format: Output format (currently only 'jsonl').
        output: Directory to write files into. None = temp directory.
        project: Limit to a specific project ID. None = current project.
        tables: Comma-separated table names (e.g., "rewards,sessions").
            None = all tables.
        buildlog_dir: Path to buildlog directory.
        include_manifest: Generate manifest.json with export metadata.
        include_rules_join: Generate rules.jsonl join table from seeds.

    Returns:
        Dict with format, project_id, tables, output path, summary

    Example:
        buildlog_export(tables="rewards,sessions")
        buildlog_export(output="./backup/", tables="bandit_state")
    """
    from buildlog.seeds import get_default_seeds_dir
    from buildlog.storage import get_backend
    from buildlog.storage.exporters import JsonlExporter

    backend, project_id = get_backend(Path(buildlog_dir))

    table_list = [t.strip() for t in tables.split(",")] if tables else None
    output_path = Path(output) if output else None
    pid = project or project_id

    seeds_dir = get_default_seeds_dir() if include_rules_join else None

    # When no output path, use a temp dir to avoid unbounded string returns
    # that can exceed MCP token limits (same class of bug as #167).
    if output_path is None:
        import tempfile

        output_path = Path(tempfile.mkdtemp(prefix="buildlog-export-"))

    exporter = JsonlExporter()
    summary = exporter.export(
        backend,
        project_id=pid,
        output_path=output_path,
        tables=table_list,
        include_manifest=include_manifest,
        include_rules_join=include_rules_join,
        seeds_dir=seeds_dir,
    )

    from buildlog.storage.exporters import EXPORTABLE_TABLES

    return {
        "format": format,
        "project_id": pid,
        "tables": table_list or EXPORTABLE_TABLES,
        "output": str(output_path),
        "summary": summary,
    }


def buildlog_ingest_seeds(
    source: str | None = None,
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Configured interop sources and want to pull in all pending seeds at once?

    Call at session start or after a qortex KG update. Scans each source's
    pending/ folder (configured in ~/.buildlog/interop.yaml), validates and
    imports YAML files, moves processed files. Returns sources (list of
    per-source results), total_ingested, total_failed, total_skipped.
    Response: ~300 tokens. Use source="qortex" to limit to one producer.
    To import a single known file, use buildlog_import_seed() instead.

    Args:
        source: Filter to a specific source name (e.g. "qortex").
            None = scan all configured sources.
        buildlog_dir: Path to buildlog directory.

    Returns:
        Dict with sources list, total_ingested, total_failed, total_skipped
    """
    from dataclasses import asdict as _asdict

    from buildlog.interop import ingest_pending

    results = ingest_pending(
        source_name=source,
        buildlog_dir=Path(buildlog_dir),
    )
    return {
        "sources": [_asdict(r) for r in results],
        "total_ingested": sum(r.ingested for r in results),
        "total_failed": sum(r.failed for r in results),
        "total_skipped": sum(r.skipped for r in results),
    }


def buildlog_init(
    defaults: bool = True,
    no_claude_md: bool = False,
    no_mcp: bool = False,
    project_dir: str = ".",
) -> dict:
    """Setting up buildlog in a project for the first time?

    Call once per project. Creates buildlog/ with entry template, optionally
    appends workflow section to CLAUDE.md, optionally registers MCP server
    in .mcp.json. Returns initialized (bool), buildlog_dir, claude_md_updated,
    mcp_registered. Response: ~200 tokens. Idempotent — safe to re-run.
    To update an existing install to latest templates, use buildlog_update().

    Args:
        defaults: Use default values (always True for MCP)
        no_claude_md: Don't update CLAUDE.md
        no_mcp: Don't register MCP server
        project_dir: Project root directory (default: current directory)

    Returns:
        Dict with initialized, buildlog_dir, claude_md_updated,
        mcp_registered, message, error
    """
    result = init_buildlog(
        project_dir=Path(project_dir).resolve(),
        defaults=True,
        no_claude_md=no_claude_md,
        no_mcp=no_mcp,
    )
    return _ensure_message(asdict(result))


def buildlog_update(
    project_dir: str = ".",
) -> dict:
    """Just ran pip install --upgrade buildlog and want templates to match?

    Runs copier update on the buildlog/ directory. Returns updated (bool),
    message (what changed or "already up to date"). Response: ~150 tokens.
    Requires buildlog_init() to have been run first. This updates TEMPLATES
    (entry format, CLAUDE.md sections) — to migrate DATA from legacy JSON
    files, use buildlog_migrate().

    Args:
        project_dir: Project root directory (default: current directory)

    Returns:
        Dict with updated, message, error
    """
    result = update_buildlog(project_dir=Path(project_dir).resolve())
    return _ensure_message(asdict(result))


def buildlog_consume_emissions(
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Emission artifacts piling up in ~/.buildlog/emissions/pending/?

    Processes mistake manifests and session summaries into the emission_edges
    table. Moves processed files to processed/. Returns consumed, failed,
    skipped, edges_stored counts. Response: ~200 tokens. Call after several
    sessions to batch-process accumulated artifacts. Typically called by
    automation, not directly by agents.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dict with consumed, failed, skipped, edges_stored, errors
    """
    from dataclasses import asdict as _asdict

    from buildlog.emissions.consumer import consume_pending_emissions

    result = consume_pending_emissions()
    return _ensure_message(
        {
            **_asdict(result),
            "message": (
                f"Consumed {result.consumed} emissions, "
                f"stored {result.edges_stored} edges"
                + (f", {result.failed} failed" if result.failed else "")
            ),
        }
    )


def buildlog_verify(
    buildlog_dir: str = DEFAULT_BUILDLOG_DIR,
) -> dict:
    """Buildlog commands failing or unsure if setup is complete?

    Runs 5-6 preflight checks: buildlog/ exists, CLAUDE.md has workflow
    section, MCP registered, not on main branch, pre-commit hook installed.
    Returns ok (bool), summary ("5/6 checks passed, 1 warning"),
    passed/warnings/failed (each a list of {name, status, message}).
    Response: ~400 tokens. Call after buildlog_init() or when debugging.

    Args:
        buildlog_dir: Path to buildlog directory (default: "buildlog")

    Returns:
        Dict with ok, summary, passed, warnings, failed check lists

    Example:
        buildlog_verify()
        # => {"ok": true, "summary": "5/6 checks passed, 1 warnings"}
    """
    project_dir = _project_root(buildlog_dir)
    result = verify_workflow(
        project_dir=project_dir,
        buildlog_dir=Path(buildlog_dir).resolve(),
    )
    return _ensure_message(asdict(result))
