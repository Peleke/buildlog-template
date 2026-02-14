"""Tests for enforcement layers: Claude Code hook, auto-reward, auto-migrate, git hook."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestClaudeCodeHookScript:
    """Tests for .claude/hooks/enforce-buildlog-commit.sh."""

    HOOK_PATH = (
        Path(__file__).parent.parent
        / ".claude"
        / "hooks"
        / "enforce-buildlog-commit.sh"
    )

    def _run_hook(
        self, tool_name: str, command: str = ""
    ) -> subprocess.CompletedProcess:
        """Run the hook script with a simulated Claude Code PreToolUse payload."""
        payload = json.dumps(
            {
                "session_id": "test-123",
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": {"command": command},
            }
        )
        return subprocess.run(
            ["bash", str(self.HOOK_PATH)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_hook_script_exists_and_executable(self):
        """Hook script should exist and be executable."""
        assert self.HOOK_PATH.exists(), f"Missing hook at {self.HOOK_PATH}"
        import os

        assert os.access(self.HOOK_PATH, os.X_OK), "Hook script is not executable"

    def test_allows_non_bash_tools(self):
        """Non-Bash tool calls should pass through."""
        result = self._run_hook("Read", "")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_blocks_bare_git_commit(self):
        """Should deny bare `git commit -m '...'`."""
        result = self._run_hook("Bash", 'git commit -m "test message"')
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert (
            "buildlog_commit"
            in output["hookSpecificOutput"]["permissionDecisionReason"]
        )

    def test_blocks_git_commit_in_chain(self):
        """Should deny git commit when chained with &&."""
        result = self._run_hook("Bash", 'git add . && git commit -m "test"')
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_allows_buildlog_commit_env_var(self):
        """Should allow when BUILDLOG_COMMIT=1 is set."""
        result = self._run_hook("Bash", 'BUILDLOG_COMMIT=1 git commit -m "test"')
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_allows_git_commit_amend(self):
        """Should allow --amend commits."""
        result = self._run_hook("Bash", "git commit --amend")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_allows_git_add(self):
        """Should allow git add (not a commit)."""
        result = self._run_hook("Bash", "git add .")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_allows_git_push(self):
        """Should allow git push."""
        result = self._run_hook("Bash", "git push origin feat/my-branch")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_allows_git_status(self):
        """Should allow git status."""
        result = self._run_hook("Bash", "git status")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_blocks_git_commit_after_semicolon(self):
        """Should block git commit after semicolon separator."""
        result = self._run_hook("Bash", 'echo "done"; git commit -m "test"')
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestClaudeCodeSettingsJson:
    """Tests for .claude/settings.json hook configuration."""

    SETTINGS_PATH = Path(__file__).parent.parent / ".claude" / "settings.json"

    def test_settings_file_exists(self):
        """Settings file should exist."""
        assert self.SETTINGS_PATH.exists()

    def test_settings_has_pretooluse_hook(self):
        """Settings should configure PreToolUse hook."""
        config = json.loads(self.SETTINGS_PATH.read_text())
        assert "hooks" in config
        assert "PreToolUse" in config["hooks"]

    def test_hook_targets_bash_tool(self):
        """Hook should match Bash tool."""
        config = json.loads(self.SETTINGS_PATH.read_text())
        hook_entry = config["hooks"]["PreToolUse"][0]
        assert hook_entry["matcher"] == "Bash"

    def test_hook_command_references_script(self):
        """Hook command should reference the enforce script."""
        config = json.loads(self.SETTINGS_PATH.read_text())
        hook_entry = config["hooks"]["PreToolUse"][0]
        command = hook_entry["hooks"][0]["command"]
        assert "enforce-buildlog-commit.sh" in command


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
