"""Tests for seed rule loading and conversion."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from buildlog.seeds import (
    ImportSeedResult,
    SeedFile,
    SeedReference,
    SeedRule,
    get_default_seeds_dir,
    get_package_seeds_dir,
    get_rules_for_persona,
    import_seed_file,
    load_all_seeds,
    load_seed_file,
    seeds_to_skills,
)
from buildlog.skills import Skill


class TestPackageSeeds:
    """Tests for bundled package seeds."""

    def test_get_package_seeds_dir_returns_path(self):
        """Should return path to bundled seeds."""
        seeds_dir = get_package_seeds_dir()
        # Should find the package seeds
        assert seeds_dir is not None
        assert seeds_dir.exists()
        assert (seeds_dir / "security_karen.yaml").exists()
        assert (seeds_dir / "test_terrorist.yaml").exists()

    def test_get_default_seeds_dir_finds_package_seeds(self, tmp_path, monkeypatch):
        """Should fall back to package seeds when no local seeds exist."""
        # Change to a directory with no local seeds
        monkeypatch.chdir(tmp_path)

        seeds_dir = get_default_seeds_dir()
        # Should fall back to package seeds
        assert seeds_dir is not None
        assert seeds_dir.exists()

    def test_local_seeds_take_precedence(self, tmp_path, monkeypatch):
        """Local seeds should override package seeds."""
        # Create local seeds
        local_seeds = tmp_path / ".buildlog" / "seeds"
        local_seeds.mkdir(parents=True)
        (local_seeds / "custom.yaml").write_text(
            "persona: custom\nversion: 1\nrules: []"
        )

        monkeypatch.chdir(tmp_path)

        seeds_dir = get_default_seeds_dir()
        # Should find local seeds, not package (compare resolved paths)
        assert seeds_dir is not None
        assert seeds_dir.resolve() == local_seeds.resolve()


class TestSeedRule:
    """Tests for SeedRule dataclass."""

    def test_seed_rule_creation(self):
        """Test creating a SeedRule with all fields."""
        rule = SeedRule(
            rule="Parameterize all SQL queries",
            category="security",
            context="Any code constructing SQL from user input",
            antipattern="String concatenation with user input",
            rationale="SQL injection is OWASP #1",
            tags=["sql", "injection"],
            references=[
                SeedReference(
                    url="https://owasp.org/Top10/A03_2021-Injection/",
                    title="OWASP A03:2021 Injection",
                )
            ],
        )
        assert rule.rule == "Parameterize all SQL queries"
        assert rule.category == "security"
        assert "sql" in rule.tags
        assert len(rule.references) == 1

    def test_seed_rule_minimal(self):
        """Test creating a SeedRule with minimal fields."""
        rule = SeedRule(
            rule="Use HTTPS",
            category="security",
            context="Network communication",
            antipattern="HTTP connections",
            rationale="Encryption in transit",
        )
        assert rule.tags == []
        assert rule.references == []


class TestSeedRuleProvenance:
    """Tests for provenance field on SeedRule (B2)."""

    def test_seed_rule_with_provenance(self):
        """SeedRule accepts a provenance dict."""
        prov = {"source_id": "q-123", "confidence": 0.8, "graph_version": "v2"}
        rule = SeedRule(
            rule="Test rule",
            category="general",
            context="ctx",
            antipattern="anti",
            rationale="why",
            provenance=prov,
        )
        assert rule.provenance == prov
        assert rule.provenance["confidence"] == 0.8

    def test_seed_rule_without_provenance(self):
        """SeedRule defaults provenance to None."""
        rule = SeedRule(
            rule="Test rule",
            category="general",
            context="ctx",
            antipattern="anti",
            rationale="why",
        )
        assert rule.provenance is None

    def test_from_dict_parses_provenance(self):
        """from_dict should parse a valid provenance dict."""
        data = {
            "persona": "test",
            "version": 1,
            "rules": [
                {
                    "rule": "Test",
                    "provenance": {
                        "source_id": "q-1",
                        "confidence": 0.9,
                        "graph_version": "v3",
                    },
                }
            ],
        }
        sf = SeedFile.from_dict(data)
        assert sf.rules[0].provenance is not None
        assert sf.rules[0].provenance["source_id"] == "q-1"

    def test_from_dict_ignores_invalid_provenance(self):
        """from_dict should set provenance=None when value is not a dict."""
        data = {
            "persona": "test",
            "version": 1,
            "rules": [
                {
                    "rule": "Test",
                    "provenance": "not-a-dict",
                }
            ],
        }
        sf = SeedFile.from_dict(data)
        assert sf.rules[0].provenance is None

    def test_default_category_is_general(self):
        """Default category should be 'general', not 'security'."""
        data = {
            "persona": "test",
            "version": 1,
            "rules": [{"rule": "No category specified"}],
        }
        sf = SeedFile.from_dict(data)
        assert sf.rules[0].category == "general"


class TestSeedFile:
    """Tests for SeedFile parsing."""

    def test_from_dict_full(self):
        """Test parsing a complete seed file dictionary."""
        data = {
            "persona": "security_karen",
            "version": 1,
            "rules": [
                {
                    "rule": "Parameterize SQL",
                    "category": "security",
                    "context": "SQL queries",
                    "antipattern": "String concatenation",
                    "rationale": "Prevents injection",
                    "tags": ["sql"],
                    "references": [{"url": "https://owasp.org", "title": "OWASP"}],
                }
            ],
        }
        seed_file = SeedFile.from_dict(data)
        assert seed_file.persona == "security_karen"
        assert seed_file.version == 1
        assert len(seed_file.rules) == 1
        assert seed_file.rules[0].rule == "Parameterize SQL"

    def test_from_dict_minimal(self):
        """Test parsing with minimal data."""
        data = {
            "rules": [
                {
                    "rule": "Use HTTPS",
                }
            ]
        }
        seed_file = SeedFile.from_dict(data)
        assert seed_file.persona == "unknown"
        assert seed_file.version == 1
        assert len(seed_file.rules) == 1

    def test_from_dict_empty_rules(self):
        """Test parsing with no rules."""
        data = {"persona": "test", "version": 1}
        seed_file = SeedFile.from_dict(data)
        assert len(seed_file.rules) == 0


class TestLoadSeedFile:
    """Tests for load_seed_file function."""

    def test_load_valid_file(self, tmp_path: Path):
        """Test loading a valid YAML seed file."""
        seed_data = {
            "persona": "test_persona",
            "version": 2,
            "rules": [
                {
                    "rule": "Test rule",
                    "category": "testing",
                    "context": "Test context",
                    "antipattern": "Bad pattern",
                    "rationale": "Because testing",
                }
            ],
        }
        seed_path = tmp_path / "test.yaml"
        with open(seed_path, "w") as f:
            yaml.dump(seed_data, f)

        result = load_seed_file(seed_path)
        assert result is not None
        assert result.persona == "test_persona"
        assert result.version == 2
        assert len(result.rules) == 1

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Test loading a file that doesn't exist."""
        result = load_seed_file(tmp_path / "nonexistent.yaml")
        assert result is None

    def test_load_invalid_yaml(self, tmp_path: Path):
        """Test loading an invalid YAML file."""
        seed_path = tmp_path / "invalid.yaml"
        seed_path.write_text("{ invalid yaml [[")
        result = load_seed_file(seed_path)
        assert result is None


class TestLoadAllSeeds:
    """Tests for load_all_seeds function."""

    def test_load_multiple_seeds(self, tmp_path: Path):
        """Test loading multiple seed files from a directory."""
        # Create two seed files
        for persona in ["security_karen", "test_terrorist"]:
            seed_data = {
                "persona": persona,
                "version": 1,
                "rules": [{"rule": f"Rule for {persona}"}],
            }
            with open(tmp_path / f"{persona}.yaml", "w") as f:
                yaml.dump(seed_data, f)

        result = load_all_seeds(tmp_path)
        assert len(result) == 2
        assert "security_karen" in result
        assert "test_terrorist" in result

    def test_load_empty_directory(self, tmp_path: Path):
        """Test loading from an empty directory."""
        result = load_all_seeds(tmp_path)
        assert result == {}

    def test_load_nonexistent_directory(self, tmp_path: Path):
        """Test loading from a directory that doesn't exist."""
        result = load_all_seeds(tmp_path / "nonexistent")
        assert result == {}


class TestSeedsToSkills:
    """Tests for seeds_to_skills conversion."""

    def test_convert_seed_to_skill(self):
        """Test converting seed rules to Skill objects."""
        seed_file = SeedFile(
            persona="security_karen",
            version=1,
            rules=[
                SeedRule(
                    rule="Parameterize SQL queries",
                    category="security",
                    context="SQL construction",
                    antipattern="String concatenation",
                    rationale="Prevents injection",
                    tags=["sql", "injection"],
                    references=[SeedReference(url="https://owasp.org", title="OWASP")],
                )
            ],
        )

        skills = seeds_to_skills(seed_file)
        assert len(skills) == 1

        skill = skills[0]
        assert skill.rule == "Parameterize SQL queries"
        assert skill.category == "security"
        assert skill.frequency == 0  # Seeded, not learned
        assert skill.confidence == "high"  # Curated
        assert skill.confidence_score == 1.0
        assert skill.confidence_tier == "entrenched"
        assert skill.context == "SQL construction"
        assert skill.antipattern == "String concatenation"
        assert skill.rationale == "Prevents injection"
        assert "security_karen" in skill.persona_tags
        assert "sql" in skill.tags
        assert "https://owasp.org" in skill.sources

    def test_seed_skill_has_stable_id(self):
        """Test that seed skills get stable IDs."""
        seed_file = SeedFile(
            persona="test",
            version=1,
            rules=[
                SeedRule(
                    rule="Same rule text",
                    category="security",
                    context="",
                    antipattern="",
                    rationale="",
                )
            ],
        )

        skills1 = seeds_to_skills(seed_file)
        skills2 = seeds_to_skills(seed_file)

        assert skills1[0].id == skills2[0].id

    def test_seed_source_includes_provenance(self):
        """Test that seed skills include provenance in sources."""
        seed_file = SeedFile(
            persona="security_karen",
            version=3,
            rules=[
                SeedRule(
                    rule="Test",
                    category="security",
                    context="",
                    antipattern="",
                    rationale="",
                )
            ],
        )

        skills = seeds_to_skills(seed_file)
        assert "seed:security_karen:v3" in skills[0].sources


class TestProvenanceForwardedToSkill:
    """Tests for provenance forwarding from SeedRule to Skill (B3)."""

    def test_provenance_forwarded_to_skill(self):
        """Provenance on SeedRule should carry through to the Skill."""
        prov = {"source_id": "q-42", "confidence": 0.7, "graph_version": "v2"}
        seed_file = SeedFile(
            persona="test",
            version=1,
            rules=[
                SeedRule(
                    rule="Provenance rule",
                    category="general",
                    context="ctx",
                    antipattern="anti",
                    rationale="why",
                    provenance=prov,
                )
            ],
        )
        skills = seeds_to_skills(seed_file)
        assert skills[0].provenance == prov
        assert skills[0].provenance["source_id"] == "q-42"

    def test_provenance_none_when_absent(self):
        """Skill.provenance should be None when SeedRule has no provenance."""
        seed_file = SeedFile(
            persona="test",
            version=1,
            rules=[
                SeedRule(
                    rule="No provenance",
                    category="general",
                    context="ctx",
                    antipattern="anti",
                    rationale="why",
                )
            ],
        )
        skills = seeds_to_skills(seed_file)
        assert skills[0].provenance is None


class TestGetRulesForPersona:
    """Tests for persona filtering."""

    def test_filter_by_persona(self):
        """Test filtering skills by persona tag."""
        skills = [
            Skill(
                id="1",
                category="security",
                rule="Security rule",
                frequency=1,
                confidence="high",
                persona_tags=["security_karen"],
            ),
            Skill(
                id="2",
                category="testing",
                rule="Testing rule",
                frequency=1,
                confidence="high",
                persona_tags=["test_terrorist"],
            ),
            Skill(
                id="3",
                category="security",
                rule="Shared rule",
                frequency=1,
                confidence="high",
                persona_tags=["security_karen", "test_terrorist"],
            ),
        ]

        karen_rules = get_rules_for_persona(skills, "security_karen")
        assert len(karen_rules) == 2
        assert all("security_karen" in s.persona_tags for s in karen_rules)

        terrorist_rules = get_rules_for_persona(skills, "test_terrorist")
        assert len(terrorist_rules) == 2

    def test_filter_no_matches(self):
        """Test filtering when no skills match."""
        skills = [
            Skill(
                id="1",
                category="security",
                rule="Security rule",
                frequency=1,
                confidence="high",
                persona_tags=["security_karen"],
            ),
        ]

        result = get_rules_for_persona(skills, "unknown_persona")
        assert result == []


class TestSecurityKarenSeedFile:
    """Integration test for the actual Security Karen seed file."""

    def test_load_security_karen_seeds(self):
        """Test loading the real Security Karen seed file."""
        seed_path = Path(".buildlog/seeds/security_karen.yaml")
        if not seed_path.exists():
            pytest.skip("Security Karen seed file not found")

        seed_file = load_seed_file(seed_path)
        assert seed_file is not None
        assert seed_file.persona == "security_karen"
        assert len(seed_file.rules) >= 10  # Should have OWASP Top 10 coverage

        # Check that rules have required defensibility fields
        for rule in seed_file.rules:
            assert rule.rule, "Rule text is required"
            assert rule.context, f"Context missing for: {rule.rule}"
            assert rule.antipattern, f"Antipattern missing for: {rule.rule}"
            assert rule.rationale, f"Rationale missing for: {rule.rule}"

    def test_security_karen_skills_are_defensible(self):
        """Test that Security Karen skills have full defensibility metadata."""
        seed_path = Path(".buildlog/seeds/security_karen.yaml")
        if not seed_path.exists():
            pytest.skip("Security Karen seed file not found")

        seed_file = load_seed_file(seed_path)
        skills = seeds_to_skills(seed_file)

        for skill in skills:
            # Every skill must be traceable
            assert skill.context is not None, f"No context: {skill.rule}"
            assert skill.antipattern is not None, f"No antipattern: {skill.rule}"
            assert skill.rationale is not None, f"No rationale: {skill.rule}"
            assert "security_karen" in skill.persona_tags

            # Must have at least seed provenance
            assert any("seed:" in s for s in skill.sources)


class TestSkillDefensibilityFields:
    """Tests for the new defensibility fields on Skill."""

    def test_skill_to_dict_includes_defensibility(self):
        """Test that to_dict includes defensibility fields when set."""
        skill = Skill(
            id="test",
            category="security",
            rule="Test rule",
            frequency=1,
            confidence="high",
            context="When this applies",
            antipattern="What not to do",
            rationale="Why it matters",
            persona_tags=["security_karen"],
        )

        d = skill.to_dict()
        assert d["context"] == "When this applies"
        assert d["antipattern"] == "What not to do"
        assert d["rationale"] == "Why it matters"
        assert d["persona_tags"] == ["security_karen"]

    def test_skill_to_dict_omits_none_defensibility(self):
        """Test that to_dict omits defensibility fields when None."""
        skill = Skill(
            id="test",
            category="security",
            rule="Test rule",
            frequency=1,
            confidence="high",
        )

        d = skill.to_dict()
        assert "context" not in d
        assert "antipattern" not in d
        assert "rationale" not in d
        assert "persona_tags" not in d


class TestSeedSchemaValidation:
    """Tests for seed file schema validation."""

    def test_rejects_non_dict_root(self, tmp_path: Path):
        """Should reject seed files where root is not a dict."""
        seed_path = tmp_path / "bad.yaml"
        seed_path.write_text("- just\n- a\n- list")
        result = load_seed_file(seed_path)
        assert result is None

    def test_rejects_rules_not_list(self, tmp_path: Path):
        """Should reject seed files where rules is not a list."""
        seed_path = tmp_path / "bad.yaml"
        seed_path.write_text("persona: test\nrules: not_a_list")
        result = load_seed_file(seed_path)
        assert result is None

    def test_rejects_rule_without_rule_key(self, tmp_path: Path):
        """Should reject rules that don't have a 'rule' key."""
        seed_path = tmp_path / "bad.yaml"
        seed_path.write_text(
            "persona: test\nrules:\n  - category: security\n    description: no rule key"
        )
        result = load_seed_file(seed_path)
        assert result is None

    def test_accepts_valid_minimal_schema(self, tmp_path: Path):
        """Should accept minimal valid schema."""
        seed_path = tmp_path / "valid.yaml"
        seed_path.write_text("persona: test\nrules:\n  - rule: Test rule")
        result = load_seed_file(seed_path)
        assert result is not None
        assert result.persona == "test"
        assert len(result.rules) == 1

    def test_accepts_empty_rules(self, tmp_path: Path):
        """Should accept seed files with empty rules list."""
        seed_path = tmp_path / "empty.yaml"
        seed_path.write_text("persona: test\nrules: []")
        result = load_seed_file(seed_path)
        assert result is not None
        assert len(result.rules) == 0

    def test_rejects_non_dict_provenance(self, tmp_path: Path):
        """Should reject rules where provenance is not a dict."""
        seed_path = tmp_path / "bad_prov.yaml"
        seed_path.write_text(
            "persona: test\nrules:\n  - rule: Test\n    provenance: not-a-dict"
        )
        result = load_seed_file(seed_path)
        assert result is None


class TestImportSeedFile:
    """Tests for seed file import with version decay."""

    def _make_seed_yaml(
        self,
        persona: str = "test_persona",
        rules: list[dict] | None = None,
    ) -> str:
        """Helper to create seed YAML content."""
        if rules is None:
            rules = [
                {
                    "rule": "Always validate input",
                    "category": "security",
                    "context": "User input handling",
                    "antipattern": "Trusting raw input",
                    "rationale": "Prevents injection attacks",
                    "provenance": {
                        "source_id": "q-001",
                        "graph_version": "1",
                        "confidence": 0.9,
                    },
                },
                {
                    "rule": "Use parameterized queries",
                    "category": "security",
                    "context": "Database access",
                    "antipattern": "String concatenation in SQL",
                    "rationale": "SQL injection prevention",
                },
            ]
        data = {"persona": persona, "version": 1, "rules": rules}
        return yaml.dump(data)

    def test_import_valid_seed_file(self, tmp_path: Path):
        """Happy path: import a valid seed file with provenance."""
        source = tmp_path / "source" / "test_persona.yaml"
        source.parent.mkdir()
        source.write_text(self._make_seed_yaml())

        target_dir = tmp_path / "target" / "seeds"

        result = import_seed_file(
            source, target_dir=target_dir, buildlog_dir=tmp_path / "buildlog"
        )

        assert result.persona == "test_persona"
        assert result.rule_count == 2
        assert result.provenance_count == 1
        assert result.version_changed is False
        assert result.decayed_rules == 0
        assert "Imported 2 rules" in result.message
        assert "1 with provenance" in result.message
        # Target file should exist
        assert (target_dir / "test_persona.yaml").exists()

    def test_import_invalid_seed_file(self, tmp_path: Path):
        """Should raise ValueError for invalid YAML schema."""
        source = tmp_path / "bad.yaml"
        source.write_text("- just\n- a\n- list")

        with pytest.raises(ValueError, match="Invalid seed file"):
            import_seed_file(source, target_dir=tmp_path / "seeds")

    def test_import_nonexistent_source(self, tmp_path: Path):
        """Should raise FileNotFoundError for missing source."""
        source = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError, match="Seed file not found"):
            import_seed_file(source)

    def test_import_detects_version_change(self, tmp_path: Path):
        """Should detect graph_version change between old and new seed."""
        target_dir = tmp_path / "seeds"
        target_dir.mkdir()
        buildlog_dir = tmp_path / "buildlog"

        # Write "old" version at target
        old_rules = [
            {
                "rule": "Always validate input",
                "category": "security",
                "provenance": {"graph_version": "1"},
            }
        ]
        old_yaml = yaml.dump({"persona": "test", "version": 1, "rules": old_rules})
        (target_dir / "test.yaml").write_text(old_yaml)

        # Write "new" version at source with changed graph_version
        new_rules = [
            {
                "rule": "Always validate input",
                "category": "security",
                "provenance": {"graph_version": "2"},
            }
        ]
        source = tmp_path / "source" / "test.yaml"
        source.parent.mkdir()
        source.write_text(
            yaml.dump({"persona": "test", "version": 2, "rules": new_rules})
        )

        result = import_seed_file(
            source, target_dir=target_dir, buildlog_dir=buildlog_dir
        )

        assert result.version_changed is True
        assert "version changed" in result.message

    def test_import_no_version_change(self, tmp_path: Path):
        """Should not flag version change when graph_version is same."""
        target_dir = tmp_path / "seeds"
        target_dir.mkdir()
        buildlog_dir = tmp_path / "buildlog"

        rules = [
            {
                "rule": "Always validate input",
                "category": "security",
                "provenance": {"graph_version": "1"},
            }
        ]
        seed_yaml = yaml.dump({"persona": "test", "version": 1, "rules": rules})

        # Same content at both source and target
        (target_dir / "test.yaml").write_text(seed_yaml)
        source = tmp_path / "source" / "test.yaml"
        source.parent.mkdir()
        source.write_text(seed_yaml)

        result = import_seed_file(
            source, target_dir=target_dir, buildlog_dir=buildlog_dir
        )

        assert result.version_changed is False
        assert result.decayed_rules == 0

    def test_import_triggers_bandit_decay(self, tmp_path: Path):
        """Should actually decay bandit arms when version changes."""
        from buildlog.core.bandit import BetaParams, ThompsonSamplingBandit
        from buildlog.skills import _generate_skill_id

        target_dir = tmp_path / "seeds"
        target_dir.mkdir()
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()

        rule_text = "Always validate input"
        category = "security"
        skill_id = _generate_skill_id(category, rule_text)

        # Pre-populate bandit with learned signal for this rule
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.state.set_params("default", skill_id, BetaParams(alpha=5.0, beta=3.0))
        bandit.state.save(bandit_path)

        # Verify pre-decay state
        pre_params = bandit.state.get_params("default", skill_id)
        assert pre_params.alpha == 5.0

        # Old version: graph_version=1
        old_rules = [
            {
                "rule": rule_text,
                "category": category,
                "provenance": {"graph_version": "1"},
            }
        ]
        (target_dir / "test.yaml").write_text(
            yaml.dump({"persona": "test", "version": 1, "rules": old_rules})
        )

        # New version: graph_version=2
        new_rules = [
            {
                "rule": rule_text,
                "category": category,
                "provenance": {"graph_version": "2"},
            }
        ]
        source = tmp_path / "source" / "test.yaml"
        source.parent.mkdir()
        source.write_text(
            yaml.dump({"persona": "test", "version": 2, "rules": new_rules})
        )

        result = import_seed_file(
            source, target_dir=target_dir, buildlog_dir=buildlog_dir
        )

        assert result.version_changed is True
        assert result.decayed_rules == 1

        # Verify the bandit arm was actually decayed by re-loading
        bandit2 = ThompsonSamplingBandit(bandit_path)
        post_params = bandit2.state.get_params("default", skill_id)
        # new_alpha = 1.0 + (5.0 - 1.0) * 0.5 = 3.0
        assert post_params.alpha == 3.0

    def test_import_creates_target_dir(self, tmp_path: Path):
        """Should create target directory if it doesn't exist."""
        source = tmp_path / "test.yaml"
        source.write_text(
            yaml.dump(
                {
                    "persona": "test",
                    "version": 1,
                    "rules": [{"rule": "Test rule"}],
                }
            )
        )

        target_dir = tmp_path / "deep" / "nested" / "seeds"
        assert not target_dir.exists()

        result = import_seed_file(
            source, target_dir=target_dir, buildlog_dir=tmp_path / "buildlog"
        )

        assert target_dir.exists()
        assert (target_dir / "test.yaml").exists()
        assert result.rule_count == 1
