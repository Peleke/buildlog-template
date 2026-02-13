"""Pluggable learning backend for buildlog.

Defines the ``LearningBackend`` protocol and two adapters:

- ``BuiltinBandit``: wraps the existing ``ThompsonSamplingBandit`` (zero deps)
- ``QortexLearner``: wraps ``qortex.learning.Learner`` (optional dep)

The ``get_learning_backend()`` factory reads ``BUILDLOG_LEARNING_BACKEND``
env var to pick the backend.  Default is ``"builtin"``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from buildlog.core.bandit import ThompsonSamplingBandit  # noqa: F811

__all__ = [
    "LearningBackend",
    "BuiltinBandit",
    "QortexLearner",
    "get_learning_backend",
]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LearningBackend(Protocol):
    """Contract for any learning backend used by buildlog.

    Matches the public API of ``ThompsonSamplingBandit`` so existing
    call sites require zero changes beyond swapping the factory call.
    """

    @property
    def backend_name(self) -> str: ...

    def select(
        self,
        candidates: list[str],
        context: str | None = None,
        k: int = 3,
        seed_rule_ids: set[str] | None = None,
        seed_confidence_map: dict[str, float] | None = None,
    ) -> list[str]: ...

    def update(
        self,
        rule_id: str,
        reward: float,
        context: str | None = None,
    ) -> None: ...

    def batch_update(
        self,
        rule_ids: list[str],
        reward: float,
        context: str | None = None,
    ) -> None: ...

    def get_stats(self, context: str | None = None) -> dict[str, dict]: ...

    def get_top_rules(
        self,
        context: str,
        k: int = 10,
    ) -> list[tuple[str, float]]: ...

    def decay_arm(
        self,
        rule_id: str,
        decay_factor: float = 0.5,
        context: str | None = None,
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Adapter: builtin ThompsonSamplingBandit
# ---------------------------------------------------------------------------


class BuiltinBandit:
    """Zero-cost adapter over the existing ``ThompsonSamplingBandit``."""

    def __init__(self, bandit: ThompsonSamplingBandit) -> None:
        self._bandit = bandit

    @property
    def backend_name(self) -> str:
        return "jsonl"

    def select(
        self,
        candidates: list[str],
        context: str | None = None,
        k: int = 3,
        seed_rule_ids: set[str] | None = None,
        seed_confidence_map: dict[str, float] | None = None,
    ) -> list[str]:
        return self._bandit.select(
            candidates=candidates,
            context=context,
            k=k,
            seed_rule_ids=seed_rule_ids,
            seed_confidence_map=seed_confidence_map,
        )

    def update(
        self,
        rule_id: str,
        reward: float,
        context: str | None = None,
    ) -> None:
        self._bandit.update(rule_id, reward, context)

    def batch_update(
        self,
        rule_ids: list[str],
        reward: float,
        context: str | None = None,
    ) -> None:
        self._bandit.batch_update(rule_ids, reward, context)

    def get_stats(self, context: str | None = None) -> dict[str, dict]:
        return self._bandit.get_stats(context)

    def get_top_rules(
        self,
        context: str,
        k: int = 10,
    ) -> list[tuple[str, float]]:
        return self._bandit.get_top_rules(context, k)

    def decay_arm(
        self,
        rule_id: str,
        decay_factor: float = 0.5,
        context: str | None = None,
    ) -> bool:
        return self._bandit.decay_arm(rule_id, decay_factor, context)


# ---------------------------------------------------------------------------
# Adapter: qortex Learner
# ---------------------------------------------------------------------------


class QortexLearner:
    """Adapter translating ``qortex.learning.Learner`` to buildlog's interface.

    All qortex imports are lazy — this class can be *defined* without
    qortex installed; it only fails when actually instantiated.

    Context translation: buildlog uses ``str`` (error class name),
    qortex uses ``dict``.  We wrap strings as ``{"error_class": value}``.
    """

    def __init__(self, learner: object) -> None:
        self._learner = learner  # qortex.learning.Learner

    @property
    def backend_name(self) -> str:
        return "qortex"

    # -- helpers --

    @staticmethod
    def _ctx(context: str | None) -> dict | None:
        """Translate buildlog's string context to qortex's dict context."""
        if context:
            return {"error_class": context}
        return None

    # -- protocol methods --

    def select(
        self,
        candidates: list[str],
        context: str | None = None,
        k: int = 3,
        seed_rule_ids: set[str] | None = None,
        seed_confidence_map: dict[str, float] | None = None,
    ) -> list[str]:
        from qortex.learning import Arm

        arms = [Arm(id=c) for c in candidates]
        result = self._learner.select(arms, context=self._ctx(context), k=k)  # type: ignore[attr-defined]
        return [a.id for a in result.selected]

    def update(
        self,
        rule_id: str,
        reward: float,
        context: str | None = None,
    ) -> None:
        from qortex.learning import ArmOutcome

        # Pass outcome="" so Learner.observe() uses reward directly
        # (avoids the ``if outcome.outcome and not outcome.reward`` branch).
        self._learner.observe(  # type: ignore[attr-defined]
            ArmOutcome(arm_id=rule_id, reward=reward, outcome=""),
            context=self._ctx(context),
        )

    def batch_update(
        self,
        rule_ids: list[str],
        reward: float,
        context: str | None = None,
    ) -> None:
        # Use observe() loop — works with any qortex version.
        for rule_id in rule_ids:
            self.update(rule_id, reward, context)

    def get_stats(self, context: str | None = None) -> dict[str, dict]:
        ctx = self._ctx(context)
        posts = self._learner.posteriors(ctx)  # type: ignore[attr-defined]

        stats: dict[str, dict] = {}
        for arm_id, info in posts.items():
            a = info["alpha"]
            b = info["beta"]
            total = a + b
            stats[arm_id] = {
                "context": context or "general",
                "mean": round(a / total, 4),
                "alpha": a,
                "beta": b,
                "variance": round((a * b) / (total * total * (total + 1)), 6),
                "is_seed": False,
                "confidence_interval": (
                    round(
                        max(
                            0.0,
                            a / total
                            - 1.96 * (a * b / (total**2 * (total + 1))) ** 0.5,
                        ),
                        4,
                    ),
                    round(
                        min(
                            1.0,
                            a / total
                            + 1.96 * (a * b / (total**2 * (total + 1))) ** 0.5,
                        ),
                        4,
                    ),
                ),
                "total_observations": info.get("pulls", 0),
            }
        return stats

    def get_top_rules(
        self,
        context: str,
        k: int = 10,
    ) -> list[tuple[str, float]]:
        ctx = self._ctx(context)
        posts = self._learner.posteriors(ctx)  # type: ignore[attr-defined]
        ranked = sorted(
            posts.items(),
            key=lambda x: x[1].get("mean", 0),
            reverse=True,
        )
        return [(arm_id, info["mean"]) for arm_id, info in ranked[:k]]

    def decay_arm(
        self,
        rule_id: str,
        decay_factor: float = 0.5,
        context: str | None = None,
    ) -> bool:
        ctx = self._ctx(context)
        state = self._learner.store.get(rule_id, ctx)  # type: ignore[attr-defined]
        if state.pulls == 0 and state.alpha == 1.0 and state.beta == 1.0:
            return False  # pristine prior — nothing to decay

        excess_alpha = state.alpha - 1.0
        excess_beta = state.beta - 1.0
        from qortex.learning import ArmState

        new_state = ArmState(
            alpha=1.0 + excess_alpha * decay_factor,
            beta=1.0 + excess_beta * decay_factor,
            pulls=state.pulls,
            total_reward=state.total_reward,
            last_updated=state.last_updated,
        )
        self._learner.store.put(rule_id, new_state, ctx)  # type: ignore[attr-defined]
        self._learner.store.save()  # type: ignore[attr-defined]
        return True


_log = logging.getLogger("buildlog.learning")

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_learning_backend(
    buildlog_dir: Path,
    seed_boost: float = 2.0,
    default_context: str = "general",
) -> LearningBackend:
    """Return the configured learning backend.

    Reads ``BUILDLOG_LEARNING_BACKEND`` env var:

    - ``"builtin"`` (default): wraps ``ThompsonSamplingBandit``
    - ``"qortex"``: wraps ``qortex.learning.Learner``
    """
    _valid_backends = {"builtin", "qortex"}
    backend_name = os.environ.get("BUILDLOG_LEARNING_BACKEND", "builtin")

    if backend_name not in _valid_backends:
        _log.warning(
            "Unknown BUILDLOG_LEARNING_BACKEND=%r, falling back to 'builtin'",
            backend_name,
        )
        backend_name = "builtin"

    if backend_name == "qortex":
        try:
            from qortex.learning import Learner, LearnerConfig
        except ImportError:
            raise ImportError(
                "qortex is required for the 'qortex' learning backend. "
                "Install it with: pip install buildlog[qortex]"
            ) from None

        config = LearnerConfig(
            name=f"buildlog-{buildlog_dir.parent.name}",
            seed_boost=seed_boost,
            baseline_rate=0.1,
        )
        learner = Learner(config)
        return QortexLearner(learner)  # type: ignore[return-value]

    # Default: builtin
    from buildlog.core.bandit import ThompsonSamplingBandit

    state_path = buildlog_dir / "bandit_state.jsonl"
    bandit = ThompsonSamplingBandit(state_path, seed_boost, default_context)
    return BuiltinBandit(bandit)  # type: ignore[return-value]
