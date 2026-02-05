"""Tests for JsonlExporter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from buildlog.storage.exporters import JsonlExporter
from buildlog.storage.schema import init_schema
from buildlog.storage.sqlite import SQLiteBackend


@pytest.fixture
def backend():
    """In-memory SQLiteBackend with sample data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    be = SQLiteBackend(conn)
    be.ensure_project("proj-1", "Project One", "/tmp/p1")
    be.ensure_project("proj-2", "Project Two", "/tmp/p2")

    # Seed data
    be.append_event(
        "proj-1",
        "rewards",
        {
            "id": "r1",
            "timestamp": "2026-01-01",
            "outcome": "accepted",
            "reward_value": 1.0,
        },
    )
    be.append_event(
        "proj-1",
        "rewards",
        {
            "id": "r2",
            "timestamp": "2026-01-02",
            "outcome": "rejected",
            "reward_value": 0.0,
        },
    )
    be.append_event(
        "proj-2",
        "rewards",
        {
            "id": "r3",
            "timestamp": "2026-01-03",
            "outcome": "accepted",
            "reward_value": 1.0,
        },
    )
    be.append_event(
        "proj-1",
        "sessions",
        {
            "id": "s1",
            "started_at": "2026-01-01T00:00:00",
            "ended_at": "2026-01-01T01:00:00",
        },
    )
    be.append_event(
        "proj-1",
        "mistakes",
        {
            "id": "m1",
            "session_id": "s1",
            "timestamp": "2026-01-01T00:30:00",
            "error_class": "missing_test",
            "description": "Forgot test",
            "semantic_hash": "abc",
            "was_repeat": False,
        },
    )
    return be


@pytest.fixture
def exporter():
    return JsonlExporter()


class TestExportToFile:
    def test_export_all_tables(
        self, backend: SQLiteBackend, exporter: JsonlExporter, tmp_path: Path
    ):
        out = tmp_path / "export"
        summary = exporter.export(backend, project_id="proj-1", output_path=out)

        assert "Exported" in summary
        assert (out / "rewards.jsonl").exists()
        assert (out / "sessions.jsonl").exists()
        assert (out / "mistakes.jsonl").exists()

        rewards = [
            json.loads(line)
            for line in (out / "rewards.jsonl").read_text().splitlines()
        ]
        assert len(rewards) == 2
        assert rewards[0]["id"] == "r1"

    def test_export_subset_tables(
        self, backend: SQLiteBackend, exporter: JsonlExporter, tmp_path: Path
    ):
        out = tmp_path / "export"
        summary = exporter.export(
            backend, project_id="proj-1", output_path=out, tables=["rewards"]
        )

        assert "rewards=2" in summary
        assert (out / "rewards.jsonl").exists()
        assert not (out / "sessions.jsonl").exists()

    def test_export_global(
        self, backend: SQLiteBackend, exporter: JsonlExporter, tmp_path: Path
    ):
        out = tmp_path / "export"
        exporter.export(backend, project_id=None, output_path=out, tables=["rewards"])

        rewards = [
            json.loads(line)
            for line in (out / "rewards.jsonl").read_text().splitlines()
        ]
        assert len(rewards) == 3  # All projects

    def test_export_empty_project(
        self, backend: SQLiteBackend, exporter: JsonlExporter, tmp_path: Path
    ):
        out = tmp_path / "export"
        exporter.export(
            backend, project_id="proj-2", output_path=out, tables=["sessions"]
        )

        sessions = (out / "sessions.jsonl").read_text()
        assert sessions == ""  # No sessions for proj-2


class TestExportToString:
    def test_returns_string(self, backend: SQLiteBackend, exporter: JsonlExporter):
        result = exporter.export(backend, project_id="proj-1")
        assert "--- rewards ---" in result
        assert "--- sessions ---" in result
        assert "--- mistakes ---" in result
        lines = result.splitlines()
        # Should contain section headers + data lines
        assert len(lines) >= 6  # 3 headers + at least 3 data lines

    def test_string_contains_json(
        self, backend: SQLiteBackend, exporter: JsonlExporter
    ):
        result = exporter.export(backend, project_id="proj-1")
        for line in result.splitlines():
            if not line.startswith("---"):
                parsed = json.loads(line)
                assert "id" in parsed


class TestExportValidation:
    def test_unknown_table(self, backend: SQLiteBackend, exporter: JsonlExporter):
        with pytest.raises(ValueError, match="Unknown table"):
            exporter.export(backend, tables=["nonexistent"])

    def test_creates_output_dir(
        self, backend: SQLiteBackend, exporter: JsonlExporter, tmp_path: Path
    ):
        out = tmp_path / "nested" / "deep" / "export"
        exporter.export(backend, project_id="proj-1", output_path=out)
        assert out.exists()


class TestRoundTrip:
    def test_export_import_roundtrip(
        self, backend: SQLiteBackend, exporter: JsonlExporter, tmp_path: Path
    ):
        """Export from SQLite → JSONL files, verify data matches."""
        out = tmp_path / "export"
        exporter.export(backend, project_id="proj-1", output_path=out)

        # Read back and compare
        exported_rewards = [
            json.loads(line)
            for line in (out / "rewards.jsonl").read_text().splitlines()
        ]
        original_rewards = backend.load_events("proj-1", "rewards")

        assert len(exported_rewards) == len(original_rewards)
        for exp, orig in zip(exported_rewards, original_rewards):
            assert exp["id"] == orig["id"]
            assert exp["outcome"] == orig["outcome"]
