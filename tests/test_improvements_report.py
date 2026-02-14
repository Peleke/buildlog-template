"""Tests for session improvements report (report.py + operations.py integration)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from buildlog.core.report import (
    _CONFIDENCE_THRESHOLD,
    _DEMOTION_THRESHOLD,
    _MARKER_END,
    _MARKER_START,
    ImprovementsReportData,
    RuleStatus,
    classify_rule,
    inject_improvements_into_entry,
    render_improvements_narrative,
    render_improvements_table,
    should_emit_report,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_data(**overrides) -> ImprovementsReportData:
    """Create ImprovementsReportData with sensible defaults."""
    defaults = dict(
        session_id="session-20260213-120000-000000",
        duration_minutes=15.3,
        error_class="missing_test",
        mistakes_caught=3,
        repeated_mistakes=1,
        rules_at_start=5,
        rules_at_end=6,
        mean_reward=0.75,
        rule_statuses=[
            RuleStatus("arch-001", 0.82, 10, "earned_confidence"),
            RuleStatus("wf-002", 0.55, 8, "stable"),
            RuleStatus("sec-003", 0.30, 5, "demoted"),
        ],
    )
    defaults.update(overrides)
    return ImprovementsReportData(**defaults)


# =============================================================================
# TestClassifyRule
# =============================================================================


class TestClassifyRule:
    """Tests for classify_rule()."""

    def test_zero_observations_returns_new(self):
        assert classify_rule(0.9, 0) == "new"

    def test_high_mean_returns_earned_confidence(self):
        assert classify_rule(0.8, 10) == "earned_confidence"

    def test_low_mean_returns_demoted(self):
        assert classify_rule(0.3, 5) == "demoted"

    def test_mid_mean_returns_stable(self):
        assert classify_rule(0.5, 8) == "stable"

    def test_boundary_confidence_threshold(self):
        assert classify_rule(_CONFIDENCE_THRESHOLD, 1) == "earned_confidence"

    def test_boundary_demotion_threshold(self):
        # At exactly _DEMOTION_THRESHOLD (0.4), NOT demoted (< 0.4 required)
        assert classify_rule(_DEMOTION_THRESHOLD, 1) == "stable"


# =============================================================================
# TestShouldEmitReport
# =============================================================================


class TestShouldEmitReport:
    """Tests for should_emit_report()."""

    def test_returns_false_for_zero_data(self):
        data = _make_data(
            mistakes_caught=0,
            rule_statuses=[],
            mean_reward=None,
        )
        assert should_emit_report(data) is False

    def test_returns_true_with_mistakes(self):
        data = _make_data(mistakes_caught=2, rule_statuses=[], mean_reward=None)
        assert should_emit_report(data) is True

    def test_returns_true_with_rewards_only(self):
        data = _make_data(mistakes_caught=0, rule_statuses=[], mean_reward=0.8)
        assert should_emit_report(data) is True

    def test_returns_true_with_rule_statuses(self):
        data = _make_data(
            mistakes_caught=0,
            rule_statuses=[RuleStatus("r1", 0.5, 3, "stable")],
            mean_reward=None,
        )
        assert should_emit_report(data) is True


# =============================================================================
# TestRenderNarrative
# =============================================================================


class TestRenderNarrative:
    """Tests for render_improvements_narrative()."""

    def test_basic_with_mistakes_and_repeats(self):
        data = _make_data()
        result = render_improvements_narrative(data)
        assert "## What Improved This Session" in result
        assert "3 mistakes caught" in result
        assert "1 were repeats" in result

    def test_no_rewards_skips_mean_reward_line(self):
        data = _make_data(mean_reward=None)
        result = render_improvements_narrative(data)
        assert "Mean reward" not in result

    def test_earned_confidence_rules_mentioned(self):
        data = _make_data()
        result = render_improvements_narrative(data)
        assert "`arch-001`" in result
        assert "earning confidence" in result

    def test_demoted_rules_mentioned(self):
        data = _make_data()
        result = render_improvements_narrative(data)
        assert "`sec-003`" in result
        assert "demoted" in result.lower()

    def test_zero_mistakes_clean_session(self):
        data = _make_data(mistakes_caught=0, repeated_mistakes=0)
        result = render_improvements_narrative(data)
        assert "Clean session" in result

    def test_advocacy_blockquote_always_present(self):
        data = _make_data()
        result = render_improvements_narrative(data)
        assert "learning loop works" in result
        assert result.count(">") >= 1

    def test_mean_reward_with_trend_arrow(self):
        data = _make_data(mean_reward=0.8, prior_mean_reward=0.6)
        result = render_improvements_narrative(data)
        assert "0.80" in result
        assert "↑" in result

    def test_error_class_in_context(self):
        data = _make_data(error_class="missing_test")
        result = render_improvements_narrative(data)
        assert "`missing_test`" in result


# =============================================================================
# TestRenderTable
# =============================================================================


class TestRenderTable:
    """Tests for render_improvements_table()."""

    def test_basic_table_with_trends(self):
        data = _make_data(
            prior_mistakes=5,
            prior_repeats=2,
            prior_rules_start=4,
            prior_rules_end=5,
            prior_mean_reward=0.6,
        )
        result = render_improvements_table(data)
        assert "### Metrics" in result
        assert "This Session" in result
        assert "Prior" in result
        assert "Trend" in result

    def test_no_prior_shows_dashes(self):
        data = _make_data()  # No prior_* set
        result = render_improvements_table(data)
        assert "—" in result

    def test_html_comment_anchor_present(self):
        data = _make_data()
        result = render_improvements_table(data)
        assert f"<!-- buildlog:session-summary:{data.session_id} -->" in result

    def test_top_rules_with_status_annotations(self):
        data = _make_data()
        result = render_improvements_table(data)
        assert "### Top Rules" in result
        assert "earned confidence" in result
        assert "stable" in result
        assert "demoted" in result

    def test_no_rules_skips_top_rules_table(self):
        data = _make_data(rule_statuses=[])
        result = render_improvements_table(data)
        assert "### Top Rules" not in result

    def test_rules_sorted_by_mean_descending(self):
        data = _make_data()
        result = render_improvements_table(data)
        lines = result.split("\n")
        rule_lines = [ln for ln in lines if ln.startswith("| `")]
        # arch-001 (0.82) should come before wf-002 (0.55)
        arch_idx = next(i for i, ln in enumerate(rule_lines) if "arch-001" in ln)
        wf_idx = next(i for i, ln in enumerate(rule_lines) if "wf-002" in ln)
        assert arch_idx < wf_idx


# =============================================================================
# TestInjectIntoEntry
# =============================================================================


class TestInjectIntoEntry:
    """Tests for inject_improvements_into_entry()."""

    def test_inserts_before_commits(self):
        content = "# Entry\n\nSome text.\n\n## Commits\n\n- abc123"
        report = "## What Improved\nstuff"
        result = inject_improvements_into_entry(content, report)
        assert _MARKER_START in result
        assert _MARKER_END in result
        # Report should come before ## Commits
        assert result.index(_MARKER_START) < result.index("## Commits")

    def test_appends_when_no_commits(self):
        content = "# Entry\n\nSome text."
        report = "## What Improved\nstuff"
        result = inject_improvements_into_entry(content, report)
        assert _MARKER_START in result
        assert result.endswith(_MARKER_END + "\n")

    def test_idempotent_replaces_between_markers(self):
        content = (
            "# Entry\n\n"
            f"{_MARKER_START}\nold report\n{_MARKER_END}\n\n"
            "## Commits\n\n- abc123"
        )
        report = "## What Improved\nnew stuff"
        result = inject_improvements_into_entry(content, report)
        assert "old report" not in result
        assert "new stuff" in result
        # Only one set of markers
        assert result.count(_MARKER_START) == 1
        assert result.count(_MARKER_END) == 1

    def test_preserves_all_other_content(self):
        content = "# My Entry\n\nImportant notes.\n\n## Commits\n\n- abc123\n- def456"
        report = "## What Improved\nstuff"
        result = inject_improvements_into_entry(content, report)
        assert "# My Entry" in result
        assert "Important notes." in result
        assert "- abc123" in result
        assert "- def456" in result


# =============================================================================
# TestComputeImprovementsData
# =============================================================================


class TestComputeImprovementsData:
    """Tests for _compute_improvements_data()."""

    def test_basic_computation(self):
        from buildlog.core.operations import (
            Mistake,
            RewardSummary,
            Session,
            _compute_improvements_data,
        )

        session = Session(
            id="s1",
            started_at=datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 13, 10, 30, tzinfo=timezone.utc),
            error_class="missing_test",
            rules_at_start=["r1", "r2"],
            rules_at_end=["r1", "r2", "r3"],
        )
        mistakes = [
            Mistake(
                id="m1",
                session_id="s1",
                error_class="missing_test",
                description="forgot test",
                semantic_hash="abc",
                was_repeat=False,
                timestamp=datetime(2026, 2, 13, 10, 5, tzinfo=timezone.utc),
            ),
        ]
        stats = {
            "r1": {"mean": 0.8, "total_observations": 10},
            "r2": {"mean": 0.3, "total_observations": 5},
        }
        reward_summary = RewardSummary(
            total_events=2, accepted=1, revisions=1, rejected=0, mean_reward=0.75
        )

        data = _compute_improvements_data(
            session=session,
            duration=30.0,
            session_mistakes=mistakes,
            stats=stats,
            prior_session=None,
            prior_mistakes=[],
            prior_reward_summary=None,
            current_reward_summary=reward_summary,
        )

        assert data.session_id == "s1"
        assert data.mistakes_caught == 1
        assert data.mean_reward == 0.75
        assert len(data.rule_statuses) == 2
        assert data.prior_mistakes is None

    def test_prior_session_metrics(self):
        from buildlog.core.operations import (
            Mistake,
            RewardSummary,
            Session,
            _compute_improvements_data,
        )

        session = Session(
            id="s2",
            started_at=datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 13, 12, 20, tzinfo=timezone.utc),
            rules_at_start=["r1"],
            rules_at_end=["r1"],
        )
        prior = Session(
            id="s1",
            started_at=datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 13, 10, 30, tzinfo=timezone.utc),
            rules_at_start=["r1", "r2"],
            rules_at_end=["r1", "r2", "r3"],
        )
        prior_mistakes = [
            Mistake(
                id="m0",
                session_id="s1",
                error_class="test",
                description="old",
                semantic_hash="xyz",
                was_repeat=True,
                timestamp=datetime(2026, 2, 13, 10, 5, tzinfo=timezone.utc),
            ),
        ]
        prior_reward = RewardSummary(
            total_events=3, accepted=2, revisions=1, rejected=0, mean_reward=0.66
        )
        current_reward = RewardSummary(
            total_events=0, accepted=0, revisions=0, rejected=0, mean_reward=0.0
        )

        data = _compute_improvements_data(
            session=session,
            duration=20.0,
            session_mistakes=[],
            stats={},
            prior_session=prior,
            prior_mistakes=prior_mistakes,
            prior_reward_summary=prior_reward,
            current_reward_summary=current_reward,
        )

        assert data.prior_mistakes == 1
        assert data.prior_repeats == 1
        assert data.prior_rules_start == 2
        assert data.prior_rules_end == 3
        assert data.prior_mean_reward == 0.66

    def test_no_prior_session(self):
        from buildlog.core.operations import (
            RewardSummary,
            Session,
            _compute_improvements_data,
        )

        session = Session(
            id="s1",
            started_at=datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 13, 10, 30, tzinfo=timezone.utc),
            rules_at_start=[],
            rules_at_end=[],
        )
        current_reward = RewardSummary(
            total_events=0, accepted=0, revisions=0, rejected=0, mean_reward=0.0
        )

        data = _compute_improvements_data(
            session=session,
            duration=30.0,
            session_mistakes=[],
            stats={},
            prior_session=None,
            prior_mistakes=[],
            prior_reward_summary=None,
            current_reward_summary=current_reward,
        )

        assert data.prior_mistakes is None
        assert data.prior_repeats is None
        assert data.prior_rules_start is None
        assert data.prior_rules_end is None
        assert data.prior_mean_reward is None

    def test_reward_summary_zero_events_means_none(self):
        from buildlog.core.operations import (
            RewardSummary,
            Session,
            _compute_improvements_data,
        )

        session = Session(
            id="s1",
            started_at=datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 13, 10, 30, tzinfo=timezone.utc),
            rules_at_start=["r1"],
            rules_at_end=["r1"],
        )
        current_reward = RewardSummary(
            total_events=0, accepted=0, revisions=0, rejected=0, mean_reward=0.0
        )

        data = _compute_improvements_data(
            session=session,
            duration=30.0,
            session_mistakes=[],
            stats={"r1": {"mean": 0.5, "total_observations": 3}},
            prior_session=None,
            prior_mistakes=[],
            prior_reward_summary=None,
            current_reward_summary=current_reward,
        )

        assert data.mean_reward is None

    def test_reward_summary_with_events(self):
        from buildlog.core.operations import (
            RewardSummary,
            Session,
            _compute_improvements_data,
        )

        session = Session(
            id="s1",
            started_at=datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 13, 10, 30, tzinfo=timezone.utc),
            rules_at_start=[],
            rules_at_end=[],
        )
        current_reward = RewardSummary(
            total_events=5, accepted=4, revisions=1, rejected=0, mean_reward=0.9
        )

        data = _compute_improvements_data(
            session=session,
            duration=30.0,
            session_mistakes=[],
            stats={},
            prior_session=None,
            prior_mistakes=[],
            prior_reward_summary=None,
            current_reward_summary=current_reward,
        )

        assert data.mean_reward == 0.9

    def test_error_class_none_uses_global_stats(self):
        """When error_class is None, stats should still be processed."""
        from buildlog.core.operations import (
            RewardSummary,
            Session,
            _compute_improvements_data,
        )

        session = Session(
            id="s1",
            started_at=datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 13, 10, 30, tzinfo=timezone.utc),
            error_class=None,
            rules_at_start=["r1"],
            rules_at_end=["r1"],
        )
        # Global stats (context=None returns all)
        stats = {"general:r1": {"mean": 0.75, "total_observations": 12}}
        current_reward = RewardSummary(
            total_events=1, accepted=1, revisions=0, rejected=0, mean_reward=1.0
        )

        data = _compute_improvements_data(
            session=session,
            duration=30.0,
            session_mistakes=[],
            stats=stats,
            prior_session=None,
            prior_mistakes=[],
            prior_reward_summary=None,
            current_reward_summary=current_reward,
        )

        assert len(data.rule_statuses) == 1
        assert data.rule_statuses[0].rule_id == "general:r1"
        assert data.rule_statuses[0].status == "earned_confidence"


# =============================================================================
# TestEndSessionWithReport (integration)
# =============================================================================


class TestEndSessionWithReport:
    """Integration tests for end_session() improvements report injection."""

    def _setup_buildlog(self, tmp_path: Path) -> Path:
        """Set up a minimal buildlog directory."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        return buildlog_dir

    def test_full_lifecycle(self, tmp_path: Path):
        """Start → mistake → reward → end → verify entry has report."""
        from buildlog.core import end_session, log_mistake, log_reward, start_session

        buildlog_dir = self._setup_buildlog(tmp_path)

        # Create an entry file
        today = datetime.now().strftime("%Y-%m-%d")
        entry = buildlog_dir / f"{today}-test.md"
        entry.write_text("# Test Entry\n\nSome notes.\n\n## Commits\n\n- abc123\n")

        # Start session
        start_session(buildlog_dir, error_class="missing_test")

        # Log a mistake
        log_mistake(
            buildlog_dir,
            error_class="missing_test",
            description="forgot unit test",
        )

        # Log a reward
        log_reward(buildlog_dir, outcome="accepted", notes="test commit")

        # End session with entry file
        result = end_session(buildlog_dir, entry_file=str(entry))

        assert result.mistakes_logged == 1
        assert result.report_appended is True
        assert result.entry_path == str(entry)

        # Verify entry content
        content = entry.read_text()
        assert _MARKER_START in content
        assert _MARKER_END in content
        assert "## What Improved This Session" in content
        # Report should be before ## Commits
        assert content.index(_MARKER_START) < content.index("## Commits")

    def test_no_entry_file_no_crash(self, tmp_path: Path):
        """No entry file → report_appended=False, no crash."""
        from buildlog.core import end_session, start_session

        buildlog_dir = self._setup_buildlog(tmp_path)

        start_session(buildlog_dir, error_class="missing_test")
        result = end_session(buildlog_dir)

        assert result.report_appended is False
        assert result.entry_path is None

    def test_prior_session_trends(self, tmp_path: Path):
        """Prior session data appears in report."""
        from buildlog.core import end_session, log_mistake, start_session

        buildlog_dir = self._setup_buildlog(tmp_path)

        # First session
        start_session(buildlog_dir, error_class="missing_test")
        log_mistake(
            buildlog_dir,
            error_class="missing_test",
            description="mistake in session 1",
        )
        end_session(buildlog_dir)

        # Second session with entry
        today = datetime.now().strftime("%Y-%m-%d")
        entry = buildlog_dir / f"{today}-test.md"
        entry.write_text("# Entry\n\n## Commits\n\n- xyz\n")

        start_session(buildlog_dir, error_class="missing_test")
        log_mistake(
            buildlog_dir,
            error_class="missing_test",
            description="mistake in session 2",
        )
        result = end_session(buildlog_dir, entry_file=str(entry))

        assert result.report_appended is True
        content = entry.read_text()
        assert "### Metrics" in content

    def test_bare_filename_normalized(self, tmp_path: Path):
        """Bare filename entry_file gets resolved relative to buildlog_dir."""
        from buildlog.core import end_session, log_mistake, start_session

        buildlog_dir = self._setup_buildlog(tmp_path)

        # Create entry as bare filename inside buildlog dir
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{today}-bare.md"
        entry = buildlog_dir / filename
        entry.write_text("# Entry\n\n## Commits\n\n- xyz\n")

        start_session(buildlog_dir, error_class="test")
        log_mistake(buildlog_dir, error_class="test", description="test mistake")
        result = end_session(buildlog_dir, entry_file=filename)

        assert result.report_appended is True

    def test_no_reward_events_omits_mean_reward(self, tmp_path: Path):
        """No reward events → report omits mean reward line."""
        from buildlog.core import end_session, log_mistake, start_session

        buildlog_dir = self._setup_buildlog(tmp_path)

        today = datetime.now().strftime("%Y-%m-%d")
        entry = buildlog_dir / f"{today}-test.md"
        entry.write_text("# Entry\n\n## Commits\n\n- xyz\n")

        start_session(buildlog_dir, error_class="test")
        log_mistake(buildlog_dir, error_class="test", description="test mistake")
        result = end_session(buildlog_dir, entry_file=str(entry))

        assert result.report_appended is True
        content = entry.read_text()
        # Narrative should NOT have bold mean reward line (table always has the row)
        assert "**Mean reward**" not in content

    def test_minimum_data_gate_clean_session(self, tmp_path: Path):
        """Clean session with no observations → no report."""
        from buildlog.core import end_session, start_session

        buildlog_dir = self._setup_buildlog(tmp_path)

        today = datetime.now().strftime("%Y-%m-%d")
        entry = buildlog_dir / f"{today}-test.md"
        entry.write_text("# Entry\n\n## Commits\n\n- xyz\n")

        start_session(buildlog_dir)
        result = end_session(buildlog_dir, entry_file=str(entry))

        # No mistakes, no rules, no rewards → gate blocks report
        assert result.report_appended is False
        content = entry.read_text()
        assert _MARKER_START not in content

    def test_idempotent_rerun(self, tmp_path: Path):
        """Re-running with existing markers replaces content."""
        from buildlog.core.report import inject_improvements_into_entry

        content = (
            "# Entry\n\n"
            f"{_MARKER_START}\nfirst report\n{_MARKER_END}\n\n"
            "## Commits\n\n- xyz\n"
        )
        result = inject_improvements_into_entry(content, "second report")
        assert "first report" not in result
        assert "second report" in result
        assert result.count(_MARKER_START) == 1
