"""Shared test fixtures and utilities."""

from __future__ import annotations

from typing import Literal

import pytest

from buildlog.skills import ConfidenceLevel, Skill


@pytest.fixture
def make_skill():
    """Factory fixture for creating test skills.

    Returns a function that creates Skill instances with sensible defaults.
    """

    def _make_skill(
        id: str = "arch-123456",
        category: str = "architectural",
        rule: str = "Test rule",
        frequency: int = 2,
        confidence: ConfidenceLevel = "medium",
    ) -> Skill:
        return Skill(
            id=id,
            category=category,
            rule=rule,
            frequency=frequency,
            confidence=confidence,
            sources=["test.md"],
            tags=["test"],
        )

    return _make_skill
