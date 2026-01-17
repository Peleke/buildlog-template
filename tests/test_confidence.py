"""Exhaustive tests for confidence scoring module.

Tests cover:
- Individual component functions (frequency, recency, contradiction)
- Combined confidence calculation
- Tier mapping
- Metric merging and serialization
- Edge cases and boundary conditions
- Mathematical properties (monotonicity, boundedness, etc.)
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from buildlog.confidence import (
    ConfidenceConfig,
    ConfidenceMetrics,
    ConfidenceTier,
    add_contradiction,
    calculate_confidence,
    calculate_contradiction_penalty,
    calculate_frequency_weight,
    calculate_recency_weight,
    get_confidence_tier,
    merge_confidence_metrics,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def default_config() -> ConfidenceConfig:
    """Default configuration for testing."""
    return ConfidenceConfig()


@pytest.fixture
def now() -> datetime:
    """Fixed 'now' timestamp for deterministic testing."""
    return datetime(2026, 1, 16, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def make_metrics(now: datetime):
    """Factory for creating test metrics."""

    def _make_metrics(
        reinforcement_count: int = 1,
        days_ago: float = 0,
        contradiction_count: int = 0,
        first_seen_days_ago: float | None = None,
    ) -> ConfidenceMetrics:
        last_reinforced = now - timedelta(days=days_ago)
        if first_seen_days_ago is None:
            first_seen_days_ago = days_ago
        first_seen = now - timedelta(days=first_seen_days_ago)
        return ConfidenceMetrics(
            reinforcement_count=reinforcement_count,
            last_reinforced=last_reinforced,
            contradiction_count=contradiction_count,
            first_seen=first_seen,
        )

    return _make_metrics


# =============================================================================
# ConfidenceConfig Tests
# =============================================================================


class TestConfidenceConfig:
    """Tests for ConfidenceConfig validation and defaults."""

    def test_default_values(self) -> None:
        """Default config should have sensible values."""
        config = ConfidenceConfig()
        assert config.tau == 30.0
        assert config.k == 5.0
        assert config.lambda_ == 2.0
        assert config.tier_thresholds == (0.2, 0.4, 0.7)

    def test_custom_values(self) -> None:
        """Config should accept custom values."""
        config = ConfidenceConfig(tau=60.0, k=10.0, lambda_=3.0)
        assert config.tau == 60.0
        assert config.k == 10.0
        assert config.lambda_ == 3.0

    def test_custom_tier_thresholds(self) -> None:
        """Config should accept custom tier thresholds."""
        config = ConfidenceConfig(tier_thresholds=(0.1, 0.3, 0.6))
        assert config.tier_thresholds == (0.1, 0.3, 0.6)

    def test_invalid_tau_zero(self) -> None:
        """tau must be positive."""
        with pytest.raises(ValueError, match="tau must be positive"):
            ConfidenceConfig(tau=0)

    def test_invalid_tau_negative(self) -> None:
        """tau must be positive."""
        with pytest.raises(ValueError, match="tau must be positive"):
            ConfidenceConfig(tau=-1)

    def test_invalid_k_zero(self) -> None:
        """k must be positive."""
        with pytest.raises(ValueError, match="k must be positive"):
            ConfidenceConfig(k=0)

    def test_invalid_k_negative(self) -> None:
        """k must be positive."""
        with pytest.raises(ValueError, match="k must be positive"):
            ConfidenceConfig(k=-1)

    def test_invalid_lambda_zero(self) -> None:
        """lambda_ must be positive."""
        with pytest.raises(ValueError, match="lambda_ must be positive"):
            ConfidenceConfig(lambda_=0)

    def test_invalid_lambda_negative(self) -> None:
        """lambda_ must be positive."""
        with pytest.raises(ValueError, match="lambda_ must be positive"):
            ConfidenceConfig(lambda_=-1)

    def test_frozen(self) -> None:
        """Config should be immutable."""
        config = ConfidenceConfig()
        with pytest.raises(AttributeError):
            config.tau = 100  # type: ignore[misc]

    def test_tier_thresholds_out_of_order_raises(self) -> None:
        """Tier thresholds must be monotonically increasing."""
        with pytest.raises(ValueError, match="tier_thresholds must be monotonically"):
            ConfidenceConfig(tier_thresholds=(0.5, 0.3, 0.7))

    def test_tier_thresholds_negative_raises(self) -> None:
        """Tier thresholds must be non-negative."""
        with pytest.raises(ValueError, match="tier_thresholds must be monotonically"):
            ConfidenceConfig(tier_thresholds=(-0.1, 0.3, 0.7))

    def test_tier_thresholds_above_one_raises(self) -> None:
        """Tier thresholds must be at most 1."""
        with pytest.raises(ValueError, match="tier_thresholds must be monotonically"):
            ConfidenceConfig(tier_thresholds=(0.2, 0.5, 1.5))


# =============================================================================
# Frequency Weight Tests
# =============================================================================


class TestFrequencyWeight:
    """Tests for frequency_weight = 1 - exp(-n/k).

    Properties:
    - Bounded: result in (0, 1)
    - Monotonically increasing with n
    - Saturates as n grows (diminishing returns)
    - At n=0, weight approaches 0
    - At n=k, weight = 1 - exp(-1) ≈ 0.632
    """

    def test_zero_reinforcement(self) -> None:
        """No reinforcement should give weight near 0."""
        weight = calculate_frequency_weight(0, k=5.0)
        assert weight == 0.0

    def test_single_reinforcement(self) -> None:
        """Single reinforcement should give small positive weight."""
        weight = calculate_frequency_weight(1, k=5.0)
        assert 0 < weight < 0.5
        # Exact: 1 - exp(-1/5) ≈ 0.181
        assert abs(weight - 0.1813) < 0.001

    def test_at_k(self) -> None:
        """At n=k, weight should be 1 - exp(-1) ≈ 0.632."""
        weight = calculate_frequency_weight(5, k=5.0)
        expected = 1 - math.exp(-1)
        assert abs(weight - expected) < 0.001

    def test_high_reinforcement(self) -> None:
        """High reinforcement should approach but not exceed 1."""
        weight = calculate_frequency_weight(100, k=5.0)
        assert weight < 1.0
        assert weight > 0.99  # Should be very close to 1

    def test_monotonically_increasing(self) -> None:
        """Weight should increase with more reinforcement."""
        weights = [calculate_frequency_weight(n, k=5.0) for n in range(20)]
        for i in range(1, len(weights)):
            assert weights[i] > weights[i - 1]

    def test_diminishing_returns(self) -> None:
        """Marginal increase should decrease as n grows."""
        deltas = []
        for n in range(1, 20):
            prev = calculate_frequency_weight(n - 1, k=5.0)
            curr = calculate_frequency_weight(n, k=5.0)
            deltas.append(curr - prev)
        # Each delta should be smaller than the previous
        for i in range(1, len(deltas)):
            assert deltas[i] < deltas[i - 1]

    def test_smaller_k_faster_saturation(self) -> None:
        """Smaller k should cause faster saturation."""
        small_k = calculate_frequency_weight(5, k=2.0)
        large_k = calculate_frequency_weight(5, k=10.0)
        assert small_k > large_k

    def test_larger_k_slower_saturation(self) -> None:
        """Larger k should require more reinforcement to reach same weight."""
        # Find n where weight ≈ 0.5 for different k values
        # For k=5: n where 1 - exp(-n/5) = 0.5 => n = -5*ln(0.5) ≈ 3.47
        # For k=10: n where 1 - exp(-n/10) = 0.5 => n = -10*ln(0.5) ≈ 6.93
        weight_k5_at_3 = calculate_frequency_weight(3, k=5.0)
        weight_k10_at_3 = calculate_frequency_weight(3, k=10.0)
        assert weight_k5_at_3 > weight_k10_at_3

    @pytest.mark.parametrize("n", [1, 5, 10, 50, 100])
    def test_always_bounded(self, n: int) -> None:
        """Weight should always be in (0, 1) for positive n.

        Note: At extreme values (n=1000+), floating point rounds to exactly 1.0,
        which is fine in practice - the formula is mathematically bounded.
        """
        weight = calculate_frequency_weight(n, k=5.0)
        assert 0 < weight < 1


# =============================================================================
# Recency Weight Tests
# =============================================================================


class TestRecencyWeight:
    """Tests for recency_weight = exp(-(t_now - t_last) / tau).

    Properties:
    - Bounded: result in (0, 1]
    - Maximum (1.0) when t_last == t_now
    - Decays exponentially with time
    - At time = tau, weight = exp(-1) ≈ 0.368
    """

    def test_just_reinforced(self, now: datetime) -> None:
        """Rule reinforced just now should have weight 1.0."""
        weight = calculate_recency_weight(t_last=now, t_now=now, tau=30.0)
        assert weight == 1.0

    def test_one_day_ago(self, now: datetime) -> None:
        """Rule reinforced 1 day ago should have high weight."""
        t_last = now - timedelta(days=1)
        weight = calculate_recency_weight(t_last=t_last, t_now=now, tau=30.0)
        # exp(-1/30) ≈ 0.967
        assert 0.96 < weight < 0.98

    def test_at_tau(self, now: datetime) -> None:
        """At time = tau, weight should be exp(-1) ≈ 0.368."""
        t_last = now - timedelta(days=30)
        weight = calculate_recency_weight(t_last=t_last, t_now=now, tau=30.0)
        expected = math.exp(-1)
        assert abs(weight - expected) < 0.001

    def test_long_ago(self, now: datetime) -> None:
        """Rule not seen for long time should have very low weight."""
        t_last = now - timedelta(days=365)
        weight = calculate_recency_weight(t_last=t_last, t_now=now, tau=30.0)
        # exp(-365/30) ≈ 5.3e-6
        assert weight < 0.001
        assert weight > 0  # Never quite zero

    def test_monotonically_decreasing(self, now: datetime) -> None:
        """Weight should decrease as time passes."""
        weights = []
        for days in range(0, 100, 10):
            t_last = now - timedelta(days=days)
            weight = calculate_recency_weight(t_last=t_last, t_now=now, tau=30.0)
            weights.append(weight)
        for i in range(1, len(weights)):
            assert weights[i] < weights[i - 1]

    def test_smaller_tau_faster_decay(self, now: datetime) -> None:
        """Smaller tau should cause faster decay."""
        t_last = now - timedelta(days=15)
        small_tau = calculate_recency_weight(t_last=t_last, t_now=now, tau=10.0)
        large_tau = calculate_recency_weight(t_last=t_last, t_now=now, tau=60.0)
        assert small_tau < large_tau

    def test_larger_tau_slower_decay(self, now: datetime) -> None:
        """Larger tau should preserve recency longer."""
        t_last = now - timedelta(days=60)
        # For tau=30: exp(-60/30) = exp(-2) ≈ 0.135
        # For tau=90: exp(-60/90) = exp(-2/3) ≈ 0.513
        small_tau = calculate_recency_weight(t_last=t_last, t_now=now, tau=30.0)
        large_tau = calculate_recency_weight(t_last=t_last, t_now=now, tau=90.0)
        assert large_tau > small_tau
        assert abs(small_tau - 0.135) < 0.01
        assert abs(large_tau - 0.513) < 0.01

    @pytest.mark.parametrize("days", [0, 1, 7, 30, 90, 365, 1000])
    def test_always_positive(self, now: datetime, days: int) -> None:
        """Weight should always be positive, never zero."""
        t_last = now - timedelta(days=days)
        weight = calculate_recency_weight(t_last=t_last, t_now=now, tau=30.0)
        assert weight > 0

    @pytest.mark.parametrize("days", [0, 1, 7, 30, 90, 365])
    def test_always_at_most_one(self, now: datetime, days: int) -> None:
        """Weight should never exceed 1.0."""
        t_last = now - timedelta(days=days)
        weight = calculate_recency_weight(t_last=t_last, t_now=now, tau=30.0)
        assert weight <= 1.0

    def test_future_timestamp_clamps_to_one(self, now: datetime) -> None:
        """Future last_reinforced should clamp to 1.0 (not explode)."""
        future = now + timedelta(days=10)
        weight = calculate_recency_weight(t_last=future, t_now=now, tau=30.0)
        assert weight == 1.0


# =============================================================================
# Contradiction Penalty Tests
# =============================================================================


class TestContradictionPenalty:
    """Tests for contradiction_penalty = exp(-c / lambda).

    Properties:
    - Bounded: result in (0, 1]
    - Maximum (1.0) when c == 0
    - Decreases with more contradictions
    - Rules don't die, they get heavy and sink
    """

    def test_no_contradictions(self) -> None:
        """No contradictions should give full weight (1.0)."""
        penalty = calculate_contradiction_penalty(0, lambda_=2.0)
        assert penalty == 1.0

    def test_single_contradiction(self) -> None:
        """Single contradiction should reduce weight."""
        penalty = calculate_contradiction_penalty(1, lambda_=2.0)
        # exp(-1/2) ≈ 0.607
        assert 0.60 < penalty < 0.62

    def test_at_lambda(self) -> None:
        """At c=lambda, penalty should be exp(-1) ≈ 0.368."""
        penalty = calculate_contradiction_penalty(2, lambda_=2.0)
        expected = math.exp(-1)
        assert abs(penalty - expected) < 0.001

    def test_many_contradictions(self) -> None:
        """Many contradictions should give very low penalty but not zero."""
        penalty = calculate_contradiction_penalty(10, lambda_=2.0)
        # exp(-10/2) = exp(-5) ≈ 0.0067
        assert penalty < 0.01
        assert penalty > 0  # Never quite zero

    def test_monotonically_decreasing(self) -> None:
        """Penalty should decrease with more contradictions."""
        penalties = [calculate_contradiction_penalty(c, lambda_=2.0) for c in range(10)]
        for i in range(1, len(penalties)):
            assert penalties[i] < penalties[i - 1]

    def test_smaller_lambda_harsher_penalty(self) -> None:
        """Smaller lambda should penalize contradictions more harshly."""
        small_lambda = calculate_contradiction_penalty(3, lambda_=1.0)
        large_lambda = calculate_contradiction_penalty(3, lambda_=5.0)
        assert small_lambda < large_lambda

    @pytest.mark.parametrize("c", [0, 1, 5, 10, 50, 100])
    def test_always_positive(self, c: int) -> None:
        """Penalty should always be positive, never zero."""
        penalty = calculate_contradiction_penalty(c, lambda_=2.0)
        assert penalty > 0

    @pytest.mark.parametrize("c", [0, 1, 5, 10])
    def test_always_at_most_one(self, c: int) -> None:
        """Penalty should never exceed 1.0."""
        penalty = calculate_contradiction_penalty(c, lambda_=2.0)
        assert penalty <= 1.0


# =============================================================================
# Combined Confidence Score Tests
# =============================================================================


class TestCalculateConfidence:
    """Tests for the combined confidence calculation.

    confidence = frequency_weight * recency_weight * contradiction_penalty
    """

    def test_new_rule_just_seen(self, make_metrics, now: datetime) -> None:
        """Newly seen rule should have low-moderate confidence."""
        metrics = make_metrics(reinforcement_count=1, days_ago=0)
        score = calculate_confidence(metrics, t_now=now)
        # freq(1,5) ≈ 0.181, recency(0) = 1.0, penalty(0) = 1.0
        # Total ≈ 0.181
        assert 0.15 < score < 0.25

    def test_frequently_reinforced_recent(self, make_metrics, now: datetime) -> None:
        """Frequently reinforced recent rule should have high confidence."""
        metrics = make_metrics(reinforcement_count=10, days_ago=1)
        score = calculate_confidence(metrics, t_now=now)
        # freq(10,5) ≈ 0.865, recency(1d) ≈ 0.967, penalty(0) = 1.0
        # Total ≈ 0.837
        assert score > 0.8

    def test_old_rule_high_frequency(self, make_metrics, now: datetime) -> None:
        """Old rule with high frequency should have moderate confidence."""
        metrics = make_metrics(reinforcement_count=20, days_ago=90)
        score = calculate_confidence(metrics, t_now=now)
        # freq(20,5) ≈ 0.982, recency(90d) ≈ 0.050, penalty(0) = 1.0
        # Total ≈ 0.049
        assert 0.03 < score < 0.1

    def test_contradicted_rule(self, make_metrics, now: datetime) -> None:
        """Contradicted rule should have reduced confidence."""
        metrics = make_metrics(reinforcement_count=5, days_ago=5, contradiction_count=2)
        score = calculate_confidence(metrics, t_now=now)
        # Compare with same rule without contradictions
        metrics_clean = make_metrics(reinforcement_count=5, days_ago=5)
        score_clean = calculate_confidence(metrics_clean, t_now=now)
        assert score < score_clean
        # penalty(2) ≈ 0.368, so contradicted ≈ 0.368 * clean
        ratio = score / score_clean
        assert abs(ratio - math.exp(-1)) < 0.01

    def test_heavily_contradicted_rule(self, make_metrics, now: datetime) -> None:
        """Heavily contradicted rule should have very low confidence."""
        metrics = make_metrics(
            reinforcement_count=10, days_ago=0, contradiction_count=10
        )
        score = calculate_confidence(metrics, t_now=now)
        # Even with high freq and recent, penalties drag it down
        assert score < 0.1

    def test_uses_default_config(self, make_metrics, now: datetime) -> None:
        """Should use default config when none provided."""
        metrics = make_metrics(reinforcement_count=5, days_ago=0)
        score = calculate_confidence(metrics, t_now=now)
        score_explicit = calculate_confidence(
            metrics, config=ConfidenceConfig(), t_now=now
        )
        assert score == score_explicit

    def test_custom_config_affects_score(self, make_metrics, now: datetime) -> None:
        """Custom config should change the score."""
        metrics = make_metrics(reinforcement_count=5, days_ago=30)
        default_score = calculate_confidence(metrics, t_now=now)
        # Longer half-life should preserve recency better
        custom_config = ConfidenceConfig(tau=90.0)
        custom_score = calculate_confidence(metrics, config=custom_config, t_now=now)
        assert custom_score > default_score

    def test_uses_current_time_by_default(self, make_metrics) -> None:
        """Should use current time when t_now not provided."""
        # This test verifies the function runs without t_now
        metrics = make_metrics(reinforcement_count=1, days_ago=0)
        score = calculate_confidence(metrics)
        assert 0 < score < 1

    @pytest.mark.parametrize(
        "reinforcement_count,days_ago,contradiction_count",
        [
            (1, 0, 0),
            (1, 365, 0),
            (100, 0, 0),
            (100, 365, 0),
            (1, 0, 10),
            (100, 0, 10),
            (50, 180, 5),
        ],
    )
    def test_always_bounded(
        self,
        make_metrics,
        now: datetime,
        reinforcement_count: int,
        days_ago: float,
        contradiction_count: int,
    ) -> None:
        """Confidence should always be in (0, 1)."""
        metrics = make_metrics(
            reinforcement_count=reinforcement_count,
            days_ago=days_ago,
            contradiction_count=contradiction_count,
        )
        score = calculate_confidence(metrics, t_now=now)
        assert 0 < score < 1


# =============================================================================
# Confidence Tier Tests
# =============================================================================


class TestConfidenceTier:
    """Tests for mapping scores to descriptive tiers."""

    def test_speculative_tier(self, default_config: ConfidenceConfig) -> None:
        """Low scores should be speculative."""
        assert get_confidence_tier(0.05, default_config) == ConfidenceTier.SPECULATIVE
        assert get_confidence_tier(0.15, default_config) == ConfidenceTier.SPECULATIVE
        assert get_confidence_tier(0.19, default_config) == ConfidenceTier.SPECULATIVE

    def test_provisional_tier(self, default_config: ConfidenceConfig) -> None:
        """Low-moderate scores should be provisional."""
        assert get_confidence_tier(0.20, default_config) == ConfidenceTier.PROVISIONAL
        assert get_confidence_tier(0.30, default_config) == ConfidenceTier.PROVISIONAL
        assert get_confidence_tier(0.39, default_config) == ConfidenceTier.PROVISIONAL

    def test_stable_tier(self, default_config: ConfidenceConfig) -> None:
        """Moderate scores should be stable."""
        assert get_confidence_tier(0.40, default_config) == ConfidenceTier.STABLE
        assert get_confidence_tier(0.55, default_config) == ConfidenceTier.STABLE
        assert get_confidence_tier(0.69, default_config) == ConfidenceTier.STABLE

    def test_entrenched_tier(self, default_config: ConfidenceConfig) -> None:
        """High scores should be entrenched."""
        assert get_confidence_tier(0.70, default_config) == ConfidenceTier.ENTRENCHED
        assert get_confidence_tier(0.85, default_config) == ConfidenceTier.ENTRENCHED
        assert get_confidence_tier(0.99, default_config) == ConfidenceTier.ENTRENCHED

    def test_custom_thresholds(self) -> None:
        """Custom thresholds should shift tier boundaries."""
        config = ConfidenceConfig(tier_thresholds=(0.1, 0.5, 0.9))
        assert get_confidence_tier(0.05, config) == ConfidenceTier.SPECULATIVE
        assert get_confidence_tier(0.30, config) == ConfidenceTier.PROVISIONAL
        assert get_confidence_tier(0.70, config) == ConfidenceTier.STABLE
        assert get_confidence_tier(0.95, config) == ConfidenceTier.ENTRENCHED

    def test_uses_default_config(self) -> None:
        """Should use default config when none provided."""
        tier = get_confidence_tier(0.5)
        tier_explicit = get_confidence_tier(0.5, ConfidenceConfig())
        assert tier == tier_explicit

    def test_tier_enum_values(self) -> None:
        """Tier enum should have expected string values."""
        assert ConfidenceTier.SPECULATIVE.value == "speculative"
        assert ConfidenceTier.PROVISIONAL.value == "provisional"
        assert ConfidenceTier.STABLE.value == "stable"
        assert ConfidenceTier.ENTRENCHED.value == "entrenched"

    def test_boundary_values(self, default_config: ConfidenceConfig) -> None:
        """Boundary values should fall into higher tier."""
        # At exactly 0.2, should be provisional (not speculative)
        assert get_confidence_tier(0.2, default_config) == ConfidenceTier.PROVISIONAL
        # At exactly 0.4, should be stable (not provisional)
        assert get_confidence_tier(0.4, default_config) == ConfidenceTier.STABLE
        # At exactly 0.7, should be entrenched (not stable)
        assert get_confidence_tier(0.7, default_config) == ConfidenceTier.ENTRENCHED

    def test_score_below_zero_raises(self) -> None:
        """Score below 0 should raise ValueError."""
        with pytest.raises(ValueError, match="score must be in"):
            get_confidence_tier(-0.1)

    def test_score_above_one_raises(self) -> None:
        """Score above 1 should raise ValueError."""
        with pytest.raises(ValueError, match="score must be in"):
            get_confidence_tier(1.5)

    def test_zero_is_valid(self) -> None:
        """Score of exactly 0 should be valid (SPECULATIVE)."""
        tier = get_confidence_tier(0.0)
        assert tier == ConfidenceTier.SPECULATIVE

    def test_one_is_valid(self) -> None:
        """Score of exactly 1 should be valid (ENTRENCHED)."""
        tier = get_confidence_tier(1.0)
        assert tier == ConfidenceTier.ENTRENCHED


# =============================================================================
# Metric Merging Tests
# =============================================================================


class TestMergeConfidenceMetrics:
    """Tests for merging new occurrences into existing metrics."""

    def test_increments_count(self, now: datetime) -> None:
        """Merging should increment reinforcement count."""
        existing = ConfidenceMetrics(
            reinforcement_count=5,
            last_reinforced=now - timedelta(days=10),
            first_seen=now - timedelta(days=30),
        )
        merged = merge_confidence_metrics(existing, new_occurrence=now)
        assert merged.reinforcement_count == 6

    def test_updates_last_reinforced(self, now: datetime) -> None:
        """Merging should update last_reinforced timestamp."""
        old_time = now - timedelta(days=10)
        existing = ConfidenceMetrics(
            reinforcement_count=5,
            last_reinforced=old_time,
            first_seen=now - timedelta(days=30),
        )
        merged = merge_confidence_metrics(existing, new_occurrence=now)
        assert merged.last_reinforced == now

    def test_preserves_first_seen(self, now: datetime) -> None:
        """Merging should preserve original first_seen timestamp."""
        first_seen = now - timedelta(days=30)
        existing = ConfidenceMetrics(
            reinforcement_count=5,
            last_reinforced=now - timedelta(days=10),
            first_seen=first_seen,
        )
        merged = merge_confidence_metrics(existing, new_occurrence=now)
        assert merged.first_seen == first_seen

    def test_preserves_contradiction_count(self, now: datetime) -> None:
        """Merging should preserve contradiction count."""
        existing = ConfidenceMetrics(
            reinforcement_count=5,
            last_reinforced=now - timedelta(days=10),
            contradiction_count=3,
            first_seen=now - timedelta(days=30),
        )
        merged = merge_confidence_metrics(existing, new_occurrence=now)
        assert merged.contradiction_count == 3

    def test_uses_current_time_by_default(self) -> None:
        """Should use current time when new_occurrence not provided."""
        before = datetime.now(timezone.utc)
        existing = ConfidenceMetrics(reinforcement_count=1)
        merged = merge_confidence_metrics(existing)
        after = datetime.now(timezone.utc)
        assert before <= merged.last_reinforced <= after

    def test_immutable_original(self, now: datetime) -> None:
        """Original metrics should not be mutated."""
        existing = ConfidenceMetrics(
            reinforcement_count=5,
            last_reinforced=now - timedelta(days=10),
            first_seen=now - timedelta(days=30),
        )
        merge_confidence_metrics(existing, new_occurrence=now)
        assert existing.reinforcement_count == 5  # Unchanged


# =============================================================================
# Add Contradiction Tests
# =============================================================================


class TestAddContradiction:
    """Tests for recording contradictions."""

    def test_increments_contradiction_count(self, now: datetime) -> None:
        """Adding contradiction should increment count."""
        existing = ConfidenceMetrics(
            reinforcement_count=5,
            contradiction_count=2,
            last_reinforced=now,
            first_seen=now - timedelta(days=30),
        )
        updated = add_contradiction(existing)
        assert updated.contradiction_count == 3

    def test_preserves_other_fields(self, now: datetime) -> None:
        """Adding contradiction should preserve other fields."""
        existing = ConfidenceMetrics(
            reinforcement_count=5,
            last_reinforced=now,
            first_seen=now - timedelta(days=30),
        )
        updated = add_contradiction(existing)
        assert updated.reinforcement_count == 5
        assert updated.last_reinforced == now
        assert updated.first_seen == existing.first_seen

    def test_immutable_original(self, now: datetime) -> None:
        """Original metrics should not be mutated."""
        existing = ConfidenceMetrics(contradiction_count=0)
        add_contradiction(existing)
        assert existing.contradiction_count == 0  # Unchanged


# =============================================================================
# Serialization Tests
# =============================================================================


class TestConfidenceMetricsValidation:
    """Tests for ConfidenceMetrics validation."""

    def test_negative_reinforcement_count_raises(self) -> None:
        """Negative reinforcement_count should raise ValueError."""
        with pytest.raises(
            ValueError, match="reinforcement_count must be non-negative"
        ):
            ConfidenceMetrics(reinforcement_count=-1)

    def test_negative_contradiction_count_raises(self) -> None:
        """Negative contradiction_count should raise ValueError."""
        with pytest.raises(
            ValueError, match="contradiction_count must be non-negative"
        ):
            ConfidenceMetrics(contradiction_count=-1)

    def test_zero_counts_valid(self) -> None:
        """Zero counts should be valid."""
        metrics = ConfidenceMetrics(reinforcement_count=0, contradiction_count=0)
        assert metrics.reinforcement_count == 0
        assert metrics.contradiction_count == 0


# =============================================================================
# Serialization Tests
# =============================================================================


class TestMetricsSerialization:
    """Tests for metrics to/from dict conversion."""

    def test_to_dict(self, now: datetime) -> None:
        """to_dict should produce valid serializable dict."""
        metrics = ConfidenceMetrics(
            reinforcement_count=5,
            last_reinforced=now,
            contradiction_count=2,
            first_seen=now - timedelta(days=30),
        )
        d = metrics.to_dict()
        assert d["reinforcement_count"] == 5
        assert d["contradiction_count"] == 2
        assert d["last_reinforced"] == now.isoformat()
        assert d["first_seen"] == (now - timedelta(days=30)).isoformat()

    def test_from_dict(self, now: datetime) -> None:
        """from_dict should reconstruct metrics correctly."""
        data = {
            "reinforcement_count": 5,
            "last_reinforced": now.isoformat(),
            "contradiction_count": 2,
            "first_seen": (now - timedelta(days=30)).isoformat(),
        }
        metrics = ConfidenceMetrics.from_dict(data)
        assert metrics.reinforcement_count == 5
        assert metrics.last_reinforced == now
        assert metrics.contradiction_count == 2

    def test_roundtrip(self, now: datetime) -> None:
        """to_dict -> from_dict should be identity."""
        original = ConfidenceMetrics(
            reinforcement_count=5,
            last_reinforced=now,
            contradiction_count=2,
            first_seen=now - timedelta(days=30),
        )
        roundtripped = ConfidenceMetrics.from_dict(original.to_dict())
        assert roundtripped.reinforcement_count == original.reinforcement_count
        assert roundtripped.last_reinforced == original.last_reinforced
        assert roundtripped.contradiction_count == original.contradiction_count
        assert roundtripped.first_seen == original.first_seen

    def test_from_dict_naive_datetime_gets_utc(self) -> None:
        """Timezone-naive datetimes in from_dict should be assumed UTC."""
        naive_timestamp = "2026-01-15T12:00:00"  # No timezone info
        data = {
            "reinforcement_count": 1,
            "last_reinforced": naive_timestamp,
            "contradiction_count": 0,
            "first_seen": naive_timestamp,
        }
        metrics = ConfidenceMetrics.from_dict(data)
        # Should have UTC timezone
        assert metrics.last_reinforced.tzinfo == timezone.utc
        assert metrics.first_seen.tzinfo == timezone.utc

    def test_from_dict_aware_datetime_preserved(self, now: datetime) -> None:
        """Timezone-aware datetimes in from_dict should be preserved."""
        data = {
            "reinforcement_count": 1,
            "last_reinforced": now.isoformat(),
            "contradiction_count": 0,
            "first_seen": now.isoformat(),
        }
        metrics = ConfidenceMetrics.from_dict(data)
        assert metrics.last_reinforced == now
        assert metrics.first_seen == now


# =============================================================================
# Integration Tests
# =============================================================================


class TestConfidenceIntegration:
    """Integration tests for full confidence workflow."""

    def test_new_rule_lifecycle(self, now: datetime) -> None:
        """Test confidence evolution of a rule over time."""
        config = ConfidenceConfig(tau=30.0, k=5.0)

        # Day 0: Rule first seen
        metrics = ConfidenceMetrics(
            reinforcement_count=1,
            last_reinforced=now,
            first_seen=now,
        )
        score = calculate_confidence(metrics, config, now)
        tier = get_confidence_tier(score, config)
        assert tier == ConfidenceTier.SPECULATIVE

        # Day 1: Reinforced again
        metrics = merge_confidence_metrics(metrics, now + timedelta(days=1))
        score = calculate_confidence(metrics, config, now + timedelta(days=1))
        # Should still be relatively low
        assert score < 0.4

        # Day 7: Reinforced 5 more times
        for i in range(5):
            metrics = merge_confidence_metrics(
                metrics, now + timedelta(days=7 + i * 0.1)
            )
        score = calculate_confidence(metrics, config, now + timedelta(days=8))
        tier = get_confidence_tier(score, config)
        # Should be stable or entrenched by now
        assert tier in (ConfidenceTier.STABLE, ConfidenceTier.ENTRENCHED)

    def test_contradicted_rule_recovery(self, now: datetime) -> None:
        """Test that contradicted rules can recover with reinforcement."""
        config = ConfidenceConfig(tau=30.0, k=5.0, lambda_=2.0)

        # Start with well-established rule
        metrics = ConfidenceMetrics(
            reinforcement_count=10,
            last_reinforced=now,
            first_seen=now - timedelta(days=60),
        )
        initial_score = calculate_confidence(metrics, config, now)

        # Add contradictions
        for _ in range(3):
            metrics = add_contradiction(metrics)
        contradicted_score = calculate_confidence(metrics, config, now)
        assert contradicted_score < initial_score

        # Heavy reinforcement can partially compensate
        for i in range(10):
            metrics = merge_confidence_metrics(metrics, now + timedelta(days=i * 0.1))
        recovered_score = calculate_confidence(metrics, config, now + timedelta(days=1))
        # Should improve from contradicted state
        assert recovered_score > contradicted_score

    def test_stale_rule_decay(self, now: datetime) -> None:
        """Test that rules decay when not reinforced."""
        config = ConfidenceConfig(tau=30.0)

        # Well-established rule
        metrics = ConfidenceMetrics(
            reinforcement_count=20,
            last_reinforced=now,
            first_seen=now - timedelta(days=60),
        )

        scores = []
        for days in [0, 30, 60, 90, 120]:
            score = calculate_confidence(metrics, config, now + timedelta(days=days))
            scores.append(score)

        # Should decay monotonically
        for i in range(1, len(scores)):
            assert scores[i] < scores[i - 1]

        # After 120 days (4x half-life), should be quite low
        assert scores[-1] < 0.1
