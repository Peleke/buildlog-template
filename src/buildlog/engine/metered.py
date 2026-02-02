"""MeteredBackend — LLM wrapper with token usage and cost tracking."""

from __future__ import annotations

__all__ = [
    "TokenUsage",
    "ModelPricing",
    "MeteredBackend",
    "DEFAULT_PRICING",
]

import logging
from dataclasses import dataclass

from buildlog.llm import ExtractedRule, LLMBackend, LLMResponse, RuleScoring

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Accumulated token usage and cost for one or more LLM calls."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_cost_usd: float = 0.0


@dataclass
class ModelPricing:
    """Per-million-token pricing for a model."""

    input_per_mtok: float
    output_per_mtok: float
    cached_per_mtok: float = 0.0


DEFAULT_PRICING: dict[str, ModelPricing] = {
    "claude-sonnet-4-20250514": ModelPricing(3.0, 15.0, 0.3),
    "claude-haiku-4-20250514": ModelPricing(0.80, 4.0, 0.08),
}


class MeteredBackend:
    """Wraps an LLMBackend to track token usage and costs per call."""

    def __init__(
        self,
        backend: LLMBackend,
        pricing: dict[str, ModelPricing] | None = None,
    ):
        self._backend = backend
        self._pricing = pricing or DEFAULT_PRICING
        self._cumulative = TokenUsage()
        self._calls: list[TokenUsage] = []

    def call(self, prompt: str) -> LLMResponse:
        """Delegate to backend.call() and record token usage."""
        response = self._backend.call(prompt)
        pricing = self._pricing.get(response.model)
        if pricing is None:
            logger.warning("No pricing for model %r; cost will be 0.0", response.model)
            cost = 0.0
        else:
            cost = (
                response.input_tokens * pricing.input_per_mtok
                + response.output_tokens * pricing.output_per_mtok
                + response.cached_tokens * pricing.cached_per_mtok
            ) / 1_000_000

        usage = TokenUsage(
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cached_tokens=response.cached_tokens,
            total_cost_usd=cost,
        )
        self._calls.append(usage)
        self._cumulative.input_tokens += usage.input_tokens
        self._cumulative.output_tokens += usage.output_tokens
        self._cumulative.cached_tokens += usage.cached_tokens
        self._cumulative.total_cost_usd += usage.total_cost_usd
        return response

    def get_cumulative_usage(self) -> TokenUsage:
        """Return cumulative token usage across all calls."""
        return TokenUsage(
            input_tokens=self._cumulative.input_tokens,
            output_tokens=self._cumulative.output_tokens,
            cached_tokens=self._cumulative.cached_tokens,
            total_cost_usd=self._cumulative.total_cost_usd,
        )

    def get_call_log(self) -> list[TokenUsage]:
        """Return per-call usage history."""
        return list(self._calls)

    def reset(self) -> None:
        """Clear all accumulated usage data."""
        self._cumulative = TokenUsage()
        self._calls.clear()

    # --- Delegate Protocol methods ---

    def extract_rules(self, entry_text: str) -> list[ExtractedRule]:
        return self._backend.extract_rules(entry_text)

    def select_canonical(self, candidates: list[str]) -> str:
        return self._backend.select_canonical(candidates)

    def score_rule(self, rule: str, context: str) -> RuleScoring:
        return self._backend.score_rule(rule, context)
