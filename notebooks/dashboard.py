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
    import os
    import sys
    from pathlib import Path

    _buildlog_dir_str = os.environ.get("BUILDLOG_DIR", "buildlog")
    buildlog_dir = Path(_buildlog_dir_str)

    if not buildlog_dir.exists():
        for _candidate in [Path("../buildlog"), Path("../../buildlog")]:
            if _candidate.exists():
                buildlog_dir = _candidate
                break

    _src = buildlog_dir.parent / "src"
    if _src.exists() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

    mo.md(f"**Data source**: `{buildlog_dir.resolve()}`")
    return (buildlog_dir,)


@app.cell
def _(buildlog_dir, mo):
    from buildlog.stats import calculate_stats

    stats = calculate_stats(buildlog_dir)

    _e = stats.entries
    _s = stats.streak

    mo.md(
        f"""
    ## Overview

    | Metric | Value |
    |--------|-------|
    | Total entries | **{_e.total}** |
    | This week | **{_e.this_week}** |
    | This month | **{_e.this_month}** |
    | Coverage | **{_e.coverage_percent}%** |
    | Current streak | **{_s.current} days** |
    | Longest streak | **{_s.longest} days** |
    """
    )
    return (stats,)


@app.cell
def _(mo, stats):
    _categories = stats.insights.by_category
    _total = stats.insights.total

    if _total > 0:
        _rows = []
        for _cat, _cnt in sorted(_categories.items(), key=lambda x: x[1], reverse=True):
            _pct = _cnt / _total * 100 if _total else 0
            _bar = "#" * int(_pct / 2)
            _display = _cat.replace("_", " ").title()
            _rows.append(f"| {_display} | {_cnt} | {_pct:.0f}% | `{_bar}` |")

        _table = "\n".join(_rows)
        mo.md(
            f"""
    ## Insights by Category

    {_total} insights extracted across {len(_categories)} categories.

    | Category | Count | Share | Distribution |
    |----------|-------|-------|-------------|
    {_table}
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

    _reward_events = []
    _rewards_path = buildlog_dir / ".buildlog" / "reward_events.jsonl"
    if _rewards_path.exists():
        for _line in _rewards_path.read_text().splitlines():
            _line = _line.strip()
            if _line:
                try:
                    _reward_events.append(json.loads(_line))
                except json.JSONDecodeError:
                    continue

    if _reward_events:
        _total_reward = 0.0
        _running_means = []
        _outcomes = {"accepted": 0, "revision": 0, "rejected": 0}

        for _i, _evt in enumerate(_reward_events, 1):
            _total_reward += _evt.get("reward_value", 0.0)
            _running_means.append(_total_reward / _i)
            _outcome = _evt.get("outcome", "unknown")
            if _outcome in _outcomes:
                _outcomes[_outcome] += 1

        _current_mean = _running_means[-1] if _running_means else 0.0
        _n = len(_reward_events)

        _outcome_rows = []
        for _oname, _ocnt in sorted(
            _outcomes.items(), key=lambda x: x[1], reverse=True
        ):
            _opct = _ocnt / _n * 100
            _outcome_rows.append(f"| {_oname} | {_ocnt} | {_opct:.0f}% |")
        _outcome_table = "\n".join(_outcome_rows)

        _recent = _running_means[-20:]
        _spark_min, _spark_max = min(_recent), max(_recent)
        _spark_range = _spark_max - _spark_min if _spark_max != _spark_min else 1.0
        _spark_chars = " _.-=^"
        _sparkline = ""
        for _val in _recent:
            _idx = int((_val - _spark_min) / _spark_range * (len(_spark_chars) - 1))
            _sparkline += _spark_chars[_idx]

        mo.md(
            f"""
    ## Learning Loop

    **{_n} reward events** recorded. Current mean reward: **{_current_mean:.3f}**

    Recent trend: `{_sparkline}`

    ### Outcome Breakdown

    | Outcome | Count | Share |
    |---------|-------|-------|
    {_outcome_table}

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

    _sessions = []
    _sessions_path = buildlog_dir / ".buildlog" / "sessions.jsonl"
    if _sessions_path.exists():
        for _line in _sessions_path.read_text().splitlines():
            _line = _line.strip()
            if _line:
                try:
                    _sessions.append(_json.loads(_line))
                except _json.JSONDecodeError:
                    continue

    if _sessions:
        _session_rows = []
        for _sess in reversed(_sessions[-10:]):
            _sid = _sess.get("id", "?")[:20]
            _started = _sess.get("started_at", "?")[:10]
            _rs = len(_sess.get("rules_at_start", []))
            _re = len(_sess.get("rules_at_end", []))
            _ec = _sess.get("error_class", "general") or "general"
            _delta = _re - _rs
            _delta_str = f"+{_delta}" if _delta > 0 else str(_delta)
            _session_rows.append(
                f"| {_started} | `{_sid}` | {_ec} | {_rs} | {_re} | {_delta_str} |"
            )

        _session_table = "\n".join(_session_rows)

        mo.md(
            f"""
    ## Session History

    **{len(_sessions)} sessions** recorded. Showing last 10.

    | Date | Session | Error Class | Rules Start | Rules End | Delta |
    |------|---------|-------------|-------------|-----------|-------|
    {_session_table}

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

    _mistakes = []
    _mistakes_path = buildlog_dir / ".buildlog" / "mistakes.jsonl"
    if _mistakes_path.exists():
        for _line in _mistakes_path.read_text().splitlines():
            _line = _line.strip()
            if _line:
                try:
                    _mistakes.append(_json2.loads(_line))
                except _json2.JSONDecodeError:
                    continue

    if _mistakes:
        _error_classes: dict[str, int] = {}
        _repeats = 0
        for _m in _mistakes:
            _ec = _m.get("error_class", "unknown")
            _error_classes[_ec] = _error_classes.get(_ec, 0) + 1
            if _m.get("was_repeat", False):
                _repeats += 1

        _repeat_pct = _repeats / len(_mistakes) * 100

        _ec_rows = []
        for _ecname, _eccnt in sorted(
            _error_classes.items(), key=lambda x: x[1], reverse=True
        ):
            _ec_rows.append(f"| {_ecname} | {_eccnt} |")
        _ec_table = "\n".join(_ec_rows)

        mo.md(
            f"""
    ## Mistake Analysis

    **{len(_mistakes)} mistakes** logged across {len(_error_classes)} error classes.
    **{_repeats} repeats** ({_repeat_pct:.0f}% repeat rate).

    A declining repeat rate means the rules are preventing recurrence.

    ### By Error Class

    | Error Class | Count |
    |-------------|-------|
    {_ec_table}
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
    _bandit_stats = {}
    try:
        from buildlog.core.learning import get_learning_backend

        _lb = get_learning_backend(buildlog_dir)
        _bandit_stats = _lb.get_stats(None)
    except Exception:
        pass

    if _bandit_stats:
        _sorted_arms = sorted(
            _bandit_stats.items(), key=lambda x: x[1].get("mean", 0), reverse=True
        )

        _arm_rows = []
        for _rule_id, _arm in _sorted_arms[:15]:
            _mean = _arm.get("mean", 0)
            _obs = int(_arm.get("total_observations", 0))
            _ci = _arm.get("confidence_interval", (0, 1))
            _ci_str = f"[{_ci[0]:.2f}, {_ci[1]:.2f}]"

            if _obs == 0:
                _status = "new"
            elif _mean >= 0.7:
                _status = "earning confidence"
            elif _mean < 0.4:
                _status = "demoted"
            else:
                _status = "stable"

            _arm_rows.append(
                f"| `{_rule_id}` | {_mean:.3f} | {_obs} | {_ci_str} | {_status} |"
            )

        _arm_table = "\n".join(_arm_rows)

        mo.md(
            f"""
    ## Bandit Arm Posteriors

    **{len(_bandit_stats)} rules** tracked by the Thompson Sampling bandit.
    Showing top 15 by posterior mean.

    | Rule | Mean | Observations | 95% CI | Status |
    |------|------|-------------|--------|--------|
    {_arm_table}

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
    _warnings = stats.warnings
    _sources = stats.top_sources

    _parts = []

    if _sources:
        _source_rows = []
        for _i, _src in enumerate(_sources, 1):
            _source_rows.append(f"| {_i} | {_src['name']} | {_src['insights']} |")
        _source_table = "\n".join(_source_rows)
        _parts.append(
            f"""### Top Sources

| Rank | Entry | Insights |
|------|-------|----------|
{_source_table}"""
        )

    if _warnings:
        _warning_items = "\n".join(f"- {_w}" for _w in _warnings)
        _parts.append(
            f"""### Quality Warnings

{_warning_items}"""
        )

    if _parts:
        mo.md("## Health\n\n" + "\n\n".join(_parts))
    else:
        mo.md("## Health\n\nNo warnings. Everything looks good.")
    return


if __name__ == "__main__":
    app.run()
