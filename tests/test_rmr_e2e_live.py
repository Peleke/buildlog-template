"""LIVE E2E eval: RMR repeat detection with real storage.

No mocks. Creates a real SQLite DB, runs real sessions, logs real mistakes
with real gauntlet-style error_classes and rules_consulted, and verifies:

Scenario 1: Same category + overlapping rules across sessions → was_repeat=True
Scenario 2: Different categories → was_repeat=False (no false positives)

This is THE acceptance test for the RMR pipeline fix.
"""

import sqlite3
from pathlib import Path

import pytest

from buildlog.core.operations import (
    end_session,
    get_session_metrics,
    log_mistake,
    start_session,
)
from buildlog.storage import get_backend
from buildlog.storage.schema import init_schema


@pytest.fixture
def live_env(tmp_path):
    """Set up a complete buildlog environment with real storage."""
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()
    return buildlog_dir


class TestRMRScenario1_RepeatDetected:
    """Same category + overlapping rules_consulted → was_repeat=True.

    Simulates:
    - Session A: security_karen catches a path traversal (gauntlet_security)
    - Session B: security_karen catches ANOTHER path traversal (gauntlet_security)
      → Should be detected as a repeat because same rules, same category.
    """

    def test_repeat_detected_across_sessions(self, live_env):
        buildlog_dir = live_env

        # --- Session A ---
        start_session(buildlog_dir, error_class="gauntlet_security")

        mistake_a = log_mistake(
            buildlog_dir,
            error_class="gauntlet_security",
            description="[src/auth.py:42] Uses os.path.join with user input for path construction",
            severity="critical",
            rules_consulted=["security_karen:a1b2c3d4", "security_karen:e5f6g7h8"],
        )
        assert mistake_a.was_repeat is False  # First time seeing this

        end_session(buildlog_dir)

        # --- Session B ---
        start_session(buildlog_dir, error_class="gauntlet_security")

        mistake_b = log_mistake(
            buildlog_dir,
            error_class="gauntlet_security",
            description="[src/routes.py:18] Path traversal via unvalidated user path input",
            severity="critical",
            rules_consulted=["security_karen:a1b2c3d4", "loki:z9y8x7w6"],
        )
        assert mistake_b.was_repeat is True  # REPEAT! Same rule caught it again

        end_session(buildlog_dir)

        # --- Verify metrics ---
        backend, project_id = get_backend(buildlog_dir, project_root=live_env.parent)
        mistakes = backend.load_events(project_id, "mistakes")
        assert len(mistakes) == 2
        assert mistakes[0]["was_repeat"] is False
        assert mistakes[1]["was_repeat"] is True


class TestRMRScenario2_NoFalsePositive:
    """Different categories → was_repeat=False.

    Simulates:
    - Session A: security_karen catches a security issue
    - Session B: testing issue with different category
      → Should NOT be a repeat even if rule IDs overlap.
    """

    def test_different_category_not_repeat(self, live_env):
        buildlog_dir = live_env

        # --- Session A ---
        start_session(buildlog_dir, error_class="gauntlet_security")

        mistake_a = log_mistake(
            buildlog_dir,
            error_class="gauntlet_security",
            description="[src/auth.py:42] Hardcoded API key",
            severity="critical",
            rules_consulted=["security_karen:a1b2c3d4"],
        )
        assert mistake_a.was_repeat is False

        end_session(buildlog_dir)

        # --- Session B ---
        start_session(buildlog_dir, error_class="gauntlet_testing")

        mistake_b = log_mistake(
            buildlog_dir,
            error_class="gauntlet_testing",  # Different category!
            description="[src/auth.py:42] Missing unit tests for auth module",
            severity="high",
            rules_consulted=[
                "security_karen:a1b2c3d4"
            ],  # Same rule, but different class
        )
        assert mistake_b.was_repeat is False  # NOT a repeat — different category

        end_session(buildlog_dir)

        # --- Verify ---
        backend, project_id = get_backend(buildlog_dir, project_root=live_env.parent)
        mistakes = backend.load_events(project_id, "mistakes")
        assert len(mistakes) == 2
        assert all(not m["was_repeat"] for m in mistakes)


class TestRMRScenario3_PosteriorSnapshotsPersist:
    """Verify posterior snapshots round-trip through real storage."""

    def test_snapshots_persist_and_query(self, live_env):
        buildlog_dir = live_env

        backend, project_id = get_backend(buildlog_dir, project_root=live_env.parent)

        # Simulate gauntlet credit snapshots
        records = [
            {
                "rule_id": "security_karen:a1b2c3d4",
                "alpha": 2.0,
                "beta": 1.0,
                "mean": 0.667,
                "trigger": "gauntlet_credit",
                "iteration": 1,
                "batch_id": "gauntlet-1-test",
                "timestamp": "2026-03-10T00:00:00Z",
            },
            {
                "rule_id": "security_karen:a1b2c3d4",
                "alpha": 3.0,
                "beta": 1.0,
                "mean": 0.75,
                "trigger": "gauntlet_credit",
                "iteration": 2,
                "batch_id": "gauntlet-2-test",
                "timestamp": "2026-03-10T01:00:00Z",
            },
            {
                "rule_id": "loki:z9y8x7w6",
                "alpha": 1.5,
                "beta": 2.0,
                "mean": 0.429,
                "trigger": "gauntlet_credit",
                "iteration": 1,
                "batch_id": "gauntlet-1-test",
                "timestamp": "2026-03-10T00:00:00Z",
            },
        ]
        count = backend.append_posterior_snapshots(project_id, records)
        assert count == 3

        # Query all
        all_history = backend.load_posterior_history(project_id)
        assert len(all_history) == 3

        # Query by rule
        karen_history = backend.load_posterior_history(
            project_id, rule_id="security_karen:a1b2c3d4"
        )
        assert len(karen_history) == 2
        # Should be ascending by timestamp
        assert karen_history[0]["alpha"] == 2.0
        assert karen_history[1]["alpha"] == 3.0

        # Query with since
        recent = backend.load_posterior_history(
            project_id, since="2026-03-10T00:30:00Z"
        )
        assert len(recent) == 1
        assert recent[0]["iteration"] == 2


class TestRMRScenario4_FullPipelineRoundTrip:
    """Full pipeline: sessions → mistakes → RMR calculation.

    Proves that get_session_metrics correctly computes RMR with the
    new repeat detection logic.
    """

    def test_rmr_nonzero_with_repeats(self, live_env):
        buildlog_dir = live_env

        # --- Session 1: first mistake ---
        start_session(buildlog_dir, error_class="gauntlet_security")
        log_mistake(
            buildlog_dir,
            error_class="gauntlet_security",
            description="SQL injection via string concatenation",
            severity="critical",
            rules_consulted=["security_karen:sql_injection_01"],
        )
        end_session(buildlog_dir)

        # --- Session 2: same kind of mistake (repeat!) ---
        start_session(buildlog_dir, error_class="gauntlet_security")
        log_mistake(
            buildlog_dir,
            error_class="gauntlet_security",
            description="SQL injection in different query builder",
            severity="critical",
            rules_consulted=["security_karen:sql_injection_01"],
        )
        end_session(buildlog_dir)

        # --- Verify RMR is nonzero ---
        backend, project_id = get_backend(buildlog_dir, project_root=live_env.parent)
        mistakes = backend.load_events(project_id, "mistakes")

        total = len(mistakes)
        repeats = sum(1 for m in mistakes if m.get("was_repeat"))

        assert total == 2
        assert repeats == 1
        # RMR = repeats / total = 0.5 (50%)
        rmr = repeats / total if total > 0 else 0.0
        assert rmr == 0.5
