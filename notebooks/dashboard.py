import marimo

__generated_with = "0.19.5"
app = marimo.App(width="medium", app_title="buildlog dashboard")


@app.cell
def _():
    import marimo as mo

    mo.md(
        """
    # buildlog dashboard

    Live view of your learning loop data. Every chart is evidence
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

    # Get SQLite backend for event data
    try:
        from buildlog.storage import get_backend

        backend, project_id = get_backend()
    except Exception:
        backend, project_id = None, None

    mo.md(f"**Data source**: `{buildlog_dir.resolve()}`")
    return backend, buildlog_dir, project_id


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
    import matplotlib.pyplot as plt

    _categories = stats.insights.by_category
    _total = stats.insights.total

    if _total > 0:
        _names = [c.replace("_", " ").title() for c in _categories]
        _counts = list(_categories.values())
        _colors = ["#2563eb", "#7c3aed", "#059669", "#d97706"]

        _fig, _ax = plt.subplots(figsize=(8, 3))
        _bars = _ax.barh(
            _names, _counts, color=_colors[: len(_names)], edgecolor="none", height=0.6
        )
        _ax.set_xlabel("Count")
        _ax.set_title(f"Insights by Category ({_total} total)")
        _ax.invert_yaxis()
        for _bar, _cnt in zip(_bars, _counts):
            _ax.text(
                _bar.get_width() + 0.3,
                _bar.get_y() + _bar.get_height() / 2,
                str(_cnt),
                va="center",
                fontsize=10,
                fontweight="bold",
            )
        _ax.spines["top"].set_visible(False)
        _ax.spines["right"].set_visible(False)
        plt.tight_layout()

        mo.vstack(
            [
                mo.as_html(_fig),
                mo.md(f"*{_total} insights across {len(_categories)} categories*"),
            ]
        )
    else:
        mo.md(
            "## Insights\n\nNo insights yet. Run `buildlog distill` to extract patterns."
        )
    return


@app.cell
def _(backend, mo, project_id):
    import matplotlib.pyplot as _plt2

    _reward_events = []
    if backend and project_id:
        try:
            _reward_events = backend.load_events(project_id, "rewards")
        except Exception:
            pass

    if _reward_events:
        _total_reward = 0.0
        _running_means = []
        _outcomes = {"accepted": 0, "revision": 0, "rejected": 0}

        for _i, _evt in enumerate(_reward_events, 1):
            _total_reward += _evt.get("reward_value", 0.0)
            _running_means.append(_total_reward / _i)
            _oname = _evt.get("outcome", "unknown")
            if _oname in _outcomes:
                _outcomes[_oname] += 1

        _current_mean = _running_means[-1] if _running_means else 0.0
        _n = len(_reward_events)

        # Line chart: running mean reward
        _fig2, (_ax_line, _ax_pie) = _plt2.subplots(1, 2, figsize=(10, 4))

        _ax_line.plot(
            range(1, len(_running_means) + 1),
            _running_means,
            color="#2563eb",
            linewidth=2,
        )
        _ax_line.fill_between(
            range(1, len(_running_means) + 1),
            _running_means,
            alpha=0.15,
            color="#2563eb",
        )
        _ax_line.set_xlabel("Event #")
        _ax_line.set_ylabel("Running Mean Reward")
        _ax_line.set_title(f"Reward Trend (current: {_current_mean:.3f})")
        _ax_line.set_ylim(0, 1.05)
        _ax_line.spines["top"].set_visible(False)
        _ax_line.spines["right"].set_visible(False)

        # Pie chart: outcome breakdown
        _pie_labels = []
        _pie_sizes = []
        _pie_colors = ["#059669", "#d97706", "#dc2626"]
        for _olabel, _ocolor in zip(["accepted", "revision", "rejected"], _pie_colors):
            if _outcomes[_olabel] > 0:
                _pie_labels.append(f"{_olabel}\n({_outcomes[_olabel]})")
                _pie_sizes.append(_outcomes[_olabel])

        if _pie_sizes:
            _ax_pie.pie(
                _pie_sizes,
                labels=_pie_labels,
                colors=_pie_colors[: len(_pie_sizes)],
                autopct="%1.0f%%",
                startangle=90,
                textprops={"fontsize": 10},
            )
        _ax_pie.set_title(f"Outcomes ({_n} events)")

        _plt2.tight_layout()

        mo.vstack(
            [
                mo.md("## Learning Loop"),
                mo.as_html(_fig2),
                mo.md(
                    f"Each reward event teaches the bandit which rules help. "
                    f"**{_n} events** recorded, mean trending "
                    f"{'up' if len(_running_means) > 1 and _running_means[-1] > _running_means[0] else 'flat'}."
                ),
            ]
        )
    else:
        mo.md(
            "## Learning Loop\n\n"
            "No reward events yet. Use `buildlog reward --outcome accepted` after "
            "successful commits to start feeding the learning loop."
        )
    return


@app.cell
def _(backend, mo, project_id):
    import matplotlib.pyplot as _plt3

    _sessions = []
    if backend and project_id:
        try:
            _sessions = backend.load_events(project_id, "sessions")
        except Exception:
            pass

    if _sessions:
        _dates = []
        _rules_start = []
        _rules_end = []

        for _sess in _sessions[-15:]:
            _dt = _sess.get("started_at", "?")[:10]
            _dates.append(_dt)
            _rs_list = _sess.get("rules_at_start", [])
            _re_list = _sess.get("rules_at_end", [])
            _rs_count = len(_rs_list) if isinstance(_rs_list, list) else 0
            _re_count = len(_re_list) if isinstance(_re_list, list) else 0
            _rules_start.append(_rs_count)
            _rules_end.append(_re_count)

        _fig3, _ax3 = _plt3.subplots(figsize=(10, 4))
        _x = range(len(_dates))
        _ax3.bar(
            [i - 0.15 for i in _x],
            _rules_start,
            width=0.3,
            label="Rules at start",
            color="#93c5fd",
            edgecolor="none",
        )
        _ax3.bar(
            [i + 0.15 for i in _x],
            _rules_end,
            width=0.3,
            label="Rules at end",
            color="#2563eb",
            edgecolor="none",
        )
        _ax3.set_xticks(list(_x))
        _ax3.set_xticklabels(_dates, rotation=45, ha="right", fontsize=8)
        _ax3.set_ylabel("Rule Count")
        _ax3.set_title(f"Session History ({len(_sessions)} total)")
        _ax3.legend(fontsize=9)
        _ax3.spines["top"].set_visible(False)
        _ax3.spines["right"].set_visible(False)
        _plt3.tight_layout()

        mo.vstack(
            [
                mo.md("## Session History"),
                mo.as_html(_fig3),
                mo.md(
                    "Rule count growth over sessions indicates the system is learning "
                    "and promoting new rules based on observed patterns."
                ),
            ]
        )
    else:
        mo.md(
            "## Session History\n\n"
            "No sessions recorded yet. Use `buildlog experiment start` to begin tracking."
        )
    return


@app.cell
def _(backend, mo, project_id):
    import matplotlib.pyplot as _plt4

    _mistakes = []
    if backend and project_id:
        try:
            _mistakes = backend.load_events(project_id, "mistakes")
        except Exception:
            pass

    if _mistakes:
        _error_classes: dict[str, int] = {}
        _repeats = 0
        for _m in _mistakes:
            _ec = _m.get("error_class", "unknown")
            _error_classes[_ec] = _error_classes.get(_ec, 0) + 1
            if _m.get("was_repeat", False):
                _repeats += 1

        _repeat_pct = _repeats / len(_mistakes) * 100
        _novel_pct = 100 - _repeat_pct

        _fig4, (_ax_bar, _ax_gauge) = _plt4.subplots(1, 2, figsize=(10, 4))

        # Bar chart: by error class
        _ec_names = list(_error_classes.keys())
        _ec_counts = list(_error_classes.values())
        _sorted_idx = sorted(range(len(_ec_counts)), key=lambda k: _ec_counts[k])
        _ec_names = [_ec_names[k] for k in _sorted_idx]
        _ec_counts = [_ec_counts[k] for k in _sorted_idx]

        _ax_bar.barh(
            _ec_names, _ec_counts, color="#dc2626", edgecolor="none", height=0.6
        )
        _ax_bar.set_xlabel("Count")
        _ax_bar.set_title(f"By Error Class ({len(_mistakes)} mistakes)")
        _ax_bar.spines["top"].set_visible(False)
        _ax_bar.spines["right"].set_visible(False)

        # Donut chart: repeat vs novel
        _ax_gauge.pie(
            [_novel_pct, _repeat_pct],
            labels=[
                f"Novel\n({100 - _repeat_pct:.0f}%)",
                f"Repeat\n({_repeat_pct:.0f}%)",
            ],
            colors=["#059669", "#dc2626"],
            startangle=90,
            wedgeprops={"width": 0.4},
            textprops={"fontsize": 10},
        )
        _ax_gauge.set_title("Repeat Rate")

        _plt4.tight_layout()

        mo.vstack(
            [
                mo.md("## Mistake Analysis"),
                mo.as_html(_fig4),
                mo.md(
                    f"**{_repeats} repeats** out of {len(_mistakes)} mistakes "
                    f"({_repeat_pct:.0f}% repeat rate). "
                    f"A declining repeat rate means the rules are preventing recurrence."
                ),
            ]
        )
    else:
        mo.md(
            "## Mistake Analysis\n\n"
            "No mistakes logged yet. When the gauntlet catches issues "
            "during sessions, they appear here."
        )
    return


@app.cell
def _(buildlog_dir, mo):
    import matplotlib.pyplot as _plt5

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
        )[:15]

        _rule_ids = []
        _means = []
        _ci_lows = []
        _ci_highs = []
        _colors = []

        for _rid, _arm in reversed(_sorted_arms):
            _mean = _arm.get("mean", 0)
            _obs = int(_arm.get("total_observations", 0))
            _ci = _arm.get("confidence_interval", (0, 1))

            _short_id = _rid[:25] + "..." if len(_rid) > 28 else _rid
            _rule_ids.append(_short_id)
            _means.append(_mean)
            _ci_lows.append(_mean - _ci[0])
            _ci_highs.append(_ci[1] - _mean)

            if _obs == 0:
                _colors.append("#9ca3af")  # gray: new
            elif _mean >= 0.7:
                _colors.append("#059669")  # green: confident
            elif _mean < 0.4:
                _colors.append("#dc2626")  # red: demoted
            else:
                _colors.append("#2563eb")  # blue: stable

        _fig5, _ax5 = _plt5.subplots(figsize=(10, max(4, len(_sorted_arms) * 0.4)))
        _ax5.barh(
            range(len(_rule_ids)),
            _means,
            xerr=[_ci_lows, _ci_highs],
            color=_colors,
            edgecolor="none",
            height=0.6,
            capsize=3,
            error_kw={"linewidth": 1, "color": "#6b7280"},
        )
        _ax5.set_yticks(range(len(_rule_ids)))
        _ax5.set_yticklabels(_rule_ids, fontsize=8)
        _ax5.set_xlabel("Posterior Mean")
        _ax5.set_xlim(0, 1.05)
        _ax5.set_title(f"Bandit Posteriors ({len(_bandit_stats)} rules)")
        _ax5.axvline(
            x=0.7, color="#059669", linestyle="--", alpha=0.4, label="confidence"
        )
        _ax5.axvline(
            x=0.4, color="#dc2626", linestyle="--", alpha=0.4, label="demotion"
        )
        _ax5.legend(fontsize=8, loc="lower right")
        _ax5.spines["top"].set_visible(False)
        _ax5.spines["right"].set_visible(False)
        _plt5.tight_layout()

        mo.vstack(
            [
                mo.md("## Bandit Arm Posteriors"),
                mo.as_html(_fig5),
                mo.md(
                    "Green = earned confidence (mean >= 0.7). "
                    "Blue = stable. Red = demoted (mean < 0.4). "
                    "Gray = new (no observations). Error bars show 95% CI."
                ),
            ]
        )
    else:
        mo.md(
            "## Bandit Arm Posteriors\n\n"
            "No bandit data available. The Thompson Sampling bandit starts tracking "
            "rules after the first session with reward events."
        )
    return


@app.cell
def _(mo, stats):
    _warnings = stats.warnings
    _sources = stats.top_sources

    _parts = []

    if _sources:
        _source_rows = []
        for _idx, _src in enumerate(_sources, 1):
            _source_rows.append(f"| {_idx} | {_src['name']} | {_src['insights']} |")
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
