import marimo

__generated_with = "0.19.5"
app = marimo.App(width="medium", app_title="buildlog dashboard")


@app.cell
def _():
    import marimo as mo

    mo.md(
        """
    # buildlog dashboard

    Live view of your learning loop data. Every chart here is evidence
    that the system is measuring, adapting, and getting better.
    """
    )
    return (mo,)


@app.cell
def _(mo):
    # Resolve buildlog directory (env var or default)
    import os
    import sys
    from pathlib import Path

    _buildlog_dir_str = os.environ.get("BUILDLOG_DIR", "buildlog")
    buildlog_dir = Path(_buildlog_dir_str)

    if not buildlog_dir.exists():
        # Try parent directories (notebook might be in notebooks/)
        for candidate in [Path("../buildlog"), Path("../../buildlog")]:
            if candidate.exists():
                buildlog_dir = candidate
                break

    # Ensure the package is importable
    _src = buildlog_dir.parent / "src"
    if _src.exists() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

    mo.md(f"**Data source**: `{buildlog_dir.resolve()}`")
    return buildlog_dir, os


@app.cell
def _(buildlog_dir, mo):
    from buildlog.stats import calculate_stats

    stats = calculate_stats(buildlog_dir)

    # Overview cards
    e = stats.entries
    s = stats.streak

    mo.md(
        f"""
    ## Overview

    | Metric | Value |
    |--------|-------|
    | Total entries | **{e.total}** |
    | This week | **{e.this_week}** |
    | This month | **{e.this_month}** |
    | Coverage | **{e.coverage_percent}%** |
    | Current streak | **{s.current} days** |
    | Longest streak | **{s.longest} days** |
    """
    )
    return (stats,)


@app.cell
def _(mo, stats):
    # Insight category breakdown
    categories = stats.insights.by_category
    total = stats.insights.total

    if total > 0:
        rows = []
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            pct = count / total * 100 if total else 0
            bar = "#" * int(pct / 2)
            display = cat.replace("_", " ").title()
            rows.append(f"| {display} | {count} | {pct:.0f}% | `{bar}` |")

        table = "\n".join(rows)
        mo.md(
            f"""
    ## Insights by Category

    {total} insights extracted across {len(categories)} categories.

    | Category | Count | Share | Distribution |
    |----------|-------|-------|-------------|
    {table}
    """
        )
    else:
        mo.md(
            """
    ## Insights by Category

    No insights extracted yet. Run `buildlog distill` to extract patterns from entries.
    """
        )
    return


@app.cell
def _(buildlog_dir, mo):
    import json

    # Load reward events for learning loop visualization
    reward_events = []
    _rewards_path = buildlog_dir / ".buildlog" / "reward_events.jsonl"
    if _rewards_path.exists():
        for line in _rewards_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    reward_events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if reward_events:
        # Compute running mean reward
        total_reward = 0.0
        running_means = []
        outcomes = {"accepted": 0, "revision": 0, "rejected": 0}

        for i, evt in enumerate(reward_events, 1):
            total_reward += evt.get("reward_value", 0.0)
            running_means.append(total_reward / i)
            outcome = evt.get("outcome", "unknown")
            if outcome in outcomes:
                outcomes[outcome] += 1

        current_mean = running_means[-1] if running_means else 0.0
        n = len(reward_events)

        # Outcome breakdown
        outcome_rows = []
        for outcome, count in sorted(
            outcomes.items(), key=lambda x: x[1], reverse=True
        ):
            pct = count / n * 100
            outcome_rows.append(f"| {outcome} | {count} | {pct:.0f}% |")
        outcome_table = "\n".join(outcome_rows)

        # Running mean as sparkline-style text
        # Show last 20 data points as a mini trend
        recent = running_means[-20:]
        spark_min, spark_max = min(recent), max(recent)
        spark_range = spark_max - spark_min if spark_max != spark_min else 1.0
        spark_chars = " _.-=^"
        sparkline = ""
        for val in recent:
            idx = int((val - spark_min) / spark_range * (len(spark_chars) - 1))
            sparkline += spark_chars[idx]

        mo.md(
            f"""
    ## Learning Loop

    **{n} reward events** recorded. Current mean reward: **{current_mean:.3f}**

    Recent trend: `{sparkline}`

    ### Outcome Breakdown

    | Outcome | Count | Share |
    |---------|-------|-------|
    {outcome_table}

    The learning loop works when accepted outcomes increase over time
    and the mean reward trends upward. Each reward event teaches the
    bandit which rules actually help.
    """
        )
    else:
        mo.md(
            """
    ## Learning Loop

    No reward events yet. Use `buildlog reward --outcome accepted` after
    successful commits to start feeding the learning loop.
    """
        )
    return


@app.cell
def _(buildlog_dir, mo):
    import json as _json

    # Load sessions for session history
    sessions = []
    _sessions_path = buildlog_dir / ".buildlog" / "sessions.jsonl"
    if _sessions_path.exists():
        for line in _sessions_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    sessions.append(_json.loads(line))
                except _json.JSONDecodeError:
                    continue

    if sessions:
        # Session metrics table
        session_rows = []
        for sess in reversed(sessions[-10:]):  # Last 10 sessions
            sid = sess.get("id", "?")[:20]
            started = sess.get("started_at", "?")[:10]
            rules_start = len(sess.get("rules_at_start", []))
            rules_end = len(sess.get("rules_at_end", []))
            error_class = sess.get("error_class", "general") or "general"
            delta = rules_end - rules_start
            delta_str = f"+{delta}" if delta > 0 else str(delta)
            session_rows.append(
                f"| {started} | `{sid}` | {error_class} | {rules_start} | {rules_end} | {delta_str} |"
            )

        session_table = "\n".join(session_rows)

        mo.md(
            f"""
    ## Session History

    **{len(sessions)} sessions** recorded. Showing last 10.

    | Date | Session | Error Class | Rules Start | Rules End | Delta |
    |------|---------|-------------|-------------|-----------|-------|
    {session_table}

    Rule count growth over sessions indicates the system is learning
    and promoting new rules based on observed patterns.
    """
        )
    else:
        mo.md(
            """
    ## Session History

    No sessions recorded yet. Use `buildlog experiment start` to begin
    tracking sessions.
    """
        )
    return


@app.cell
def _(buildlog_dir, mo):
    import json as _json2

    # Load mistakes for mistake analysis
    mistakes = []
    _mistakes_path = buildlog_dir / ".buildlog" / "mistakes.jsonl"
    if _mistakes_path.exists():
        for line in _mistakes_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    mistakes.append(_json2.loads(line))
                except _json2.JSONDecodeError:
                    continue

    if mistakes:
        # Group by error class
        error_classes: dict[str, int] = {}
        repeats = 0
        for m in mistakes:
            ec = m.get("error_class", "unknown")
            error_classes[ec] = error_classes.get(ec, 0) + 1
            if m.get("was_repeat", False):
                repeats += 1

        repeat_pct = repeats / len(mistakes) * 100

        ec_rows = []
        for ec, count in sorted(
            error_classes.items(), key=lambda x: x[1], reverse=True
        ):
            ec_rows.append(f"| {ec} | {count} |")
        ec_table = "\n".join(ec_rows)

        mo.md(
            f"""
    ## Mistake Analysis

    **{len(mistakes)} mistakes** logged across {len(error_classes)} error classes.
    **{repeats} repeats** ({repeat_pct:.0f}% repeat rate).

    A declining repeat rate means the rules are preventing recurrence.

    ### By Error Class

    | Error Class | Count |
    |-------------|-------|
    {ec_table}
    """
        )
    else:
        mo.md(
            """
    ## Mistake Analysis

    No mistakes logged yet. When the gauntlet catches issues during
    sessions, they appear here.
    """
        )
    return


@app.cell
def _(buildlog_dir, mo):
    # Bandit arm stats (if SQLite bandit exists)
    bandit_stats = {}
    try:
        from buildlog.core.learning import get_learning_backend

        lb = get_learning_backend(buildlog_dir)
        bandit_stats = lb.get_stats(None)  # All contexts
    except Exception:
        pass

    if bandit_stats:
        # Sort by mean descending
        sorted_arms = sorted(
            bandit_stats.items(), key=lambda x: x[1].get("mean", 0), reverse=True
        )

        arm_rows = []
        for rule_id, arm in sorted_arms[:15]:  # Top 15
            mean = arm.get("mean", 0)
            obs = int(arm.get("total_observations", 0))
            ci = arm.get("confidence_interval", (0, 1))
            ci_str = f"[{ci[0]:.2f}, {ci[1]:.2f}]"

            # Status classification
            if obs == 0:
                status = "new"
            elif mean >= 0.7:
                status = "earning confidence"
            elif mean < 0.4:
                status = "demoted"
            else:
                status = "stable"

            arm_rows.append(
                f"| `{rule_id}` | {mean:.3f} | {obs} | {ci_str} | {status} |"
            )

        arm_table = "\n".join(arm_rows)

        mo.md(
            f"""
    ## Bandit Arm Posteriors

    **{len(bandit_stats)} rules** tracked by the Thompson Sampling bandit.
    Showing top 15 by posterior mean.

    | Rule | Mean | Observations | 95% CI | Status |
    |------|------|-------------|--------|--------|
    {arm_table}

    Rules with high means and narrow confidence intervals are the ones
    the bandit exploits most. New rules get explored until there is enough
    evidence to exploit or demote them.
    """
        )
    else:
        mo.md(
            """
    ## Bandit Arm Posteriors

    No bandit data available. The Thompson Sampling bandit starts tracking
    rules after the first session with reward events.
    """
        )
    return


@app.cell
def _(mo, stats):
    # Quality warnings and top sources
    warnings = stats.warnings
    sources = stats.top_sources

    parts = []

    if sources:
        source_rows = []
        for i, src in enumerate(sources, 1):
            source_rows.append(f"| {i} | {src['name']} | {src['insights']} |")
        source_table = "\n".join(source_rows)
        parts.append(
            f"""### Top Sources

| Rank | Entry | Insights |
|------|-------|----------|
{source_table}"""
        )

    if warnings:
        warning_items = "\n".join(f"- {w}" for w in warnings)
        parts.append(
            f"""### Quality Warnings

{warning_items}"""
        )

    if parts:
        mo.md("## Health\n\n" + "\n\n".join(parts))
    else:
        mo.md("## Health\n\nNo warnings. Everything looks good.")
    return


if __name__ == "__main__":
    app.run()
