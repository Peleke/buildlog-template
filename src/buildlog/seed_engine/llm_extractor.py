"""LLM-backed rule extraction for the seed engine pipeline.

Adapts LLMBackend.extract_rules() into the RuleExtractor interface,
bridging the LLM module with the seed engine's 4-step pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from buildlog.seed_engine.extractors import RuleExtractor
from buildlog.seed_engine.models import CandidateRule, Source

if TYPE_CHECKING:
    from buildlog.llm import LLMBackend

logger = logging.getLogger(__name__)

_PLACEHOLDER = "Not specified by LLM"


class LLMExtractor(RuleExtractor):
    """LLM-backed rule extraction from source content.

    Wraps any LLMBackend to produce CandidateRules with full
    defensibility fields. Fields the LLM doesn't populate get
    placeholder values so downstream validation passes.

    Usage:
        from buildlog.llm import OllamaBackend
        from buildlog.seed_engine.llm_extractor import LLMExtractor

        backend = OllamaBackend(model="llama3.2")
        extractor = LLMExtractor(backend, source_content={"https://...": "..."})

        rules = extractor.extract(source)
    """

    def __init__(
        self,
        backend: LLMBackend,
        source_content: dict[str, str] | None = None,
    ) -> None:
        """Initialize with an LLM backend.

        Args:
            backend: Any LLMBackend (Ollama, Anthropic, etc.).
            source_content: Optional map of source.url → text content.
                For sources that need pre-fetched content.
        """
        self._backend = backend
        self._source_content = source_content or {}

    def extract(self, source: Source) -> list[CandidateRule]:
        """Extract candidate rules from a source via LLM.

        Resolution for content:
        1. source_content dict (keyed by source.url)
        2. source.description as fallback

        Returns empty list on LLM failure (logged, not raised).
        """
        content = self._source_content.get(source.url, "").strip()
        if not content:
            content = source.description.strip()
        if not content:
            logger.warning("No content for source %s, skipping", source.name)
            return []

        try:
            extracted = self._backend.extract_rules(content)
        except Exception:
            logger.exception("LLM extraction failed for %s", source.name)
            return []

        candidates: list[CandidateRule] = []
        for er in extracted:
            if not er.rule.strip():
                continue

            metadata: dict[str, Any] = {
                "extractor": "llm",
                "severity": er.severity,
                "scope": er.scope,
            }
            # Include backend class name (public info only)
            metadata["backend_type"] = type(self._backend).__name__

            candidates.append(
                CandidateRule(
                    rule=er.rule,
                    context=er.context or _PLACEHOLDER,
                    antipattern=er.antipattern or _PLACEHOLDER,
                    rationale=er.rationale or _PLACEHOLDER,
                    source=source,
                    raw_tags=[er.category] + er.applicability,
                    confidence=0.7,
                    metadata=metadata,
                )
            )

        logger.info("LLM extracted %d rules from %s", len(candidates), source.name)
        return candidates

    def validate(self, rule: CandidateRule) -> list[str]:
        """Validate a candidate rule.

        Warns on placeholder defensibility fields.
        Requires non-empty rule text.
        """
        issues: list[str] = []
        if not rule.rule.strip():
            issues.append("Rule text is empty")
        if rule.context == _PLACEHOLDER:
            issues.append("Context is LLM placeholder — consider enriching")
        if rule.antipattern == _PLACEHOLDER:
            issues.append("Antipattern is LLM placeholder — consider enriching")
        if rule.rationale == _PLACEHOLDER:
            issues.append("Rationale is LLM placeholder — consider enriching")
        return issues
