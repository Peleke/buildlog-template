"""Pipeline orchestration for the seed engine.

The Pipeline ties together all 4 steps:
1. Source identification (input)
2. Rule extraction
3. Categorization
4. Seed generation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from buildlog.seed_engine.categorizers import Categorizer, TagBasedCategorizer
from buildlog.seed_engine.extractors import ManualExtractor, RuleExtractor
from buildlog.seed_engine.generators import SeedGenerator
from buildlog.seed_engine.models import CandidateRule, CategorizedRule, Source

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of running the seed engine pipeline."""

    persona: str
    sources: list[Source]
    candidates: list[CandidateRule]
    categorized: list[CategorizedRule]
    seed_data: dict[str, Any]
    output_path: Path | None = None

    @property
    def rule_count(self) -> int:
        return len(self.categorized)

    @property
    def source_count(self) -> int:
        return len(self.sources)

    def summary(self) -> str:
        """Human-readable summary of the pipeline run."""
        lines = [
            f"Seed Engine Pipeline Result: {self.persona}",
            f"  Sources: {self.source_count}",
            f"  Candidates extracted: {len(self.candidates)}",
            f"  Rules categorized: {self.rule_count}",
        ]
        if self.output_path:
            lines.append(f"  Output: {self.output_path}")
        return "\n".join(lines)


@dataclass
class Pipeline:
    """The seed engine pipeline.

    Orchestrates the 4-step process for creating reviewer personas:

    1. SOURCES → Define authoritative domain sources
    2. EXTRACT → Pull rules with defensibility fields
    3. CATEGORIZE → Assign categories and tags
    4. GENERATE → Output validated YAML seed file

    Usage:
        # Create pipeline with default components
        pipeline = Pipeline(
            persona="test_terrorist",
            default_category="testing",
        )

        # Or customize each step
        pipeline = Pipeline(
            persona="test_terrorist",
            extractor=MyCustomExtractor(),
            categorizer=MyCustomCategorizer(),
            generator=SeedGenerator(persona="test_terrorist", version=1),
        )

        # Run the pipeline
        result = pipeline.run(sources, output_dir=Path(".buildlog/seeds"))
    """

    persona: str
    default_category: str = "general"
    version: int = 1
    extractor: RuleExtractor | None = None
    categorizer: Categorizer | None = None
    generator: SeedGenerator | None = None

    def __post_init__(self) -> None:
        # Set defaults if not provided
        if self.extractor is None:
            self.extractor = ManualExtractor()
        if self.categorizer is None:
            self.categorizer = TagBasedCategorizer(
                default_category=self.default_category
            )
        if self.generator is None:
            self.generator = SeedGenerator(
                persona=self.persona,
                version=self.version,
            )

    def run(
        self,
        sources: list[Source],
        output_dir: Path | None = None,
        write: bool = True,
    ) -> PipelineResult:
        """Run the full pipeline.

        Args:
            sources: Step 1 - The authoritative sources to extract from.
            output_dir: Where to write the seed file.
            write: Whether to write the seed file to disk.

        Returns:
            PipelineResult with all intermediate and final outputs.
        """
        logger.info(f"Starting seed engine pipeline for '{self.persona}'")
        logger.info(f"Processing {len(sources)} sources")

        # These are guaranteed set by __post_init__
        assert self.extractor is not None
        assert self.categorizer is not None
        assert self.generator is not None

        # Step 2: Extract rules from each source
        candidates: list[CandidateRule] = []
        for source in sources:
            extracted = self.extractor.extract(source)
            logger.info(f"  Extracted {len(extracted)} rules from {source.name}")
            candidates.extend(extracted)

        logger.info(f"Total candidates: {len(candidates)}")

        # Step 3: Categorize each rule
        categorized: list[CategorizedRule] = []
        for candidate in candidates:
            cat_rule = self.categorizer.categorize(candidate)
            categorized.append(cat_rule)

        logger.info(f"Categorized {len(categorized)} rules")

        # Step 4: Generate seed file
        self.generator.output_dir = output_dir
        seed_data = self.generator.generate(categorized)

        # Optionally write to disk
        output_path = None
        if write and output_dir:
            output_path = self.generator.write(seed_data)
            logger.info(f"Wrote seed file to {output_path}")

        return PipelineResult(
            persona=self.persona,
            sources=sources,
            candidates=candidates,
            categorized=categorized,
            seed_data=seed_data,
            output_path=output_path,
        )

    def validate_sources(self, sources: list[Source]) -> list[str]:
        """Validate that sources are properly defined.

        Args:
            sources: The sources to validate.

        Returns:
            List of validation issues (empty if valid).
        """
        issues = []
        for i, source in enumerate(sources):
            prefix = f"Source {i + 1} ({source.name})"
            if not source.name.strip():
                issues.append(f"{prefix}: Missing name")
            if not source.url.strip():
                issues.append(f"{prefix}: Missing URL")
            if not source.domain.strip():
                issues.append(f"{prefix}: Missing domain")
        return issues

    def dry_run(self, sources: list[Source]) -> dict[str, Any]:
        """Run pipeline without writing, returning preview.

        Useful for validation before committing to disk.
        """
        result = self.run(sources, write=False)
        return {
            "persona": result.persona,
            "rule_count": result.rule_count,
            "source_count": result.source_count,
            "categories": list(set(r.category for r in result.categorized)),
            "sample_rules": [
                {"rule": r.rule, "category": r.category} for r in result.categorized[:3]
            ],
        }
