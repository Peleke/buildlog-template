"""Thompson Sampling Bandit for Contextual Rule Selection.

=============================================================================
CANONICAL EXAMPLE: Thompson Sampling with Beta-Bernoulli Distributions
=============================================================================

This module implements a contextual multi-armed bandit using Thompson Sampling
for automatic rule selection in buildlog. It serves as an instructive,
production-ready example of these fundamental concepts.

BACKGROUND: THE MULTI-ARMED BANDIT PROBLEM
------------------------------------------
Imagine you're in a casino with multiple slot machines ("arms"). Each machine
has an unknown probability of paying out. You want to maximize your winnings,
but you face a fundamental tension:

  - EXPLOITATION: Play the machine that has paid best so far
  - EXPLORATION: Try other machines to learn if they're actually better

This is the "explore-exploit tradeoff" - one of the most important concepts
in decision-making under uncertainty.

WHY THOMPSON SAMPLING?
----------------------
Thompson Sampling is an elegant Bayesian approach that naturally balances
exploration and exploitation:

  1. Maintain a probability distribution over each arm's true reward rate
  2. Sample from each distribution
  3. Pick the arm with the highest sample

The magic: arms we're uncertain about have high-variance distributions,
so they occasionally produce high samples, causing us to explore them.
As we gather data, distributions narrow, and we naturally exploit.

BETA-BERNOULLI MODEL
--------------------
For binary outcomes (success/failure), we use:

  - Prior: Beta(α, β) - our belief before seeing data
  - Likelihood: Bernoulli - each observation is success (1) or failure (0)
  - Posterior: Beta(α + successes, β + failures)

The Beta distribution is "conjugate" to Bernoulli, meaning the posterior
has the same form as the prior. This makes updates trivial:

  After observing a success:  α → α + 1
  After observing a failure:  β → β + 1

CONTEXTUAL EXTENSION
--------------------
"Contextual" means we maintain separate distributions per context. In buildlog:

  - Context = error class (e.g., "type-errors", "api-design")
  - Arms = rules (skills that should prevent mistakes)

A rule might be excellent for type errors but useless for API design.
Separate distributions let us learn this.

USAGE IN BUILDLOG
-----------------
  1. Session starts → bandit.select() picks top-k rules for this error class
  2. Mistake logged → bandit.update(reward=0) for rules that didn't help
  3. Explicit reward → bandit.update(reward=value) for direct feedback

References:
  - Thompson (1933). "On the likelihood that one unknown probability exceeds another"
  - Russo et al. (2018). "A Tutorial on Thompson Sampling"
  - https://en.wikipedia.org/wiki/Thompson_sampling
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

__all__ = [
    "BetaParams",
    "BanditState",
    "ThompsonSamplingBandit",
    "DEFAULT_SEED_BOOST",
    "DEFAULT_CONTEXT",
]

# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_SEED_BOOST = 2.0  # Extra α for seed rules (higher prior confidence)
DEFAULT_CONTEXT = "general"  # Fallback when no error class specified


# ============================================================================
# BETA DISTRIBUTION PARAMETERS
# ============================================================================


@dataclass
class BetaParams:
    """Parameters for a Beta distribution representing belief about a rule's effectiveness.

    The Beta distribution is parameterized by α (alpha) and β (beta):

        Beta(α, β) has mean = α / (α + β)

    Interpretation:
        - α represents "pseudo-successes" (prior + observed successes)
        - β represents "pseudo-failures" (prior + observed failures)

    With uninformative prior Beta(1, 1):
        - Uniform distribution over [0, 1]
        - Mean = 0.5 (maximum uncertainty)

    As we observe outcomes:
        - Success → α += 1 (distribution shifts right)
        - Failure → β += 1 (distribution shifts left)
        - More observations → distribution narrows (less uncertainty)

    Example evolution:
        Beta(1, 1)   → Uniform, mean=0.5, high variance
        Beta(3, 2)   → Skewed right, mean=0.6, moderate variance
        Beta(30, 20) → Peaked at 0.6, low variance (high confidence)

    Attributes:
        alpha: Pseudo-count of successes (must be > 0)
        beta: Pseudo-count of failures (must be > 0)
    """

    alpha: float = 1.0
    beta: float = 1.0

    def __post_init__(self) -> None:
        """Validate parameters."""
        if self.alpha <= 0 or self.beta <= 0:
            raise ValueError(
                f"Alpha and beta must be positive: α={self.alpha}, β={self.beta}"
            )

    def sample(self) -> float:
        """Draw a random sample from Beta(α, β).

        This is the core of Thompson Sampling: we sample from our belief
        distribution rather than using the mean. This naturally balances
        exploration (high variance → occasional high samples) and
        exploitation (high mean → consistently high samples).

        Returns:
            A value in [0, 1] representing a possible true reward rate.
        """
        return random.betavariate(self.alpha, self.beta)

    def update(self, reward: float) -> None:
        """Update posterior with observed reward.

        For Bernoulli rewards (0 or 1), this is exact Bayesian inference.
        For continuous rewards in [0, 1], this is an approximation that
        still works well in practice.

        Args:
            reward: Observed reward, typically in [0, 1].
                   - 1.0 = full success (rule helped)
                   - 0.0 = failure (rule didn't help)
                   - Values in between for partial credit
        """
        self.alpha += reward
        self.beta += 1.0 - reward

    def mean(self) -> float:
        """Expected value of the distribution.

        This is our best point estimate of the arm's true reward rate.
        We don't use this for selection (we sample instead), but it's
        useful for reporting and debugging.

        Returns:
            E[X] = α / (α + β)
        """
        return self.alpha / (self.alpha + self.beta)

    def variance(self) -> float:
        """Variance of the distribution.

        Higher variance means more uncertainty. Thompson Sampling
        naturally explores high-variance arms because their samples
        occasionally exceed the mean.

        Returns:
            Var[X] = αβ / ((α + β)² × (α + β + 1))
        """
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total * total * (total + 1))

    def confidence_interval(self, level: float = 0.95) -> tuple[float, float]:
        """Approximate confidence interval using normal approximation.

        For large α + β, the Beta distribution approaches normal.
        This gives us a quick sense of our uncertainty range.

        Args:
            level: Confidence level (default 0.95 for 95% CI).

        Returns:
            (lower, upper) bounds of the interval.
        """
        import math

        mean = self.mean()
        std = math.sqrt(self.variance())
        # Z-score for 95% CI is approximately 1.96
        z = 1.96 if level == 0.95 else 2.576 if level == 0.99 else 1.645

        lower = max(0.0, mean - z * std)
        upper = min(1.0, mean + z * std)
        return (lower, upper)

    def to_dict(self) -> dict[str, float]:
        """Serialize for storage."""
        return {"alpha": self.alpha, "beta": self.beta}

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> BetaParams:
        """Deserialize from storage."""
        return cls(alpha=data["alpha"], beta=data["beta"])


# ============================================================================
# BANDIT STATE PERSISTENCE
# ============================================================================


@dataclass
class ArmRecord:
    """A single arm's state record for persistence.

    Stored as one line in the JSONL file.
    """

    context: str
    rule_id: str
    params: BetaParams
    is_seed: bool = False
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Serialize for JSONL storage."""
        return {
            "context": self.context,
            "rule_id": self.rule_id,
            "alpha": self.params.alpha,
            "beta": self.params.beta,
            "is_seed": self.is_seed,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ArmRecord:
        """Deserialize from JSONL storage."""
        updated_at = datetime.fromisoformat(data["updated_at"])
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        return cls(
            context=data["context"],
            rule_id=data["rule_id"],
            params=BetaParams(alpha=data["alpha"], beta=data["beta"]),
            is_seed=data.get("is_seed", False),
            updated_at=updated_at,
        )


@dataclass
class BanditState:
    """Persisted state for the contextual bandit.

    Structure:
        arms[context][rule_id] = BetaParams

    This allows O(1) lookup for any (context, rule) pair while
    maintaining separate belief distributions per context.

    Storage Format (JSONL):
        Each line is a JSON object representing one arm's state.
        We use append-only writes and compact on load to handle
        concurrent access and crash recovery gracefully.

    Example .buildlog/bandit_state.jsonl:
        {"context": "type-errors", "rule_id": "arch-123", "alpha": 3.0, "beta": 2.0, ...}
        {"context": "type-errors", "rule_id": "arch-123", "alpha": 4.0, "beta": 2.0, ...}

    The second line supersedes the first (same context + rule_id).
    """

    arms: dict[str, dict[str, BetaParams]] = field(default_factory=dict)
    seed_flags: dict[str, dict[str, bool]] = field(default_factory=dict)

    def get_params(self, context: str, rule_id: str) -> BetaParams | None:
        """Get parameters for a (context, rule) pair, if they exist."""
        return self.arms.get(context, {}).get(rule_id)

    def set_params(
        self,
        context: str,
        rule_id: str,
        params: BetaParams,
        is_seed: bool = False,
    ) -> None:
        """Set parameters for a (context, rule) pair."""
        if context not in self.arms:
            self.arms[context] = {}
            self.seed_flags[context] = {}
        self.arms[context][rule_id] = params
        self.seed_flags[context][rule_id] = is_seed

    def is_seed(self, context: str, rule_id: str) -> bool:
        """Check if a rule was initialized as a seed rule."""
        return self.seed_flags.get(context, {}).get(rule_id, False)

    def all_arms(self) -> Iterator[tuple[str, str, BetaParams]]:
        """Iterate over all (context, rule_id, params) tuples."""
        for context, rules in self.arms.items():
            for rule_id, params in rules.items():
                yield context, rule_id, params

    @classmethod
    def load(cls, path: Path) -> BanditState:
        """Load state from JSONL file, compacting duplicate entries.

        Because we append updates, the file may contain multiple entries
        for the same (context, rule_id). We keep only the latest.
        """
        state = cls()

        if not path.exists():
            return state

        # Read all records, keeping only the latest per (context, rule_id)
        records: dict[tuple[str, str], ArmRecord] = {}

        for line in path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                record = ArmRecord.from_dict(data)
                key = (record.context, record.rule_id)

                # Keep if newer or first seen
                if key not in records or record.updated_at > records[key].updated_at:
                    records[key] = record
            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip malformed lines (crash recovery)
                continue

        # Populate state from compacted records
        for (context, rule_id), record in records.items():
            state.set_params(context, rule_id, record.params, record.is_seed)

        return state

    def save(self, path: Path) -> None:
        """Save full state to JSONL file (compacted).

        This writes a fresh file with one line per arm, removing
        any historical duplicates from append-only updates.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        for context, rule_id, params in self.all_arms():
            record = ArmRecord(
                context=context,
                rule_id=rule_id,
                params=params,
                is_seed=self.is_seed(context, rule_id),
            )
            lines.append(json.dumps(record.to_dict()))

        path.write_text("\n".join(lines) + "\n" if lines else "")

    def append_update(self, path: Path, context: str, rule_id: str) -> None:
        """Append a single arm's update to the JSONL file.

        This is more efficient than rewriting the entire file for
        each update. The file will be compacted on next load.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        params = self.get_params(context, rule_id)
        if params is None:
            return

        record = ArmRecord(
            context=context,
            rule_id=rule_id,
            params=params,
            is_seed=self.is_seed(context, rule_id),
        )

        with open(path, "a") as f:
            f.write(json.dumps(record.to_dict()) + "\n")


# ============================================================================
# THOMPSON SAMPLING BANDIT
# ============================================================================


class ThompsonSamplingBandit:
    """Thompson Sampling bandit for contextual rule selection.

    This is the main interface for the bandit. It handles:

    1. SELECTION: Pick top-k rules for a given context
       - Sample from each rule's Beta distribution
       - Return rules with highest samples
       - Initialize new rules with appropriate priors

    2. UPDATES: Learn from feedback
       - Success (reward=1): rule helped prevent mistakes
       - Failure (reward=0): mistake occurred despite rule
       - Partial (0 < reward < 1): for nuanced feedback

    3. PERSISTENCE: State survives across sessions
       - Append-only writes for crash safety
       - Compact on load for efficiency

    Example usage:
        bandit = ThompsonSamplingBandit(buildlog_dir / "bandit_state.jsonl")

        # At session start: select rules
        selected = bandit.select(
            candidates=["rule-1", "rule-2", "rule-3"],
            context="type-errors",
            k=2,
        )
        # selected might be ["rule-2", "rule-1"] based on sampling

        # On mistake: negative feedback
        for rule_id in selected:
            bandit.update(rule_id, reward=0.0, context="type-errors")

        # On success: positive feedback
        bandit.update("rule-2", reward=1.0, context="type-errors")
    """

    def __init__(
        self,
        state_path: Path,
        seed_boost: float = DEFAULT_SEED_BOOST,
        default_context: str = DEFAULT_CONTEXT,
    ):
        """Initialize the bandit.

        Args:
            state_path: Path to JSONL file for persistence.
            seed_boost: Extra α for seed rules. Higher values mean
                       seed rules start with higher assumed success rates.
                       Default 2.0 means seed rules start as if they've
                       already had 2 extra successes.
            default_context: Fallback context when none specified.
        """
        self.state_path = state_path
        self.seed_boost = seed_boost
        self.default_context = default_context
        self.state = BanditState.load(state_path)

    def select(
        self,
        candidates: list[str],
        context: str | None = None,
        k: int = 3,
        seed_rule_ids: set[str] | None = None,
    ) -> list[str]:
        """Select top-k rules using Thompson Sampling.

        This is where the magic happens:

        1. For each candidate rule, get or create its Beta distribution
        2. Sample from each distribution (not the mean!)
        3. Return the k rules with highest samples

        The sampling step is crucial: it means rules we're uncertain about
        (high variance) will occasionally beat rules with higher means,
        ensuring we explore enough to learn their true values.

        Args:
            candidates: List of rule IDs to choose from.
            context: Error class for contextual selection.
                    Different contexts have independent distributions.
            k: Number of rules to select.
            seed_rule_ids: Set of rule IDs that are from seeds (axioms).
                          These get boosted priors.

        Returns:
            List of k rule IDs, ordered by their sampled values (best first).
            If fewer than k candidates, returns all of them.
        """
        ctx = context or self.default_context
        seed_ids = seed_rule_ids or set()

        # Sample from each candidate's distribution
        samples: list[tuple[str, float]] = []

        for rule_id in candidates:
            params = self.state.get_params(ctx, rule_id)

            if params is None:
                # Initialize new arm
                is_seed = rule_id in seed_ids
                params = self._create_prior(is_seed)
                self.state.set_params(ctx, rule_id, params, is_seed)

            # THE KEY STEP: sample, don't use mean
            sample = params.sample()
            samples.append((rule_id, sample))

        # Sort by sampled value (descending) and take top k
        samples.sort(key=lambda x: x[1], reverse=True)
        selected = [rule_id for rule_id, _ in samples[:k]]

        # Persist any new arms we created
        self.state.save(self.state_path)

        return selected

    def update(
        self,
        rule_id: str,
        reward: float,
        context: str | None = None,
    ) -> None:
        """Update posterior for a rule based on observed reward.

        This is Bayesian learning in action:

            Prior: Beta(α, β)
            + Observation: reward r
            = Posterior: Beta(α + r, β + (1 - r))

        Over time, rules that consistently help will have high α,
        rules that don't help will have high β, and the bandit will
        naturally favor effective rules.

        Args:
            rule_id: The rule to update.
            reward: Observed reward in [0, 1].
                   - 1.0: Rule helped (full success)
                   - 0.0: Rule didn't help (failure)
                   - 0.5: Partial credit
            context: Error class context.
        """
        ctx = context or self.default_context
        params = self.state.get_params(ctx, rule_id)

        if params is None:
            # Rule wasn't initialized yet - create with default prior
            params = self._create_prior(is_seed=False)
            self.state.set_params(ctx, rule_id, params, is_seed=False)

        # Bayesian update
        params.update(reward)

        # Persist (append-only for efficiency)
        self.state.append_update(self.state_path, ctx, rule_id)

    def batch_update(
        self,
        rule_ids: list[str],
        reward: float,
        context: str | None = None,
    ) -> None:
        """Update multiple rules with the same reward.

        Convenience method for updating all rules active during a session
        when a mistake occurs (reward=0) or when giving positive feedback
        (reward>0) to all active rules.

        Args:
            rule_ids: Rules to update.
            reward: Reward value for all rules.
            context: Error class context.
        """
        for rule_id in rule_ids:
            self.update(rule_id, reward, context)

    def get_stats(self, context: str | None = None) -> dict[str, dict]:
        """Get statistics for all rules in a context.

        Useful for debugging and reporting.

        Args:
            context: Error class to get stats for.
                    If None, returns stats for all contexts.

        Returns:
            Dict mapping rule_id to stats dict with:
            - mean: Expected reward rate
            - alpha, beta: Distribution parameters
            - variance: Uncertainty measure
            - is_seed: Whether this is a seed rule
            - confidence_interval: 95% CI
        """
        stats: dict[str, dict] = {}

        if context is not None:
            contexts = [context]
        else:
            contexts = list(self.state.arms.keys())

        for ctx in contexts:
            rules = self.state.arms.get(ctx, {})
            for rule_id, params in rules.items():
                key = f"{ctx}:{rule_id}" if context is None else rule_id
                ci_low, ci_high = params.confidence_interval()
                stats[key] = {
                    "context": ctx,
                    "mean": round(params.mean(), 4),
                    "alpha": params.alpha,
                    "beta": params.beta,
                    "variance": round(params.variance(), 6),
                    "is_seed": self.state.is_seed(ctx, rule_id),
                    "confidence_interval": (round(ci_low, 4), round(ci_high, 4)),
                    "total_observations": params.alpha
                    + params.beta
                    - 2,  # Subtract prior
                }

        return stats

    def get_top_rules(
        self,
        context: str,
        k: int = 10,
    ) -> list[tuple[str, float]]:
        """Get top rules by expected value (not sampled).

        Unlike select(), this uses the mean rather than sampling.
        Useful for reporting "best rules so far" without the
        exploration randomness.

        Args:
            context: Error class.
            k: Number of rules to return.

        Returns:
            List of (rule_id, mean) tuples, sorted by mean descending.
        """
        rules = self.state.arms.get(context, {})
        ranked = [(rule_id, params.mean()) for rule_id, params in rules.items()]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:k]

    def _create_prior(self, is_seed: bool) -> BetaParams:
        """Create prior distribution for a new arm.

        Seed rules (from gauntlet personas / axioms) get a boosted prior,
        reflecting our belief that curated rules are likely effective.

        Non-seed rules get the uninformative Beta(1, 1) prior,
        meaning we start with maximum uncertainty about their value.

        Args:
            is_seed: Whether this rule comes from seeds.

        Returns:
            BetaParams with appropriate prior.
        """
        if is_seed:
            # Boosted prior: as if rule already had seed_boost successes
            # Beta(1 + boost, 1) → mean = (1 + boost) / (2 + boost)
            # With boost=2: mean = 3/4 = 0.75 (optimistic)
            return BetaParams(alpha=1.0 + self.seed_boost, beta=1.0)
        else:
            # Uninformative prior: maximum uncertainty
            # Beta(1, 1) is uniform → mean = 0.5
            return BetaParams(alpha=1.0, beta=1.0)

    def reset(self, context: str | None = None) -> None:
        """Reset bandit state.

        Use with caution - this discards learned information.

        Args:
            context: If provided, only reset this context.
                    If None, reset everything.
        """
        if context is None:
            self.state = BanditState()
        else:
            if context in self.state.arms:
                del self.state.arms[context]
            if context in self.state.seed_flags:
                del self.state.seed_flags[context]

        self.state.save(self.state_path)
