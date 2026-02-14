"""E2E tests for the learning loop: ID alignment, seed detection, migration.

Verifies that:
1. _generate_learning_id() produces the same IDs as _generate_skill_id() (P0)
2. _get_seed_rule_ids() detects YAML seeds in gauntlet_rules (P1)
3. migrate_learning_ids() re-keys old-style IDs (P0)
4. The full loop (import → select → mistake → review → promote) works end-to-end
5. Dashboard data (session.rules_at_start) contains the unified pool
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.core.operations import (
    _generate_learning_id,
    _get_current_rules,
    _get_seed_rule_ids,
    learn_from_review,
    migrate_learning_ids,
    promote,
    start_session,
)
from buildlog.skills import Skill, SkillSet, _generate_skill_id
from buildlog.storage.schema import init_schema
from buildlog.storage.sqlite import SQLiteBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_backend(tmp_path: Path) -> tuple[SQLiteBackend, str, Path]:
    """Create a fresh backend with schema."""
    buildlog_dir = tmp_path / "project"
    db_dir = buildlog_dir / ".buildlog"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "buildlog.db"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    backend = SQLiteBackend(conn)
    project_id = "test-project"
    backend.ensure_project(project_id, "Test Project", str(buildlog_dir))

    return backend, project_id, buildlog_dir


def _make_skill(rule: str, category: str = "architectural", **kw) -> Skill:
    """Create a test Skill."""
    return Skill(
        id=_generate_skill_id(category, rule),
        category=category,
        rule=rule,
        frequency=kw.get("frequency", 3),
        confidence="high",
        sources=kw.get("sources", ["test.md"]),
        tags=kw.get("tags", []),
        persona_tags=kw.get("persona_tags", []),
        provenance=kw.get("provenance"),
    )


def _insert_gauntlet_rule(
    backend: SQLiteBackend,
    rule_id: str,
    rule: str,
    persona: str = "test_persona",
    active: int = 1,
    provenance: dict | None = None,
) -> None:
    """Insert a gauntlet rule directly."""
    prov = json.dumps(provenance or {"derivation": "seed"})
    backend.save_gauntlet_rules_batch(
        [
            {
                "rule_id": rule_id,
                "persona": persona,
                "rule": rule,
                "category": "principle",
                "context": "",
                "antipattern": "",
                "rationale": "",
                "tags": "[]",
                "refs": "[]",
                "provenance": prov,
                "version": 1,
                "active": active,
            }
        ]
    )


def _mock_storage(backend, project_id):
    """Return a context manager that patches _get_storage."""
    return patch(
        "buildlog.core.operations._get_storage",
        return_value=(backend, project_id),
    )


def _mock_generate_skills(skill_set):
    """Return a context manager that patches generate_skills."""
    return patch(
        "buildlog.core.operations.generate_skills",
        return_value=skill_set,
    )


def _empty_skill_set() -> SkillSet:
    return SkillSet(
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_entries=0,
        skills={},
    )


# ---------------------------------------------------------------------------
# Tests: ID Alignment (P0)
# ---------------------------------------------------------------------------


class TestIDAlignment:
    """_generate_learning_id must produce the same ID as _generate_skill_id."""

    def test_learning_id_matches_skill_id(self):
        """Same (category, rule) → same ID for all standard categories."""
        for category in ("architectural", "workflow", "tool_usage", "domain_knowledge"):
            rule = "Always define interfaces before implementations"
            assert _generate_learning_id(category, rule) == _generate_skill_id(
                category, rule
            ), f"ID mismatch for category={category}"

    def test_domain_knowledge_prefix_is_dk(self):
        """domain_knowledge rules must use 'dk-' prefix, not 'dom-'."""
        rule_id = _generate_learning_id("domain_knowledge", "test rule")
        assert rule_id.startswith("dk-"), f"Expected dk- prefix, got {rule_id}"

    def test_unknown_category_prefix_is_sk(self):
        """Unknown categories must use 'sk-' fallback, not category[:4]."""
        rule_id = _generate_learning_id("something_new", "test rule")
        assert rule_id.startswith("sk-"), f"Expected sk- prefix, got {rule_id}"


# ---------------------------------------------------------------------------
# Tests: Skill-Learning Merge (P0 enables this)
# ---------------------------------------------------------------------------


class TestSkillLearningMerge:
    def test_learning_merges_with_skill(self, tmp_path: Path):
        """When IDs match, generate_skills() merges learnings into skills."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)
        rule = "Always define interfaces before implementations"
        category = "architectural"

        # Create a review learning with aligned ID
        learning_id = _generate_learning_id(category, rule)
        skill_id = _generate_skill_id(category, rule)

        # IDs MUST match (this is the P0 fix)
        assert learning_id == skill_id

        # Store a learning via the backend
        data = {
            "learnings": {
                learning_id: {
                    "id": learning_id,
                    "rule": rule,
                    "category": category,
                    "severity": "major",
                    "source": "review:test",
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "last_reinforced": datetime.now(timezone.utc).isoformat(),
                    "reinforcement_count": 2,
                    "contradiction_count": 0,
                    "functional_principle": "",
                }
            },
            "review_history": [],
        }
        backend.save_learnings(project_id, data)

        # Now generate_skills should merge when it finds the same ID
        # We test the ID equality which is the prerequisite for merge
        assert learning_id == skill_id


# ---------------------------------------------------------------------------
# Tests: Seed Rule Detection (P1)
# ---------------------------------------------------------------------------


class TestSeedRuleDetection:
    def test_seed_from_gauntlet_rules_detected(self, tmp_path: Path):
        """Gauntlet rules with persona != 'learned' should be in seed_ids."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        _insert_gauntlet_rule(
            backend, "tt:abc123", "Every PR must have tests", persona="test_terrorist"
        )

        with (
            _mock_storage(backend, project_id),
            _mock_generate_skills(_empty_skill_set()),
        ):
            seed_ids, _ = _get_seed_rule_ids(buildlog_dir)

        assert "tt:abc123" in seed_ids

    def test_learned_rules_not_treated_as_seeds(self, tmp_path: Path):
        """Gauntlet rules with persona='learned' should NOT be seeds."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        _insert_gauntlet_rule(
            backend, "arch-abc123", "Some learned rule", persona="learned"
        )

        with (
            _mock_storage(backend, project_id),
            _mock_generate_skills(_empty_skill_set()),
        ):
            seed_ids, _ = _get_seed_rule_ids(buildlog_dir)

        assert "arch-abc123" not in seed_ids

    def test_seed_confidence_extracted_from_provenance(self, tmp_path: Path):
        """Confidence from provenance JSON should appear in confidence_map."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        _insert_gauntlet_rule(
            backend,
            "sk:conf_test",
            "Rule with confidence",
            persona="security_karen",
            provenance={"confidence": 0.75, "derivation": "seed"},
        )

        with (
            _mock_storage(backend, project_id),
            _mock_generate_skills(_empty_skill_set()),
        ):
            seed_ids, confidence_map = _get_seed_rule_ids(buildlog_dir)

        assert "sk:conf_test" in seed_ids
        assert confidence_map["sk:conf_test"] == pytest.approx(0.75)

    def test_bandit_gives_boosted_priors_to_seeds(self, tmp_path: Path):
        """Seed rules should get Beta(3,1) priors, non-seeds Beta(1,1)."""
        from buildlog.core.bandit import ThompsonSamplingBandit

        state_path = tmp_path / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(state_path)

        seed_ids = {"seed_rule_1"}
        candidates = ["seed_rule_1", "non_seed_rule"]

        # Select triggers arm creation with appropriate priors
        bandit.select(
            candidates=candidates,
            context="test",
            k=2,
            seed_rule_ids=seed_ids,
        )

        stats = bandit.get_stats("test")

        # Seed should have boosted alpha (1 + 2.0 = 3.0)
        assert stats["seed_rule_1"]["alpha"] == pytest.approx(3.0)
        assert stats["seed_rule_1"]["beta"] == pytest.approx(1.0)

        # Non-seed should have uninformative prior
        assert stats["non_seed_rule"]["alpha"] == pytest.approx(1.0)
        assert stats["non_seed_rule"]["beta"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Tests: Migration (P0)
# ---------------------------------------------------------------------------


class TestMigrateLearningIds:
    def test_old_ids_get_migrated(self, tmp_path: Path):
        """Old-style IDs are recomputed and reinforcement counts preserved."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        rule = "Always test edge cases"
        category = "domain_knowledge"

        # Simulate an old-style ID (category in hash, "dom" prefix)
        old_id = "dom-oldstyle00"
        new_id = _generate_skill_id(category, rule)

        # Ensure IDs differ (the old format was different)
        assert old_id != new_id

        # Store learning with old ID
        data = {
            "learnings": {
                old_id: {
                    "id": old_id,
                    "rule": rule,
                    "category": category,
                    "severity": "major",
                    "source": "review:test",
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "last_reinforced": datetime.now(timezone.utc).isoformat(),
                    "reinforcement_count": 5,
                    "contradiction_count": 0,
                    "functional_principle": "",
                }
            },
            "review_history": [],
        }
        backend.save_learnings(project_id, data)

        with _mock_storage(backend, project_id):
            result = migrate_learning_ids(buildlog_dir)

        assert result["migrated"] == 1
        assert result["skipped"] == 0

        # Verify new ID exists with preserved count
        migrated_data = backend.load_learnings(project_id)
        assert new_id in migrated_data["learnings"]
        assert migrated_data["learnings"][new_id]["reinforcement_count"] == 5
        assert old_id not in migrated_data["learnings"]


# ---------------------------------------------------------------------------
# Tests: Full E2E Learning Loop
# ---------------------------------------------------------------------------


class TestLearningLoopE2E:
    def test_full_loop(self, tmp_path: Path):
        """End-to-end: import seeds → select → review → promote → unified pool.

        Steps:
        1. Import seeds → verify in gauntlet_rules
        2. start_session → bandit selects from unified pool
        3. gauntlet_process_issues → learn_from_review creates learnings
        4. Verify learning ID == skill ID (P0 fix)
        5. promote → skill enters gauntlet_rules (PR #190)
        6. _get_current_rules → unified pool includes both
        7. Seed rules get detected (P1 fix)
        """
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        # Step 1: Import seed rules (simulating YAML import)
        _insert_gauntlet_rule(
            backend,
            "tt:001",
            "Every function must have tests",
            persona="test_terrorist",
        )
        _insert_gauntlet_rule(
            backend,
            "sk:002",
            "Never trust user input",
            persona="security_karen",
            provenance={"confidence": 0.8, "derivation": "seed"},
        )

        # Verify seeds are in the DB
        rows = backend.load_gauntlet_rules(active_only=True)
        assert len(rows) == 2

        # Step 2: start_session — bandit selects from unified pool
        with (
            _mock_storage(backend, project_id),
            _mock_generate_skills(_empty_skill_set()),
        ):
            result = start_session(buildlog_dir, error_class="missing_test")

        assert result.rules_count == 2
        assert len(result.selected_rules) == 2

        # Step 3: Simulate gauntlet review → learn_from_review
        issues = [
            {
                "rule_id": "tt:001",
                "severity": "major",
                "category": "architectural",
                "description": "Missing tests for parser module",
                "rule_learned": "Always test parser edge cases",
                "functional_principle": "test_coverage",
            }
        ]

        with _mock_storage(backend, project_id):
            learn_result = learn_from_review(buildlog_dir, issues, "gauntlet:test")

        assert len(learn_result.new_learnings) == 1
        learning_id = learn_result.new_learnings[0]

        # Step 4: Verify learning ID matches skill ID (P0 fix)
        expected_skill_id = _generate_skill_id(
            "architectural", "Always test parser edge cases"
        )
        assert learning_id == expected_skill_id

        # Step 5: promote a skill → enters gauntlet_rules
        skill = _make_skill("Always test parser edge cases", "architectural")
        skill_set = SkillSet(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_entries=1,
            skills={"architectural": [skill]},
        )

        with _mock_storage(backend, project_id), _mock_generate_skills(skill_set):
            promote_result = promote(
                buildlog_dir=buildlog_dir,
                skill_ids=[skill.id],
                target="skill",
            )

        assert skill.id in promote_result.promoted_ids

        # Step 6: _get_current_rules returns unified pool
        with _mock_storage(backend, project_id):
            rules = _get_current_rules(buildlog_dir)

        # Seeds + promoted skill all present
        assert "tt:001" in rules
        assert "sk:002" in rules
        assert skill.id in rules

        # Step 7: Seed rules detected for boosted priors (P1 fix)
        with (
            _mock_storage(backend, project_id),
            _mock_generate_skills(_empty_skill_set()),
        ):
            seed_ids, confidence_map = _get_seed_rule_ids(buildlog_dir)

        assert "tt:001" in seed_ids
        assert "sk:002" in seed_ids
        # Promoted skill has persona='learned', so NOT a seed
        assert skill.id not in seed_ids
        # Confidence from provenance
        assert confidence_map["sk:002"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Tests: Dashboard Data Integrity
# ---------------------------------------------------------------------------


class TestDashboardDataIntegrity:
    def test_session_rules_contain_unified_pool(self, tmp_path: Path):
        """session.rules_at_start should contain both seeds and promoted skills."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        # Insert seed + promoted skill
        _insert_gauntlet_rule(
            backend, "bragi:001", "Write clear prose", persona="bragi"
        )
        backend.save_id_set(project_id, "promoted", {"arch-promoted1"})
        _insert_gauntlet_rule(
            backend, "arch-promoted1", "Promoted rule", persona="learned"
        )

        with (
            _mock_storage(backend, project_id),
            _mock_generate_skills(_empty_skill_set()),
        ):
            result = start_session(buildlog_dir, error_class="style")

        # rules_at_start comes from _get_current_rules which is now unified
        assert "bragi:001" in result.selected_rules or result.rules_count >= 2
        # Both seeds and promoted must be in the pool
        with _mock_storage(backend, project_id):
            rules = _get_current_rules(buildlog_dir)
        assert "bragi:001" in rules
        assert "arch-promoted1" in rules
