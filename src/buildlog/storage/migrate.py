"""Migrate legacy per-project JSON/JSONL files into the global SQLite DB.

Usage from the CLI::

    buildlog migrate [--dry-run] [--buildlog-dir buildlog]

The migration is idempotent: ``INSERT OR REPLACE`` handles re-runs, and
files already renamed to ``*.migrated`` are skipped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from buildlog.storage import GLOBAL_DB_PATH, get_project_id
from buildlog.storage.schema import open_db
from buildlog.storage.sqlite import SQLiteBackend

__all__ = ["migrate_project"]

# Mapping from legacy file basenames to the migration handler key.
_LEGACY_FILES: dict[str, str] = {
    "promoted.json": "promoted",
    "rejected.json": "rejected",
    "review_learnings.json": "learnings",
    "reward_events.jsonl": "rewards",
    "sessions.jsonl": "sessions",
    "mistakes.jsonl": "mistakes",
    "active_session.json": "active_session",
}


def migrate_project(
    buildlog_dir: Path,
    *,
    project_root: Path | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Migrate a single project's legacy files into the global SQLite DB.

    Args:
        buildlog_dir: Path to the project's ``buildlog/`` directory.
        project_root: Explicit project root.  Defaults to *cwd*.
        dry_run: If ``True``, report what would happen without writing.

    Returns:
        List of human-readable summary lines.
    """
    if project_root is None:
        project_root = Path.cwd()
    project_root = project_root.resolve()

    dot = buildlog_dir / ".buildlog"
    if not dot.is_dir():
        return ["No .buildlog/ directory found — nothing to migrate."]

    project_id = get_project_id(project_root)
    project_name = project_root.name

    summary: list[str] = []
    summary.append(f"Project: {project_name} ({project_id})")
    summary.append(f"Source:  {dot}")
    summary.append(f"Target:  {GLOBAL_DB_PATH}")
    summary.append("")

    if dry_run:
        summary.append("=== DRY RUN ===")
        for fname in _LEGACY_FILES:
            path = dot / fname
            migrated = dot / f"{fname}.migrated"
            if migrated.exists():
                summary.append(f"  SKIP {fname} (already migrated)")
            elif path.exists():
                summary.append(f"  WILL MIGRATE {fname}")
            else:
                summary.append(f"  SKIP {fname} (not found)")
        # Check bandit_state.jsonl in parent
        bandit_path = buildlog_dir / "bandit_state.jsonl"
        bandit_migrated = buildlog_dir / "bandit_state.jsonl.migrated"
        if bandit_migrated.exists():
            summary.append("  SKIP bandit_state.jsonl (already migrated)")
        elif bandit_path.exists():
            summary.append("  WILL MIGRATE bandit_state.jsonl")
        else:
            summary.append("  SKIP bandit_state.jsonl (not found)")
        return summary

    # ── Open / create global DB ──────────────────────────────────────────
    conn = open_db(GLOBAL_DB_PATH)
    backend = SQLiteBackend(conn)
    backend.ensure_project(project_id, project_name, str(project_root))

    # ── Migrate each file ────────────────────────────────────────────────
    for fname, key in _LEGACY_FILES.items():
        path = dot / fname
        migrated = dot / f"{fname}.migrated"
        if migrated.exists():
            summary.append(f"  SKIP {fname} (already migrated)")
            continue
        if not path.exists():
            continue

        try:
            count = _MIGRATE_HANDLERS[key](backend, project_id, path)
            summary.append(f"  OK   {fname} ({count} records)")
            path.rename(migrated)
        except Exception as exc:
            summary.append(f"  FAIL {fname}: {exc}")

    # ── Bandit state (lives in buildlog_dir, not .buildlog/) ─────────────
    bandit_path = buildlog_dir / "bandit_state.jsonl"
    bandit_migrated = buildlog_dir / "bandit_state.jsonl.migrated"
    if bandit_migrated.exists():
        summary.append("  SKIP bandit_state.jsonl (already migrated)")
    elif bandit_path.exists():
        try:
            count = _migrate_bandit(backend, project_id, bandit_path)
            summary.append(f"  OK   bandit_state.jsonl ({count} arms)")
            bandit_path.rename(bandit_migrated)
        except Exception as exc:
            summary.append(f"  FAIL bandit_state.jsonl: {exc}")

    conn.close()
    summary.append("")
    summary.append("Migration complete.")
    return summary


# ── Per-file handlers ────────────────────────────────────────────────────


def _migrate_id_set(
    backend: SQLiteBackend,
    project_id: str,
    path: Path,
    collection: str,
) -> int:
    """Migrate promoted.json or rejected.json."""
    data = json.loads(path.read_text())
    ids = set(data.get("skill_ids", []))
    meta = data.get(f"{collection}_at", {})
    backend.save_id_set(project_id, collection, ids, meta if meta else None)
    return len(ids)


def _migrate_promoted(backend: SQLiteBackend, project_id: str, path: Path) -> int:
    return _migrate_id_set(backend, project_id, path, "promoted")


def _migrate_rejected(backend: SQLiteBackend, project_id: str, path: Path) -> int:
    return _migrate_id_set(backend, project_id, path, "rejected")


def _migrate_learnings(backend: SQLiteBackend, project_id: str, path: Path) -> int:
    data = json.loads(path.read_text())
    backend.save_learnings(project_id, data)
    return len(data.get("learnings", {}))


def _migrate_jsonl_events(
    backend: SQLiteBackend, project_id: str, path: Path, table: str
) -> int:
    count = 0
    for line in path.read_text().strip().split("\n"):
        if not line:
            continue
        try:
            record = json.loads(line)
            backend.append_event(project_id, table, record)
            count += 1
        except (json.JSONDecodeError, KeyError):
            continue
    return count


def _migrate_rewards(backend: SQLiteBackend, project_id: str, path: Path) -> int:
    return _migrate_jsonl_events(backend, project_id, path, "rewards")


def _migrate_sessions(backend: SQLiteBackend, project_id: str, path: Path) -> int:
    return _migrate_jsonl_events(backend, project_id, path, "sessions")


def _migrate_mistakes(backend: SQLiteBackend, project_id: str, path: Path) -> int:
    return _migrate_jsonl_events(backend, project_id, path, "mistakes")


def _migrate_active_session(backend: SQLiteBackend, project_id: str, path: Path) -> int:
    data = json.loads(path.read_text())
    backend.save_active_session(project_id, data)
    return 1


def _migrate_bandit(backend: SQLiteBackend, project_id: str, path: Path) -> int:
    """Migrate bandit_state.jsonl → bandit_arms table (compacted)."""
    from buildlog.storage.legacy import LegacyBackend

    # Re-use LegacyBackend's compaction logic
    tmp_backend = LegacyBackend(path.parent)
    arms = tmp_backend.load_bandit_state("")
    backend.save_bandit_state(project_id, arms)
    count = sum(len(rules) for rules in arms.values())
    return count


_MigrateFunc = Callable[[SQLiteBackend, str, Path], int]

_MIGRATE_HANDLERS: dict[str, _MigrateFunc] = {
    "promoted": _migrate_promoted,
    "rejected": _migrate_rejected,
    "learnings": _migrate_learnings,
    "rewards": _migrate_rewards,
    "sessions": _migrate_sessions,
    "mistakes": _migrate_mistakes,
    "active_session": _migrate_active_session,
}
