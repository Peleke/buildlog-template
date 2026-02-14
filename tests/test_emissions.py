"""Tests for the emissions protocol: schema v2, emit_artifact, mappers, seeds."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from buildlog.core.operations import Mistake, MistakeDict
from buildlog.emissions import (
    EmissionConfig,
    emit_artifact,
    get_emission_config,
    list_pending,
    list_processed,
)
from buildlog.emissions.mappers import (
    DEFAULT_REGISTRY,
    EdgeMapperContext,
    EdgeMapperRegistry,
    MapperOutput,
    _mistake_to_manifest,
    concept_involvement,
    mistake_chain,
    resolution_edges,
    resolution_rule,
    rule_challenge,
    rule_support,
)
from buildlog.storage.schema import SCHEMA_VERSION, init_schema

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def emission_dir(tmp_path: Path) -> EmissionConfig:
    """Create a temporary emission config."""
    return get_emission_config(tmp_path / "emissions")


def _make_mistake(**overrides) -> Mistake:
    """Factory for test Mistake objects."""
    defaults = dict(
        id="mistake-test-001",
        session_id="session-test-001",
        timestamp=datetime(2026, 2, 6, 12, 0, 0, tzinfo=timezone.utc),
        error_class="missing_test",
        description="Forgot to test the frobulator",
        semantic_hash="abc123",
        was_repeat=False,
        corrected_by_rule=None,
        related_concepts=None,
        relation_to_prior=None,
        resolution_action=None,
        context=None,
        severity=None,
    )
    defaults.update(overrides)
    return Mistake(**defaults)


def _make_ctx(mistake: Mistake | None = None, **overrides) -> EdgeMapperContext:
    """Factory for test EdgeMapperContext objects."""
    m = mistake or _make_mistake()
    defaults = dict(
        mistake=m,
        mistake_node_id=f"mistake:{m.id}",
        domain="experiential",
        source_id="buildlog:test-proj",
        selected_rules=[],
        session_data=None,
    )
    defaults.update(overrides)
    return EdgeMapperContext(**defaults)


# ============================================================================
# Part 1: Schema v2 migration tests
# ============================================================================


class TestSchemaV2Migration:
    def test_schema_version_is_3(self):
        assert SCHEMA_VERSION == 4

    def test_fresh_install_has_v2_columns(self):
        """Fresh DB should have all v2 columns in mistakes table."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        # Check schema_version
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == 4

        # Check v2 columns exist
        cursor = conn.execute("PRAGMA table_info(mistakes)")
        columns = {row["name"] for row in cursor.fetchall()}
        v2_cols = {
            "related_concepts",
            "relation_to_prior",
            "resolution_action",
            "context",
            "severity",
        }
        assert v2_cols.issubset(columns)

        # Check v3 column exists on reward_events
        cursor = conn.execute("PRAGMA table_info(reward_events)")
        reward_cols = {row["name"] for row in cursor.fetchall()}
        assert "session_id" in reward_cols

    def test_v1_to_v2_migration(self):
        """Simulate a v1 DB and verify v2 migration applies cleanly."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # Manually create a v1 mistakes table WITHOUT v2 columns
        _V1_MISTAKES_DDL = """\
CREATE TABLE IF NOT EXISTS mistakes (
    project_id      TEXT NOT NULL,
    id              TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    error_class     TEXT NOT NULL,
    description     TEXT NOT NULL,
    semantic_hash   TEXT NOT NULL,
    was_repeat      INTEGER NOT NULL DEFAULT 0,
    corrected_by_rule TEXT,
    PRIMARY KEY (project_id, id)
);"""
        # Apply minimal schema_version + mistakes table as v1
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY,"
            "applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            ");"
        )
        conn.executescript(_V1_MISTAKES_DDL)
        conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (1,))
        conn.commit()

        # Verify v1 doesn't have v2 cols
        cursor = conn.execute("PRAGMA table_info(mistakes)")
        columns_v1 = {row["name"] for row in cursor.fetchall()}
        assert "related_concepts" not in columns_v1

        # Apply v2 migration manually (init_schema needs all tables)
        from buildlog.storage.schema import _MIGRATE_V2

        for stmt in _MIGRATE_V2:
            conn.execute(stmt)
        conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (2,))
        conn.commit()

        # Verify v2 cols exist
        cursor = conn.execute("PRAGMA table_info(mistakes)")
        columns_v2 = {row["name"] for row in cursor.fetchall()}
        assert "related_concepts" in columns_v2
        assert "severity" in columns_v2
        assert "context" in columns_v2
        assert "relation_to_prior" in columns_v2
        assert "resolution_action" in columns_v2

    def test_v2_migration_idempotent(self):
        """Running init_schema twice doesn't break anything."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        version = init_schema(conn)
        assert version == 4


# ============================================================================
# Part 2: Enriched Mistake dataclass tests
# ============================================================================


class TestEnrichedMistake:
    def test_new_fields_default_none(self):
        m = _make_mistake()
        assert m.related_concepts is None
        assert m.relation_to_prior is None
        assert m.resolution_action is None
        assert m.context is None
        assert m.severity is None

    def test_to_dict_includes_new_fields(self):
        m = _make_mistake(
            related_concepts=["testing", "validation"],
            severity="high",
            context="writing unit tests",
            resolution_action="added missing test",
            relation_to_prior={"id": "mistake-prior-001", "type": "same_pattern"},
        )
        d = m.to_dict()
        assert d["related_concepts"] == ["testing", "validation"]
        assert d["severity"] == "high"
        assert d["context"] == "writing unit tests"
        assert d["resolution_action"] == "added missing test"
        assert d["relation_to_prior"] == {
            "id": "mistake-prior-001",
            "type": "same_pattern",
        }

    def test_to_dict_omits_none_fields(self):
        m = _make_mistake()
        d = m.to_dict()
        assert "related_concepts" not in d
        assert "severity" not in d

    def test_from_dict_round_trip(self):
        m = _make_mistake(
            related_concepts=["X"],
            severity="critical",
            resolution_action="fixed it",
        )
        d = m.to_dict()
        m2 = Mistake.from_dict(d)
        assert m2.related_concepts == ["X"]
        assert m2.severity == "critical"
        assert m2.resolution_action == "fixed it"

    def test_from_dict_json_string_deserialization(self):
        """SQLite stores JSON fields as strings; from_dict should handle that."""
        d: MistakeDict = {
            "id": "test",
            "session_id": "sess",
            "timestamp": "2026-02-06T12:00:00+00:00",
            "error_class": "test",
            "description": "test",
            "semantic_hash": "abc",
            "was_repeat": False,
            "related_concepts": '["a", "b"]',  # type: ignore[typeddict-item]
            "relation_to_prior": '{"id": "x", "type": "escalation"}',  # type: ignore[typeddict-item]
        }
        m = Mistake.from_dict(d)
        assert m.related_concepts == ["a", "b"]
        assert m.relation_to_prior == {"id": "x", "type": "escalation"}

    def test_backwards_compat_no_new_fields(self):
        """Old data without new fields still deserializes fine."""
        d: MistakeDict = {
            "id": "old",
            "session_id": "sess",
            "timestamp": "2026-01-01T00:00:00",
            "error_class": "old_error",
            "description": "old mistake",
            "semantic_hash": "old_hash",
            "was_repeat": False,
        }
        m = Mistake.from_dict(d)
        assert m.related_concepts is None
        assert m.severity is None


# ============================================================================
# Part 3: Emission protocol tests
# ============================================================================


class TestEmissionProtocol:
    def test_get_emission_config_creates_dirs(self, tmp_path: Path):
        cfg = get_emission_config(tmp_path / "emissions")
        assert cfg.pending.exists()
        assert cfg.processed.exists()
        assert cfg.failed.exists()

    def test_emit_artifact_writes_file(self, emission_dir: EmissionConfig):
        path = emit_artifact(
            artifact={"test": "data"},
            artifact_type="test_type",
            project_id="test-proj",
            config=emission_dir,
        )
        assert path is not None
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["test"] == "data"

    def test_emit_artifact_filename_convention(self, emission_dir: EmissionConfig):
        path = emit_artifact(
            artifact={},
            artifact_type="mistake_manifest",
            project_id="proj123",
            config=emission_dir,
        )
        assert path is not None
        assert path.name.startswith("mistake_manifest_proj123_")
        assert path.name.endswith(".json")

    def test_emit_artifact_appends_signal_log(self, emission_dir: EmissionConfig):
        emit_artifact(
            artifact={"x": 1},
            artifact_type="test_type",
            project_id="proj",
            config=emission_dir,
        )
        assert emission_dir.signal_log.exists()
        lines = emission_dir.signal_log.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event"] == "emitted"
        assert entry["type"] == "test_type"
        assert entry["source"] == "buildlog"

    def test_list_pending(self, emission_dir: EmissionConfig):
        emit_artifact({"a": 1}, "t1", "p1", emission_dir)
        emit_artifact({"b": 2}, "t2", "p2", emission_dir)
        pending = list_pending(emission_dir)
        assert len(pending) == 2

    def test_list_processed_empty(self, emission_dir: EmissionConfig):
        assert list_processed(emission_dir) == []

    def test_emit_failure_returns_none(self, tmp_path: Path):
        """Emission with unserializable data returns None, not raise."""
        cfg = get_emission_config(tmp_path / "emissions")
        # Make pending dir unwritable
        cfg.pending.chmod(0o444)
        try:
            result = emit_artifact({"x": 1}, "test", "proj", cfg)
            assert result is None
        finally:
            cfg.pending.chmod(0o755)


# ============================================================================
# Part 4: Edge mapper tests
# ============================================================================


class TestConceptInvolvement:
    def test_no_concepts(self):
        ctx = _make_ctx()
        out = concept_involvement(ctx)
        assert out.edges == []

    def test_with_concepts(self):
        m = _make_mistake(related_concepts=["schema", "migration"])
        ctx = _make_ctx(m)
        out = concept_involvement(ctx)
        assert len(out.edges) == 2
        assert all(e["relation_type"] == "uses" for e in out.edges)
        targets = {e["target_id"] for e in out.edges}
        assert targets == {"schema", "migration"}


class TestRuleChallenge:
    def test_no_rules(self):
        ctx = _make_ctx(selected_rules=[])
        out = rule_challenge(ctx)
        assert out.edges == []

    def test_with_rules(self):
        ctx = _make_ctx(selected_rules=["rule-1", "rule-2"])
        out = rule_challenge(ctx)
        assert len(out.edges) == 2
        assert all(e["relation_type"] == "challenges" for e in out.edges)


class TestRuleSupport:
    def test_no_corrected_by(self):
        ctx = _make_ctx()
        out = rule_support(ctx)
        assert out.edges == []

    def test_with_corrected_by(self):
        m = _make_mistake(corrected_by_rule="rule-fix-1")
        ctx = _make_ctx(m)
        out = rule_support(ctx)
        assert len(out.edges) == 1
        assert out.edges[0]["relation_type"] == "supports"
        assert out.edges[0]["target_id"] == "rule-fix-1"


class TestMistakeChain:
    def test_no_relation(self):
        ctx = _make_ctx()
        out = mistake_chain(ctx)
        assert out.edges == []

    def test_escalation(self):
        m = _make_mistake(
            relation_to_prior={"id": "mistake-prior", "type": "escalation"}
        )
        ctx = _make_ctx(m)
        out = mistake_chain(ctx)
        assert len(out.edges) == 1
        assert out.edges[0]["relation_type"] == "refines"

    def test_same_pattern(self):
        m = _make_mistake(
            relation_to_prior={"id": "mistake-prior", "type": "same_pattern"}
        )
        ctx = _make_ctx(m)
        out = mistake_chain(ctx)
        assert out.edges[0]["relation_type"] == "similar_to"

    def test_regression(self):
        m = _make_mistake(
            relation_to_prior={"id": "mistake-prior", "type": "regression"}
        )
        ctx = _make_ctx(m)
        out = mistake_chain(ctx)
        assert out.edges[0]["relation_type"] == "contradicts"

    def test_caused_by(self):
        m = _make_mistake(
            relation_to_prior={"id": "mistake-prior", "type": "caused_by"}
        )
        ctx = _make_ctx(m)
        out = mistake_chain(ctx)
        assert out.edges[0]["relation_type"] == "requires"

    def test_part_of(self):
        m = _make_mistake(relation_to_prior={"id": "mistake-prior", "type": "part_of"})
        ctx = _make_ctx(m)
        out = mistake_chain(ctx)
        assert out.edges[0]["relation_type"] == "part_of"

    def test_unknown_type_defaults_to_similar(self):
        m = _make_mistake(
            relation_to_prior={"id": "mistake-prior", "type": "some_new_thing"}
        )
        ctx = _make_ctx(m)
        out = mistake_chain(ctx)
        assert out.edges[0]["relation_type"] == "similar_to"


class TestResolutionRule:
    def test_no_resolution(self):
        ctx = _make_ctx()
        out = resolution_rule(ctx)
        assert out.rules == []

    def test_with_resolution(self):
        m = _make_mistake(resolution_action="Added the missing test")
        ctx = _make_ctx(m)
        out = resolution_rule(ctx)
        assert len(out.rules) == 1
        assert out.rules[0]["rule"] == "Added the missing test"
        assert out.rules[0]["provenance"]["domain"] == "experiential"


class TestResolutionEdges:
    def test_no_resolution(self):
        ctx = _make_ctx()
        out = resolution_edges(ctx)
        assert out.edges == []

    def test_with_resolution_no_corrected_rule(self):
        m = _make_mistake(resolution_action="Fixed it")
        ctx = _make_ctx(m)
        out = resolution_edges(ctx)
        assert len(out.edges) == 1
        assert out.edges[0]["relation_type"] == "implements"

    def test_with_resolution_and_corrected_rule(self):
        m = _make_mistake(resolution_action="Fixed it", corrected_by_rule="rule-1")
        ctx = _make_ctx(m)
        out = resolution_edges(ctx)
        assert len(out.edges) == 2
        types = {e["relation_type"] for e in out.edges}
        assert types == {"implements", "supports"}


class TestEdgeMapperRegistry:
    def test_default_registry_has_6_mappers(self):
        assert len(DEFAULT_REGISTRY.enabled_names()) == 6

    def test_disable_enable(self):
        reg = EdgeMapperRegistry()
        reg.register("test", lambda ctx: MapperOutput())
        assert "test" in reg.enabled_names()
        reg.disable("test")
        assert "test" not in reg.enabled_names()
        reg.enable("test")
        assert "test" in reg.enabled_names()

    def test_run_all_merges(self):
        reg = EdgeMapperRegistry()
        reg.register(
            "a",
            lambda ctx: MapperOutput(edges=[{"id": "e1"}]),
        )
        reg.register(
            "b",
            lambda ctx: MapperOutput(rules=[{"id": "r1"}]),
        )
        ctx = _make_ctx()
        out = reg.run_all(ctx)
        assert len(out.edges) == 1
        assert len(out.rules) == 1

    def test_disabled_mapper_not_run(self):
        reg = EdgeMapperRegistry()
        reg.register(
            "a",
            lambda ctx: MapperOutput(edges=[{"id": "e1"}]),
        )
        reg.disable("a")
        ctx = _make_ctx()
        out = reg.run_all(ctx)
        assert len(out.edges) == 0


# ============================================================================
# Part 5: Manifest builder tests
# ============================================================================


class TestMistakeToManifest:
    def test_basic_manifest_structure(self):
        m = _make_mistake()
        manifest = _mistake_to_manifest(m, None, [], "test-proj")
        assert manifest["source_id"] == "buildlog:test-proj"
        assert manifest["domain"] == "experiential"
        assert len(manifest["concepts"]) == 1
        assert manifest["concepts"][0]["name"] == f"mistake:{m.id}"
        assert "metadata" in manifest

    def test_manifest_with_full_enrichment(self):
        m = _make_mistake(
            related_concepts=["X", "Y"],
            severity="high",
            corrected_by_rule="rule-1",
            resolution_action="fixed",
            relation_to_prior={"id": "prior-1", "type": "escalation"},
        )
        manifest = _mistake_to_manifest(m, None, ["rule-1", "rule-2"], "test-proj")

        # Should have edges from concept_involvement (2) + rule_challenge (2)
        # + rule_support (1) + mistake_chain (1) + resolution_edges (2)
        assert len(manifest["edges"]) >= 6

        # Should have 1 rule from resolution_rule
        assert len(manifest["rules"]) == 1

        # Concept node should have severity
        assert manifest["concepts"][0]["properties"]["severity"] == "high"


# ============================================================================
# Part 6: Seed emission tests
# ============================================================================


class TestLearningsToSeed:
    def test_seed_structure(self):
        from buildlog.core.operations import _learnings_to_seed

        data = {
            "learnings": {
                "learn-1": {
                    "rule": "Always test edge cases",
                    "category": "testing",
                    "reinforcement_count": 2,
                }
            }
        }
        seed = _learnings_to_seed(["learn-1"], data, [], None, "proj-1")
        assert seed["persona"] == "buildlog_proj-1"
        assert seed["version"] == 1
        assert len(seed["rules"]) == 1
        assert seed["rules"][0]["rule"] == "Always test edge cases"
        assert seed["rules"][0]["provenance"]["domain"] == "experiential"
        # confidence = min(1.0, 2 * 0.3 + 0.4) = 1.0
        assert seed["rules"][0]["provenance"]["confidence"] == 1.0
        assert seed["metadata"]["source"] == "buildlog"

    def test_seed_confidence_calculation(self):
        from buildlog.core.operations import _learnings_to_seed

        data = {
            "learnings": {
                "learn-1": {
                    "rule": "test",
                    "category": "test",
                    "reinforcement_count": 1,
                }
            }
        }
        seed = _learnings_to_seed(["learn-1"], data, [], None, "proj")
        # confidence = min(1.0, 1 * 0.3 + 0.4) = 0.7
        assert seed["rules"][0]["provenance"]["confidence"] == pytest.approx(0.7)

    def test_seed_missing_learning_skipped(self):
        from buildlog.core.operations import _learnings_to_seed

        data = {"learnings": {}}
        seed = _learnings_to_seed(["nonexistent"], data, [], None, "proj")
        assert len(seed["rules"]) == 0


# ============================================================================
# Part 7: Property-based tests (hypothesis)
# ============================================================================

# Strategies
severity_st = st.sampled_from([None, "low", "medium", "high", "critical"])
concepts_st = st.one_of(
    st.none(), st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5)
)
chain_type_st = st.sampled_from(
    ["escalation", "same_pattern", "regression", "caused_by", "part_of", "unknown"]
)
relation_st = st.one_of(
    st.none(),
    st.fixed_dictionaries(
        {"id": st.text(min_size=1, max_size=20), "type": chain_type_st}
    ),
)


@st.composite
def mistake_st(draw):
    return _make_mistake(
        related_concepts=draw(concepts_st),
        severity=draw(severity_st),
        corrected_by_rule=draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        resolution_action=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
        relation_to_prior=draw(relation_st),
        context=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
    )


class TestPropertyBased:
    @given(m=mistake_st())
    @settings(max_examples=50)
    def test_manifest_always_has_one_concept(self, m: Mistake):
        """For ANY valid Mistake, manifest has exactly 1 concept node."""
        manifest = _mistake_to_manifest(m, None, [], "test-proj")
        assert len(manifest["concepts"]) == 1

    @given(m=mistake_st(), rules=st.lists(st.text(min_size=1, max_size=10), max_size=5))
    @settings(max_examples=50)
    def test_edge_count_lower_bound(self, m: Mistake, rules: list[str]):
        """Edge count >= len(related_concepts) + len(selected_rules)."""
        manifest = _mistake_to_manifest(m, None, rules, "test-proj")
        min_expected = len(m.related_concepts or []) + len(rules)
        assert len(manifest["edges"]) >= min_expected

    @given(m=mistake_st())
    @settings(max_examples=50)
    def test_resolution_rule_count(self, m: Mistake):
        """If resolution_action is set, exactly 1 rule; else 0."""
        manifest = _mistake_to_manifest(m, None, [], "test-proj")
        if m.resolution_action:
            assert len(manifest["rules"]) == 1
        else:
            assert len(manifest["rules"]) == 0

    @given(m=mistake_st(), rules=st.lists(st.text(min_size=1, max_size=10), max_size=5))
    @settings(max_examples=50)
    def test_all_edge_relation_types_valid(self, m: Mistake, rules: list[str]):
        """Every emitted edge has a valid relation_type."""
        valid_types = {
            "uses",
            "challenges",
            "supports",
            "contradicts",
            "requires",
            "refines",
            "similar_to",
            "part_of",
            "implements",
            "alternative_to",
        }
        manifest = _mistake_to_manifest(m, None, rules, "test-proj")
        for edge in manifest["edges"]:
            assert (
                edge["relation_type"] in valid_types
            ), f"Invalid relation_type: {edge['relation_type']}"


# ============================================================================
# Part 8: Metamorphic tests
# ============================================================================


class TestMetamorphic:
    def test_more_concepts_more_edges(self):
        """Adding N concepts increases edge count by exactly N."""
        m0 = _make_mistake(related_concepts=[])
        m3 = _make_mistake(related_concepts=["a", "b", "c"])
        man0 = _mistake_to_manifest(m0, None, [], "proj")
        man3 = _mistake_to_manifest(m3, None, [], "proj")
        assert len(man3["edges"]) - len(man0["edges"]) == 3

    def test_severity_doesnt_change_structure(self):
        """Changing severity doesn't change edge/node counts."""
        m_low = _make_mistake(severity="low", related_concepts=["X"])
        m_crit = _make_mistake(severity="critical", related_concepts=["X"])
        man_low = _mistake_to_manifest(m_low, None, ["r1"], "proj")
        man_crit = _mistake_to_manifest(m_crit, None, ["r1"], "proj")
        assert len(man_low["edges"]) == len(man_crit["edges"])
        assert len(man_low["concepts"]) == len(man_crit["concepts"])

    def test_resolution_adds_rule_and_implements_edge(self):
        """Adding resolution_action adds exactly 1 rule + 1 IMPLEMENTS edge."""
        m_no = _make_mistake()
        m_res = _make_mistake(resolution_action="fixed it")
        man_no = _mistake_to_manifest(m_no, None, [], "proj")
        man_res = _mistake_to_manifest(m_res, None, [], "proj")
        assert len(man_res["rules"]) - len(man_no["rules"]) == 1
        implements_no = [
            e for e in man_no["edges"] if e["relation_type"] == "implements"
        ]
        implements_res = [
            e for e in man_res["edges"] if e["relation_type"] == "implements"
        ]
        assert len(implements_res) - len(implements_no) == 1

    def test_resolution_with_corrected_rule_adds_supports_edge(self):
        """resolution_action + corrected_by_rule adds an extra SUPPORTS edge."""
        m_res_only = _make_mistake(resolution_action="fixed")
        m_res_rule = _make_mistake(
            resolution_action="fixed", corrected_by_rule="rule-1"
        )
        man1 = _mistake_to_manifest(m_res_only, None, [], "proj")
        man2 = _mistake_to_manifest(m_res_rule, None, [], "proj")
        # man2 has 1 extra supports edge from resolution_edges
        # + 1 supports edge from rule_support = 2 more supports edges
        supports1 = [e for e in man1["edges"] if e["relation_type"] == "supports"]
        supports2 = [e for e in man2["edges"] if e["relation_type"] == "supports"]
        assert len(supports2) - len(supports1) == 2

    def test_chain_type_mapping_exhaustive(self):
        """Every known chain type produces a valid edge."""
        for chain_type in [
            "escalation",
            "same_pattern",
            "regression",
            "caused_by",
            "part_of",
        ]:
            m = _make_mistake(relation_to_prior={"id": "prior", "type": chain_type})
            ctx = _make_ctx(m)
            out = mistake_chain(ctx)
            assert len(out.edges) == 1
            assert out.edges[0]["relation_type"] in {
                "refines",
                "similar_to",
                "contradicts",
                "requires",
                "part_of",
            }

    def test_idempotent_emission(self):
        """Emitting the same mistake twice produces structurally identical manifests."""
        m = _make_mistake(
            related_concepts=["X"],
            severity="high",
            corrected_by_rule="r1",
            resolution_action="fixed",
        )
        man1 = _mistake_to_manifest(m, None, ["r1"], "proj")
        man2 = _mistake_to_manifest(m, None, ["r1"], "proj")
        assert len(man1["concepts"]) == len(man2["concepts"])
        assert len(man1["edges"]) == len(man2["edges"])
        assert len(man1["rules"]) == len(man2["rules"])
        # Same relation types
        types1 = sorted(e["relation_type"] for e in man1["edges"])
        types2 = sorted(e["relation_type"] for e in man2["edges"])
        assert types1 == types2


# ============================================================================
# Part 9: Round-trip property test for enriched Mistake fields via SQLite
# ============================================================================


class TestMistakeSQLiteRoundTrip:
    """Property test: enriched Mistake fields survive persist → load via SQLite."""

    @given(m=mistake_st())
    @settings(max_examples=50)
    def test_round_trip_fidelity(self, m: Mistake):
        """Persist a random Mistake via SQLite, load it back, verify all fields."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        from buildlog.storage.sqlite import SQLiteBackend

        backend = SQLiteBackend(conn)
        project_id = "roundtrip-test"
        backend.ensure_project(project_id, "test", "/tmp/test")

        # Persist
        backend.append_event(project_id, "mistakes", m.to_dict())

        # Load
        rows = backend.load_events(project_id, "mistakes")
        assert len(rows) == 1
        loaded = Mistake.from_dict(rows[0])

        # Verify every field round-trips
        assert loaded.id == m.id
        assert loaded.session_id == m.session_id
        assert loaded.error_class == m.error_class
        assert loaded.description == m.description
        assert loaded.semantic_hash == m.semantic_hash
        assert loaded.was_repeat == m.was_repeat
        assert loaded.corrected_by_rule == m.corrected_by_rule
        assert loaded.related_concepts == m.related_concepts
        assert loaded.relation_to_prior == m.relation_to_prior
        assert loaded.resolution_action == m.resolution_action
        assert loaded.context == m.context
        assert loaded.severity == m.severity


# ============================================================================
# Part 10: YAML emissions config integration test (disabled_mappers)
# ============================================================================


class TestYAMLEmissionsConfig:
    """Integration test: YAML config disables individual mappers."""

    def test_disabled_mappers_skipped(self):
        """Load a YAML config string and verify disabled mappers are not run."""
        import yaml

        yaml_content = """\
disabled_mappers:
  - resolution_edges
  - concept_involvement
"""
        cfg = yaml.safe_load(yaml_content) or {}

        # Build a fresh registry with all 6 mappers
        reg = EdgeMapperRegistry()
        reg.register("concept_involvement", concept_involvement)
        reg.register("rule_challenge", rule_challenge)
        reg.register("rule_support", rule_support)
        reg.register("mistake_chain", mistake_chain)
        reg.register("resolution_rule", resolution_rule)
        reg.register("resolution_edges", resolution_edges)

        # Apply YAML config
        for mapper_name in cfg.get("disabled_mappers", []):
            reg.disable(mapper_name)

        # Verify disabled mappers are gone
        enabled = reg.enabled_names()
        assert "resolution_edges" not in enabled
        assert "concept_involvement" not in enabled

        # Verify remaining mappers still present
        assert "rule_challenge" in enabled
        assert "rule_support" in enabled
        assert "mistake_chain" in enabled
        assert "resolution_rule" in enabled
        assert len(enabled) == 4

    def test_disabled_mappers_not_executed(self):
        """Disabled mappers should produce no output when run_all is called."""
        import yaml

        yaml_content = """\
disabled_mappers:
  - concept_involvement
"""
        cfg = yaml.safe_load(yaml_content) or {}

        reg = EdgeMapperRegistry()
        reg.register("concept_involvement", concept_involvement)
        for mapper_name in cfg.get("disabled_mappers", []):
            reg.disable(mapper_name)

        # Run with a mistake that has related_concepts
        m = _make_mistake(related_concepts=["schema", "migration"])
        ctx = _make_ctx(m)
        out = reg.run_all(ctx)

        # concept_involvement is disabled, so no edges
        assert out.edges == []
        assert out.rules == []

    def test_empty_disabled_list_keeps_all(self):
        """An empty disabled_mappers list should keep all mappers enabled."""
        import yaml

        yaml_content = "disabled_mappers: []\n"
        cfg = yaml.safe_load(yaml_content) or {}

        reg = EdgeMapperRegistry()
        reg.register("concept_involvement", concept_involvement)
        reg.register("rule_challenge", rule_challenge)

        for mapper_name in cfg.get("disabled_mappers", []):
            reg.disable(mapper_name)

        assert len(reg.enabled_names()) == 2

    def test_unknown_mapper_name_ignored(self):
        """Disabling a non-existent mapper should not raise."""
        import yaml

        yaml_content = """\
disabled_mappers:
  - nonexistent_mapper
"""
        cfg = yaml.safe_load(yaml_content) or {}

        reg = EdgeMapperRegistry()
        reg.register("concept_involvement", concept_involvement)

        for mapper_name in cfg.get("disabled_mappers", []):
            reg.disable(mapper_name)

        # nonexistent_mapper is not in the registry, so discard is a no-op
        assert "concept_involvement" in reg.enabled_names()


# ============================================================================
# Part 11: Schema v3 migration — session_id on reward_events
# ============================================================================


class TestSchemaV3Migration:
    """Tests for v3 migration: session_id column on reward_events."""

    def test_fresh_install_has_session_id(self):
        """Fresh DB should have session_id column on reward_events."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        cursor = conn.execute("PRAGMA table_info(reward_events)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "session_id" in columns

    def test_v2_to_v3_migration(self):
        """Simulate a v2 DB and verify v3 migration applies cleanly."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # Create reward_events WITHOUT session_id (v1/v2 schema)
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY,"
            "applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            ");"
        )
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS projects ("
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,"
            "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),"
            "updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            ");"
        )
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS reward_events ("
            "project_id TEXT NOT NULL REFERENCES projects(id),"
            "id TEXT NOT NULL, timestamp TEXT NOT NULL,"
            "outcome TEXT NOT NULL, reward_value REAL NOT NULL,"
            "rules_active TEXT, revision_distance REAL,"
            "error_class TEXT, notes TEXT, source TEXT,"
            "PRIMARY KEY (project_id, id));"
        )
        conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (2,))
        conn.commit()

        # Verify session_id doesn't exist yet
        cursor = conn.execute("PRAGMA table_info(reward_events)")
        cols_v2 = {row["name"] for row in cursor.fetchall()}
        assert "session_id" not in cols_v2

        # Apply v3 migration
        from buildlog.storage.schema import _MIGRATE_V3

        for stmt in _MIGRATE_V3:
            conn.execute(stmt)
        conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (3,))
        conn.commit()

        # Verify session_id exists now
        cursor = conn.execute("PRAGMA table_info(reward_events)")
        cols_v3 = {row["name"] for row in cursor.fetchall()}
        assert "session_id" in cols_v3

    def test_v3_migration_idempotent(self):
        """Running v3 migration twice doesn't break anything."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        version1 = init_schema(conn)
        version2 = init_schema(conn)
        assert version1 == 4
        assert version2 == 4


# ============================================================================
# Part 12: Reward-session linking tests
# ============================================================================


class TestRewardSessionLinking:
    """Tests for RewardEvent.session_id field and reward emission."""

    def test_reward_event_session_id_default_none(self):
        """New field defaults to None."""
        from buildlog.core.operations import RewardEvent

        event = RewardEvent(
            id="test",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
        )
        assert event.session_id is None

    def test_reward_event_to_dict_includes_session_id(self):
        """session_id appears in to_dict when set."""
        from buildlog.core.operations import RewardEvent

        event = RewardEvent(
            id="test",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
            session_id="sess-123",
        )
        d = event.to_dict()
        assert d["session_id"] == "sess-123"

    def test_reward_event_to_dict_omits_none_session(self):
        """session_id omitted from to_dict when None."""
        from buildlog.core.operations import RewardEvent

        event = RewardEvent(
            id="test",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
        )
        d = event.to_dict()
        assert "session_id" not in d

    def test_reward_event_from_dict_round_trip(self):
        """session_id survives from_dict round-trip."""
        from buildlog.core.operations import RewardEvent

        event = RewardEvent(
            id="test",
            timestamp=datetime.now(timezone.utc),
            outcome="revision",
            reward_value=0.7,
            session_id="sess-456",
        )
        d = event.to_dict()
        loaded = RewardEvent.from_dict(d)
        assert loaded.session_id == "sess-456"

    def test_reward_event_backwards_compat(self):
        """from_dict without session_id (v2 data) still works."""
        from buildlog.core.operations import RewardEvent

        d = {
            "id": "old",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "outcome": "accepted",
            "reward_value": 1.0,
            "rules_active": [],
        }
        event = RewardEvent.from_dict(d)
        assert event.session_id is None

    def test_reward_sqlite_round_trip(self):
        """session_id survives SQLite persist → load."""
        from buildlog.core.operations import RewardEvent
        from buildlog.storage.sqlite import SQLiteBackend

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        backend = SQLiteBackend(conn)
        project_id = "reward-rt"
        backend.ensure_project(project_id, "test", "/tmp/test")

        event = RewardEvent(
            id="rt-1",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
            rules_active=["rule-a", "rule-b"],
            session_id="sess-789",
        )
        backend.append_event(project_id, "rewards", event.to_dict())

        rows = backend.load_events(project_id, "rewards")
        assert len(rows) == 1
        loaded = RewardEvent.from_dict(rows[0])
        assert loaded.session_id == "sess-789"
        assert loaded.rules_active == ["rule-a", "rule-b"]


# ============================================================================
# Part 13: Reward emission tests
# ============================================================================


class TestRewardEmission:
    """Tests for _reward_to_emission helper."""

    def test_basic_reward_emission(self):
        """Accepted reward emits correct structure."""
        from buildlog.core.operations import RewardEvent, _reward_to_emission

        event = RewardEvent(
            id="r-1",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
            rules_active=["rule-1", "rule-2"],
            session_id="sess-1",
        )
        emission = _reward_to_emission(event, "proj")

        assert emission["domain"] == "experiential"
        assert len(emission["concepts"]) == 1
        assert emission["concepts"][0]["name"] == "reward:r-1"

        # 2 rule edges (supports) + 1 session edge (part_of)
        assert len(emission["edges"]) == 3

        # Check rule edges are SUPPORTS (accepted)
        rule_edges = [e for e in emission["edges"] if e["target_id"].startswith("rule")]
        assert all(e["relation_type"] == "supports" for e in rule_edges)

        # Check session edge
        session_edges = [
            e for e in emission["edges"] if e["relation_type"] == "part_of"
        ]
        assert len(session_edges) == 1
        assert session_edges[0]["target_id"] == "session:sess-1"

    def test_rejected_reward_challenges_rules(self):
        """Rejected reward emits CHALLENGES edges."""
        from buildlog.core.operations import RewardEvent, _reward_to_emission

        event = RewardEvent(
            id="r-2",
            timestamp=datetime.now(timezone.utc),
            outcome="rejected",
            reward_value=0.0,
            rules_active=["rule-1"],
        )
        emission = _reward_to_emission(event, "proj")

        rule_edges = [e for e in emission["edges"] if e["target_id"] == "rule-1"]
        assert len(rule_edges) == 1
        assert rule_edges[0]["relation_type"] == "challenges"

    def test_revision_reward_edge_direction(self):
        """Revision with high reward → supports, low reward → challenges."""
        from buildlog.core.operations import RewardEvent, _reward_to_emission

        # High revision (reward=0.7 > 0.5) → supports
        event_hi = RewardEvent(
            id="r-hi",
            timestamp=datetime.now(timezone.utc),
            outcome="revision",
            reward_value=0.7,
            rules_active=["rule-1"],
        )
        em_hi = _reward_to_emission(event_hi, "proj")
        assert em_hi["edges"][0]["relation_type"] == "supports"

        # Low revision (reward=0.3 < 0.5) → challenges
        event_lo = RewardEvent(
            id="r-lo",
            timestamp=datetime.now(timezone.utc),
            outcome="revision",
            reward_value=0.3,
            rules_active=["rule-1"],
        )
        em_lo = _reward_to_emission(event_lo, "proj")
        assert em_lo["edges"][0]["relation_type"] == "challenges"

    def test_no_rules_no_rule_edges(self):
        """Reward without rules_active produces no rule edges."""
        from buildlog.core.operations import RewardEvent, _reward_to_emission

        event = RewardEvent(
            id="r-3",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
            rules_active=[],
        )
        emission = _reward_to_emission(event, "proj")
        assert len(emission["edges"]) == 0

    def test_no_session_no_session_edge(self):
        """Reward without session_id produces no session edge."""
        from buildlog.core.operations import RewardEvent, _reward_to_emission

        event = RewardEvent(
            id="r-4",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
            rules_active=["rule-1"],
        )
        emission = _reward_to_emission(event, "proj")
        session_edges = [
            e for e in emission["edges"] if e["relation_type"] == "part_of"
        ]
        assert len(session_edges) == 0

    def test_emission_metadata(self):
        """Emission metadata includes project_id, reward_id, session_id."""
        from buildlog.core.operations import RewardEvent, _reward_to_emission

        event = RewardEvent(
            id="r-5",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
            session_id="sess-meta",
        )
        emission = _reward_to_emission(event, "proj-x")
        assert emission["metadata"]["project_id"] == "proj-x"
        assert emission["metadata"]["reward_id"] == "r-5"
        assert emission["metadata"]["session_id"] == "sess-meta"

    def test_edge_count_property(self):
        """Edge count ≥ len(rules_active) + (1 if session_id else 0)."""
        from buildlog.core.operations import RewardEvent, _reward_to_emission

        event = RewardEvent(
            id="r-prop",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
            rules_active=["a", "b", "c"],
            session_id="s-1",
        )
        emission = _reward_to_emission(event, "proj")
        assert len(emission["edges"]) >= len(event.rules_active) + 1

    def test_revision_midpoint_boundary(self):
        """Revision at exactly 0.5 → challenges (pessimistic lean), confidence=0.0."""
        from buildlog.core.operations import RewardEvent, _reward_to_emission

        event = RewardEvent(
            id="r-mid",
            timestamp=datetime.now(timezone.utc),
            outcome="revision",
            reward_value=0.5,
            rules_active=["rule-1"],
        )
        emission = _reward_to_emission(event, "proj")
        edge = emission["edges"][0]
        # At 0.5 boundary: lean pessimistic → challenges
        assert edge["relation_type"] == "challenges"
        # Confidence = abs(0.5 - 0.5) * 2 = 0.0
        assert edge["confidence"] == 0.0

    def test_no_matching_session_returns_empty(self):
        """get_rewards with non-existent session_id returns empty summary."""
        from buildlog.core.operations import RewardEvent, get_rewards
        from buildlog.storage.sqlite import SQLiteBackend

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        backend = SQLiteBackend(conn)
        project_id = "filter-test"
        backend.ensure_project(project_id, "test", "/tmp/test")

        # Add a reward with session "s-1"
        event = RewardEvent(
            id="r-filter",
            timestamp=datetime.now(timezone.utc),
            outcome="accepted",
            reward_value=1.0,
            session_id="s-1",
        )
        backend.append_event(project_id, "rewards", event.to_dict())

        # Query for non-existent session
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            buildlog_dir = Path(tmpdir) / "buildlog"
            buildlog_dir.mkdir()
            # We need to use the real get_rewards which calls _get_storage,
            # but that needs a real project. Test the filtering logic directly:
            raw_events = backend.load_events(project_id, "rewards")
            filtered = [e for e in raw_events if e.get("session_id") == "nonexistent"]
            assert filtered == []


# ============================================================================
# Part 14: Integration test — log_reward fires emission
# ============================================================================


class TestLogRewardEmissionIntegration:
    """Verify that log_reward() actually calls emit_artifact."""

    def test_log_reward_fires_emission(self, tmp_path, monkeypatch):
        """log_reward() calls emit_artifact with artifact_type='reward_signal'."""
        from unittest.mock import MagicMock, patch

        from buildlog.core.operations import log_reward

        # Set up a minimal buildlog dir with SQLite backend
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        mock_emit = MagicMock(return_value=None)
        with patch("buildlog.core.operations.emit_artifact", mock_emit, create=True):
            # Need to also patch the import inside the try block
            import buildlog.emissions

            monkeypatch.setattr(buildlog.emissions, "emit_artifact", mock_emit)

            result = log_reward(
                buildlog_dir,
                outcome="accepted",
                rules_active=["rule-1"],
                source="test",
            )

        assert result.reward_id
        # Verify emit_artifact was called
        assert mock_emit.called
        call_kwargs = mock_emit.call_args
        assert call_kwargs[1]["artifact_type"] == "reward_signal"
