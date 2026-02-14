"""Dogfood tests for workflow enforcement.

These tests exercise the REAL enforcement mechanisms end-to-end,
in real git repos, with real hooks. No mocks. The hooks either
block what they should block, or they don't.

What this proves:
1. Pre-commit hook prevents commits to main/master
2. Pre-commit hook blocks bare git commit on feature branches (enforcement always-on)
3. Pre-commit hook allows BUILDLOG_COMMIT=1 commits on feature branches
4. Post-commit hook nudges toward buildlog_commit (when enforcement disabled)
5. Post-commit hook is silent when BUILDLOG_COMMIT=1
6. `buildlog verify --fix` detects + repairs missing workflow section
7. Full init sets up the entire enforcement stack
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from buildlog.cli import main
from buildlog.hooks import install_hooks


def _git(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a git command in the given directory."""
    run_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=run_env,
    )


@pytest.fixture
def real_git_repo(tmp_path: Path) -> Path:
    """A real git repo with an initial commit on main."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "dogfood@test.com")
    _git(tmp_path, "config", "user.name", "Dogfood Test")
    (tmp_path / "README.md").write_text("# Test\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "initial", "--no-verify")
    return tmp_path


class TestPreCommitHookBlocksMain:
    """The pre-commit hook must actually block commits to main."""

    def test_blocks_commit_on_main(self, real_git_repo: Path):
        """Committing on main should FAIL with the hook installed."""
        install_hooks(real_git_repo)

        # Stage a change
        (real_git_repo / "file.py").write_text("x = 1\n")
        _git(real_git_repo, "add", "file.py")

        # Try to commit — should be blocked by pre-commit hook
        result = _git(real_git_repo, "commit", "-m", "should fail")
        assert result.returncode != 0, (
            f"Commit on main should have been blocked!\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "not allowed" in result.stderr or "not allowed" in result.stdout

    def test_blocks_bare_commit_on_feature_branch(self, real_git_repo: Path):
        """Bare git commit on a feature branch should be blocked (enforcement is always-on)."""
        install_hooks(real_git_repo)

        _git(real_git_repo, "checkout", "-b", "feat/dogfood-test")
        (real_git_repo / "file.py").write_text("x = 1\n")
        _git(real_git_repo, "add", "file.py")

        result = _git(real_git_repo, "commit", "-m", "should fail")
        assert result.returncode != 0, (
            f"Bare commit on feature branch should be blocked by enforcement!\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "blocked" in combined.lower() or "buildlog" in combined.lower()

    def test_allows_buildlog_commit_on_feature_branch(self, real_git_repo: Path):
        """Commit via buildlog_commit (BUILDLOG_COMMIT=1) should succeed on feature branches."""
        install_hooks(real_git_repo)

        _git(real_git_repo, "checkout", "-b", "feat/dogfood-test")
        (real_git_repo / "file.py").write_text("x = 1\n")
        _git(real_git_repo, "add", "file.py")

        result = _git(
            real_git_repo,
            "commit",
            "-m",
            "should succeed",
            env={"BUILDLOG_COMMIT": "1"},
        )
        assert result.returncode == 0, (
            f"Commit with BUILDLOG_COMMIT=1 should succeed on feature branch!\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestPostCommitHookNudge:
    """The post-commit hook must nudge users toward buildlog_commit."""

    def test_nudge_fires_without_env_var(self, real_git_repo: Path):
        """Post-commit should print nudge when BUILDLOG_COMMIT is not set.

        Requires BUILDLOG_ENFORCE=0 because enforcement (always-on) would
        block the commit before the post-commit nudge fires.
        """
        install_hooks(real_git_repo)

        _git(real_git_repo, "checkout", "-b", "feat/nudge-test")
        (real_git_repo / "file.py").write_text("x = 1\n")
        _git(real_git_repo, "add", "file.py")

        # Commit WITHOUT BUILDLOG_COMMIT, enforcement disabled
        env = {k: v for k, v in os.environ.items() if k != "BUILDLOG_COMMIT"}
        env["BUILDLOG_ENFORCE"] = "0"
        result = _git(real_git_repo, "commit", "-m", "raw commit", env=env)
        assert result.returncode == 0

        # Should see the nudge in stdout (post-commit hooks write to stdout)
        combined = result.stdout + result.stderr
        assert "buildlog" in combined.lower(), (
            f"Post-commit nudge should mention buildlog.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_nudge_silent_with_env_var(self, real_git_repo: Path):
        """Post-commit should be silent when BUILDLOG_COMMIT=1."""
        install_hooks(real_git_repo)

        _git(real_git_repo, "checkout", "-b", "feat/silent-test")
        (real_git_repo / "file.py").write_text("x = 1\n")
        _git(real_git_repo, "add", "file.py")

        # Commit WITH BUILDLOG_COMMIT=1 (simulates buildlog_commit path)
        result = _git(
            real_git_repo,
            "commit",
            "-m",
            "buildlog commit",
            env={"BUILDLOG_COMMIT": "1"},
        )
        assert result.returncode == 0

        # Should NOT see the nudge
        combined = result.stdout + result.stderr
        assert "Tip:" not in combined, (
            f"Post-commit nudge should be suppressed with BUILDLOG_COMMIT=1.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestVerifyFixDogfood:
    """buildlog verify --fix should detect and repair a broken setup."""

    def test_detect_and_fix_missing_workflow(self, real_git_repo: Path, monkeypatch):
        """Full cycle: broken → detect → fix → verify passes."""
        monkeypatch.chdir(real_git_repo)

        # Set up buildlog dir (simulates partial init)
        buildlog_dir = real_git_repo / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()
        (real_git_repo / "CLAUDE.md").write_text("# Dev Guidelines\n")

        runner = CliRunner()

        # Step 1: Verify should report failures (no workflow section)
        result = runner.invoke(main, ["verify", "--json"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert data["ok"] is False, "Should detect missing workflow section"
        failed_names = [c["name"] for c in data["failed"]]
        assert "workflow_section" in failed_names

        # Step 2: Run --fix
        result = runner.invoke(main, ["verify", "--fix"])
        assert result.exit_code == 0
        assert "[FIX]" in result.output

        # Step 3: Verify again — should pass now
        result = runner.invoke(main, ["verify", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # workflow_section should now be in passed, not failed
        passed_names = [c["name"] for c in data["passed"]]
        assert "workflow_section" in passed_names


class TestFullInitDogfood:
    """buildlog init should set up the entire enforcement stack."""

    def test_init_produces_working_enforcement(self, real_git_repo: Path, monkeypatch):
        """After init, the enforcement stack should be functional."""
        monkeypatch.chdir(real_git_repo)

        # Create CLAUDE.md before init (init appends to it)
        (real_git_repo / "CLAUDE.md").write_text("# Dev\n")

        runner = CliRunner()

        # Run init (mock copier but let everything else be real)
        _real_run = subprocess.run

        def copier_mock(cmd, *args, **kwargs):
            if isinstance(cmd, list) and any("copier" in str(c) for c in cmd):
                (real_git_repo / "buildlog").mkdir(exist_ok=True)
                (real_git_repo / "buildlog" / ".buildlog").mkdir(exist_ok=True)
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="", stderr=""
                )
            return _real_run(cmd, *args, **kwargs)

        from unittest.mock import patch

        with patch("buildlog.cli.subprocess.run", side_effect=copier_mock):
            result = runner.invoke(main, ["init", "--defaults", "--no-mcp"])
        assert result.exit_code == 0, result.output

        # Verify 1: Pre-commit hook exists and is executable
        pre_commit = real_git_repo / ".git" / "hooks" / "pre-commit"
        assert pre_commit.exists(), "Pre-commit hook should be installed"
        assert os.access(pre_commit, os.X_OK), "Pre-commit hook should be executable"

        # Verify 2: Post-commit hook exists and is executable
        post_commit = real_git_repo / ".git" / "hooks" / "post-commit"
        assert post_commit.exists(), "Post-commit hook should be installed"
        assert os.access(post_commit, os.X_OK), "Post-commit hook should be executable"

        # Verify 3: CLAUDE.md has workflow section
        from buildlog.constants import _WORKFLOW_SECTION_START

        content = (real_git_repo / "CLAUDE.md").read_text()
        assert (
            _WORKFLOW_SECTION_START in content
        ), "CLAUDE.md should have workflow section after init"

        # Verify 4: Pre-commit hook actually blocks main
        (real_git_repo / "test.txt").write_text("test\n")
        _git(real_git_repo, "add", "test.txt")
        commit_result = _git(real_git_repo, "commit", "-m", "blocked?")
        assert (
            commit_result.returncode != 0
        ), "Pre-commit hook should block commits on main after init"

        # Verify 5: Feature branch commits work via buildlog_commit (BUILDLOG_COMMIT=1)
        _git(real_git_repo, "checkout", "-b", "feat/dogfood-full")
        commit_result = _git(
            real_git_repo,
            "commit",
            "-m",
            "should work",
            env={"BUILDLOG_COMMIT": "1"},
        )
        assert commit_result.returncode == 0, (
            f"Feature branch commits with BUILDLOG_COMMIT=1 should work!\n"
            f"stdout: {commit_result.stdout}\nstderr: {commit_result.stderr}"
        )
