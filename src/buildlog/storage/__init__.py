"""Storage backend resolution.

Provides :func:`get_backend` to transparently select between
:class:`SQLiteBackend` (global DB) and :class:`LegacyBackend` (per-project
JSON/JSONL files), plus :func:`get_project_id` for deterministic project
identification.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from buildlog.storage.base import Exporter, StorageBackend
from buildlog.storage.legacy import LegacyBackend
from buildlog.storage.schema import open_db
from buildlog.storage.sqlite import SQLiteBackend

__all__ = [
    "GLOBAL_DB_PATH",
    "Exporter",
    "LegacyBackend",
    "SQLiteBackend",
    "StorageBackend",
    "get_backend",
    "get_project_id",
]

GLOBAL_DB_PATH: Path = Path.home() / ".buildlog" / "buildlog.db"


def get_project_id(project_root: Path | None = None) -> str:
    """Derive a deterministic project ID.

    Strategy:
      1. Hash the git remote ``origin`` URL (portable across machines).
      2. Fall back to hashing the absolute path (local-only).

    Returns:
        A 12-character hex string.
    """
    if project_root is None:
        project_root = Path.cwd()
    project_root = project_root.resolve()

    # Try git remote URL first
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            source = result.stdout.strip()
            return hashlib.sha256(source.encode()).hexdigest()[:12]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: hash the absolute path
    return hashlib.sha256(str(project_root).encode()).hexdigest()[:12]


def get_backend(
    buildlog_dir: Path | None = None,
    *,
    project_root: Path | None = None,
) -> tuple[StorageBackend, str]:
    """Resolve the storage backend for a project.

    Resolution order:
      1. Global DB exists **and** project is registered → ``SQLiteBackend``
      2. Global DB exists, project **not** registered → auto-register, ``SQLiteBackend``
      3. No global DB **but** ``buildlog_dir/.buildlog/`` has legacy files → ``LegacyBackend``
      4. Nothing exists → create global DB, register project, ``SQLiteBackend``

    Args:
        buildlog_dir: Path to the project's ``buildlog/`` directory (used for
            legacy detection and as the project name).
        project_root: Explicit project root.  Defaults to *cwd*.

    Returns:
        A ``(backend, project_id)`` tuple.
    """
    if project_root is None:
        project_root = Path.cwd()
    project_root = project_root.resolve()

    project_id = get_project_id(project_root)
    project_name = project_root.name

    # Resolve buildlog_dir
    if buildlog_dir is None:
        buildlog_dir = project_root / "buildlog"

    # ── Case 1 & 2: global DB exists ────────────────────────────────────
    if GLOBAL_DB_PATH.exists():
        conn = open_db(GLOBAL_DB_PATH)
        backend = SQLiteBackend(conn)
        if not backend.project_exists(project_id):
            backend.ensure_project(project_id, project_name, str(project_root))
        return backend, project_id

    # ── Case 3: legacy files present, no global DB ──────────────────────
    legacy_dot = buildlog_dir / ".buildlog"
    if legacy_dot.is_dir() and any(legacy_dot.iterdir()):
        return LegacyBackend(buildlog_dir), project_id

    # ── Case 4: fresh install — create global DB ────────────────────────
    conn = open_db(GLOBAL_DB_PATH)
    backend = SQLiteBackend(conn)
    backend.ensure_project(project_id, project_name, str(project_root))
    return backend, project_id
