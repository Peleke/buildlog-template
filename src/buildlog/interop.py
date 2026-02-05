"""Shared directory protocol for ingesting seed files from external producers.

Implements the consumer side of a producer/consumer directory protocol:

    ~/.qortex/seeds/pending/    <- producer drops files here
    ~/.qortex/seeds/processed/  <- consumer moves here on success
    ~/.qortex/seeds/failed/     <- consumer moves here on failure (+ .error sidecar)
    ~/.qortex/signals/projections.jsonl  <- optional append-only signal log

Any producer following this layout works — not just qortex.
"""

from __future__ import annotations

__all__ = [
    "SeedSource",
    "InteropConfig",
    "IngestFileResult",
    "IngestResult",
    "load_interop_config",
    "ingest_pending",
]

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# B7a: Configuration
# ---------------------------------------------------------------------------

_SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+\.ya?ml$")


@dataclass
class SeedSource:
    """A single seed producer's directory layout."""

    name: str
    pending_dir: Path
    processed_dir: Path
    failed_dir: Path
    signal_log: Path | None = None


@dataclass
class InteropConfig:
    """Configuration for the interop consumer."""

    sources: list[SeedSource] = field(default_factory=list)
    max_file_size: int = 1_048_576  # 1 MB
    max_rules_per_file: int = 500
    max_rule_text_length: int = 10_000  # chars per rule


DEFAULT_SOURCE = SeedSource(
    name="qortex",
    pending_dir=Path.home() / ".qortex" / "seeds" / "pending",
    processed_dir=Path.home() / ".qortex" / "seeds" / "processed",
    failed_dir=Path.home() / ".qortex" / "seeds" / "failed",
    signal_log=Path.home() / ".qortex" / "signals" / "projections.jsonl",
)


def _expand_path(p: str) -> Path:
    """Expand ~ and resolve a path string."""
    return Path(p).expanduser().resolve()


def load_interop_config() -> InteropConfig:
    """Load interop config from ~/.buildlog/interop.yaml, or return defaults."""
    config_path = Path.home() / ".buildlog" / "interop.yaml"
    if not config_path.exists():
        return InteropConfig(sources=[DEFAULT_SOURCE])

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to load interop config %s: %s", config_path, e)
        return InteropConfig(sources=[DEFAULT_SOURCE])

    if not isinstance(data, dict):
        logger.warning("Invalid interop config (expected dict): %s", config_path)
        return InteropConfig(sources=[DEFAULT_SOURCE])

    sources: list[SeedSource] = []
    for src in data.get("sources", []):
        if not isinstance(src, dict) or "name" not in src:
            continue
        signal_log_raw = src.get("signal_log")
        sources.append(
            SeedSource(
                name=src["name"],
                pending_dir=_expand_path(src.get("pending_dir", "")),
                processed_dir=_expand_path(src.get("processed_dir", "")),
                failed_dir=_expand_path(src.get("failed_dir", "")),
                signal_log=_expand_path(signal_log_raw) if signal_log_raw else None,
            )
        )

    if not sources:
        sources = [DEFAULT_SOURCE]

    return InteropConfig(
        sources=sources,
        max_file_size=data.get("max_file_size", 1_048_576),
        max_rules_per_file=data.get("max_rules_per_file", 500),
        max_rule_text_length=data.get("max_rule_text_length", 10_000),
    )


# ---------------------------------------------------------------------------
# B7b: Security validation + ingest
# ---------------------------------------------------------------------------


def _validate_pending_file(path: Path, config: InteropConfig) -> str | None:
    """Pre-read security checks. Returns error string or None if OK."""
    # 1. Symlink rejection
    if path.is_symlink():
        return "symlink rejected"

    # 2. Filename sanitization (also covers extension check)
    if not _SAFE_FILENAME_RE.match(path.name):
        return f"unsafe filename: {path.name}"

    # 3. File size limit
    try:
        size = path.stat().st_size
    except OSError as e:
        return f"cannot stat: {e}"
    if size > config.max_file_size:
        return f"file too large: {size} bytes (max {config.max_file_size})"

    return None


@dataclass
class IngestFileResult:
    """Result for a single file ingest attempt."""

    file: str
    status: Literal["ingested", "failed", "skipped"]
    persona: str = ""
    rule_count: int = 0
    error: str | None = None


@dataclass
class IngestResult:
    """Aggregate result for one source's ingest run."""

    source: str
    ingested: int = 0
    failed: int = 0
    skipped: int = 0
    files: list[IngestFileResult] = field(default_factory=list)
    message: str = ""


def _write_error_sidecar(failed_path: Path, error: str) -> None:
    """Write a .error JSON sidecar next to a failed file."""
    sidecar = failed_path.with_suffix(failed_path.suffix + ".error")
    payload = {
        "file": failed_path.name,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    sidecar.write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# B7c: Signal log appender
# ---------------------------------------------------------------------------


def _append_signal(signal_log: Path | None, event: dict) -> None:
    """Append a signal event to the JSONL log. No-op if signal_log is None."""
    if signal_log is None:
        return
    try:
        signal_log.parent.mkdir(parents=True, exist_ok=True)
        with open(signal_log, "a") as f:
            f.write(json.dumps(event) + "\n")
    except OSError as e:
        logger.warning("Failed to append signal to %s: %s", signal_log, e)


# ---------------------------------------------------------------------------
# B7b (continued): ingest_pending
# ---------------------------------------------------------------------------


def ingest_pending(
    config: InteropConfig | None = None,
    source_name: str | None = None,
    target_dir: Path | None = None,
    buildlog_dir: Path | None = None,
) -> list[IngestResult]:
    """Ingest pending seed files from configured sources.

    Args:
        config: InteropConfig to use. Loaded from disk if None.
        source_name: Filter to a single source by name.
        target_dir: Override seed target directory.
        buildlog_dir: Override buildlog directory (for bandit decay).

    Returns:
        List of IngestResult, one per source processed.
    """
    from buildlog.seeds import import_seed_file, load_seed_file

    if config is None:
        config = load_interop_config()

    sources = config.sources
    if source_name is not None:
        sources = [s for s in sources if s.name == source_name]

    results: list[IngestResult] = []

    for source in sources:
        result = IngestResult(source=source.name)

        if not source.pending_dir.exists():
            result.message = f"No pending directory: {source.pending_dir}"
            results.append(result)
            continue

        pending_files = sorted(source.pending_dir.iterdir())
        if not pending_files:
            result.message = "No pending files"
            results.append(result)
            continue

        # Ensure destination dirs exist
        source.processed_dir.mkdir(parents=True, exist_ok=True)
        source.failed_dir.mkdir(parents=True, exist_ok=True)

        for path in pending_files:
            if not path.is_file() and not path.is_symlink():
                continue

            # Security validation (layers 1-3)
            error = _validate_pending_file(path, config)
            if error:
                logger.warning("Skipping %s: %s", path.name, error)
                # Symlinks and bad filenames are skipped (not moved)
                if "symlink" in error or "unsafe filename" in error:
                    result.skipped += 1
                    result.files.append(
                        IngestFileResult(file=path.name, status="skipped", error=error)
                    )
                    _append_signal(
                        source.signal_log,
                        {
                            "type": "seed_skipped",
                            "file": path.name,
                            "error": error,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                else:
                    # Size violations get moved to failed
                    dest = source.failed_dir / path.name
                    shutil.move(str(path), str(dest))
                    _write_error_sidecar(dest, error)
                    result.failed += 1
                    result.files.append(
                        IngestFileResult(file=path.name, status="failed", error=error)
                    )
                    _append_signal(
                        source.signal_log,
                        {
                            "type": "seed_failed",
                            "file": path.name,
                            "error": error,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                continue

            # Layer 5: YAML parse + Layer 6: schema validation
            seed_file = load_seed_file(path)
            if seed_file is None:
                error_msg = "Invalid YAML or schema"
                dest = source.failed_dir / path.name
                shutil.move(str(path), str(dest))
                _write_error_sidecar(dest, error_msg)
                result.failed += 1
                result.files.append(
                    IngestFileResult(file=path.name, status="failed", error=error_msg)
                )
                _append_signal(
                    source.signal_log,
                    {
                        "type": "seed_failed",
                        "file": path.name,
                        "error": error_msg,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            # Layer 7: Content size limits
            if len(seed_file.rules) > config.max_rules_per_file:
                error_msg = (
                    f"Too many rules: {len(seed_file.rules)} "
                    f"(max {config.max_rules_per_file})"
                )
                dest = source.failed_dir / path.name
                shutil.move(str(path), str(dest))
                _write_error_sidecar(dest, error_msg)
                result.failed += 1
                result.files.append(
                    IngestFileResult(
                        file=path.name,
                        status="failed",
                        persona=seed_file.persona,
                        error=error_msg,
                    )
                )
                _append_signal(
                    source.signal_log,
                    {
                        "type": "seed_failed",
                        "file": path.name,
                        "error": error_msg,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            oversized_rule = next(
                (
                    r
                    for r in seed_file.rules
                    if len(r.rule) > config.max_rule_text_length
                ),
                None,
            )
            if oversized_rule is not None:
                error_msg = (
                    f"Rule text too long: {len(oversized_rule.rule)} chars "
                    f"(max {config.max_rule_text_length})"
                )
                dest = source.failed_dir / path.name
                shutil.move(str(path), str(dest))
                _write_error_sidecar(dest, error_msg)
                result.failed += 1
                result.files.append(
                    IngestFileResult(
                        file=path.name,
                        status="failed",
                        persona=seed_file.persona,
                        error=error_msg,
                    )
                )
                _append_signal(
                    source.signal_log,
                    {
                        "type": "seed_failed",
                        "file": path.name,
                        "error": error_msg,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            # All checks passed — import
            try:
                import_result = import_seed_file(
                    source_path=path,
                    target_dir=target_dir,
                    buildlog_dir=buildlog_dir,
                )
            except (FileNotFoundError, ValueError) as e:
                error_msg = str(e)
                dest = source.failed_dir / path.name
                shutil.move(str(path), str(dest))
                _write_error_sidecar(dest, error_msg)
                result.failed += 1
                result.files.append(
                    IngestFileResult(file=path.name, status="failed", error=error_msg)
                )
                _append_signal(
                    source.signal_log,
                    {
                        "type": "seed_failed",
                        "file": path.name,
                        "error": error_msg,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            # Success — move to processed
            dest = source.processed_dir / path.name
            shutil.move(str(path), str(dest))
            result.ingested += 1
            result.files.append(
                IngestFileResult(
                    file=path.name,
                    status="ingested",
                    persona=import_result.persona,
                    rule_count=import_result.rule_count,
                )
            )
            _append_signal(
                source.signal_log,
                {
                    "type": "seed_ingested",
                    "file": path.name,
                    "persona": import_result.persona,
                    "rule_count": import_result.rule_count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        parts = []
        if result.ingested:
            parts.append(f"{result.ingested} ingested")
        if result.failed:
            parts.append(f"{result.failed} failed")
        if result.skipped:
            parts.append(f"{result.skipped} skipped")
        result.message = f"[{source.name}] " + (", ".join(parts) or "nothing to do")
        results.append(result)

    return results
