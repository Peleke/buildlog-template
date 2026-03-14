"""Tests for ensure_session() and the decoupled commit flow.

Proves that:
1. ensure_session() creates a lightweight session when none exists
2. ensure_session() is a no-op when a session already exists
3. commit() no longer blocks without a session (auto-creates one)
4. Lightweight sessions are distinguishable from full TS sessions
5. The gauntlet + commit flow works end-to-end without manual ceremony
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.core.operations import commit, ensure_session, start_session
from buildlog.storage import get_backend


class TestEnsureSession:
    """ensure_session() creates or returns an active session."""

    def test_creates_session_when_none_exists(self, tmp_path: Path):
        """With no active session, ensure_session creates a lightweight one."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        session_id = ensure_session(buildlog_dir)

        assert session_id.startswith("session-")

        # Verify it's stored
        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        session_data = backend.load_active_session(project_id)
        assert session_data is not None
        assert session_data["id"] == session_id

    def test_returns_existing_session_id(self, tmp_path: Path):
        """With an active session, ensure_session returns its ID (no-op)."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Start a full session first
        result = start_session(buildlog_dir, error_class="test")
        original_id = result.session_id

        # ensure_session should return the same ID
        returned_id = ensure_session(buildlog_dir)
        assert returned_id == original_id

    def test_does_not_overwrite_full_session(self, tmp_path: Path):
        """ensure_session must not replace a full TS session with a lightweight one."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = start_session(buildlog_dir, error_class="test")
        original_id = result.session_id

        ensure_session(buildlog_dir)

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        session_data = backend.load_active_session(project_id)
        assert session_data["id"] == original_id

    def test_lightweight_session_has_empty_selected_rules(self, tmp_path: Path):
        """Lightweight sessions have selected_rules=[] and notes='auto'."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        ensure_session(buildlog_dir)

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        session_data = backend.load_active_session(project_id)

        # Lightweight marker
        assert session_data.get("notes") == "auto"
        # No rules selected (no Thompson Sampling ran)
        assert session_data.get("selected_rules", []) == []

    def test_survives_broken_storage(self, tmp_path: Path):
        """ensure_session doesn't crash if storage is broken."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        with patch(
            "buildlog.core.operations._get_storage",
            side_effect=RuntimeError("storage broken"),
        ):
            # Should not raise
            session_id = ensure_session(buildlog_dir)
            assert session_id.startswith("session-")

    def test_idempotent_multiple_calls(self, tmp_path: Path):
        """Calling ensure_session twice returns the same session ID."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        first = ensure_session(buildlog_dir)
        second = ensure_session(buildlog_dir)
        assert first == second


class TestCommitWithoutSession:
    """commit() no longer blocks without a session."""

    def test_commit_no_longer_blocks_without_session(self, tmp_path: Path):
        """commit() should NOT return 'No active experiment session' error."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        result = commit(buildlog_dir, git_args=["-m", "test"])

        # It may fail at git (no repo), but must NOT fail at session check
        if result.error:
            assert "No active experiment session" not in result.error

    def test_commit_auto_creates_session(self, tmp_path: Path):
        """commit() should auto-create a session via ensure_session."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # No session exists
        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        assert backend.load_active_session(project_id) is None

        # commit() triggers ensure_session
        commit(buildlog_dir, git_args=["-m", "test"])

        # Now a session should exist
        session_data = backend.load_active_session(project_id)
        assert session_data is not None
        assert session_data.get("notes") == "auto"

    def test_commit_with_enforce_zero_skips_session(self, tmp_path: Path):
        """BUILDLOG_ENFORCE=0 skips ensure_session entirely."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        with patch.dict(os.environ, {"BUILDLOG_ENFORCE": "0"}):
            commit(buildlog_dir, git_args=["-m", "test"])

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        # No session created (enforcement was skipped)
        assert backend.load_active_session(project_id) is None

    def test_commit_preserves_existing_full_session(self, tmp_path: Path):
        """commit() with an existing full session doesn't replace it."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        result = start_session(buildlog_dir, error_class="test")
        original_id = result.session_id

        commit(buildlog_dir, git_args=["-m", "test"])

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        session_data = backend.load_active_session(project_id)
        assert session_data["id"] == original_id


class TestNewUserFlow:
    """End-to-end: a new user installs buildlog and commits without ceremony."""

    def test_fresh_install_commit_works(self, tmp_path: Path):
        """Simulates: pip install buildlog → init → commit (no experiment start)."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # User commits — no session started, no hooks, nothing
        result = commit(buildlog_dir, git_args=["-m", "first commit"])

        # Should fail at git (no repo), NOT at session enforcement
        if result.error:
            assert "No active experiment session" not in result.error
            assert "experiment" not in result.error.lower()

        # A lightweight session was auto-created
        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        session_data = backend.load_active_session(project_id)
        assert session_data is not None
        assert session_data.get("notes") == "auto"
        assert session_data.get("selected_rules", []) == []

    def test_gauntlet_then_commit_works_without_ceremony(self, tmp_path: Path):
        """Simulates: gauntlet review → commit, no manual session start."""
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        # Run gauntlet (works without session)
        gauntlet_result = gauntlet_process_issues(
            buildlog_dir,
            issues=[
                {
                    "severity": "minor",
                    "description": "Style nit",
                    "rule_learned": "Use pathlib",
                }
            ],
        )
        assert gauntlet_result.action in ("clean", "checkpoint_minors")

        # Now commit — should not block
        result = commit(buildlog_dir, git_args=["-m", "fix: style nit"])
        if result.error:
            assert "No active experiment session" not in result.error
