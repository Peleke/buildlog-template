"""Tests for buildlog git hook installation."""

import os
import stat
from pathlib import Path

import pytest

from buildlog.hooks import (
    _HOOK_MARKER,
    ENFORCE_COMMIT_HOOK,
    POST_COMMIT_HOOK,
    PRE_COMMIT_CONFIG_ENTRY,
    PRE_COMMIT_HOOK,
    install_hooks,
)


class TestInstallHooks:
    """Tests for install_hooks()."""

    def _setup_git_repo(self, tmp_path: Path) -> Path:
        """Create a minimal .git structure."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        return tmp_path

    def test_no_hooks_flag(self, tmp_path: Path):
        """Should skip installation when no_hooks=True."""
        project = self._setup_git_repo(tmp_path)
        result = install_hooks(project, no_hooks=True)
        assert result["installed"] == []
        assert "skipped" in result["message"]

    def test_not_git_repo(self, tmp_path: Path):
        """Should skip when not a git repo."""
        result = install_hooks(tmp_path)
        assert result["installed"] == []
        assert "Not a git repository" in result["message"]

    def test_installs_pre_commit_standalone(self, tmp_path: Path):
        """Should install standalone pre-commit hook."""
        project = self._setup_git_repo(tmp_path)
        result = install_hooks(project)
        assert "pre-commit" in result["installed"]

        hook = tmp_path / ".git" / "hooks" / "pre-commit"
        assert hook.exists()
        content = hook.read_text()
        assert _HOOK_MARKER in content
        assert "main" in content

    def test_installs_post_commit(self, tmp_path: Path):
        """Should install post-commit hook."""
        project = self._setup_git_repo(tmp_path)
        result = install_hooks(project)
        assert "post-commit" in result["installed"]

        hook = tmp_path / ".git" / "hooks" / "post-commit"
        assert hook.exists()
        content = hook.read_text()
        assert "BUILDLOG_COMMIT" in content

    def test_hooks_are_executable(self, tmp_path: Path):
        """Installed hooks should be executable."""
        project = self._setup_git_repo(tmp_path)
        install_hooks(project)

        for name in ("pre-commit", "post-commit"):
            hook = tmp_path / ".git" / "hooks" / name
            assert hook.exists()
            assert os.access(hook, os.X_OK)

    def test_chains_with_existing_pre_commit(self, tmp_path: Path):
        """Should append to existing pre-commit hook, not clobber it."""
        project = self._setup_git_repo(tmp_path)
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir()

        existing_hook = hooks_dir / "pre-commit"
        existing_hook.write_text("#!/bin/sh\n# my existing hook\necho 'hello'\n")

        result = install_hooks(project)
        assert "pre-commit (appended)" in result["installed"]

        content = existing_hook.read_text()
        assert "my existing hook" in content  # Original preserved
        assert _HOOK_MARKER in content  # Buildlog added

    def test_chains_with_existing_post_commit(self, tmp_path: Path):
        """Should append to existing post-commit hook."""
        project = self._setup_git_repo(tmp_path)
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir()

        existing_hook = hooks_dir / "post-commit"
        existing_hook.write_text("#!/bin/sh\n# my hook\necho done\n")

        result = install_hooks(project)
        assert "post-commit (appended)" in result["installed"]

        content = existing_hook.read_text()
        assert "my hook" in content
        assert "BUILDLOG_COMMIT" in content

    def test_idempotent_no_double_install(self, tmp_path: Path):
        """Should not install twice."""
        project = self._setup_git_repo(tmp_path)
        install_hooks(project)
        result = install_hooks(project)

        # Second run should not install anything
        assert result["installed"] == []
        assert all(
            "already installed" in m
            for m in result["message"].split("; ")
            if "buildlog" in m
        )

    def test_pre_commit_config_integration(self, tmp_path: Path):
        """Should add to .pre-commit-config.yaml when it exists."""
        import yaml

        project = self._setup_git_repo(tmp_path)
        config = tmp_path / ".pre-commit-config.yaml"
        config.write_text(
            "repos:\n  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        )

        result = install_hooks(project)
        assert "pre-commit-config (branch protection)" in result["installed"]

        content = config.read_text()
        assert "prevent-commit-to-main" in content

        # Result should be valid YAML with all repos preserved
        parsed = yaml.safe_load(content)
        assert len(parsed["repos"]) == 3  # original + branch protection + enforcement
        ids = [
            h["id"]
            for repo in parsed["repos"]
            for h in repo.get("hooks", [])
            if "id" in h
        ]
        assert "prevent-commit-to-main" in ids
        assert "enforce-buildlog-commit" in ids

    def test_pre_commit_config_idempotent(self, tmp_path: Path):
        """Should not double-add to .pre-commit-config.yaml."""
        project = self._setup_git_repo(tmp_path)
        config = tmp_path / ".pre-commit-config.yaml"
        config.write_text(
            "repos:\n  - repo: local\n    hooks:\n"
            "      - id: prevent-commit-to-main\n"
        )

        result = install_hooks(project)
        # Should not add again
        assert "pre-commit-config (branch protection)" not in result["installed"]

    def test_pre_commit_config_no_standalone_hooks(self, tmp_path: Path):
        """When .pre-commit-config.yaml exists, both hooks go to yaml, not standalone.

        The pre-commit framework uses `exec` in .git/hooks/pre-commit, so
        appending to it would be dead code. Both branch protection and
        enforcement go into the yaml config instead.
        """
        import yaml

        project = self._setup_git_repo(tmp_path)
        config = tmp_path / ".pre-commit-config.yaml"
        config.write_text("repos: []\n")

        install_hooks(project)
        standalone = tmp_path / ".git" / "hooks" / "pre-commit"
        # Neither hook should be standalone when yaml exists
        if standalone.exists():
            content = standalone.read_text()
            assert "prevent direct commits to main" not in content
            assert "BUILDLOG_ENFORCE" not in content

        # Both should be in the yaml
        parsed = yaml.safe_load(config.read_text())
        ids = [
            h["id"]
            for repo in parsed["repos"]
            for h in repo.get("hooks", [])
            if "id" in h
        ]
        assert "prevent-commit-to-main" in ids
        assert "enforce-buildlog-commit" in ids

    def test_chains_enforce_hook_with_existing_pre_commit(self, tmp_path: Path):
        """Should append enforcement hook to existing pre-commit alongside branch protection."""
        project = self._setup_git_repo(tmp_path)
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir()

        existing_hook = hooks_dir / "pre-commit"
        existing_hook.write_text("#!/bin/sh\n# user lint hook\nflake8 .\n")

        install_hooks(project)

        content = existing_hook.read_text()
        assert "user lint hook" in content  # Original preserved
        assert "BUILDLOG_ENFORCE" in content  # Enforcement added

    def test_creates_hooks_dir(self, tmp_path: Path):
        """Should create .git/hooks/ if it doesn't exist."""
        project = self._setup_git_repo(tmp_path)
        hooks_dir = tmp_path / ".git" / "hooks"
        assert not hooks_dir.exists()

        install_hooks(project)
        assert hooks_dir.exists()


class TestHookConstants:
    """Tests for hook template content."""

    def test_pre_commit_checks_main(self):
        assert 'branch" = "main"' in PRE_COMMIT_HOOK

    def test_pre_commit_checks_master(self):
        assert 'branch" = "master"' in PRE_COMMIT_HOOK

    def test_post_commit_checks_env_var(self):
        assert "BUILDLOG_COMMIT" in POST_COMMIT_HOOK

    def test_pre_commit_config_entry_valid_yaml(self):
        """Should be valid YAML when appended to a config file."""
        import yaml

        full_config = "repos:\n" + PRE_COMMIT_CONFIG_ENTRY
        parsed = yaml.safe_load(full_config)
        assert "repos" in parsed

    def test_string_and_dict_forms_equivalent(self):
        """PRE_COMMIT_CONFIG_ENTRY (string) and _PRE_COMMIT_HOOK_DICT (dict) must match."""
        import yaml

        from buildlog.hooks import _PRE_COMMIT_HOOK_DICT

        parsed_string = yaml.safe_load("repos:\n" + PRE_COMMIT_CONFIG_ENTRY)
        string_hook = parsed_string["repos"][0]["hooks"][0]
        dict_hook = _PRE_COMMIT_HOOK_DICT["hooks"][0]

        assert string_hook["id"] == dict_hook["id"]
        assert string_hook["language"] == dict_hook["language"]
        assert string_hook["always_run"] == dict_hook["always_run"]
        assert string_hook["pass_filenames"] == dict_hook["pass_filenames"]


class TestBuildlogCommitEnvVar:
    """Tests that commit() sets BUILDLOG_COMMIT=1."""

    def test_env_var_in_commit_call(self, tmp_path: Path):
        """commit() should set BUILDLOG_COMMIT=1 in subprocess env."""
        from unittest.mock import MagicMock, patch

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="not a git repo", stdout=""
            )
            from buildlog.core import commit

            commit(buildlog_dir, ["-m", "test"])

            # First call is 'git commit'
            call_args = mock_run.call_args_list[0]
            env = call_args.kwargs.get("env", {})
            assert env.get("BUILDLOG_COMMIT") == "1"
