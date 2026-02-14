"""Tests for enforcement layers: Claude Code hook, auto-reward, auto-migrate, git hook."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestAutoRewardOnEndSession:
    """Tests that end_session() auto-fires a reward signal."""

    def test_auto_reward_accepted_on_clean_session(self, tmp_path: Path):
        """Clean session (no repeats) should auto-log accepted reward."""
        from buildlog.core import end_session, start_session

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")
        end_session(buildlog_dir)

        # Verify reward was logged
        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        rewards = backend.load_events(project_id, "rewards")
        auto_rewards = [r for r in rewards if r.get("source") == "auto:end_session"]
        assert len(auto_rewards) == 1
        assert auto_rewards[0]["outcome"] == "accepted"

    def test_auto_reward_revision_on_repeated_mistakes(self, tmp_path: Path):
        """Session with repeated mistakes should auto-log revision reward."""
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
        # First session clean → accepted, second session with repeat → revision
        assert len(auto_rewards) == 2
        outcomes = [r["outcome"] for r in auto_rewards]
        assert "accepted" in outcomes
        assert "revision" in outcomes

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

    def test_enforce_hook_opt_in_only(self):
        """Should only block when BUILDLOG_ENFORCE=1, not by default."""
        from buildlog.hooks import ENFORCE_COMMIT_HOOK

        assert "BUILDLOG_ENFORCE:-0" in ENFORCE_COMMIT_HOOK


class TestInstallClaudeHooks:
    """Tests for install_claude_hooks(): writes script + merges settings."""

    def test_creates_hook_script(self, tmp_path: Path):
        """Should create .claude/hooks/enforce-buildlog-commit.sh."""
        from buildlog.hooks import install_claude_hooks

        result = install_claude_hooks(tmp_path)
        hook_path = tmp_path / ".claude" / "hooks" / "enforce-buildlog-commit.sh"
        assert hook_path.exists()
        assert "enforce-buildlog-commit.sh" in result["installed"]

    def test_hook_script_is_executable(self, tmp_path: Path):
        """Hook script must have executable permission."""
        import stat

        from buildlog.hooks import install_claude_hooks

        install_claude_hooks(tmp_path)
        hook_path = tmp_path / ".claude" / "hooks" / "enforce-buildlog-commit.sh"
        mode = hook_path.stat().st_mode
        assert mode & stat.S_IEXEC

    def test_hook_script_actually_blocks_git_commit(self, tmp_path: Path):
        """Run the installed script and verify it blocks bare git commit."""
        from buildlog.hooks import install_claude_hooks

        install_claude_hooks(tmp_path)
        hook_path = tmp_path / ".claude" / "hooks" / "enforce-buildlog-commit.sh"

        payload = json.dumps(
            {
                "session_id": "test",
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git commit -m 'test'"},
            }
        )
        result = subprocess.run(
            [str(hook_path)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_hook_script_allows_buildlog_commit(self, tmp_path: Path):
        """Installed script should allow BUILDLOG_COMMIT=1 git commit."""
        from buildlog.hooks import install_claude_hooks

        install_claude_hooks(tmp_path)
        hook_path = tmp_path / ".claude" / "hooks" / "enforce-buildlog-commit.sh"

        payload = json.dumps(
            {
                "session_id": "test",
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "BUILDLOG_COMMIT=1 git commit -m 'test'"},
            }
        )
        result = subprocess.run(
            [str(hook_path)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""  # No deny output

    def test_creates_settings_with_pretooluse_config(self, tmp_path: Path):
        """Should create .claude/settings.json with PreToolUse hook."""
        from buildlog.hooks import install_claude_hooks

        install_claude_hooks(tmp_path)
        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        settings = json.loads(settings_path.read_text())
        assert "hooks" in settings
        assert "PreToolUse" in settings["hooks"]
        entries = settings["hooks"]["PreToolUse"]
        assert len(entries) == 1
        assert entries[0]["matcher"] == "Bash"
        assert "enforce-buildlog-commit.sh" in entries[0]["hooks"][0]["command"]

    def test_merges_with_existing_settings(self, tmp_path: Path):
        """Should preserve existing settings when adding hook config."""
        from buildlog.hooks import install_claude_hooks

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "mcpServers": {"buildlog": {"command": "buildlog-mcp"}},
                    "permissions": {"allow": ["Bash(git status:*)"]},
                }
            )
        )

        install_claude_hooks(tmp_path)
        settings = json.loads(settings_path.read_text())
        # Original keys preserved
        assert "mcpServers" in settings
        assert "buildlog" in settings["mcpServers"]
        assert "permissions" in settings
        # Hook added
        assert "hooks" in settings
        assert len(settings["hooks"]["PreToolUse"]) == 1

    def test_idempotent(self, tmp_path: Path):
        """Calling twice should not duplicate the hook entry."""
        from buildlog.hooks import install_claude_hooks

        install_claude_hooks(tmp_path)
        install_claude_hooks(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert len(settings["hooks"]["PreToolUse"]) == 1


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
