"""Tests for LLM-backed rule extraction, dedup, and scoring."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from buildlog.confidence import apply_severity_weight
from buildlog.llm import (
    PROVIDERS,
    AnthropicBackend,
    ExtractedRule,
    LLMConfig,
    OllamaBackend,
    RuleScoring,
    _parse_json_response,
    get_llm_backend,
    register_provider,
)

# --- ExtractedRule tests ---


class TestExtractedRule:
    def test_defaults(self):
        rule = ExtractedRule(rule="Test rule", category="workflow")
        assert rule.severity == "info"
        assert rule.scope == "global"
        assert rule.applicability == []
        assert rule.context is None

    def test_invalid_severity_defaults_to_info(self):
        rule = ExtractedRule(rule="Test", category="workflow", severity="bogus")
        assert rule.severity == "info"

    def test_invalid_scope_defaults_to_global(self):
        rule = ExtractedRule(rule="Test", category="workflow", scope="bogus")
        assert rule.scope == "global"

    def test_invalid_category_defaults_to_architectural(self):
        rule = ExtractedRule(rule="Test", category="bogus")
        assert rule.category == "architectural"

    def test_valid_fields_preserved(self):
        rule = ExtractedRule(
            rule="Always validate input",
            category="architectural",
            severity="critical",
            scope="module",
            applicability=["python", "api"],
            context="When handling user input",
            antipattern="Passing raw input to SQL",
            rationale="Prevents injection attacks",
        )
        assert rule.severity == "critical"
        assert rule.scope == "module"
        assert rule.applicability == ["python", "api"]


# --- RuleScoring tests ---


class TestRuleScoring:
    def test_defaults(self):
        scoring = RuleScoring()
        assert scoring.severity == "info"
        assert scoring.scope == "global"
        assert scoring.applicability == []


# --- LLMConfig tests ---


class TestLLMConfig:
    def test_from_buildlog_config_missing_file(self, tmp_path):
        assert LLMConfig.from_buildlog_config(tmp_path) is None

    def test_from_buildlog_config_no_llm_section(self, tmp_path):
        config_dir = tmp_path / ".buildlog"
        config_dir.mkdir()
        (config_dir / "config.yml").write_text("other: stuff\n")
        assert LLMConfig.from_buildlog_config(tmp_path) is None

    def test_from_buildlog_config_valid(self, tmp_path):
        config_dir = tmp_path / ".buildlog"
        config_dir.mkdir()
        (config_dir / "config.yml").write_text(
            "llm:\n  provider: ollama\n  model: llama3.2\n"
        )
        config = LLMConfig.from_buildlog_config(tmp_path)
        assert config is not None
        assert config.provider == "ollama"
        assert config.model == "llama3.2"

    def test_from_buildlog_config_no_provider(self, tmp_path):
        config_dir = tmp_path / ".buildlog"
        config_dir.mkdir()
        (config_dir / "config.yml").write_text("llm:\n  model: llama3.2\n")
        assert LLMConfig.from_buildlog_config(tmp_path) is None

    @patch("buildlog.llm._is_ollama_available", return_value=True)
    def test_auto_detect_ollama(self, mock_ollama):
        config = LLMConfig.auto_detect()
        assert config is not None
        assert config.provider == "ollama"

    @patch("buildlog.llm._is_ollama_available", return_value=False)
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_auto_detect_anthropic(self, mock_ollama):
        config = LLMConfig.auto_detect()
        assert config is not None
        assert config.provider == "anthropic"
        assert config.api_key == "test-key"

    @patch("buildlog.llm._is_ollama_available", return_value=False)
    @patch.dict("os.environ", {}, clear=True)
    def test_auto_detect_none(self, mock_ollama):
        # Remove ANTHROPIC_API_KEY if present
        config = LLMConfig.auto_detect()
        assert config is None


# --- _parse_json_response tests ---


class TestParseJsonResponse:
    def test_plain_json_array(self):
        result = _parse_json_response('[{"rule": "test"}]')
        assert result == [{"rule": "test"}]

    def test_markdown_code_block(self):
        text = '```json\n[{"rule": "test"}]\n```'
        result = _parse_json_response(text)
        assert result == [{"rule": "test"}]

    def test_plain_json_object(self):
        result = _parse_json_response('{"severity": "critical"}')
        assert result == {"severity": "critical"}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("not json")


# --- Provider registry tests ---


class TestProviderRegistry:
    def test_default_providers(self):
        assert "ollama" in PROVIDERS
        assert "anthropic" in PROVIDERS

    def test_register_provider(self):
        class FakeBackend:
            pass

        register_provider("fake", FakeBackend)
        assert "fake" in PROVIDERS
        # Cleanup
        del PROVIDERS["fake"]


# --- get_llm_backend tests ---


class TestGetLlmBackend:
    def test_explicit_config(self):
        config = LLMConfig(provider="ollama", model="test-model")
        with patch.object(OllamaBackend, "__init__", return_value=None):
            backend = get_llm_backend(config=config)
            assert backend is not None

    def test_unknown_provider_returns_none(self):
        config = LLMConfig(provider="nonexistent")
        backend = get_llm_backend(config=config)
        assert backend is None

    @patch("buildlog.llm.LLMConfig.auto_detect", return_value=None)
    def test_no_provider_returns_none(self, mock_detect):
        backend = get_llm_backend()
        assert backend is None

    def test_config_file_fallback(self, tmp_path):
        config_dir = tmp_path / ".buildlog"
        config_dir.mkdir()
        (config_dir / "config.yml").write_text(
            "llm:\n  provider: ollama\n  model: test\n"
        )
        with patch.object(OllamaBackend, "__init__", return_value=None):
            backend = get_llm_backend(buildlog_dir=tmp_path)
            assert backend is not None


# --- Mock backend for integration tests ---


class MockLLMBackend:
    """Mock LLM backend for testing."""

    def extract_rules(self, entry_text: str) -> list[ExtractedRule]:
        return [
            ExtractedRule(
                rule="Always validate input",
                category="architectural",
                severity="critical",
                scope="global",
                applicability=["python"],
            )
        ]

    def select_canonical(self, candidates: list[str]) -> str:
        return "Canonical: " + candidates[0]

    def score_rule(self, rule: str, context: str) -> RuleScoring:
        return RuleScoring(severity="major", scope="module", applicability=["python"])


class TestMockBackendIntegration:
    def test_extract_rules(self):
        backend = MockLLMBackend()
        rules = backend.extract_rules("Some improvements text")
        assert len(rules) == 1
        assert rules[0].severity == "critical"

    def test_select_canonical(self):
        backend = MockLLMBackend()
        result = backend.select_canonical(["rule A", "rule B"])
        assert result.startswith("Canonical:")

    def test_score_rule(self):
        backend = MockLLMBackend()
        scoring = backend.score_rule("some rule", "some context")
        assert scoring.severity == "major"


# --- Severity weighting tests ---


class TestSeverityWeight:
    def test_critical_boosts(self):
        result = apply_severity_weight(0.5, "critical")
        assert result == 0.75  # 0.5 * 1.5

    def test_major_boosts(self):
        result = apply_severity_weight(0.5, "major")
        assert result == 0.6  # 0.5 * 1.2

    def test_minor_unchanged(self):
        result = apply_severity_weight(0.5, "minor")
        assert result == 0.5  # 0.5 * 1.0

    def test_info_dampens(self):
        result = apply_severity_weight(0.5, "info")
        assert result == 0.4  # 0.5 * 0.8

    def test_capped_at_one(self):
        result = apply_severity_weight(0.9, "critical")
        assert result == 1.0  # min(0.9 * 1.5, 1.0)

    def test_unknown_severity_uses_default(self):
        result = apply_severity_weight(0.5, "unknown")
        assert result == 0.5  # default weight 1.0


# --- Distill integration tests ---


class TestDistillLLMIntegration:
    def test_parse_improvements_llm(self):
        from buildlog.distill import parse_improvements_llm

        backend = MockLLMBackend()
        content = "## Improvements\n\n### Architectural\n\n- Validate input\n"
        rules = parse_improvements_llm(content, backend)
        assert len(rules) == 1
        assert rules[0].rule == "Always validate input"

    def test_parse_improvements_llm_no_section(self):
        from buildlog.distill import parse_improvements_llm

        backend = MockLLMBackend()
        content = "## Other Section\n\nSome content\n"
        rules = parse_improvements_llm(content, backend)
        assert rules == []


# --- Skills dedup with LLM tests ---


class TestSkillsLLMDedup:
    def test_deduplicate_with_llm_canonical(self):
        from buildlog.distill import PatternDict
        from buildlog.skills import _deduplicate_insights

        patterns = [
            PatternDict(
                insight="validate input always",
                source="a.md",
                date="2026-01-01",
                context="",
            ),
            PatternDict(
                insight="always validate input",
                source="b.md",
                date="2026-01-02",
                context="",
            ),
        ]

        # With a mock embedding backend that always returns high similarity
        mock_embedding = MagicMock()
        mock_embedding.similarity.return_value = 0.9

        mock_llm = MockLLMBackend()
        result = _deduplicate_insights(
            patterns, backend=mock_embedding, llm_backend=mock_llm
        )
        assert len(result) == 1
        # LLM canonical should be used
        assert result[0][0].startswith("Canonical:")
