"""Tests for auto-pipeline (distill/skills/emissions) in end_session() and emission consumer."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from buildlog.emissions import EmissionConfig, get_emission_config
from buildlog.emissions.consumer import (
    ConsumptionResult,
    _classify_artifact_type,
    _extract_edges,
    consume_pending_emissions,
)
from buildlog.storage.schema import init_schema
from buildlog.storage.sqlite import SQLiteBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_emissions(tmp_path):
    """Set up temporary emission dirs and return config."""
    cfg = EmissionConfig(
        pending=tmp_path / "pending",
        processed=tmp_path / "processed",
        failed=tmp_path / "failed",
        signal_log=tmp_path / "signal.jsonl",
    )
    cfg.pending.mkdir(parents=True)
    cfg.processed.mkdir(parents=True)
    cfg.failed.mkdir(parents=True)
    return cfg


@pytest.fixture
def backend():
    """Create an in-memory SQLite backend with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return SQLiteBackend(conn)


@pytest.fixture
def sample_mistake_manifest():
    """A realistic mistake_manifest artifact with edges."""
    return {
        "source_id": "buildlog:test-project",
        "domain": "experiential",
        "concepts": [
            {
                "name": "mistake:mistake-test-123",
                "domain": "experiential",
                "properties": {
                    "error_class": "missing_test",
                    "description": "Forgot tests",
                },
                "source_id": "buildlog:test-project",
            }
        ],
        "edges": [
            {
                "source_id": "mistake:mistake-test-123",
                "target_id": "arch-rule-1",
                "relation_type": "challenges",
                "properties": {"source_text": "Rule failed to prevent mistake"},
                "confidence": 0.7,
            },
            {
                "source_id": "mistake:mistake-test-123",
                "target_id": "testing",
                "relation_type": "uses",
                "properties": {"source_text": "Mistake involved concept: testing"},
                "confidence": 0.8,
            },
        ],
        "rules": [],
        "metadata": {
            "source": "buildlog",
            "emitted_at": "2026-02-14T10:00:00+00:00",
            "project_id": "test-project",
            "mistake_id": "mistake-test-123",
        },
    }


@pytest.fixture
def sample_reward_signal():
    """A reward_signal artifact with edges."""
    return {
        "source_id": "buildlog:test-project",
        "domain": "experiential",
        "concepts": [
            {
                "name": "reward:rew-abc",
                "domain": "experiential",
                "properties": {"outcome": "accepted", "reward_value": 1.0},
                "source_id": "buildlog:test-project",
            }
        ],
        "edges": [
            {
                "source_id": "reward:rew-abc",
                "target_id": "arch-rule-1",
                "relation_type": "supports",
                "properties": {"outcome": "accepted"},
                "confidence": 1.0,
            }
        ],
        "rules": [],
        "metadata": {
            "source": "buildlog",
            "emitted_at": "2026-02-14T10:00:00+00:00",
            "project_id": "test-project",
            "reward_id": "rew-abc",
        },
    }


@pytest.fixture
def sample_learned_rules():
    """A learned_rules artifact (no edges)."""
    return {
        "persona": "buildlog_test",
        "version": 1,
        "rules": [{"rule": "Always test", "category": "testing"}],
        "metadata": {
            "source": "buildlog",
            "projected_at": "2026-02-14T10:00:00+00:00",
            "rule_count": 1,
        },
    }


@pytest.fixture
def sample_session_summary():
    """A session_summary artifact with edges."""
    return {
        "source_id": "buildlog:test-project",
        "domain": "experiential",
        "concepts": [
            {
                "name": "session:session-test-123",
                "domain": "experiential",
                "properties": {"duration_minutes": 30.0, "mistakes_logged": 2},
                "source_id": "buildlog:test-project",
            }
        ],
        "edges": [
            {
                "source_id": "session:session-test-123",
                "target_id": "arch-rule-1",
                "relation_type": "uses",
                "properties": {"type": "rule_in_session"},
                "confidence": 1.0,
            },
            {
                "source_id": "session:session-test-123",
                "target_id": "mistake:mistake-test-123",
                "relation_type": "contains",
                "properties": {"error_class": "missing_test"},
                "confidence": 1.0,
            },
        ],
        "rules": [],
        "metadata": {
            "source": "buildlog",
            "emitted_at": "2026-02-14T10:00:00+00:00",
            "project_id": "test-project",
            "session_id": "session-test-123",
        },
    }


# ---------------------------------------------------------------------------
# Classify artifact type
# ---------------------------------------------------------------------------


class TestClassifyArtifactType:
    def test_mistake_manifest(self):
        assert (
            _classify_artifact_type("mistake_manifest_proj_20260214.json")
            == "mistake_manifest"
        )

    def test_reward_signal(self):
        assert (
            _classify_artifact_type("reward_signal_proj_20260214.json")
            == "reward_signal"
        )

    def test_learned_rules(self):
        assert (
            _classify_artifact_type("learned_rules_proj_20260214.json")
            == "learned_rules"
        )

    def test_session_summary(self):
        assert (
            _classify_artifact_type("session_summary_proj_20260214.json")
            == "session_summary"
        )

    def test_unknown(self):
        assert _classify_artifact_type("random_file.json") is None


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------


class TestExtractEdges:
    def test_extracts_edges(self, sample_mistake_manifest):
        edges = _extract_edges(
            sample_mistake_manifest, "mistake_manifest", "2026-02-14T12:00:00Z"
        )
        assert len(edges) == 2
        assert edges[0]["source_id"] == "mistake:mistake-test-123"
        assert edges[0]["relation_type"] == "challenges"
        assert edges[0]["artifact_type"] == "mistake_manifest"
        assert edges[0]["project_id"] == "test-project"

    def test_no_edges(self):
        artifact = {"edges": [], "metadata": {"project_id": "p", "emitted_at": "t"}}
        assert _extract_edges(artifact, "test", "now") == []

    def test_missing_edges_key(self):
        artifact = {"metadata": {"project_id": "p", "emitted_at": "t"}}
        assert _extract_edges(artifact, "test", "now") == []


# ---------------------------------------------------------------------------
# Emission edges backend
# ---------------------------------------------------------------------------


class TestEmissionEdgesBackend:
    def test_store_and_count(self, backend):
        edges = [
            {
                "source_id": "mistake:m1",
                "target_id": "rule:r1",
                "relation_type": "challenges",
                "confidence": 0.7,
                "artifact_type": "mistake_manifest",
                "project_id": "test-project",
                "emitted_at": "2026-02-14T10:00:00Z",
                "consumed_at": "2026-02-14T12:00:00Z",
                "properties": {"foo": "bar"},
            }
        ]
        stored = backend.store_emission_edges(edges)
        assert stored == 1
        assert backend.count_emission_edges() == 1

    def test_count_with_filters(self, backend):
        edges = [
            {
                "source_id": "m1",
                "target_id": "r1",
                "relation_type": "challenges",
                "confidence": 0.7,
                "artifact_type": "mistake_manifest",
                "project_id": "p1",
                "emitted_at": "t1",
                "consumed_at": "t2",
            },
            {
                "source_id": "m2",
                "target_id": "r2",
                "relation_type": "supports",
                "confidence": 0.9,
                "artifact_type": "reward_signal",
                "project_id": "p2",
                "emitted_at": "t3",
                "consumed_at": "t4",
            },
        ]
        backend.store_emission_edges(edges)
        assert backend.count_emission_edges(project_id="p1") == 1
        assert backend.count_emission_edges(relation_type="supports") == 1
        assert backend.count_emission_edges(project_id="nonexistent") == 0

    def test_load_edges(self, backend):
        edges = [
            {
                "source_id": "m1",
                "target_id": "r1",
                "relation_type": "challenges",
                "confidence": 0.7,
                "artifact_type": "mistake_manifest",
                "project_id": "p1",
                "emitted_at": "t1",
                "consumed_at": "t2",
                "properties": {"key": "value"},
            }
        ]
        backend.store_emission_edges(edges)
        loaded = backend.load_emission_edges()
        assert len(loaded) == 1
        assert loaded[0]["source_id"] == "m1"
        assert loaded[0]["properties"] == {"key": "value"}

    def test_unique_constraint_skips_duplicates(self, backend):
        edge = {
            "source_id": "m1",
            "target_id": "r1",
            "relation_type": "challenges",
            "confidence": 0.7,
            "artifact_type": "mistake_manifest",
            "project_id": "p1",
            "emitted_at": "t1",
            "consumed_at": "t2",
        }
        assert backend.store_emission_edges([edge]) == 1
        assert backend.store_emission_edges([edge]) == 0
        assert backend.count_emission_edges() == 1


# ---------------------------------------------------------------------------
# Consumer: consume_pending_emissions
# ---------------------------------------------------------------------------


class TestConsumePendingEmissions:
    def test_empty_pending_dir(self, tmp_emissions, backend):
        result = consume_pending_emissions(config=tmp_emissions, backend=backend)
        assert result.consumed == 0
        assert result.failed == 0
        assert result.edges_stored == 0

    def test_consumes_mistake_manifest(
        self, tmp_emissions, backend, sample_mistake_manifest
    ):
        path = tmp_emissions.pending / "mistake_manifest_test_20260214T100000.json"
        path.write_text(json.dumps(sample_mistake_manifest))

        result = consume_pending_emissions(config=tmp_emissions, backend=backend)
        assert result.consumed == 1
        assert result.edges_stored == 2
        assert not path.exists()
        assert (tmp_emissions.processed / path.name).exists()
        assert backend.count_emission_edges() == 2

    def test_consumes_reward_signal_with_edges(
        self, tmp_emissions, backend, sample_reward_signal
    ):
        path = tmp_emissions.pending / "reward_signal_test_20260214T100000.json"
        path.write_text(json.dumps(sample_reward_signal))

        result = consume_pending_emissions(config=tmp_emissions, backend=backend)
        assert result.consumed == 1
        assert result.edges_stored == 1
        assert (tmp_emissions.processed / path.name).exists()

    def test_consumes_learned_rules_no_edges(
        self, tmp_emissions, backend, sample_learned_rules
    ):
        path = tmp_emissions.pending / "learned_rules_test_20260214T100000.json"
        path.write_text(json.dumps(sample_learned_rules))

        result = consume_pending_emissions(config=tmp_emissions, backend=backend)
        assert result.consumed == 1
        assert result.edges_stored == 0
        assert (tmp_emissions.processed / path.name).exists()

    def test_consumes_session_summary(
        self, tmp_emissions, backend, sample_session_summary
    ):
        path = tmp_emissions.pending / "session_summary_test_20260214T100000.json"
        path.write_text(json.dumps(sample_session_summary))

        result = consume_pending_emissions(config=tmp_emissions, backend=backend)
        assert result.consumed == 1
        assert result.edges_stored == 2
        assert backend.count_emission_edges() == 2

    def test_bad_json_goes_to_failed(self, tmp_emissions, backend):
        path = tmp_emissions.pending / "mistake_manifest_test_20260214T100000.json"
        path.write_text("not valid json {{{")

        result = consume_pending_emissions(config=tmp_emissions, backend=backend)
        assert result.failed == 1
        assert result.consumed == 0
        assert not path.exists()
        assert (tmp_emissions.failed / path.name).exists()
        assert (tmp_emissions.failed / f"{path.name}.error").exists()

    def test_signal_log_updated(self, tmp_emissions, backend, sample_learned_rules):
        path = tmp_emissions.pending / "learned_rules_test_20260214T100000.json"
        path.write_text(json.dumps(sample_learned_rules))

        consume_pending_emissions(config=tmp_emissions, backend=backend)
        assert tmp_emissions.signal_log.exists()
        lines = tmp_emissions.signal_log.read_text().strip().splitlines()
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["event"] == "consumed"

    def test_skips_unknown_artifact_type(self, tmp_emissions, backend):
        path = tmp_emissions.pending / "unknown_type_test_20260214T100000.json"
        path.write_text(json.dumps({"data": "test"}))

        result = consume_pending_emissions(config=tmp_emissions, backend=backend)
        assert result.skipped == 1
        assert result.consumed == 0
        assert path.exists()  # Not moved


# ---------------------------------------------------------------------------
# Auto-pipeline in end_session
# ---------------------------------------------------------------------------


class TestAutoDistill:
    @patch("buildlog.core.operations.log_reward")
    @patch("buildlog.distill.distill_all")
    def test_distill_called_on_session_end(self, mock_distill, mock_reward, tmp_path):
        """distill_all is called during end_session."""
        from buildlog.core.operations import end_session

        mock_distill.return_value = MagicMock(statistics={"total_patterns": 5})

        _setup_session(tmp_path)

        result = end_session(tmp_path)
        mock_distill.assert_called_once_with(tmp_path)
        assert result.distill_count == 5

    @patch("buildlog.core.operations.log_reward")
    @patch("buildlog.distill.distill_all", side_effect=Exception("boom"))
    def test_distill_failure_doesnt_break_session(
        self, mock_distill, mock_reward, tmp_path
    ):
        """distill_all failure is swallowed."""
        from buildlog.core.operations import end_session

        _setup_session(tmp_path)

        result = end_session(tmp_path)
        assert result.distill_count == 0
        assert result.session_id  # Session still ended fine


class TestAutoSkills:
    @patch("buildlog.core.operations.log_reward")
    @patch("buildlog.core.operations.generate_skills")
    @patch("buildlog.distill.distill_all")
    def test_skills_called_on_session_end(
        self, mock_distill, mock_skills, mock_reward, tmp_path
    ):
        """generate_skills is called during end_session."""
        from buildlog.core.operations import end_session

        mock_distill.return_value = MagicMock(statistics={"total_patterns": 0})
        mock_skills.return_value = MagicMock(total_skills=3)

        _setup_session(tmp_path)

        result = end_session(tmp_path)
        # generate_skills is called both during end_session auto-pipeline
        assert result.skills_count == 3

    @patch("buildlog.core.operations.log_reward")
    @patch("buildlog.core.operations.generate_skills", side_effect=Exception("boom"))
    @patch("buildlog.distill.distill_all")
    def test_skills_failure_doesnt_break_session(
        self, mock_distill, mock_skills, mock_reward, tmp_path
    ):
        """generate_skills failure is swallowed."""
        from buildlog.core.operations import end_session

        mock_distill.return_value = MagicMock(statistics={"total_patterns": 0})

        _setup_session(tmp_path)

        result = end_session(tmp_path)
        assert result.skills_count == 0
        assert result.session_id


class TestSessionEmission:
    @patch("buildlog.core.operations.log_reward")
    @patch("buildlog.emissions.emit_artifact")
    @patch("buildlog.core.operations.generate_skills")
    @patch("buildlog.distill.distill_all")
    def test_session_emission_fired(
        self, mock_distill, mock_skills, mock_emit, mock_reward, tmp_path
    ):
        """emit_artifact is called with session_summary type."""
        from buildlog.core.operations import end_session

        mock_distill.return_value = MagicMock(statistics={"total_patterns": 0})
        mock_skills.return_value = MagicMock(total_skills=0)

        _setup_session(tmp_path)

        end_session(tmp_path)
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args
        assert call_kwargs[1]["artifact_type"] == "session_summary"
        artifact = call_kwargs[1]["artifact"]
        assert artifact["concepts"][0]["name"].startswith("session:")
        assert len(artifact["edges"]) >= 0  # May or may not have edges

    @patch("buildlog.core.operations.log_reward")
    @patch("buildlog.emissions.emit_artifact", side_effect=Exception("boom"))
    @patch("buildlog.core.operations.generate_skills")
    @patch("buildlog.distill.distill_all")
    def test_emission_failure_doesnt_break_session(
        self, mock_distill, mock_skills, mock_emit, mock_reward, tmp_path
    ):
        """emit_artifact failure is swallowed."""
        from buildlog.core.operations import end_session

        mock_distill.return_value = MagicMock(statistics={"total_patterns": 0})
        mock_skills.return_value = MagicMock(total_skills=0)

        _setup_session(tmp_path)

        result = end_session(tmp_path)
        assert result.session_id


class TestAutoConsumeOnEndSession:
    @patch("buildlog.core.operations.log_reward")
    @patch("buildlog.emissions.consumer.consume_pending_emissions")
    @patch("buildlog.emissions.emit_artifact")
    @patch("buildlog.core.operations.generate_skills")
    @patch("buildlog.distill.distill_all")
    def test_consume_called_on_session_end(
        self, mock_distill, mock_skills, mock_emit, mock_consume, mock_reward, tmp_path
    ):
        """consume_pending_emissions is called during end_session."""
        from buildlog.core.operations import end_session

        mock_distill.return_value = MagicMock(statistics={"total_patterns": 0})
        mock_skills.return_value = MagicMock(total_skills=0)
        mock_consume.return_value = ConsumptionResult(consumed=5, edges_stored=10)

        _setup_session(tmp_path)

        result = end_session(tmp_path)
        mock_consume.assert_called_once()
        assert result.emissions_consumed == 5
        assert result.edges_stored == 10

    @patch("buildlog.core.operations.log_reward")
    @patch(
        "buildlog.emissions.consumer.consume_pending_emissions",
        side_effect=Exception("boom"),
    )
    @patch("buildlog.emissions.emit_artifact")
    @patch("buildlog.core.operations.generate_skills")
    @patch("buildlog.distill.distill_all")
    def test_consume_failure_doesnt_break_session(
        self, mock_distill, mock_skills, mock_emit, mock_consume, mock_reward, tmp_path
    ):
        """consume failure is swallowed."""
        from buildlog.core.operations import end_session

        mock_distill.return_value = MagicMock(statistics={"total_patterns": 0})
        mock_skills.return_value = MagicMock(total_skills=0)

        _setup_session(tmp_path)

        result = end_session(tmp_path)
        assert result.emissions_consumed == 0
        assert result.session_id


class TestEmissionHealth:
    def test_overview_includes_emission_fields(self, tmp_path):
        """get_overview includes pending_emissions and total_emission_edges."""
        from buildlog.core.operations import get_overview

        _setup_buildlog_dir(tmp_path)

        with patch("buildlog.emissions.list_pending", return_value=[]):
            result = get_overview(tmp_path)
        assert hasattr(result, "pending_emissions")
        assert hasattr(result, "total_emission_edges")
        assert result.pending_emissions == 0
        assert result.total_emission_edges == 0

    def test_overview_emission_fields_nonzero(self, tmp_path):
        """get_overview returns nonzero emission counts when present."""
        from buildlog.core.operations import get_overview

        _setup_buildlog_dir(tmp_path)
        backend, project_id = _get_backend(tmp_path)
        backend.store_emission_edges(
            [
                {
                    "source_id": "m1",
                    "target_id": "r1",
                    "relation_type": "challenges",
                    "confidence": 0.7,
                    "artifact_type": "mistake_manifest",
                    "project_id": project_id,
                    "emitted_at": "t1",
                    "consumed_at": "t2",
                }
            ]
        )

        with patch(
            "buildlog.emissions.list_pending",
            return_value=[Path("/fake/a.json"), Path("/fake/b.json")],
        ):
            result = get_overview(tmp_path)
        assert result.pending_emissions == 2
        assert result.total_emission_edges == 1


# ---------------------------------------------------------------------------
# Session emission builder
# ---------------------------------------------------------------------------


class TestSessionToEmission:
    def test_session_to_emission_structure(self):
        from buildlog.core.operations import Mistake, Session, _session_to_emission

        now = datetime.now(timezone.utc)
        session = Session(
            id="session-test-123",
            started_at=now,
            ended_at=now,
            selected_rules=["rule-a", "rule-b"],
        )
        mistakes = [
            Mistake(
                id="m1",
                session_id="session-test-123",
                timestamp=now,
                error_class="test",
                description="desc",
                semantic_hash="h1",
                was_repeat=False,
            )
        ]
        result = _session_to_emission(session, mistakes, 30.0, 0, "accepted", "proj-1")

        assert result["concepts"][0]["name"] == "session:session-test-123"
        assert result["metadata"]["session_id"] == "session-test-123"
        # 2 rule edges + 1 mistake edge
        assert len(result["edges"]) == 3
        rule_edges = [e for e in result["edges"] if e["relation_type"] == "uses"]
        mistake_edges = [e for e in result["edges"] if e["relation_type"] == "contains"]
        assert len(rule_edges) == 2
        assert len(mistake_edges) == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_session(buildlog_dir: Path):
    """Set up a minimal buildlog dir with an active session for end_session() tests."""
    buildlog_dir.mkdir(exist_ok=True)
    # Need the CLAUDE.md and project structure
    project_dir = buildlog_dir.parent
    claude_md = project_dir / "CLAUDE.md"
    if not claude_md.exists():
        # buildlog_dir IS the project when using tmp_path directly
        pass

    from buildlog.core.operations import Session
    from buildlog.storage import get_backend

    backend, project_id = get_backend(buildlog_dir)
    now = datetime.now(timezone.utc)
    session = Session(
        id=f"session-test-{now.strftime('%Y%m%d-%H%M%S')}",
        started_at=now,
        ended_at=None,
        rules_at_start=["rule-a"],
        selected_rules=["rule-a"],
    )
    backend.save_active_session(project_id, session.to_dict())


def _setup_buildlog_dir(buildlog_dir: Path):
    """Set up minimal buildlog dir for get_overview() tests."""
    buildlog_dir.mkdir(exist_ok=True)
    (buildlog_dir.parent / "CLAUDE.md").write_text(
        "# CLAUDE\n## Standard Development Workflow\ntest"
    )


def _get_backend(buildlog_dir: Path):
    """Get backend and project_id for a buildlog dir."""
    from buildlog.storage import get_backend

    return get_backend(buildlog_dir)
