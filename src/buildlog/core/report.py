"""Pure rendering logic for session improvements reports.

Zero I/O, zero storage dependency. Imported by operations.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Threshold for declaring a rule has "earned confidence" — posterior mean
# above this indicates the bandit has enough positive evidence to exploit.
# 0.7 chosen to match Beta(7,3) ≈ 70% success rate baseline.
_CONFIDENCE_THRESHOLD = 0.7

# Threshold for demoting a rule — posterior mean below this suggests the
# rule is not helping. 0.4 = worse than random (Beta(1,1) prior = 0.5).
_DEMOTION_THRESHOLD = 0.4


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RuleStatus:
    """Status of a single rule in the bandit."""

    rule_id: str
    mean: float
    observations: int
    status: str  # "earned_confidence" | "stable" | "demoted" | "new"


@dataclass
class ImprovementsReportData:
    """All data needed to render an improvements report."""

    session_id: str
    duration_minutes: float
    error_class: str | None
    mistakes_caught: int
    repeated_mistakes: int
    rules_at_start: int
    rules_at_end: int
    mean_reward: float | None  # None = no reward events (NOT 0.0)
    rule_statuses: list[RuleStatus] = field(default_factory=list)
    # Prior session (None if no prior or first session)
    prior_mistakes: int | None = None
    prior_repeats: int | None = None
    prior_rules_start: int | None = None
    prior_rules_end: int | None = None
    prior_mean_reward: float | None = None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_rule(mean: float, observations: int) -> str:
    """Classify a rule based on its posterior mean and observation count.

    Returns one of: "new", "earned_confidence", "demoted", "stable".
    """
    if observations == 0:
        return "new"
    if mean >= _CONFIDENCE_THRESHOLD:
        return "earned_confidence"
    if mean < _DEMOTION_THRESHOLD:
        return "demoted"
    return "stable"


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def should_emit_report(data: ImprovementsReportData) -> bool:
    """Return False when there's nothing to show.

    Empty report is anti-evidence for H1 — skip it.
    """
    if (
        data.mistakes_caught == 0
        and not data.rule_statuses
        and data.mean_reward is None
    ):
        return False
    return True


# ---------------------------------------------------------------------------
# Rendering — narrative
# ---------------------------------------------------------------------------


def _trend_arrow(current: float | int | None, prior: float | int | None) -> str:
    """Return a trend arrow comparing current to prior."""
    if current is None or prior is None:
        return ""
    if current > prior:
        return " ↑"
    if current < prior:
        return " ↓"
    return " →"


def render_improvements_narrative(data: ImprovementsReportData) -> str:
    """Render the narrative section of the improvements report."""
    lines: list[str] = []
    lines.append("## What Improved This Session")
    lines.append("")

    # Mistakes paragraph
    if data.mistakes_caught > 0:
        repeat_note = ""
        if data.repeated_mistakes > 0:
            repeat_note = f", {data.repeated_mistakes} were repeats"
        lines.append(
            f"**{data.mistakes_caught} mistakes caught{repeat_note}** — "
            f"the gauntlet flagged issues before they shipped."
        )
    else:
        lines.append("**Clean session** — no mistakes were flagged.")
    lines.append("")

    # Rules earned/demoted
    earned = [r for r in data.rule_statuses if r.status == "earned_confidence"]
    demoted = [r for r in data.rule_statuses if r.status == "demoted"]

    if earned:
        names = ", ".join(f"`{r.rule_id}`" for r in earned)
        lines.append(
            f"**Rules earning confidence**: {names} "
            f"(mean ≥ {_CONFIDENCE_THRESHOLD})."
        )
        lines.append("")

    if demoted:
        names = ", ".join(f"`{r.rule_id}`" for r in demoted)
        lines.append(f"**Rules demoted**: {names} " f"(mean < {_DEMOTION_THRESHOLD}).")
        lines.append("")

    # Mean reward with trend
    if data.mean_reward is not None:
        arrow = _trend_arrow(data.mean_reward, data.prior_mean_reward)
        lines.append(f"**Mean reward**: {data.mean_reward:.2f}{arrow}")
        lines.append("")

    # Duration + error class context
    context_parts = [f"Session ran for {data.duration_minutes:.1f} minutes"]
    if data.error_class:
        context_parts.append(f"targeting `{data.error_class}`")
    context_parts.append(
        f"with {data.rules_at_start} rules at start → {data.rules_at_end} at end"
    )
    lines.append(". ".join(context_parts) + ".")
    lines.append("")

    # Advocacy blockquote
    lines.append(
        "> Every session that measures improvement is evidence that "
        "the learning loop works. This is buildlog's thesis: "
        "track, learn, improve — automatically."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rendering — data table
# ---------------------------------------------------------------------------


def _fmt(value: float | int | None, fmt: str = ".2f") -> str:
    """Format a value or return '—' for None."""
    if value is None:
        return "—"
    if isinstance(value, int):
        return str(value)
    return f"{value:{fmt}}"


def _trend_cell(current: float | int | None, prior: float | int | None) -> str:
    """Trend cell: arrow or — if no prior."""
    if current is None or prior is None:
        return "—"
    arrow = _trend_arrow(current, prior)
    return arrow.strip() if arrow.strip() else "→"


def render_improvements_table(data: ImprovementsReportData) -> str:
    """Render the data table section of the improvements report."""
    lines: list[str] = []

    # Metrics table
    lines.append("### Metrics")
    lines.append("")
    lines.append("| Metric | This Session | Prior | Trend |")
    lines.append("|--------|-------------|-------|-------|")
    lines.append(
        f"| Mistakes caught | {data.mistakes_caught} "
        f"| {_fmt(data.prior_mistakes)} "
        f"| {_trend_cell(data.mistakes_caught, data.prior_mistakes)} |"
    )
    lines.append(
        f"| Repeated mistakes | {data.repeated_mistakes} "
        f"| {_fmt(data.prior_repeats)} "
        f"| {_trend_cell(data.repeated_mistakes, data.prior_repeats)} |"
    )
    lines.append(
        f"| Rules at start | {data.rules_at_start} "
        f"| {_fmt(data.prior_rules_start)} "
        f"| {_trend_cell(data.rules_at_start, data.prior_rules_start)} |"
    )
    lines.append(
        f"| Rules at end | {data.rules_at_end} "
        f"| {_fmt(data.prior_rules_end)} "
        f"| {_trend_cell(data.rules_at_end, data.prior_rules_end)} |"
    )
    lines.append(
        f"| Mean reward | {_fmt(data.mean_reward)} "
        f"| {_fmt(data.prior_mean_reward)} "
        f"| {_trend_cell(data.mean_reward, data.prior_mean_reward)} |"
    )
    lines.append("")

    # Top rules table (only if we have rule statuses)
    if data.rule_statuses:
        lines.append("### Top Rules")
        lines.append("")
        lines.append("| Rule | Mean | Observations | Status |")
        lines.append("|------|------|-------------|--------|")
        # Sort by mean descending
        sorted_rules = sorted(data.rule_statuses, key=lambda r: r.mean, reverse=True)
        for r in sorted_rules:
            status_label = r.status.replace("_", " ")
            lines.append(
                f"| `{r.rule_id}` | {r.mean:.4f} | {r.observations} | {status_label} |"
            )
        lines.append("")

    # Anchor comment
    lines.append(f"<!-- buildlog:session-summary:{data.session_id} -->")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Injection
# ---------------------------------------------------------------------------

_MARKER_START = "<!-- buildlog:improvements:start -->"
_MARKER_END = "<!-- buildlog:improvements:end -->"


def inject_improvements_into_entry(content: str, report: str) -> str:
    """Inject an improvements report into a journal entry.

    - If markers already exist: replace between them (inclusive).
    - Else if ``## Commits`` exists: insert before it.
    - Else: append to end.
    """
    wrapped = f"{_MARKER_START}\n{report}\n{_MARKER_END}"

    # Idempotent replace
    start_idx = content.find(_MARKER_START)
    end_idx = content.find(_MARKER_END)
    if start_idx != -1 and end_idx != -1:
        end_idx += len(_MARKER_END)
        return content[:start_idx] + wrapped + content[end_idx:]

    # Insert before ## Commits
    commits_idx = content.find("\n## Commits")
    if commits_idx != -1:
        return content[:commits_idx] + "\n" + wrapped + "\n" + content[commits_idx:]

    # Append
    if content and not content.endswith("\n"):
        content += "\n"
    return content + "\n" + wrapped + "\n"
