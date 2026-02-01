"""Unit tests for LLMExtractor."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from buildlog.llm import ExtractedRule
from buildlog.seed_engine.llm_extractor import _PLACEHOLDER, LLMExtractor
from buildlog.seed_engine.models import CandidateRule, Source, SourceType


def _make_source(**overrides) -> Source:
    defaults = dict(
        name="Test Source",
        url="https://example.com/test",
        source_type=SourceType.REFERENCE_DOC,
        domain="testing",
        description="Some test content for extraction.",
    )
    defaults.update(overrides)
    return Source(**defaults)


def _make_backend(rules: list[ExtractedRule] | None = None) -> MagicMock:
    backend = MagicMock()
    backend.extract_rules.return_value = rules or []
    backend._model = "test-model-v1"
    return backend


class TestExtractedRuleToCandidateRule:
    """ExtractedRule → CandidateRule conversion."""

    def test_all_fields_populated(self):
        er = ExtractedRule(
            rule="Always validate input at boundaries",
            category="architectural",
            severity="critical",
            scope="global",
            applicability=["python", "api-design"],
            context="When accepting external input",
            antipattern="Trusting raw user input without sanitization",
            rationale="Prevents injection attacks",
        )
        backend = _make_backend([er])
        extractor = LLMExtractor(backend)
        source = _make_source()

        candidates = extractor.extract(source)

        assert len(candidates) == 1
        c = candidates[0]
        assert c.rule == "Always validate input at boundaries"
        assert c.context == "When accepting external input"
        assert c.antipattern == "Trusting raw user input without sanitization"
        assert c.rationale == "Prevents injection attacks"
        assert c.confidence == 0.7
        assert c.metadata["extractor"] == "llm"
        assert c.metadata["backend_type"] == "MagicMock"
        assert c.metadata["severity"] == "critical"
        assert c.metadata["scope"] == "global"
        assert "architectural" in c.raw_tags
        assert "python" in c.raw_tags
        assert "api-design" in c.raw_tags
        assert c.source is source
        assert c.is_complete()

    def test_none_defensibility_fields_get_placeholders(self):
        er = ExtractedRule(
            rule="Use immutable data structures",
            category="architectural",
            context=None,
            antipattern=None,
            rationale=None,
        )
        backend = _make_backend([er])
        extractor = LLMExtractor(backend)

        candidates = extractor.extract(_make_source())

        assert len(candidates) == 1
        c = candidates[0]
        assert c.context == _PLACEHOLDER
        assert c.antipattern == _PLACEHOLDER
        assert c.rationale == _PLACEHOLDER
        # Still validates as complete (placeholders are non-empty)
        assert c.is_complete()

    def test_empty_extraction_returns_empty(self):
        backend = _make_backend([])
        extractor = LLMExtractor(backend)
        assert extractor.extract(_make_source()) == []

    def test_empty_rule_text_skipped(self):
        er = ExtractedRule(rule="", category="workflow")
        backend = _make_backend([er])
        extractor = LLMExtractor(backend)
        assert extractor.extract(_make_source()) == []


class TestValidation:
    """LLMExtractor.validate() warnings."""

    def test_warns_on_placeholder_context(self):
        c = CandidateRule(
            rule="Do something",
            context=_PLACEHOLDER,
            antipattern="Bad thing",
            rationale="Because reasons",
            source=_make_source(),
        )
        extractor = LLMExtractor(_make_backend())
        issues = extractor.validate(c)
        assert any("Context" in i for i in issues)

    def test_warns_on_all_placeholders(self):
        c = CandidateRule(
            rule="Do something",
            context=_PLACEHOLDER,
            antipattern=_PLACEHOLDER,
            rationale=_PLACEHOLDER,
            source=_make_source(),
        )
        extractor = LLMExtractor(_make_backend())
        issues = extractor.validate(c)
        assert len(issues) == 3

    def test_no_warnings_on_real_fields(self):
        c = CandidateRule(
            rule="Do something",
            context="When doing X",
            antipattern="Doing Y instead",
            rationale="Because Z",
            source=_make_source(),
        )
        extractor = LLMExtractor(_make_backend())
        assert extractor.validate(c) == []

    def test_empty_rule_text_is_error(self):
        c = CandidateRule(
            rule="",
            context="ctx",
            antipattern="ap",
            rationale="rat",
            source=_make_source(),
        )
        extractor = LLMExtractor(_make_backend())
        issues = extractor.validate(c)
        assert any("empty" in i.lower() for i in issues)


class TestSourceContent:
    """Content resolution: source_content dict vs description fallback."""

    def test_uses_source_content_dict(self):
        backend = _make_backend([])
        source = _make_source(description="fallback text")
        content_map = {source.url: "primary content"}
        extractor = LLMExtractor(backend, source_content=content_map)

        extractor.extract(source)

        backend.extract_rules.assert_called_once_with("primary content")

    def test_falls_back_to_description(self):
        backend = _make_backend([])
        source = _make_source(description="description content")
        extractor = LLMExtractor(backend)

        extractor.extract(source)

        backend.extract_rules.assert_called_once_with("description content")

    def test_skips_source_with_no_content(self):
        backend = _make_backend([])
        source = _make_source(description="")
        extractor = LLMExtractor(backend)

        result = extractor.extract(source)

        assert result == []
        backend.extract_rules.assert_not_called()


class TestLLMFailure:
    """Graceful handling of LLM backend failures."""

    def test_returns_empty_on_exception(self):
        backend = _make_backend()
        backend.extract_rules.side_effect = RuntimeError("connection refused")
        extractor = LLMExtractor(backend)

        result = extractor.extract(_make_source())

        assert result == []

    def test_no_model_attr_still_works(self):
        """Backend without _model attribute doesn't crash."""
        backend = MagicMock(spec=["extract_rules", "select_canonical", "score_rule"])
        backend.extract_rules.return_value = [
            ExtractedRule(rule="Test rule", category="workflow")
        ]
        extractor = LLMExtractor(backend)

        candidates = extractor.extract(_make_source())

        assert len(candidates) == 1
        assert "backend_type" in candidates[0].metadata


class TestMockIntegration:
    """Mock LLMBackend integration with multiple rules."""

    def test_multi_rule_extraction(self):
        rules = [
            ExtractedRule(
                rule="Always define interfaces before implementations",
                category="architectural",
                severity="major",
                scope="global",
                applicability=["python", "oop"],
                context="When designing module boundaries",
                antipattern="Jumping straight to implementation",
                rationale="Interfaces clarify contracts",
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
        ]
        backend = _make_backend(rules)
        extractor = LLMExtractor(backend)

        candidates = extractor.extract(_make_source())

        assert len(candidates) == 2
        assert candidates[0].metadata["severity"] == "major"
        assert candidates[1].metadata["scope"] == "function"
        assert all(c.confidence == 0.7 for c in candidates)
