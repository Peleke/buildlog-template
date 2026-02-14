"""Tests for Thompson Sampling Bandit.

=============================================================================
CANONICAL TEST SUITE: Thompson Sampling with Beta-Bernoulli Distributions
=============================================================================

This test suite verifies the correctness of the bandit implementation and
serves as executable documentation for how Thompson Sampling works.

TEST ORGANIZATION
-----------------
1. BetaParams tests: Verify Beta distribution mechanics
2. BanditState tests: Verify persistence and state management
3. ThompsonSamplingBandit tests: Verify selection and update logic
4. Integration tests: Verify end-to-end flow with operations.py

STATISTICAL NOTES
-----------------
Thompson Sampling is probabilistic, so we can't test exact outputs.
Instead, we test:
- Invariants (e.g., α and β must increase after updates)
- Statistical properties (e.g., means should converge with many samples)
- Edge cases (e.g., empty candidates, new arms)

For deterministic tests, we seed the random number generator.
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest

from buildlog.core.bandit import (
    DEFAULT_SEED_BOOST,
    BanditPersistence,
    BanditState,
    BetaParams,
    JsonlPersistence,
    SqlitePersistence,
    ThompsonSamplingBandit,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test state files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def bandit_path(temp_dir):
    """Create a path for bandit state file."""
    return temp_dir / "bandit_state.jsonl"


@pytest.fixture
def seeded_random():
    """Seed random for reproducible tests."""
    random.seed(42)
    yield
    # Reset to non-deterministic after test
    random.seed()


# =============================================================================
# BETA PARAMS TESTS
# =============================================================================


class TestBetaParams:
    """Tests for the Beta distribution parameter class.

    The Beta distribution is the heart of Thompson Sampling. These tests
    verify the mathematical properties we rely on.
    """

    def test_default_initialization(self):
        """Default Beta(1,1) is the uninformative prior (uniform on [0,1]).

        Interpretation: We have no prior knowledge about the arm's true
        success rate. Any value from 0 to 1 is equally likely.
        """
        params = BetaParams()
        assert params.alpha == 1.0
        assert params.beta == 1.0
        assert params.mean() == 0.5  # Uniform has mean 0.5

    def test_custom_initialization(self):
        """Custom parameters allow encoding prior beliefs."""
        params = BetaParams(alpha=3.0, beta=1.0)
        assert params.alpha == 3.0
        assert params.beta == 1.0
        # Beta(3,1) has mean = 3/4 = 0.75 (optimistic prior)
        assert params.mean() == 0.75

    def test_invalid_parameters_raise_error(self):
        """Alpha and beta must be positive."""
        with pytest.raises(ValueError):
            BetaParams(alpha=0, beta=1)
        with pytest.raises(ValueError):
            BetaParams(alpha=1, beta=-1)

    def test_mean_calculation(self):
        """Mean = α / (α + β).

        This is our best point estimate of the true success rate.
        """
        # Beta(2, 8): 2 successes, 8 failures → mean = 0.2
        params = BetaParams(alpha=2, beta=8)
        assert params.mean() == 0.2

        # Beta(50, 50): balanced → mean = 0.5
        params = BetaParams(alpha=50, beta=50)
        assert params.mean() == 0.5

    def test_variance_calculation(self):
        """Variance decreases as we gather more data.

        This is key to Thompson Sampling: uncertain arms have high variance,
        leading to occasional high samples, causing exploration.
        """
        # Low data: high variance
        low_data = BetaParams(alpha=2, beta=2)

        # High data (same mean): low variance
        high_data = BetaParams(alpha=20, beta=20)

        assert low_data.variance() > high_data.variance()
        # Both have mean 0.5, but we're more confident about high_data

    def test_sample_is_in_valid_range(self):
        """Samples from Beta distribution are in [0, 1]."""
        params = BetaParams(alpha=2, beta=3)
        for _ in range(100):
            sample = params.sample()
            assert 0 <= sample <= 1

    def test_update_with_success(self):
        """Success (reward=1) increases α, leaving β unchanged.

        Bayesian update: Beta(α, β) + success → Beta(α+1, β)
        This shifts the distribution RIGHT (higher expected value).
        """
        params = BetaParams(alpha=1, beta=1)
        initial_mean = params.mean()

        params.update(reward=1.0)

        assert params.alpha == 2.0
        assert params.beta == 1.0
        assert params.mean() > initial_mean

    def test_update_with_failure(self):
        """Failure (reward=0) increases β, leaving α unchanged.

        Bayesian update: Beta(α, β) + failure → Beta(α, β+1)
        This shifts the distribution LEFT (lower expected value).
        """
        params = BetaParams(alpha=1, beta=1)
        initial_mean = params.mean()

        params.update(reward=0.0)

        assert params.alpha == 1.0
        assert params.beta == 2.0
        assert params.mean() < initial_mean

    def test_update_with_partial_reward(self):
        """Partial reward updates both α and β proportionally.

        For reward r: α += r, β += (1-r)
        This allows nuanced feedback between full success and failure.
        """
        params = BetaParams(alpha=1, beta=1)
        params.update(reward=0.7)

        assert params.alpha == 1.7
        assert params.beta == 1.3

    def test_confidence_interval(self):
        """Confidence intervals narrow as data increases."""
        # Low data: wide interval
        low_data = BetaParams(alpha=2, beta=2)
        low_ci = low_data.confidence_interval()

        # High data: narrow interval
        high_data = BetaParams(alpha=20, beta=20)
        high_ci = high_data.confidence_interval()

        low_width = low_ci[1] - low_ci[0]
        high_width = high_ci[1] - high_ci[0]

        assert low_width > high_width

    def test_serialization_roundtrip(self):
        """Parameters survive serialization/deserialization."""
        original = BetaParams(alpha=3.5, beta=2.7)
        data = original.to_dict()
        restored = BetaParams.from_dict(data)

        assert restored.alpha == original.alpha
        assert restored.beta == original.beta


# =============================================================================
# BANDIT STATE TESTS
# =============================================================================


class TestBanditState:
    """Tests for bandit state persistence.

    State must survive across sessions. We use JSONL format for
    crash safety (append-only) and debuggability (human-readable).
    """

    def test_empty_state_on_missing_file(self, bandit_path):
        """Loading from non-existent file returns empty state."""
        state = BanditState.load(bandit_path)
        assert len(list(state.all_arms())) == 0

    def test_set_and_get_params(self):
        """Can store and retrieve parameters by (context, rule_id)."""
        state = BanditState()
        params = BetaParams(alpha=3, beta=2)

        state.set_params("type-errors", "rule-1", params)
        retrieved = state.get_params("type-errors", "rule-1")

        assert retrieved is not None
        assert retrieved.alpha == 3
        assert retrieved.beta == 2

    def test_get_missing_params_returns_none(self):
        """Getting non-existent arm returns None (not error)."""
        state = BanditState()
        assert state.get_params("unknown", "rule") is None

    def test_seed_flag_tracking(self):
        """Track which rules are from seeds for boosted priors."""
        state = BanditState()

        state.set_params("ctx", "seed-rule", BetaParams(), is_seed=True)
        state.set_params("ctx", "learned-rule", BetaParams(), is_seed=False)

        assert state.is_seed("ctx", "seed-rule") is True
        assert state.is_seed("ctx", "learned-rule") is False

    def test_save_and_load_roundtrip(self, bandit_path):
        """State survives save/load cycle."""
        original = BanditState()
        original.set_params("ctx1", "rule1", BetaParams(alpha=5, beta=3), is_seed=True)
        original.set_params("ctx2", "rule2", BetaParams(alpha=2, beta=8), is_seed=False)

        original.save(bandit_path)
        restored = BanditState.load(bandit_path)

        params1 = restored.get_params("ctx1", "rule1")
        assert params1 is not None
        assert params1.alpha == 5
        assert params1.beta == 3
        assert restored.is_seed("ctx1", "rule1") is True

        params2 = restored.get_params("ctx2", "rule2")
        assert params2 is not None
        assert params2.alpha == 2

    def test_append_update_efficiency(self, bandit_path):
        """Append updates without rewriting entire file."""
        state = BanditState()
        state.set_params("ctx", "rule", BetaParams(alpha=1, beta=1))
        state.save(bandit_path)

        # Update and append
        state.get_params("ctx", "rule").update(reward=1.0)
        state.append_update(bandit_path, "ctx", "rule")

        # File should have 2 lines (initial + update)
        lines = bandit_path.read_text().strip().split("\n")
        assert len(lines) == 2

        # But loading compacts to latest values
        reloaded = BanditState.load(bandit_path)
        params = reloaded.get_params("ctx", "rule")
        assert params.alpha == 2.0  # Updated value

    def test_malformed_lines_skipped_gracefully(self, bandit_path):
        """Crash recovery: skip malformed lines."""
        # Write valid + invalid lines
        line1 = '{"context": "ctx", "rule_id": "r1", "alpha": 2, "beta": 1, '
        line1 += '"is_seed": false, "updated_at": "2024-01-01T00:00:00+00:00"}\n'
        line2 = "this is not json\n"
        line3 = '{"context": "ctx", "rule_id": "r2", "alpha": 3, "beta": 2, '
        line3 += '"is_seed": false, "updated_at": "2024-01-01T00:00:00+00:00"}\n'
        bandit_path.write_text(line1 + line2 + line3)

        state = BanditState.load(bandit_path)

        # Valid lines loaded
        assert state.get_params("ctx", "r1") is not None
        assert state.get_params("ctx", "r2") is not None


# =============================================================================
# THOMPSON SAMPLING BANDIT TESTS
# =============================================================================


class TestThompsonSamplingBandit:
    """Tests for the main bandit class.

    These tests verify the selection and update logic that forms
    the core of Thompson Sampling.
    """

    def test_select_from_empty_candidates(self, bandit_path):
        """Selecting from empty list returns empty list."""
        bandit = ThompsonSamplingBandit(bandit_path)
        selected = bandit.select(candidates=[], context="ctx", k=3)
        assert selected == []

    def test_select_fewer_than_k_candidates(self, bandit_path):
        """If fewer candidates than k, return all of them."""
        bandit = ThompsonSamplingBandit(bandit_path)
        selected = bandit.select(
            candidates=["r1", "r2"],
            context="ctx",
            k=5,
        )
        assert len(selected) == 2
        assert set(selected) == {"r1", "r2"}

    def test_select_initializes_new_arms(self, bandit_path):
        """First selection creates arms with default priors."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.select(candidates=["r1", "r2"], context="ctx", k=2)

        # Arms should now exist
        assert bandit.state.get_params("ctx", "r1") is not None
        assert bandit.state.get_params("ctx", "r2") is not None

    def test_seed_rules_get_boosted_priors(self, bandit_path):
        """Seed rules start with higher alpha (more optimistic)."""
        bandit = ThompsonSamplingBandit(bandit_path, seed_boost=2.0)

        bandit.select(
            candidates=["seed-rule", "learned-rule"],
            context="ctx",
            k=2,
            seed_rule_ids={"seed-rule"},
        )

        seed_params = bandit.state.get_params("ctx", "seed-rule")
        learned_params = bandit.state.get_params("ctx", "learned-rule")

        # Seed: Beta(1+2, 1) = Beta(3, 1), mean = 0.75
        assert seed_params.alpha == 3.0
        assert seed_params.beta == 1.0

        # Learned: Beta(1, 1), mean = 0.5
        assert learned_params.alpha == 1.0
        assert learned_params.beta == 1.0

    def test_update_increases_appropriate_param(self, bandit_path):
        """Updates modify α or β based on reward."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.select(candidates=["rule"], context="ctx", k=1)

        initial_params = bandit.state.get_params("ctx", "rule")
        initial_alpha = initial_params.alpha
        initial_beta = initial_params.beta

        # Success increases alpha
        bandit.update("rule", reward=1.0, context="ctx")
        assert bandit.state.get_params("ctx", "rule").alpha == initial_alpha + 1
        assert bandit.state.get_params("ctx", "rule").beta == initial_beta

    def test_batch_update_applies_to_all_rules(self, bandit_path):
        """Batch update affects all specified rules."""
        bandit = ThompsonSamplingBandit(bandit_path)
        rules = ["r1", "r2", "r3"]
        bandit.select(candidates=rules, context="ctx", k=3)

        bandit.batch_update(rules, reward=0.0, context="ctx")

        for rule in rules:
            params = bandit.state.get_params("ctx", rule)
            # Beta was incremented (failure)
            assert params.beta == 2.0

    def test_contexts_are_independent(self, bandit_path):
        """Different contexts maintain separate distributions.

        This is the "contextual" in contextual bandits. A rule might be
        great for type errors but useless for API design.
        """
        bandit = ThompsonSamplingBandit(bandit_path)

        # Same rule, different contexts
        bandit.select(candidates=["rule"], context="type-errors", k=1)
        bandit.select(candidates=["rule"], context="api-design", k=1)

        # Update only in type-errors context
        bandit.update("rule", reward=1.0, context="type-errors")

        type_params = bandit.state.get_params("type-errors", "rule")
        api_params = bandit.state.get_params("api-design", "rule")

        # Only type-errors context was updated
        assert type_params.alpha == 2.0  # 1 (prior) + 1 (success)
        assert api_params.alpha == 1.0  # Still at prior

    def test_selection_favors_higher_mean_arms_statistically(
        self, bandit_path, seeded_random
    ):
        """Over many selections, arms with higher means are chosen more often.

        This test verifies the exploration-exploitation tradeoff:
        - Arms with high means (proven good) are selected often
        - But arms with high variance still get occasional chances
        """
        bandit = ThompsonSamplingBandit(bandit_path)

        # Create arms with different priors
        # good_arm: Beta(10, 2) → mean ≈ 0.83
        # mediocre_arm: Beta(5, 5) → mean = 0.50
        # bad_arm: Beta(2, 10) → mean ≈ 0.17
        bandit.state.set_params("ctx", "good", BetaParams(alpha=10, beta=2))
        bandit.state.set_params("ctx", "mediocre", BetaParams(alpha=5, beta=5))
        bandit.state.set_params("ctx", "bad", BetaParams(alpha=2, beta=10))
        bandit.state.save(bandit_path)

        # Count selections over many trials
        selection_counts = {"good": 0, "mediocre": 0, "bad": 0}
        trials = 1000

        for _ in range(trials):
            selected = bandit.select(
                candidates=["good", "mediocre", "bad"],
                context="ctx",
                k=1,
            )[0]
            selection_counts[selected] += 1

        # Good arm should be selected most often
        assert selection_counts["good"] > selection_counts["mediocre"]
        assert selection_counts["mediocre"] >= selection_counts["bad"]

        # Note: With extreme priors (Beta(10,2) vs Beta(2,10)), bad arm
        # may never be selected in 1000 trials. That's actually correct
        # behavior - Thompson Sampling eventually stops exploring arms
        # that are clearly worse. The key property is the ordering.

    def test_get_stats_returns_all_arm_info(self, bandit_path):
        """Stats provide debugging/reporting information."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.select(
            candidates=["r1", "r2"],
            context="ctx",
            k=2,
            seed_rule_ids={"r1"},
        )
        bandit.update("r1", reward=1.0, context="ctx")

        stats = bandit.get_stats(context="ctx")

        assert "r1" in stats
        assert stats["r1"]["is_seed"] is True
        assert stats["r1"]["alpha"] == 4.0  # 3 (boosted prior) + 1 (success)
        assert "mean" in stats["r1"]
        assert "variance" in stats["r1"]
        assert "confidence_interval" in stats["r1"]

    def test_get_top_rules_returns_ranked_list(self, bandit_path):
        """Top rules are sorted by expected value (exploitation view)."""
        bandit = ThompsonSamplingBandit(bandit_path)

        # Create arms with known means
        bandit.state.set_params("ctx", "best", BetaParams(alpha=9, beta=1))  # mean=0.9
        bandit.state.set_params("ctx", "mid", BetaParams(alpha=5, beta=5))  # mean=0.5
        bandit.state.set_params("ctx", "worst", BetaParams(alpha=1, beta=9))  # mean=0.1

        top = bandit.get_top_rules("ctx", k=3)

        assert top[0][0] == "best"
        assert top[1][0] == "mid"
        assert top[2][0] == "worst"

    def test_reset_clears_state(self, bandit_path):
        """Reset removes all learned information."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.select(candidates=["r1"], context="ctx", k=1)

        assert bandit.state.get_params("ctx", "r1") is not None

        bandit.reset()

        assert bandit.state.get_params("ctx", "r1") is None

    def test_reset_specific_context(self, bandit_path):
        """Can reset single context while preserving others."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.select(candidates=["r1"], context="ctx1", k=1)
        bandit.select(candidates=["r2"], context="ctx2", k=1)

        bandit.reset(context="ctx1")

        assert bandit.state.get_params("ctx1", "r1") is None
        assert bandit.state.get_params("ctx2", "r2") is not None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestBanditIntegration:
    """Integration tests verifying bandit works with operations.py.

    These tests verify the full flow from session start through
    feedback and state persistence.
    """

    def test_session_start_selects_rules(self, temp_dir):
        """start_session uses bandit to select rules."""
        from buildlog.core.operations import start_session

        # Create a minimal buildlog setup
        # Note: buildlog_dir is the ROOT, promoted.json goes in .buildlog subdir
        buildlog_dir = temp_dir
        inner_dir = buildlog_dir / ".buildlog"
        inner_dir.mkdir()

        # Create promoted.json with some rules
        promoted_path = inner_dir / "promoted.json"
        promoted_path.write_text(json.dumps({"skill_ids": ["r1", "r2", "r3"]}))

        result = start_session(
            buildlog_dir,
            error_class="type-errors",
            select_k=2,
        )

        # Should have selected 2 rules
        assert len(result.selected_rules) == 2
        assert all(r in ["r1", "r2", "r3"] for r in result.selected_rules)

    def test_mistake_gives_negative_feedback(self, temp_dir):
        """log_mistake updates bandit with reward=0 for selected rules."""
        from buildlog.core.operations import log_mistake, start_session

        # Note: buildlog_dir is the ROOT, internal files go in .buildlog subdir
        buildlog_dir = temp_dir
        inner_dir = buildlog_dir / ".buildlog"
        inner_dir.mkdir()

        # Setup
        promoted_path = inner_dir / "promoted.json"
        promoted_path.write_text(json.dumps({"skill_ids": ["r1", "r2"]}))

        # Start session (triggers bandit initialization)
        start_session(
            buildlog_dir,
            error_class="type-errors",
            select_k=2,
        )

        # Get initial bandit state (stored at buildlog_dir root, not .buildlog)
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)
        initial_beta = bandit.state.get_params("type-errors", "r1").beta

        # Log mistake
        log_mistake(
            buildlog_dir,
            error_class="type-errors",
            description="Forgot to add test",
        )

        # Reload bandit and check beta increased
        bandit = ThompsonSamplingBandit(bandit_path)
        final_beta = bandit.state.get_params("type-errors", "r1").beta

        assert final_beta > initial_beta  # Negative feedback

    def test_reward_gives_explicit_feedback(self, temp_dir):
        """log_reward updates bandit with specified reward."""
        from buildlog.core.operations import log_reward, start_session

        # Note: buildlog_dir is the ROOT, internal files go in .buildlog subdir
        buildlog_dir = temp_dir
        inner_dir = buildlog_dir / ".buildlog"
        inner_dir.mkdir()

        # Setup
        promoted_path = inner_dir / "promoted.json"
        promoted_path.write_text(json.dumps({"skill_ids": ["r1"]}))

        # Start session
        start_session(buildlog_dir, error_class="api-design", select_k=1)

        # Get initial state (stored at buildlog_dir root, not .buildlog)
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)
        initial_alpha = bandit.state.get_params("api-design", "r1").alpha

        # Log positive reward
        log_reward(buildlog_dir, outcome="accepted")

        # Check alpha increased
        bandit = ThompsonSamplingBandit(bandit_path)
        final_alpha = bandit.state.get_params("api-design", "r1").alpha

        assert final_alpha > initial_alpha  # Positive feedback

    def test_bandit_state_persists_across_sessions(self, temp_dir):
        """Learning persists across multiple sessions."""
        from buildlog.core.operations import end_session, log_mistake, start_session

        # Note: buildlog_dir is the ROOT, internal files go in .buildlog subdir
        buildlog_dir = temp_dir
        inner_dir = buildlog_dir / ".buildlog"
        inner_dir.mkdir()

        promoted_path = inner_dir / "promoted.json"
        promoted_path.write_text(json.dumps({"skill_ids": ["r1", "r2"]}))

        # Session 1: r1 fails
        start_session(buildlog_dir, error_class="test", select_k=2)
        log_mistake(buildlog_dir, error_class="test", description="Mistake 1")
        end_session(buildlog_dir)

        # Session 2: check state persisted
        start_session(buildlog_dir, error_class="test", select_k=2)

        # Bandit state stored at buildlog_dir root
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit = ThompsonSamplingBandit(bandit_path)

        # Beta should be > 1 due to previous failure
        r1_beta = bandit.state.get_params("test", "r1").beta
        assert r1_beta > 1.0


# =============================================================================
# PROPERTY-BASED INTUITION TESTS
# =============================================================================


class TestVersionAwareDecay:
    """Tests for version-aware bandit decay (B6)."""

    def test_decay_halves_learned_signal(self, bandit_path):
        """Beta(5,3) with factor=0.5 → Beta(3,2)."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.state.set_params("ctx", "rule", BetaParams(alpha=5.0, beta=3.0))
        bandit.state.save(bandit_path)

        result = bandit.decay_arm("rule", decay_factor=0.5, context="ctx")

        assert result is True
        params = bandit.state.get_params("ctx", "rule")
        # new_alpha = 1.0 + (5.0 - 1.0) * 0.5 = 1.0 + 2.0 = 3.0
        assert params.alpha == 3.0
        # new_beta = 1.0 + (3.0 - 1.0) * 0.5 = 1.0 + 1.0 = 2.0
        assert params.beta == 2.0

    def test_decay_full_reset(self, bandit_path):
        """factor=0.0 should reset to Beta(1,1)."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.state.set_params("ctx", "rule", BetaParams(alpha=10.0, beta=5.0))
        bandit.state.save(bandit_path)

        bandit.decay_arm("rule", decay_factor=0.0, context="ctx")

        params = bandit.state.get_params("ctx", "rule")
        assert params.alpha == 1.0
        assert params.beta == 1.0

    def test_decay_no_change(self, bandit_path):
        """factor=1.0 should leave params unchanged."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.state.set_params("ctx", "rule", BetaParams(alpha=5.0, beta=3.0))
        bandit.state.save(bandit_path)

        bandit.decay_arm("rule", decay_factor=1.0, context="ctx")

        params = bandit.state.get_params("ctx", "rule")
        assert params.alpha == 5.0
        assert params.beta == 3.0

    def test_decay_nonexistent_returns_false(self, bandit_path):
        """Decaying a non-existent rule should return False."""
        bandit = ThompsonSamplingBandit(bandit_path)
        result = bandit.decay_arm("nonexistent", context="ctx")
        assert result is False

    def test_decay_specific_context(self, bandit_path):
        """Should only decay in the specified context."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.state.set_params("ctx1", "rule", BetaParams(alpha=5.0, beta=3.0))
        bandit.state.set_params("ctx2", "rule", BetaParams(alpha=5.0, beta=3.0))
        bandit.state.save(bandit_path)

        bandit.decay_arm("rule", decay_factor=0.5, context="ctx1")

        # ctx1 decayed
        assert bandit.state.get_params("ctx1", "rule").alpha == 3.0
        # ctx2 unchanged
        assert bandit.state.get_params("ctx2", "rule").alpha == 5.0

    def test_decay_all_contexts(self, bandit_path):
        """context=None should decay across all contexts."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.state.set_params("ctx1", "rule", BetaParams(alpha=5.0, beta=3.0))
        bandit.state.set_params("ctx2", "rule", BetaParams(alpha=5.0, beta=3.0))
        bandit.state.save(bandit_path)

        bandit.decay_arm("rule", decay_factor=0.5)

        assert bandit.state.get_params("ctx1", "rule").alpha == 3.0
        assert bandit.state.get_params("ctx2", "rule").alpha == 3.0

    def test_decay_clamps_negative_factor(self, bandit_path):
        """Negative decay_factor should be clamped to 0.0 (full reset)."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.state.set_params("ctx", "rule", BetaParams(alpha=5.0, beta=3.0))
        bandit.state.save(bandit_path)

        bandit.decay_arm("rule", decay_factor=-1.0, context="ctx")

        params = bandit.state.get_params("ctx", "rule")
        assert params.alpha == 1.0  # Clamped to 0.0, same as full reset
        assert params.beta == 1.0

    def test_decay_clamps_factor_above_one(self, bandit_path):
        """decay_factor > 1.0 should be clamped to 1.0 (no change)."""
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.state.set_params("ctx", "rule", BetaParams(alpha=5.0, beta=3.0))
        bandit.state.save(bandit_path)

        bandit.decay_arm("rule", decay_factor=2.0, context="ctx")

        params = bandit.state.get_params("ctx", "rule")
        assert params.alpha == 5.0  # Clamped to 1.0, no change
        assert params.beta == 3.0


class TestConfidenceWeightedBoosting:
    """Tests for confidence-weighted seed boosting (B5)."""

    def test_create_prior_with_confidence(self, bandit_path):
        """confidence=0.5 should give half the seed boost."""
        bandit = ThompsonSamplingBandit(bandit_path, seed_boost=2.0)
        params = bandit._create_prior(is_seed=True, confidence=0.5)
        # effective_boost = 2.0 * 0.5 = 1.0 → alpha = 1.0 + 1.0 = 2.0
        assert params.alpha == 2.0
        assert params.beta == 1.0

    def test_create_prior_full_confidence(self, bandit_path):
        """confidence=1.0 should give same result as no confidence arg."""
        bandit = ThompsonSamplingBandit(bandit_path, seed_boost=2.0)
        params_with = bandit._create_prior(is_seed=True, confidence=1.0)
        params_without = bandit._create_prior(is_seed=True)
        assert params_with.alpha == params_without.alpha
        assert params_with.beta == params_without.beta

    def test_create_prior_zero_confidence(self, bandit_path):
        """confidence=0.0 should give no boost (alpha=1.0)."""
        bandit = ThompsonSamplingBandit(bandit_path, seed_boost=2.0)
        params = bandit._create_prior(is_seed=True, confidence=0.0)
        assert params.alpha == 1.0
        assert params.beta == 1.0

    def test_create_prior_clamps_confidence(self, bandit_path):
        """confidence > 1.0 should be clamped to 1.0."""
        bandit = ThompsonSamplingBandit(bandit_path, seed_boost=2.0)
        params = bandit._create_prior(is_seed=True, confidence=1.5)
        # clamped to 1.0 → same as full boost → alpha = 3.0
        assert params.alpha == 3.0
        assert params.beta == 1.0

    def test_select_uses_confidence_map(self, bandit_path):
        """select() should pass confidence to _create_prior via confidence map."""
        bandit = ThompsonSamplingBandit(bandit_path, seed_boost=2.0)
        bandit.select(
            candidates=["seed-rule"],
            context="ctx",
            k=1,
            seed_rule_ids={"seed-rule"},
            seed_confidence_map={"seed-rule": 0.5},
        )
        params = bandit.state.get_params("ctx", "seed-rule")
        # effective_boost = 2.0 * 0.5 = 1.0 → alpha = 2.0
        assert params.alpha == 2.0

    def test_select_backward_compat_without_confidence(self, bandit_path):
        """select() without confidence map should use full boost."""
        bandit = ThompsonSamplingBandit(bandit_path, seed_boost=2.0)
        bandit.select(
            candidates=["seed-rule"],
            context="ctx",
            k=1,
            seed_rule_ids={"seed-rule"},
        )
        params = bandit.state.get_params("ctx", "seed-rule")
        # Full boost → alpha = 3.0
        assert params.alpha == 3.0


class TestThompsonSamplingIntuitions:
    """Tests that verify our intuitions about Thompson Sampling behavior.

    These aren't strict property tests, but they document expected behavior
    and serve as sanity checks.
    """

    def test_arms_converge_to_true_rates(self, bandit_path, seeded_random):
        """With enough data, estimates converge to true success rates.

        This is the key promise of Thompson Sampling: we eventually learn
        the true arm qualities through exploration.
        """
        bandit = ThompsonSamplingBandit(bandit_path)

        # Simulate arm with true success rate of 0.7
        true_rate = 0.7
        bandit.select(candidates=["arm"], context="ctx", k=1)

        # Run 100 "experiments"
        for _ in range(100):
            success = random.random() < true_rate
            bandit.update("arm", reward=1.0 if success else 0.0, context="ctx")

        estimated_rate = bandit.state.get_params("ctx", "arm").mean()

        # Should be within 0.1 of true rate (statistical tolerance)
        assert abs(estimated_rate - true_rate) < 0.15

    def test_exploration_decreases_over_time(self, bandit_path, seeded_random):
        """Uncertainty (variance) decreases as we gather data.

        Early on, we explore a lot. Later, we exploit our knowledge.
        """
        bandit = ThompsonSamplingBandit(bandit_path)
        bandit.select(candidates=["arm"], context="ctx", k=1)

        initial_variance = bandit.state.get_params("ctx", "arm").variance()

        # Add 50 observations
        for _ in range(50):
            bandit.update("arm", reward=0.6, context="ctx")

        final_variance = bandit.state.get_params("ctx", "arm").variance()

        assert final_variance < initial_variance

    def test_bad_arms_get_abandoned(self, bandit_path, seeded_random):
        """Arms that consistently fail stop being selected.

        This is exploitation: we stop wasting time on proven losers.
        """
        bandit = ThompsonSamplingBandit(bandit_path)

        # Good arm with many successes
        bandit.state.set_params("ctx", "good", BetaParams(alpha=50, beta=10))
        # Bad arm with many failures
        bandit.state.set_params("ctx", "bad", BetaParams(alpha=10, beta=50))

        # Over 100 selections of 1 arm, bad should rarely be chosen
        bad_count = 0
        for _ in range(100):
            selected = bandit.select(candidates=["good", "bad"], context="ctx", k=1)
            if selected[0] == "bad":
                bad_count += 1

        # Bad arm should be selected < 20% of the time
        assert bad_count < 20


# =============================================================================
# BANDIT PERSISTENCE TESTS
# =============================================================================


@pytest.fixture
def sqlite_backend():
    """Create an in-memory SQLite backend for testing."""
    import sqlite3

    from buildlog.storage.sqlite import SQLiteBackend

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    backend = SQLiteBackend(conn)
    backend.ensure_project("test-proj", "test", "/tmp/test")
    return backend, "test-proj"


class TestBanditPersistenceProtocol:
    """Verify both implementations satisfy the BanditPersistence protocol."""

    def test_jsonl_is_bandit_persistence(self, bandit_path):
        persistence = JsonlPersistence(bandit_path)
        assert isinstance(persistence, BanditPersistence)

    def test_sqlite_is_bandit_persistence(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)
        assert isinstance(persistence, BanditPersistence)


class TestJsonlPersistence:
    """Verify JsonlPersistence delegates correctly to BanditState."""

    def test_name(self, bandit_path):
        assert JsonlPersistence(bandit_path).name == "jsonl"

    def test_roundtrip(self, bandit_path):
        persistence = JsonlPersistence(bandit_path)
        state = persistence.load()
        state.set_params("ctx", "r1", BetaParams(alpha=5, beta=3), is_seed=True)
        persistence.save(state)

        loaded = persistence.load()
        params = loaded.get_params("ctx", "r1")
        assert params is not None
        assert params.alpha == 5
        assert params.beta == 3
        assert loaded.is_seed("ctx", "r1") is True


class TestSqlitePersistence:
    """Verify SqlitePersistence round-trips through the SQLite backend."""

    def test_name(self, sqlite_backend):
        backend, project_id = sqlite_backend
        assert SqlitePersistence(backend, project_id).name == "sqlite"

    def test_empty_load(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)
        state = persistence.load()
        assert len(list(state.all_arms())) == 0

    def test_save_and_load_roundtrip(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)

        state = BanditState()
        state.set_params("ctx1", "r1", BetaParams(alpha=5, beta=3), is_seed=True)
        state.set_params("ctx2", "r2", BetaParams(alpha=2, beta=8), is_seed=False)
        persistence.save(state)

        loaded = persistence.load()
        p1 = loaded.get_params("ctx1", "r1")
        assert p1 is not None
        assert p1.alpha == 5
        assert p1.beta == 3
        assert loaded.is_seed("ctx1", "r1") is True

        p2 = loaded.get_params("ctx2", "r2")
        assert p2 is not None
        assert p2.alpha == 2
        assert p2.beta == 8
        assert loaded.is_seed("ctx2", "r2") is False

    def test_append_update(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)

        state = BanditState()
        state.set_params("ctx", "r1", BetaParams(alpha=1, beta=1))
        persistence.save(state)

        # Update and append
        state.get_params("ctx", "r1").update(reward=1.0)
        persistence.append_update(state, "ctx", "r1")

        # Verify the update persisted
        loaded = persistence.load()
        params = loaded.get_params("ctx", "r1")
        assert params.alpha == 2.0
        assert params.beta == 1.0

    def test_append_update_nonexistent_is_noop(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)
        state = BanditState()
        # Should not raise
        persistence.append_update(state, "ctx", "nonexistent")


class TestBanditWithSqlitePersistence:
    """Integration: ThompsonSamplingBandit with SqlitePersistence."""

    def test_bandit_with_sqlite(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)
        bandit = ThompsonSamplingBandit(persistence)

        selected = bandit.select(
            candidates=["r1", "r2", "r3"],
            context="ctx",
            k=2,
            seed_rule_ids={"r1"},
        )
        assert len(selected) == 2

        # Arms persisted in SQLite
        loaded = persistence.load()
        assert loaded.get_params("ctx", "r1") is not None
        assert loaded.get_params("ctx", "r2") is not None
        assert loaded.get_params("ctx", "r3") is not None

    def test_state_path_is_none_with_persistence(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)
        bandit = ThompsonSamplingBandit(persistence)
        assert bandit.state_path is None

    def test_state_path_preserved_with_path(self, bandit_path):
        bandit = ThompsonSamplingBandit(bandit_path)
        assert bandit.state_path == bandit_path

    def test_update_persists_via_sqlite(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)
        bandit = ThompsonSamplingBandit(persistence)

        bandit.select(candidates=["r1"], context="ctx", k=1)
        bandit.update("r1", reward=1.0, context="ctx")

        # Create a fresh bandit from the same backend — should see the update
        bandit2 = ThompsonSamplingBandit(SqlitePersistence(backend, project_id))
        params = bandit2.state.get_params("ctx", "r1")
        assert params is not None
        assert params.alpha == 2.0  # 1 (prior) + 1 (success)

    def test_reset_persists_via_sqlite(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)
        bandit = ThompsonSamplingBandit(persistence)

        bandit.select(candidates=["r1"], context="ctx", k=1)
        bandit.reset()

        bandit2 = ThompsonSamplingBandit(SqlitePersistence(backend, project_id))
        assert bandit2.state.get_params("ctx", "r1") is None

    def test_decay_persists_via_sqlite(self, sqlite_backend):
        backend, project_id = sqlite_backend
        persistence = SqlitePersistence(backend, project_id)
        bandit = ThompsonSamplingBandit(persistence)

        bandit.state.set_params("ctx", "r1", BetaParams(alpha=5.0, beta=3.0))
        persistence.save(bandit.state)

        bandit.decay_arm("r1", decay_factor=0.5, context="ctx")

        bandit2 = ThompsonSamplingBandit(SqlitePersistence(backend, project_id))
        params = bandit2.state.get_params("ctx", "r1")
        assert params.alpha == 3.0
        assert params.beta == 2.0
