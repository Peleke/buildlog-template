"""Edge mapper registry for mistake → manifest emission.

Each mapper is a standalone callable that produces edges and/or rules
from a ``Mistake`` and its surrounding context. All mappers are registered
in ``DEFAULT_REGISTRY`` and enabled by default.

Configuration: mappers can be disabled via ``~/.buildlog/emissions.yaml``::

    disabled_mappers:
      - resolution_edges
"""

from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from buildlog.core.operations import Mistake

__all__ = [
    "EdgeMapperContext",
    "MapperOutput",
    "EdgeMapper",
    "EdgeMapperRegistry",
    "DEFAULT_REGISTRY",
    "_mistake_to_manifest",
]

logger = logging.getLogger(__name__)

# Mapping from relation_to_prior.type → edge relation_type
_CHAIN_TYPE_MAP: dict[str, str] = {
    "escalation": "refines",
    "same_pattern": "similar_to",
    "regression": "contradicts",
    "caused_by": "requires",
    "part_of": "part_of",
}


@dataclass
class EdgeMapperContext:
    """All data available to edge mappers at emission time."""

    mistake: Mistake
    mistake_node_id: str
    domain: str
    source_id: str
    selected_rules: list[str]
    session_data: dict | None


@dataclass
class MapperOutput:
    """Output from an edge mapper."""

    edges: list[dict] = field(default_factory=list)
    rules: list[dict] = field(default_factory=list)

    def merge(self, other: "MapperOutput") -> "MapperOutput":
        """Merge another output into this one (mutates self)."""
        self.edges.extend(other.edges)
        self.rules.extend(other.rules)
        return self


EdgeMapper = Callable[[EdgeMapperContext], MapperOutput]


class EdgeMapperRegistry:
    """Registry of edge mappers. All registered by default. Individually toggleable."""

    def __init__(self) -> None:
        self._mappers: dict[str, EdgeMapper] = {}
        self._enabled: set[str] = set()

    def register(self, name: str, mapper: EdgeMapper) -> None:
        """Register a mapper and enable it by default."""
        self._mappers[name] = mapper
        self._enabled.add(name)

    def enable(self, name: str) -> None:
        """Enable a registered mapper."""
        if name in self._mappers:
            self._enabled.add(name)

    def disable(self, name: str) -> None:
        """Disable a mapper without removing it."""
        self._enabled.discard(name)

    def enable_all(self) -> None:
        """Enable all registered mappers."""
        self._enabled = set(self._mappers.keys())

    def enabled_names(self) -> list[str]:
        """Return sorted list of enabled mapper names."""
        return sorted(self._enabled)

    def run_all(self, ctx: EdgeMapperContext) -> MapperOutput:
        """Run all enabled mappers and merge outputs."""
        merged = MapperOutput()
        for name in sorted(self._enabled):
            mapper = self._mappers.get(name)
            if mapper is None:
                continue
            try:
                result = mapper(ctx)
                merged.merge(result)
            except Exception:
                logger.debug("Mapper %s failed", name, exc_info=True)
        return merged


# ---------------------------------------------------------------------------
# The 6 mappers
# ---------------------------------------------------------------------------


def concept_involvement(ctx: EdgeMapperContext) -> MapperOutput:
    """USES edges from mistake to each related concept."""
    edges = []
    for concept_name in ctx.mistake.related_concepts or []:
        edges.append(
            {
                "source_id": ctx.mistake_node_id,
                "target_id": concept_name,
                "relation_type": "uses",
                "properties": {
                    "source_text": f"Mistake involved concept: {concept_name}"
                },
                "confidence": 0.8,
            }
        )
    return MapperOutput(edges=edges)


def rule_challenge(ctx: EdgeMapperContext) -> MapperOutput:
    """CHALLENGES edges from mistake to each selected rule that failed to prevent it."""
    edges = []
    for rule_id in ctx.selected_rules:
        edges.append(
            {
                "source_id": ctx.mistake_node_id,
                "target_id": rule_id,
                "relation_type": "challenges",
                "properties": {
                    "source_text": "Rule was active but failed to prevent mistake"
                },
                "confidence": 0.7,
            }
        )
    return MapperOutput(edges=edges)


def rule_support(ctx: EdgeMapperContext) -> MapperOutput:
    """SUPPORTS edge from mistake to the rule that corrected it."""
    if not ctx.mistake.corrected_by_rule:
        return MapperOutput()
    return MapperOutput(
        edges=[
            {
                "source_id": ctx.mistake_node_id,
                "target_id": ctx.mistake.corrected_by_rule,
                "relation_type": "supports",
                "properties": {
                    "source_text": (
                        "Mistake proves rule matters "
                        "(happened because rule wasn't followed)"
                    )
                },
                "confidence": 0.9,
            }
        ]
    )


def mistake_chain(ctx: EdgeMapperContext) -> MapperOutput:
    """Edge from mistake to a prior mistake based on relation_to_prior."""
    rel = ctx.mistake.relation_to_prior
    if not rel or "id" not in rel:
        return MapperOutput()

    chain_type = rel.get("type", "same_pattern")
    relation_type = _CHAIN_TYPE_MAP.get(chain_type, "similar_to")

    return MapperOutput(
        edges=[
            {
                "source_id": ctx.mistake_node_id,
                "target_id": rel["id"],
                "relation_type": relation_type,
                "properties": {
                    "chain_type": chain_type,
                    "source_text": f"Mistake chain: {chain_type}",
                },
                "confidence": 0.75,
            }
        ]
    )


def resolution_rule(ctx: EdgeMapperContext) -> MapperOutput:
    """Emit an ExplicitRule from the resolution action."""
    if not ctx.mistake.resolution_action:
        return MapperOutput()

    return MapperOutput(
        rules=[
            {
                "rule": ctx.mistake.resolution_action,
                "category": ctx.mistake.error_class,
                "provenance": {
                    "id": f"bl:{ctx.mistake.id}",
                    "domain": "experiential",
                    "derivation": "explicit",
                    "confidence": 0.6,
                },
            }
        ]
    )


def resolution_edges(ctx: EdgeMapperContext) -> MapperOutput:
    """IMPLEMENTS + SUPPORTS edges for resolution actions."""
    if not ctx.mistake.resolution_action:
        return MapperOutput()

    resolution_id = f"resolution:{ctx.mistake.id}"
    edges = [
        {
            "source_id": resolution_id,
            "target_id": ctx.mistake_node_id,
            "relation_type": "implements",
            "properties": {"source_text": "Resolution implements fix for mistake"},
            "confidence": 0.8,
        }
    ]

    if ctx.mistake.corrected_by_rule:
        edges.append(
            {
                "source_id": resolution_id,
                "target_id": ctx.mistake.corrected_by_rule,
                "relation_type": "supports",
                "properties": {
                    "source_text": "Resolution reinforces the correcting rule"
                },
                "confidence": 0.7,
            }
        )

    return MapperOutput(edges=edges)


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

# NOTE (issue #121): DEFAULT_REGISTRY is intentionally created at module level
# rather than lazily. The overhead is negligible — each register() call just
# stores a function reference in a dict and adds a name to a set. There are
# only 6 mappers and no heavy initialization (no I/O, no network, no large
# allocations). Lazy initialization would add complexity (thread-safety,
# first-call latency surprises) for no measurable benefit. Evaluated and
# accepted on 2026-02-06.
DEFAULT_REGISTRY = EdgeMapperRegistry()
DEFAULT_REGISTRY.register("concept_involvement", concept_involvement)
DEFAULT_REGISTRY.register("rule_challenge", rule_challenge)
DEFAULT_REGISTRY.register("rule_support", rule_support)
DEFAULT_REGISTRY.register("mistake_chain", mistake_chain)
DEFAULT_REGISTRY.register("resolution_rule", resolution_rule)
DEFAULT_REGISTRY.register("resolution_edges", resolution_edges)

# Apply YAML config if present
_CONFIG_PATH = Path.home() / ".buildlog" / "emissions.yaml"
if _CONFIG_PATH.exists():
    try:
        import yaml

        _yaml_cfg = yaml.safe_load(_CONFIG_PATH.read_text()) or {}
        for mapper_name in _yaml_cfg.get("disabled_mappers", []):
            DEFAULT_REGISTRY.disable(mapper_name)
            logger.debug("Disabled mapper %s via emissions.yaml", mapper_name)
    except Exception:
        logger.debug("Failed to load emissions.yaml", exc_info=True)


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def _get_version() -> str:
    """Get the buildlog package version."""
    try:
        return importlib.metadata.version("buildlog")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


def _mistake_to_manifest(
    mistake: Mistake,
    session_data: dict | None,
    selected_rules: list[str],
    project_id: str,
    registry: EdgeMapperRegistry | None = None,
) -> dict:
    """Build a manifest dict from a mistake using the mapper registry."""
    reg = registry or DEFAULT_REGISTRY
    domain = "experiential"
    source_id = f"buildlog:{project_id}"
    mistake_node_id = f"mistake:{mistake.id}"

    ctx = EdgeMapperContext(
        mistake=mistake,
        mistake_node_id=mistake_node_id,
        domain=domain,
        source_id=source_id,
        selected_rules=selected_rules,
        session_data=session_data,
    )

    output = reg.run_all(ctx)

    # Build the concept node for the mistake itself
    props: dict = {
        "error_class": mistake.error_class,
        "description": mistake.description,
        "timestamp": mistake.timestamp.isoformat(),
        "was_repeat": mistake.was_repeat,
        "session_id": mistake.session_id,
    }
    if mistake.severity:
        props["severity"] = mistake.severity
    if mistake.context:
        props["context"] = mistake.context

    mistake_node = {
        "name": mistake_node_id,
        "domain": domain,
        "properties": props,
        "source_id": source_id,
    }

    return {
        "source_id": source_id,
        "domain": domain,
        "concepts": [mistake_node],
        "edges": output.edges,
        "rules": output.rules,
        "metadata": {
            "source": "buildlog",
            "source_version": _get_version(),
            "emitted_at": datetime.now(timezone.utc).isoformat(),
            "project_id": project_id,
            "mistake_id": mistake.id,
        },
    }
