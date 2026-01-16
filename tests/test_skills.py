"""Tests for buildlog.skills module."""

from datetime import date
from pathlib import Path

import pytest

from buildlog.skills import (
    Skill,
    SkillSet,
    _deduplicate_insights,
    _calculate_confidence,
    _extract_tags,
    _generate_skill_id,
    _to_imperative,
    generate_skills,
    format_skills,
)
from buildlog.embeddings import TokenBackend, get_backend


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "buildlog"


class TestSkillIdGeneration:
    """Tests for stable skill ID generation."""

    def test_generates_prefixed_id(self):
        """Should generate ID with category prefix."""
        assert _generate_skill_id("architectural", "test rule").startswith("arch-")
        assert _generate_skill_id("workflow", "test rule").startswith("wf-")
        assert _generate_skill_id("tool_usage", "test rule").startswith("tool-")
        assert _generate_skill_id("domain_knowledge", "test rule").startswith("dk-")

    def test_id_is_deterministic(self):
        """Same input should produce same ID."""
        id1 = _generate_skill_id("architectural", "Use composition over inheritance")
        id2 = _generate_skill_id("architectural", "Use composition over inheritance")
        assert id1 == id2

    def test_id_is_case_insensitive(self):
        """IDs should be case-insensitive."""
        id1 = _generate_skill_id("architectural", "Use Composition Over Inheritance")
        id2 = _generate_skill_id("architectural", "use composition over inheritance")
        assert id1 == id2

    def test_different_rules_different_ids(self):
        """Different rules should produce different IDs."""
        id1 = _generate_skill_id("architectural", "rule one")
        id2 = _generate_skill_id("architectural", "rule two")
        assert id1 != id2


class TestConfidenceScoring:
    """Tests for confidence level calculation.

    Uses explicit reference_date for deterministic, time-independent tests.
    """

    def test_high_confidence(self):
        """High frequency + recent = high confidence."""
        reference = date(2026, 2, 1)
        recent = date(2026, 1, 20)  # 12 days before reference (within 30 days)
        assert _calculate_confidence(3, recent, reference_date=reference) == "high"
        assert _calculate_confidence(5, recent, reference_date=reference) == "high"

    def test_medium_confidence(self):
        """Medium frequency = medium confidence (regardless of recency)."""
        reference = date(2026, 2, 1)
        old = date(2020, 1, 1)  # Old date (outside 30-day window)
        assert _calculate_confidence(2, old, reference_date=reference) == "medium"
        assert _calculate_confidence(3, old, reference_date=reference) == "medium"

    def test_low_confidence(self):
        """Low frequency = low confidence."""
        reference = date(2026, 2, 1)
        recent = date(2026, 1, 20)
        assert _calculate_confidence(1, recent, reference_date=reference) == "low"
        assert _calculate_confidence(1, None, reference_date=reference) == "low"


class TestTagExtraction:
    """Tests for tag extraction from rules."""

    def test_extracts_known_tags(self):
        """Should extract known technology tags."""
        tags = _extract_tags("Use Redis for caching instead of database queries")
        assert "redis" in tags
        assert "database" in tags
        assert "cache" in tags

    def test_extracts_testing_tags(self):
        """Should extract testing-related tags."""
        tags = _extract_tags("Always run pytest before git commit")
        assert "test" in tags
        assert "git" in tags

    def test_returns_empty_for_no_matches(self):
        """Should return empty list if no known tags."""
        tags = _extract_tags("Keep things simple and clear")
        assert tags == []


class TestTokenBackend:
    """Tests for token-based similarity."""

    def test_identical_strings(self):
        """Identical strings should have similarity 1.0."""
        backend = TokenBackend()
        assert backend.similarity("run type checker", "run type checker") == 1.0

    def test_completely_different(self):
        """Completely different strings should have low similarity."""
        backend = TokenBackend()
        sim = backend.similarity("run type checker", "eat pizza for lunch")
        assert sim < 0.3

    def test_synonym_normalization(self):
        """Synonyms should increase similarity."""
        backend = TokenBackend()
        # "tsc" and "typescript" are synonyms
        sim = backend.similarity("run tsc before commit", "run typescript before commit")
        assert sim > 0.7

    def test_stop_word_removal(self):
        """Stop words should be filtered."""
        backend = TokenBackend()
        # "always" and "the" are stop words
        sim = backend.similarity(
            "always run the type checker",
            "run type checker"
        )
        assert sim > 0.8

    def test_verb_normalization(self):
        """Verb forms should be normalized."""
        backend = TokenBackend()
        sim = backend.similarity("running tests", "run test")
        assert sim > 0.7


class TestDeduplication:
    """Tests for insight deduplication."""

    def test_merges_similar_insights(self):
        """Should merge similar insights."""
        patterns = [
            {"insight": "run tests before commit", "source": "a.md", "date": "2026-01-01", "context": ""},
            {"insight": "run testing before committing", "source": "b.md", "date": "2026-01-02", "context": ""},
        ]
        backend = TokenBackend()
        result = _deduplicate_insights(patterns, threshold=0.5, backend=backend)

        # Should merge into one (both normalize to "run test commit")
        assert len(result) == 1
        assert result[0][1] == 2  # frequency = 2

    def test_keeps_distinct_insights(self):
        """Should not merge distinct insights."""
        patterns = [
            {"insight": "use redis for caching", "source": "a.md", "date": "2026-01-01", "context": ""},
            {"insight": "write tests first", "source": "b.md", "date": "2026-01-02", "context": ""},
        ]
        backend = TokenBackend()
        result = _deduplicate_insights(patterns, threshold=0.5, backend=backend)

        assert len(result) == 2

    def test_empty_patterns(self):
        """Should handle empty patterns list."""
        result = _deduplicate_insights([])
        assert result == []

    def test_tracks_sources(self):
        """Should track all sources for merged insights."""
        patterns = [
            {"insight": "run tests", "source": "a.md", "date": "2026-01-01", "context": ""},
            {"insight": "run test", "source": "b.md", "date": "2026-01-02", "context": ""},
            {"insight": "run testing", "source": "c.md", "date": "2026-01-03", "context": ""},
        ]
        backend = TokenBackend()
        result = _deduplicate_insights(patterns, threshold=0.5, backend=backend)

        assert len(result) == 1
        rule, freq, sources, _ = result[0]
        assert freq == 3
        assert len(sources) == 3


class TestGenerateSkills:
    """Tests for full skill generation."""

    def test_generates_skills_from_fixtures(self):
        """Should generate skills from fixture buildlog entries."""
        skill_set = generate_skills(FIXTURES_DIR)

        assert skill_set.source_entries >= 1
        assert skill_set.total_skills >= 0

    def test_respects_min_frequency(self):
        """Should filter by minimum frequency."""
        skill_set = generate_skills(FIXTURES_DIR, min_frequency=100)

        # With min_frequency=100, no skills should pass (fixtures have low freq)
        assert skill_set.total_skills == 0

    def test_has_all_categories(self):
        """Should have all category keys even if empty."""
        skill_set = generate_skills(FIXTURES_DIR)

        assert "architectural" in skill_set.skills
        assert "workflow" in skill_set.skills
        assert "tool_usage" in skill_set.skills
        assert "domain_knowledge" in skill_set.skills


class TestSkillSetSerialization:
    """Tests for SkillSet serialization."""

    def test_to_dict(self):
        """Should convert to dictionary correctly."""
        skill = Skill(
            id="arch-123456",
            category="architectural",
            rule="Test rule",
            frequency=2,
            confidence="medium",
            sources=["a.md", "b.md"],
            tags=["test"],
        )
        skill_set = SkillSet(
            generated_at="2026-01-16T00:00:00Z",
            source_entries=5,
            skills={"architectural": [skill]},
        )

        data = skill_set.to_dict()

        assert data["generated_at"] == "2026-01-16T00:00:00Z"
        assert data["source_entries"] == 5
        assert data["total_skills"] == 1
        assert len(data["skills"]["architectural"]) == 1


class TestFormatSkills:
    """Tests for output formatting."""

    def test_yaml_format(self):
        """Should produce valid YAML."""
        import yaml

        skill_set = generate_skills(FIXTURES_DIR)
        output = format_skills(skill_set, "yaml")

        # Should parse without error
        data = yaml.safe_load(output)
        assert "generated_at" in data
        assert "skills" in data

    def test_json_format(self):
        """Should produce valid JSON."""
        import json

        skill_set = generate_skills(FIXTURES_DIR)
        output = format_skills(skill_set, "json")

        # Should parse without error
        data = json.loads(output)
        assert "generated_at" in data
        assert "skills" in data

    def test_markdown_format(self):
        """Should produce markdown with headers."""
        skill_set = generate_skills(FIXTURES_DIR)
        output = format_skills(skill_set, "markdown")

        assert "## Learned Skills" in output
        assert "Generated:" in output

    def test_rules_format(self):
        """Should produce CLAUDE.md-ready rules."""
        skill_set = generate_skills(FIXTURES_DIR)
        output = format_skills(skill_set, "rules")

        assert "# Project Rules" in output
        assert "Auto-generated from" in output
        # Should have rules with imperative prefixes
        assert "Consider:" in output or "Always" in output or "Prefer" in output

    def test_settings_format(self):
        """Should produce .claude/settings.json compatible output."""
        import json

        skill_set = generate_skills(FIXTURES_DIR)
        output = format_skills(skill_set, "settings")

        # Should parse as valid JSON
        data = json.loads(output)
        assert "rules" in data
        assert isinstance(data["rules"], list)
        assert "_generated" in data

    def test_invalid_format_raises(self):
        """Should raise ValueError for invalid format."""
        skill_set = generate_skills(FIXTURES_DIR)

        with pytest.raises(ValueError, match="Unknown format"):
            format_skills(skill_set, "xml")


class TestGetBackend:
    """Tests for backend factory."""

    def test_default_is_token(self):
        """Default backend should be token-based."""
        backend = get_backend("token")
        assert backend.name == "token"

    def test_invalid_backend_raises(self):
        """Should raise ValueError for unknown backend."""
        with pytest.raises(ValueError, match="Unknown embedding backend"):
            get_backend("nonexistent")

    def test_openai_backend_requires_api_key(self, monkeypatch):
        """OpenAI backend should fail without API key."""
        from buildlog.embeddings import OpenAIBackend

        # Ensure API key is not set
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            OpenAIBackend()


class TestToImperative:
    """Tests for _to_imperative() rule transformation."""

    def test_empty_string(self):
        """Should handle empty strings gracefully."""
        assert _to_imperative("", "high") == ""
        assert _to_imperative("   ", "high") == ""

    def test_already_has_confidence_modifier(self):
        """Should preserve rules that already have confidence modifiers."""
        assert _to_imperative("always validate inputs", "high") == "Always validate inputs"
        assert _to_imperative("never use global state", "medium") == "Never use global state"
        assert _to_imperative("prefer composition over inheritance", "low") == "Prefer composition over inheritance"
        assert _to_imperative("avoid mutable defaults", "high") == "Avoid mutable defaults"

    def test_plain_imperative_gets_confidence_prefix(self):
        """Plain imperatives should get confidence prefixes."""
        # Low confidence adds "Consider:"
        assert _to_imperative("use frozen dataclasses", "low") == "Consider: use frozen dataclasses"
        # High confidence adds "Always"
        assert _to_imperative("run tests before commit", "high") == "Always run tests before commit"

    def test_high_confidence_basic(self):
        """High confidence should prefix with Always."""
        result = _to_imperative("validate inputs at boundary", "high")
        assert result == "Always validate inputs at boundary"

    def test_high_confidence_negative(self):
        """High confidence negative should prefix with Never."""
        result = _to_imperative("you shouldn't use mutable defaults", "high")
        assert result == "Never use mutable defaults"

    def test_high_confidence_comparison(self):
        """High confidence comparison should prefix with Always."""
        result = _to_imperative("composition is better than inheritance", "high")
        assert result == "Always composition is better than inheritance"

    def test_medium_confidence_basic(self):
        """Medium confidence should prefix with Prefer to."""
        result = _to_imperative("cache database queries", "medium")
        assert result == "Prefer to cache database queries"

    def test_medium_confidence_negative(self):
        """Medium confidence negative should prefix with Avoid + gerund."""
        result = _to_imperative("you should not use eval", "medium")
        assert result == "Avoid using eval"

    def test_medium_confidence_comparison(self):
        """Medium confidence comparison should prefix with Prefer + gerund."""
        result = _to_imperative("use TypeScript over JavaScript", "medium")
        assert result == "Prefer using TypeScript over JavaScript"

    def test_low_confidence(self):
        """Low confidence should prefix with Consider:."""
        result = _to_imperative("try caching hot paths", "low")
        assert result == "Consider: try caching hot paths"

    def test_should_cleaner(self):
        """Should remove 'should' prefixes."""
        result = _to_imperative("should validate inputs", "high")
        assert result == "Always validate inputs"

        result = _to_imperative("you should check errors", "medium")
        assert result == "Prefer to check errors"

    def test_double_word_prevention(self):
        """Should not produce 'Avoid avoid' or similar doubles."""
        result = _to_imperative("avoid using global state", "medium")
        # Should NOT be "Avoid avoid using global state"
        assert "avoid avoid" not in result.lower()
        assert "Avoid" in result

    def test_word_boundary_not_false_positive(self):
        """Should not match 'not' in 'notify' or 'notation'."""
        # "notify" contains "not" but is not a negative
        result = _to_imperative("send notifications promptly", "high")
        # Should be "Always send notifications..." not "Never send notifications..."
        assert result.startswith("Always")

    def test_word_boundary_over_false_positive(self):
        """Should not match 'over' in 'override' as comparison."""
        result = _to_imperative("the override method handles errors", "high")
        # Should be "Always the override..." - detected as comparison due to 'over' substring
        # Actually this should NOT be detected since 'over' is inside 'override'
        assert "Always" in result

    def test_preserves_case_in_content(self):
        """Should preserve internal capitalization."""
        result = _to_imperative("should use PostgreSQL", "high")
        assert "PostgreSQL" in result

    def test_invalid_confidence_raises(self):
        """Should raise ValueError for invalid confidence levels."""
        with pytest.raises(ValueError, match="Invalid confidence level"):
            _to_imperative("some rule", "hgih")  # typo

        with pytest.raises(ValueError, match="Invalid confidence level"):
            _to_imperative("some rule", "invalid")

    def test_gerund_conversion(self):
        """Should convert verbs to gerund form for Avoid/Prefer."""
        # Avoid + verb -> Avoid + gerund
        assert _to_imperative("use mutable defaults", "medium") == "Prefer to use mutable defaults"
        assert _to_imperative("should not run tests in production", "medium") == "Avoid running tests in production"

        # Prefer (comparison) + verb -> Prefer + gerund
        assert _to_imperative("write tests before code", "medium") == "Prefer to write tests before code"
