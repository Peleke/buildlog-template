# /// script
# [tool.marimo.display]
# theme = "dark"
# ///

import marimo

__generated_with = "0.19.5"
app = marimo.App(width="full", app_title="buildlog dashboard")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    import json
    import os
    import sqlite3
    import sys
    from pathlib import Path

    import plotly.graph_objects as go
    import plotly.io as pio

    pio.templates.default = "plotly_dark"

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

    try:
        from buildlog.storage import get_backend

        backend, current_project_id = get_backend()
    except Exception:
        backend, current_project_id = None, None

    # --- Build project selector ---
    _project_options = {"All Projects": "__all__"}
    if backend:
        try:
            _projects = backend.list_projects()
            for _p in _projects:
                _label = _p["name"]
                if _p["id"] == current_project_id:
                    _label += " (current)"
                _project_options[_label] = _p["id"]
        except Exception:
            pass

    project_selector = mo.ui.dropdown(
        options=_project_options,
        value="All Projects",
        label="Project scope",
    )

    # --- Design tokens ---
    BLUE = "#3b82f6"
    GREEN = "#22c55e"
    RED = "#ef4444"
    AMBER = "#f59e0b"
    PURPLE = "#a855f7"
    CYAN = "#06b6d4"
    GRAY = "#6b7280"
    MUTED = "#94a3b8"
    BORDER = "#334155"
    CARD_BG = "#1e293b"
    TEXT = "#e2e8f0"

    LAYOUT = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, family="Inter, system-ui, sans-serif", size=12),
        margin=dict(l=60, r=20, t=50, b=40),
    )

    def kpi_card(value, label, color, subtitle=None):
        """Styled KPI card with optional subtitle."""
        _sub = (
            f'<div style="color:{MUTED}; font-size:0.7rem; margin-top:2px;">{subtitle}</div>'
            if subtitle
            else ""
        )
        return mo.md(
            f'<div style="text-align:center; padding:1.25rem 1.5rem; '
            f"border:1px solid {BORDER}; border-radius:12px; "
            f'background:linear-gradient(135deg, {CARD_BG} 0%, rgba(30,41,59,0.5) 100%);">'
            f'<div style="font-size:2rem; font-weight:700; color:{color}; '
            f'letter-spacing:-0.02em; line-height:1;">{value}</div>'
            f'<div style="color:{MUTED}; font-size:0.8rem; margin-top:6px; '
            f'text-transform:uppercase; letter-spacing:0.05em;">{label}</div>'
            f"{_sub}</div>"
        )

    def section_header(title, description):
        """Section description block, following the qortex Grafana pattern."""
        return mo.md(
            f'<div style="border-left:3px solid {BLUE}; padding:0.5rem 0 0.5rem 1rem; '
            f'margin:0.25rem 0 1rem 0;">'
            f'<div style="font-size:0.95rem; font-weight:600; color:{TEXT}; '
            f'margin-bottom:4px;">{title}</div>'
            f'<div style="font-size:0.8rem; color:{MUTED}; line-height:1.5;">'
            f"{description}</div></div>"
        )

    def panel_note(text):
        """Subtle annotation below a chart."""
        return mo.md(
            f'<div style="font-size:0.75rem; color:{MUTED}; padding:0 0.5rem; '
            f'line-height:1.4; margin-top:-0.25rem;">{text}</div>'
        )

    mo.md(
        f"""
    <div style="text-align:center; padding:1.5rem 0 0.5rem 0;">
    <h1 style="margin:0; font-size:1.75rem; font-weight:700;
    letter-spacing:-0.03em; color:{TEXT};">buildlog</h1>
    <p style="color:{MUTED}; margin:0.25rem 0 0 0; font-size:0.85rem;">
    learning loop dashboard
    </p>
    </div>
    """
    )
    return (
        AMBER,
        BLUE,
        BORDER,
        CARD_BG,
        CYAN,
        GRAY,
        GREEN,
        LAYOUT,
        MUTED,
        PURPLE,
        RED,
        TEXT,
        backend,
        buildlog_dir,
        current_project_id,
        go,
        json,
        kpi_card,
        panel_note,
        project_selector,
        section_header,
        sqlite3,
    )


@app.cell
def _(backend, current_project_id, mo, project_selector, MUTED):
    """Derive the active project scope from the dropdown."""

    mo.hstack(
        [project_selector],
        justify="center",
        gap=1,
    )

    _sel = project_selector.value
    if _sel == "__all__" or _sel is None:
        selected_project_id = None
    else:
        selected_project_id = _sel

    def load_events_scoped(table):
        """Load events respecting the project selector."""
        if not backend:
            return []
        try:
            if selected_project_id:
                return backend.load_events(selected_project_id, table)
            else:
                return backend.load_events_global(table)
        except Exception:
            return []

    _scope_label = (
        "all projects" if not selected_project_id else selected_project_id[:12]
    )
    scope_note = mo.md(
        f'<div style="text-align:center; font-size:0.75rem; color:{MUTED}; '
        f'margin-bottom:0.5rem;">Showing data for: <strong>{_scope_label}</strong></div>'
    )

    return load_events_scoped, scope_note, selected_project_id


@app.cell
def _(
    AMBER,
    BLUE,
    GRAY,
    GREEN,
    LAYOUT,
    MUTED,
    RED,
    buildlog_dir,
    go,
    kpi_card,
    load_events_scoped,
    mo,
    panel_note,
    scope_note,
    section_header,
):
    """Overview + Learning Loop tab."""
    from buildlog.stats import calculate_stats

    stats = calculate_stats(buildlog_dir)
    _e = stats.entries
    _s = stats.streak

    _header = section_header(
        "Learning Loop Overview",
        "The core feedback cycle: commit &rarr; review &rarr; reward. "
        "Reward trend tracks whether reviews are improving over time. "
        "A healthy system shows a running mean above 0.7 (green line). "
        "Sustained drops below 0.4 (red line) indicate the review process needs attention.",
    )

    _kpis = mo.hstack(
        [
            kpi_card(_e.total, "entries", BLUE, f"{_e.this_month} this month"),
            kpi_card(f"{_s.current}d", "streak", GREEN, f"best: {_s.longest}d"),
            kpi_card(f"{_e.coverage_percent}%", "coverage", AMBER),
            kpi_card(_e.this_week, "this week", RED if _e.this_week == 0 else BLUE),
        ],
        justify="center",
        gap=1,
    )

    # --- Reward trend ---
    _reward_events = load_events_scoped("rewards")

    _reward_chart = None
    if _reward_events:
        _running = []
        _total_r = 0.0
        _outcomes = {"accepted": 0, "revision": 0, "rejected": 0}
        for _i, _evt in enumerate(_reward_events, 1):
            _total_r += _evt.get("reward_value", 0.0)
            _running.append(_total_r / _i)
            _o = _evt.get("outcome", "unknown")
            if _o in _outcomes:
                _outcomes[_o] += 1

        _fig_r = go.Figure()
        _fig_r.add_trace(
            go.Scatter(
                y=_running,
                mode="lines",
                fill="tozeroy",
                line=dict(color=BLUE, width=2),
                fillcolor="rgba(59,130,246,0.12)",
                name="Running mean",
                hovertemplate="Event %{x}<br>Mean: %{y:.3f}<extra></extra>",
            )
        )
        _fig_r.add_hline(
            y=0.7,
            line_dash="dash",
            line_color=GREEN,
            opacity=0.5,
            annotation_text="target",
            annotation_position="right",
            annotation_font_color=MUTED,
            annotation_font_size=10,
        )
        _fig_r.add_hline(
            y=0.4,
            line_dash="dash",
            line_color=RED,
            opacity=0.5,
            annotation_text="investigate",
            annotation_position="right",
            annotation_font_color=MUTED,
            annotation_font_size=10,
        )
        _fig_r.update_layout(
            **LAYOUT,
            title=dict(
                text=f"Reward Trend ({len(_reward_events)} events, mean {_running[-1]:.3f})",
                font=dict(size=14),
            ),
            yaxis=dict(
                range=[0, 1.05],
                title="Running Mean",
                gridcolor="rgba(255,255,255,0.05)",
            ),
            xaxis=dict(title="Event #", gridcolor="rgba(255,255,255,0.05)"),
            height=320,
            showlegend=False,
        )
        _reward_chart = mo.ui.plotly(_fig_r)
    else:
        _reward_chart = mo.md(
            f'<p style="color:{GRAY}; text-align:center; padding:2rem;">'
            f"No reward events yet. Use <code>buildlog_log_reward()</code> after PR merges.</p>"
        )

    # --- Outcome distribution ---
    _outcome_chart = None
    if _reward_events:
        _labels = [k for k, v in _outcomes.items() if v > 0]
        _values = [v for v in _outcomes.values() if v > 0]
        _colors_pie = [GREEN, AMBER, RED][: len(_labels)]
        _fig_o = go.Figure(
            go.Pie(
                labels=_labels,
                values=_values,
                marker=dict(
                    colors=_colors_pie, line=dict(width=1, color="rgba(0,0,0,0.3)")
                ),
                hole=0.6,
                textinfo="label+percent",
                textfont=dict(size=11),
                hovertemplate="%{label}: %{value}<extra></extra>",
            )
        )
        _fig_o.update_layout(
            **LAYOUT,
            title=dict(text="Outcomes", font=dict(size=14)),
            height=320,
            showlegend=False,
        )
        _outcome_chart = mo.ui.plotly(_fig_o)
    else:
        _outcome_chart = mo.md("")

    _reward_note = panel_note(
        "Running mean of reward values (accepted=1.0, revision=0.5, rejected=0.0). "
        "Each event is one PR review cycle."
    )

    overview_tab = mo.vstack(
        [
            scope_note,
            _header,
            _kpis,
            mo.hstack([_reward_chart, _outcome_chart], widths=[0.65, 0.35]),
            _reward_note,
        ]
    )
    return overview_tab, stats


@app.cell
def _(
    BLUE,
    CYAN,
    GRAY,
    GREEN,
    LAYOUT,
    MUTED,
    PURPLE,
    RED,
    go,
    kpi_card,
    load_events_scoped,
    mo,
    panel_note,
    section_header,
):
    """Sessions + Mistakes tab."""

    _header = section_header(
        "Sessions & Mistake Patterns",
        "Each session tracks which gauntlet rules were active and what mistakes were logged. "
        "Rule growth (start vs end) shows whether sessions are discovering new patterns. "
        "The Repeated Mistake Rate (RMR) is the key metric: it should trend downward over time. "
        "A rising RMR means the learning loop isn't working. Rules aren't preventing known mistakes.",
    )

    # --- Session history ---
    _sessions = load_events_scoped("sessions")

    _session_chart = None
    if _sessions:
        _dates = []
        _rules_start = []
        _rules_end = []
        for _sess in _sessions[-20:]:
            _dt = _sess.get("started_at", "?")[:10]
            _dates.append(_dt)
            _rs = _sess.get("rules_at_start", [])
            _re = _sess.get("rules_at_end", [])
            _rules_start.append(len(_rs) if isinstance(_rs, list) else 0)
            _rules_end.append(len(_re) if isinstance(_re, list) else 0)

        _fig_s = go.Figure()
        _fig_s.add_trace(
            go.Bar(
                x=_dates,
                y=_rules_start,
                name="Start",
                marker_color=CYAN,
                opacity=0.6,
                hovertemplate="%{x}<br>Rules at start: %{y}<extra></extra>",
            )
        )
        _fig_s.add_trace(
            go.Bar(
                x=_dates,
                y=_rules_end,
                name="End",
                marker_color=BLUE,
                hovertemplate="%{x}<br>Rules at end: %{y}<extra></extra>",
            )
        )
        _fig_s.update_layout(
            **LAYOUT,
            title=dict(
                text=f"Rule Growth Across Sessions ({len(_sessions)} total)",
                font=dict(size=14),
            ),
            barmode="group",
            xaxis=dict(title="Session Date", gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(title="Rule Count", gridcolor="rgba(255,255,255,0.05)"),
            height=350,
        )
        _session_chart = mo.ui.plotly(_fig_s)
    else:
        _session_chart = mo.md(
            f'<p style="color:{GRAY}; text-align:center; padding:2rem;">No sessions recorded yet.</p>'
        )

    # --- Mistake analysis ---
    _mistakes = load_events_scoped("mistakes")

    _mistake_kpis = None
    _mistake_chart = None
    _rmr_chart = None
    if _mistakes:
        _ec_counts: dict[str, int] = {}
        _repeats = 0
        for _m in _mistakes:
            _ec = _m.get("error_class", "unknown")
            _ec_counts[_ec] = _ec_counts.get(_ec, 0) + 1
            if _m.get("was_repeat", False):
                _repeats += 1

        _repeat_pct = _repeats / len(_mistakes) * 100
        _unique_classes = len(_ec_counts)

        _mistake_kpis = mo.hstack(
            [
                kpi_card(len(_mistakes), "total mistakes", RED),
                kpi_card(
                    f"{_repeat_pct:.0f}%",
                    "repeat rate",
                    PURPLE if _repeat_pct < 30 else RED,
                ),
                kpi_card(_unique_classes, "error classes", MUTED),
            ],
            justify="center",
            gap=1,
        )

        _sorted_ec = sorted(_ec_counts.items(), key=lambda x: x[1])
        _ec_names = [k for k, _ in _sorted_ec]
        _ec_vals = [v for _, v in _sorted_ec]

        _fig_m = go.Figure()
        _fig_m.add_trace(
            go.Bar(
                y=_ec_names,
                x=_ec_vals,
                orientation="h",
                marker_color=RED,
                text=_ec_vals,
                textposition="outside",
                hovertemplate="%{y}: %{x} occurrences<extra></extra>",
            )
        )
        _fig_m.update_layout(
            **LAYOUT,
            title=dict(text="Mistakes by Error Class", font=dict(size=14)),
            height=max(250, len(_ec_names) * 35 + 100),
            xaxis=dict(title="Count", gridcolor="rgba(255,255,255,0.05)"),
        )
        _mistake_chart = mo.ui.plotly(_fig_m)

        # --- RMR over time ---
        _session_rmr: dict[str, list[bool]] = {}
        for _m in _mistakes:
            _sid = _m.get("session_id", "unknown")
            if _sid not in _session_rmr:
                _session_rmr[_sid] = []
            _session_rmr[_sid].append(bool(_m.get("was_repeat", False)))

        if len(_session_rmr) > 1:
            _rmr_values = [
                sum(v) / len(v) * 100 if v else 0 for v in _session_rmr.values()
            ]
            _fig_rmr = go.Figure()
            _fig_rmr.add_trace(
                go.Scatter(
                    x=list(range(1, len(_rmr_values) + 1)),
                    y=_rmr_values,
                    mode="lines+markers",
                    line=dict(color=PURPLE, width=2),
                    marker=dict(size=6, color=PURPLE),
                    fill="tozeroy",
                    fillcolor="rgba(168,85,247,0.08)",
                    hovertemplate="Session %{x}<br>RMR: %{y:.1f}%<extra></extra>",
                )
            )
            _fig_rmr.update_layout(
                **LAYOUT,
                title=dict(text="Repeated Mistake Rate", font=dict(size=14)),
                xaxis=dict(title="Session #", gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(
                    title="RMR %", range=[0, 100], gridcolor="rgba(255,255,255,0.05)"
                ),
                height=300,
                showlegend=False,
            )
            _rmr_chart = mo.ui.plotly(_fig_rmr)
        else:
            _rmr_chart = mo.md(
                f'<p style="color:{GRAY}; text-align:center;">Need 2+ sessions for RMR trend.</p>'
            )
    else:
        _mistake_chart = mo.md(
            f'<p style="color:{GRAY}; text-align:center; padding:2rem;">No mistakes logged yet.</p>'
        )
        _rmr_chart = mo.md("")

    _rmr_note = panel_note(
        "RMR = percentage of mistakes in a session that were previously seen. "
        "Downward trend = the system is learning. "
        "Flat or rising = rules need tuning or new error classes are emerging."
    )

    _parts = [_header, _session_chart]
    if _mistake_kpis:
        _parts.append(_mistake_kpis)
    _parts.append(mo.hstack([_mistake_chart, _rmr_chart], widths=[0.5, 0.5]))
    _parts.append(_rmr_note)

    sessions_tab = mo.vstack(_parts)
    return (sessions_tab,)


@app.cell
def _(
    BLUE,
    GRAY,
    GREEN,
    LAYOUT,
    MUTED,
    RED,
    buildlog_dir,
    go,
    load_events_scoped,
    mo,
    panel_note,
    section_header,
):
    """Bandit posteriors tab."""

    _header = section_header(
        "Bandit & Rule Selection",
        "Each gauntlet rule is modeled as a Thompson Sampling arm. "
        "The bandit tracks which rules lead to accepted PRs (reward=1.0) vs rejections (reward=0.0). "
        "Green bars (mean &ge; 0.7) are high-confidence winners. "
        "Red bars (mean &lt; 0.4) may need revision or retirement. "
        "Wide confidence intervals mean the system needs more observations before it can rank reliably.",
    )

    _bandit_stats = {}
    try:
        from buildlog.core.learning import get_learning_backend

        _lb = get_learning_backend(buildlog_dir)
        _bandit_stats = _lb.get_stats(None)
    except Exception:
        pass

    _bandit_chart = None
    if _bandit_stats:
        _sorted_arms = sorted(
            _bandit_stats.items(), key=lambda x: x[1].get("mean", 0), reverse=True
        )[:20]

        _rids = []
        _means = []
        _ci_lo = []
        _ci_hi = []
        _colors_b = []
        _obs_text = []

        for _rid, _arm in reversed(_sorted_arms):
            _mean = _arm.get("mean", 0)
            _obs = int(_arm.get("total_observations", 0))
            _ci = _arm.get("confidence_interval", (0, 1))

            _short = _rid[:30] + "..." if len(_rid) > 33 else _rid
            _rids.append(_short)
            _means.append(_mean)
            _ci_lo.append(_mean - _ci[0])
            _ci_hi.append(_ci[1] - _mean)
            _obs_text.append(f"n={_obs}")

            if _obs == 0:
                _colors_b.append(GRAY)
            elif _mean >= 0.7:
                _colors_b.append(GREEN)
            elif _mean < 0.4:
                _colors_b.append(RED)
            else:
                _colors_b.append(BLUE)

        _fig_b = go.Figure()
        _fig_b.add_trace(
            go.Bar(
                y=_rids,
                x=_means,
                orientation="h",
                marker_color=_colors_b,
                error_x=dict(
                    type="data", symmetric=False, array=_ci_hi, arrayminus=_ci_lo
                ),
                text=_obs_text,
                textposition="outside",
                textfont=dict(size=10),
                hovertemplate="%{y}<br>Mean: %{x:.3f}<br>%{text}<extra></extra>",
            )
        )
        _fig_b.add_vline(
            x=0.7,
            line_dash="dash",
            line_color=GREEN,
            opacity=0.4,
            annotation_text="strong",
            annotation_position="top",
            annotation_font_color=MUTED,
            annotation_font_size=10,
        )
        _fig_b.add_vline(
            x=0.4,
            line_dash="dash",
            line_color=RED,
            opacity=0.4,
            annotation_text="weak",
            annotation_position="top",
            annotation_font_color=MUTED,
            annotation_font_size=10,
        )
        _fig_b.update_layout(
            **LAYOUT,
            title=dict(
                text=f"Thompson Sampling Posteriors ({len(_bandit_stats)} rules)",
                font=dict(size=14),
            ),
            xaxis=dict(
                range=[0, 1.15],
                title="Posterior Mean",
                gridcolor="rgba(255,255,255,0.05)",
            ),
            height=max(400, len(_sorted_arms) * 28 + 100),
        )
        _bandit_chart = mo.ui.plotly(_fig_b)
    else:
        _bandit_chart = mo.md(
            f'<p style="color:{GRAY}; text-align:center; padding:2rem;">'
            f"No bandit data yet. Start sessions to begin tracking.</p>"
        )

    # --- Rule usage frequency from sessions ---
    _rule_usage: dict[str, int] = {}
    _usage_sessions = load_events_scoped("sessions")

    _usage_chart = None
    if _usage_sessions:
        for _sess in _usage_sessions:
            _sel = _sess.get("selected_rules", [])
            if isinstance(_sel, list):
                for _rid in _sel:
                    _rule_usage[_rid] = _rule_usage.get(_rid, 0) + 1

    if _rule_usage:
        _sorted_usage = sorted(_rule_usage.items(), key=lambda x: x[1])[-15:]
        _u_names = [k[:30] + "..." if len(k) > 33 else k for k, _ in _sorted_usage]
        _u_counts = [v for _, v in _sorted_usage]

        _fig_u = go.Figure()
        _fig_u.add_trace(
            go.Bar(
                y=_u_names,
                x=_u_counts,
                orientation="h",
                marker=dict(color=_u_counts, colorscale=[[0, BLUE], [1, GREEN]]),
                text=_u_counts,
                textposition="outside",
                hovertemplate="%{y}<br>Selected %{x} times<extra></extra>",
            )
        )
        _fig_u.update_layout(
            **LAYOUT,
            title=dict(text="Rule Selection Frequency", font=dict(size=14)),
            xaxis=dict(title="Times Selected", gridcolor="rgba(255,255,255,0.05)"),
            height=max(300, len(_sorted_usage) * 28 + 100),
        )
        _usage_chart = mo.ui.plotly(_fig_u)
    else:
        _usage_chart = mo.md(
            f'<p style="color:{GRAY}; text-align:center;">No rule usage data yet.</p>'
        )

    _bandit_note = panel_note(
        "Posteriors are Beta distributions updated after each reward event. "
        "Error bars show 90% credible intervals. "
        "Selection frequency shows how often the bandit picks each rule across sessions."
    )

    bandit_tab = mo.vstack(
        [
            _header,
            _bandit_chart,
            _bandit_note,
            _usage_chart,
        ]
    )
    return (bandit_tab,)


@app.cell
def _(
    AMBER,
    BLUE,
    CYAN,
    GRAY,
    GREEN,
    LAYOUT,
    MUTED,
    PURPLE,
    RED,
    backend,
    go,
    json,
    kpi_card,
    mo,
    panel_note,
    section_header,
    selected_project_id,
):
    """Emissions tab — signal timeline, artifact breakdown, pipeline health."""
    from collections import defaultdict

    _header = section_header(
        "Emission Pipeline",
        "Every <code>log_mistake()</code>, <code>log_reward()</code>, and "
        "<code>learn_from_review()</code> fires a structured JSON artifact to "
        "<code>~/.buildlog/emissions/</code>. The consumer processes pending "
        "artifacts and extracts relationship edges into SQLite. "
        "A healthy pipeline has zero pending and a steady emission rate. "
        "Spikes indicate burst activity; gaps indicate idle periods or broken hooks.",
    )

    # --- Parse signal.jsonl ---
    _emitted = 0
    _consumed = 0
    _pending_count = 0
    _daily_emissions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    _type_counts: dict[str, int] = defaultdict(int)
    _daily_consumed: dict[str, int] = defaultdict(int)

    try:
        from buildlog.emissions import get_emission_config, list_pending

        _cfg = get_emission_config()
        _all_pending = list_pending(_cfg)
        if selected_project_id:
            _pending_count = sum(
                1 for p in _all_pending if selected_project_id in p.name
            )
        else:
            _pending_count = len(_all_pending)
        if _cfg.signal_log.exists():
            for _line in _cfg.signal_log.read_text().strip().split("\n"):
                try:
                    _evt = json.loads(_line)
                    # Filter to selected project (skip filter when showing all)
                    if (
                        selected_project_id
                        and _evt.get("project_id")
                        and _evt["project_id"] != selected_project_id
                    ):
                        continue
                    _event = _evt.get("event", "")
                    _ts = _evt.get("ts", "")[:10]
                    _atype = _evt.get("type", "unknown")
                    if _event == "emitted":
                        _emitted += 1
                        if _ts:
                            _daily_emissions[_ts][_atype] += 1
                            _type_counts[_atype] += 1
                    elif _event == "consumed":
                        _consumed += 1
                        if _ts:
                            _daily_consumed[_ts] += 1
                except Exception:
                    pass
    except Exception:
        pass

    _edge_count = 0
    if backend:
        try:
            _edge_count = backend.count_emission_edges(project_id=selected_project_id)
        except Exception:
            pass

    # --- KPI cards ---
    _pipeline_kpis = mo.hstack(
        [
            kpi_card(_emitted, "emitted", BLUE, "total artifacts fired"),
            kpi_card(_consumed, "consumed", GREEN, "processed to storage"),
            kpi_card(
                _pending_count,
                "pending",
                GREEN if _pending_count == 0 else AMBER,
                "healthy = 0" if _pending_count == 0 else "run consume_emissions()",
            ),
            kpi_card(_edge_count, "edges", PURPLE, "relationship data stored"),
        ],
        justify="center",
        gap=1,
    )

    # --- Emission rate over time ---
    _type_colors = {
        "mistake_manifest": RED,
        "reward_signal": GREEN,
        "learned_rules": PURPLE,
        "session_summary": CYAN,
    }

    _timeline_chart = None
    if _daily_emissions:
        _all_dates = sorted(_daily_emissions.keys())
        _all_types = sorted(
            _type_counts.keys(), key=lambda t: _type_counts[t], reverse=True
        )

        _fig_timeline = go.Figure()
        for _atype in _all_types:
            _y_vals = [_daily_emissions[d].get(_atype, 0) for d in _all_dates]
            _fig_timeline.add_trace(
                go.Scatter(
                    x=_all_dates,
                    y=_y_vals,
                    mode="lines",
                    name=_atype.replace("_", " "),
                    stackgroup="one",
                    line=dict(width=0.5, color=_type_colors.get(_atype, GRAY)),
                    hovertemplate="%{x}<br>%{fullData.name}: %{y}<extra></extra>",
                )
            )

        if _daily_consumed:
            _consumed_y = [_daily_consumed.get(d, 0) for d in _all_dates]
            _fig_timeline.add_trace(
                go.Scatter(
                    x=_all_dates,
                    y=_consumed_y,
                    mode="lines+markers",
                    name="consumed",
                    line=dict(color=AMBER, width=2, dash="dot"),
                    marker=dict(size=4),
                    hovertemplate="%{x}<br>consumed: %{y}<extra></extra>",
                )
            )

        _fig_timeline.update_layout(
            **LAYOUT,
            title=dict(text="Emission Rate Over Time", font=dict(size=14)),
            xaxis=dict(title="Date", gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(title="Artifacts / Day", gridcolor="rgba(255,255,255,0.05)"),
            height=350,
            legend=dict(orientation="h", y=-0.18, font=dict(size=11)),
        )
        _timeline_chart = mo.ui.plotly(_fig_timeline)
    else:
        _timeline_chart = mo.md(
            f'<p style="color:{GRAY}; text-align:center; padding:2rem;">'
            f"No emission signal data yet.</p>"
        )

    _timeline_note = panel_note(
        "Stacked area shows daily emission volume by artifact type. "
        "Dotted amber overlay shows consumption rate. "
        "When consumed matches emitted, the pipeline is keeping up."
    )

    # --- Artifact type breakdown ---
    _type_chart = None
    if _type_counts:
        _sorted_types = sorted(_type_counts.items(), key=lambda x: x[1], reverse=True)
        _t_names = [k.replace("_", " ") for k, _ in _sorted_types]
        _t_vals = [v for _, v in _sorted_types]
        _t_colors = [_type_colors.get(k, GRAY) for k, _ in _sorted_types]

        _fig_types = go.Figure()
        _fig_types.add_trace(
            go.Bar(
                x=_t_names,
                y=_t_vals,
                marker_color=_t_colors,
                text=_t_vals,
                textposition="outside",
                hovertemplate="%{x}: %{y}<extra></extra>",
            )
        )
        _fig_types.update_layout(
            **LAYOUT,
            title=dict(text="Artifacts by Type", font=dict(size=14)),
            height=300,
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        )
        _type_chart = mo.ui.plotly(_fig_types)
    else:
        _type_chart = mo.md("")

    # --- Emission edges ---
    _edges = []
    if backend:
        try:
            _edges = backend.load_emission_edges(
                project_id=selected_project_id, limit=500
            )
        except Exception:
            pass

    _edge_chart = None
    if _edges:
        _rel_counts: dict[str, int] = {}
        for _edge in _edges:
            _rt = _edge.get("relation_type", "unknown")
            _rel_counts[_rt] = _rel_counts.get(_rt, 0) + 1

        _rel_sorted = sorted(_rel_counts.items(), key=lambda x: x[1], reverse=True)
        _fig_rel = go.Figure(
            go.Pie(
                labels=[k for k, _ in _rel_sorted],
                values=[v for _, v in _rel_sorted],
                marker=dict(
                    colors=[BLUE, GREEN, PURPLE, AMBER, CYAN, RED, GRAY][
                        : len(_rel_sorted)
                    ],
                    line=dict(width=1, color="rgba(0,0,0,0.3)"),
                ),
                hole=0.55,
                textinfo="label+value",
                textfont=dict(size=11),
            )
        )
        _fig_rel.update_layout(
            **LAYOUT,
            title=dict(text=f"Edge Types ({len(_edges)} edges)", font=dict(size=14)),
            height=300,
        )
        _edge_chart = mo.ui.plotly(_fig_rel)
    else:
        _edge_chart = mo.md(
            f'<div style="text-align:center; padding:1.5rem; '
            f'border:1px dashed {GRAY}; border-radius:8px; margin:0.5rem;">'
            f'<div style="color:{MUTED}; font-size:0.85rem; line-height:1.5;">'
            f"Edge data accumulates as new sessions run with v0.17+.<br>"
            f"Older artifacts ({_consumed} consumed) predate the edge mapper."
            f"</div></div>"
        )

    emissions_tab = mo.vstack(
        [
            _header,
            _pipeline_kpis,
            _timeline_chart,
            _timeline_note,
            mo.hstack([_type_chart, _edge_chart], widths=[0.55, 0.45]),
        ]
    )
    return (emissions_tab,)


@app.cell
def _(
    AMBER,
    BLUE,
    GRAY,
    GREEN,
    LAYOUT,
    MUTED,
    RED,
    backend,
    go,
    kpi_card,
    mo,
    panel_note,
    section_header,
    selected_project_id,
    stats,
):
    """Insights + Health tab."""

    _header = section_header(
        "Insights & System Health",
        "Insights are patterns extracted from journal entries via <code>buildlog distill</code>. "
        "Review learnings track which gauntlet findings get reinforced (seen again) vs contradicted "
        "(later proven wrong). High reinforcement counts validate the review process. "
        "Contradictions surface rules that may need updating.",
    )

    # --- Insights by category ---
    _categories = stats.insights.by_category
    _total_insights = stats.insights.total

    _insight_kpis = mo.hstack(
        [
            kpi_card(_total_insights, "insights", BLUE),
            kpi_card(len(_categories), "categories", AMBER),
        ],
        justify="center",
        gap=1,
    )

    _insights_chart = None
    if _total_insights > 0:
        _cat_names = [c.replace("_", " ").title() for c in _categories]
        _cat_counts = list(_categories.values())
        _cat_colors = [BLUE, AMBER, GREEN, RED, MUTED]

        _fig_i = go.Figure()
        _fig_i.add_trace(
            go.Bar(
                y=_cat_names,
                x=_cat_counts,
                orientation="h",
                marker_color=_cat_colors[: len(_cat_names)],
                text=_cat_counts,
                textposition="outside",
                hovertemplate="%{y}: %{x}<extra></extra>",
            )
        )
        _fig_i.update_layout(
            **LAYOUT,
            title=dict(text="Insights by Category", font=dict(size=14)),
            height=max(220, len(_cat_names) * 40 + 80),
            xaxis=dict(title="Count", gridcolor="rgba(255,255,255,0.05)"),
        )
        _insights_chart = mo.ui.plotly(_fig_i)
    else:
        _insights_chart = mo.md(
            f'<p style="color:{GRAY}; text-align:center; padding:2rem;">'
            f"No insights yet. Run <code>buildlog distill</code> to extract patterns.</p>"
        )

    # --- Review learnings ---
    _learnings = []
    if backend:
        try:
            if selected_project_id:
                _rows = backend.conn.execute(
                    "SELECT rule, reinforcement_count, contradiction_count, category "
                    "FROM review_learnings WHERE project_id = ? "
                    "ORDER BY reinforcement_count DESC LIMIT 15",
                    (selected_project_id,),
                ).fetchall()
            else:
                _rows = backend.conn.execute(
                    "SELECT rule, reinforcement_count, contradiction_count, category "
                    "FROM review_learnings "
                    "ORDER BY reinforcement_count DESC LIMIT 15",
                ).fetchall()
            _learnings = [dict(r) for r in _rows]
        except Exception:
            pass

    _learnings_chart = None
    if _learnings:
        _l_names = [
            r["rule"][:40] + "..." if len(r["rule"]) > 43 else r["rule"]
            for r in _learnings
        ]
        _l_reinf = [r["reinforcement_count"] for r in _learnings]
        _l_contra = [r["contradiction_count"] for r in _learnings]

        _fig_l = go.Figure()
        _fig_l.add_trace(
            go.Bar(
                y=list(reversed(_l_names)),
                x=list(reversed(_l_reinf)),
                orientation="h",
                name="Reinforced",
                marker_color=GREEN,
            )
        )
        _fig_l.add_trace(
            go.Bar(
                y=list(reversed(_l_names)),
                x=list(reversed(_l_contra)),
                orientation="h",
                name="Contradicted",
                marker_color=RED,
            )
        )
        _fig_l.update_layout(
            **LAYOUT,
            title=dict(text="Review Learnings", font=dict(size=14)),
            barmode="group",
            height=max(300, len(_learnings) * 28 + 100),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        )
        _learnings_chart = mo.ui.plotly(_fig_l)
    else:
        _learnings_chart = mo.md(
            f'<p style="color:{GRAY}; text-align:center; padding:2rem;">'
            f"No review learnings yet. Run the gauntlet to start building learnings.</p>"
        )

    _learnings_note = panel_note(
        "Green = reinforced (seen again in later reviews). "
        "Red = contradicted (later evidence disagreed). "
        "High reinforcement with zero contradictions = strong signal."
    )

    # --- System health ---
    _warnings = stats.warnings
    _sources = stats.top_sources

    _health_parts = []
    if _sources:
        _rows_md = "\n".join(
            f"| {i} | {s['name']} | {s['insights']} |"
            for i, s in enumerate(_sources, 1)
        )
        _health_parts.append(
            f"#### Top Sources\n\n| # | Entry | Insights |\n|---|-------|----------|\n{_rows_md}"
        )
    if _warnings:
        _health_parts.append(
            "#### Warnings\n\n" + "\n".join(f"- {w}" for w in _warnings)
        )
    if not _health_parts:
        _health_parts.append(
            f'<p style="color:{GREEN}; font-size:0.85rem;">All systems nominal.</p>'
        )

    _health_md = mo.md("\n\n".join(_health_parts))

    insights_tab = mo.vstack(
        [
            _header,
            _insight_kpis,
            mo.hstack([_insights_chart, _learnings_chart], widths=[0.45, 0.55]),
            _learnings_note,
            _health_md,
        ]
    )
    return (insights_tab,)


@app.cell
def _(mo, overview_tab, sessions_tab, bandit_tab, emissions_tab, insights_tab):
    """Main tabbed layout."""

    mo.ui.tabs(
        {
            "Overview": overview_tab,
            "Sessions & Mistakes": sessions_tab,
            "Bandit & Rules": bandit_tab,
            "Emissions": emissions_tab,
            "Insights & Health": insights_tab,
        }
    )


if __name__ == "__main__":
    app.run()
