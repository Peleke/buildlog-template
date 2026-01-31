"""Re-export confidence scoring from buildlog.confidence.

Provides clean access to confidence calculation without reaching into
top-level module internals.

Usage:
    from buildlog.engine.confidence import calculate_confidence, ConfidenceMetrics
"""

from buildlog.confidence import (
    ConfidenceConfig,
    ConfidenceMetrics,
    ConfidenceTier,
    add_contradiction,
    calculate_confidence,
    get_confidence_tier,
    merge_confidence_metrics,
)

__all__ = [
    "calculate_confidence",
    "get_confidence_tier",
    "merge_confidence_metrics",
    "add_contradiction",
    "ConfidenceMetrics",
    "ConfidenceConfig",
    "ConfidenceTier",
]
