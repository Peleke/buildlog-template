#!/usr/bin/env python3
"""Generate the Test Terrorist seed file from curated rules.

Uses the seed engine pipeline to create a validated seed file
with rules across all Test Terrorist concern categories.

Usage:
    uv run python scripts/generate_test_terrorist_seeds.py
"""

from pathlib import Path

from buildlog.seed_engine import (
    CandidateRule,
    CategoryMapping,
    ManualExtractor,
    Pipeline,
    Source,
    SourceType,
    TagBasedCategorizer,
)

# ============================================================================
# CURATED RULES BY CATEGORY
# ============================================================================


def get_coverage_rules(sources: dict[str, Source]) -> list[CandidateRule]:
    """Rules about code coverage and test existence."""
    return [
        CandidateRule(
            rule="Every public API must have at least one happy path test",
            context="New endpoints, public functions, exported modules",
            antipattern="Shipping code with no tests; 'I'll add tests later'; PRs without test changes",
            rationale="Untested code is legacy code the moment it's merged. Tests are executable documentation.",
            source=sources["google_pyramid"],
            raw_tags=["coverage", "public-api", "happy-path"],
        ),
        CandidateRule(
            rule="Critical paths require edge case and error path coverage",
            context="Payment flows, authentication, data mutations, external integrations",
            antipattern="Only happy path tests for critical code; no error handling tests",
            rationale="Edge cases in critical paths cause production incidents. Murphy's law applies.",
            source=sources["fowler_pyramid"],
            raw_tags=["coverage", "critical-path", "edge-cases"],
        ),
        CandidateRule(
            rule="New bug fixes must include a regression test",
            context="Any bug fix PR or commit",
            antipattern="Fixing bugs without adding tests that would have caught them",
            rationale="A bug that escapes once will escape again. Regression tests prevent recurrence.",
            source=sources["google_pyramid"],
            raw_tags=["coverage", "regression", "bug-fix"],
        ),
    ]


def get_isolation_rules(sources: dict[str, Source]) -> list[CandidateRule]:
    """Rules about test isolation and hermeticity."""
    return [
        CandidateRule(
            rule="Tests must not depend on execution order",
            context="Test suites with multiple tests, shared fixtures, database state",
            antipattern="Test A creates data that Test B asserts on; tests fail when run individually",
            rationale="Order-dependent tests are flaky and hide real failures. Each test must be hermetic.",
            source=sources["google_sizes"],
            raw_tags=["isolation", "hermetic", "order-independent"],
        ),
        CandidateRule(
            rule="Tests must clean up after themselves",
            context="Tests using databases, files, external services, global state",
            antipattern="Tests leaving data in shared resources; no teardown; assuming clean state",
            rationale="Test pollution causes cascading failures and makes debugging impossible.",
            source=sources["google_sizes"],
            raw_tags=["isolation", "cleanup", "teardown"],
        ),
        CandidateRule(
            rule="Mock external dependencies at test boundaries",
            context="Tests calling APIs, databases, file systems, network services",
            antipattern="Real network calls in unit tests; tests that require running services",
            rationale="External dependencies make tests slow, flaky, and expensive. Mock at boundaries.",
            source=sources["fowler_doubles"],
            raw_tags=["isolation", "mocking", "boundaries"],
        ),
    ]


def get_assertions_rules(sources: dict[str, Source]) -> list[CandidateRule]:
    """Rules about meaningful assertions."""
    return [
        CandidateRule(
            rule="Every test must have at least one meaningful assertion",
            context="All test functions",
            antipattern="Tests that only call code without asserting; assert True; empty test bodies",
            rationale="A test without assertions is not a test. It's a false sense of security.",
            source=sources["xunit_smells"],
            raw_tags=["assertions", "meaningful", "no-pass-through"],
        ),
        CandidateRule(
            rule="Assert on behavior, not implementation details",
            context="Unit tests, refactoring scenarios",
            antipattern="Asserting on private method calls; testing internal state; mock call counts",
            rationale="Implementation-coupled tests break on refactoring. Test the contract, not the code.",
            source=sources["fowler_pyramid"],
            raw_tags=["assertions", "behavior", "contract"],
        ),
    ]


def get_structure_rules(sources: dict[str, Source]) -> list[CandidateRule]:
    """Rules about test structure and organization."""
    return [
        CandidateRule(
            rule="Follow Arrange-Act-Assert (AAA) pattern",
            context="All test functions",
            antipattern="Interleaved setup and assertions; multiple acts per test; unclear test phases",
            rationale="AAA makes tests readable and debuggable. One logical assertion per test.",
            source=sources["xunit_smells"],
            raw_tags=["structure", "aaa", "readability"],
        ),
        CandidateRule(
            rule="Test names should describe the scenario and expected outcome",
            context="Test function naming",
            antipattern="test_1, test_function, test_it_works; names that don't explain the test",
            rationale="Test names are documentation. A failing test name should tell you what broke.",
            source=sources["pytest_practices"],
            raw_tags=["structure", "naming", "documentation"],
        ),
    ]


def get_property_rules(sources: dict[str, Source]) -> list[CandidateRule]:
    """Rules about property-based testing."""
    return [
        CandidateRule(
            rule="Use property-based testing for functions with clear invariants",
            context="Serializers, parsers, encoders/decoders, sorting, mathematical operations",
            antipattern="Only example-based tests for encode/decode pairs; hand-picked edge cases",
            rationale="Property tests generate thousands of examples, finding edge cases humans miss.",
            source=sources["hypothesis"],
            raw_tags=["property", "invariants", "hypothesis"],
        ),
        CandidateRule(
            rule="Define roundtrip properties for serialization code",
            context="JSON, protobuf, custom serializers, data transformation pipelines",
            antipattern="Testing serialize and deserialize separately with fixed examples",
            rationale="decode(encode(x)) == x is a universal property. Hypothesis finds corner cases.",
            source=sources["hypothesis"],
            raw_tags=["property", "roundtrip", "serialization"],
        ),
    ]


def get_metamorphic_rules(sources: dict[str, Source]) -> list[CandidateRule]:
    """Rules about metamorphic testing."""
    return [
        CandidateRule(
            rule="Apply metamorphic relations when test oracles are unavailable",
            context="ML models, search engines, optimization algorithms, complex computations",
            antipattern="No testing because 'we don't know the right answer'; only manual inspection",
            rationale="Metamorphic testing validates input-output relationships without ground truth.",
            source=sources["metamorphic_chen"],
            raw_tags=["metamorphic", "oracle-free", "ml"],
        ),
        CandidateRule(
            rule="Define permutation invariance for order-independent operations",
            context="Aggregations, set operations, commutative functions",
            antipattern="Testing with single fixed input order; assuming order doesn't matter",
            rationale="sum([1,2,3]) == sum([3,1,2]) is a metamorphic relation that catches bugs.",
            source=sources["metamorphic_chen"],
            raw_tags=["metamorphic", "permutation", "invariance"],
        ),
    ]


def get_statistical_rules(sources: dict[str, Source]) -> list[CandidateRule]:
    """Rules about statistical and distribution testing."""
    return [
        CandidateRule(
            rule="Validate data distributions at pipeline boundaries",
            context="ETL pipelines, ML feature stores, data ingestion, API responses",
            antipattern="Assuming input data matches expected distribution; no schema validation",
            rationale="Distribution drift breaks models silently. Validate expectations at boundaries.",
            source=sources["great_expectations"],
            raw_tags=["statistical", "distribution", "drift"],
        ),
        CandidateRule(
            rule="Define and enforce data contracts with schemas",
            context="Data pipelines, API integrations, database migrations",
            antipattern="Implicit schemas; duck typing for data; hoping fields exist",
            rationale="Schema validation catches contract violations before they cause failures.",
            source=sources["pandera"],
            raw_tags=["statistical", "schema", "contracts"],
        ),
    ]


def get_llm_testing_rules(sources: dict[str, Source]) -> list[CandidateRule]:
    """Rules about LLM testing - GAP FLAGS only."""
    return [
        CandidateRule(
            rule="LLM outputs require structured validation beyond string matching",
            context="Any code using LLM-generated content in production paths",
            antipattern="No validation; trusting raw LLM output; regex-only validation",
            rationale=(
                "[GAP] Standard test frameworks don't cover LLM eval. "
                "See Guardrails/DeepEval for emerging patterns. "
                "This is a known gap requiring specialized tooling."
            ),
            source=sources["guardrails"],
            raw_tags=["llm-testing", "gap", "emerging", "validation"],
        ),
        CandidateRule(
            rule="LLM-based features need evaluation datasets and metrics",
            context="RAG systems, chatbots, content generation, code assistants",
            antipattern="Vibes-based testing; manual spot checks; no regression tracking",
            rationale=(
                "[GAP] LLM behavior is non-deterministic. "
                "Evaluation datasets with metrics enable regression detection. "
                "Tooling is immature."
            ),
            source=sources["deepeval"],
            raw_tags=["llm-testing", "gap", "emerging", "evaluation"],
        ),
    ]


def get_antipattern_rules(sources: dict[str, Source]) -> list[CandidateRule]:
    """Rules about test anti-patterns and smells."""
    return [
        CandidateRule(
            rule="Flaky tests must be fixed or quarantined immediately",
            context="CI pipelines, test suites with intermittent failures",
            antipattern="Rerunning CI until green; ignoring flaky tests; 'it works on my machine'",
            rationale="Flaky tests erode trust in the test suite. A flaky test is worse than no test.",
            source=sources["google_flaky"],
            raw_tags=["anti-patterns", "flaky", "ci"],
        ),
        CandidateRule(
            rule="Tests should run in under 10 seconds for fast feedback",
            context="Unit test suites, developer workflows, pre-commit hooks",
            antipattern="Minute-long test suites; 'just run CI'; tests that require coffee breaks",
            rationale="Slow tests don't get run. Fast feedback enables TDD and catches bugs early.",
            source=sources["google_sizes"],
            raw_tags=["anti-patterns", "slow-tests", "feedback"],
        ),
        CandidateRule(
            rule="Avoid testing implementation details that change frequently",
            context="Refactoring scenarios, internal APIs, private methods",
            antipattern="Tests break on every refactor; testing private method behavior",
            rationale="Fragile tests slow development. Test stable interfaces, not implementation.",
            source=sources["xunit_smells"],
            raw_tags=["anti-patterns", "fragile", "implementation-details"],
        ),
    ]


def build_source_map() -> dict[str, Source]:
    """Build a map of source keys to Source objects."""
    return {
        # Testing philosophy
        "google_sizes": Source(
            name="Google Testing Blog - Test Sizes",
            url="https://testing.googleblog.com/2010/12/test-sizes.html",
            source_type=SourceType.BLOG_POST,
            domain="testing-philosophy",
        ),
        "google_pyramid": Source(
            name="Google Testing Blog - Just Say No to More E2E Tests",
            url="https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html",
            source_type=SourceType.BLOG_POST,
            domain="testing-philosophy",
        ),
        "fowler_pyramid": Source(
            name="Martin Fowler - Testing Pyramid",
            url="https://martinfowler.com/articles/practical-test-pyramid.html",
            source_type=SourceType.REFERENCE_DOC,
            domain="testing-philosophy",
        ),
        "fowler_doubles": Source(
            name="Martin Fowler - Test Double",
            url="https://martinfowler.com/bliki/TestDouble.html",
            source_type=SourceType.REFERENCE_DOC,
            domain="testing-philosophy",
        ),
        # Property testing
        "hypothesis": Source(
            name="Hypothesis Documentation",
            url="https://hypothesis.readthedocs.io/en/latest/",
            source_type=SourceType.REFERENCE_DOC,
            domain="property-testing",
        ),
        # Metamorphic
        "metamorphic_chen": Source(
            name="Metamorphic Testing - Chen et al. Survey",
            url="https://www.sciencedirect.com/science/article/pii/S0950584918300016",
            source_type=SourceType.STANDARD,
            domain="metamorphic",
        ),
        # Statistical
        "great_expectations": Source(
            name="Great Expectations Documentation",
            url="https://docs.greatexpectations.io/docs/",
            source_type=SourceType.REFERENCE_DOC,
            domain="statistical",
        ),
        "pandera": Source(
            name="Pandera Documentation",
            url="https://pandera.readthedocs.io/en/stable/",
            source_type=SourceType.REFERENCE_DOC,
            domain="statistical",
        ),
        # LLM testing
        "guardrails": Source(
            name="Guardrails AI Documentation",
            url="https://www.guardrailsai.com/docs/concepts/guard",
            source_type=SourceType.REFERENCE_DOC,
            domain="llm-testing",
        ),
        "deepeval": Source(
            name="DeepEval Documentation",
            url="https://docs.confident-ai.com/docs/getting-started",
            source_type=SourceType.REFERENCE_DOC,
            domain="llm-testing",
        ),
        # Anti-patterns
        "xunit_smells": Source(
            name="xUnit Test Patterns - Test Smells",
            url="http://xunitpatterns.com/Test%20Smells.html",
            source_type=SourceType.BOOK,
            domain="anti-patterns",
        ),
        "google_flaky": Source(
            name="Google Testing Blog - Test Flakiness",
            url="https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html",
            source_type=SourceType.BLOG_POST,
            domain="anti-patterns",
        ),
        # Tooling
        "pytest_practices": Source(
            name="pytest - Good Integration Practices",
            url="https://docs.pytest.org/en/stable/explanation/goodpractices.html",
            source_type=SourceType.REFERENCE_DOC,
            domain="tooling",
        ),
    }


def main():
    """Generate the Test Terrorist seed file."""
    output_dir = Path(".buildlog/seeds")

    # Build sources
    sources = build_source_map()

    # Collect all rules
    all_rules: list[CandidateRule] = []
    all_rules.extend(get_coverage_rules(sources))
    all_rules.extend(get_isolation_rules(sources))
    all_rules.extend(get_assertions_rules(sources))
    all_rules.extend(get_structure_rules(sources))
    all_rules.extend(get_property_rules(sources))
    all_rules.extend(get_metamorphic_rules(sources))
    all_rules.extend(get_statistical_rules(sources))
    all_rules.extend(get_llm_testing_rules(sources))
    all_rules.extend(get_antipattern_rules(sources))

    print(f"Total rules: {len(all_rules)}")

    # Create extractor and register rules
    extractor = ManualExtractor()
    for source in sources.values():
        source_rules = [r for r in all_rules if r.source.url == source.url]
        if source_rules:
            extractor.register(source, source_rules)
            print(f"  {source.name}: {len(source_rules)} rules")

    # Create categorizer
    categorizer = TagBasedCategorizer(
        default_category="testing",
        mappings=[
            CategoryMapping(
                "coverage", ["coverage", "regression", "public-api"], priority=1
            ),
            CategoryMapping(
                "isolation", ["isolation", "hermetic", "mocking"], priority=1
            ),
            CategoryMapping(
                "assertions", ["assertions", "meaningful", "behavior"], priority=1
            ),
            CategoryMapping("structure", ["structure", "aaa", "naming"], priority=1),
            CategoryMapping(
                "property-testing", ["property", "hypothesis", "invariants"], priority=2
            ),
            CategoryMapping(
                "metamorphic-testing", ["metamorphic", "oracle-free"], priority=2
            ),
            CategoryMapping(
                "statistical-testing",
                ["statistical", "distribution", "schema"],
                priority=2,
            ),
            CategoryMapping("llm-testing", ["llm-testing", "gap"], priority=3),
            CategoryMapping(
                "anti-patterns", ["anti-patterns", "flaky", "fragile"], priority=1
            ),
        ],
        additional_tags=["test_terrorist"],
    )

    # Create and run pipeline
    pipeline = Pipeline(
        persona="test_terrorist",
        extractor=extractor,
        categorizer=categorizer,
        version=1,
    )

    result = pipeline.run(
        sources=list(sources.values()),
        output_dir=output_dir,
    )

    print(f"\n{result.summary()}")

    # Category breakdown
    categories = {}
    for rule in result.categorized:
        cat = rule.category
        categories[cat] = categories.get(cat, 0) + 1

    print("\nBy category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
