"""Tests for SQLiteBackend."""

from __future__ import annotations

import sqlite3

import pytest

from buildlog.storage.schema import init_schema
from buildlog.storage.sqlite import SQLiteBackend


@pytest.fixture
def backend():
    """Create an in-memory SQLiteBackend for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    be = SQLiteBackend(conn)
    be.ensure_project("test-proj", "Test Project", "/tmp/test")
    return be


PID = "test-proj"


class TestProjectRegistration:
    def test_ensure_project(self, backend: SQLiteBackend):
        assert backend.project_exists(PID)

    def test_project_not_exists(self, backend: SQLiteBackend):
        assert not backend.project_exists("nonexistent")

    def test_ensure_project_idempotent(self, backend: SQLiteBackend):
        backend.ensure_project(PID, "Test Project", "/tmp/test")
        assert backend.project_exists(PID)


class TestIdSets:
    def test_empty_set(self, backend: SQLiteBackend):
        result = backend.load_id_set(PID, "promoted")
        assert result == set()

    def test_save_and_load(self, backend: SQLiteBackend):
        ids = {"skill-1", "skill-2", "skill-3"}
        backend.save_id_set(PID, "promoted", ids)
        loaded = backend.load_id_set(PID, "promoted")
        assert loaded == ids

    def test_overwrite(self, backend: SQLiteBackend):
        backend.save_id_set(PID, "promoted", {"a", "b"})
        backend.save_id_set(PID, "promoted", {"b", "c"})
        loaded = backend.load_id_set(PID, "promoted")
        assert loaded == {"b", "c"}

    def test_separate_collections(self, backend: SQLiteBackend):
        backend.save_id_set(PID, "promoted", {"a"})
        backend.save_id_set(PID, "rejected", {"b"})
        assert backend.load_id_set(PID, "promoted") == {"a"}
        assert backend.load_id_set(PID, "rejected") == {"b"}

    def test_with_metadata(self, backend: SQLiteBackend):
        ids = {"skill-1"}
        meta = {"skill-1": "2026-01-01T00:00:00"}
        backend.save_id_set(PID, "promoted", ids, meta)
        loaded = backend.load_id_set(PID, "promoted")
        assert loaded == ids

    def test_empty_save(self, backend: SQLiteBackend):
        backend.save_id_set(PID, "promoted", {"a", "b"})
        backend.save_id_set(PID, "promoted", set())
        assert backend.load_id_set(PID, "promoted") == set()


class TestLearnings:
    def test_empty_learnings(self, backend: SQLiteBackend):
        result = backend.load_learnings(PID)
        assert result == {"learnings": {}, "review_history": []}

    def test_save_and_load(self, backend: SQLiteBackend):
        data = {
            "learnings": {
                "arch-abc123": {
                    "id": "arch-abc123",
                    "rule": "Test rule",
                    "category": "architectural",
                    "severity": "critical",
                    "source": "review:test",
                    "first_seen": "2026-01-01T00:00:00",
                    "last_reinforced": "2026-01-01T00:00:00",
                    "reinforcement_count": 1,
                    "contradiction_count": 0,
                    "functional_principle": None,
                }
            },
            "review_history": [
                {
                    "timestamp": "2026-01-01T00:00:00",
                    "source": "review:test",
                    "issues_count": 1,
                    "new_learning_ids": ["arch-abc123"],
                    "reinforced_learning_ids": [],
                }
            ],
        }
        backend.save_learnings(PID, data)
        loaded = backend.load_learnings(PID)

        assert "arch-abc123" in loaded["learnings"]
        assert loaded["learnings"]["arch-abc123"]["rule"] == "Test rule"
        assert len(loaded["review_history"]) == 1

    def test_reinforce_learning(self, backend: SQLiteBackend):
        data = {
            "learnings": {
                "arch-abc123": {
                    "id": "arch-abc123",
                    "rule": "Test rule",
                    "category": "architectural",
                    "severity": "critical",
                    "source": "review:test",
                    "first_seen": "2026-01-01T00:00:00",
                    "last_reinforced": "2026-01-01T00:00:00",
                    "reinforcement_count": 1,
                    "contradiction_count": 0,
                    "functional_principle": None,
                }
            },
            "review_history": [],
        }
        backend.save_learnings(PID, data)

        # Reinforce
        data["learnings"]["arch-abc123"]["reinforcement_count"] = 2
        data["learnings"]["arch-abc123"]["last_reinforced"] = "2026-01-02T00:00:00"
        backend.save_learnings(PID, data)

        loaded = backend.load_learnings(PID)
        assert loaded["learnings"]["arch-abc123"]["reinforcement_count"] == 2


class TestActiveSession:
    def test_no_session(self, backend: SQLiteBackend):
        assert backend.load_active_session(PID) is None

    def test_save_and_load(self, backend: SQLiteBackend):
        data = {"id": "session-123", "started_at": "2026-01-01T00:00:00"}
        backend.save_active_session(PID, data)
        loaded = backend.load_active_session(PID)
        assert loaded == data

    def test_delete(self, backend: SQLiteBackend):
        backend.save_active_session(PID, {"id": "s1"})
        backend.delete_active_session(PID)
        assert backend.load_active_session(PID) is None

    def test_overwrite(self, backend: SQLiteBackend):
        backend.save_active_session(PID, {"id": "s1"})
        backend.save_active_session(PID, {"id": "s2"})
        loaded = backend.load_active_session(PID)
        assert loaded["id"] == "s2"


class TestEvents:
    def test_empty_events(self, backend: SQLiteBackend):
        assert backend.load_events(PID, "rewards") == []
        assert backend.count_events(PID, "rewards") == 0

    def test_append_and_load_rewards(self, backend: SQLiteBackend):
        record = {
            "id": "rew-123",
            "timestamp": "2026-01-01T00:00:00",
            "outcome": "accepted",
            "reward_value": 1.0,
            "rules_active": ["rule-1"],
        }
        backend.append_event(PID, "rewards", record)
        events = backend.load_events(PID, "rewards")
        assert len(events) == 1
        assert events[0]["id"] == "rew-123"
        assert events[0]["rules_active"] == ["rule-1"]

    def test_append_and_load_sessions(self, backend: SQLiteBackend):
        record = {
            "id": "sess-123",
            "started_at": "2026-01-01T00:00:00",
            "ended_at": None,
            "rules_at_start": ["rule-1"],
            "rules_at_end": [],
            "selected_rules": ["rule-1"],
        }
        backend.append_event(PID, "sessions", record)
        events = backend.load_events(PID, "sessions")
        assert len(events) == 1
        assert events[0]["selected_rules"] == ["rule-1"]

    def test_append_and_load_mistakes(self, backend: SQLiteBackend):
        record = {
            "id": "mistake-123",
            "session_id": "sess-123",
            "timestamp": "2026-01-01T00:00:00",
            "error_class": "missing_test",
            "description": "Forgot to test X",
            "semantic_hash": "abc123",
            "was_repeat": False,
        }
        backend.append_event(PID, "mistakes", record)
        events = backend.load_events(PID, "mistakes")
        assert len(events) == 1
        assert events[0]["was_repeat"] is False

    def test_count_events(self, backend: SQLiteBackend):
        for i in range(5):
            backend.append_event(
                PID,
                "rewards",
                {
                    "id": f"rew-{i}",
                    "timestamp": f"2026-01-0{i + 1}T00:00:00",
                    "outcome": "accepted",
                    "reward_value": 1.0,
                },
            )
        assert backend.count_events(PID, "rewards") == 5

    def test_unknown_table(self, backend: SQLiteBackend):
        with pytest.raises(ValueError, match="Unknown event table"):
            backend.append_event(PID, "nonexistent", {})

    def test_idempotent_replace(self, backend: SQLiteBackend):
        record = {
            "id": "rew-123",
            "timestamp": "2026-01-01T00:00:00",
            "outcome": "accepted",
            "reward_value": 1.0,
        }
        backend.append_event(PID, "rewards", record)
        backend.append_event(PID, "rewards", record)
        assert backend.count_events(PID, "rewards") == 1


class TestGlobalEvents:
    def test_load_events_global(self, backend: SQLiteBackend):
        backend.ensure_project("proj-2", "P2", "/tmp/p2")
        backend.append_event(
            PID,
            "rewards",
            {
                "id": "r1",
                "timestamp": "2026-01-01",
                "outcome": "accepted",
                "reward_value": 1.0,
            },
        )
        backend.append_event(
            "proj-2",
            "rewards",
            {
                "id": "r2",
                "timestamp": "2026-01-02",
                "outcome": "rejected",
                "reward_value": 0.0,
            },
        )
        all_events = backend.load_events_global("rewards")
        assert len(all_events) == 2

    def test_count_events_global(self, backend: SQLiteBackend):
        backend.ensure_project("proj-2", "P2", "/tmp/p2")
        backend.append_event(
            PID,
            "rewards",
            {
                "id": "r1",
                "timestamp": "2026-01-01",
                "outcome": "accepted",
                "reward_value": 1.0,
            },
        )
        backend.append_event(
            "proj-2",
            "rewards",
            {
                "id": "r2",
                "timestamp": "2026-01-02",
                "outcome": "rejected",
                "reward_value": 0.0,
            },
        )
        assert backend.count_events_global("rewards") == 2


class TestBanditState:
    def test_empty_state(self, backend: SQLiteBackend):
        state = backend.load_bandit_state(PID)
        assert state == {}

    def test_save_and_load(self, backend: SQLiteBackend):
        arms = {
            "general": {
                "rule-1": {
                    "alpha": 2.0,
                    "beta": 1.0,
                    "is_seed": True,
                    "updated_at": "2026-01-01T00:00:00",
                },
                "rule-2": {
                    "alpha": 1.0,
                    "beta": 3.0,
                    "is_seed": False,
                    "updated_at": "2026-01-01T00:00:00",
                },
            }
        }
        backend.save_bandit_state(PID, arms)
        loaded = backend.load_bandit_state(PID)
        assert "general" in loaded
        assert loaded["general"]["rule-1"]["alpha"] == 2.0
        assert loaded["general"]["rule-1"]["is_seed"] is True
        assert loaded["general"]["rule-2"]["beta"] == 3.0

    def test_append_update(self, backend: SQLiteBackend):
        record = {
            "alpha": 3.0,
            "beta": 2.0,
            "is_seed": False,
            "updated_at": "2026-01-01T00:00:00",
        }
        backend.append_bandit_update(PID, "general", "rule-1", record)
        state = backend.load_bandit_state(PID)
        assert state["general"]["rule-1"]["alpha"] == 3.0

    def test_save_compacts(self, backend: SQLiteBackend):
        # Append multiple updates
        for i in range(5):
            backend.append_bandit_update(
                PID,
                "general",
                "rule-1",
                {"alpha": float(i), "beta": 1.0, "is_seed": False},
            )
        # Save should compact
        state = backend.load_bandit_state(PID)
        backend.save_bandit_state(PID, state)
        reloaded = backend.load_bandit_state(PID)
        assert "general" in reloaded
        assert "rule-1" in reloaded["general"]


class TestConnectionReuse:
    """Tests for connection caching and lifecycle."""

    def test_get_connection_returns_same_object(self, tmp_path):
        """_get_connection should return the same conn for the same DB path."""
        from unittest.mock import patch

        from buildlog.storage import _get_connection

        db = tmp_path / "test.db"
        # Patch the cache to isolate from global state
        with patch("buildlog.storage._conn_cache", {}):
            conn1 = _get_connection(db)
            conn2 = _get_connection(db)
            assert conn1 is conn2

    def test_get_connection_reopens_after_close(self, tmp_path):
        """Should create a new connection if the cached one was closed."""
        from unittest.mock import patch

        from buildlog.storage import _get_connection

        db = tmp_path / "test.db"
        with patch("buildlog.storage._conn_cache", {}):
            conn1 = _get_connection(db)
            conn1.close()
            conn2 = _get_connection(db)
            assert conn2 is not conn1
            # The new connection should work
            conn2.execute("SELECT 1")


class TestTransactionSafety:
    """Tests for transaction wrapping in multi-statement writes."""

    def test_save_id_set_atomic(self, backend: SQLiteBackend):
        """save_id_set should be atomic — either all or nothing."""
        backend.save_id_set(PID, "promoted", {"a", "b", "c"})
        assert backend.load_id_set(PID, "promoted") == {"a", "b", "c"}
        # Overwrite with a new set
        backend.save_id_set(PID, "promoted", {"d", "e"})
        assert backend.load_id_set(PID, "promoted") == {"d", "e"}

    def test_save_bandit_state_atomic(self, backend: SQLiteBackend):
        """save_bandit_state should be atomic — old state fully replaced."""
        arms_v1 = {
            "ctx1": {
                "r1": {"alpha": 1.0, "beta": 1.0, "is_seed": True},
                "r2": {"alpha": 2.0, "beta": 1.0, "is_seed": False},
            }
        }
        arms_v2 = {
            "ctx1": {
                "r3": {"alpha": 5.0, "beta": 1.0, "is_seed": True},
            }
        }
        backend.save_bandit_state(PID, arms_v1)
        backend.save_bandit_state(PID, arms_v2)
        loaded = backend.load_bandit_state(PID)
        assert "r3" in loaded["ctx1"]
        assert "r1" not in loaded.get("ctx1", {})
        assert "r2" not in loaded.get("ctx1", {})


class TestHistoryDedup:
    """Tests for timestamp-based history dedup."""

    def test_save_learnings_no_duplicate_history(self, backend: SQLiteBackend):
        """Saving learnings twice should not duplicate review_history entries."""
        data = {
            "learnings": {
                "test-1": {
                    "id": "test-1",
                    "rule": "Always test",
                    "category": "testing",
                    "severity": "major",
                    "source": "review:test",
                    "first_seen": "2026-01-01",
                    "last_reinforced": "2026-01-01",
                    "reinforcement_count": 1,
                    "contradiction_count": 0,
                    "functional_principle": None,
                }
            },
            "review_history": [
                {
                    "timestamp": "2026-01-01T12:00:00",
                    "source": "test",
                    "issues_count": 1,
                    "new_learning_ids": ["test-1"],
                    "reinforced_learning_ids": [],
                }
            ],
        }
        backend.save_learnings(PID, data)
        backend.save_learnings(PID, data)  # Save again
        loaded = backend.load_learnings(PID)
        assert len(loaded["review_history"]) == 1

    def test_save_learnings_appends_new_history(self, backend: SQLiteBackend):
        """New history entries with different timestamps should be appended."""
        data1 = {
            "learnings": {},
            "review_history": [
                {
                    "timestamp": "2026-01-01T12:00:00",
                    "source": "test",
                    "issues_count": 1,
                },
            ],
        }
        data2 = {
            "learnings": {},
            "review_history": [
                {
                    "timestamp": "2026-01-01T12:00:00",
                    "source": "test",
                    "issues_count": 1,
                },
                {
                    "timestamp": "2026-01-02T12:00:00",
                    "source": "test",
                    "issues_count": 2,
                },
            ],
        }
        backend.save_learnings(PID, data1)
        backend.save_learnings(PID, data2)
        loaded = backend.load_learnings(PID)
        assert len(loaded["review_history"]) == 2
