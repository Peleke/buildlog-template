"""Tests for LegacyBackend."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from buildlog.storage.legacy import LegacyBackend


@pytest.fixture
def backend(tmp_path: Path):
    """Create a LegacyBackend against a temp directory."""
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    return LegacyBackend(buildlog_dir)


@pytest.fixture
def dot(tmp_path: Path):
    """Return the .buildlog dir (created by backend on first write)."""
    return tmp_path / "buildlog" / ".buildlog"


PID = "ignored"  # LegacyBackend ignores project_id


class TestIdSets:
    def test_empty(self, backend: LegacyBackend):
        assert backend.load_id_set(PID, "promoted") == set()

    def test_save_and_load(self, backend: LegacyBackend):
        backend.save_id_set(PID, "promoted", {"a", "b"})
        assert backend.load_id_set(PID, "promoted") == {"a", "b"}

    def test_overwrite(self, backend: LegacyBackend):
        backend.save_id_set(PID, "promoted", {"a"})
        backend.save_id_set(PID, "promoted", {"b", "c"})
        assert backend.load_id_set(PID, "promoted") == {"b", "c"}

    def test_metadata_preserved(self, backend: LegacyBackend, dot: Path):
        meta = {"skill-1": "2026-01-01"}
        backend.save_id_set(PID, "promoted", {"skill-1"}, meta)
        data = json.loads((dot / "promoted.json").read_text())
        assert data["promoted_at"]["skill-1"] == "2026-01-01"


class TestLearnings:
    def test_empty(self, backend: LegacyBackend):
        result = backend.load_learnings(PID)
        assert result == {"learnings": {}, "review_history": []}

    def test_save_and_load(self, backend: LegacyBackend):
        data = {"learnings": {"id1": {"rule": "test"}}, "review_history": []}
        backend.save_learnings(PID, data)
        loaded = backend.load_learnings(PID)
        assert loaded == data


class TestActiveSession:
    def test_no_session(self, backend: LegacyBackend):
        assert backend.load_active_session(PID) is None

    def test_save_and_load(self, backend: LegacyBackend):
        data = {"id": "session-1"}
        backend.save_active_session(PID, data)
        assert backend.load_active_session(PID) == data

    def test_delete(self, backend: LegacyBackend):
        backend.save_active_session(PID, {"id": "s1"})
        backend.delete_active_session(PID)
        assert backend.load_active_session(PID) is None


class TestEvents:
    def test_empty(self, backend: LegacyBackend):
        assert backend.load_events(PID, "rewards") == []
        assert backend.count_events(PID, "rewards") == 0

    def test_append_and_load(self, backend: LegacyBackend):
        record = {"id": "rew-1", "outcome": "accepted"}
        backend.append_event(PID, "rewards", record)
        events = backend.load_events(PID, "rewards")
        assert len(events) == 1
        assert events[0]["id"] == "rew-1"

    def test_multiple_append(self, backend: LegacyBackend):
        for i in range(3):
            backend.append_event(PID, "sessions", {"id": f"s-{i}"})
        assert backend.count_events(PID, "sessions") == 3

    def test_unknown_table(self, backend: LegacyBackend):
        with pytest.raises(ValueError):
            backend.append_event(PID, "nonexistent", {})


class TestBanditState:
    def test_empty(self, backend: LegacyBackend):
        assert backend.load_bandit_state(PID) == {}

    def test_save_and_load(self, backend: LegacyBackend):
        arms = {
            "general": {
                "rule-1": {
                    "alpha": 2.0,
                    "beta": 1.0,
                    "is_seed": True,
                    "updated_at": "2026-01-01",
                }
            }
        }
        backend.save_bandit_state(PID, arms)
        loaded = backend.load_bandit_state(PID)
        assert loaded["general"]["rule-1"]["alpha"] == 2.0

    def test_append_update(self, backend: LegacyBackend):
        record = {
            "context": "general",
            "rule_id": "rule-1",
            "alpha": 3.0,
            "beta": 2.0,
            "is_seed": False,
            "updated_at": "2026-01-02",
        }
        backend.append_bandit_update(PID, "general", "rule-1", record)
        state = backend.load_bandit_state(PID)
        assert state["general"]["rule-1"]["alpha"] == 3.0
