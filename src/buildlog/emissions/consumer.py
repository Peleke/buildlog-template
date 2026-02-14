"""Consume pending emission artifacts into SQLite storage.

Follows the B7 interop pattern: list → parse → classify → store → move.
Edges from ``mistake_manifest`` and ``session_summary`` artifacts are stored
in the ``emission_edges`` table.  ``reward_signal`` and ``learned_rules``
artifacts are moved to processed/ without storage (already in SQLite via
the primary write path).
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone

from buildlog.emissions import EmissionConfig, get_emission_config

__all__ = ["ConsumptionResult", "consume_pending_emissions"]

logger = logging.getLogger(__name__)

# Artifact types whose edges we store in emission_edges.
_EDGE_ARTIFACT_TYPES = frozenset(
    {"mistake_manifest", "session_summary", "reward_signal"}
)


@dataclass
class ConsumptionResult:
    """Result of consuming pending emissions."""

    consumed: int = 0
    failed: int = 0
    skipped: int = 0
    edges_stored: int = 0
    errors: list[str] = field(default_factory=list)


def _classify_artifact_type(filename: str) -> str | None:
    """Extract artifact type from filename pattern ``{type}_{project}_{ts}.json``."""
    for prefix in (
        "mistake_manifest",
        "session_summary",
        "reward_signal",
        "learned_rules",
    ):
        if filename.startswith(prefix + "_"):
            return prefix
    return None


def _extract_edges(artifact: dict, artifact_type: str, consumed_at: str) -> list[dict]:
    """Extract edge dicts ready for ``store_emission_edges()``."""
    edges_raw = artifact.get("edges", [])
    if not edges_raw:
        return []

    project_id = artifact.get("metadata", {}).get("project_id", "unknown")
    emitted_at = artifact.get("metadata", {}).get("emitted_at", consumed_at)

    result = []
    for edge in edges_raw:
        result.append(
            {
                "source_id": edge.get("source_id", ""),
                "target_id": edge.get("target_id", ""),
                "relation_type": edge.get("relation_type", "unknown"),
                "confidence": edge.get("confidence"),
                "artifact_type": artifact_type,
                "project_id": project_id,
                "emitted_at": emitted_at,
                "consumed_at": consumed_at,
                "properties": edge.get("properties"),
            }
        )
    return result


def consume_pending_emissions(
    config: EmissionConfig | None = None,
    backend: "SQLiteBackend | None" = None,  # type: ignore[name-defined]  # noqa: F821
) -> ConsumptionResult:
    """Consume pending emission artifacts.

    - ``mistake_manifest``, ``session_summary``, ``reward_signal``: extract
      edges → ``emission_edges`` table (if edges present).
    - ``learned_rules``: move to processed/ (data already in SQLite via
      primary write path, and has no edges).
    - Bad files → ``failed/`` with ``.error`` sidecar.

    Args:
        config: Override default emission paths.
        backend: SQLite backend for edge storage.  Resolved lazily if None.

    Returns:
        ConsumptionResult with counts and errors.
    """
    cfg = config or get_emission_config()
    result = ConsumptionResult()
    consumed_at = datetime.now(timezone.utc).isoformat()

    pending_files = sorted(cfg.pending.glob("*.json"))
    if not pending_files:
        return result

    # Lazy backend resolution
    if backend is None:
        try:
            from buildlog.storage import get_backend

            backend, _ = get_backend()
        except Exception:
            backend = None

    for path in pending_files:
        try:
            artifact_type = _classify_artifact_type(path.name)
            if artifact_type is None:
                result.skipped += 1
                continue

            text = path.read_text()
            artifact = json.loads(text)

            # Extract and store edges for types that have them
            if artifact_type in _EDGE_ARTIFACT_TYPES and backend is not None:
                edges = _extract_edges(artifact, artifact_type, consumed_at)
                if edges:
                    stored = backend.store_emission_edges(edges)
                    result.edges_stored += stored

            # Move to processed
            dest = cfg.processed / path.name
            shutil.move(str(path), str(dest))
            result.consumed += 1

            # Append signal log entry
            try:
                signal_entry = {
                    "event": "consumed",
                    "type": artifact_type,
                    "path": str(dest),
                    "ts": consumed_at,
                    "edges_extracted": result.edges_stored,
                }
                with cfg.signal_log.open("a") as f:
                    f.write(json.dumps(signal_entry) + "\n")
            except Exception:
                pass  # Signal log is best-effort

        except (json.JSONDecodeError, KeyError, OSError) as exc:
            result.failed += 1
            result.errors.append(f"{path.name}: {exc}")

            # Move to failed with error sidecar
            try:
                failed_dest = cfg.failed / path.name
                shutil.move(str(path), str(failed_dest))
                error_path = cfg.failed / f"{path.name}.error"
                error_path.write_text(str(exc))
            except Exception:
                pass

    return result
