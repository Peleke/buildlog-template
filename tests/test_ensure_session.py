"""Tests for _require_active_session() and the decoupled commit flow.

Proves that:
1. _require_active_session() creates a real session with Thompson Sampling
2. _require_active_session() returns existing session without modification
3. _require_active_session(auto_start=False) raises when no session exists
4. Zombie sessions (notes="auto", empty selected_rules) are upgraded in-place
5. commit() no longer creates sessions (removed ensure_session call)
6. ensure_session() is a deprecated wrapper
7. Session.to_dict() always includes selected_rules
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from pathlib import Path

import pytest

from buildlog.core.operations import (
    Session,
    _require_active_session,
    commit,
    ensure_session,
    start_session,
)
from buildlog.storage import get_backend


def _seed_rules(buildlog_dir: Path, n: int = 3) -> list[str]:
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
                "rule": f"Test rule {i}",
                "category": "test",
                "context": "",
                "antipattern": "",
                "rationale": f"Rationale {i}",
                "tags": "test",
                "refs": "",
                "provenance": "seed",
                "version": 1,
                "active": 1,
            }
        )
    backend.save_gauntlet_rules_batch(rules)
    return [r["rule_id"] for r in rules]


class TestRequireActiveSession:
    """_require_active_session() creates or returns an active session with TS."""

    def test_creates_real_session_when_none_exists(self, tmp_path: Path):
        """With no active session, auto-creates one via start_session()."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        session = _require_active_session(buildlog_dir)

        assert isinstance(session, Session)
        assert session.id.startswith("session-")
        # Real session — created via start_session, not a zombie
        assert session.notes == "auto:created"

    def test_returns_existing_session_unchanged(self, tmp_path: Path):
        """With an active session, returns it without modification."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = start_session(buildlog_dir, error_class="test")
        original_id = result.session_id

        session = _require_active_session(buildlog_dir)
        assert session.id == original_id

    def test_auto_start_false_raises_when_no_session(self, tmp_path: Path):
        """auto_start=False raises ValueError when no session exists."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        with pytest.raises(ValueError, match="No active session"):
            _require_active_session(buildlog_dir, auto_start=False)

    def test_upgrades_zombie_session(self, tmp_path: Path):
        """Zombie session (notes='auto', empty selected_rules) gets upgraded."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        _seed_rules(buildlog_dir, n=3)  # Need rules in pool for upgrade

        # Manually create a zombie session (simulates old ensure_session)
        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        zombie = Session(
            id="session-zombie-001",
            started_at=datetime.now(timezone.utc),
            rules_at_start=[],
            selected_rules=[],
            error_class=None,
            notes="auto",
        )
        backend.save_active_session(project_id, zombie.to_dict())  # type: ignore[arg-type]

        session = _require_active_session(buildlog_dir)

        assert session.id == "session-zombie-001"  # Same session, upgraded
        assert session.notes == "auto:upgraded"
        assert len(session.selected_rules) > 0  # TS populated rules

    def test_does_not_upgrade_non_zombie(self, tmp_path: Path):
        """A real session with notes != 'auto' is NOT treated as zombie."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = start_session(buildlog_dir, error_class="test", notes="real session")
        original_id = result.session_id

        session = _require_active_session(buildlog_dir)
        assert session.id == original_id
        assert session.notes == "real session"

    def test_zombie_upgrade_idempotent(self, tmp_path: Path):
        """Calling _require_active_session twice returns the same session."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        _seed_rules(buildlog_dir, n=3)

        # Create zombie
        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        zombie = Session(
            id="session-zombie-002",
            started_at=datetime.now(timezone.utc),
            rules_at_start=[],
            selected_rules=[],
            error_class=None,
            notes="auto",
        )
        backend.save_active_session(project_id, zombie.to_dict())  # type: ignore[arg-type]

        first = _require_active_session(buildlog_dir)
        second = _require_active_session(buildlog_dir)
        assert first.id == second.id
        # After first call: "auto:upgraded". Second call: not a zombie, returned as-is.
        assert second.notes == "auto:upgraded"

    def test_zombie_with_empty_pool_not_upgraded(self, tmp_path: Path):
        """No rules in pool -> zombie left as-is (valid empty state)."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        zombie = Session(
            id="session-zombie-003",
            started_at=datetime.now(timezone.utc),
            rules_at_start=[],
            selected_rules=[],
            error_class=None,
            notes="auto",
        )
        backend.save_active_session(project_id, zombie.to_dict())  # type: ignore[arg-type]

        session = _require_active_session(buildlog_dir)
        assert session.id == "session-zombie-003"
        # No rules available, so selected_rules stays empty.
        # notes stays "auto" because the upgrade path saw an empty pool.
        assert session.selected_rules == []

    def test_idempotent_multiple_calls(self, tmp_path: Path):
        """Calling _require_active_session twice returns the same session."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        first = _require_active_session(buildlog_dir)
        second = _require_active_session(buildlog_dir)
        assert first.id == second.id


class TestEnsureSessionDeprecated:
    """ensure_session() is a deprecated wrapper."""

    def test_emits_deprecation_warning(self, tmp_path: Path):
        """ensure_session() emits a DeprecationWarning."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            session_id = ensure_session(buildlog_dir)

        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated" in str(w[0].message).lower()
        assert session_id.startswith("session-")

    def test_returns_string_id(self, tmp_path: Path):
        """ensure_session() returns a string session ID for backward compat."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            session_id = ensure_session(buildlog_dir)

        assert isinstance(session_id, str)
        assert session_id.startswith("session-")


class TestCommitDecoupled:
    """commit() no longer creates sessions."""

    def test_commit_does_not_create_session(self, tmp_path: Path):
        """commit() should NOT create a session (ensure_session removed)."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        assert backend.load_active_session(project_id) is None

        commit(buildlog_dir, git_args=["-m", "test"])

        # No session should have been created
        assert backend.load_active_session(project_id) is None

    def test_commit_preserves_existing_session(self, tmp_path: Path):
        """commit() with an existing session doesn't touch it."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = start_session(buildlog_dir, error_class="test")
        original_id = result.session_id

        commit(buildlog_dir, git_args=["-m", "test"])

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        session_data = backend.load_active_session(project_id)
        assert session_data["id"] == original_id

    def test_commit_no_session_error_is_git_error(self, tmp_path: Path):
        """commit() without a session fails at git, not session enforcement."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = commit(buildlog_dir, git_args=["-m", "test"])
        if result.error:
            assert "session" not in result.error.lower()
            assert "experiment" not in result.error.lower()


class TestSessionDictSerialization:
    """Session.to_dict() always includes selected_rules."""

    def test_empty_selected_rules_serialized(self):
        """selected_rules=[] must appear in serialized dict, not be omitted."""
        session = Session(
            id="session-test-001",
            started_at=datetime.now(timezone.utc),
            selected_rules=[],
        )
        d = session.to_dict()
        assert "selected_rules" in d
        assert d["selected_rules"] == []

    def test_populated_selected_rules_serialized(self):
        """selected_rules with values are serialized normally."""
        session = Session(
            id="session-test-002",
            started_at=datetime.now(timezone.utc),
            selected_rules=["rule-a", "rule-b"],
        )
        d = session.to_dict()
        assert d["selected_rules"] == ["rule-a", "rule-b"]

    def test_roundtrip_preserves_empty_selected_rules(self):
        """to_dict -> from_dict preserves empty list."""
        session = Session(
            id="session-test-003",
            started_at=datetime.now(timezone.utc),
            selected_rules=[],
        )
        d = session.to_dict()
        restored = Session.from_dict(d)  # type: ignore[arg-type]
        assert restored.selected_rules == []
