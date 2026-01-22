"""Seed Engine - Formalized pipeline for creating reviewer personas.

The seed engine abstracts the 4-step process for bootstrapping
defensible reviewer personas from authoritative domain sources:

    1. SOURCE IDENTIFICATION - Define authoritative sources
    2. RULE EXTRACTION - Extract candidate rules with defensibility fields
    3. CATEGORIZATION - Map rules to persona concern categories
    4. SEED GENERATION - Output validated YAML seed file

Usage:
    from buildlog.seed_engine import Pipeline, Source, SourceType

    # Define sources
    sources = [
        Source(
            name="OWASP Top 10",
            url="https://owasp.org/Top10/",
            source_type=SourceType.REFERENCE_DOC,
            domain="security",
        )
    ]

    # Run pipeline
    pipeline = Pipeline(persona="security_karen")
    seed_file = pipeline.run(sources)
"""

from buildlog.seed_engine.categorizers import (
    Categorizer,
    CategoryMapping,
    TagBasedCategorizer,
)
from buildlog.seed_engine.extractors import ManualExtractor, RuleExtractor
from buildlog.seed_engine.generators import SeedGenerator
from buildlog.seed_engine.models import (
    CandidateRule,
    CategorizedRule,
    Source,
    SourceType,
)
from buildlog.seed_engine.pipeline import Pipeline
from buildlog.seed_engine.sources import (
    FetchStatus,
    SourceEntry,
    SourceFetcher,
    SourceManifest,
    url_to_cache_filename,
)

__all__ = [
    # Models
    "Source",
    "SourceType",
    "CandidateRule",
    "CategorizedRule",
    # Pipeline
    "Pipeline",
    # Extractors
    "RuleExtractor",
    "ManualExtractor",
    # Categorizers
    "Categorizer",
    "TagBasedCategorizer",
    "CategoryMapping",
    # Generators
    "SeedGenerator",
    # Sources
    "FetchStatus",
    "SourceEntry",
    "SourceManifest",
    "SourceFetcher",
    "url_to_cache_filename",
]
