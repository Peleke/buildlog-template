"""Tests for get_backend() resolution logic."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.storage import SQLiteBackend, get_backend
from buildlog.storage.schema import open_db


@pytest.fixture
def global_db(tmp_path):
    """Create a real global SQLite DB in a temp location."""
    db_path = tmp_path / ".buildlog-global" / "buildlog.db"
    db_path.parent.mkdir(parents=True)
    conn = open_db(db_path)
    return db_path, conn


class TestOrphanedLocalDataWarning:
    """Case 2: global DB exists, project not registered, local files present."""

    def test_warns_on_unmigrated_local_files(self, tmp_path, global_db, caplog):
        db_path, conn = global_db

        # Set up a project with local legacy data
        project_root = tmp_path / "my-project"
        buildlog_dir = project_root / "buildlog"
        legacy_dot = buildlog_dir / ".buildlog"
        legacy_dot.mkdir(parents=True)
        (legacy_dot / "reward_events.jsonl").write_text('{"event": "test"}\n')

        with (
            patch("buildlog.storage.GLOBAL_DB_PATH", db_path),
            patch("buildlog.storage._conn_cache", {}),
            caplog.at_level(logging.WARNING, logger="buildlog.storage"),
        ):
            backend, pid = get_backend(buildlog_dir, project_root=project_root)

        assert isinstance(backend, SQLiteBackend)
        assert "un-migrated local data" in caplog.text
        assert "buildlog migrate" in caplog.text

    def test_no_warning_when_all_files_migrated(self, tmp_path, global_db, caplog):
        db_path, conn = global_db

        project_root = tmp_path / "my-project"
        buildlog_dir = project_root / "buildlog"
        legacy_dot = buildlog_dir / ".buildlog"
        legacy_dot.mkdir(parents=True)
        # Only .migrated files — should not warn
        (legacy_dot / "reward_events.jsonl.migrated").write_text("")

        with (
            patch("buildlog.storage.GLOBAL_DB_PATH", db_path),
            patch("buildlog.storage._conn_cache", {}),
            caplog.at_level(logging.WARNING, logger="buildlog.storage"),
        ):
            backend, pid = get_backend(buildlog_dir, project_root=project_root)

        assert isinstance(backend, SQLiteBackend)
        assert "un-migrated" not in caplog.text

    def test_no_warning_when_no_local_dir(self, tmp_path, global_db, caplog):
        db_path, conn = global_db

        project_root = tmp_path / "my-project"
        project_root.mkdir(parents=True)
        buildlog_dir = project_root / "buildlog"
        # No .buildlog dir at all

        with (
            patch("buildlog.storage.GLOBAL_DB_PATH", db_path),
            patch("buildlog.storage._conn_cache", {}),
            caplog.at_level(logging.WARNING, logger="buildlog.storage"),
        ):
            backend, pid = get_backend(buildlog_dir, project_root=project_root)

        assert isinstance(backend, SQLiteBackend)
        assert "un-migrated" not in caplog.text

    def test_no_warning_when_project_already_registered(
        self, tmp_path, global_db, caplog
    ):
        """Case 1: project already registered — no warning even with local files."""
        db_path, conn = global_db

        project_root = tmp_path / "my-project"
        buildlog_dir = project_root / "buildlog"
        legacy_dot = buildlog_dir / ".buildlog"
        legacy_dot.mkdir(parents=True)
        (legacy_dot / "sessions.jsonl").write_text('{"session": "test"}\n')

        with (
            patch("buildlog.storage.GLOBAL_DB_PATH", db_path),
            patch("buildlog.storage._conn_cache", {}),
        ):
            # First call registers the project
            get_backend(buildlog_dir, project_root=project_root)

        # Second call — project is now registered (Case 1), should not warn
        with (
            patch("buildlog.storage.GLOBAL_DB_PATH", db_path),
            patch("buildlog.storage._conn_cache", {}),
            caplog.at_level(logging.WARNING, logger="buildlog.storage"),
        ):
            caplog.clear()
            backend, pid = get_backend(buildlog_dir, project_root=project_root)

        assert isinstance(backend, SQLiteBackend)
        assert "un-migrated" not in caplog.text
