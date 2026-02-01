"""Pure Python statistical tests for experiment evaluation.

Uses only ``math`` and ``random`` from the standard library.
"""

from __future__ import annotations

__all__ = [
    "fisher_exact_test",
    "permutation_test",
    "bootstrap_ci",
    "cohens_h",
]

import math
import random

# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _log_comb(n: int, k: int) -> float:
    """Log-space binomial coefficient using lgamma to avoid overflow."""
    if k < 0 or k > n:
        return float("-inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def _hypergeom_log_pmf(k: int, N: int, K: int, n: int) -> float:
    """Log of hypergeometric PMF: P(X=k) for pop N, successes K, draws n."""
    return _log_comb(K, k) + _log_comb(N - K, n - k) - _log_comb(N, n)


# ---------------------------------------------------------------------------
# Fisher exact test (2×2)
# ---------------------------------------------------------------------------


def fisher_exact_test(a: int, b: int, c: int, d: int) -> tuple[float, float]:
    """Two-sided Fisher exact test for a 2×2 contingency table.

    Table layout::

             Group1  Group2
        Yes    a       b
        No     c       d

    Returns ``(odds_ratio, p_value)``.
    """
    if any(x < 0 for x in (a, b, c, d)):
        raise ValueError("Cell counts must be non-negative")

    # Odds ratio
    if b * c == 0:
        odds_ratio = (
            float("inf") if a * d > 0 else (1.0 if a * d == 0 and b * c == 0 else 0.0)
        )
    else:
        odds_ratio = (a * d) / (b * c)

    N = a + b + c + d
    K = a + b  # row 1 total
    n = a + c  # col 1 total

    if N == 0:
        return (1.0, 1.0)

    # Observed log-pmf
    observed_log_p = _hypergeom_log_pmf(a, N, K, n)

    # Sum probabilities for all tables as extreme or more extreme (two-sided)
    lo = max(0, n - (N - K))
    hi = min(n, K)

    p_value = 0.0
    for k in range(lo, hi + 1):
        log_p = _hypergeom_log_pmf(k, N, K, n)
        if log_p <= observed_log_p + 1e-12:  # as extreme or more extreme
            p_value += math.exp(log_p)

    p_value = min(p_value, 1.0)
    return (odds_ratio, p_value)


# ---------------------------------------------------------------------------
# Permutation test
# ---------------------------------------------------------------------------


def permutation_test(
    group_a: list[float],
    group_b: list[float],
    n_permutations: int = 10000,
    seed: int = 42,
) -> float:
    """Two-sided permutation test for difference in means.

    Returns a p-value. Deterministic when *seed* is fixed.
    """
    if not group_a or not group_b:
        raise ValueError("Both groups must be non-empty")

    observed_diff = abs(sum(group_a) / len(group_a) - sum(group_b) / len(group_b))
    combined = group_a + group_b
    n_a = len(group_a)
    rng = random.Random(seed)

    count = 0
    for _ in range(n_permutations):
        rng.shuffle(combined)
        perm_a = combined[:n_a]
        perm_b = combined[n_a:]
        perm_diff = abs(sum(perm_a) / len(perm_a) - sum(perm_b) / len(perm_b))
        if perm_diff >= observed_diff - 1e-12:
            count += 1

    return count / n_permutations


# ---------------------------------------------------------------------------
# Bootstrap confidence interval
# ---------------------------------------------------------------------------


def bootstrap_ci(
    data: list[float],
    statistic_fn=None,
    n_bootstrap: int = 10000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Percentile bootstrap confidence interval.

    *statistic_fn* defaults to the arithmetic mean.

    Returns ``(point_estimate, ci_lower, ci_upper)``.
    """
    if not data:
        raise ValueError("Data must be non-empty")

    if statistic_fn is None:

        def statistic_fn(d: list[float]) -> float:
            return sum(d) / len(d)

    point = statistic_fn(data)
    rng = random.Random(seed)
    n = len(data)

    estimates: list[float] = []
    for _ in range(n_bootstrap):
        sample = [data[rng.randint(0, n - 1)] for _ in range(n)]
        estimates.append(statistic_fn(sample))

    estimates.sort()
    alpha = 1 - confidence
    lo_idx = int(math.floor((alpha / 2) * n_bootstrap))
    hi_idx = int(math.floor((1 - alpha / 2) * n_bootstrap)) - 1
    lo_idx = max(0, min(lo_idx, n_bootstrap - 1))
    hi_idx = max(0, min(hi_idx, n_bootstrap - 1))

    return (point, estimates[lo_idx], estimates[hi_idx])


# ---------------------------------------------------------------------------
# Cohen's h
# ---------------------------------------------------------------------------


def cohens_h(p1: float, p2: float) -> float:
    """Cohen's *h* effect size for two proportions.

    ``h = 2 * arcsin(sqrt(p1)) - 2 * arcsin(sqrt(p2))``
    """
    if not (0 <= p1 <= 1) or not (0 <= p2 <= 1):
        raise ValueError("Proportions must be between 0 and 1")
    return 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))
