"""Tests for the pluggable LearningBackend protocol and adapters.

Tests:
- Protocol compliance for BuiltinBandit and QortexLearner
- BuiltinBandit passthrough behavior
- QortexLearner context translation and delegation
- get_learning_backend() factory logic
"""

from __future__ import annotations

import random
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from buildlog.core.bandit import ThompsonSamplingBandit
from buildlog.core.learning import (
    BuiltinBandit,
    LearningBackend,
    QortexLearner,
    get_learning_backend,
)

# ---------------------------------------------------------------------------
# Mock qortex module for tests (qortex may not be installed)
# ---------------------------------------------------------------------------


def _install_qortex_mock():
    """Install a fake qortex.learning module so adapter lazy imports work."""
    mock_learning = types.ModuleType("qortex.learning")
    mock_learning.Arm = lambda id, **kw: SimpleNamespace(id=id, **kw)  # type: ignore[attr-defined]
    mock_learning.ArmOutcome = lambda **kw: SimpleNamespace(**kw)  # type: ignore[attr-defined]
    mock_learning.ArmState = lambda **kw: SimpleNamespace(**kw)  # type: ignore[attr-defined]

    mock_qortex = types.ModuleType("qortex")
    mock_qortex.learning = mock_learning  # type: ignore[attr-defined]

    sys.modules.setdefault("qortex", mock_qortex)
    sys.modules.setdefault("qortex.learning", mock_learning)
    return mock_learning


_qortex_learning = _install_qortex_mock()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def bandit_path(temp_dir):
    return temp_dir / "bandit_state.jsonl"


@pytest.fixture
def bandit(bandit_path):
    return ThompsonSamplingBandit(bandit_path)


@pytest.fixture
def builtin(bandit):
    return BuiltinBandit(bandit)


@pytest.fixture
def seeded_random():
    random.seed(42)
    yield
    random.seed()


def _make_mock_learner() -> MagicMock:
    """Build a mock that mimics qortex.learning.Learner's public API."""
    learner = MagicMock()

    # select() returns a SelectionResult with .selected list of Arm-like objects
    arm_a = SimpleNamespace(id="rule-a")
    arm_b = SimpleNamespace(id="rule-b")
    learner.select.return_value = SimpleNamespace(selected=[arm_a, arm_b])

    # posteriors() returns dict of arm_id -> {alpha, beta, mean, pulls}
    learner.posteriors.return_value = {
        "rule-a": {"alpha": 3.0, "beta": 1.0, "mean": 0.75, "pulls": 3},
        "rule-b": {"alpha": 1.0, "beta": 3.0, "mean": 0.25, "pulls": 3},
    }

    # store.get() returns an ArmState-like object
    learner.store = MagicMock()
    learner.store.get.return_value = SimpleNamespace(
        alpha=3.0,
        beta=2.0,
        pulls=4,
        total_reward=2.5,
        last_updated="2026-01-01T00:00:00Z",
    )

    return learner


@pytest.fixture
def mock_learner():
    return _make_mock_learner()


@pytest.fixture
def qortex_adapter(mock_learner):
    return QortexLearner(mock_learner)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_builtin_satisfies_protocol(self, builtin):
        assert isinstance(builtin, LearningBackend)

    def test_qortex_satisfies_protocol(self, qortex_adapter):
        assert isinstance(qortex_adapter, LearningBackend)

    def test_protocol_is_runtime_checkable(self):
        assert hasattr(LearningBackend, "__protocol_attrs__") or hasattr(
            LearningBackend, "__abstractmethods__"
        )


# ---------------------------------------------------------------------------
# BuiltinBandit adapter
# ---------------------------------------------------------------------------


class TestBuiltinBandit:
    def test_backend_name_jsonl(self, bandit_path):
        bandit = ThompsonSamplingBandit(bandit_path)
        adapter = BuiltinBandit(bandit)
        assert adapter.backend_name == "jsonl"

    def test_select_returns_list_of_strings(self, builtin, seeded_random):
        candidates = ["r1", "r2", "r3", "r4", "r5"]
        selected = builtin.select(candidates, context="general", k=3)
        assert isinstance(selected, list)
        assert len(selected) == 3
        assert all(isinstance(s, str) for s in selected)
        assert all(s in candidates for s in selected)

    def test_update_changes_stats(self, builtin):
        builtin.update("rule-x", reward=1.0, context="test")
        stats = builtin.get_stats(context="test")
        assert "rule-x" in stats
        assert stats["rule-x"]["alpha"] > 1.0

    def test_batch_update(self, builtin):
        builtin.batch_update(["r1", "r2", "r3"], reward=1.0, context="test")
        stats = builtin.get_stats(context="test")
        assert "r1" in stats
        assert "r2" in stats
        assert "r3" in stats

    def test_get_top_rules_sorted(self, builtin):
        # Give different rewards to create ordering
        for _ in range(5):
            builtin.update("high", reward=1.0, context="ctx")
        for _ in range(5):
            builtin.update("low", reward=0.0, context="ctx")

        top = builtin.get_top_rules("ctx", k=2)
        assert isinstance(top, list)
        assert len(top) == 2
        assert top[0][0] == "high"
        assert top[0][1] > top[1][1]

    def test_decay_arm_shrinks_signal(self, builtin):
        # Build up signal first
        for _ in range(10):
            builtin.update("decay-me", reward=1.0, context="ctx")

        stats_before = builtin.get_stats(context="ctx")
        alpha_before = stats_before["decay-me"]["alpha"]

        result = builtin.decay_arm("decay-me", decay_factor=0.5, context="ctx")
        assert result is True

        stats_after = builtin.get_stats(context="ctx")
        alpha_after = stats_after["decay-me"]["alpha"]
        assert alpha_after < alpha_before

    def test_decay_arm_nonexistent_returns_false(self, builtin):
        result = builtin.decay_arm("no-such-arm", context="ctx")
        assert result is False

    def test_select_with_seed_rules(self, builtin, seeded_random):
        candidates = ["seed-1", "learned-1", "learned-2"]
        selected = builtin.select(
            candidates,
            context="general",
            k=2,
            seed_rule_ids={"seed-1"},
            seed_confidence_map={"seed-1": 0.9},
        )
        assert isinstance(selected, list)
        assert len(selected) == 2


# ---------------------------------------------------------------------------
# QortexLearner adapter
# ---------------------------------------------------------------------------


class TestQortexLearner:
    def test_backend_name(self, qortex_adapter):
        assert qortex_adapter.backend_name == "qortex"

    def test_ctx_translation_with_string(self):
        assert QortexLearner._ctx("type-error") == {"error_class": "type-error"}

    def test_ctx_translation_with_none(self):
        assert QortexLearner._ctx(None) is None

    def test_ctx_translation_with_empty_string(self):
        assert QortexLearner._ctx("") is None

    def test_select_translates_candidates(self, qortex_adapter, mock_learner):
        result = qortex_adapter.select(
            candidates=["c1", "c2", "c3"],
            context="type-error",
            k=2,
        )
        assert result == ["rule-a", "rule-b"]

        # Verify Arm objects were created from strings
        call_args = mock_learner.select.call_args
        arms = call_args[0][0]
        assert len(arms) == 3
        assert all(hasattr(a, "id") for a in arms)
        assert call_args[1]["context"] == {"error_class": "type-error"}
        assert call_args[1]["k"] == 2

    def test_update_calls_observe(self, qortex_adapter, mock_learner):
        qortex_adapter.update("rule-x", reward=0.8, context="ctx")

        mock_learner.observe.assert_called_once()
        call_args = mock_learner.observe.call_args
        outcome = call_args[0][0]
        assert outcome.arm_id == "rule-x"
        assert outcome.reward == 0.8
        assert outcome.outcome == ""
        assert call_args[1]["context"] == {"error_class": "ctx"}

    def test_update_with_none_context(self, qortex_adapter, mock_learner):
        qortex_adapter.update("rule-x", reward=1.0, context=None)
        call_args = mock_learner.observe.call_args
        assert call_args[1]["context"] is None

    def test_batch_update_calls_observe_for_each(self, qortex_adapter, mock_learner):
        qortex_adapter.batch_update(["r1", "r2", "r3"], reward=0.5, context="ctx")
        assert mock_learner.observe.call_count == 3

    def test_get_stats_transforms_posteriors(self, qortex_adapter):
        stats = qortex_adapter.get_stats(context="test")

        assert "rule-a" in stats
        assert "rule-b" in stats

        a_stats = stats["rule-a"]
        assert a_stats["context"] == "test"
        assert a_stats["alpha"] == 3.0
        assert a_stats["beta"] == 1.0
        assert a_stats["mean"] == round(3.0 / 4.0, 4)
        assert "variance" in a_stats
        assert "confidence_interval" in a_stats
        assert a_stats["total_observations"] == 3
        assert a_stats["is_seed"] is False

    def test_get_stats_with_none_context(self, qortex_adapter):
        stats = qortex_adapter.get_stats(context=None)
        assert stats["rule-a"]["context"] == "general"

    def test_get_top_rules_sorted_by_mean(self, qortex_adapter):
        top = qortex_adapter.get_top_rules("ctx", k=10)
        assert isinstance(top, list)
        assert len(top) == 2
        # rule-a has mean=0.75, rule-b has mean=0.25
        assert top[0][0] == "rule-a"
        assert top[0][1] > top[1][1]

    def test_get_top_rules_respects_k(self, qortex_adapter):
        top = qortex_adapter.get_top_rules("ctx", k=1)
        assert len(top) == 1

    def test_decay_arm_modifies_state(self, qortex_adapter, mock_learner):
        result = qortex_adapter.decay_arm("rule-x", decay_factor=0.5, context="ctx")
        assert result is True

        # Verify store.put was called with decayed values
        mock_learner.store.put.assert_called_once()
        call_args = mock_learner.store.put.call_args
        new_state = call_args[0][1]
        # Original alpha=3.0, excess=2.0, decayed excess=1.0, new alpha=2.0
        assert new_state.alpha == 2.0
        # Original beta=2.0, excess=1.0, decayed excess=0.5, new beta=1.5
        assert new_state.beta == 1.5
        mock_learner.store.save.assert_called_once()

    def test_decay_arm_pristine_returns_false(self, qortex_adapter, mock_learner):
        mock_learner.store.get.return_value = SimpleNamespace(
            alpha=1.0, beta=1.0, pulls=0, total_reward=0.0, last_updated=""
        )
        result = qortex_adapter.decay_arm("pristine-arm")
        assert result is False
        mock_learner.store.put.assert_not_called()


# ---------------------------------------------------------------------------
# Factory: get_learning_backend()
# ---------------------------------------------------------------------------


class TestGetLearningBackend:
    def test_default_returns_builtin(self, temp_dir):
        backend = get_learning_backend(temp_dir)
        assert isinstance(backend, BuiltinBandit)

    def test_explicit_builtin_returns_builtin(self, temp_dir):
        with patch.dict("os.environ", {"BUILDLOG_LEARNING_BACKEND": "builtin"}):
            backend = get_learning_backend(temp_dir)
            assert isinstance(backend, BuiltinBandit)

    def test_unknown_backend_falls_back_to_builtin(self, temp_dir):
        with patch.dict("os.environ", {"BUILDLOG_LEARNING_BACKEND": "nonsense"}):
            backend = get_learning_backend(temp_dir)
            assert isinstance(backend, BuiltinBandit)

    def test_qortex_backend_raises_without_package(self, temp_dir):
        with patch.dict("os.environ", {"BUILDLOG_LEARNING_BACKEND": "qortex"}):
            with patch.dict("sys.modules", {"qortex": None, "qortex.learning": None}):
                with pytest.raises(ImportError, match="qortex is required"):
                    get_learning_backend(temp_dir)

    def test_backend_name_on_builtin(self, temp_dir):
        backend = get_learning_backend(temp_dir)
        assert backend.backend_name in ("jsonl", "sqlite")


# ---------------------------------------------------------------------------
# E2E: full loop with builtin backend
# ---------------------------------------------------------------------------


class TestE2EBuiltinLoop:
    def test_full_loop(self, temp_dir, seeded_random):
        """select → update → batch_update → stats → top_rules → decay"""
        backend = get_learning_backend(temp_dir)
        candidates = ["rule-1", "rule-2", "rule-3", "rule-4", "rule-5"]

        # Select
        selected = backend.select(candidates, context="e2e", k=3)
        assert len(selected) == 3

        # Positive reward for selected
        for rule_id in selected:
            backend.update(rule_id, reward=1.0, context="e2e")

        # Negative batch update for unselected
        unselected = [c for c in candidates if c not in selected]
        backend.batch_update(unselected, reward=0.0, context="e2e")

        # Verify stats reflect updates
        stats = backend.get_stats(context="e2e")
        assert len(stats) == 5

        # Top rules should rank positively-rewarded rules higher
        top = backend.get_top_rules("e2e", k=3)
        assert len(top) == 3
        top_ids = {t[0] for t in top}
        assert top_ids == set(selected)

        # Decay one arm
        result = backend.decay_arm(selected[0], decay_factor=0.5, context="e2e")
        assert result is True

    def test_multiple_contexts(self, temp_dir):
        """Backend should isolate state per context."""
        backend = get_learning_backend(temp_dir)

        backend.update("shared-rule", reward=1.0, context="ctx-a")
        backend.update("shared-rule", reward=0.0, context="ctx-b")

        stats_a = backend.get_stats(context="ctx-a")
        stats_b = backend.get_stats(context="ctx-b")

        assert stats_a["shared-rule"]["mean"] > stats_b["shared-rule"]["mean"]
