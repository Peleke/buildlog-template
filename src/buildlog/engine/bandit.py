"""Re-export Thompson Sampling bandit from core.

Provides clean access to the bandit without reaching into core internals.

Usage:
    from buildlog.engine.bandit import ThompsonSamplingBandit, BetaParams
"""

from buildlog.core.bandit import (
    DEFAULT_CONTEXT,
    DEFAULT_SEED_BOOST,
    BanditState,
    BetaParams,
    ThompsonSamplingBandit,
)

__all__ = [
    "ThompsonSamplingBandit",
    "BetaParams",
    "BanditState",
    "DEFAULT_SEED_BOOST",
    "DEFAULT_CONTEXT",
]
