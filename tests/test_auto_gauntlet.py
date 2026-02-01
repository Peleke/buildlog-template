"""Tests for auto-gauntlet state management and commit gate."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from buildlog.cli import main
from buildlog.core.operations import (
    GauntletState,
    _load_auto_gauntlet_config,
    _sanitize_filepath,
    check_gauntlet_freshness,
    increment_gauntlet_staleness,
    load_gauntlet_state,
    record_gauntlet_run,
    save_gauntlet_state,
    track_dirty_file,
)
from buildlog.mcp.tools import buildlog_gauntlet_check


@pytest.fixture
def buildlog_dir(tmp_path):
    """Create a minimal buildlog directory."""
    d = tmp_path / "buildlog"
    d.mkdir()
    (d / ".buildlog").mkdir()
    return d


@pytest.fixture
def config_dir(buildlog_dir):
    """Create config with auto-gauntlet enabled."""
    config = {
        "auto_gauntlet": {
            "enabled": True,
            "commit_gate": {
                "enabled": True,
                "max_staleness_commits": 3,
                "fail_action": "warn",
            },
            "hooks": {
                "enabled": True,
                "track_dirty_files": True,
            },
        }
    }
    config_path = buildlog_dir / ".buildlog" / "config.json"
    config_path.write_text(json.dumps(config))
    return buildlog_dir


# 1. GauntletState serialization round-trip
def test_gauntlet_state_round_trip():
    state = GauntletState(
        last_run_timestamp="2026-01-31T00:00:00+00:00",
        last_run_commit="abc1234",
        commits_since_gauntlet=5,
        dirty_files=["src/main.py", "tests/test_main.py"],
        last_result_action="clean",
    )
    data = state.to_dict()
    restored = GauntletState.from_dict(data)
    assert restored.last_run_timestamp == state.last_run_timestamp
    assert restored.last_run_commit == state.last_run_commit
    assert restored.commits_since_gauntlet == state.commits_since_gauntlet
    assert restored.dirty_files == state.dirty_files
    assert restored.last_result_action == state.last_result_action


# 2. load_gauntlet_state returns default when file missing
def test_load_gauntlet_state_default(buildlog_dir):
    state = load_gauntlet_state(buildlog_dir)
    assert state.commits_since_gauntlet == 0
    assert state.dirty_files == []
    assert state.last_run_timestamp is None


# 3. increment_gauntlet_staleness increments counter
def test_increment_gauntlet_staleness(buildlog_dir):
    increment_gauntlet_staleness(buildlog_dir)
    state = load_gauntlet_state(buildlog_dir)
    assert state.commits_since_gauntlet == 1

    increment_gauntlet_staleness(buildlog_dir)
    state = load_gauntlet_state(buildlog_dir)
    assert state.commits_since_gauntlet == 2


# 4. record_gauntlet_run resets counter and dirty files
def test_record_gauntlet_run_resets(buildlog_dir):
    # Set up some state
    state = GauntletState(
        commits_since_gauntlet=5,
        dirty_files=["a.py", "b.py"],
    )
    save_gauntlet_state(buildlog_dir, state)

    with patch("buildlog.core.operations._subprocess") as mock_sub:
        mock_sub.run.return_value.returncode = 0
        mock_sub.run.return_value.stdout = "abc1234\n"
        mock_sub.TimeoutExpired = TimeoutError
        record_gauntlet_run(buildlog_dir, "clean")

    state = load_gauntlet_state(buildlog_dir)
    assert state.commits_since_gauntlet == 0
    assert state.dirty_files == []
    assert state.last_result_action == "clean"
    assert state.last_run_timestamp is not None


# 5. track_dirty_file appends without duplicates
def test_track_dirty_file_no_duplicates(buildlog_dir):
    track_dirty_file(buildlog_dir, "src/main.py")
    track_dirty_file(buildlog_dir, "src/main.py")
    track_dirty_file(buildlog_dir, "src/other.py")

    state = load_gauntlet_state(buildlog_dir)
    assert state.dirty_files == ["src/main.py", "src/other.py"]


# 6. check_gauntlet_freshness returns stale=True when over threshold
def test_check_freshness_stale(config_dir):
    state = GauntletState(commits_since_gauntlet=3)
    save_gauntlet_state(config_dir, state)

    result = check_gauntlet_freshness(config_dir)
    assert result["stale"] is True
    assert result["commits_since_gauntlet"] == 3
    assert "stale" in result["recommendation"].lower()


# 7. check_gauntlet_freshness returns stale=False when fresh
def test_check_freshness_fresh(config_dir):
    state = GauntletState(commits_since_gauntlet=2)
    save_gauntlet_state(config_dir, state)

    result = check_gauntlet_freshness(config_dir)
    assert result["stale"] is False
    assert result["recommendation"] == ""


# 8. Config loading returns empty dict when missing (fail open)
def test_config_missing_returns_empty(buildlog_dir):
    config = _load_auto_gauntlet_config(buildlog_dir)
    assert config == {}


# 9. Commit gate warns on stale (doesn't block by default)
def test_commit_gate_warns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # Set up buildlog dir with config and stale state
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()
    (buildlog_dir / "_TEMPLATE.md").write_text("# [YYYY-MM-DD]")

    config = {
        "auto_gauntlet": {
            "commit_gate": {
                "enabled": True,
                "max_staleness_commits": 3,
                "fail_action": "warn",
            }
        }
    }
    (buildlog_dir / ".buildlog" / "config.json").write_text(json.dumps(config))

    state = GauntletState(commits_since_gauntlet=5)
    save_gauntlet_state(buildlog_dir, state)

    import subprocess as _sub

    runner = CliRunner()
    with patch("buildlog.cli._get_current_git_branch", return_value="feat/test"):
        with patch("buildlog.cli.subprocess") as mock_sub:
            mock_sub.run.return_value.returncode = 0
            mock_sub.run.return_value.stdout = "abc123\nfeat: test\nsrc/main.py\n"
            mock_sub.CalledProcessError = _sub.CalledProcessError
            mock_sub.TimeoutExpired = _sub.TimeoutExpired
            result = runner.invoke(main, ["commit", "-m", "test"])

    # Should have printed a warning
    assert "WARNING" in result.output


# 10. Commit gate blocks when fail_action=block
def test_commit_gate_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    config = {
        "auto_gauntlet": {
            "commit_gate": {
                "enabled": True,
                "max_staleness_commits": 3,
                "fail_action": "block",
            }
        }
    }
    (buildlog_dir / ".buildlog" / "config.json").write_text(json.dumps(config))

    state = GauntletState(commits_since_gauntlet=5)
    save_gauntlet_state(buildlog_dir, state)

    runner = CliRunner()
    with patch("buildlog.cli._get_current_git_branch", return_value="feat/test"):
        result = runner.invoke(main, ["commit", "-m", "test"])

    assert result.exit_code == 1
    assert "BLOCKED" in result.output


# 11. --skip-gauntlet flag bypasses check
def test_skip_gauntlet_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    config = {
        "auto_gauntlet": {
            "commit_gate": {
                "enabled": True,
                "max_staleness_commits": 3,
                "fail_action": "block",
            }
        }
    }
    (buildlog_dir / ".buildlog" / "config.json").write_text(json.dumps(config))

    state = GauntletState(commits_since_gauntlet=5)
    save_gauntlet_state(buildlog_dir, state)

    runner = CliRunner()
    with patch("buildlog.cli._get_current_git_branch", return_value="feat/test"):
        with patch("buildlog.cli.subprocess") as mock_sub:
            mock_sub.run.return_value.returncode = 0
            mock_sub.run.return_value.stdout = "abc123\nfeat: test\nsrc/main.py\n"
            mock_sub.CalledProcessError = Exception
            mock_sub.TimeoutExpired = Exception
            result = runner.invoke(main, ["commit", "--skip-gauntlet", "-m", "test"])

    # Should NOT be blocked
    assert "BLOCKED" not in result.output


# 12. gauntlet check CLI exits 0/1 correctly
def test_gauntlet_check_cli_fresh(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    # Write config with threshold 3
    config = {
        "auto_gauntlet": {
            "commit_gate": {"max_staleness_commits": 3},
        }
    }
    (buildlog_dir / ".buildlog" / "config.json").write_text(json.dumps(config))

    state = GauntletState(commits_since_gauntlet=1)
    save_gauntlet_state(buildlog_dir, state)

    runner = CliRunner()
    result = runner.invoke(main, ["gauntlet", "check"])
    assert result.exit_code == 0
    assert "Fresh" in result.output


def test_gauntlet_check_cli_stale(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    config = {
        "auto_gauntlet": {
            "commit_gate": {"max_staleness_commits": 3},
        }
    }
    (buildlog_dir / ".buildlog" / "config.json").write_text(json.dumps(config))

    state = GauntletState(commits_since_gauntlet=5)
    save_gauntlet_state(buildlog_dir, state)

    runner = CliRunner()
    result = runner.invoke(main, ["gauntlet", "check"])
    assert result.exit_code == 1
    assert "STALE" in result.output


def test_gauntlet_check_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    config = {
        "auto_gauntlet": {
            "commit_gate": {"max_staleness_commits": 3},
        }
    }
    (buildlog_dir / ".buildlog" / "config.json").write_text(json.dumps(config))

    state = GauntletState(commits_since_gauntlet=1)
    save_gauntlet_state(buildlog_dir, state)

    runner = CliRunner()
    result = runner.invoke(main, ["gauntlet", "check", "--json"])
    data = json.loads(result.output)
    assert data["stale"] is False
    assert data["commits_since_gauntlet"] == 1


# 13. gauntlet_process_issues resets gauntlet state
def test_gauntlet_process_issues_resets_state(buildlog_dir):
    # Set up stale state
    state = GauntletState(commits_since_gauntlet=5, dirty_files=["a.py"])
    save_gauntlet_state(buildlog_dir, state)

    from buildlog.core.operations import gauntlet_process_issues

    with patch("buildlog.core.operations._subprocess") as mock_sub:
        mock_sub.run.return_value.returncode = 0
        mock_sub.run.return_value.stdout = "abc1234\n"
        mock_sub.TimeoutExpired = TimeoutError
        gauntlet_process_issues(buildlog_dir, issues=[], iteration=1)

    state = load_gauntlet_state(buildlog_dir)
    assert state.commits_since_gauntlet == 0
    assert state.dirty_files == []


# -------------------------------------------------------------------------
# Path validation tests
# -------------------------------------------------------------------------


def test_sanitize_filepath_rejects_absolute():
    assert _sanitize_filepath("/etc/passwd") is None


def test_sanitize_filepath_rejects_traversal():
    assert _sanitize_filepath("../../etc/passwd") is None
    assert _sanitize_filepath("foo/../../../bar") is None


def test_sanitize_filepath_rejects_long_paths():
    assert _sanitize_filepath("a" * 501) is None


def test_sanitize_filepath_rejects_empty():
    assert _sanitize_filepath("") is None
    assert _sanitize_filepath(None) is None


def test_sanitize_filepath_accepts_valid():
    assert _sanitize_filepath("src/main.py") is not None
    assert _sanitize_filepath("tests/test_foo.py") is not None


def test_track_dirty_file_rejects_traversal(buildlog_dir):
    track_dirty_file(buildlog_dir, "../../etc/passwd")
    state = load_gauntlet_state(buildlog_dir)
    assert state.dirty_files == []


def test_track_dirty_file_bounds_list(buildlog_dir):
    """dirty_files list is bounded at 500."""
    state = GauntletState(dirty_files=[f"file{i}.py" for i in range(500)])
    save_gauntlet_state(buildlog_dir, state)
    track_dirty_file(buildlog_dir, "one_more.py")
    state = load_gauntlet_state(buildlog_dir)
    assert len(state.dirty_files) == 500
    assert "one_more.py" not in state.dirty_files


# -------------------------------------------------------------------------
# Edge case tests
# -------------------------------------------------------------------------


def test_load_gauntlet_state_malformed_json(buildlog_dir):
    path = buildlog_dir / ".buildlog" / "gauntlet_state.json"
    path.write_text("{invalid json!!")
    state = load_gauntlet_state(buildlog_dir)
    assert state.commits_since_gauntlet == 0


def test_load_config_malformed_json(buildlog_dir):
    path = buildlog_dir / ".buildlog" / "config.json"
    path.write_text("{bad json")
    config = _load_auto_gauntlet_config(buildlog_dir)
    assert config == {}


def test_check_freshness_no_config_uses_default_threshold(buildlog_dir):
    """Without config, default threshold of 3 is used."""
    state = GauntletState(commits_since_gauntlet=3)
    save_gauntlet_state(buildlog_dir, state)
    result = check_gauntlet_freshness(buildlog_dir)
    assert result["stale"] is True


def test_check_freshness_no_config_below_default(buildlog_dir):
    state = GauntletState(commits_since_gauntlet=2)
    save_gauntlet_state(buildlog_dir, state)
    result = check_gauntlet_freshness(buildlog_dir)
    assert result["stale"] is False


# -------------------------------------------------------------------------
# CLI: track-file and track-edit
# -------------------------------------------------------------------------


def test_gauntlet_track_file_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    runner = CliRunner()
    result = runner.invoke(main, ["gauntlet", "track-file", "src/foo.py"])
    assert result.exit_code == 0

    state = load_gauntlet_state(buildlog_dir)
    assert "src/foo.py" in state.dirty_files


def test_gauntlet_track_file_rejects_bad_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    runner = CliRunner()
    runner.invoke(main, ["gauntlet", "track-file", "/etc/passwd"])
    state = load_gauntlet_state(buildlog_dir)
    assert state.dirty_files == []


def test_gauntlet_track_edit_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    stdin_data = json.dumps({"tool_input": {"file_path": "src/bar.py"}})
    runner = CliRunner()
    result = runner.invoke(main, ["gauntlet", "track-edit"], input=stdin_data)
    assert result.exit_code == 0

    state = load_gauntlet_state(buildlog_dir)
    assert "src/bar.py" in state.dirty_files


def test_gauntlet_track_edit_bad_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    runner = CliRunner()
    result = runner.invoke(main, ["gauntlet", "track-edit"], input="not json")
    assert result.exit_code == 0

    state = load_gauntlet_state(buildlog_dir)
    assert state.dirty_files == []


def test_gauntlet_track_edit_no_file_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    stdin_data = json.dumps({"tool_input": {"other_key": "value"}})
    runner = CliRunner()
    runner.invoke(main, ["gauntlet", "track-edit"], input=stdin_data)

    state = load_gauntlet_state(buildlog_dir)
    assert state.dirty_files == []


# -------------------------------------------------------------------------
# CLI: gauntlet check --event
# -------------------------------------------------------------------------


def test_gauntlet_check_event_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    config = {"auto_gauntlet": {"commit_gate": {"max_staleness_commits": 3}}}
    (buildlog_dir / ".buildlog" / "config.json").write_text(json.dumps(config))
    state = GauntletState(commits_since_gauntlet=1)
    save_gauntlet_state(buildlog_dir, state)

    runner = CliRunner()
    result = runner.invoke(main, ["gauntlet", "check", "--json", "--event", "stop"])
    data = json.loads(result.output)
    assert data["event"] == "stop"
    assert data["stale"] is False


# -------------------------------------------------------------------------
# MCP tool test
# -------------------------------------------------------------------------


def test_buildlog_gauntlet_check_mcp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    config = {"auto_gauntlet": {"commit_gate": {"max_staleness_commits": 3}}}
    (buildlog_dir / ".buildlog" / "config.json").write_text(json.dumps(config))
    state = GauntletState(commits_since_gauntlet=5)
    save_gauntlet_state(buildlog_dir, state)

    result = buildlog_gauntlet_check(buildlog_dir=str(buildlog_dir))
    assert result["stale"] is True
    assert result["commits_since_gauntlet"] == 5


def test_buildlog_gauntlet_check_mcp_fresh(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    buildlog_dir = tmp_path / "buildlog"
    buildlog_dir.mkdir()
    (buildlog_dir / ".buildlog").mkdir()

    result = buildlog_gauntlet_check(buildlog_dir=str(buildlog_dir))
    assert result["stale"] is False


# -------------------------------------------------------------------------
# gauntlet_process_issues categorization test
# -------------------------------------------------------------------------


def test_gauntlet_process_issues_categorizes(buildlog_dir):
    issues = [
        {
            "severity": "critical",
            "category": "security",
            "description": "SQL injection",
            "rule_learned": "Parameterize queries",
        },
        {
            "severity": "major",
            "category": "testing",
            "description": "No tests",
            "rule_learned": "Write tests",
        },
        {
            "severity": "minor",
            "category": "workflow",
            "description": "Style",
            "rule_learned": "Follow style guide",
        },
        {
            "severity": "nitpick",
            "category": "workflow",
            "description": "Naming",
            "rule_learned": "Use clear names",
        },
    ]

    from buildlog.core.operations import gauntlet_process_issues

    with patch("buildlog.core.operations._subprocess") as mock_sub:
        mock_sub.run.return_value.returncode = 0
        mock_sub.run.return_value.stdout = "abc1234\n"
        mock_sub.TimeoutExpired = TimeoutError
        result = gauntlet_process_issues(buildlog_dir, issues, iteration=2)

    assert result.action == "fix_criticals"
    assert len(result.criticals) == 1
    assert len(result.majors) == 1
    assert len(result.minors) == 2  # minor + nitpick
    assert result.iteration == 2


def test_gauntlet_process_issues_checkpoint_majors(buildlog_dir):
    issues = [
        {
            "severity": "major",
            "category": "testing",
            "description": "No tests",
            "rule_learned": "Write tests",
        },
    ]

    from buildlog.core.operations import gauntlet_process_issues

    with patch("buildlog.core.operations._subprocess") as mock_sub:
        mock_sub.run.return_value.returncode = 0
        mock_sub.run.return_value.stdout = "abc\n"
        mock_sub.TimeoutExpired = TimeoutError
        result = gauntlet_process_issues(buildlog_dir, issues, iteration=3)

    assert result.action == "checkpoint_majors"


def test_gauntlet_process_issues_clean(buildlog_dir):
    from buildlog.core.operations import gauntlet_process_issues

    with patch("buildlog.core.operations._subprocess") as mock_sub:
        mock_sub.run.return_value.returncode = 0
        mock_sub.run.return_value.stdout = "abc\n"
        mock_sub.TimeoutExpired = TimeoutError
        result = gauntlet_process_issues(buildlog_dir, [], iteration=4)

    assert result.action == "clean"
