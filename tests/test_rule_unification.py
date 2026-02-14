"""Tests for rule unification: skills → gauntlet_rules on promote().

Verifies that:
1. promote() inserts skills into gauntlet_rules table
2. _get_current_rules() returns both promoted skills AND gauntlet rules
3. The unified pool is deduplicated and excludes inactive rules
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from buildlog.core.operations import _get_current_rules, promote
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
    )


def _insert_gauntlet_rule(
    backend: SQLiteBackend,
    rule_id: str,
    rule: str,
    persona: str = "test_persona",
    active: int = 1,
) -> None:
    """Insert a gauntlet rule directly."""
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
                "provenance": json.dumps({"derivation": "seed"}),
                "version": 1,
                "active": active,
            }
        ]
    )


# ---------------------------------------------------------------------------
# Tests: promote() inserts into gauntlet_rules
# ---------------------------------------------------------------------------


class TestPromoteInsertsGauntletRules:
    def test_promoted_skill_appears_in_gauntlet_rules(self, tmp_path: Path):
        """A promoted skill should be inserted into gauntlet_rules."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        skill = _make_skill("Always test edge cases", "architectural")

        # Mock generate_skills to return our skill
        skill_set = SkillSet(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_entries=1,
            skills={"architectural": [skill]},
        )

        with (
            patch("buildlog.core.operations.generate_skills", return_value=skill_set),
            patch(
                "buildlog.core.operations._get_storage",
                return_value=(backend, project_id),
            ),
        ):
            result = promote(
                buildlog_dir=buildlog_dir,
                skill_ids=[skill.id],
                target="skill",
            )

        assert skill.id in result.promoted_ids

        # Verify it's in gauntlet_rules
        rows = backend.load_gauntlet_rules(active_only=True)
        gauntlet_ids = {r["rule_id"] for r in rows}
        assert skill.id in gauntlet_ids

    def test_gauntlet_rule_has_learned_persona(self, tmp_path: Path):
        """Skills inserted into gauntlet_rules should have persona='learned'."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        skill = _make_skill("Use dependency injection", "architectural")
        skill_set = SkillSet(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_entries=1,
            skills={"architectural": [skill]},
        )

        with (
            patch("buildlog.core.operations.generate_skills", return_value=skill_set),
            patch(
                "buildlog.core.operations._get_storage",
                return_value=(backend, project_id),
            ),
        ):
            promote(buildlog_dir=buildlog_dir, skill_ids=[skill.id], target="skill")

        rows = backend.load_gauntlet_rules(persona="learned")
        assert len(rows) >= 1
        rule = next(r for r in rows if r["rule_id"] == skill.id)
        assert rule["rule"] == "Use dependency injection"
        assert rule["category"] == "architectural"

    def test_gauntlet_rule_has_provenance(self, tmp_path: Path):
        """Provenance should record skill_promotion source."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        skill = _make_skill("Keep functions pure", "workflow")
        skill_set = SkillSet(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_entries=1,
            skills={"workflow": [skill]},
        )

        with (
            patch("buildlog.core.operations.generate_skills", return_value=skill_set),
            patch(
                "buildlog.core.operations._get_storage",
                return_value=(backend, project_id),
            ),
        ):
            promote(buildlog_dir=buildlog_dir, skill_ids=[skill.id], target="skill")

        rows = backend.load_gauntlet_rules(persona="learned")
        rule = next(r for r in rows if r["rule_id"] == skill.id)
        prov = json.loads(rule["provenance"])
        assert prov["source"] == "skill_promotion"
        assert prov["skill_id"] == skill.id
        assert prov["derivation"] == "learned"

    def test_idempotent_promotion(self, tmp_path: Path):
        """Promoting same skill twice doesn't create duplicates."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        skill = _make_skill("Test all edge cases", "architectural")
        skill_set = SkillSet(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_entries=1,
            skills={"architectural": [skill]},
        )

        with (
            patch("buildlog.core.operations.generate_skills", return_value=skill_set),
            patch(
                "buildlog.core.operations._get_storage",
                return_value=(backend, project_id),
            ),
        ):
            promote(buildlog_dir=buildlog_dir, skill_ids=[skill.id], target="skill")
            promote(buildlog_dir=buildlog_dir, skill_ids=[skill.id], target="skill")

        rows = backend.load_gauntlet_rules(persona="learned")
        matching = [r for r in rows if r["rule_id"] == skill.id]
        assert len(matching) == 1  # upsert, not duplicate


# ---------------------------------------------------------------------------
# Tests: _get_current_rules() returns unified pool
# ---------------------------------------------------------------------------


class TestGetCurrentRulesUnified:
    def test_returns_promoted_skills(self, tmp_path: Path):
        """Returns promoted skill IDs."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        backend.save_id_set(project_id, "promoted", {"arch-abc", "dk-xyz"})

        with patch(
            "buildlog.core.operations._get_storage", return_value=(backend, project_id)
        ):
            rules = _get_current_rules(buildlog_dir)

        assert "arch-abc" in rules
        assert "dk-xyz" in rules

    def test_returns_gauntlet_rules(self, tmp_path: Path):
        """Returns active gauntlet rule IDs."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        _insert_gauntlet_rule(backend, "test_terrorist:abc123", "Test everything")

        with patch(
            "buildlog.core.operations._get_storage", return_value=(backend, project_id)
        ):
            rules = _get_current_rules(buildlog_dir)

        assert "test_terrorist:abc123" in rules

    def test_returns_union_of_both(self, tmp_path: Path):
        """Returns BOTH promoted skills AND gauntlet rules."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        backend.save_id_set(project_id, "promoted", {"arch-abc"})
        _insert_gauntlet_rule(backend, "test_terrorist:abc123", "Test everything")

        with patch(
            "buildlog.core.operations._get_storage", return_value=(backend, project_id)
        ):
            rules = _get_current_rules(buildlog_dir)

        assert "arch-abc" in rules
        assert "test_terrorist:abc123" in rules
        assert len(rules) >= 2

    def test_deduplication(self, tmp_path: Path):
        """If a skill ID is in both promoted and gauntlet_rules, no dupes."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        # Same ID in both places (happens after promote() unification)
        backend.save_id_set(project_id, "promoted", {"arch-abc"})
        _insert_gauntlet_rule(backend, "arch-abc", "Some rule")

        with patch(
            "buildlog.core.operations._get_storage", return_value=(backend, project_id)
        ):
            rules = _get_current_rules(buildlog_dir)

        assert rules.count("arch-abc") == 1

    def test_excludes_inactive_gauntlet_rules(self, tmp_path: Path):
        """Inactive gauntlet rules are NOT in the pool."""
        backend, project_id, buildlog_dir = _init_backend(tmp_path)

        _insert_gauntlet_rule(backend, "active:rule", "Active rule", active=1)
        _insert_gauntlet_rule(backend, "inactive:rule", "Inactive rule", active=0)

        with patch(
            "buildlog.core.operations._get_storage", return_value=(backend, project_id)
        ):
            rules = _get_current_rules(buildlog_dir)

        assert "active:rule" in rules
        assert "inactive:rule" not in rules
