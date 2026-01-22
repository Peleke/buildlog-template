"""Data models for the seed engine pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(Enum):
    """Type of authoritative source."""

    REFERENCE_DOC = "reference_doc"  # OWASP, RFC, official docs
    BLOG_POST = "blog_post"  # Google Testing Blog, Fowler
    BOOK = "book"  # Clean Code, xUnit Patterns
    STANDARD = "standard"  # ISO, IEEE standards
    CHEATSHEET = "cheatsheet"  # OWASP cheatsheets


@dataclass
class Source:
    """An authoritative source for rule extraction.

    Step 1 output: Sources define where domain knowledge comes from.
    Each source should be citable and defensible.
    """

    name: str
    url: str
    source_type: SourceType
    domain: str  # e.g., "security", "testing", "code-quality"
    description: str = ""
    sections: list[str] = field(default_factory=list)  # Specific sections to extract

    def to_reference(self) -> dict[str, str]:
        """Convert to seed file reference format."""
        return {"url": self.url, "title": self.name}


@dataclass
class CandidateRule:
    """A rule extracted from a source, before categorization.

    Step 2 output: Raw rule with all defensibility fields.
    May not yet be categorized or tagged.
    """

    rule: str  # The prescription
    context: str  # When it applies
    antipattern: str  # What violation looks like
    rationale: str  # Why it matters
    source: Source  # Where it came from
    raw_tags: list[str] = field(default_factory=list)  # Tags from extraction
    confidence: float = 1.0  # Extraction confidence (1.0 for manual)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_complete(self) -> bool:
        """Check if all defensibility fields are populated."""
        return bool(
            self.rule.strip()
            and self.context.strip()
            and self.antipattern.strip()
            and self.rationale.strip()
        )


@dataclass
class CategorizedRule:
    """A rule after categorization and tagging.

    Step 3 output: Ready for seed file generation.
    Has final category and tags assigned.
    """

    rule: str
    category: str  # Final category (e.g., "testing", "security")
    context: str
    antipattern: str
    rationale: str
    tags: list[str]  # Final tags
    references: list[dict[str, str]]  # [{"url": ..., "title": ...}]
    confidence: float = 1.0

    @classmethod
    def from_candidate(
        cls,
        candidate: CandidateRule,
        category: str,
        tags: list[str],
    ) -> CategorizedRule:
        """Create from a candidate rule with assigned category/tags."""
        return cls(
            rule=candidate.rule,
            category=category,
            context=candidate.context,
            antipattern=candidate.antipattern,
            rationale=candidate.rationale,
            tags=tags,
            references=[candidate.source.to_reference()],
            confidence=candidate.confidence,
        )

    def to_seed_dict(self) -> dict[str, Any]:
        """Convert to seed file rule format."""
        return {
            "rule": self.rule,
            "category": self.category,
            "context": self.context,
            "antipattern": self.antipattern,
            "rationale": self.rationale,
            "tags": self.tags,
            "references": self.references,
        }
