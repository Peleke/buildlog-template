"""Comprehensive tests for DB-backed gauntlet rules.

Covers: schema v4, CRUD, generate_rule_id, import_seeds_to_db,
load_rules_from_db, load_rules (unified), content-hash IDs,
idempotent upserts, persona filtering, JSON serialization,
migration, edge cases, and round-trip fidelity.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from buildlog.seeds import (
    SeedFile,
    SeedReference,
    SeedRule,
    generate_rule_id,
    import_seeds_to_db,
    load_all_seeds,
    load_rules,
    load_rules_from_db,
)
from buildlog.storage.schema import SCHEMA_VERSION, init_schema
from buildlog.storage.sqlite import SQLiteBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backend():
    """In-memory SQLiteBackend with schema v4."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    be = SQLiteBackend(conn)
    be.ensure_project("test-proj", "Test Project", "/tmp/test")
    return be


@pytest.fixture
def conn():
    """Raw in-memory connection with schema v4 (for schema-level tests)."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_schema(c)
    return c


@pytest.fixture
def sample_rule():
    """A fully-populated rule dict ready for save_gauntlet_rules_batch."""
    return {
        "rule_id": "security_karen:abc12345",
        "persona": "security_karen",
        "rule": "Parameterize all SQL queries",
        "category": "security",
        "context": "Any code constructing SQL from user input",
        "antipattern": "String concatenation with user input in SQL",
        "rationale": "SQL injection is OWASP #1 and trivially preventable",
        "tags": ["sql", "injection", "owasp"],
        "refs": [
            {"url": "https://owasp.org/Top10/A03_2021-Injection/", "title": "OWASP A03"}
        ],
        "provenance": {
            "id": "security_karen:abc12345",
            "source_id": "q-001",
            "confidence": 0.95,
        },
        "version": 1,
        "active": True,
    }


@pytest.fixture
def sample_rules_batch():
    """A batch of 3 rules across 2 personas."""
    return [
        {
            "rule_id": "security_karen:r1",
            "persona": "security_karen",
            "rule": "Use parameterized queries",
            "category": "security",
            "context": "Database access",
            "antipattern": "String concatenation",
            "rationale": "Prevents SQL injection",
            "tags": ["sql"],
            "refs": [],
            "version": 1,
            "active": True,
        },
        {
            "rule_id": "security_karen:r2",
            "persona": "security_karen",
            "rule": "Validate all inputs",
            "category": "security",
            "context": "User input handling",
            "antipattern": "Trusting raw input",
            "rationale": "Prevents injection attacks",
            "tags": ["validation", "input"],
            "refs": [{"url": "https://example.com", "title": "Example"}],
            "version": 1,
            "active": True,
        },
        {
            "rule_id": "test_terrorist:r1",
            "persona": "test_terrorist",
            "rule": "Every public method needs a test",
            "category": "testing",
            "context": "Public API surface",
            "antipattern": "Untested public methods",
            "rationale": "Untested code is broken code",
            "tags": ["testing", "coverage"],
            "refs": [],
            "version": 1,
            "active": True,
        },
    ]


def _make_seeds_dir(tmp_path: Path, personas: dict[str, list[dict]]) -> Path:
    """Helper: create a seeds directory with YAML files."""
    seeds_dir = tmp_path / ".buildlog" / "seeds"
    seeds_dir.mkdir(parents=True)
    for persona, rules in personas.items():
        data = {"persona": persona, "version": 1, "rules": rules}
        (seeds_dir / f"{persona}.yaml").write_text(yaml.dump(data))
    return seeds_dir


# ===========================================================================
# Schema v4
# ===========================================================================


class TestSchemaV4:
    """Tests for the gauntlet_rules table schema."""

    def test_schema_version_is_4(self):
        assert SCHEMA_VERSION == 4

    def test_init_schema_returns_4(self, conn):
        # init_schema already ran in fixture; verify version
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == 4

    def test_gauntlet_rules_table_exists(self, conn):
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "gauntlet_rules" in tables

    def test_gauntlet_rules_columns(self, conn):
        info = conn.execute("PRAGMA table_info(gauntlet_rules)").fetchall()
        col_names = {r[1] for r in info}
        expected = {
            "rule_id",
            "persona",
            "rule",
            "category",
            "context",
            "antipattern",
            "rationale",
            "tags",
            "refs",
            "provenance",
            "version",
            "active",
            "created_at",
            "updated_at",
            "seed_file_hash",
            "seed_filename",
        }
        assert expected == col_names

    def test_rule_id_is_primary_key(self, conn):
        info = conn.execute("PRAGMA table_info(gauntlet_rules)").fetchall()
        pk_cols = [r[1] for r in info if r[5] == 1]  # pk flag
        assert pk_cols == ["rule_id"]

    def test_indices_exist(self, conn):
        indices = [
            r[1]
            for r in conn.execute(
                "SELECT * FROM sqlite_master WHERE type='index' "
                "AND tbl_name='gauntlet_rules'"
            ).fetchall()
        ]
        assert "idx_gauntlet_rules_persona" in indices
        assert "idx_gauntlet_rules_active" in indices

    def test_v3_to_v4_migration(self):
        """Simulate a v3 DB and upgrade to v4."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # Create a minimal v3 schema (just schema_version + a v3 table)
        conn.executescript(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            INSERT INTO schema_version (version) VALUES (3);
            CREATE TABLE projects (
                project_id TEXT PRIMARY KEY,
                name TEXT, path TEXT,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE skill_decisions (
                project_id TEXT, collection TEXT, skill_id TEXT, metadata TEXT,
                PRIMARY KEY (project_id, collection, skill_id)
            );
            CREATE TABLE review_learnings (
                project_id TEXT PRIMARY KEY, data TEXT
            );
            CREATE TABLE review_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT, timestamp TEXT, source TEXT, data TEXT
            );
            CREATE TABLE active_sessions (
                project_id TEXT PRIMARY KEY, data TEXT
            );
            CREATE TABLE reward_events (
                id TEXT, project_id TEXT, timestamp TEXT, outcome TEXT,
                reward_value REAL, data TEXT, session_id TEXT,
                PRIMARY KEY (project_id, id)
            );
            CREATE TABLE sessions (
                id TEXT, project_id TEXT, started_at TEXT, ended_at TEXT,
                data TEXT, PRIMARY KEY (project_id, id)
            );
            CREATE TABLE mistakes (
                id TEXT, project_id TEXT, session_id TEXT, timestamp TEXT,
                error_class TEXT, description TEXT, semantic_hash TEXT,
                was_repeat INTEGER, data TEXT, context TEXT, remediation TEXT,
                PRIMARY KEY (project_id, id)
            );
            CREATE TABLE bandit_arms (
                project_id TEXT, context TEXT, rule_id TEXT,
                alpha REAL, beta REAL, is_seed INTEGER, updated_at TEXT,
                PRIMARY KEY (project_id, context, rule_id)
            );
            """
        )

        # Verify we start at v3
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == 3

        # Run init_schema — should migrate to v4
        v = init_schema(conn)
        assert v == 4

        # gauntlet_rules should now exist
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "gauntlet_rules" in tables

        # Version should be 4
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == 4

    def test_fresh_db_gets_v4(self):
        """A brand-new DB should land on v4 directly."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        v = init_schema(conn)
        assert v == 4

    def test_migration_is_idempotent(self, conn):
        """Running init_schema again should be a no-op."""
        v1 = init_schema(conn)
        v2 = init_schema(conn)
        assert v1 == v2 == 4


# ===========================================================================
# CRUD Operations on SQLiteBackend
# ===========================================================================


class TestSaveGauntletRulesBatch:
    """Tests for save_gauntlet_rules_batch."""

    def test_save_single_rule(self, backend, sample_rule):
        count = backend.save_gauntlet_rules_batch([sample_rule])
        assert count == 1

    def test_save_batch(self, backend, sample_rules_batch):
        count = backend.save_gauntlet_rules_batch(sample_rules_batch)
        assert count == 3

    def test_save_with_seed_metadata(self, backend, sample_rule):
        count = backend.save_gauntlet_rules_batch(
            [sample_rule],
            seed_file_hash="abc123hash",
            seed_filename="security_karen.yaml",
        )
        assert count == 1
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["seed_file_hash"] == "abc123hash"
        assert loaded["seed_filename"] == "security_karen.yaml"

    def test_upsert_updates_existing(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])

        # Update the rule text
        updated = dict(sample_rule)
        updated["rule"] = "Always use parameterized queries (v2)"
        backend.save_gauntlet_rules_batch([updated])

        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["rule"] == "Always use parameterized queries (v2)"
        assert backend.count_gauntlet_rules() == 1  # No duplicates

    def test_upsert_preserves_created_at(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        original = backend.get_gauntlet_rule(sample_rule["rule_id"])
        created_at_1 = original["created_at"]

        # Upsert again
        updated = dict(sample_rule)
        updated["rule"] = "Updated rule"
        backend.save_gauntlet_rules_batch([updated])

        reloaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        # created_at should NOT change on upsert (it's not in the DO UPDATE SET)
        assert reloaded["created_at"] == created_at_1

    def test_save_empty_batch(self, backend):
        count = backend.save_gauntlet_rules_batch([])
        assert count == 0

    def test_json_serialization_tags(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert isinstance(loaded["tags"], list)
        assert loaded["tags"] == ["sql", "injection", "owasp"]

    def test_json_serialization_refs(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert isinstance(loaded["refs"], list)
        assert loaded["refs"][0]["url"] == "https://owasp.org/Top10/A03_2021-Injection/"

    def test_json_serialization_provenance(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert isinstance(loaded["provenance"], dict)
        assert loaded["provenance"]["confidence"] == 0.95

    def test_provenance_none_stored_as_null(self, backend):
        rule = {
            "rule_id": "test:r1",
            "persona": "test",
            "rule": "No provenance",
            "category": "general",
        }
        backend.save_gauntlet_rules_batch([rule])
        loaded = backend.get_gauntlet_rule("test:r1")
        assert loaded["provenance"] is None


class TestLoadGauntletRules:
    """Tests for load_gauntlet_rules."""

    def test_load_empty(self, backend):
        rules = backend.load_gauntlet_rules()
        assert rules == []

    def test_load_all(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        rules = backend.load_gauntlet_rules()
        assert len(rules) == 3

    def test_load_by_persona(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)

        karen = backend.load_gauntlet_rules(persona="security_karen")
        assert len(karen) == 2
        assert all(r["persona"] == "security_karen" for r in karen)

        terrorist = backend.load_gauntlet_rules(persona="test_terrorist")
        assert len(terrorist) == 1
        assert terrorist[0]["persona"] == "test_terrorist"

    def test_load_nonexistent_persona(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        rules = backend.load_gauntlet_rules(persona="nonexistent")
        assert rules == []

    def test_load_active_only_default(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        # Deactivate one
        backend.deactivate_gauntlet_rule("security_karen:r1")

        # Default: active_only=True
        rules = backend.load_gauntlet_rules()
        assert len(rules) == 2

    def test_load_all_including_inactive(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        backend.deactivate_gauntlet_rule("security_karen:r1")

        rules = backend.load_gauntlet_rules(active_only=False)
        assert len(rules) == 3

    def test_load_order_is_persona_then_rowid(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        rules = backend.load_gauntlet_rules()
        personas = [r["persona"] for r in rules]
        # security_karen rules should come before test_terrorist
        assert personas == ["security_karen", "security_karen", "test_terrorist"]

    def test_active_field_is_bool(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        rules = backend.load_gauntlet_rules()
        for r in rules:
            assert isinstance(r["active"], bool)
            assert r["active"] is True


class TestGetGauntletRule:
    """Tests for get_gauntlet_rule."""

    def test_get_existing(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded is not None
        assert loaded["rule_id"] == sample_rule["rule_id"]
        assert loaded["rule"] == sample_rule["rule"]

    def test_get_nonexistent(self, backend):
        loaded = backend.get_gauntlet_rule("nonexistent:rule")
        assert loaded is None

    def test_get_returns_all_fields(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        expected_keys = {
            "rule_id",
            "persona",
            "rule",
            "category",
            "context",
            "antipattern",
            "rationale",
            "tags",
            "refs",
            "provenance",
            "version",
            "active",
            "created_at",
            "updated_at",
            "seed_file_hash",
            "seed_filename",
        }
        assert expected_keys == set(loaded.keys())


class TestUpdateGauntletRule:
    """Tests for update_gauntlet_rule."""

    def test_update_rule_text(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        result = backend.update_gauntlet_rule(
            sample_rule["rule_id"], rule="Updated rule text"
        )
        assert result is True
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["rule"] == "Updated rule text"

    def test_update_category(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        backend.update_gauntlet_rule(sample_rule["rule_id"], category="architectural")
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["category"] == "architectural"

    def test_update_tags_list(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        backend.update_gauntlet_rule(
            sample_rule["rule_id"], tags=["new-tag-1", "new-tag-2"]
        )
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["tags"] == ["new-tag-1", "new-tag-2"]

    def test_update_provenance_dict(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        new_prov = {"source_id": "q-999", "confidence": 0.5}
        backend.update_gauntlet_rule(sample_rule["rule_id"], provenance=new_prov)
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["provenance"]["source_id"] == "q-999"

    def test_update_sets_updated_at(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        original = backend.get_gauntlet_rule(sample_rule["rule_id"])

        backend.update_gauntlet_rule(sample_rule["rule_id"], rule="Updated")
        updated = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert updated["updated_at"] >= original["updated_at"]

    def test_update_nonexistent_returns_false(self, backend):
        result = backend.update_gauntlet_rule("nonexistent:rule", rule="Updated")
        assert result is False

    def test_update_rejects_unsafe_columns(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        # "persona" and "created_at" are NOT in the whitelist
        result = backend.update_gauntlet_rule(
            sample_rule["rule_id"], persona="evil_persona"
        )
        assert result is False  # No safe fields → returns False

    def test_update_ignores_unsafe_keeps_safe(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        # Mix of safe (rule) and unsafe (created_at)
        result = backend.update_gauntlet_rule(
            sample_rule["rule_id"],
            rule="Safe update",
            created_at="1999-01-01",  # unsafe, ignored
        )
        assert result is True
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["rule"] == "Safe update"
        assert loaded["created_at"] != "1999-01-01"  # Unchanged

    def test_update_multiple_fields(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        backend.update_gauntlet_rule(
            sample_rule["rule_id"],
            rule="New rule",
            category="testing",
            rationale="New rationale",
        )
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["rule"] == "New rule"
        assert loaded["category"] == "testing"
        assert loaded["rationale"] == "New rationale"


class TestDeactivateGauntletRule:
    """Tests for deactivate_gauntlet_rule (soft-delete)."""

    def test_deactivate(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        result = backend.deactivate_gauntlet_rule(sample_rule["rule_id"])
        assert result is True

        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["active"] is False

    def test_deactivate_hides_from_active_load(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        backend.deactivate_gauntlet_rule(sample_rule["rule_id"])

        # active_only=True (default) should not see it
        rules = backend.load_gauntlet_rules()
        assert len(rules) == 0

        # active_only=False should still see it
        rules = backend.load_gauntlet_rules(active_only=False)
        assert len(rules) == 1

    def test_deactivate_nonexistent(self, backend):
        result = backend.deactivate_gauntlet_rule("nonexistent:rule")
        assert result is False

    def test_reactivate_via_update(self, backend, sample_rule):
        backend.save_gauntlet_rules_batch([sample_rule])
        backend.deactivate_gauntlet_rule(sample_rule["rule_id"])

        # Re-activate
        backend.update_gauntlet_rule(sample_rule["rule_id"], active=1)
        loaded = backend.get_gauntlet_rule(sample_rule["rule_id"])
        assert loaded["active"] is True


class TestCountGauntletRules:
    """Tests for count_gauntlet_rules."""

    def test_count_empty(self, backend):
        assert backend.count_gauntlet_rules() == 0

    def test_count_all(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        assert backend.count_gauntlet_rules() == 3

    def test_count_by_persona(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        assert backend.count_gauntlet_rules(persona="security_karen") == 2
        assert backend.count_gauntlet_rules(persona="test_terrorist") == 1
        assert backend.count_gauntlet_rules(persona="nonexistent") == 0

    def test_count_active_only(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        backend.deactivate_gauntlet_rule("security_karen:r1")

        assert backend.count_gauntlet_rules(active_only=True) == 2
        assert backend.count_gauntlet_rules(active_only=False) == 3

    def test_count_persona_and_active(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        backend.deactivate_gauntlet_rule("security_karen:r1")

        assert (
            backend.count_gauntlet_rules(persona="security_karen", active_only=True)
            == 1
        )
        assert (
            backend.count_gauntlet_rules(persona="security_karen", active_only=False)
            == 2
        )


# ===========================================================================
# generate_rule_id
# ===========================================================================


class TestGenerateRuleId:
    """Tests for content-addressable rule IDs."""

    def test_format(self):
        rid = generate_rule_id("security_karen", "Parameterize SQL")
        assert rid.startswith("security_karen:")
        # 8 hex chars after colon
        suffix = rid.split(":")[1]
        assert len(suffix) == 8
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_deterministic(self):
        """Same input always yields same ID."""
        r1 = generate_rule_id("persona", "rule text")
        r2 = generate_rule_id("persona", "rule text")
        assert r1 == r2

    def test_different_text_different_id(self):
        r1 = generate_rule_id("persona", "rule A")
        r2 = generate_rule_id("persona", "rule B")
        assert r1 != r2

    def test_different_persona_different_id(self):
        r1 = generate_rule_id("persona_a", "same rule")
        r2 = generate_rule_id("persona_b", "same rule")
        assert r1 != r2

    def test_consistent_with_manual_sha256(self):
        text = "Parameterize SQL queries"
        expected_hash = hashlib.sha256(text.encode()).hexdigest()[:8]
        rid = generate_rule_id("karen", text)
        assert rid == f"karen:{expected_hash}"

    def test_stable_across_whitespace_variations(self):
        """ID depends on EXACT text — no normalization."""
        r1 = generate_rule_id("p", "rule text")
        r2 = generate_rule_id("p", "rule  text")
        assert r1 != r2  # Different text, different ID

    def test_unicode_support(self):
        rid = generate_rule_id("persona", "Vermeiden Sie SQL-Injection")
        assert ":" in rid

    def test_empty_text(self):
        rid = generate_rule_id("persona", "")
        # Empty string still hashes deterministically
        expected = hashlib.sha256(b"").hexdigest()[:8]
        assert rid == f"persona:{expected}"


# ===========================================================================
# import_seeds_to_db
# ===========================================================================


class TestImportSeedsToDb:
    """Tests for bulk-importing YAML seeds into the DB."""

    def test_import_single_persona(self, backend, tmp_path):
        seeds_dir = _make_seeds_dir(
            tmp_path,
            {
                "test_persona": [
                    {
                        "rule": "Always test",
                        "category": "testing",
                        "context": "All code",
                        "antipattern": "No tests",
                        "rationale": "Testing is essential",
                    }
                ]
            },
        )

        result = import_seeds_to_db(backend, seeds_dir=seeds_dir)
        assert result == {"test_persona": 1}
        assert backend.count_gauntlet_rules() == 1

    def test_import_multiple_personas(self, backend, tmp_path):
        seeds_dir = _make_seeds_dir(
            tmp_path,
            {
                "karen": [{"rule": "SQL safety"}, {"rule": "XSS prevention"}],
                "bragi": [{"rule": "Document everything"}],
            },
        )

        result = import_seeds_to_db(backend, seeds_dir=seeds_dir)
        assert result == {"karen": 2, "bragi": 1}
        assert backend.count_gauntlet_rules() == 3

    def test_import_idempotent(self, backend, tmp_path):
        """Importing twice should not duplicate rules."""
        seeds_dir = _make_seeds_dir(
            tmp_path, {"persona": [{"rule": "Test rule"}, {"rule": "Another rule"}]}
        )

        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        assert backend.count_gauntlet_rules() == 2  # Not 4

    def test_import_sets_content_hash_id(self, backend, tmp_path):
        seeds_dir = _make_seeds_dir(tmp_path, {"persona": [{"rule": "Hash me"}]})

        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        rules = backend.load_gauntlet_rules()
        assert len(rules) == 1

        rid = rules[0]["rule_id"]
        expected = generate_rule_id("persona", "Hash me")
        assert rid == expected

    def test_import_sets_provenance_id(self, backend, tmp_path):
        seeds_dir = _make_seeds_dir(
            tmp_path, {"persona": [{"rule": "Provenance test"}]}
        )

        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        rules = backend.load_gauntlet_rules()
        prov = rules[0]["provenance"]
        assert prov is not None
        assert prov["id"] == rules[0]["rule_id"]

    def test_import_sets_seed_file_hash(self, backend, tmp_path):
        seeds_dir = _make_seeds_dir(tmp_path, {"persona": [{"rule": "Hash test"}]})

        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        rules = backend.load_gauntlet_rules()
        assert rules[0]["seed_file_hash"] is not None
        # Should be a SHA256 hex digest
        assert len(rules[0]["seed_file_hash"]) == 64

    def test_import_sets_seed_filename(self, backend, tmp_path):
        seeds_dir = _make_seeds_dir(
            tmp_path, {"my_persona": [{"rule": "Filename test"}]}
        )

        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        rules = backend.load_gauntlet_rules()
        assert rules[0]["seed_filename"] == "my_persona.yaml"

    def test_import_no_seeds_dir(self, backend, tmp_path, monkeypatch):
        """import_seeds_to_db with no seeds dir returns empty."""
        monkeypatch.chdir(tmp_path)  # No .buildlog/seeds here
        # Need to also patch get_package_seeds_dir to return None for isolation
        from unittest.mock import patch

        with patch("buildlog.seeds.get_default_seeds_dir", return_value=None):
            result = import_seeds_to_db(backend, seeds_dir=None)
            assert result == {}

    def test_import_preserves_references(self, backend, tmp_path):
        seeds_dir = _make_seeds_dir(
            tmp_path,
            {
                "persona": [
                    {
                        "rule": "Rule with refs",
                        "references": [
                            {"url": "https://example.com", "title": "Example"}
                        ],
                    }
                ]
            },
        )

        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        rules = backend.load_gauntlet_rules()
        assert rules[0]["refs"] == [{"url": "https://example.com", "title": "Example"}]

    def test_import_preserves_existing_provenance(self, backend, tmp_path):
        seeds_dir = _make_seeds_dir(
            tmp_path,
            {
                "persona": [
                    {
                        "rule": "Rule with provenance",
                        "provenance": {
                            "source_id": "q-42",
                            "confidence": 0.8,
                            "graph_version": "v2",
                        },
                    }
                ]
            },
        )

        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        rules = backend.load_gauntlet_rules()
        prov = rules[0]["provenance"]
        assert prov["source_id"] == "q-42"
        assert prov["confidence"] == 0.8
        assert prov["id"] == rules[0]["rule_id"]  # ID injected


# ===========================================================================
# load_rules_from_db
# ===========================================================================


class TestLoadRulesFromDb:
    """Tests for loading rules from DB as SeedFile dicts."""

    def test_load_empty_db(self, backend):
        result = load_rules_from_db(backend)
        assert result == {}

    def test_load_returns_seedfile_dict(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        result = load_rules_from_db(backend)

        assert isinstance(result, dict)
        assert "security_karen" in result
        assert "test_terrorist" in result
        assert isinstance(result["security_karen"], SeedFile)

    def test_load_preserves_persona(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        result = load_rules_from_db(backend)
        assert result["security_karen"].persona == "security_karen"
        assert result["test_terrorist"].persona == "test_terrorist"

    def test_load_preserves_rules(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        result = load_rules_from_db(backend)
        assert len(result["security_karen"].rules) == 2
        assert len(result["test_terrorist"].rules) == 1

    def test_load_preserves_rule_text(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        result = load_rules_from_db(backend)
        rule_texts = {r.rule for r in result["security_karen"].rules}
        assert "Use parameterized queries" in rule_texts
        assert "Validate all inputs" in rule_texts

    def test_load_preserves_references(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        result = load_rules_from_db(backend)
        # security_karen:r2 has a reference
        r2 = [r for r in result["security_karen"].rules if "Validate" in r.rule][0]
        assert len(r2.references) == 1
        assert r2.references[0].url == "https://example.com"
        assert isinstance(r2.references[0], SeedReference)

    def test_load_injects_provenance_id(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        result = load_rules_from_db(backend)
        for sf in result.values():
            for rule in sf.rules:
                assert rule.provenance is not None
                assert "id" in rule.provenance

    def test_load_persona_filter(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        result = load_rules_from_db(backend, persona="test_terrorist")
        assert list(result.keys()) == ["test_terrorist"]

    def test_load_skips_inactive(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        backend.deactivate_gauntlet_rule("security_karen:r1")

        result = load_rules_from_db(backend)
        karen_rules = result.get("security_karen")
        assert karen_rules is not None
        assert len(karen_rules.rules) == 1  # Only the active one


# ===========================================================================
# load_rules (unified entry point)
# ===========================================================================


class TestLoadRulesUnified:
    """Tests for the unified load_rules() entry point."""

    def test_legacy_mode_no_backend(self, tmp_path):
        """Without backend, falls back to YAML."""
        seeds_dir = _make_seeds_dir(tmp_path, {"legacy": [{"rule": "Legacy rule"}]})
        result = load_rules(backend=None, seeds_dir=seeds_dir)
        assert "legacy" in result
        assert len(result["legacy"].rules) == 1

    def test_legacy_mode_persona_filter(self, tmp_path):
        seeds_dir = _make_seeds_dir(
            tmp_path,
            {
                "a": [{"rule": "Rule A"}],
                "b": [{"rule": "Rule B"}],
            },
        )
        result = load_rules(backend=None, seeds_dir=seeds_dir, persona="a")
        assert "a" in result
        assert "b" not in result

    def test_db_mode_returns_from_db(self, backend, sample_rules_batch):
        backend.save_gauntlet_rules_batch(sample_rules_batch)
        result = load_rules(backend=backend)
        assert "security_karen" in result
        assert len(result["security_karen"].rules) == 2

    def test_auto_import_on_empty_db(self, backend, tmp_path):
        """If DB is empty, load_rules should auto-import from YAML."""
        seeds_dir = _make_seeds_dir(
            tmp_path, {"auto_imported": [{"rule": "Auto rule"}]}
        )

        # DB starts empty
        assert backend.count_gauntlet_rules() == 0

        result = load_rules(backend=backend, seeds_dir=seeds_dir)
        assert "auto_imported" in result
        assert len(result["auto_imported"].rules) == 1

        # DB should now have the rules
        assert backend.count_gauntlet_rules() == 1

    def test_no_backend_no_seeds_returns_empty(self, tmp_path, monkeypatch):
        """No backend + no seeds = empty dict."""
        monkeypatch.chdir(tmp_path)
        from unittest.mock import patch

        with patch("buildlog.seeds.get_default_seeds_dir", return_value=None):
            result = load_rules(backend=None)
            assert result == {}

    def test_db_preferred_over_yaml(self, backend, tmp_path):
        """If DB has rules, YAML is NOT consulted."""
        seeds_dir = _make_seeds_dir(tmp_path, {"yaml_persona": [{"rule": "From YAML"}]})

        # Manually insert a different rule into DB
        backend.save_gauntlet_rules_batch(
            [
                {
                    "rule_id": "db_persona:r1",
                    "persona": "db_persona",
                    "rule": "From DB",
                    "category": "testing",
                }
            ]
        )

        result = load_rules(backend=backend, seeds_dir=seeds_dir)
        # Should see DB persona, NOT yaml persona
        assert "db_persona" in result
        assert "yaml_persona" not in result


# ===========================================================================
# Round-trip fidelity: YAML → DB → SeedFile
# ===========================================================================


class TestRoundTrip:
    """Verify data integrity across the full YAML → import → load → SeedFile cycle."""

    def test_full_round_trip(self, backend, tmp_path):
        """A rule should survive the full round-trip with all fields intact."""
        rules = [
            {
                "rule": "Parameterize all SQL queries",
                "category": "security",
                "context": "Any code constructing SQL from user input",
                "antipattern": "String concatenation with user input",
                "rationale": "SQL injection is OWASP #1",
                "tags": ["sql", "injection", "owasp"],
                "references": [
                    {"url": "https://owasp.org/A03", "title": "OWASP Injection"}
                ],
                "provenance": {
                    "source_id": "q-001",
                    "confidence": 0.95,
                    "graph_version": "v3",
                },
            }
        ]
        seeds_dir = _make_seeds_dir(tmp_path, {"security_karen": rules})

        # Import → load
        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        result = load_rules_from_db(backend)

        sf = result["security_karen"]
        assert sf.persona == "security_karen"
        assert len(sf.rules) == 1

        r = sf.rules[0]
        assert r.rule == "Parameterize all SQL queries"
        assert r.category == "security"
        assert r.context == "Any code constructing SQL from user input"
        assert r.antipattern == "String concatenation with user input"
        assert r.rationale == "SQL injection is OWASP #1"
        assert r.tags == ["sql", "injection", "owasp"]
        assert len(r.references) == 1
        assert r.references[0].url == "https://owasp.org/A03"
        assert r.references[0].title == "OWASP Injection"
        assert r.provenance["source_id"] == "q-001"
        assert r.provenance["confidence"] == 0.95
        assert r.provenance["graph_version"] == "v3"
        # Content-hash ID should be injected
        assert r.provenance["id"] == generate_rule_id(
            "security_karen", "Parameterize all SQL queries"
        )

    def test_round_trip_matches_yaml_load(self, backend, tmp_path):
        """DB-loaded rules should match YAML-loaded rules in structure."""
        rules = [
            {
                "rule": "Test rule A",
                "category": "testing",
                "context": "Context A",
                "antipattern": "Anti A",
                "rationale": "Why A",
            },
            {
                "rule": "Test rule B",
                "category": "security",
                "context": "Context B",
                "antipattern": "Anti B",
                "rationale": "Why B",
                "tags": ["b-tag"],
            },
        ]
        seeds_dir = _make_seeds_dir(tmp_path, {"test_persona": rules})

        # Load from YAML directly
        yaml_result = load_all_seeds(seeds_dir)

        # Load via DB
        import_seeds_to_db(backend, seeds_dir=seeds_dir)
        db_result = load_rules_from_db(backend)

        # Same personas
        assert set(yaml_result.keys()) == set(db_result.keys())

        # Same number of rules
        assert len(yaml_result["test_persona"].rules) == len(
            db_result["test_persona"].rules
        )

        # Same rule texts
        yaml_texts = {r.rule for r in yaml_result["test_persona"].rules}
        db_texts = {r.rule for r in db_result["test_persona"].rules}
        assert yaml_texts == db_texts

    def test_round_trip_with_real_seeds(self, backend):
        """Import the actual bundled seeds and verify round-trip."""
        from buildlog.seeds import get_package_seeds_dir

        seeds_dir = get_package_seeds_dir()
        if seeds_dir is None:
            pytest.skip("No package seeds found")

        # Import real seeds
        result = import_seeds_to_db(backend, seeds_dir=seeds_dir)
        assert len(result) > 0

        # Load back
        db_seeds = load_rules_from_db(backend)
        assert len(db_seeds) > 0

        # Every persona that was imported should be loadable
        for persona in result:
            assert persona in db_seeds
            assert len(db_seeds[persona].rules) == result[persona]

        # Verify rule IDs are content-addressable
        for persona, sf in db_seeds.items():
            for rule in sf.rules:
                expected_id = generate_rule_id(persona, rule.rule)
                assert rule.provenance["id"] == expected_id


# ===========================================================================
# Edge Cases & Error Handling
# ===========================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_rule_with_empty_tags(self, backend):
        rule = {
            "rule_id": "test:empty-tags",
            "persona": "test",
            "rule": "Empty tags",
            "category": "general",
            "tags": [],
        }
        backend.save_gauntlet_rules_batch([rule])
        loaded = backend.get_gauntlet_rule("test:empty-tags")
        assert loaded["tags"] == []

    def test_rule_with_empty_refs(self, backend):
        rule = {
            "rule_id": "test:empty-refs",
            "persona": "test",
            "rule": "Empty refs",
            "category": "general",
            "refs": [],
        }
        backend.save_gauntlet_rules_batch([rule])
        loaded = backend.get_gauntlet_rule("test:empty-refs")
        assert loaded["refs"] == []

    def test_rule_with_long_text(self, backend):
        long_text = "A" * 10000
        rule = {
            "rule_id": generate_rule_id("test", long_text),
            "persona": "test",
            "rule": long_text,
            "category": "general",
        }
        backend.save_gauntlet_rules_batch([rule])
        loaded = backend.get_gauntlet_rule(rule["rule_id"])
        assert loaded["rule"] == long_text

    def test_rule_with_special_characters(self, backend):
        text = "Don't use `eval()` — it's dangerous! 🔥"
        rule = {
            "rule_id": generate_rule_id("test", text),
            "persona": "test",
            "rule": text,
            "category": "general",
        }
        backend.save_gauntlet_rules_batch([rule])
        loaded = backend.get_gauntlet_rule(rule["rule_id"])
        assert loaded["rule"] == text

    def test_rule_with_sql_injection_attempt(self, backend):
        """SQL injection in rule text should be safely stored."""
        text = "'; DROP TABLE gauntlet_rules; --"
        rule = {
            "rule_id": generate_rule_id("test", text),
            "persona": "test",
            "rule": text,
            "category": "general",
        }
        backend.save_gauntlet_rules_batch([rule])
        # Table should still exist
        loaded = backend.get_gauntlet_rule(rule["rule_id"])
        assert loaded["rule"] == text
        assert backend.count_gauntlet_rules() == 1

    def test_minimal_rule_defaults(self, backend):
        """A rule with only required fields should get proper defaults."""
        rule = {
            "rule_id": "test:minimal",
            "persona": "test",
            "rule": "Minimal rule",
            "category": "general",
        }
        backend.save_gauntlet_rules_batch([rule])
        loaded = backend.get_gauntlet_rule("test:minimal")

        assert loaded["context"] == ""
        assert loaded["antipattern"] == ""
        assert loaded["rationale"] == ""
        assert loaded["tags"] == []
        assert loaded["refs"] == []
        assert loaded["active"] is True
        assert loaded["version"] == 1
        assert loaded["created_at"] is not None
        assert loaded["updated_at"] is not None

    def test_concurrent_persona_operations(self, backend):
        """Operations on different personas should not interfere."""
        # Save rules for persona A
        backend.save_gauntlet_rules_batch(
            [{"rule_id": "a:r1", "persona": "a", "rule": "Rule A", "category": "x"}]
        )
        # Save rules for persona B
        backend.save_gauntlet_rules_batch(
            [{"rule_id": "b:r1", "persona": "b", "rule": "Rule B", "category": "y"}]
        )

        # Deactivate A
        backend.deactivate_gauntlet_rule("a:r1")

        # B should be unaffected
        b_rules = backend.load_gauntlet_rules(persona="b")
        assert len(b_rules) == 1
        assert b_rules[0]["active"] is True

    def test_large_batch(self, backend):
        """Import a large batch of rules."""
        batch = [
            {
                "rule_id": f"perf:r{i}",
                "persona": "performance",
                "rule": f"Performance rule {i}",
                "category": "performance",
                "tags": [f"tag{i}"],
            }
            for i in range(200)
        ]
        count = backend.save_gauntlet_rules_batch(batch)
        assert count == 200
        assert backend.count_gauntlet_rules() == 200
        assert backend.count_gauntlet_rules(persona="performance") == 200
