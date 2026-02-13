"""Re-export Thompson Sampling bandit from core.

Provides clean access to the bandit without reaching into core internals.

Usage:
    from buildlog.engine.bandit import ThompsonSamplingBandit, BetaParams
"""

from buildlog.core.bandit import (
    DEFAULT_CONTEXT,
    DEFAULT_SEED_BOOST,
    BanditPersistence,
    BanditState,
    BetaParams,
    JsonlPersistence,
    SqlitePersistence,
    ThompsonSamplingBandit,
    resolve_bandit_persistence,
)

__all__ = [
    "BanditPersistence",
    "BanditState",
    "BetaParams",
    "JsonlPersistence",
    "SqlitePersistence",
    "ThompsonSamplingBandit",
    "resolve_bandit_persistence",
    "DEFAULT_SEED_BOOST",
    "DEFAULT_CONTEXT",
]
