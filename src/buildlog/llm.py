"""LLM-backed rule extraction, deduplication, and scoring.

Provides a provider-agnostic interface for using LLMs to:
- Extract structured rules from buildlog entries
- Select canonical forms when deduplicating similar rules
- Score rules with severity/scope/applicability

Provider cascade:
1. Explicit config (.buildlog/config.yml or env)
2. Injected at call site (API parameter)
3. Auto-detect: Ollama -> Anthropic -> None (regex fallback)
"""

from __future__ import annotations

__all__ = [
    "ExtractedRule",
    "RuleScoring",
    "LLMResponse",
    "LLMConfig",
    "LLMBackend",
    "OllamaBackend",
    "AnthropicBackend",
    "PROVIDERS",
    "register_provider",
    "get_llm_backend",
]

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# --- Data types (provider-agnostic) ---

VALID_SEVERITIES = ("critical", "major", "minor", "info")
VALID_SCOPES = ("global", "module", "function")
VALID_CATEGORIES = ("architectural", "workflow", "tool_usage", "domain_knowledge")


@dataclass
class ExtractedRule:
    """A rule extracted from buildlog text by an LLM."""

    rule: str
    category: str  # architectural/workflow/tool_usage/domain_knowledge
    severity: str = "info"  # critical/major/minor/info
    scope: str = "global"  # global/module/function
    applicability: list[str] = field(default_factory=list)
    context: str | None = None  # when to apply
    antipattern: str | None = None  # what violation looks like
    rationale: str | None = None  # why it matters

    def __post_init__(self) -> None:
        if self.severity not in VALID_SEVERITIES:
            self.severity = "info"
        if self.scope not in VALID_SCOPES:
            self.scope = "global"
        if self.category not in VALID_CATEGORIES:
            self.category = "architectural"


@dataclass
class LLMResponse:
    """Structured response from an LLM call with token usage metadata."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    cached_tokens: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class RuleScoring:
    """Severity/scope/applicability scoring for a rule."""

    severity: str = "info"
    scope: str = "global"
    applicability: list[str] = field(default_factory=list)


# --- Provider config ---


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""

    provider: str  # "ollama", "anthropic", "openai", ...
    model: str | None = None  # None = auto-detect or provider default
    base_url: str | None = None  # Override endpoint
    api_key: str | None = None  # From config or env var

    def __repr__(self) -> str:
        """Redact api_key to prevent accidental exposure in logs/tracebacks."""
        key_display = "***" if self.api_key else "None"
        return (
            f"LLMConfig(provider={self.provider!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, api_key={key_display})"
        )

    @classmethod
    def from_buildlog_config(cls, buildlog_dir: Path) -> LLMConfig | None:
        """Read from .buildlog/config.yml [llm] section."""
        config_path = buildlog_dir / ".buildlog" / "config.yml"
        if not config_path.exists():
            return None

        try:
            import yaml
        except ImportError:
            logger.debug("PyYAML not available, skipping config file")
            return None

        try:
            data = yaml.safe_load(config_path.read_text())
        except Exception:
            logger.warning("Failed to parse %s", config_path)
            return None

        if not isinstance(data, dict):
            return None

        llm_config = data.get("llm")
        if not isinstance(llm_config, dict):
            return None

        provider = llm_config.get("provider")
        if not provider:
            return None

        return cls(
            provider=str(provider),
            model=llm_config.get("model"),
            base_url=llm_config.get("base_url"),
            api_key=llm_config.get("api_key"),
        )

    @classmethod
    def auto_detect(cls) -> LLMConfig | None:
        """Ollama running? -> use it. ANTHROPIC_API_KEY? -> use that. Else None."""
        # Try Ollama first (local, no API key needed)
        if _is_ollama_available():
            return cls(provider="ollama")

        # Try Anthropic (cloud)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            return cls(provider="anthropic", api_key=api_key)

        return None


def _is_ollama_available() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        import ollama as ollama_lib

        ollama_lib.list()
        return True
    except Exception:
        return False


# --- Interface ---


@runtime_checkable
class LLMBackend(Protocol):
    """Protocol for LLM backends."""

    def extract_rules(self, entry_text: str) -> list[ExtractedRule]:
        """Extract structured rules from buildlog entry text."""
        ...

    def select_canonical(self, candidates: list[str]) -> str:
        """Given similar rules, produce the single best canonical form."""
        ...

    def score_rule(self, rule: str, context: str) -> RuleScoring:
        """Score a rule with severity/scope/applicability."""
        ...

    def call(self, prompt: str) -> LLMResponse:
        """Send a prompt and return a structured response with token usage."""
        ...


# --- Prompts ---

EXTRACT_RULES_PROMPT = """\
You are analyzing a buildlog entry's Improvements section. Extract actionable rules.

For each rule, return a JSON array of objects with these fields:
- "rule": string — the actionable rule in imperative form
- "category": string — one of: architectural, workflow, tool_usage, domain_knowledge
- "severity": string — one of: critical, major, minor, info
- "scope": string — one of: global, module, function
- "applicability": array of strings — contexts where relevant (e.g., "python", "api-design")
- "context": string or null — when to apply this rule
- "antipattern": string or null — what violation looks like
- "rationale": string or null — why it matters

Return ONLY a JSON array. No markdown, no explanation.

Text to analyze:
{text}
"""

SELECT_CANONICAL_PROMPT = """\
Given these similar rules, produce the single best canonical form.
The canonical rule should be clear, concise, and actionable.

Similar rules:
{candidates}

Return ONLY the canonical rule text as a plain string. No JSON, no quotes, no explanation.
"""

SCORE_RULE_PROMPT = """\
Score this rule for severity, scope, and applicability.

Rule: {rule}
Context: {context}

Return ONLY a JSON object with:
- "severity": one of: critical, major, minor, info
- "scope": one of: global, module, function
- "applicability": array of strings (contexts where relevant)

No markdown, no explanation.
"""


def _parse_json_response(text: str) -> list | dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    # Strip markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (``` markers)
        lines = [ln for ln in lines[1:] if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


# --- Rate limiting ---

# Minimum seconds between API calls (per-backend instance).
_MIN_CALL_INTERVAL = 0.5


class _RateLimiter:
    """Simple per-instance rate limiter to prevent API abuse."""

    def __init__(self, min_interval: float = _MIN_CALL_INTERVAL):
        self._min_interval = min_interval
        self._last_call: float = 0.0

    def wait(self) -> None:
        """Block until min_interval has elapsed since last call."""
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


# --- Implementations ---


class OllamaBackend:
    """LLM backend using Ollama (local)."""

    def __init__(self, model: str | None = None, base_url: str | None = None):
        self._model = model
        self._base_url = base_url
        self._resolved_model: str | None = None
        self._rate_limiter = _RateLimiter()

    def _get_model(self) -> str:
        """Resolve model name, auto-detecting largest if not specified."""
        if self._resolved_model:
            return self._resolved_model

        if self._model:
            self._resolved_model = self._model
            return self._resolved_model

        # Auto-detect: pick largest pulled model
        try:
            import ollama as ollama_lib

            models = ollama_lib.list()
            if not models or not models.get("models"):
                raise RuntimeError(
                    "No Ollama models found. Pull one with: ollama pull llama3.2"
                )

            model_list = models["models"]
            # Sort by size descending, pick largest
            largest = max(model_list, key=lambda m: m.get("size", 0))
            model_name: str = largest["name"]
            self._resolved_model = model_name
            logger.info("Auto-detected Ollama model: %s", model_name)
            return model_name
        except ImportError:
            raise ImportError(
                "ollama package is required. Install with: pip install buildlog[ollama]"
            )

    def _chat(self, prompt: str) -> str:
        """Send a prompt to Ollama and return the response text."""
        self._rate_limiter.wait()
        import ollama as ollama_lib

        kwargs = {
            "model": self._get_model(),
            "messages": [{"role": "user", "content": prompt}],
        }
        if self._base_url:
            client = ollama_lib.Client(host=self._base_url)
            response = client.chat(**kwargs)
        else:
            response = ollama_lib.chat(**kwargs)
        return response["message"]["content"]

    def call(self, prompt: str) -> LLMResponse:
        """Send a prompt and return a structured response with token usage."""
        self._rate_limiter.wait()
        import ollama as ollama_lib

        kwargs = {
            "model": self._get_model(),
            "messages": [{"role": "user", "content": prompt}],
        }
        if self._base_url:
            client = ollama_lib.Client(host=self._base_url)
            response = client.chat(**kwargs)
        else:
            response = ollama_lib.chat(**kwargs)
        return LLMResponse(
            text=response["message"]["content"],
            input_tokens=response.get("prompt_eval_count", 0),
            output_tokens=response.get("eval_count", 0),
            model=response.get("model", self._get_model()),
        )

    def extract_rules(self, entry_text: str) -> list[ExtractedRule]:
        """Extract structured rules from buildlog entry text."""
        prompt = EXTRACT_RULES_PROMPT.format(text=entry_text)
        try:
            response = self._chat(prompt)
            parsed = _parse_json_response(response)
            if not isinstance(parsed, list):
                parsed = [parsed]
            return [ExtractedRule(**item) for item in parsed]
        except Exception as e:
            logger.warning("Ollama extraction failed: %s", e)
            return []

    def select_canonical(self, candidates: list[str]) -> str:
        """Given similar rules, produce the single best canonical form."""
        numbered = "\n".join(f"{i+1}. {c}" for i, c in enumerate(candidates))
        prompt = SELECT_CANONICAL_PROMPT.format(candidates=numbered)
        try:
            response = self._chat(prompt)
            return response.strip().strip('"').strip("'")
        except Exception as e:
            logger.warning("Ollama canonical selection failed: %s", e)
            return min(candidates, key=len)

    def score_rule(self, rule: str, context: str) -> RuleScoring:
        """Score a rule with severity/scope/applicability."""
        prompt = SCORE_RULE_PROMPT.format(rule=rule, context=context)
        try:
            response = self._chat(prompt)
            parsed = _parse_json_response(response)
            if isinstance(parsed, dict):
                return RuleScoring(
                    severity=parsed.get("severity", "info"),
                    scope=parsed.get("scope", "global"),
                    applicability=parsed.get("applicability", []),
                )
        except Exception as e:
            logger.warning("Ollama scoring failed: %s", e)
        return RuleScoring()


class AnthropicBackend:
    """LLM backend using Anthropic Claude API."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self._model = model or "claude-haiku-4-20250514"
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None
        self._rate_limiter = _RateLimiter()

    def __repr__(self) -> str:
        """Redact API key from repr to prevent exposure in logs/tracebacks."""
        return f"AnthropicBackend(model={self._model!r}, api_key=***)"

    def _get_client(self):
        """Lazy-load the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic package is required. Install with: pip install buildlog[anthropic]"
                )
            if not self._api_key:
                raise ValueError("ANTHROPIC_API_KEY is required for Anthropic backend")
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _chat(self, prompt: str) -> str:
        """Send a prompt to Claude and return the response text."""
        self._rate_limiter.wait()
        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def call(self, prompt: str) -> LLMResponse:
        """Send a prompt and return a structured response with token usage."""
        self._rate_limiter.wait()
        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        cached = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        return LLMResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            cached_tokens=cached,
        )

    def extract_rules(self, entry_text: str) -> list[ExtractedRule]:
        """Extract structured rules from buildlog entry text."""
        prompt = EXTRACT_RULES_PROMPT.format(text=entry_text)
        try:
            response = self._chat(prompt)
            parsed = _parse_json_response(response)
            if not isinstance(parsed, list):
                parsed = [parsed]
            return [ExtractedRule(**item) for item in parsed]
        except Exception as e:
            logger.warning("Anthropic extraction failed: %s", e)
            return []

    def select_canonical(self, candidates: list[str]) -> str:
        """Given similar rules, produce the single best canonical form."""
        numbered = "\n".join(f"{i+1}. {c}" for i, c in enumerate(candidates))
        prompt = SELECT_CANONICAL_PROMPT.format(candidates=numbered)
        try:
            response = self._chat(prompt)
            return response.strip().strip('"').strip("'")
        except Exception as e:
            logger.warning("Anthropic canonical selection failed: %s", e)
            return min(candidates, key=len)

    def score_rule(self, rule: str, context: str) -> RuleScoring:
        """Score a rule with severity/scope/applicability."""
        prompt = SCORE_RULE_PROMPT.format(rule=rule, context=context)
        try:
            response = self._chat(prompt)
            parsed = _parse_json_response(response)
            if isinstance(parsed, dict):
                return RuleScoring(
                    severity=parsed.get("severity", "info"),
                    scope=parsed.get("scope", "global"),
                    applicability=parsed.get("applicability", []),
                )
        except Exception as e:
            logger.warning("Anthropic scoring failed: %s", e)
        return RuleScoring()


# --- Registry ---

_PROVIDERS: dict[str, type] = {
    "ollama": OllamaBackend,
    "anthropic": AnthropicBackend,
}
# Public read-only view. Use register_provider() to add entries.
PROVIDERS: MappingProxyType[str, type] = MappingProxyType(_PROVIDERS)


def register_provider(name: str, cls: type) -> None:
    """Register a new LLM provider backend.

    This is the only sanctioned way to mutate the provider registry.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Provider name must be a non-empty string")
    _PROVIDERS[name] = cls


def get_llm_backend(
    config: LLMConfig | None = None,
    buildlog_dir: Path | None = None,
) -> LLMBackend | None:
    """Get an LLM backend using the provider cascade.

    Resolution order:
    1. Explicit config parameter (highest priority)
    2. Config file (.buildlog/config.yml)
    3. Auto-detect: Ollama -> Anthropic -> None

    Returns None if no provider is available (regex fallback).
    """
    # 1. Explicit config
    if config is None and buildlog_dir is not None:
        # 2. Config file
        config = LLMConfig.from_buildlog_config(buildlog_dir)

    if config is None:
        # 3. Auto-detect
        config = LLMConfig.auto_detect()

    if config is None:
        logger.info("No LLM provider available, using regex fallback")
        return None

    provider_cls = _PROVIDERS.get(config.provider)
    if provider_cls is None:
        logger.warning("Unknown LLM provider: %s", config.provider)
        return None

    try:
        kwargs: dict = {}
        if config.model:
            kwargs["model"] = config.model
        if config.provider == "ollama" and config.base_url:
            kwargs["base_url"] = config.base_url
        if config.provider == "anthropic" and config.api_key:
            kwargs["api_key"] = config.api_key

        backend = provider_cls(**kwargs)
        logger.info("Using LLM provider: %s", config.provider)
        return backend
    except Exception as e:
        logger.warning("Failed to initialize %s backend: %s", config.provider, e)
        return None
