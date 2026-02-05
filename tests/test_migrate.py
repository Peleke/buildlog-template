"""Tests for migrate_project()."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.storage.migrate import migrate_project
from buildlog.storage.schema import open_db
from buildlog.storage.sqlite import SQLiteBackend


@pytest.fixture
def legacy_project(tmp_path: Path):
    """Create a legacy project with sample data files."""
    project_root = tmp_path / "my-project"
    project_root.mkdir()
    buildlog_dir = project_root / "buildlog"
    buildlog_dir.mkdir()
    dot = buildlog_dir / ".buildlog"
    dot.mkdir()

    # promoted.json
    (dot / "promoted.json").write_text(
        json.dumps(
            {
                "skill_ids": ["arch-abc", "wf-xyz"],
                "promoted_at": {"arch-abc": "2026-01-01"},
            }
        )
    )

    # rejected.json
    (dot / "rejected.json").write_text(
        json.dumps({"skill_ids": ["tool-bad"], "rejected_at": {}})
    )

    # review_learnings.json
    (dot / "review_learnings.json").write_text(
        json.dumps(
            {
                "learnings": {
                    "arch-abc": {
                        "id": "arch-abc",
                        "rule": "Always test",
                        "category": "architectural",
                        "severity": "critical",
                        "source": "review:test",
                        "first_seen": "2026-01-01T00:00:00",
                        "last_reinforced": "2026-01-01T00:00:00",
                        "reinforcement_count": 1,
                        "contradiction_count": 0,
                        "functional_principle": None,
                    }
                },
                "review_history": [
                    {
                        "timestamp": "2026-01-01T00:00:00",
                        "source": "review:test",
                        "issues_count": 1,
                        "new_learning_ids": ["arch-abc"],
                        "reinforced_learning_ids": [],
                    }
                ],
            }
        )
    )

    # reward_events.jsonl
    (dot / "reward_events.jsonl").write_text(
        json.dumps(
            {
                "id": "rew-1",
                "timestamp": "2026-01-01T00:00:00",
                "outcome": "accepted",
                "reward_value": 1.0,
                "rules_active": ["arch-abc"],
            }
        )
        + "\n"
    )

    # sessions.jsonl
    (dot / "sessions.jsonl").write_text(
        json.dumps(
            {
                "id": "sess-1",
                "started_at": "2026-01-01T00:00:00",
                "ended_at": "2026-01-01T01:00:00",
                "rules_at_start": ["arch-abc"],
                "rules_at_end": ["arch-abc"],
                "selected_rules": ["arch-abc"],
            }
        )
        + "\n"
    )

    # mistakes.jsonl
    (dot / "mistakes.jsonl").write_text(
        json.dumps(
            {
                "id": "mistake-1",
                "session_id": "sess-1",
                "timestamp": "2026-01-01T00:30:00",
                "error_class": "missing_test",
                "description": "Forgot test",
                "semantic_hash": "abc123",
                "was_repeat": False,
            }
        )
        + "\n"
    )

    # active_session.json
    (dot / "active_session.json").write_text(
        json.dumps({"id": "active-1", "started_at": "2026-01-02T00:00:00"})
    )

    return project_root


@pytest.fixture
def db_path(tmp_path: Path):
    """Temp path for global DB."""
    return tmp_path / ".buildlog" / "buildlog.db"


def test_migrate_full(legacy_project: Path, db_path: Path):
    """Full migration: all files migrated and renamed."""
    buildlog_dir = legacy_project / "buildlog"
    dot = buildlog_dir / ".buildlog"

    with patch("buildlog.storage.migrate.GLOBAL_DB_PATH", db_path):
        lines = migrate_project(buildlog_dir, project_root=legacy_project)

    summary = "\n".join(lines)
    assert "Migration complete" in summary
    assert "promoted.json" in summary
    assert "rejected.json" in summary

    # Originals should be renamed
    assert (dot / "promoted.json.migrated").exists()
    assert not (dot / "promoted.json").exists()
    assert (dot / "reward_events.jsonl.migrated").exists()

    # Verify data in SQLite
    conn = open_db(db_path)
    backend = SQLiteBackend(conn)
    # We need the actual project_id
    row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
    pid = row["id"]

    promoted = backend.load_id_set(pid, "promoted")
    assert "arch-abc" in promoted
    assert "wf-xyz" in promoted

    rejected = backend.load_id_set(pid, "rejected")
    assert "tool-bad" in rejected

    learnings = backend.load_learnings(pid)
    assert "arch-abc" in learnings["learnings"]
    assert len(learnings["review_history"]) == 1

    rewards = backend.load_events(pid, "rewards")
    assert len(rewards) == 1
    assert rewards[0]["outcome"] == "accepted"

    sessions = backend.load_events(pid, "sessions")
    assert len(sessions) == 1

    mistakes = backend.load_events(pid, "mistakes")
    assert len(mistakes) == 1

    active = backend.load_active_session(pid)
    assert active is not None
    assert active["id"] == "active-1"

    conn.close()


def test_migrate_dry_run(legacy_project: Path, db_path: Path):
    """Dry run should not modify files."""
    buildlog_dir = legacy_project / "buildlog"
    dot = buildlog_dir / ".buildlog"

    with patch("buildlog.storage.migrate.GLOBAL_DB_PATH", db_path):
        lines = migrate_project(buildlog_dir, project_root=legacy_project, dry_run=True)

    summary = "\n".join(lines)
    assert "DRY RUN" in summary
    assert "WILL MIGRATE" in summary

    # Files should NOT be renamed
    assert (dot / "promoted.json").exists()
    assert not (dot / "promoted.json.migrated").exists()

    # DB should NOT be created
    assert not db_path.exists()


def test_migrate_idempotent(legacy_project: Path, db_path: Path):
    """Running migrate twice should succeed without errors."""
    buildlog_dir = legacy_project / "buildlog"

    with patch("buildlog.storage.migrate.GLOBAL_DB_PATH", db_path):
        migrate_project(buildlog_dir, project_root=legacy_project)
        # Second run — all files are .migrated now
        lines2 = migrate_project(buildlog_dir, project_root=legacy_project)

    summary2 = "\n".join(lines2)
    assert "SKIP" in summary2 or "Migration complete" in summary2


def test_migrate_no_buildlog_dir(tmp_path: Path, db_path: Path):
    """Non-existent .buildlog/ → graceful message."""
    buildlog_dir = tmp_path / "empty" / "buildlog"
    buildlog_dir.mkdir(parents=True)

    with patch("buildlog.storage.migrate.GLOBAL_DB_PATH", db_path):
        lines = migrate_project(buildlog_dir, project_root=tmp_path / "empty")

    assert any("nothing to migrate" in line.lower() for line in lines)
