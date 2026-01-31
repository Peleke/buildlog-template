"""Confidence scoring for rules and patterns.

Confidence represents structural inertia - how hard it would be for the system
to stop believing a rule. It reflects accumulated mass from reinforcement,
not objective correctness.

A rule gains mass when:
- It shows up again (frequency)
- It shows up recently (recency)
- It survives contradictions

A rule loses mass when:
- It's unused (time decay)
- It's contradicted
- It's contextually bypassed
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TypedDict

__all__ = [
    "ConfidenceTier",
    "ConfidenceConfig",
    "ConfidenceMetrics",
    "ConfidenceMetricsDict",
    "calculate_confidence",
    "get_confidence_tier",
    "merge_confidence_metrics",
    "add_contradiction",
    "apply_severity_weight",
]


class ConfidenceTier(str, Enum):
    """Descriptive tiers for rule confidence.

    These are purely descriptive labels for human interpretation.
    No logic gates or hard thresholds are enforced by the system.
    """

    SPECULATIVE = "speculative"  # Low mass, recently introduced
    PROVISIONAL = "provisional"  # Growing mass, some reinforcement
    STABLE = "stable"  # Consistent reinforcement, moderate mass
    ENTRENCHED = "entrenched"  # High mass, sustained over time


@dataclass(frozen=True)
class ConfidenceConfig:
    """Configuration parameters for confidence calculation.

    Attributes:
        tau: Half-life for recency decay (in days). Smaller = twitchier system.
        k: Saturation constant for frequency. Larger = slower saturation.
        lambda_: Decay constant for contradiction penalty.
        tier_thresholds: Confidence score thresholds for each tier.
    """

    tau: float = 30.0  # 30-day half-life by default
    k: float = 5.0  # Frequency saturation constant
    lambda_: float = 2.0  # Contradiction decay constant
    tier_thresholds: tuple[float, float, float] = (0.2, 0.4, 0.7)

    def __post_init__(self) -> None:
        if self.tau <= 0:
            raise ValueError("tau must be positive")
        if self.k <= 0:
            raise ValueError("k must be positive")
        if self.lambda_ <= 0:
            raise ValueError("lambda_ must be positive")
        low, mid, high = self.tier_thresholds
        if not (0 <= low <= mid <= high <= 1):
            raise ValueError(
                "tier_thresholds must be monotonically increasing in [0, 1]"
            )


class ConfidenceMetricsDict(TypedDict):
    """Serializable form of confidence metrics."""

    reinforcement_count: int
    last_reinforced: str  # ISO format timestamp
    contradiction_count: int
    first_seen: str  # ISO format timestamp


@dataclass
class ConfidenceMetrics:
    """Tracked metrics for confidence calculation.

    These are the raw inputs that feed into the confidence formula.
    """

    reinforcement_count: int = 1
    last_reinforced: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    contradiction_count: int = 0
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.reinforcement_count < 0:
            raise ValueError("reinforcement_count must be non-negative")
        if self.contradiction_count < 0:
            raise ValueError("contradiction_count must be non-negative")

    def to_dict(self) -> ConfidenceMetricsDict:
        """Convert to serializable dictionary."""
        return {
            "reinforcement_count": self.reinforcement_count,
            "last_reinforced": self.last_reinforced.isoformat(),
            "contradiction_count": self.contradiction_count,
            "first_seen": self.first_seen.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: ConfidenceMetricsDict) -> ConfidenceMetrics:
        """Reconstruct from serialized dictionary.

        Note: Timezone-naive datetimes are assumed to be UTC.
        """
        last_reinforced = datetime.fromisoformat(data["last_reinforced"])
        first_seen = datetime.fromisoformat(data["first_seen"])

        # Ensure timezone awareness (assume UTC for naive datetimes)
        if last_reinforced.tzinfo is None:
            last_reinforced = last_reinforced.replace(tzinfo=timezone.utc)
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)

        return cls(
            reinforcement_count=data["reinforcement_count"],
            last_reinforced=last_reinforced,
            contradiction_count=data["contradiction_count"],
            first_seen=first_seen,
        )


def calculate_frequency_weight(n: int, k: float) -> float:
    """Calculate frequency weight with saturation.

    Uses bounded exponential: 1 - exp(-n/k)
    This makes early reinforcement matter more than late spam.

    Args:
        n: Reinforcement count
        k: Saturation constant (larger = slower saturation)

    Returns:
        Weight in range (0, 1), approaching 1 as n grows
    """
    return 1.0 - math.exp(-n / k)


def calculate_recency_weight(
    t_last: datetime,
    t_now: datetime,
    tau: float,
) -> float:
    """Calculate recency weight with exponential decay.

    Uses: exp(-(t_now - t_last) / tau)

    Args:
        t_last: Timestamp of last reinforcement
        t_now: Current timestamp
        tau: Half-life in days

    Returns:
        Weight in range (0, 1], decaying over time.
        If t_last is in the future, clamps to 1.0.
    """
    days_elapsed = (t_now - t_last).total_seconds() / (24 * 60 * 60)
    if days_elapsed < 0:
        return 1.0  # Future timestamps treated as "just now"
    return math.exp(-days_elapsed / tau)


def calculate_contradiction_penalty(c: int, lambda_: float) -> float:
    """Calculate contradiction penalty (drag).

    Rules don't die from contradictions, they get heavy and sink.
    Uses: exp(-c / lambda)

    Args:
        c: Contradiction count
        lambda_: Decay constant

    Returns:
        Penalty multiplier in range (0, 1]
    """
    return math.exp(-c / lambda_)


def calculate_confidence(
    metrics: ConfidenceMetrics,
    config: ConfidenceConfig | None = None,
    t_now: datetime | None = None,
) -> float:
    """Calculate confidence score for a rule.

    Confidence = frequency_weight * recency_weight * contradiction_penalty

    This gives a scalar that:
    - Rises fast early
    - Decays naturally over time
    - Never quite hits zero
    - Never explodes to infinity

    Args:
        metrics: Tracked metrics for the rule
        config: Scoring configuration (uses defaults if None)
        t_now: Current time (uses now if None)

    Returns:
        Confidence score in range (0, 1)
    """
    if config is None:
        config = ConfidenceConfig()
    if t_now is None:
        t_now = datetime.now(timezone.utc)

    freq = calculate_frequency_weight(metrics.reinforcement_count, config.k)
    recency = calculate_recency_weight(metrics.last_reinforced, t_now, config.tau)
    penalty = calculate_contradiction_penalty(
        metrics.contradiction_count, config.lambda_
    )

    return freq * recency * penalty


def get_confidence_tier(
    score: float,
    config: ConfidenceConfig | None = None,
) -> ConfidenceTier:
    """Map confidence score to descriptive tier.

    Args:
        score: Confidence score in range [0, 1]
        config: Configuration with tier thresholds

    Returns:
        Descriptive tier label

    Raises:
        ValueError: If score is outside [0, 1] range
    """
    if not (0.0 <= score <= 1.0):
        raise ValueError(f"score must be in [0, 1], got {score}")

    if config is None:
        config = ConfidenceConfig()

    low, mid, high = config.tier_thresholds

    if score < low:
        return ConfidenceTier.SPECULATIVE
    elif score < mid:
        return ConfidenceTier.PROVISIONAL
    elif score < high:
        return ConfidenceTier.STABLE
    else:
        return ConfidenceTier.ENTRENCHED


def merge_confidence_metrics(
    existing: ConfidenceMetrics,
    new_occurrence: datetime | None = None,
) -> ConfidenceMetrics:
    """Merge a new occurrence into existing metrics.

    This is called when a rule is reinforced (seen again).

    Args:
        existing: Current metrics for the rule
        new_occurrence: Timestamp of new occurrence (uses now if None)

    Returns:
        Updated metrics with incremented count and updated timestamp
    """
    if new_occurrence is None:
        new_occurrence = datetime.now(timezone.utc)

    return ConfidenceMetrics(
        reinforcement_count=existing.reinforcement_count + 1,
        last_reinforced=new_occurrence,
        contradiction_count=existing.contradiction_count,
        first_seen=existing.first_seen,
    )


def add_contradiction(metrics: ConfidenceMetrics) -> ConfidenceMetrics:
    """Record a contradiction against a rule.

    Contradictions add drag but don't invalidate rules.

    Args:
        metrics: Current metrics for the rule

    Returns:
        Updated metrics with incremented contradiction count
    """
    return ConfidenceMetrics(
        reinforcement_count=metrics.reinforcement_count,
        last_reinforced=metrics.last_reinforced,
        contradiction_count=metrics.contradiction_count + 1,
        first_seen=metrics.first_seen,
    )


# Severity weight multipliers for confidence scoring
SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 1.5,
    "major": 1.2,
    "minor": 1.0,
    "info": 0.8,
}


def apply_severity_weight(confidence_score: float, severity: str) -> float:
    """Apply severity weighting to a continuous confidence score.

    Severity acts as a multiplier: critical rules get boosted,
    info rules get dampened. Result is capped at 1.0.

    Args:
        confidence_score: Base confidence score in [0, 1].
        severity: One of: critical, major, minor, info.

    Returns:
        Weighted confidence score, capped at 1.0.
    """
    weight = SEVERITY_WEIGHTS.get(severity, 1.0)
    return min(confidence_score * weight, 1.0)
