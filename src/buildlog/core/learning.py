"""Pluggable learning backend for buildlog.

Defines the ``LearningBackend`` protocol and two adapters:

- ``QortexLearner``: wraps ``qortex.learning.Learner`` (default)
- ``BuiltinBandit``: wraps the existing ``ThompsonSamplingBandit`` (fallback)

The ``get_learning_backend()`` factory reads ``BUILDLOG_LEARNING_BACKEND``
env var to pick the backend.  Default is ``"qortex"``, falling back to
``"builtin"`` if qortex-learning is not installed.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
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
# Sync-to-async bridge
# ---------------------------------------------------------------------------

# Persistent event loop for the qortex adapter. aiosqlite holds a thread
# that references the event loop, so we can't create/destroy loops per call.
_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_BRIDGE_THREAD: "threading.Thread | None" = None


def _get_bridge_loop() -> asyncio.AbstractEventLoop:
    """Get or create a persistent event loop running in a background thread.

    The loop stays alive for the process lifetime so aiosqlite connections
    don't lose their event loop reference between calls.
    """
    global _BRIDGE_LOOP, _BRIDGE_THREAD
    import threading

    if _BRIDGE_LOOP is not None and _BRIDGE_LOOP.is_running():
        return _BRIDGE_LOOP

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    _BRIDGE_LOOP = loop
    _BRIDGE_THREAD = thread
    return loop


def _run_async(coro):
    """Run an async coroutine from sync code.

    Uses a persistent background event loop so aiosqlite connections
    survive across multiple calls.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is not None and running.is_running():
        # Already in an async context (e.g. MCP server).
        # Submit to the bridge loop in its background thread.
        loop = _get_bridge_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    else:
        # No loop running — still use the persistent bridge loop
        # to keep aiosqlite happy across calls.
        loop = _get_bridge_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)


# ---------------------------------------------------------------------------
# Adapter: builtin ThompsonSamplingBandit
# ---------------------------------------------------------------------------


class BuiltinBandit:
    """Zero-cost adapter over the existing ``ThompsonSamplingBandit``."""

    def __init__(self, bandit: ThompsonSamplingBandit) -> None:
        self._bandit = bandit

    @property
    def backend_name(self) -> str:
        return self._bandit.persistence_name

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
# Adapter: qortex Learner (async → sync bridge)
# ---------------------------------------------------------------------------


class QortexLearner:
    """Adapter translating ``qortex.learning.Learner`` to buildlog's sync interface.

    qortex's Learner is fully async (since the REST/Starlette extraction).
    This adapter bridges via ``_run_async()`` which handles both sync CLI
    contexts and async MCP server contexts.

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
        result = _run_async(
            self._learner.select(arms, context=self._ctx(context), k=k)  # type: ignore[attr-defined]
        )
        return [a.id for a in result.selected]

    def update(
        self,
        rule_id: str,
        reward: float,
        context: str | None = None,
    ) -> None:
        from qortex.learning import ArmOutcome

        _run_async(
            self._learner.observe(  # type: ignore[attr-defined]
                ArmOutcome(arm_id=rule_id, reward=reward, outcome=""),
                context=self._ctx(context),
            )
        )

    def batch_update(
        self,
        rule_ids: list[str],
        reward: float,
        context: str | None = None,
    ) -> None:
        from qortex.learning import ArmOutcome

        outcomes = [
            ArmOutcome(arm_id=rid, reward=reward, outcome="") for rid in rule_ids
        ]
        _run_async(
            self._learner.batch_observe(outcomes, context=self._ctx(context))  # type: ignore[attr-defined]
        )

    def get_stats(self, context: str | None = None) -> dict[str, dict]:
        ctx = self._ctx(context)
        posts = _run_async(self._learner.posteriors(ctx))  # type: ignore[attr-defined]

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
        top = _run_async(self._learner.top_arms(ctx, k=k))  # type: ignore[attr-defined]
        return [(arm_id, state.mean) for arm_id, state in top]

    def decay_arm(
        self,
        rule_id: str,
        decay_factor: float = 0.5,
        context: str | None = None,
    ) -> bool:
        ctx = self._ctx(context)
        state = _run_async(self._learner.store.get(rule_id, ctx))  # type: ignore[attr-defined]
        if state.pulls == 0 and state.alpha == 1.0 and state.beta == 1.0:
            return False  # pristine prior — nothing to decay

        _run_async(
            self._learner.decay_arm(rule_id, decay_factor, ctx)  # type: ignore[attr-defined]
        )
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

    - ``"qortex"`` (default): wraps ``qortex.learning.Learner``
    - ``"builtin"``: wraps ``ThompsonSamplingBandit`` (fallback)

    If qortex-learning is not installed and backend is ``"qortex"``,
    falls back to ``"builtin"`` with a warning.
    """
    _valid_backends = {"builtin", "qortex"}
    backend_name = os.environ.get("BUILDLOG_LEARNING_BACKEND", "qortex")

    if backend_name not in _valid_backends:
        _log.warning(
            "Unknown BUILDLOG_LEARNING_BACKEND=%r, falling back to 'qortex'",
            backend_name,
        )
        backend_name = "qortex"

    if backend_name == "qortex":
        try:
            from qortex.learning import Learner, LearnerConfig

            config = LearnerConfig(
                name=f"buildlog-{buildlog_dir.parent.name}",
                seed_boost=seed_boost,
                baseline_rate=0.1,
            )
            learner = Learner(config)
            return QortexLearner(learner)  # type: ignore[return-value]
        except ImportError:
            _log.warning(
                "qortex-learning not installed, falling back to builtin bandit. "
                "Install with: pip install qortex-learning",
            )
            backend_name = "builtin"

    # Fallback: builtin — use SQLite if available, else JSONL
    from buildlog.core.bandit import ThompsonSamplingBandit, resolve_bandit_persistence

    persistence = resolve_bandit_persistence(buildlog_dir)
    bandit = ThompsonSamplingBandit(persistence, seed_boost, default_context)
    return BuiltinBandit(bandit)  # type: ignore[return-value]
