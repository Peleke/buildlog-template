"""Rule extractors for Step 2 of the seed engine pipeline.

Extractors take sources and produce candidate rules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from buildlog.seed_engine.models import CandidateRule, Source


class RuleExtractor(ABC):
    """Protocol for extracting rules from sources.

    Implementations:
    - ManualExtractor: Human-curated rules (highest quality)
    - LLMExtractor: LLM-assisted extraction (future)
    - StructuredExtractor: Parse structured docs like OWASP (future)
    """

    @abstractmethod
    def extract(self, source: Source) -> list[CandidateRule]:
        """Extract candidate rules from a source.

        Args:
            source: The source to extract rules from.

        Returns:
            List of candidate rules with defensibility fields.
        """
        ...

    @abstractmethod
    def validate(self, rule: CandidateRule) -> list[str]:
        """Validate a candidate rule, returning any issues.

        Args:
            rule: The rule to validate.

        Returns:
            List of validation issues (empty if valid).
        """
        ...


class ManualExtractor(RuleExtractor):
    """Manual rule extraction via human curation.

    This is the gold standard—humans read the source and
    extract rules with full defensibility metadata.

    Usage:
        extractor = ManualExtractor()

        # Register rules for a source
        extractor.register(
            source=google_testing_blog,
            rules=[
                CandidateRule(
                    rule="Tests must not depend on execution order",
                    context="Test suites with multiple tests",
                    antipattern="Test A sets state that Test B relies on",
                    rationale="Order-dependent tests are flaky",
                    source=google_testing_blog,
                    raw_tags=["isolation", "flaky"],
                )
            ]
        )

        # Extract returns registered rules
        rules = extractor.extract(google_testing_blog)
    """

    def __init__(self) -> None:
        self._rules_by_source: dict[str, list[CandidateRule]] = {}

    def register(self, source: Source, rules: list[CandidateRule]) -> None:
        """Register manually curated rules for a source.

        Args:
            source: The source these rules come from.
            rules: The curated rules.
        """
        # Validate all rules are complete
        for rule in rules:
            issues = self.validate(rule)
            if issues:
                raise ValueError(
                    f"Invalid rule '{rule.rule[:50]}...': {'; '.join(issues)}"
                )
        self._rules_by_source[source.url] = rules

    def extract(self, source: Source) -> list[CandidateRule]:
        """Return registered rules for this source."""
        return self._rules_by_source.get(source.url, [])

    def validate(self, rule: CandidateRule) -> list[str]:
        """Validate defensibility fields are populated."""
        issues = []
        if not rule.rule.strip():
            issues.append("Rule text is empty")
        if not rule.context.strip():
            issues.append("Context is required for defensibility")
        if not rule.antipattern.strip():
            issues.append("Antipattern is required for defensibility")
        if not rule.rationale.strip():
            issues.append("Rationale is required for defensibility")
        return issues


class FunctionExtractor(RuleExtractor):
    """Extraction via custom function (for structured sources).

    Allows plugging in custom extraction logic for sources
    with known structure (e.g., OWASP pages, API docs).

    Usage:
        def extract_from_owasp(source: Source) -> list[CandidateRule]:
            # Custom parsing logic for OWASP format
            ...

        extractor = FunctionExtractor(extract_from_owasp)
        rules = extractor.extract(owasp_source)
    """

    def __init__(
        self,
        extract_fn: Callable[[Source], list[CandidateRule]],
        validate_fn: Callable[[CandidateRule], list[str]] | None = None,
    ) -> None:
        self._extract_fn = extract_fn
        self._validate_fn = validate_fn or self._default_validate

    def extract(self, source: Source) -> list[CandidateRule]:
        """Run the custom extraction function."""
        return self._extract_fn(source)

    def validate(self, rule: CandidateRule) -> list[str]:
        """Run the validation function."""
        return self._validate_fn(rule)

    def _default_validate(self, rule: CandidateRule) -> list[str]:
        """Default validation: check completeness."""
        if not rule.is_complete():
            return ["Rule is missing required defensibility fields"]
        return []
