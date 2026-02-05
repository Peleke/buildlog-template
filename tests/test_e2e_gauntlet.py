"""E2E tests for the full LLM extraction → gauntlet learn loop.

Tests the complete pipeline: LLM extraction → seed generation →
gauntlet review → learn → rules persist.

Includes both mock-based tests (always run) and Ollama smoke tests
(skipped in CI, run locally with --run-ollama).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from buildlog.core import learn_from_review
from buildlog.llm import ExtractedRule
from buildlog.seed_engine import Pipeline, Source, SourceType
from buildlog.seed_engine.llm_extractor import LLMExtractor
from buildlog.seeds import load_seed_file, seeds_to_skills


def _make_source(**overrides) -> Source:
    defaults = dict(
        name="Test Source",
        url="https://example.com/test",
        source_type=SourceType.REFERENCE_DOC,
        domain="testing",
        description="Test content for extraction.",
    )
    defaults.update(overrides)
    return Source(**defaults)


def _make_mock_backend(rules: list[ExtractedRule]) -> MagicMock:
    backend = MagicMock()
    backend.extract_rules.return_value = rules
    backend._model = "mock-model"
    return backend


SAMPLE_RULES = [
    ExtractedRule(
        rule="Always define interfaces before implementations",
        category="architectural",
        severity="major",
        scope="global",
        applicability=["python", "oop"],
        context="When designing module boundaries",
        antipattern="Jumping straight to concrete classes",
        rationale="Interfaces clarify contracts and enable substitution",
    ),
    ExtractedRule(
        rule="Validate parsed dates are within valid ranges",
        category="domain_knowledge",
        severity="critical",
        scope="function",
        applicability=["python", "datetime"],
        context="When parsing user-provided dates",
        antipattern="Accepting any parseable date without range check",
        rationale="Prevents nonsensical dates from entering the system",
    ),
    ExtractedRule(
        rule="Use structured logging over print statements",
        category="workflow",
        severity="minor",
        scope="global",
        applicability=["python"],
        context=None,
        antipattern=None,
        rationale="Structured logs are searchable and parseable",
    ),
]


class TestFullLoopExtractToLearn:
    """Full loop: LLM extraction → seed YAML → load → learn → persist."""

    def test_extract_to_seed_yaml(self, tmp_path: Path):
        backend = _make_mock_backend(SAMPLE_RULES)
        source = _make_source()

        pipeline = Pipeline.with_llm(
            persona="test_persona",
            backend=backend,
            source_content={source.url: "some content"},
        )

        result = pipeline.run([source], output_dir=tmp_path)

        assert result.rule_count == 3
        assert result.output_path is not None
        assert result.output_path.exists()

        # Verify YAML is loadable
        with open(result.output_path) as f:
            data = yaml.safe_load(f)
        assert data["persona"] == "test_persona"
        assert len(data["rules"]) == 3

    def test_seed_yaml_has_defensibility_fields(self, tmp_path: Path):
        backend = _make_mock_backend(SAMPLE_RULES)
        pipeline = Pipeline.with_llm(
            persona="test_persona",
            backend=backend,
            source_content={_make_source().url: "content"},
        )
        result = pipeline.run([_make_source()], output_dir=tmp_path)

        with open(result.output_path) as f:
            data = yaml.safe_load(f)

        for rule in data["rules"]:
            assert "context" in rule
            assert "antipattern" in rule
            assert "rationale" in rule
            assert rule["context"]  # non-empty
            assert rule["antipattern"]
            assert rule["rationale"]

    def test_load_seed_and_convert_to_skills(self, tmp_path: Path):
        backend = _make_mock_backend(SAMPLE_RULES)
        pipeline = Pipeline.with_llm(
            persona="test_persona",
            backend=backend,
            source_content={_make_source().url: "content"},
        )
        result = pipeline.run([_make_source()], output_dir=tmp_path)

        seed_file = load_seed_file(result.output_path)
        assert seed_file is not None
        assert len(seed_file.rules) == 3

        skills = seeds_to_skills(seed_file)
        assert len(skills) == 3
        for skill in skills:
            assert skill.confidence == "high"
            assert skill.frequency == 0
            assert "test_persona" in skill.persona_tags

    def test_learn_from_review_persists(self, tmp_path: Path):
        """Simulate review issues and verify learnings persist."""
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "Missing interface for data layer",
                "rule_learned": "Always define interfaces before implementations",
            },
            {
                "severity": "major",
                "category": "domain_knowledge",
                "description": "Date parsing accepts year 9999",
                "rule_learned": "Validate parsed dates are within valid ranges",
            },
        ]

        result = learn_from_review(buildlog_dir, issues, source="gauntlet:e2e-test")

        assert result.total_issues_processed == 2
        assert len(result.new_learnings) == 2
        assert len(result.reinforced_learnings) == 0

        # Verify persistence via backend
        from buildlog.storage import get_backend

        backend, pid = get_backend(buildlog_dir, project_root=tmp_path)
        data = backend.load_learnings(pid)
        assert len(data["learnings"]) == 2


class TestGauntletLearnPersistsAndReinforces:
    """Reinforcement tracking across multiple learn calls."""

    def test_reinforcement_on_repeat(self, tmp_path: Path):
        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        issues_round1 = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "Issue A",
                "rule_learned": "Always define interfaces before implementations",
            },
            {
                "severity": "major",
                "category": "workflow",
                "description": "Issue B",
                "rule_learned": "Use structured logging over print statements",
            },
            {
                "severity": "minor",
                "category": "domain_knowledge",
                "description": "Issue C",
                "rule_learned": "Validate parsed dates are within valid ranges",
            },
        ]

        r1 = learn_from_review(buildlog_dir, issues_round1, source="gauntlet:round1")
        assert len(r1.new_learnings) == 3
        assert len(r1.reinforced_learnings) == 0

        # Round 2: 2 overlapping + 1 new
        issues_round2 = [
            {
                "severity": "critical",
                "category": "architectural",
                "description": "Issue A again",
                "rule_learned": "Always define interfaces before implementations",
            },
            {
                "severity": "major",
                "category": "workflow",
                "description": "Issue B again",
                "rule_learned": "Use structured logging over print statements",
            },
            {
                "severity": "minor",
                "category": "tool_usage",
                "description": "New issue",
                "rule_learned": "Pin dependency versions in CI",
            },
        ]

        r2 = learn_from_review(buildlog_dir, issues_round2, source="gauntlet:round2")
        assert len(r2.reinforced_learnings) == 2
        assert len(r2.new_learnings) == 1

        # Verify reinforcement counts via backend
        from buildlog.storage import get_backend

        backend, pid = get_backend(buildlog_dir, project_root=tmp_path)
        data = backend.load_learnings(pid)

        for lid in r2.reinforced_learnings:
            learning = data["learnings"][lid]
            assert learning["reinforcement_count"] >= 2


class TestSeedToSkillWithLLMMetadata:
    """Verify LLM metadata flows through to skills."""

    def test_metadata_preserved_in_seed(self, tmp_path: Path):
        backend = _make_mock_backend(SAMPLE_RULES)
        pipeline = Pipeline.with_llm(
            persona="test_persona",
            backend=backend,
            source_content={_make_source().url: "content"},
        )
        result = pipeline.run([_make_source()], output_dir=tmp_path)

        # LLM metadata is in candidates
        for c in result.candidates:
            assert c.metadata["extractor"] == "llm"
            assert c.confidence == 0.7

        # Skills from seeds maintain persona
        seed_file = load_seed_file(result.output_path)
        skills = seeds_to_skills(seed_file)
        for skill in skills:
            assert "test_persona" in skill.persona_tags


class TestLLMFallback:
    """Pipeline behavior when LLM backend fails."""

    def test_extraction_failure_returns_empty(self, tmp_path: Path):
        backend = _make_mock_backend([])
        backend.extract_rules.side_effect = RuntimeError("LLM unavailable")

        pipeline = Pipeline.with_llm(
            persona="test_persona",
            backend=backend,
            source_content={_make_source().url: "content"},
        )
        result = pipeline.run([_make_source()], output_dir=tmp_path, write=False)

        assert result.rule_count == 0
        assert result.candidates == []


# ---------------------------------------------------------------------------
# Ollama smoke tests — skipped in CI, run locally with: pytest --run-ollama
# ---------------------------------------------------------------------------


def _ollama_available() -> bool:
    """Check at call time, not import time, to avoid slowing test collection."""
    try:
        import ollama as ollama_lib

        ollama_lib.list()
        return True
    except Exception:
        return False


class TestOllamaSmokeExtraction:
    """Smoke tests hitting real Ollama. Skipped if Ollama isn't running."""

    @pytest.fixture(autouse=True)
    def _require_ollama(self):
        if not _ollama_available():
            pytest.skip("Ollama not available")

    SAMPLE_ENTRY = """\
## Improvements

- Always define interfaces (protocols/ABCs) before writing concrete implementations.
  This forces you to think about the contract first, making the code easier to test
  and substitute.

- When parsing dates from user input, validate that the parsed date falls within
  a reasonable range (e.g., not year 0 or year 9999). Garbage-in-garbage-out is
  real and date bugs are subtle.

- Prefer structured logging (Python logging module) over bare print() calls.
  Structured logs can be filtered, routed, and parsed by tooling.
"""

    def test_ollama_extracts_at_least_one_rule(self):
        from buildlog.llm import OllamaBackend

        backend = OllamaBackend()
        extractor = LLMExtractor(backend)
        source = _make_source(description=self.SAMPLE_ENTRY)

        candidates = extractor.extract(source)

        assert len(candidates) >= 1, "Ollama should extract at least 1 rule"
        for c in candidates:
            assert c.rule.strip(), "Rule text should be non-empty"
            assert c.confidence == 0.7

    def test_ollama_pipeline_produces_seed_yaml(self, tmp_path: Path):
        from buildlog.llm import OllamaBackend

        backend = OllamaBackend()
        pipeline = Pipeline.with_llm(
            persona="smoke_test",
            backend=backend,
            source_content={_make_source().url: self.SAMPLE_ENTRY},
        )

        result = pipeline.run([_make_source()], output_dir=tmp_path)

        assert result.rule_count >= 1
        assert result.output_path.exists()

        seed_file = load_seed_file(result.output_path)
        assert seed_file is not None
        assert len(seed_file.rules) >= 1

    def test_ollama_full_loop_extract_learn(self, tmp_path: Path):
        """Full loop: Ollama extract → seed → learn → persist."""
        from buildlog.llm import OllamaBackend

        backend = OllamaBackend()
        pipeline = Pipeline.with_llm(
            persona="smoke_test",
            backend=backend,
            source_content={_make_source().url: self.SAMPLE_ENTRY},
        )

        result = pipeline.run([_make_source()], output_dir=tmp_path)
        assert result.rule_count >= 1

        # Build issues from extracted rules
        issues = [
            {
                "severity": "major",
                "category": "architectural",
                "description": f"Violation of: {c.rule}",
                "rule_learned": c.rule,
            }
            for c in result.candidates
        ]

        buildlog_dir = tmp_path / "buildlog"
        buildlog_dir.mkdir()
        (buildlog_dir / ".buildlog").mkdir()

        learn_result = learn_from_review(
            buildlog_dir, issues, source="gauntlet:ollama-smoke"
        )

        assert learn_result.total_issues_processed >= 1
        assert len(learn_result.new_learnings) >= 1

        learnings_path = buildlog_dir / ".buildlog" / "review_learnings.json"
        assert learnings_path.exists()
