"""Exhaustive tests for pure Python statistical functions."""

from __future__ import annotations

import math

import pytest

from buildlog.engine.statistics import (
    bootstrap_ci,
    cohens_h,
    fisher_exact_test,
    permutation_test,
)

# ---------------------------------------------------------------------------
# Fisher exact test
# ---------------------------------------------------------------------------


class TestFisherExact:
    def test_known_table(self):
        # Classic lady tasting tea: [[3,1],[1,3]]
        odds, p = fisher_exact_test(3, 1, 1, 3)
        assert odds == 9.0
        assert 0 < p <= 1.0

    def test_no_effect(self):
        odds, p = fisher_exact_test(5, 5, 5, 5)
        assert abs(odds - 1.0) < 1e-9
        assert p > 0.5

    def test_all_in_one_cell(self):
        odds, p = fisher_exact_test(10, 0, 0, 0)
        # degenerate table
        assert p > 0

    def test_zero_cells(self):
        odds, p = fisher_exact_test(0, 0, 0, 0)
        assert p == 1.0

    def test_perfect_separation(self):
        odds, p = fisher_exact_test(10, 0, 0, 10)
        assert odds == float("inf")
        assert p < 0.01

    def test_large_table(self):
        # Should not overflow
        odds, p = fisher_exact_test(100, 50, 60, 90)
        assert 0 < p <= 1.0
        assert odds > 0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            fisher_exact_test(-1, 0, 0, 0)

    def test_symmetric(self):
        _, p1 = fisher_exact_test(3, 1, 1, 3)
        _, p2 = fisher_exact_test(1, 3, 3, 1)
        assert abs(p1 - p2) < 1e-9


# ---------------------------------------------------------------------------
# Permutation test
# ---------------------------------------------------------------------------


class TestPermutationTest:
    def test_identical_groups_high_p(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [1.0, 2.0, 3.0, 4.0, 5.0]
        p = permutation_test(a, b)
        assert p > 0.9

    def test_very_different_groups_low_p(self):
        a = [100.0, 101.0, 102.0, 103.0, 104.0]
        b = [0.0, 1.0, 2.0, 3.0, 4.0]
        p = permutation_test(a, b)
        assert p < 0.01

    def test_deterministic_with_seed(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        p1 = permutation_test(a, b, seed=42)
        p2 = permutation_test(a, b, seed=42)
        assert p1 == p2

    def test_different_seeds_may_differ(self):
        a = [1.0, 2.0, 3.0, 4.0]
        b = [3.0, 4.0, 5.0, 6.0]
        p1 = permutation_test(a, b, seed=1)
        p2 = permutation_test(a, b, seed=999)
        # May or may not differ, but should both be valid
        assert 0 <= p1 <= 1
        assert 0 <= p2 <= 1

    def test_empty_group_raises(self):
        with pytest.raises(ValueError):
            permutation_test([], [1.0])
        with pytest.raises(ValueError):
            permutation_test([1.0], [])

    def test_single_element_groups(self):
        p = permutation_test([10.0], [20.0])
        assert 0 <= p <= 1

    def test_p_value_bounds(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        p = permutation_test(a, b, n_permutations=100)
        assert 0 <= p <= 1


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------


class TestBootstrapCI:
    def test_known_mean(self):
        data = [10.0] * 100
        point, lo, hi = bootstrap_ci(data)
        assert abs(point - 10.0) < 1e-9
        assert abs(lo - 10.0) < 1e-9
        assert abs(hi - 10.0) < 1e-9

    def test_ci_contains_mean(self):
        data = list(range(100))
        data_f = [float(x) for x in data]
        point, lo, hi = bootstrap_ci(data_f)
        assert lo <= point <= hi

    def test_custom_statistic(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        point, lo, hi = bootstrap_ci(data, statistic_fn=max)
        assert point == 5.0
        assert lo <= hi

    def test_single_element(self):
        point, lo, hi = bootstrap_ci([42.0])
        assert point == 42.0
        assert lo == 42.0
        assert hi == 42.0

    def test_deterministic(self):
        data = [1.0, 2.0, 3.0, 4.0]
        r1 = bootstrap_ci(data, seed=42)
        r2 = bootstrap_ci(data, seed=42)
        assert r1 == r2

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            bootstrap_ci([])

    def test_wider_ci_with_more_variance(self):
        narrow = [5.0, 5.0, 5.0, 5.0, 5.0]
        wide = [0.0, 2.5, 5.0, 7.5, 10.0]
        _, lo_n, hi_n = bootstrap_ci(narrow)
        _, lo_w, hi_w = bootstrap_ci(wide)
        assert (hi_w - lo_w) >= (hi_n - lo_n)

    def test_higher_confidence_wider(self):
        data = [float(x) for x in range(50)]
        _, lo90, hi90 = bootstrap_ci(data, confidence=0.90)
        _, lo99, hi99 = bootstrap_ci(data, confidence=0.99)
        assert (hi99 - lo99) >= (hi90 - lo90)


# ---------------------------------------------------------------------------
# Cohen's h
# ---------------------------------------------------------------------------


class TestCohensH:
    def test_equal_proportions(self):
        assert cohens_h(0.5, 0.5) == 0.0

    def test_symmetry(self):
        h1 = cohens_h(0.3, 0.7)
        h2 = cohens_h(0.7, 0.3)
        assert abs(h1 + h2) < 1e-9

    def test_small_effect(self):
        h = abs(cohens_h(0.5, 0.55))
        assert h < 0.2  # small effect

    def test_medium_effect(self):
        h = abs(cohens_h(0.3, 0.5))
        assert 0.2 < h < 0.8

    def test_large_effect(self):
        h = abs(cohens_h(0.1, 0.9))
        assert h > 0.8

    def test_boundary_zero(self):
        h = cohens_h(0.0, 0.0)
        assert h == 0.0

    def test_boundary_one(self):
        h = cohens_h(1.0, 1.0)
        assert h == 0.0

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            cohens_h(-0.1, 0.5)
        with pytest.raises(ValueError):
            cohens_h(0.5, 1.1)

    def test_known_value(self):
        # h(0.5, 0.0) = 2*arcsin(sqrt(0.5)) - 0 = 2*arcsin(0.7071) ≈ 1.5708
        h = cohens_h(0.5, 0.0)
        assert abs(h - math.pi / 2) < 0.01
