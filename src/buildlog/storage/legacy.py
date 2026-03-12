"""Legacy file-based storage backend.

Wraps the existing JSON / JSONL I/O that lives under ``buildlog_dir/.buildlog/``.
The ``project_id`` parameter is accepted but ignored — data is already scoped
by the ``buildlog_dir`` path passed at construction time.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["LegacyBackend"]

# Mapping from logical table names to file names.
_TABLE_FILES: dict[str, str] = {
    "rewards": "reward_events.jsonl",
    "sessions": "sessions.jsonl",
    "mistakes": "mistakes.jsonl",
}


class LegacyBackend:
    """StorageBackend backed by per-project JSON/JSONL files."""

    def __init__(self, buildlog_dir: Path) -> None:
        self.buildlog_dir = buildlog_dir
        self._dot = buildlog_dir / ".buildlog"

    # -- project listing -----------------------------------------------------

    def list_projects(self) -> list[dict]:
        """Legacy backend has no project registry; return empty list."""
        return []

    # -- helpers -------------------------------------------------------------

    def _ensure_dot(self) -> Path:
        self._dot.mkdir(parents=True, exist_ok=True)
        return self._dot

    def _collection_path(self, collection: str) -> Path:
        return self._dot / f"{collection}.json"

    def _table_path(self, table: str) -> Path:
        fname = _TABLE_FILES.get(table)
        if fname is None:
            raise ValueError(f"Unknown table: {table}")
        return self._dot / fname

    # -- ID set ops (promoted / rejected) -----------------------------------

    def load_id_set(self, project_id: str, collection: str) -> set[str]:
        path = self._collection_path(collection)
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text())
            return set(data.get("skill_ids", []))
        except (json.JSONDecodeError, OSError):
            return set()

    def save_id_set(
        self,
        project_id: str,
        collection: str,
        ids: set[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._ensure_dot()
        path = self._collection_path(collection)

        # Preserve existing metadata structure
        existing: dict[str, Any] = {"skill_ids": [], f"{collection}_at": {}}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        existing["skill_ids"] = sorted(ids)
        if metadata:
            # Merge per-ID metadata (e.g. timestamps)
            meta_key = f"{collection}_at"
            if meta_key not in existing:
                existing[meta_key] = {}
            existing[meta_key].update(metadata)

        path.write_text(json.dumps(existing, indent=2))

    # -- Learnings ----------------------------------------------------------

    def load_learnings(self, project_id: str) -> dict:
        path = self._dot / "review_learnings.json"
        if not path.exists():
            return {"learnings": {}, "review_history": []}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"learnings": {}, "review_history": []}

    def save_learnings(self, project_id: str, data: dict) -> None:
        self._ensure_dot()
        path = self._dot / "review_learnings.json"
        path.write_text(json.dumps(data, indent=2))

    # -- Active session -----------------------------------------------------

    def load_active_session(self, project_id: str) -> dict | None:
        path = self._dot / "active_session.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def save_active_session(self, project_id: str, data: dict) -> None:
        self._ensure_dot()
        path = self._dot / "active_session.json"
        path.write_text(json.dumps(data, indent=2))

    def delete_active_session(self, project_id: str) -> None:
        path = self._dot / "active_session.json"
        if path.exists():
            path.unlink()

    # -- Event streams (JSONL) ----------------------------------------------

    def append_event(self, project_id: str, table: str, record: dict) -> None:
        self._ensure_dot()
        path = self._table_path(table)
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def load_events(self, project_id: str, table: str) -> list[dict]:
        path = self._table_path(table)
        if not path.exists():
            return []
        events: list[dict] = []
        for line in path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def count_events(self, project_id: str, table: str) -> int:
        path = self._table_path(table)
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text().strip().split("\n") if line)

    # -- Bandit state -------------------------------------------------------

    def load_bandit_state(self, project_id: str) -> dict[str, dict[str, dict]]:
        # bandit_state.jsonl lives at buildlog/ level (not .buildlog/) for
        # historical reasons — it predates the .buildlog/ convention.
        path = self._dot.parent / "bandit_state.jsonl"
        if not path.exists():
            return {}

        # Read all records, keep only latest per (context, rule_id)
        records: dict[tuple[str, str], dict] = {}
        for line in path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                key = (data["context"], data["rule_id"])
                if key not in records:
                    records[key] = data
                else:
                    existing_ts = records[key].get("updated_at", "")
                    new_ts = data.get("updated_at", "")
                    if new_ts > existing_ts:
                        records[key] = data
            except (json.JSONDecodeError, KeyError):
                continue

        # Build nested dict
        result: dict[str, dict[str, dict]] = {}
        for (ctx, rule_id), data in records.items():
            if ctx not in result:
                result[ctx] = {}
            result[ctx][rule_id] = {
                "alpha": data.get("alpha", 1.0),
                "beta": data.get("beta", 1.0),
                "is_seed": data.get("is_seed", False),
                "updated_at": data.get(
                    "updated_at", datetime.now(timezone.utc).isoformat()
                ),
            }
        return result

    def save_bandit_state(
        self, project_id: str, arms: dict[str, dict[str, dict]]
    ) -> None:
        path = self._dot.parent / "bandit_state.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        for context, rules in arms.items():
            for rule_id, params in rules.items():
                record = {
                    "context": context,
                    "rule_id": rule_id,
                    "alpha": params["alpha"],
                    "beta": params["beta"],
                    "is_seed": params.get("is_seed", False),
                    "updated_at": params.get(
                        "updated_at", datetime.now(timezone.utc).isoformat()
                    ),
                }
                lines.append(json.dumps(record))
        path.write_text("\n".join(lines) + "\n" if lines else "")

    def append_bandit_update(
        self, project_id: str, context: str, rule_id: str, record: dict
    ) -> None:
        path = self._dot.parent / "bandit_state.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")

    # -- Posterior snapshots (JSONL fallback) --------------------------------

    def append_posterior_snapshots(self, project_id: str, records: list[dict]) -> int:
        self._ensure_dot()
        path = self._dot / "posterior_snapshots.jsonl"
        with open(path, "a") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
        return len(records)

    def load_posterior_history(
        self,
        project_id: str,
        rule_id: str | None = None,
        since: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        path = self._dot / "posterior_snapshots.jsonl"
        if not path.exists():
            return []
        results: list[dict] = []
        for line in path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rule_id and rec.get("rule_id") != rule_id:
                continue
            if since and rec.get("timestamp", "") < since:
                continue
            results.append(rec)
        results.sort(key=lambda r: r.get("timestamp", ""))
        return results[:limit]

    # -- Gauntlet rules (no-op for legacy) ----------------------------------

    def load_gauntlet_rules(
        self,
        persona: str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        logger.debug("LegacyBackend.load_gauntlet_rules: no-op (use YAML)")
        return []

    def save_gauntlet_rules_batch(
        self,
        rules: list[dict],
        seed_file_hash: str | None = None,
        seed_filename: str | None = None,
    ) -> int:
        logger.debug("LegacyBackend.save_gauntlet_rules_batch: no-op")
        return 0

    def get_gauntlet_rule(self, rule_id: str) -> dict | None:
        return None

    def update_gauntlet_rule(self, rule_id: str, **fields: Any) -> bool:
        return False

    def deactivate_gauntlet_rule(self, rule_id: str) -> bool:
        return False

    def count_gauntlet_rules(
        self,
        persona: str | None = None,
        active_only: bool = True,
    ) -> int:
        return 0

    # -- Emission edges (no-op for legacy) ----------------------------------

    def store_emission_edges(self, edges: list[dict]) -> int:
        return 0

    def count_emission_edges(
        self,
        project_id: str | None = None,
        relation_type: str | None = None,
    ) -> int:
        return 0

    def load_emission_edges(
        self,
        project_id: str | None = None,
        relation_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return []
