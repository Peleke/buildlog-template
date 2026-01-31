"""Buildlog Engine — agent-agnostic core for rule learning and experiment tracking.

This package provides the pure algorithmic core of buildlog without any
CLI, copier, or agent-specific rendering dependencies. Use it when you
want Thompson Sampling bandits, confidence scoring, embedding similarity,
or experiment tracking in your own tools.

Usage:
    from buildlog.engine import ThompsonSamplingBandit, BetaParams
    from buildlog.engine import calculate_confidence, ConfidenceMetrics
    from buildlog.engine import start_session, end_session, log_mistake
    from buildlog.engine.types import Skill, Session, Mistake, RewardEvent

Install:
    pip install buildlog          # engine is part of the base package
    pip install buildlog[engine]  # same thing — documents the namespace
"""

from buildlog.engine.bandit import BetaParams, ThompsonSamplingBandit
from buildlog.engine.confidence import (
    ConfidenceConfig,
    ConfidenceMetrics,
    calculate_confidence,
    get_confidence_tier,
    merge_confidence_metrics,
)
from buildlog.engine.experiments import (
    end_session,
    experiment_report,
    get_rewards,
    log_mistake,
    log_reward,
    session_metrics,
    start_session,
)
from buildlog.engine.types import Mistake, RewardEvent, Session, Skill

__all__ = [
    # Bandit
    "ThompsonSamplingBandit",
    "BetaParams",
    # Confidence
    "calculate_confidence",
    "get_confidence_tier",
    "merge_confidence_metrics",
    "ConfidenceMetrics",
    "ConfidenceConfig",
    # Experiments
    "start_session",
    "end_session",
    "log_mistake",
    "log_reward",
    "get_rewards",
    "session_metrics",
    "experiment_report",
    # Types
    "Skill",
    "Session",
    "Mistake",
    "RewardEvent",
]
