"""Integration tests for the session invariant fix (GH #246).

Cross-function chain tests. No mocks — real storage, real bandit.
Proves that session-dependent operations create real sessions with
Thompson Sampling, and that the bandit actually learns.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from buildlog.core.learning import get_learning_backend
from buildlog.core.operations import (
    Session,
    _require_active_session,
    end_session,
    gauntlet_process_issues,
    get_experiment_report,
    get_session_metrics,
    log_mistake,
    log_reward,
    start_session,
)
from buildlog.storage import get_backend


def _seed_rules(buildlog_dir: Path, n: int = 5) -> list[str]:
    """Insert gauntlet rules into the DB so Thompson Sampling has a pool."""
    project_root = buildlog_dir.parent
    backend, _pid = get_backend(buildlog_dir, project_root=project_root)

    rules = []
    for i in range(n):
        rule_id = f"test_persona:{i:04d}"
        rules.append(
            {
                "rule_id": rule_id,
                "persona": "test_persona",
                "rule": f"Test rule number {i}",
                "category": "test",
                "context": "",
                "antipattern": "",
                "rationale": f"Rationale for rule {i}",
                "tags": "test",
                "refs": "",
                "provenance": "seed",
                "version": 1,
                "active": 1,
            }
        )

    backend.save_gauntlet_rules_batch(rules)
    return [r["rule_id"] for r in rules]


class TestGauntletToBanditUpdate:
    """gauntlet_process_issues -> log_mistake -> bandit.batch_update."""

    def test_gauntlet_critical_issues_update_bandit(self, tmp_path: Path):
        """Critical gauntlet issues trigger negative bandit feedback."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        _seed_rules(buildlog_dir, n=5)

        # Start a real session so rules are selected
        result = start_session(buildlog_dir)
        assert len(result.selected_rules) > 0

        bandit = get_learning_backend(buildlog_dir)

        # Gauntlet finds critical issues -> auto-logs mistakes
        gauntlet_process_issues(
            buildlog_dir,
            issues=[
                {
                    "severity": "critical",
                    "description": "Missing input validation",
                    "category": "security",
                    "rule_learned": "Always validate input",
                },
            ],
        )

        stats_after = bandit.get_stats(context="general")
        # The bandit should have been updated (beta increased for some arms)
        assert stats_after, "Bandit should have stats after mistake logged"
        # At least one arm should have observations
        has_observations = any(
            s.get("total_observations", 0) > 0 for s in stats_after.values()
        )
        assert has_observations, "At least one arm should have observations"


class TestFullSessionLifecycle:
    """start -> mistake -> reward -> end -> verify posteriors shifted."""

    def test_complete_lifecycle_updates_bandit(self, tmp_path: Path):
        """Full session lifecycle produces real bandit learning."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        _seed_rules(buildlog_dir, n=5)

        # Start — no error_class so context defaults to "general"
        result = start_session(buildlog_dir)
        session_id = result.session_id
        assert len(result.selected_rules) > 0

        # Mistake -> negative feedback (reward=0 for selected rules)
        log_mistake(
            buildlog_dir,
            error_class="test_error",
            description="Forgot to validate input",
        )

        # Reward -> positive feedback
        log_reward(buildlog_dir, outcome="accepted")

        bandit = get_learning_backend(buildlog_dir)
        stats = bandit.get_stats(context="general")
        # After mistake + reward, at least some arms should have observations
        assert stats, "Bandit should have stats after full lifecycle"
        has_observations = any(
            s.get("total_observations", 0) > 0 for s in stats.values()
        )
        assert has_observations, "Bandit should have learned from the lifecycle"

        # End session
        end_result = end_session(buildlog_dir)
        assert end_result.session_id == session_id
        assert end_result.mistakes_logged >= 1


class TestRewardAfterEndSession:
    """end_session deletes the session, then calls log_reward internally."""

    def test_auto_reward_uses_explicit_params(self, tmp_path: Path):
        """Auto-reward at end_session works even though session is deleted."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        _seed_rules(buildlog_dir, n=3)

        start_session(buildlog_dir, error_class="test")

        # End session — triggers auto-reward internally
        result = end_session(buildlog_dir)
        assert result.session_id.startswith("session-")
        assert result.duration_minutes >= 0

        # Verify reward was logged
        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        assert len(rewards) >= 1


class TestMultipleMistakesShareSession:
    """Multiple mistakes in a gauntlet batch share one session."""

    def test_no_phantom_sessions(self, tmp_path: Path):
        """All mistakes from gauntlet share the same real session."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        _seed_rules(buildlog_dir, n=5)

        # No session exists — gauntlet will auto-create via log_mistake
        gauntlet_process_issues(
            buildlog_dir,
            issues=[
                {
                    "severity": "critical",
                    "description": f"Issue {i}",
                    "category": "test",
                    "rule_learned": f"Rule {i}",
                }
                for i in range(3)
            ],
        )

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        mistakes = backend.load_events(project_id, "mistakes")

        # All mistakes should share the same session_id
        session_ids = {m["session_id"] for m in mistakes}
        assert (
            len(session_ids) == 1
        ), f"Expected 1 session, got {len(session_ids)}: {session_ids}"

        # And it should be a real session, not synthetic
        session_id = session_ids.pop()
        assert not session_id.startswith(
            "no-session-"
        ), f"Got synthetic session ID: {session_id}"


class TestRMRNoPhantomSessions:
    """RMR computation doesn't include phantom sessions."""

    def test_rmr_computed_correctly(self, tmp_path: Path):
        """Mistakes attributed to real session, visible in metrics."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        _seed_rules(buildlog_dir, n=5)

        result = start_session(buildlog_dir, error_class="test")
        session_id = result.session_id

        # Log some mistakes
        log_mistake(buildlog_dir, error_class="test", description="Mistake 1")
        log_mistake(buildlog_dir, error_class="test", description="Mistake 2")

        # End session
        end_session(buildlog_dir)

        # Check metrics
        metrics = get_session_metrics(buildlog_dir, session_id=session_id)
        assert metrics.total_mistakes == 2
        assert metrics.session_id == session_id


class TestZombieUpgradeThenEndSession:
    """Zombie upgrade before end_session produces correct metrics."""

    def test_zombie_upgraded_then_ended(self, tmp_path: Path):
        """Zombie gets upgraded, end_session sees real selected_rules."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        _seed_rules(buildlog_dir, n=5)

        # Create zombie
        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        zombie = Session(
            id="session-zombie-end-test",
            started_at=datetime.now(timezone.utc),
            rules_at_start=[],
            selected_rules=[],
            error_class=None,
            notes="auto",
        )
        backend.save_active_session(project_id, zombie.to_dict())  # type: ignore[arg-type]

        # End session — should upgrade zombie first
        result = end_session(buildlog_dir)
        assert result.session_id == "session-zombie-end-test"

        # Verify the session was saved with upgraded notes and selected_rules
        sessions = backend.load_events(project_id, "sessions")
        ended = [s for s in sessions if s["id"] == "session-zombie-end-test"]
        assert len(ended) == 1
        # Notes should reflect upgrade
        assert "auto:upgraded" in (ended[0].get("notes") or "")


class TestNoSyntheticIDsAnywhere:
    """No operation produces synthetic no-session-* IDs."""

    def test_log_mistake_without_session_creates_real_one(self, tmp_path: Path):
        """log_mistake with no session auto-creates a real session."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = log_mistake(
            buildlog_dir,
            error_class="test",
            description="A mistake without prior session",
        )

        assert not result.session_id.startswith(
            "no-session-"
        ), f"Got synthetic ID: {result.session_id}"
        assert result.session_id.startswith("session-")

        # Session was auto-created
        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        session_data = backend.load_active_session(project_id)
        assert session_data is not None


class TestStructuralInvariant:
    """No function in operations.py calls load_active_session directly
    except _require_active_session and start_session."""

    def test_no_direct_load_active_session_bypass(self):
        """Grep-based test: verify enforcement point isn't bypassed."""
        ops_path = (
            Path(__file__).parent.parent / "src" / "buildlog" / "core" / "operations.py"
        )
        source = ops_path.read_text()
        tree = ast.parse(source)

        # Find all function definitions and their calls to load_active_session.
        # get_overview is read-only (displays session info), not session-dependent.
        allowed_callers = {"_require_active_session", "start_session", "get_overview"}
        violations = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Attribute)
                        and child.attr == "load_active_session"
                        and func_name not in allowed_callers
                    ):
                        violations.append(
                            f"{func_name}() calls load_active_session directly"
                        )

        assert (
            violations == []
        ), f"These functions bypass _require_active_session: {violations}"
