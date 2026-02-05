"""Tests for JsonlExporter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from buildlog.storage.exporters import _EXPORTABLE_TABLES, JsonlExporter
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


@pytest.fixture
def backend_with_bandit():
    """Backend with bandit state and learnings data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    be = SQLiteBackend(conn)
    be.ensure_project("proj-1", "Project One", "/tmp/p1")

    # Add bandit state
    be.append_bandit_update(
        "proj-1",
        "default",
        "rule-1",
        {
            "alpha": 5.0,
            "beta": 2.0,
            "is_seed": True,
            "updated_at": "2026-01-01T00:00:00",
        },
    )
    be.append_bandit_update(
        "proj-1",
        "default",
        "rule-2",
        {
            "alpha": 1.0,
            "beta": 3.0,
            "is_seed": False,
            "updated_at": "2026-01-02T00:00:00",
        },
    )

    # Add learnings
    be.save_learnings(
        "proj-1",
        {
            "learnings": {
                "always-test": {
                    "rule": "Always write tests",
                    "category": "testing",
                    "severity": "high",
                    "source": "review",
                    "first_seen": "2026-01-01",
                    "last_reinforced": "2026-01-02",
                    "reinforcement_count": 3,
                    "contradiction_count": 0,
                    "functional_principle": "Test coverage",
                },
                "check-types": {
                    "rule": "Check types early",
                    "category": "quality",
                    "severity": "medium",
                    "source": "review",
                    "first_seen": "2026-01-01",
                    "last_reinforced": "2026-01-01",
                    "reinforcement_count": 1,
                    "contradiction_count": 0,
                    "functional_principle": "Type safety",
                },
            },
            "review_history": [],
        },
    )

    # Add skill decisions
    be.save_id_set("proj-1", "promoted", {"skill-a", "skill-b"})
    be.save_id_set("proj-1", "rejected", {"skill-c"})

    return be


class TestExportBanditState:
    def test_export_bandit_state(
        self,
        backend_with_bandit: SQLiteBackend,
        exporter: JsonlExporter,
        tmp_path: Path,
    ):
        """Should export bandit state as flat JSONL rows."""
        out = tmp_path / "export"
        exporter.export(
            backend_with_bandit,
            project_id="proj-1",
            output_path=out,
            tables=["bandit_state"],
            include_manifest=False,
            include_rules_join=False,
        )

        rows = [
            json.loads(line)
            for line in (out / "bandit_state.jsonl").read_text().splitlines()
        ]
        assert len(rows) == 2

        by_rule = {r["rule_id"]: r for r in rows}
        assert by_rule["rule-1"]["alpha"] == 5.0
        assert by_rule["rule-1"]["beta"] == 2.0
        assert by_rule["rule-1"]["is_seed"] is True
        assert by_rule["rule-1"]["context"] == "default"
        assert "mean" in by_rule["rule-1"]  # mean = 5/(5+2) ≈ 0.7143

        assert by_rule["rule-2"]["is_seed"] is False


class TestExportLearnings:
    def test_export_learnings(
        self,
        backend_with_bandit: SQLiteBackend,
        exporter: JsonlExporter,
        tmp_path: Path,
    ):
        """Should export learnings as JSONL rows."""
        out = tmp_path / "export"
        exporter.export(
            backend_with_bandit,
            project_id="proj-1",
            output_path=out,
            tables=["learnings"],
            include_manifest=False,
            include_rules_join=False,
        )

        rows = [
            json.loads(line)
            for line in (out / "learnings.jsonl").read_text().splitlines()
        ]
        assert len(rows) == 2
        keys = {r["key"] for r in rows}
        assert "always-test" in keys
        assert "check-types" in keys


class TestExportSkillDecisions:
    def test_export_skill_decisions(
        self,
        backend_with_bandit: SQLiteBackend,
        exporter: JsonlExporter,
        tmp_path: Path,
    ):
        """Should export promoted/rejected decisions."""
        out = tmp_path / "export"
        exporter.export(
            backend_with_bandit,
            project_id="proj-1",
            output_path=out,
            tables=["skill_decisions"],
            include_manifest=False,
            include_rules_join=False,
        )

        rows = [
            json.loads(line)
            for line in (out / "skill_decisions.jsonl").read_text().splitlines()
        ]
        assert len(rows) == 3

        promoted = [r for r in rows if r["decision"] == "promoted"]
        rejected = [r for r in rows if r["decision"] == "rejected"]
        assert len(promoted) == 2
        assert len(rejected) == 1
        assert rejected[0]["skill_id"] == "skill-c"


class TestManifest:
    def test_manifest_generated(
        self, backend: SQLiteBackend, exporter: JsonlExporter, tmp_path: Path
    ):
        """Should generate manifest.json with table record counts."""
        out = tmp_path / "export"
        exporter.export(
            backend,
            project_id="proj-1",
            output_path=out,
            tables=["rewards", "sessions"],
            include_rules_join=False,
        )

        manifest_path = out / "manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert "exported_at" in manifest
        assert manifest["project_id"] == "proj-1"
        assert manifest["tables"]["rewards"] == 2
        assert manifest["tables"]["sessions"] == 1

    def test_manifest_not_generated_when_disabled(
        self, backend: SQLiteBackend, exporter: JsonlExporter, tmp_path: Path
    ):
        """Should skip manifest when include_manifest=False."""
        out = tmp_path / "export"
        exporter.export(
            backend,
            project_id="proj-1",
            output_path=out,
            tables=["rewards"],
            include_manifest=False,
            include_rules_join=False,
        )

        assert not (out / "manifest.json").exists()


class TestRulesJoin:
    def test_rules_join_with_provenance(self, exporter: JsonlExporter, tmp_path: Path):
        """Should generate rules.jsonl with provenance fields from seeds."""
        # Create a seed file with provenance
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        seed_data = {
            "persona": "test_persona",
            "version": 1,
            "rules": [
                {
                    "rule": "Always validate input",
                    "category": "security",
                    "context": "User input handling",
                    "antipattern": "Trusting raw input",
                    "rationale": "Prevents injection",
                    "provenance": {
                        "source_id": "q-001",
                        "source_domain": "qortex",
                        "graph_version": "2",
                        "confidence": 0.9,
                    },
                }
            ],
        }
        (seeds_dir / "test_persona.yaml").write_text(yaml.dump(seed_data))

        # Create a minimal backend (no data needed for rules join)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        be = SQLiteBackend(conn)
        be.ensure_project("proj-1", "Project One", "/tmp/p1")

        out = tmp_path / "export"
        exporter.export(
            be,
            project_id="proj-1",
            output_path=out,
            tables=["rewards"],
            include_manifest=False,
            include_rules_join=True,
            seeds_dir=seeds_dir,
        )

        rules_path = out / "rules.jsonl"
        assert rules_path.exists()

        rows = [json.loads(line) for line in rules_path.read_text().splitlines()]
        assert len(rows) == 1
        row = rows[0]
        assert row["buildlog_id"]  # Should have a generated ID
        assert row["rule"] == "Always validate input"
        assert row["persona"] == "test_persona"
        assert row["source_id"] == "q-001"
        assert row["source_domain"] == "qortex"
        assert row["graph_version"] == "2"
        assert row["source_confidence"] == 0.9

    def test_rules_join_without_provenance(
        self, exporter: JsonlExporter, tmp_path: Path
    ):
        """Should generate rules.jsonl without provenance fields when absent."""
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        seed_data = {
            "persona": "plain",
            "version": 1,
            "rules": [
                {
                    "rule": "Write tests",
                    "category": "testing",
                    "context": "After code changes",
                    "antipattern": "No tests",
                    "rationale": "Catches regressions",
                }
            ],
        }
        (seeds_dir / "plain.yaml").write_text(yaml.dump(seed_data))

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        be = SQLiteBackend(conn)
        be.ensure_project("proj-1", "Project One", "/tmp/p1")

        out = tmp_path / "export"
        exporter.export(
            be,
            project_id="proj-1",
            output_path=out,
            tables=["rewards"],
            include_manifest=False,
            include_rules_join=True,
            seeds_dir=seeds_dir,
        )

        rows = [
            json.loads(line) for line in (out / "rules.jsonl").read_text().splitlines()
        ]
        assert len(rows) == 1
        row = rows[0]
        assert row["rule"] == "Write tests"
        assert row["persona"] == "plain"
        # No provenance fields
        assert "source_id" not in row
        assert "graph_version" not in row
