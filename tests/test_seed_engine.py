"""Tests for the seed engine pipeline."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from buildlog.seed_engine import (
    CandidateRule,
    CategorizedRule,
    CategoryMapping,
    ManualExtractor,
    Pipeline,
    SeedGenerator,
    Source,
    SourceType,
    TagBasedCategorizer,
)


class TestSource:
    """Tests for Source model."""

    def test_source_creation(self):
        """Test creating a source with all fields."""
        source = Source(
            name="Google Testing Blog",
            url="https://testing.googleblog.com/",
            source_type=SourceType.BLOG_POST,
            domain="testing",
            description="Google's testing best practices",
        )
        assert source.name == "Google Testing Blog"
        assert source.source_type == SourceType.BLOG_POST

    def test_source_to_reference(self):
        """Test converting source to reference format."""
        source = Source(
            name="OWASP Top 10",
            url="https://owasp.org/Top10/",
            source_type=SourceType.REFERENCE_DOC,
            domain="security",
        )
        ref = source.to_reference()
        assert ref["url"] == "https://owasp.org/Top10/"
        assert ref["title"] == "OWASP Top 10"


class TestCandidateRule:
    """Tests for CandidateRule model."""

    def test_candidate_rule_creation(self):
        """Test creating a candidate rule."""
        source = Source(
            name="Test",
            url="https://test.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        rule = CandidateRule(
            rule="Tests must be hermetic",
            context="Test isolation",
            antipattern="Shared mutable state",
            rationale="Flaky tests waste time",
            source=source,
            raw_tags=["isolation", "hermetic"],
        )
        assert rule.is_complete()

    def test_incomplete_rule(self):
        """Test that incomplete rules are detected."""
        source = Source(
            name="Test",
            url="https://test.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        rule = CandidateRule(
            rule="Missing fields",
            context="",  # Empty
            antipattern="Bad",
            rationale="",  # Empty
            source=source,
        )
        assert not rule.is_complete()


class TestCategorizedRule:
    """Tests for CategorizedRule model."""

    def test_from_candidate(self):
        """Test creating categorized rule from candidate."""
        source = Source(
            name="Test",
            url="https://test.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        candidate = CandidateRule(
            rule="Test rule",
            context="When to apply",
            antipattern="What not to do",
            rationale="Why it matters",
            source=source,
            raw_tags=["tag1"],
        )
        categorized = CategorizedRule.from_candidate(
            candidate=candidate,
            category="testing",
            tags=["tag1", "tag2"],
        )
        assert categorized.category == "testing"
        assert categorized.tags == ["tag1", "tag2"]
        assert categorized.references[0]["url"] == "https://test.com"

    def test_to_seed_dict(self):
        """Test converting to seed file format."""
        categorized = CategorizedRule(
            rule="Test rule",
            category="testing",
            context="When to apply",
            antipattern="What not to do",
            rationale="Why it matters",
            tags=["unit", "coverage"],
            references=[{"url": "https://test.com", "title": "Test"}],
        )
        d = categorized.to_seed_dict()
        assert d["rule"] == "Test rule"
        assert d["category"] == "testing"
        assert d["context"] == "When to apply"
        assert d["antipattern"] == "What not to do"
        assert d["rationale"] == "Why it matters"
        assert "unit" in d["tags"]


class TestManualExtractor:
    """Tests for ManualExtractor."""

    def test_register_and_extract(self):
        """Test registering and extracting rules."""
        source = Source(
            name="Test Source",
            url="https://test.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        rule = CandidateRule(
            rule="Test rule",
            context="Context",
            antipattern="Antipattern",
            rationale="Rationale",
            source=source,
        )

        extractor = ManualExtractor()
        extractor.register(source, [rule])

        extracted = extractor.extract(source)
        assert len(extracted) == 1
        assert extracted[0].rule == "Test rule"

    def test_extract_unknown_source(self):
        """Test extracting from unregistered source."""
        source = Source(
            name="Unknown",
            url="https://unknown.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        extractor = ManualExtractor()
        extracted = extractor.extract(source)
        assert extracted == []

    def test_validation_rejects_incomplete(self):
        """Test that incomplete rules are rejected."""
        source = Source(
            name="Test",
            url="https://test.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        incomplete_rule = CandidateRule(
            rule="Missing context",
            context="",  # Empty!
            antipattern="Bad",
            rationale="Why",
            source=source,
        )

        extractor = ManualExtractor()
        with pytest.raises(ValueError, match="Context is required"):
            extractor.register(source, [incomplete_rule])


class TestTagBasedCategorizer:
    """Tests for TagBasedCategorizer."""

    def test_default_category(self):
        """Test that default category is used when no match."""
        source = Source(
            name="Test",
            url="https://test.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        candidate = CandidateRule(
            rule="Generic rule",
            context="Context",
            antipattern="Antipattern",
            rationale="Rationale",
            source=source,
            raw_tags=["misc"],
        )

        categorizer = TagBasedCategorizer(default_category="general")
        result = categorizer.categorize(candidate)
        assert result.category == "general"

    def test_keyword_matching(self):
        """Test category assignment via keyword matching."""
        source = Source(
            name="Test",
            url="https://test.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        candidate = CandidateRule(
            rule="Use coverage tools",
            context="Context",
            antipattern="Antipattern",
            rationale="Rationale",
            source=source,
            raw_tags=["coverage", "ci"],
        )

        categorizer = TagBasedCategorizer(
            default_category="general",
            mappings=[
                CategoryMapping("coverage", ["coverage", "untested"]),
                CategoryMapping("isolation", ["flaky", "hermetic"]),
            ],
        )
        result = categorizer.categorize(candidate)
        assert result.category == "coverage"


class TestSeedGenerator:
    """Tests for SeedGenerator."""

    def test_generate(self):
        """Test generating seed file dictionary."""
        rules = [
            CategorizedRule(
                rule="Test rule",
                category="testing",
                context="Context",
                antipattern="Antipattern",
                rationale="Rationale",
                tags=["unit"],
                references=[{"url": "https://test.com", "title": "Test"}],
            )
        ]

        generator = SeedGenerator(persona="test_terrorist", version=1)
        seed_data = generator.generate(rules)

        assert seed_data["persona"] == "test_terrorist"
        assert seed_data["version"] == 1
        assert len(seed_data["rules"]) == 1
        assert seed_data["rules"][0]["rule"] == "Test rule"

    def test_write_to_file(self, tmp_path: Path):
        """Test writing seed file to disk."""
        rules = [
            CategorizedRule(
                rule="Test rule",
                category="testing",
                context="Context",
                antipattern="Antipattern",
                rationale="Rationale",
                tags=["unit"],
                references=[],
            )
        ]

        generator = SeedGenerator(
            persona="test_terrorist",
            version=1,
            output_dir=tmp_path,
        )
        seed_data = generator.generate(rules)
        output_path = generator.write(seed_data)

        assert output_path.exists()
        assert output_path.name == "test_terrorist.yaml"

        # Verify content
        with open(output_path) as f:
            loaded = yaml.safe_load(f)
        assert loaded["persona"] == "test_terrorist"

    def test_validation(self):
        """Test seed file validation."""
        generator = SeedGenerator(persona="test", version=1)

        # Valid
        valid_data = {
            "persona": "test",
            "version": 1,
            "rules": [
                {
                    "rule": "Test",
                    "context": "Context",
                    "antipattern": "Anti",
                    "rationale": "Why",
                }
            ],
        }
        assert generator.validate(valid_data) == []

        # Missing fields
        invalid_data = {
            "persona": "test",
            "version": 1,
            "rules": [{"rule": "Test"}],  # Missing defensibility fields
        }
        issues = generator.validate(invalid_data)
        assert len(issues) == 3  # context, antipattern, rationale


class TestSourceManifest:
    """Tests for SourceManifest."""

    def test_add_and_retrieve_sources(self):
        """Test adding and retrieving sources."""
        from buildlog.seed_engine import SourceManifest

        manifest = SourceManifest(persona="test")
        source = Source(
            name="Test",
            url="https://test.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        manifest.add_source(source)

        assert len(manifest.entries) == 1
        assert manifest.get_by_url("https://test.com") is not None
        assert manifest.get_by_url("https://other.com") is None

    def test_save_and_load(self, tmp_path: Path):
        """Test saving and loading manifest."""
        from buildlog.seed_engine import SourceManifest

        manifest = SourceManifest(persona="test_persona")
        manifest.add_source(
            Source(
                name="Test",
                url="https://test.com",
                source_type=SourceType.BLOG_POST,
                domain="testing",
            )
        )
        manifest.save(tmp_path)

        loaded = SourceManifest.load(tmp_path)
        assert loaded is not None
        assert loaded.persona == "test_persona"
        assert len(loaded.entries) == 1

    def test_summary(self):
        """Test manifest summary."""
        from buildlog.seed_engine import FetchStatus, SourceManifest

        manifest = SourceManifest(persona="test")
        for i in range(3):
            manifest.add_source(
                Source(
                    name=f"Test {i}",
                    url=f"https://test{i}.com",
                    source_type=SourceType.BLOG_POST,
                    domain="testing",
                )
            )

        # Mark one as cached
        manifest.entries[0].status = FetchStatus.CACHED

        summary = manifest.summary()
        assert summary["total"] == 3
        assert summary["pending"] == 2
        assert summary["cached"] == 1


class TestUrlToCacheFilename:
    """Tests for url_to_cache_filename."""

    def test_simple_url(self):
        """Test converting a simple URL."""
        from buildlog.seed_engine import url_to_cache_filename

        url = "https://testing.googleblog.com/2015/04/test.html"
        filename = url_to_cache_filename(url)
        assert filename.endswith(".md")
        assert "googleblog" in filename
        assert "2015" in filename

    def test_complex_url(self):
        """Test converting a complex URL."""
        from buildlog.seed_engine import url_to_cache_filename

        url = "https://example.com/path/to/some-doc.pdf"
        filename = url_to_cache_filename(url)
        assert filename.endswith(".md")
        assert len(filename) <= 104  # 100 + ".md"


class TestPipeline:
    """Tests for the full pipeline."""

    def test_full_pipeline(self, tmp_path: Path):
        """Test running the complete pipeline."""
        # Step 1: Define sources
        source = Source(
            name="Google Testing Blog",
            url="https://testing.googleblog.com/",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )

        # Step 2: Create extractor with rules
        extractor = ManualExtractor()
        extractor.register(
            source,
            [
                CandidateRule(
                    rule="Tests must be hermetic",
                    context="Any test that uses external state",
                    antipattern="Tests sharing database, files, or global state",
                    rationale="Shared state causes flaky tests that erode trust",
                    source=source,
                    raw_tags=["isolation", "hermetic"],
                ),
                CandidateRule(
                    rule="Aim for 80% code coverage on critical paths",
                    context="New features and bug fixes",
                    antipattern="No coverage targets; untested code paths",
                    rationale="Coverage ensures code is exercised; 100% is diminishing returns",
                    source=source,
                    raw_tags=["coverage"],
                ),
            ],
        )

        # Step 3: Create categorizer
        categorizer = TagBasedCategorizer(
            default_category="testing",
            mappings=[
                CategoryMapping("isolation", ["isolation", "hermetic", "flaky"]),
                CategoryMapping("coverage", ["coverage", "untested"]),
            ],
        )

        # Create and run pipeline
        pipeline = Pipeline(
            persona="test_terrorist",
            extractor=extractor,
            categorizer=categorizer,
            version=1,
        )

        result = pipeline.run([source], output_dir=tmp_path)

        # Verify result
        assert result.persona == "test_terrorist"
        assert result.source_count == 1
        assert result.rule_count == 2
        assert result.output_path is not None
        assert result.output_path.exists()

        # Verify categories were assigned
        categories = [r.category for r in result.categorized]
        assert "isolation" in categories
        assert "coverage" in categories

    def test_dry_run(self):
        """Test dry run without writing."""
        source = Source(
            name="Test",
            url="https://test.com",
            source_type=SourceType.BLOG_POST,
            domain="testing",
        )
        extractor = ManualExtractor()
        extractor.register(
            source,
            [
                CandidateRule(
                    rule="Test rule",
                    context="Context",
                    antipattern="Antipattern",
                    rationale="Rationale",
                    source=source,
                )
            ],
        )

        pipeline = Pipeline(
            persona="test",
            extractor=extractor,
            default_category="testing",
        )

        preview = pipeline.dry_run([source])
        assert preview["persona"] == "test"
        assert preview["rule_count"] == 1
        assert "testing" in preview["categories"]


class TestTestTerroristSeedFile:
    """Integration tests for the Test Terrorist seed file."""

    def test_load_test_terrorist_seeds(self):
        """Test that the Test Terrorist seed file is valid."""
        seed_path = Path(".buildlog/seeds/test_terrorist.yaml")
        if not seed_path.exists():
            pytest.skip("Test Terrorist seed file not found")

        with open(seed_path) as f:
            seed_data = yaml.safe_load(f)

        assert seed_data["persona"] == "test_terrorist"
        assert seed_data["version"] == 1
        assert len(seed_data["rules"]) >= 15  # Should have substantial coverage

    def test_test_terrorist_rules_are_defensible(self):
        """Test that all Test Terrorist rules have defensibility fields."""
        seed_path = Path(".buildlog/seeds/test_terrorist.yaml")
        if not seed_path.exists():
            pytest.skip("Test Terrorist seed file not found")

        with open(seed_path) as f:
            seed_data = yaml.safe_load(f)

        for rule in seed_data["rules"]:
            assert rule.get("rule"), "Missing rule text"
            assert rule.get(
                "context"
            ), f"Missing context for: {rule.get('rule', 'unknown')}"
            assert rule.get(
                "antipattern"
            ), f"Missing antipattern for: {rule.get('rule', 'unknown')}"
            assert rule.get(
                "rationale"
            ), f"Missing rationale for: {rule.get('rule', 'unknown')}"
            assert rule.get(
                "references"
            ), f"Missing references for: {rule.get('rule', 'unknown')}"

    def test_test_terrorist_categories_coverage(self):
        """Test that Test Terrorist covers expected categories."""
        seed_path = Path(".buildlog/seeds/test_terrorist.yaml")
        if not seed_path.exists():
            pytest.skip("Test Terrorist seed file not found")

        with open(seed_path) as f:
            seed_data = yaml.safe_load(f)

        categories = set(rule["category"] for rule in seed_data["rules"])

        # Should cover core testing concerns
        expected = {"coverage", "isolation", "assertions", "anti-patterns"}
        assert expected.issubset(
            categories
        ), f"Missing categories: {expected - categories}"

        # Should also cover advanced testing
        advanced = {"property-testing", "metamorphic-testing", "statistical-testing"}
        assert advanced.issubset(
            categories
        ), f"Missing advanced categories: {advanced - categories}"

    def test_llm_testing_rules_are_flagged(self):
        """Test that LLM testing rules are marked as gaps."""
        seed_path = Path(".buildlog/seeds/test_terrorist.yaml")
        if not seed_path.exists():
            pytest.skip("Test Terrorist seed file not found")

        with open(seed_path) as f:
            seed_data = yaml.safe_load(f)

        llm_rules = [r for r in seed_data["rules"] if r["category"] == "llm-testing"]
        assert len(llm_rules) >= 1, "Should have LLM testing rules"

        for rule in llm_rules:
            # LLM testing rules should indicate they are gaps
            assert (
                "[GAP]" in rule["rationale"]
            ), f"LLM rule should be flagged as gap: {rule['rule']}"
            assert "gap" in rule.get(
                "tags", []
            ), f"LLM rule should have 'gap' tag: {rule['rule']}"

    def test_source_validation(self):
        """Test source validation."""
        pipeline = Pipeline(persona="test")

        # Valid source
        valid = [
            Source(
                name="Test",
                url="https://test.com",
                source_type=SourceType.BLOG_POST,
                domain="testing",
            )
        ]
        assert pipeline.validate_sources(valid) == []

        # Invalid sources
        invalid = [
            Source(
                name="",  # Missing name
                url="https://test.com",
                source_type=SourceType.BLOG_POST,
                domain="testing",
            ),
            Source(
                name="Test",
                url="",  # Missing URL
                source_type=SourceType.BLOG_POST,
                domain="testing",
            ),
        ]
        issues = pipeline.validate_sources(invalid)
        assert len(issues) == 2
