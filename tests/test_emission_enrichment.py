"""Tests for emission edge enrichment: skill ID → gauntlet rule ID resolution.

Covers:
- _build_skill_to_gauntlet_map() — mapping function
- _resolve_rule_target() — resolution helper
- Mapper integration — rule_challenge, rule_support, resolution_edges
- Emission functions — _session_to_emission, _reward_to_emission, _mistake_to_manifest
- Backward compatibility — empty/missing mapping falls back to bare IDs
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from buildlog.core.operations import (
    Mistake,
    RewardEvent,
    Session,
    _build_skill_to_gauntlet_map,
    _resolve_rule_target,
    _reward_to_emission,
    _session_to_emission,
)
from buildlog.emissions.mappers import (
    EdgeMapperContext,
    MapperOutput,
    _mistake_to_manifest,
    resolution_edges,
    rule_challenge,
    rule_support,
)
from buildlog.skills import _generate_skill_id
from buildlog.storage.schema import init_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_gauntlet_db(db_path: Path, rules: list[dict]) -> None:
    """Create a minimal gauntlet_rules table with test rules."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gauntlet_rules (
            rule_id TEXT PRIMARY KEY,
            persona TEXT NOT NULL,
            rule TEXT NOT NULL,
            category TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            provenance TEXT,
            seed_filename TEXT,
            context TEXT NOT NULL DEFAULT '',
            antipattern TEXT NOT NULL DEFAULT '',
            rationale TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            refs TEXT DEFAULT '[]',
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            seed_file_hash TEXT
        )
    """
    )
    for r in rules:
        conn.execute(
            "INSERT INTO gauntlet_rules (rule_id, persona, rule, category, active) "
            "VALUES (?, ?, ?, ?, ?)",
            (r["rule_id"], r["persona"], r["rule"], r["category"], r.get("active", 1)),
        )
    conn.commit()
    conn.close()


def _make_gauntlet_rule(
    persona: str, rule_text: str, category: str = "architectural"
) -> dict:
    """Build a gauntlet rule dict with its deterministic rule_id."""
    digest = hashlib.sha256(rule_text.encode()).hexdigest()[:8]
    return {
        "rule_id": f"{persona}:{digest}",
        "persona": persona,
        "rule": rule_text,
        "category": category,
        "active": 1,
    }


def _make_mistake(**overrides) -> Mistake:
    """Factory for test Mistake objects."""
    defaults = dict(
        id="mistake-test-001",
        session_id="session-test-001",
        timestamp=datetime(2026, 2, 14, 12, 0, 0, tzinfo=timezone.utc),
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


def _make_session(**overrides) -> Session:
    """Factory for test Session objects."""
    defaults = dict(
        id="session-test-001",
        started_at=datetime(2026, 2, 14, 10, 0, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 2, 14, 11, 0, 0, tzinfo=timezone.utc),
        selected_rules=[],
        rules_at_start=[],
        rules_at_end=[],
        error_class=None,
        entry_file=None,
        notes=None,
    )
    defaults.update(overrides)
    return Session(**defaults)


def _make_reward_event(**overrides) -> RewardEvent:
    """Factory for test RewardEvent objects."""
    defaults = dict(
        id="reward-test-001",
        timestamp=datetime(2026, 2, 14, 12, 0, 0, tzinfo=timezone.utc),
        outcome="accepted",
        reward_value=1.0,
        rules_active=[],
        error_class=None,
        session_id="session-test-001",
        source="test",
        notes=None,
    )
    defaults.update(overrides)
    return RewardEvent(**defaults)


# ---------------------------------------------------------------------------
# Tests: _build_skill_to_gauntlet_map
# ---------------------------------------------------------------------------


class TestBuildSkillToGauntletMap:
    def test_builds_correct_mapping(self, tmp_path: Path):
        """Gauntlet rule text → skill ID → gauntlet_rule:{rule_id} mapping."""
        rule_text = "Always define interfaces before implementations"
        rule = _make_gauntlet_rule("test_terrorist", rule_text, "architectural")

        buildlog_dir = tmp_path / "buildlog"
        db_path = buildlog_dir / ".buildlog" / "buildlog.db"
        _setup_gauntlet_db(db_path, [rule])

        mapping = _build_skill_to_gauntlet_map(buildlog_dir)

        # The skill ID for this rule
        expected_skill_id = _generate_skill_id("architectural", rule_text)
        assert expected_skill_id in mapping
        assert mapping[expected_skill_id] == f"gauntlet_rule:{rule['rule_id']}"

    def test_multiple_rules_multiple_categories(self, tmp_path: Path):
        """Maps rules across different categories correctly."""
        rules = [
            _make_gauntlet_rule("test_terrorist", "Test everything", "architectural"),
            _make_gauntlet_rule("qortex_dp", "Use dependency injection", "workflow"),
            _make_gauntlet_rule("pragmatic_pete", "Keep it simple", "domain_knowledge"),
        ]

        buildlog_dir = tmp_path / "buildlog"
        db_path = buildlog_dir / ".buildlog" / "buildlog.db"
        _setup_gauntlet_db(db_path, rules)

        mapping = _build_skill_to_gauntlet_map(buildlog_dir)
        assert len(mapping) == 3

        for rule in rules:
            skill_id = _generate_skill_id(rule["category"], rule["rule"])
            assert skill_id in mapping
            assert mapping[skill_id] == f"gauntlet_rule:{rule['rule_id']}"

    def test_skips_inactive_rules(self, tmp_path: Path):
        """Inactive gauntlet rules are excluded from mapping."""
        active_rule = _make_gauntlet_rule("persona_a", "Active rule", "architectural")
        inactive_rule = _make_gauntlet_rule(
            "persona_b", "Inactive rule", "architectural"
        )
        inactive_rule["active"] = 0

        buildlog_dir = tmp_path / "buildlog"
        db_path = buildlog_dir / ".buildlog" / "buildlog.db"
        _setup_gauntlet_db(db_path, [active_rule, inactive_rule])

        mapping = _build_skill_to_gauntlet_map(buildlog_dir)
        assert len(mapping) == 1

        inactive_skill = _generate_skill_id("architectural", "Inactive rule")
        assert inactive_skill not in mapping

    def test_returns_empty_when_no_db(self, tmp_path: Path):
        """Returns empty dict when buildlog DB doesn't exist."""
        mapping = _build_skill_to_gauntlet_map(tmp_path / "nonexistent")
        assert mapping == {}

    def test_returns_empty_when_no_gauntlet_table(self, tmp_path: Path):
        """Returns empty dict when gauntlet_rules table doesn't exist."""
        buildlog_dir = tmp_path / "buildlog"
        db_path = buildlog_dir / ".buildlog" / "buildlog.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Create DB without gauntlet_rules table
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dummy (id TEXT)")
        conn.close()

        mapping = _build_skill_to_gauntlet_map(buildlog_dir)
        assert mapping == {}


# ---------------------------------------------------------------------------
# Tests: _resolve_rule_target
# ---------------------------------------------------------------------------


class TestResolveRuleTarget:
    def test_resolves_known_skill_id(self):
        mapping = {"arch-abc1234567": "gauntlet_rule:test_terrorist:deadbeef"}
        assert (
            _resolve_rule_target("arch-abc1234567", mapping)
            == "gauntlet_rule:test_terrorist:deadbeef"
        )

    def test_passthrough_unknown_skill_id(self):
        mapping = {"arch-abc1234567": "gauntlet_rule:test_terrorist:deadbeef"}
        assert _resolve_rule_target("dk-unknown12345", mapping) == "dk-unknown12345"

    def test_passthrough_with_empty_map(self):
        assert _resolve_rule_target("arch-abc1234567", {}) == "arch-abc1234567"


# ---------------------------------------------------------------------------
# Tests: Mapper integration with gauntlet_map
# ---------------------------------------------------------------------------


class TestMapperGauntletResolution:
    def _make_ctx(
        self, selected_rules: list[str], gauntlet_map: dict[str, str], **kw
    ) -> EdgeMapperContext:
        mistake = _make_mistake(**kw)
        return EdgeMapperContext(
            mistake=mistake,
            mistake_node_id=f"mistake:{mistake.id}",
            domain="experiential",
            source_id="buildlog:test",
            selected_rules=selected_rules,
            session_data=None,
            gauntlet_map=gauntlet_map,
        )

    def test_rule_challenge_resolves_targets(self):
        """rule_challenge mapper uses gauntlet_map to resolve skill IDs."""
        gmap = {"arch-abc": "gauntlet_rule:test_terrorist:deadbeef"}
        ctx = self._make_ctx(selected_rules=["arch-abc"], gauntlet_map=gmap)
        result = rule_challenge(ctx)

        assert len(result.edges) == 1
        assert result.edges[0]["target_id"] == "gauntlet_rule:test_terrorist:deadbeef"

    def test_rule_challenge_passthrough_without_map(self):
        """rule_challenge falls back to bare ID when no map entry."""
        ctx = self._make_ctx(selected_rules=["arch-abc"], gauntlet_map={})
        result = rule_challenge(ctx)

        assert len(result.edges) == 1
        assert result.edges[0]["target_id"] == "arch-abc"

    def test_rule_support_resolves_target(self):
        """rule_support mapper uses gauntlet_map to resolve corrected_by_rule."""
        gmap = {"wf-xyz": "gauntlet_rule:qortex_dp:cafebabe"}
        ctx = self._make_ctx(
            selected_rules=[],
            gauntlet_map=gmap,
            corrected_by_rule="wf-xyz",
        )
        result = rule_support(ctx)

        assert len(result.edges) == 1
        assert result.edges[0]["target_id"] == "gauntlet_rule:qortex_dp:cafebabe"

    def test_resolution_edges_resolves_target(self):
        """resolution_edges mapper uses gauntlet_map to resolve corrected_by_rule."""
        gmap = {"dk-fix": "gauntlet_rule:pragmatic:12345678"}
        ctx = self._make_ctx(
            selected_rules=[],
            gauntlet_map=gmap,
            corrected_by_rule="dk-fix",
            resolution_action="Fixed the thing",
        )
        result = resolution_edges(ctx)

        # Should have 2 edges: resolution→mistake (implements) + resolution→rule (supports)
        assert len(result.edges) == 2
        supports_edge = [e for e in result.edges if e["relation_type"] == "supports"][0]
        assert supports_edge["target_id"] == "gauntlet_rule:pragmatic:12345678"


# ---------------------------------------------------------------------------
# Tests: _mistake_to_manifest with gauntlet_map
# ---------------------------------------------------------------------------


class TestMistakeToManifestEnriched:
    def test_manifest_edges_use_gauntlet_ids(self):
        """Manifest edges resolve skill IDs to gauntlet_rule:{id} format."""
        gmap = {"arch-abc": "gauntlet_rule:test_terrorist:deadbeef"}
        mistake = _make_mistake()
        manifest = _mistake_to_manifest(
            mistake=mistake,
            session_data=None,
            selected_rules=["arch-abc"],
            project_id="test-proj",
            gauntlet_map=gmap,
        )

        challenge_edges = [
            e for e in manifest["edges"] if e["relation_type"] == "challenges"
        ]
        assert len(challenge_edges) == 1
        assert (
            challenge_edges[0]["target_id"] == "gauntlet_rule:test_terrorist:deadbeef"
        )

    def test_manifest_backward_compat_no_map(self):
        """Manifest works without gauntlet_map (backward compatible)."""
        mistake = _make_mistake()
        manifest = _mistake_to_manifest(
            mistake=mistake,
            session_data=None,
            selected_rules=["arch-abc"],
            project_id="test-proj",
        )

        challenge_edges = [
            e for e in manifest["edges"] if e["relation_type"] == "challenges"
        ]
        assert len(challenge_edges) == 1
        assert challenge_edges[0]["target_id"] == "arch-abc"


# ---------------------------------------------------------------------------
# Tests: _session_to_emission with gauntlet_map
# ---------------------------------------------------------------------------


class TestSessionToEmissionEnriched:
    def test_session_edges_use_gauntlet_ids(self):
        """Session emission resolves selected_rules to gauntlet IDs."""
        gmap = {
            "arch-abc": "gauntlet_rule:test_terrorist:deadbeef",
            "dk-xyz": "gauntlet_rule:pragmatic:cafebabe",
        }
        session = _make_session(selected_rules=["arch-abc", "dk-xyz"])

        emission = _session_to_emission(
            session=session,
            session_mistakes=[],
            duration=60.0,
            repeated=0,
            auto_outcome="accepted",
            project_id="test-proj",
            gauntlet_map=gmap,
        )

        rule_edges = [e for e in emission["edges"] if e["relation_type"] == "uses"]
        targets = {e["target_id"] for e in rule_edges}
        assert targets == {
            "gauntlet_rule:test_terrorist:deadbeef",
            "gauntlet_rule:pragmatic:cafebabe",
        }

    def test_session_backward_compat_no_map(self):
        """Session emission works without gauntlet_map."""
        session = _make_session(selected_rules=["arch-abc"])

        emission = _session_to_emission(
            session=session,
            session_mistakes=[],
            duration=60.0,
            repeated=0,
            auto_outcome="accepted",
            project_id="test-proj",
        )

        rule_edges = [e for e in emission["edges"] if e["relation_type"] == "uses"]
        assert rule_edges[0]["target_id"] == "arch-abc"

    def test_session_mixed_resolved_and_unresolved(self):
        """Some rules resolve, others fall through."""
        gmap = {"arch-abc": "gauntlet_rule:persona:deadbeef"}
        session = _make_session(selected_rules=["arch-abc", "unknown-id"])

        emission = _session_to_emission(
            session=session,
            session_mistakes=[],
            duration=60.0,
            repeated=0,
            auto_outcome="accepted",
            project_id="test-proj",
            gauntlet_map=gmap,
        )

        rule_edges = [e for e in emission["edges"] if e["relation_type"] == "uses"]
        targets = {e["target_id"] for e in rule_edges}
        assert "gauntlet_rule:persona:deadbeef" in targets
        assert "unknown-id" in targets


# ---------------------------------------------------------------------------
# Tests: _reward_to_emission with gauntlet_map
# ---------------------------------------------------------------------------


class TestRewardToEmissionEnriched:
    def test_reward_edges_use_gauntlet_ids(self):
        """Reward emission resolves rules_active to gauntlet IDs."""
        gmap = {"arch-abc": "gauntlet_rule:test_terrorist:deadbeef"}
        event = _make_reward_event(rules_active=["arch-abc"])

        emission = _reward_to_emission(
            event=event,
            project_id="test-proj",
            gauntlet_map=gmap,
        )

        rule_edges = [
            e
            for e in emission["edges"]
            if e["relation_type"] in ("supports", "challenges")
            and e["target_id"].startswith("gauntlet_rule:")
        ]
        assert len(rule_edges) == 1
        assert rule_edges[0]["target_id"] == "gauntlet_rule:test_terrorist:deadbeef"

    def test_reward_backward_compat_no_map(self):
        """Reward emission works without gauntlet_map."""
        event = _make_reward_event(rules_active=["arch-abc"])

        emission = _reward_to_emission(
            event=event,
            project_id="test-proj",
        )

        rule_edges = [
            e
            for e in emission["edges"]
            if e["relation_type"] in ("supports", "challenges")
        ]
        assert len(rule_edges) == 1
        assert rule_edges[0]["target_id"] == "arch-abc"


# ---------------------------------------------------------------------------
# Tests: End-to-end mapping round-trip
# ---------------------------------------------------------------------------


class TestEndToEndMapping:
    def test_roundtrip_rule_text_to_gauntlet_id(self, tmp_path: Path):
        """Full round-trip: rule text → gauntlet DB → skill ID → mapping → resolved target."""
        rule_text = "Never commit directly to main"
        persona = "test_terrorist"
        category = "workflow"

        rule = _make_gauntlet_rule(persona, rule_text, category)
        buildlog_dir = tmp_path / "buildlog"
        db_path = buildlog_dir / ".buildlog" / "buildlog.db"
        _setup_gauntlet_db(db_path, [rule])

        # Build the mapping
        mapping = _build_skill_to_gauntlet_map(buildlog_dir)

        # Compute the skill ID that would be used in a session
        skill_id = _generate_skill_id(category, rule_text)

        # Resolve it
        resolved = _resolve_rule_target(skill_id, mapping)
        assert resolved == f"gauntlet_rule:{rule['rule_id']}"

    def test_emission_with_real_db(self, tmp_path: Path):
        """Session emission with real gauntlet DB produces resolved targets."""
        rule_text = "Always test edge cases"
        persona = "qa_master"
        category = "architectural"

        rule = _make_gauntlet_rule(persona, rule_text, category)
        buildlog_dir = tmp_path / "buildlog"
        db_path = buildlog_dir / ".buildlog" / "buildlog.db"
        _setup_gauntlet_db(db_path, [rule])

        mapping = _build_skill_to_gauntlet_map(buildlog_dir)
        skill_id = _generate_skill_id(category, rule_text)

        session = _make_session(selected_rules=[skill_id])
        emission = _session_to_emission(
            session=session,
            session_mistakes=[],
            duration=60.0,
            repeated=0,
            auto_outcome="accepted",
            project_id="test-proj",
            gauntlet_map=mapping,
        )

        rule_edges = [e for e in emission["edges"] if e["relation_type"] == "uses"]
        assert len(rule_edges) == 1
        assert rule_edges[0]["target_id"] == f"gauntlet_rule:{rule['rule_id']}"
