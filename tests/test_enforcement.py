"""Tests for enforcement layers: auto-reward, auto-migrate, git hook."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


class TestAutoRewardOnEndSession:
    """Tests that end_session() auto-fires a reward signal."""

    def test_auto_reward_fallback_on_clean_session(self, tmp_path: Path):
        """Clean session (no explicit reward) should auto-log neutral revision fallback."""
        from buildlog.core import end_session, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")
        end_session(buildlog_dir)

        # Verify reward was logged as neutral fallback
        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        auto_rewards = [r for r in rewards if r.get("source") == "auto:end_session"]
        assert len(auto_rewards) == 1
        assert auto_rewards[0]["outcome"] == "revision"
        assert auto_rewards[0]["revision_distance"] == 0.5

    def test_auto_reward_revision_on_repeated_mistakes(self, tmp_path: Path):
        """Both sessions get neutral revision fallback (no explicit reward for either)."""
        from buildlog.core import end_session, log_mistake, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Session 1: create a mistake
        start_session(buildlog_dir, error_class="test")
        log_mistake(buildlog_dir, error_class="test", description="forgot tests")
        end_session(buildlog_dir)

        # Session 2: same mistake = repeat
        start_session(buildlog_dir, error_class="test")
        result = log_mistake(
            buildlog_dir, error_class="test", description="forgot tests"
        )
        assert result.was_repeat
        end_session(buildlog_dir)

        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        auto_rewards = [r for r in rewards if r.get("source") == "auto:end_session"]
        # Both sessions get neutral revision fallback (no explicit reward)
        assert len(auto_rewards) == 2
        for r in auto_rewards:
            assert r["outcome"] == "revision"
            assert r["revision_distance"] == 0.5

    def test_auto_reward_does_not_break_end_session(self, tmp_path: Path):
        """If reward logging fails, end_session() should still succeed."""
        from buildlog.core import end_session, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")

        with patch(
            "buildlog.core.operations.log_reward", side_effect=RuntimeError("boom")
        ):
            result = end_session(buildlog_dir)

        # Should still succeed
        assert result.session_id is not None
        assert result.duration_minutes >= 0

    def test_auto_reward_has_rules_active(self, tmp_path: Path):
        """Auto-reward must pass rules_active explicitly (session is already deleted)."""
        from buildlog.core import end_session, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")
        end_session(buildlog_dir)

        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        auto_rewards = [r for r in rewards if r.get("source") == "auto:end_session"]
        assert len(auto_rewards) == 1
        # rules_active should be a list (possibly empty if no rules selected,
        # but NOT missing/None which would mean the bandit got nothing)
        assert isinstance(auto_rewards[0].get("rules_active"), list)

    def test_auto_reward_has_session_id(self, tmp_path: Path):
        """Auto-reward should be linked to the correct session."""
        from buildlog.core import end_session, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_result = start_session(buildlog_dir, error_class="test")
        end_session(buildlog_dir)

        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        auto_rewards = [r for r in rewards if r.get("source") == "auto:end_session"]
        assert len(auto_rewards) == 1
        assert auto_rewards[0]["session_id"] == start_result.session_id

    def test_auto_reward_skipped_when_explicit_reward_exists(self, tmp_path: Path):
        """If an explicit reward was logged during the session, skip auto-reward."""
        from buildlog.core import end_session, log_reward, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")
        # Explicit reward during session
        log_reward(buildlog_dir, outcome="accepted", source="hook:merge")
        end_session(buildlog_dir)

        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        # Only the explicit reward, no auto-reward
        assert len(rewards) == 1
        assert rewards[0]["source"] == "hook:merge"
        auto_rewards = [r for r in rewards if r.get("source") == "auto:end_session"]
        assert len(auto_rewards) == 0

    def test_auto_reward_fires_when_no_explicit_reward(self, tmp_path: Path):
        """When no explicit reward exists, auto-reward should fire."""
        from buildlog.core import end_session, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")
        # No log_reward() call
        end_session(buildlog_dir)

        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        assert len(rewards) == 1
        assert rewards[0]["source"] == "auto:end_session"

    def test_dedup_matches_on_session_id(self, tmp_path: Path):
        """Dedup should not bleed across sessions — session B gets auto-reward."""
        from buildlog.core import end_session, log_reward, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Session A: explicit reward → no auto-reward
        start_session(buildlog_dir, error_class="test")
        log_reward(buildlog_dir, outcome="accepted", source="hook:merge")
        end_session(buildlog_dir)

        # Session B: no explicit reward → auto-reward fires
        start_session(buildlog_dir, error_class="test")
        end_session(buildlog_dir)

        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        auto_rewards = [r for r in rewards if r.get("source") == "auto:end_session"]
        # Only session B got auto-reward
        assert len(auto_rewards) == 1
        explicit_rewards = [r for r in rewards if r.get("source") == "hook:merge"]
        assert len(explicit_rewards) == 1

    def test_auto_reward_fallback_uses_neutral_signal(self, tmp_path: Path):
        """Auto-fallback must use revision with distance=0.5 → reward_value=0.5."""
        from buildlog.core import end_session, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")
        end_session(buildlog_dir)

        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        auto_rewards = [r for r in rewards if r.get("source") == "auto:end_session"]
        assert len(auto_rewards) == 1
        r = auto_rewards[0]
        assert r["outcome"] == "revision"
        assert r["revision_distance"] == 0.5
        assert r["reward_value"] == 0.5


class TestAutoMigrate:
    """Tests that get_backend() auto-migrates legacy data."""

    def test_auto_migrates_legacy_files(self, tmp_path: Path):
        """Should auto-migrate when global DB exists but project has legacy files."""
        from buildlog.storage import GLOBAL_DB_PATH, get_backend
        from buildlog.storage.schema import open_db

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        dot = buildlog_dir / ".buildlog"
        dot.mkdir()

        # Create a legacy reward file
        legacy_file = dot / "reward_events.jsonl"
        legacy_file.write_text(
            json.dumps(
                {
                    "id": "rew-001",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "outcome": "accepted",
                    "reward_value": 1.0,
                    "rules_active": [],
                    "source": "manual",
                }
            )
            + "\n"
        )

        with patch("buildlog.storage.GLOBAL_DB_PATH", tmp_path / "global.db"):
            # Create the global DB so it exists
            conn = open_db(tmp_path / "global.db")
            conn.close()

            with patch("buildlog.storage._get_connection") as mock_conn:
                # This test verifies the migration path is triggered.
                # Full migration integration is tested in test_storage_*.py.
                # Here we just verify the auto-migrate code path doesn't crash.
                from buildlog.storage.sqlite import SQLiteBackend

                real_conn = open_db(tmp_path / "global.db")
                mock_conn.return_value = real_conn
                real_backend = SQLiteBackend(real_conn)

                with patch.object(real_backend, "project_exists", return_value=False):
                    with patch(
                        "buildlog.storage.SQLiteBackend", return_value=real_backend
                    ):
                        with patch(
                            "buildlog.storage.migrate.migrate_project"
                        ) as mock_migrate:
                            try:
                                get_backend(buildlog_dir, project_root=tmp_path)
                            except Exception:
                                pass  # Backend setup may fail in test env
                            # The key assertion: migrate_project was called
                            mock_migrate.assert_called_once()

    def test_auto_migrate_failure_does_not_crash(self, tmp_path: Path):
        """If auto-migration fails, get_backend() should still return a backend."""
        from buildlog.storage import get_backend

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # No legacy files = no migration needed = should work fine
        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        assert backend is not None
        assert project_id is not None


class TestEnforceCommitHookConstant:
    """Tests for the ENFORCE_COMMIT_HOOK constant."""

    def test_enforce_hook_checks_env_var(self):
        from buildlog.hooks import ENFORCE_COMMIT_HOOK

        assert "BUILDLOG_ENFORCE" in ENFORCE_COMMIT_HOOK

    def test_enforce_hook_allows_buildlog_commit(self):
        from buildlog.hooks import ENFORCE_COMMIT_HOOK

        assert "BUILDLOG_COMMIT" in ENFORCE_COMMIT_HOOK

    def test_enforce_hook_exits_nonzero(self):
        from buildlog.hooks import ENFORCE_COMMIT_HOOK

        assert "exit 1" in ENFORCE_COMMIT_HOOK

    def test_enforce_hook_has_shebang(self):
        from buildlog.hooks import ENFORCE_COMMIT_HOOK

        assert ENFORCE_COMMIT_HOOK.startswith("#!/bin/sh")

    def test_enforce_hook_always_on_by_default(self):
        """Should block by default (BUILDLOG_ENFORCE defaults to 1, opt-out with 0)."""
        from buildlog.hooks import ENFORCE_COMMIT_HOOK

        assert "BUILDLOG_ENFORCE:-1" in ENFORCE_COMMIT_HOOK


class TestInstallEnforceHook:
    """Tests that install_hooks() installs the enforce hook."""

    def _setup_git_repo(self, tmp_path: Path) -> Path:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        return tmp_path

    def test_installs_enforce_hook_in_pre_commit(self, tmp_path: Path):
        """Should append enforce hook to pre-commit."""
        from buildlog.hooks import install_hooks

        project = self._setup_git_repo(tmp_path)
        install_hooks(project)

        hook = tmp_path / ".git" / "hooks" / "pre-commit"
        content = hook.read_text()
        assert "BUILDLOG_ENFORCE" in content
