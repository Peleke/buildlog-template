"""Shared test fixtures and utilities."""

from __future__ import annotations

import pytest

from buildlog.skills import ConfidenceLevel, Skill


def pytest_addoption(parser):
    """Register custom CLI flags for optional test suites."""
    parser.addoption(
        "--run-ollama",
        action="store_true",
        default=False,
        help="Run smoke tests against a local Ollama instance",
    )


@pytest.fixture
def make_skill():
    """Factory fixture for creating test skills.

    Returns a function that creates Skill instances with sensible defaults.
    Supports both discrete confidence (high/medium/low) and optional
    continuous confidence (confidence_score, confidence_tier).
    """

    def _make_skill(
        id: str = "arch-123456",
        category: str = "architectural",
        rule: str = "Test rule",
        frequency: int = 2,
        confidence: ConfidenceLevel = "medium",
        sources: list[str] | None = None,
        tags: list[str] | None = None,
        confidence_score: float | None = None,
        confidence_tier: str | None = None,
    ) -> Skill:
        return Skill(
            id=id,
            category=category,
            rule=rule,
            frequency=frequency,
            confidence=confidence,
            sources=sources if sources is not None else ["test.md"],
            tags=tags if tags is not None else ["test"],
            confidence_score=confidence_score,
            confidence_tier=confidence_tier,
        )

    return _make_skill
