#!/usr/bin/env python3
"""Create the Test Terrorist source manifest.

Defines all canonical sources for the Test Terrorist persona.
Run once to create the manifest, then incrementally fetch/populate.

Usage:
    uv run python scripts/create_test_terrorist_manifest.py
"""

from pathlib import Path

from buildlog.seed_engine import Source, SourceManifest, SourceType

# ============================================================================
# CANONICAL SOURCES FOR TEST TERRORIST
# ============================================================================

SOURCES = [
    # -------------------------------------------------------------------------
    # TESTING PHILOSOPHY / PYRAMID
    # -------------------------------------------------------------------------
    Source(
        name="Google Testing Blog - Test Sizes",
        url="https://testing.googleblog.com/2010/12/test-sizes.html",
        source_type=SourceType.BLOG_POST,
        domain="testing-philosophy",
        description="Google's definition of small/medium/large tests",
        sections=["test-sizes", "hermetic-tests"],
    ),
    Source(
        name="Google Testing Blog - Just Say No to More E2E Tests",
        url="https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html",
        source_type=SourceType.BLOG_POST,
        domain="testing-philosophy",
        description="The testing pyramid and why E2E tests are costly",
        sections=["test-pyramid", "cost-of-e2e"],
    ),
    Source(
        name="Martin Fowler - Testing Pyramid",
        url="https://martinfowler.com/articles/practical-test-pyramid.html",
        source_type=SourceType.REFERENCE_DOC,
        domain="testing-philosophy",
        description="Comprehensive guide to the test pyramid",
        sections=["unit-tests", "integration-tests", "e2e-tests", "test-doubles"],
    ),
    Source(
        name="Martin Fowler - Test Double",
        url="https://martinfowler.com/bliki/TestDouble.html",
        source_type=SourceType.REFERENCE_DOC,
        domain="testing-philosophy",
        description="Mocks, stubs, fakes, spies, dummies",
        sections=["test-doubles"],
    ),
    # -------------------------------------------------------------------------
    # PROPERTY-BASED TESTING
    # -------------------------------------------------------------------------
    Source(
        name="Hypothesis Documentation",
        url="https://hypothesis.readthedocs.io/en/latest/",
        source_type=SourceType.REFERENCE_DOC,
        domain="property-testing",
        description="Property-based testing for Python",
        sections=["quickstart", "settings", "strategies", "stateful-testing"],
    ),
    Source(
        name="Hypothesis - What is Property-Based Testing",
        url="https://hypothesis.readthedocs.io/en/latest/quickstart.html",
        source_type=SourceType.REFERENCE_DOC,
        domain="property-testing",
        description="Introduction to property-based testing concepts",
        sections=["properties", "shrinking", "examples"],
    ),
    Source(
        name="PropEr Testing (Erlang/Elixir)",
        url="https://propertesting.com/",
        source_type=SourceType.REFERENCE_DOC,
        domain="property-testing",
        description="Property testing concepts (language-agnostic principles)",
        sections=["properties", "generators"],
    ),
    # -------------------------------------------------------------------------
    # METAMORPHIC TESTING
    # -------------------------------------------------------------------------
    Source(
        name="Metamorphic Testing - Chen et al. Survey",
        url="https://www.sciencedirect.com/science/article/pii/S0950584918300016",
        source_type=SourceType.STANDARD,
        domain="metamorphic",
        description="Comprehensive survey on metamorphic testing (2018)",
        sections=["metamorphic-relations", "test-oracle-problem", "applications"],
    ),
    Source(
        name="Metamorphic Testing - A Review (Segura et al.)",
        url="https://ieeexplore.ieee.org/document/7422146",
        source_type=SourceType.STANDARD,
        domain="metamorphic",
        description="IEEE TSE review of metamorphic testing",
        sections=["mr-identification", "case-studies"],
    ),
    # -------------------------------------------------------------------------
    # STATISTICAL / DISTRIBUTION TESTING
    # -------------------------------------------------------------------------
    Source(
        name="Great Expectations Documentation",
        url="https://docs.greatexpectations.io/docs/",
        source_type=SourceType.REFERENCE_DOC,
        domain="statistical",
        description="Data validation and profiling framework",
        sections=["expectations", "data-docs", "checkpoints"],
    ),
    Source(
        name="Pandera Documentation",
        url="https://pandera.readthedocs.io/en/stable/",
        source_type=SourceType.REFERENCE_DOC,
        domain="statistical",
        description="Statistical data validation for pandas",
        sections=["schemas", "checks", "hypothesis-integration"],
    ),
    Source(
        name="Evidently AI - ML Monitoring",
        url="https://docs.evidentlyai.com/",
        source_type=SourceType.REFERENCE_DOC,
        domain="statistical",
        description="Data drift and model monitoring",
        sections=["data-drift", "model-performance", "reports"],
    ),
    # -------------------------------------------------------------------------
    # LLM TESTING (GAPS - FLAG ONLY)
    # -------------------------------------------------------------------------
    Source(
        name="Guardrails AI Documentation",
        url="https://www.guardrailsai.com/docs/concepts/guard",
        source_type=SourceType.REFERENCE_DOC,
        domain="llm-testing",
        description="LLM output validation framework - GAP FLAG",
        sections=["validators", "guards", "structured-output"],
    ),
    Source(
        name="DeepEval Documentation",
        url="https://docs.confident-ai.com/docs/getting-started",
        source_type=SourceType.REFERENCE_DOC,
        domain="llm-testing",
        description="LLM evaluation framework - GAP FLAG",
        sections=["metrics", "test-cases", "benchmarks"],
    ),
    Source(
        name="LangSmith Evaluation",
        url="https://docs.smith.langchain.com/evaluation",
        source_type=SourceType.REFERENCE_DOC,
        domain="llm-testing",
        description="LangChain's evaluation tools - GAP FLAG",
        sections=["datasets", "evaluators", "experiments"],
    ),
    # -------------------------------------------------------------------------
    # ANTI-PATTERNS / TEST SMELLS
    # -------------------------------------------------------------------------
    Source(
        name="xUnit Test Patterns - Test Smells",
        url="http://xunitpatterns.com/Test%20Smells.html",
        source_type=SourceType.BOOK,
        domain="anti-patterns",
        description="Meszaros' catalog of test smells",
        sections=["fragile-test", "obscure-test", "slow-test", "erratic-test"],
    ),
    Source(
        name="Google Testing Blog - Test Flakiness",
        url="https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html",
        source_type=SourceType.BLOG_POST,
        domain="anti-patterns",
        description="How Google handles flaky tests",
        sections=["flaky-tests", "quarantine", "deflaking"],
    ),
    # -------------------------------------------------------------------------
    # TOOLING / PYTEST
    # -------------------------------------------------------------------------
    Source(
        name="pytest Documentation",
        url="https://docs.pytest.org/en/stable/",
        source_type=SourceType.REFERENCE_DOC,
        domain="tooling",
        description="pytest testing framework",
        sections=["fixtures", "parametrize", "markers", "plugins"],
    ),
    Source(
        name="pytest - Good Integration Practices",
        url="https://docs.pytest.org/en/stable/explanation/goodpractices.html",
        source_type=SourceType.REFERENCE_DOC,
        domain="tooling",
        description="pytest best practices",
        sections=["test-layout", "src-layout", "tox"],
    ),
]


def main():
    """Create and save the Test Terrorist source manifest."""
    base_dir = Path(".buildlog/sources/test_terrorist")

    # Create manifest
    manifest = SourceManifest(persona="test_terrorist")

    for source in SOURCES:
        manifest.add_source(source)
        print(f"  Added: {source.name}")

    # Save
    manifest_path = manifest.save(base_dir)
    print(f"\nManifest saved to: {manifest_path}")

    # Summary
    summary = manifest.summary()
    print("\nSummary:")
    print(f"  Total sources: {summary['total']}")
    print(f"  Pending fetch: {summary['pending']}")
    print(f"  Cached: {summary['cached']}")

    # Domain breakdown
    domains = {}
    for entry in manifest.entries:
        domain = entry.source.domain
        domains[domain] = domains.get(domain, 0) + 1

    print("\nBy domain:")
    for domain, count in sorted(domains.items()):
        print(f"  {domain}: {count}")


if __name__ == "__main__":
    main()
