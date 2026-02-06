"""Ambient emission protocol for buildlog.

Writes artifacts to ``~/.buildlog/emissions/`` for downstream consumers
(e.g. qortex) to ingest offline. All emission is fire-and-forget: failures
are silently swallowed so they never break primary operations.

Directory convention::

    ~/.buildlog/emissions/
    ├── pending/          # new artifacts
    ├── processed/        # consumer moved here
    ├── failed/           # consumer moved here + .error sidecar
    └── signal.jsonl      # append-only event log
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "EMISSIONS_DIR",
    "EmissionConfig",
    "emit_artifact",
    "get_emission_config",
    "list_pending",
    "list_processed",
]

logger = logging.getLogger(__name__)

EMISSIONS_DIR: Path = Path.home() / ".buildlog" / "emissions"


@dataclass
class EmissionConfig:
    """Paths used by the emission protocol."""

    pending: Path
    processed: Path
    failed: Path
    signal_log: Path


def get_emission_config(base: Path | None = None) -> EmissionConfig:
    """Return emission paths, creating directories as needed."""
    root = base or EMISSIONS_DIR
    cfg = EmissionConfig(
        pending=root / "pending",
        processed=root / "processed",
        failed=root / "failed",
        signal_log=root / "signal.jsonl",
    )
    cfg.pending.mkdir(parents=True, exist_ok=True)
    cfg.processed.mkdir(parents=True, exist_ok=True)
    cfg.failed.mkdir(parents=True, exist_ok=True)
    return cfg


def emit_artifact(
    artifact: dict,
    artifact_type: str,
    project_id: str,
    config: EmissionConfig | None = None,
) -> Path | None:
    """Write a JSON artifact to the pending directory.

    Appends a signal log entry on success. Returns the written path,
    or ``None`` if emission failed (fire-and-forget).

    Args:
        artifact: The artifact payload (must be JSON-serializable).
        artifact_type: E.g. ``"mistake_manifest"`` or ``"learned_rules"``.
        project_id: Identifies the source project.
        config: Override default emission paths.

    Returns:
        Path to the written file, or None on failure.
    """
    try:
        cfg = config or get_emission_config()
        ts = datetime.now(timezone.utc)
        ts_str = ts.strftime("%Y%m%dT%H%M%S")
        filename = f"{artifact_type}_{project_id}_{ts_str}.json"
        path = cfg.pending / filename

        path.write_text(json.dumps(artifact, indent=2, default=str))

        # Append to signal log
        signal_entry = {
            "event": "emitted",
            "type": artifact_type,
            "project_id": project_id,
            "path": str(path),
            "ts": ts.isoformat(),
            "source": "buildlog",
        }
        with cfg.signal_log.open("a") as f:
            f.write(json.dumps(signal_entry) + "\n")

        logger.debug("Emitted %s to %s", artifact_type, path)
        return path

    except Exception:
        logger.debug("Emission failed for %s", artifact_type, exc_info=True)
        return None


def list_pending(config: EmissionConfig | None = None) -> list[Path]:
    """List pending artifact files."""
    cfg = config or get_emission_config()
    return sorted(cfg.pending.glob("*.json"))


def list_processed(config: EmissionConfig | None = None) -> list[Path]:
    """List processed artifact files."""
    cfg = config or get_emission_config()
    return sorted(cfg.processed.glob("*.json"))
