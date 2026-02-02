"""Tests for MeteredBackend and token tracking."""

from __future__ import annotations

from dataclasses import dataclass, field

from buildlog.engine.metered import (
    DEFAULT_PRICING,
    MeteredBackend,
    ModelPricing,
    TokenUsage,
)
from buildlog.llm import ExtractedRule, LLMResponse, RuleScoring

# ---------------------------------------------------------------------------
# Mock backend
# ---------------------------------------------------------------------------


class MockLLMBackend:
    """Canned LLM backend for testing MeteredBackend."""

    def __init__(
        self,
        response: LLMResponse | None = None,
        model: str = "claude-haiku-4-20250514",
    ):
        self._response = response or LLMResponse(
            text="hello",
            input_tokens=100,
            output_tokens=50,
            model=model,
        )
        self.call_count = 0

    def call(self, prompt: str) -> LLMResponse:
        self.call_count += 1
        return self._response

    def extract_rules(self, entry_text: str) -> list[ExtractedRule]:
        return [ExtractedRule(rule="test rule", category="architectural")]

    def select_canonical(self, candidates: list[str]) -> str:
        return candidates[0] if candidates else ""

    def score_rule(self, rule: str, context: str) -> RuleScoring:
        return RuleScoring(severity="major")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_defaults(self):
        u = TokenUsage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.cached_tokens == 0
        assert u.total_cost_usd == 0.0


class TestModelPricing:
    def test_defaults(self):
        p = ModelPricing(input_per_mtok=3.0, output_per_mtok=15.0)
        assert p.cached_per_mtok == 0.0


class TestMeteredBackend:
    def test_single_call_tracks_tokens(self):
        backend = MockLLMBackend()
        metered = MeteredBackend(backend)
        resp = metered.call("hi")
        assert resp.text == "hello"
        usage = metered.get_cumulative_usage()
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50

    def test_multiple_calls_accumulate(self):
        backend = MockLLMBackend()
        metered = MeteredBackend(backend)
        metered.call("a")
        metered.call("b")
        metered.call("c")
        usage = metered.get_cumulative_usage()
        assert usage.input_tokens == 300
        assert usage.output_tokens == 150
        assert len(metered.get_call_log()) == 3

    def test_cost_calculation_known_model(self):
        resp = LLMResponse(
            text="ok",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="claude-haiku-4-20250514",
        )
        backend = MockLLMBackend(response=resp)
        metered = MeteredBackend(backend)
        metered.call("test")
        usage = metered.get_cumulative_usage()
        expected = 0.80 + 4.0  # input + output per mtok
        assert abs(usage.total_cost_usd - expected) < 0.001

    def test_cost_with_cached_tokens(self):
        resp = LLMResponse(
            text="ok",
            input_tokens=1_000_000,
            output_tokens=0,
            model="claude-haiku-4-20250514",
            cached_tokens=500_000,
        )
        backend = MockLLMBackend(response=resp)
        metered = MeteredBackend(backend)
        metered.call("test")
        usage = metered.get_cumulative_usage()
        expected = 0.80 + 0.08 * 0.5  # input + cached
        assert abs(usage.total_cost_usd - expected) < 0.001

    def test_unknown_model_zero_cost(self):
        resp = LLMResponse(
            text="ok",
            input_tokens=1000,
            output_tokens=500,
            model="unknown-model-xyz",
        )
        backend = MockLLMBackend(response=resp)
        metered = MeteredBackend(backend)
        metered.call("test")
        usage = metered.get_cumulative_usage()
        assert usage.total_cost_usd == 0.0
        assert usage.input_tokens == 1000

    def test_custom_pricing(self):
        pricing = {"my-model": ModelPricing(1.0, 2.0, 0.0)}
        resp = LLMResponse(
            text="ok", input_tokens=1_000_000, output_tokens=1_000_000, model="my-model"
        )
        backend = MockLLMBackend(response=resp)
        metered = MeteredBackend(backend, pricing=pricing)
        metered.call("test")
        usage = metered.get_cumulative_usage()
        assert abs(usage.total_cost_usd - 3.0) < 0.001

    def test_reset_clears_state(self):
        backend = MockLLMBackend()
        metered = MeteredBackend(backend)
        metered.call("a")
        metered.call("b")
        metered.reset()
        usage = metered.get_cumulative_usage()
        assert usage.input_tokens == 0
        assert usage.total_cost_usd == 0.0
        assert len(metered.get_call_log()) == 0

    def test_call_log_per_call(self):
        backend = MockLLMBackend()
        metered = MeteredBackend(backend)
        metered.call("a")
        metered.call("b")
        log = metered.get_call_log()
        assert len(log) == 2
        assert all(u.input_tokens == 100 for u in log)

    def test_cumulative_is_copy(self):
        backend = MockLLMBackend()
        metered = MeteredBackend(backend)
        metered.call("a")
        u1 = metered.get_cumulative_usage()
        metered.call("b")
        u2 = metered.get_cumulative_usage()
        assert u1.input_tokens == 100
        assert u2.input_tokens == 200

    def test_delegate_extract_rules(self):
        backend = MockLLMBackend()
        metered = MeteredBackend(backend)
        rules = metered.extract_rules("some text")
        assert len(rules) == 1
        assert rules[0].rule == "test rule"

    def test_delegate_select_canonical(self):
        backend = MockLLMBackend()
        metered = MeteredBackend(backend)
        result = metered.select_canonical(["rule a", "rule b"])
        assert result == "rule a"

    def test_delegate_score_rule(self):
        backend = MockLLMBackend()
        metered = MeteredBackend(backend)
        scoring = metered.score_rule("test", "ctx")
        assert scoring.severity == "major"

    def test_call_log_is_copy(self):
        backend = MockLLMBackend()
        metered = MeteredBackend(backend)
        metered.call("a")
        log1 = metered.get_call_log()
        metered.call("b")
        log2 = metered.get_call_log()
        assert len(log1) == 1
        assert len(log2) == 2

    def test_default_pricing_has_expected_models(self):
        assert "claude-sonnet-4-20250514" in DEFAULT_PRICING
        assert "claude-haiku-4-20250514" in DEFAULT_PRICING
