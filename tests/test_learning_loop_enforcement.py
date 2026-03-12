"""Tests for learning loop enforcement: session gating, gauntlet markers, auto-mistakes."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


class TestCommitBlocksWithoutSession:
    """commit() must block when no active experiment session exists."""

    def test_commit_blocked_without_active_session(self, tmp_path: Path):
        """commit() returns error when no session is active."""
        from buildlog.core.operations import commit

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        result = commit(buildlog_dir, git_args=["-m", "test"])
        assert result.error is not None
        assert "No active experiment session" in result.error

    def test_commit_allowed_with_active_session(self, tmp_path: Path):
        """commit() proceeds when a session is active."""
        from buildlog.core import start_session
        from buildlog.core.operations import commit

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")

        # Will fail at git commit (no repo), but should NOT fail at session check
        result = commit(buildlog_dir, git_args=["-m", "test"])
        # Error should be about git, not about session
        if result.error:
            assert "No active experiment session" not in result.error

    def test_commit_bypass_with_enforce_zero(self, tmp_path: Path):
        """BUILDLOG_ENFORCE=0 bypasses session check."""
        from buildlog.core.operations import commit

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        with patch.dict(os.environ, {"BUILDLOG_ENFORCE": "0"}):
            result = commit(buildlog_dir, git_args=["-m", "test"])
            # Should NOT block for session — might fail at git, that's fine
            if result.error:
                assert "No active experiment session" not in result.error

    def test_commit_session_check_failure_does_not_block(self, tmp_path: Path):
        """If storage is broken, don't block commits."""
        from buildlog.core.operations import commit

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        with patch(
            "buildlog.core.operations._get_storage",
            side_effect=RuntimeError("storage broken"),
        ):
            result = commit(buildlog_dir, git_args=["-m", "test"])
            # Should NOT block — might fail at git, that's fine
            if result.error:
                assert "No active experiment session" not in result.error


class TestGauntletMarker:
    """gauntlet_process_issues() writes marker on clean, accept_risk writes marker."""

    def test_clean_gauntlet_writes_marker(self, tmp_path: Path):
        """Action=clean should write gauntlet_cleared marker."""
        from buildlog.core.operations import (
            _get_gauntlet_marker_path,
            gauntlet_process_issues,
        )

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        # No issues = clean
        result = gauntlet_process_issues(buildlog_dir, issues=[])
        assert result.action == "clean"

        marker = _get_gauntlet_marker_path(buildlog_dir)
        assert marker.exists()

    def test_critical_gauntlet_no_marker(self, tmp_path: Path):
        """Action=fix_criticals should NOT write marker."""
        from buildlog.core.operations import (
            _get_gauntlet_marker_path,
            gauntlet_process_issues,
            start_session,
        )

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        # Need a session for log_mistake inside gauntlet
        start_session(buildlog_dir, error_class="test")

        result = gauntlet_process_issues(
            buildlog_dir,
            issues=[
                {"severity": "critical", "description": "bad", "rule_learned": "x"}
            ],
        )
        assert result.action == "fix_criticals"

        marker = _get_gauntlet_marker_path(buildlog_dir)
        assert not marker.exists()

    def test_accept_risk_writes_marker(self, tmp_path: Path):
        """gauntlet_accept_risk() should write marker."""
        from buildlog.core.operations import (
            _get_gauntlet_marker_path,
            gauntlet_accept_risk,
        )

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        gauntlet_accept_risk(
            remaining_issues=[{"severity": "minor", "description": "nit"}],
            buildlog_dir=buildlog_dir,
        )

        marker = _get_gauntlet_marker_path(buildlog_dir)
        assert marker.exists()

    def test_accept_risk_without_buildlog_dir_no_crash(self):
        """gauntlet_accept_risk() without buildlog_dir should not crash."""
        from buildlog.core.operations import gauntlet_accept_risk

        # No buildlog_dir = no marker, but no crash
        result = gauntlet_accept_risk(
            remaining_issues=[{"severity": "minor", "description": "nit"}],
        )
        assert result.accepted_issues == 1


class TestGauntletAutoLogsMistakes:
    """gauntlet_process_issues() auto-logs mistakes for criticals and majors."""

    def test_critical_auto_logs_mistake(self, tmp_path: Path):
        """Critical issue should auto-log a mistake."""
        from buildlog.core import start_session
        from buildlog.core.operations import gauntlet_process_issues
        from buildlog.storage import get_backend

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")

        gauntlet_process_issues(
            buildlog_dir,
            issues=[
                {
                    "severity": "critical",
                    "category": "security",
                    "description": "SQL injection in query builder",
                    "location": "src/db.py:42",
                    "rule_learned": "Always parameterize queries",
                }
            ],
        )

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        mistakes = backend.load_events(project_id, "mistakes")
        gauntlet_mistakes = [
            m for m in mistakes if m.get("error_class", "").startswith("gauntlet_")
        ]
        assert len(gauntlet_mistakes) == 1
        assert gauntlet_mistakes[0]["error_class"] == "gauntlet_security"
        assert "SQL injection" in gauntlet_mistakes[0]["description"]

    def test_major_auto_logs_mistake(self, tmp_path: Path):
        """Major issue should auto-log a mistake."""
        from buildlog.core import start_session
        from buildlog.core.operations import gauntlet_process_issues
        from buildlog.storage import get_backend

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")

        gauntlet_process_issues(
            buildlog_dir,
            issues=[
                {
                    "severity": "major",
                    "category": "error_handling",
                    "description": "Missing error handling",
                    "rule_learned": "Handle errors",
                }
            ],
        )

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        mistakes = backend.load_events(project_id, "mistakes")
        gauntlet_mistakes = [
            m for m in mistakes if m.get("error_class", "").startswith("gauntlet_")
        ]
        assert len(gauntlet_mistakes) == 1
        assert gauntlet_mistakes[0]["error_class"] == "gauntlet_error_handling"

    def test_minor_does_not_log_mistake(self, tmp_path: Path):
        """Minor issues should NOT auto-log mistakes."""
        from buildlog.core.operations import gauntlet_process_issues

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        gauntlet_process_issues(
            buildlog_dir,
            issues=[
                {
                    "severity": "minor",
                    "description": "Style nit",
                    "rule_learned": "Use pathlib",
                }
            ],
        )

        from buildlog.storage import get_backend

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        mistakes = backend.load_events(project_id, "mistakes")
        gauntlet_mistakes = [
            m for m in mistakes if m.get("error_class", "").startswith("gauntlet_")
        ]
        assert len(gauntlet_mistakes) == 0

    def test_multiple_issues_log_multiple_mistakes(self, tmp_path: Path):
        """Each critical/major should log its own mistake."""
        from buildlog.core import start_session
        from buildlog.core.operations import gauntlet_process_issues
        from buildlog.storage import get_backend

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        start_session(buildlog_dir, error_class="test")

        gauntlet_process_issues(
            buildlog_dir,
            issues=[
                {"severity": "critical", "description": "Bad 1", "rule_learned": "x"},
                {"severity": "major", "description": "Bad 2", "rule_learned": "y"},
                {"severity": "minor", "description": "Nit", "rule_learned": "z"},
            ],
        )

        backend, project_id = get_backend(buildlog_dir, project_root=tmp_path)
        mistakes = backend.load_events(project_id, "mistakes")
        gauntlet_mistakes = [
            m for m in mistakes if m.get("error_class", "").startswith("gauntlet_")
        ]
        # 1 critical + 1 major = 2 mistakes (minor excluded)
        assert len(gauntlet_mistakes) == 2


class TestHookScripts:
    """Tests that hook scripts exist and are executable."""

    HOOKS_DIR = Path(__file__).parent.parent / ".claude" / "hooks"

    @pytest.mark.parametrize(
        "script",
        [
            "enforce-buildlog-commit.sh",
            "session-start.sh",
            "session-end.sh",
            "post-tool-use.sh",
        ],
    )
    def test_hook_exists_and_executable(self, script: str):
        hook = self.HOOKS_DIR / script
        assert hook.exists(), f"{script} not found"
        assert os.access(hook, os.X_OK), f"{script} not executable"

    def test_pre_tool_use_denies_bare_git_commit(self):
        """PreToolUse hook should deny bare git commit."""
        hook = self.HOOKS_DIR / "enforce-buildlog-commit.sh"
        input_json = json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'test'"}}
        )
        result = subprocess.run(
            [str(hook)],
            input=input_json,
            capture_output=True,
            text=True,
            env={**os.environ, "BUILDLOG_ENFORCE": "1"},
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_pre_tool_use_allows_buildlog_commit(self):
        """PreToolUse hook should allow BUILDLOG_COMMIT=1."""
        hook = self.HOOKS_DIR / "enforce-buildlog-commit.sh"
        input_json = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "BUILDLOG_COMMIT=1 git commit -m 'test'"},
            }
        )
        result = subprocess.run(
            [str(hook)],
            input=input_json,
            capture_output=True,
            text=True,
            env={**os.environ, "BUILDLOG_ENFORCE": "1"},
        )
        assert result.returncode == 0
        # Should NOT output deny JSON
        assert "deny" not in result.stdout

    def test_pre_tool_use_denies_pr_without_marker(self, tmp_path: Path):
        """PreToolUse hook should deny gh pr create without gauntlet marker."""
        hook = self.HOOKS_DIR / "enforce-buildlog-commit.sh"
        input_json = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "gh pr create --title 'test'"},
            }
        )
        # Point CLAUDE_PROJECT_DIR at tmp_path (no marker there)
        env = {
            **os.environ,
            "BUILDLOG_ENFORCE": "1",
            "CLAUDE_PROJECT_DIR": str(tmp_path),
        }
        # Create buildlog dir so the hook can find it
        (tmp_path / "buildlog" / ".buildlog").mkdir(parents=True)

        result = subprocess.run(
            [str(hook)],
            input=input_json,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert (
            "gauntlet"
            in output["hookSpecificOutput"]["permissionDecisionReason"].lower()
        )

    def test_pre_tool_use_allows_pr_with_marker(self, tmp_path: Path):
        """PreToolUse hook should allow gh pr create with gauntlet marker."""
        hook = self.HOOKS_DIR / "enforce-buildlog-commit.sh"
        input_json = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "gh pr create --title 'test'"},
            }
        )
        # Create marker
        marker_dir = tmp_path / "buildlog" / ".buildlog"
        marker_dir.mkdir(parents=True)
        (marker_dir / "gauntlet_cleared").write_text("2026-02-14T00:00:00Z\n")

        env = {
            **os.environ,
            "BUILDLOG_ENFORCE": "1",
            "CLAUDE_PROJECT_DIR": str(tmp_path),
        }
        result = subprocess.run(
            [str(hook)],
            input=input_json,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "deny" not in result.stdout

    def test_enforce_zero_bypasses_all(self):
        """BUILDLOG_ENFORCE=0 should bypass all enforcement."""
        hook = self.HOOKS_DIR / "enforce-buildlog-commit.sh"
        input_json = json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'test'"}}
        )
        result = subprocess.run(
            [str(hook)],
            input=input_json,
            capture_output=True,
            text=True,
            env={**os.environ, "BUILDLOG_ENFORCE": "0"},
        )
        assert result.returncode == 0
        assert "deny" not in result.stdout


class TestSettingsJson:
    """Verify .claude/settings.json has all required hook types."""

    def test_settings_has_all_hook_types(self):
        settings_path = Path(__file__).parent.parent / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text())
        hooks = settings["hooks"]
        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks
        assert "SessionStart" in hooks
        assert "SessionEnd" in hooks

    def test_settings_hooks_point_to_existing_scripts(self):
        settings_path = Path(__file__).parent.parent / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text())
        project_dir = settings_path.parent.parent

        for hook_type, entries in settings["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    cmd = hook["command"]
                    # Replace $CLAUDE_PROJECT_DIR with actual path
                    script_path = cmd.replace(
                        '"$CLAUDE_PROJECT_DIR"', str(project_dir)
                    ).replace("$CLAUDE_PROJECT_DIR", str(project_dir))
                    # Extract the script path (may be quoted)
                    script_path = script_path.strip('"').strip("'")
                    assert Path(
                        script_path
                    ).exists(), (
                        f"{hook_type} hook points to missing script: {script_path}"
                    )
