"""Tests for `buildlog commit` CLI command."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from buildlog.cli import main


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch):
    """Create a minimal git repo with buildlog dir."""
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    # Create buildlog dir
    (tmp_path / "buildlog").mkdir()
    # Create a file to commit
    (tmp_path / "hello.py").write_text("print('hello')\n")
    subprocess.run(
        ["git", "add", "hello.py"], cwd=tmp_path, capture_output=True, check=True
    )
    # Switch to a feature branch to avoid branch protection
    subprocess.run(
        ["git", "checkout", "-b", "feat/test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    return tmp_path


class TestBuildlogCommit:
    """Tests for the commit command."""

    def test_commit_creates_entry(self, git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(main, ["commit", "-m", "feat: initial"])

        assert result.exit_code == 0, result.output + (result.exception or "")
        entries = list((git_repo / "buildlog").glob("*-*.md"))
        assert len(entries) == 1
        content = entries[0].read_text()
        assert "## Commits" in content
        assert "feat: initial" in content
        assert "hello.py" in content

    def test_commit_appends_to_existing_entry(self, git_repo: Path):
        from datetime import date

        today = date.today().isoformat()
        entry_path = git_repo / "buildlog" / f"{today}-existing.md"
        entry_path.write_text("# Existing Entry\n\n## Context\n\nSome work.\n")

        runner = CliRunner()
        result = runner.invoke(main, ["commit", "-m", "feat: second commit"])

        assert result.exit_code == 0, result.output
        content = entry_path.read_text()
        assert "# Existing Entry" in content
        assert "## Commits" in content
        assert "feat: second commit" in content

    def test_commit_with_explicit_slug(self, git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(
            main, ["commit", "--slug", "my-feature", "-m", "feat: stuff"]
        )

        assert result.exit_code == 0, result.output
        entries = list((git_repo / "buildlog").glob("*-my-feature.md"))
        assert len(entries) == 1

    def test_no_entry_flag_skips_entry(self, git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(main, ["commit", "--no-entry", "-m", "chore: fmt"])

        assert result.exit_code == 0, result.output
        entries = list((git_repo / "buildlog").glob("*-*.md"))
        assert len(entries) == 0

    def test_multiple_commits_append(self, git_repo: Path):
        runner = CliRunner()
        result1 = runner.invoke(main, ["commit", "-m", "feat: first"])
        assert result1.exit_code == 0, result1.output

        # Create another file for second commit
        (git_repo / "world.py").write_text("print('world')\n")
        subprocess.run(
            ["git", "add", "world.py"], cwd=git_repo, capture_output=True, check=True
        )

        result2 = runner.invoke(main, ["commit", "-m", "feat: second"])
        assert result2.exit_code == 0, result2.output

        entries = list((git_repo / "buildlog").glob("*-*.md"))
        assert len(entries) == 1
        content = entries[0].read_text()
        assert "feat: first" in content
        assert "feat: second" in content

    def test_explicit_entry_flag(self, git_repo: Path):
        entry_path = git_repo / "buildlog" / "custom-entry.md"
        entry_path.write_text("# Custom\n")

        runner = CliRunner()
        result = runner.invoke(
            main, ["commit", "--entry", str(entry_path), "-m", "feat: custom"]
        )

        assert result.exit_code == 0, result.output
        content = entry_path.read_text()
        assert "## Commits" in content
        assert "feat: custom" in content

    def test_failed_commit_no_entry(self, git_repo: Path):
        """If git commit fails, no entry is created/updated."""
        # First commit hello.py so nothing is left to stage
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Now try to commit with nothing staged — should fail
        runner = CliRunner()
        result = runner.invoke(main, ["commit", "-m", "should fail"])

        # git commit exits 1 when nothing to commit
        assert result.exit_code != 0
        entries = list((git_repo / "buildlog").glob("*-*.md"))
        assert len(entries) == 0
