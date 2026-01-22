"""Rule categorizers for Step 3 of the seed engine pipeline.

Categorizers take candidate rules and assign final categories and tags.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from buildlog.seed_engine.models import CandidateRule, CategorizedRule


class Categorizer(ABC):
    """Protocol for categorizing rules.

    Implementations:
    - TagBasedCategorizer: Category from tags/keywords
    - MappingCategorizer: Explicit source→category mapping
    """

    @abstractmethod
    def categorize(self, rule: CandidateRule) -> CategorizedRule:
        """Assign category and final tags to a rule.

        Args:
            rule: The candidate rule to categorize.

        Returns:
            Categorized rule ready for seed generation.
        """
        ...


@dataclass
class CategoryMapping:
    """Mapping from keywords/tags to category."""

    category: str
    keywords: list[str]  # If any of these appear in tags/rule, assign this category
    priority: int = 0  # Higher priority wins on conflicts


class TagBasedCategorizer(Categorizer):
    """Categorize rules based on their tags and keywords.

    Usage:
        categorizer = TagBasedCategorizer(
            default_category="testing",
            mappings=[
                CategoryMapping("coverage", ["coverage", "untested"]),
                CategoryMapping("isolation", ["flaky", "order", "hermetic"]),
                CategoryMapping("assertions", ["assert", "expect", "verify"]),
            ],
            tag_normalizer=lambda t: t.lower().replace("-", "_"),
        )

        categorized = categorizer.categorize(candidate_rule)
    """

    def __init__(
        self,
        default_category: str,
        mappings: list[CategoryMapping] | None = None,
        tag_normalizer: Callable[[str], str] | None = None,
        additional_tags: list[str] | None = None,
    ) -> None:
        self.default_category = default_category
        self.mappings = sorted(mappings or [], key=lambda m: m.priority, reverse=True)
        self.tag_normalizer = tag_normalizer or (lambda t: t.lower())
        self.additional_tags = additional_tags or []

    def categorize(self, rule: CandidateRule) -> CategorizedRule:
        """Assign category based on tag matching."""
        # Normalize tags
        normalized_tags = [self.tag_normalizer(t) for t in rule.raw_tags]

        # Also check rule text for keywords
        rule_text_lower = rule.rule.lower()

        # Find matching category
        category = self.default_category
        for mapping in self.mappings:
            for keyword in mapping.keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in normalized_tags or keyword_lower in rule_text_lower:
                    category = mapping.category
                    break
            else:
                continue
            break

        # Build final tags
        final_tags = list(set(normalized_tags + self.additional_tags))

        return CategorizedRule.from_candidate(
            candidate=rule,
            category=category,
            tags=final_tags,
        )


class MappingCategorizer(Categorizer):
    """Categorize rules via explicit source→category mapping.

    Useful when sources map directly to categories
    (e.g., OWASP A03 → "injection").

    Usage:
        categorizer = MappingCategorizer(
            source_category_map={
                "https://owasp.org/Top10/A03": "injection",
                "https://owasp.org/Top10/A01": "access-control",
            },
            default_category="security",
        )
    """

    def __init__(
        self,
        source_category_map: dict[str, str],
        default_category: str,
        tag_transform: Callable[[list[str]], list[str]] | None = None,
    ) -> None:
        self.source_category_map = source_category_map
        self.default_category = default_category
        self.tag_transform = tag_transform or (lambda tags: tags)

    def categorize(self, rule: CandidateRule) -> CategorizedRule:
        """Assign category based on source URL."""
        # Find category by matching source URL prefix
        category = self.default_category
        for url_prefix, cat in self.source_category_map.items():
            if rule.source.url.startswith(url_prefix):
                category = cat
                break

        final_tags = self.tag_transform(rule.raw_tags)

        return CategorizedRule.from_candidate(
            candidate=rule,
            category=category,
            tags=final_tags,
        )
