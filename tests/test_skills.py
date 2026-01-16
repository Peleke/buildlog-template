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
        # Should have at least one confidence section
        assert "Confidence)" in output or "Insights" in output

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
