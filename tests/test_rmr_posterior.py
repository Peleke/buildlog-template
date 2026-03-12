"""E2E tests for RMR repeat detection (Part 1) and posterior history (Part 2).

These tests prove:
1. RMR registers repeats when same rules catch same-category issues across sessions
2. RMR stays flat when categories differ (no false positives)
3. Posterior snapshots are persisted and queryable
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from buildlog.core.operations import (
    Mistake,
    _compute_semantic_hash,
    _find_similar_prior_mistake,
    end_session,
    get_posterior_history,
    log_mistake,
    start_session,
)
from buildlog.storage.schema import init_schema
from buildlog.storage.sqlite import SQLiteBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory SQLite database with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


@pytest.fixture
def backend(db):
    """SQLiteBackend wrapping the in-memory database."""
    b = SQLiteBackend(db)
    b.ensure_project("test-proj", "Test Project", "/tmp/test")
    return b


@pytest.fixture
def buildlog_dir(tmp_path):
    """Temporary buildlog directory with .buildlog subdirectory."""
    bd = tmp_path / "buildlog"
    bd.mkdir()
    (bd / ".buildlog").mkdir()
    return bd


# ===========================================================================
# Part 1: Repeat Detection
# ===========================================================================


class TestRepeatDetectionByRuleOverlap:
    """Prove that rule overlap triggers repeat detection."""

    def test_same_rules_same_category_is_repeat(self):
        """Two mistakes in different sessions with same error_class and
        overlapping rules_consulted should be detected as repeats."""
        prior = Mistake(
            id="m-001",
            session_id="session-A",
            timestamp="2026-03-10T00:00:00Z",
            error_class="gauntlet_security",
            description="[src/auth.py:42] Uses startswith for path checking",
            semantic_hash=_compute_semantic_hash(
                "[src/auth.py:42] Uses startswith for path checking"
            ),
            was_repeat=False,
            rules_consulted=["security_karen:abc123", "security_karen:def456"],
        )

        result = _find_similar_prior_mistake(
            description="[src/routes.py:18] Path traversal via startswith",
            error_class="gauntlet_security",
            current_session_id="session-B",
            all_mistakes=[prior],
            rules_consulted=["security_karen:abc123", "loki:xyz789"],
        )

        assert result is not None
        assert result.id == "m-001"

    def test_different_category_no_repeat(self):
        """Same rules but different error_class should NOT be a repeat."""
        prior = Mistake(
            id="m-002",
            session_id="session-A",
            timestamp="2026-03-10T00:00:00Z",
            error_class="gauntlet_security",
            description="SQL injection risk",
            semantic_hash=_compute_semantic_hash("SQL injection risk"),
            was_repeat=False,
            rules_consulted=["security_karen:abc123"],
        )

        result = _find_similar_prior_mistake(
            description="Missing unit tests for parser",
            error_class="gauntlet_testing",  # Different category!
            current_session_id="session-B",
            all_mistakes=[prior],
            rules_consulted=["security_karen:abc123"],  # Same rule but wrong class
        )

        assert result is None

    def test_same_session_not_repeat(self):
        """Mistakes in the same session are never repeats."""
        prior = Mistake(
            id="m-003",
            session_id="session-A",
            timestamp="2026-03-10T00:00:00Z",
            error_class="gauntlet_security",
            description="Path traversal",
            semantic_hash=_compute_semantic_hash("Path traversal"),
            was_repeat=False,
            rules_consulted=["security_karen:abc123"],
        )

        result = _find_similar_prior_mistake(
            description="Another path traversal",
            error_class="gauntlet_security",
            current_session_id="session-A",  # Same session!
            all_mistakes=[prior],
            rules_consulted=["security_karen:abc123"],
        )

        assert result is None

    def test_no_rules_no_rule_repeat(self):
        """If either side has no rules_consulted, rule overlap can't trigger."""
        prior = Mistake(
            id="m-004",
            session_id="session-A",
            timestamp="2026-03-10T00:00:00Z",
            error_class="gauntlet_security",
            description="Totally different description with no word overlap at all xyz",
            semantic_hash=_compute_semantic_hash(
                "Totally different description with no word overlap at all xyz"
            ),
            was_repeat=False,
            rules_consulted=None,  # No rules
        )

        result = _find_similar_prior_mistake(
            description="Another completely unrelated problem description abc",
            error_class="gauntlet_security",
            current_session_id="session-B",
            all_mistakes=[prior],
            rules_consulted=["security_karen:abc123"],
        )

        assert result is None

    def test_hash_match_still_works(self):
        """Semantic hash match (strategy 1) should still catch exact repeats."""
        desc = "[src/foo.py:10] Hardcoded secret in config"
        prior = Mistake(
            id="m-005",
            session_id="session-A",
            timestamp="2026-03-10T00:00:00Z",
            error_class="gauntlet_security",
            description=desc,
            semantic_hash=_compute_semantic_hash(desc),
            was_repeat=False,
        )

        result = _find_similar_prior_mistake(
            description=desc,  # Exact same description
            error_class="gauntlet_security",
            current_session_id="session-B",
            all_mistakes=[prior],
        )

        assert result is not None

    def test_word_overlap_still_works(self):
        """High word overlap (strategy 2) should still catch near-duplicates."""
        prior = Mistake(
            id="m-006",
            session_id="session-A",
            timestamp="2026-03-10T00:00:00Z",
            error_class="gauntlet_security",
            description="hardcoded secret found in config file at line 42",
            semantic_hash=_compute_semantic_hash(
                "hardcoded secret found in config file at line 42"
            ),
            was_repeat=False,
        )

        result = _find_similar_prior_mistake(
            description="hardcoded secret found in config file at line 99",
            error_class="gauntlet_security",
            current_session_id="session-B",
            all_mistakes=[prior],
        )

        assert result is not None


class TestCategoryAwareErrorClass:
    """Verify that gauntlet auto-log uses category in error_class."""

    def test_mistake_serializes_rules_consulted(self):
        """Mistake.to_dict() should include rules_consulted when set."""
        m = Mistake(
            id="m-010",
            session_id="s-1",
            timestamp=datetime(2026, 3, 10, tzinfo=timezone.utc),
            error_class="gauntlet_security",
            description="test",
            semantic_hash="abc",
            rules_consulted=["rule:001", "rule:002"],
        )
        d = m.to_dict()
        assert d["rules_consulted"] == ["rule:001", "rule:002"]
        assert d["error_class"] == "gauntlet_security"

    def test_mistake_from_dict_parses_rules_consulted(self):
        """Mistake.from_dict() should handle rules_consulted as JSON string."""
        data = {
            "id": "m-011",
            "session_id": "s-1",
            "timestamp": "2026-03-10T00:00:00Z",
            "error_class": "gauntlet_testing",
            "description": "test",
            "semantic_hash": "abc",
            "rules_consulted": '["rule:001", "rule:002"]',
        }
        m = Mistake.from_dict(data)
        assert m.rules_consulted == ["rule:001", "rule:002"]

    def test_mistake_from_dict_handles_list(self):
        """Mistake.from_dict() should handle rules_consulted as native list."""
        data = {
            "id": "m-012",
            "session_id": "s-1",
            "timestamp": "2026-03-10T00:00:00Z",
            "error_class": "gauntlet_testing",
            "description": "test",
            "semantic_hash": "abc",
            "rules_consulted": ["rule:001"],
        }
        m = Mistake.from_dict(data)
        assert m.rules_consulted == ["rule:001"]


# ===========================================================================
# Part 2: Posterior History
# ===========================================================================


class TestPosteriorSnapshots:
    """Verify posterior snapshot persistence and retrieval."""

    def test_append_and_load(self, backend):
        """Snapshots inserted via append should be loadable."""
        records = [
            {
                "rule_id": "security_karen:abc123",
                "alpha": 3.0,
                "beta": 1.5,
                "mean": 0.667,
                "trigger": "gauntlet_credit",
                "iteration": 1,
                "batch_id": "gauntlet-1-2026-03-10",
                "timestamp": "2026-03-10T00:00:00Z",
            },
            {
                "rule_id": "security_karen:abc123",
                "alpha": 4.0,
                "beta": 1.5,
                "mean": 0.727,
                "trigger": "gauntlet_credit",
                "iteration": 2,
                "batch_id": "gauntlet-2-2026-03-10",
                "timestamp": "2026-03-10T01:00:00Z",
            },
        ]
        count = backend.append_posterior_snapshots("test-proj", records)
        assert count == 2

        history = backend.load_posterior_history("test-proj")
        assert len(history) == 2
        assert history[0]["alpha"] == 3.0
        assert history[1]["alpha"] == 4.0

    def test_filter_by_rule_id(self, backend):
        """Should filter snapshots by rule_id."""
        records = [
            {
                "rule_id": "security_karen:abc123",
                "alpha": 3.0,
                "beta": 1.5,
                "mean": 0.667,
                "trigger": "gauntlet_credit",
            },
            {
                "rule_id": "loki:xyz789",
                "alpha": 2.0,
                "beta": 3.0,
                "mean": 0.4,
                "trigger": "gauntlet_credit",
            },
        ]
        backend.append_posterior_snapshots("test-proj", records)

        history = backend.load_posterior_history(
            "test-proj", rule_id="security_karen:abc123"
        )
        assert len(history) == 1
        assert history[0]["rule_id"] == "security_karen:abc123"

    def test_filter_by_since(self, backend):
        """Should filter snapshots by timestamp lower bound."""
        records = [
            {
                "rule_id": "r1",
                "alpha": 1.0,
                "beta": 1.0,
                "mean": 0.5,
                "trigger": "gauntlet_credit",
                "timestamp": "2026-03-01T00:00:00Z",
            },
            {
                "rule_id": "r1",
                "alpha": 2.0,
                "beta": 1.0,
                "mean": 0.667,
                "trigger": "gauntlet_credit",
                "timestamp": "2026-03-10T00:00:00Z",
            },
        ]
        backend.append_posterior_snapshots("test-proj", records)

        history = backend.load_posterior_history(
            "test-proj", since="2026-03-05T00:00:00Z"
        )
        assert len(history) == 1
        assert history[0]["alpha"] == 2.0

    def test_limit(self, backend):
        """Should respect the limit parameter."""
        records = [
            {
                "rule_id": f"r{i}",
                "alpha": float(i),
                "beta": 1.0,
                "mean": float(i) / (float(i) + 1.0),
                "trigger": "gauntlet_credit",
            }
            for i in range(10)
        ]
        backend.append_posterior_snapshots("test-proj", records)

        history = backend.load_posterior_history("test-proj", limit=3)
        assert len(history) == 3


class TestMistakesWithRulesConsulted:
    """Verify the mistakes table stores and retrieves rules_consulted."""

    def test_store_and_load_rules_consulted(self, backend):
        """rules_consulted should round-trip through the database."""
        record = {
            "id": "m-100",
            "session_id": "s-1",
            "timestamp": "2026-03-10T00:00:00Z",
            "error_class": "gauntlet_security",
            "description": "test mistake",
            "semantic_hash": "hash123",
            "was_repeat": False,
            "rules_consulted": ["security_karen:abc", "loki:def"],
        }
        backend.append_event("test-proj", "mistakes", record)

        events = backend.load_events("test-proj", "mistakes")
        assert len(events) == 1
        # rules_consulted is stored as JSON text, loaded as-is
        rc = events[0].get("rules_consulted")
        if isinstance(rc, str):
            rc = json.loads(rc)
        assert rc == ["security_karen:abc", "loki:def"]


class TestSchemaV7Migration:
    """Verify schema v7 migration creates required objects."""

    def test_posterior_snapshots_table_exists(self, db):
        """posterior_snapshots table should exist after init_schema."""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='posterior_snapshots'"
        ).fetchone()
        assert row is not None

    def test_rules_consulted_column_exists(self, db):
        """mistakes table should have rules_consulted column."""
        cols = db.execute("PRAGMA table_info(mistakes)").fetchall()
        col_names = [c[1] for c in cols]
        assert "rules_consulted" in col_names

    def test_schema_version_is_7(self, db):
        """Schema version should be 7."""
        row = db.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == 7

    def test_idempotent_migration(self, db):
        """Running init_schema again should not fail."""
        version = init_schema(db)
        assert version == 7
