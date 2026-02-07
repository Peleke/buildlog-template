"""SQLite storage backend.

Implements :class:`StorageBackend` against the global ``~/.buildlog/buildlog.db``
database.  A single instance can serve multiple projects because every row is
keyed by ``project_id``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from buildlog.storage.schema import init_schema

__all__ = ["SQLiteBackend"]


class SQLiteBackend:
    """StorageBackend backed by a global SQLite database."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        init_schema(conn)

    # -- project registration -----------------------------------------------

    def ensure_project(self, project_id: str, name: str, path: str) -> None:
        """Register a project if it doesn't exist yet."""
        self.conn.execute(
            """\
            INSERT OR IGNORE INTO projects (id, name, path)
            VALUES (?, ?, ?)
            """,
            (project_id, name, path),
        )
        self.conn.commit()

    def project_exists(self, project_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return row is not None

    # -- ID set ops (skill_decisions) ---------------------------------------

    def load_id_set(self, project_id: str, collection: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT skill_id FROM skill_decisions WHERE project_id = ? AND decision = ?",
            (project_id, collection),
        ).fetchall()
        return {row[0] for row in rows}

    def save_id_set(
        self,
        project_id: str,
        collection: str,
        ids: set[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        # Atomic: DELETE stale + INSERT new in one transaction
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            if ids:
                self.conn.execute(
                    "DELETE FROM skill_decisions WHERE project_id = ? AND decision = ? AND skill_id NOT IN ({})".format(
                        ",".join("?" * len(ids))
                    ),
                    [project_id, collection, *sorted(ids)],
                )
            else:
                # Empty set: remove all for this collection
                self.conn.execute(
                    "DELETE FROM skill_decisions WHERE project_id = ? AND decision = ?",
                    [project_id, collection],
                )
            # Upsert each ID
            for skill_id in ids:
                meta_json = None
                if metadata and skill_id in metadata:
                    meta_json = json.dumps(metadata[skill_id])
                self.conn.execute(
                    """\
                    INSERT INTO skill_decisions (project_id, skill_id, decision, decided_at, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (project_id, skill_id)
                    DO UPDATE SET decision = excluded.decision,
                                  decided_at = excluded.decided_at,
                                  metadata = excluded.metadata
                    """,
                    (project_id, skill_id, collection, now, meta_json),
                )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    # -- Learnings ----------------------------------------------------------

    def load_learnings(self, project_id: str) -> dict:
        # Load learnings
        rows = self.conn.execute(
            "SELECT * FROM review_learnings WHERE project_id = ?",
            (project_id,),
        ).fetchall()

        learnings: dict[str, dict] = {}
        for row in rows:
            learning_id = row["id"]
            learnings[learning_id] = {
                "id": learning_id,
                "rule": row["rule"],
                "category": row["category"],
                "severity": row["severity"],
                "source": row["source"],
                "first_seen": row["first_seen"],
                "last_reinforced": row["last_reinforced"],
                "reinforcement_count": row["reinforcement_count"],
                "contradiction_count": row["contradiction_count"],
                "functional_principle": row["functional_principle"],
            }

        # Load history
        history_rows = self.conn.execute(
            "SELECT * FROM review_history WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ).fetchall()

        review_history: list[dict] = []
        for row in history_rows:
            review_history.append(
                {
                    "timestamp": row["timestamp"],
                    "source": row["source"],
                    "issues_count": row["issues_count"],
                    "new_learning_ids": (
                        json.loads(row["new_learning_ids"])
                        if row["new_learning_ids"]
                        else []
                    ),
                    "reinforced_learning_ids": (
                        json.loads(row["reinforced_learning_ids"])
                        if row["reinforced_learning_ids"]
                        else []
                    ),
                }
            )

        return {"learnings": learnings, "review_history": review_history}

    def save_learnings(self, project_id: str, data: dict) -> None:
        learnings = data.get("learnings", {})
        review_history = data.get("review_history", [])

        # Upsert each learning
        for learning_id, ld in learnings.items():
            self.conn.execute(
                """\
                INSERT INTO review_learnings
                    (project_id, id, rule, category, severity, source,
                     first_seen, last_reinforced, reinforcement_count,
                     contradiction_count, functional_principle)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (project_id, id)
                DO UPDATE SET
                    rule = excluded.rule,
                    last_reinforced = excluded.last_reinforced,
                    reinforcement_count = excluded.reinforcement_count,
                    contradiction_count = excluded.contradiction_count,
                    functional_principle = excluded.functional_principle
                """,
                (
                    project_id,
                    learning_id,
                    ld["rule"],
                    ld["category"],
                    ld["severity"],
                    ld["source"],
                    ld["first_seen"],
                    ld["last_reinforced"],
                    ld.get("reinforcement_count", 1),
                    ld.get("contradiction_count", 0),
                    ld.get("functional_principle"),
                ),
            )

        # Append new history entries — skip any whose timestamp already exists
        existing_ts = {
            row[0]
            for row in self.conn.execute(
                "SELECT timestamp FROM review_history WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        }

        for entry in review_history:
            if entry.get("timestamp") in existing_ts:
                continue
            self.conn.execute(
                """\
                INSERT INTO review_history
                    (project_id, timestamp, source, issues_count,
                     new_learning_ids, reinforced_learning_ids)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    entry["timestamp"],
                    entry.get("source"),
                    entry.get("issues_count", 0),
                    json.dumps(entry.get("new_learning_ids", [])),
                    json.dumps(entry.get("reinforced_learning_ids", [])),
                ),
            )

        self.conn.commit()

    # -- Active session -----------------------------------------------------

    def load_active_session(self, project_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT data FROM active_sessions WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["data"])

    def save_active_session(self, project_id: str, data: dict) -> None:
        self.conn.execute(
            """\
            INSERT INTO active_sessions (project_id, data)
            VALUES (?, ?)
            ON CONFLICT (project_id)
            DO UPDATE SET data = excluded.data,
                          created_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (project_id, json.dumps(data)),
        )
        self.conn.commit()

    def delete_active_session(self, project_id: str) -> None:
        self.conn.execute(
            "DELETE FROM active_sessions WHERE project_id = ?",
            (project_id,),
        )
        self.conn.commit()

    # -- Event streams ------------------------------------------------------

    _EVENT_TABLE_MAP = {
        "rewards": "reward_events",
        "sessions": "sessions",
        "mistakes": "mistakes",
    }

    # Whitelist of valid SQL table names — f-string interpolation is only
    # safe for values in this set.
    _VALID_SQL_TABLES = frozenset({"reward_events", "sessions", "mistakes"})

    def _resolve_table(self, table: str) -> str:
        resolved = self._EVENT_TABLE_MAP.get(table)
        if resolved is None:
            raise ValueError(f"Unknown event table: {table}")
        assert (
            resolved in self._VALID_SQL_TABLES
        ), f"Table {resolved!r} not in whitelist"
        return resolved

    def append_event(self, project_id: str, table: str, record: dict) -> None:
        resolved = self._resolve_table(table)

        if resolved == "reward_events":
            self.conn.execute(
                """\
                INSERT OR REPLACE INTO reward_events
                    (project_id, id, timestamp, outcome, reward_value,
                     rules_active, revision_distance, error_class, notes, source,
                     session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    record["id"],
                    record["timestamp"],
                    record["outcome"],
                    record["reward_value"],
                    json.dumps(record.get("rules_active", [])),
                    record.get("revision_distance"),
                    record.get("error_class"),
                    record.get("notes"),
                    record.get("source"),
                    record.get("session_id"),
                ),
            )
        elif resolved == "sessions":
            self.conn.execute(
                """\
                INSERT OR REPLACE INTO sessions
                    (project_id, id, started_at, ended_at, entry_file,
                     rules_at_start, rules_at_end, selected_rules,
                     error_class, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    record["id"],
                    record["started_at"],
                    record.get("ended_at"),
                    record.get("entry_file"),
                    json.dumps(record.get("rules_at_start", [])),
                    json.dumps(record.get("rules_at_end", [])),
                    json.dumps(record.get("selected_rules", [])),
                    record.get("error_class"),
                    record.get("notes"),
                ),
            )
        elif resolved == "mistakes":
            # Serialize list/dict fields to JSON for SQLite TEXT columns
            related_concepts = record.get("related_concepts")
            if related_concepts is not None and not isinstance(related_concepts, str):
                related_concepts = json.dumps(related_concepts)

            relation_to_prior = record.get("relation_to_prior")
            if relation_to_prior is not None and not isinstance(relation_to_prior, str):
                relation_to_prior = json.dumps(relation_to_prior)

            self.conn.execute(
                """\
                INSERT OR REPLACE INTO mistakes
                    (project_id, id, session_id, timestamp, error_class,
                     description, semantic_hash, was_repeat, corrected_by_rule,
                     related_concepts, relation_to_prior, resolution_action,
                     context, severity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    record["id"],
                    record["session_id"],
                    record["timestamp"],
                    record["error_class"],
                    record["description"],
                    record["semantic_hash"],
                    1 if record.get("was_repeat") else 0,
                    record.get("corrected_by_rule"),
                    related_concepts,
                    relation_to_prior,
                    record.get("resolution_action"),
                    record.get("context"),
                    record.get("severity"),
                ),
            )

        self.conn.commit()

    def load_events(self, project_id: str, table: str) -> list[dict]:
        resolved = self._resolve_table(table)

        rows = self.conn.execute(
            f"SELECT * FROM {resolved} WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ).fetchall()

        return [self._row_to_event_dict(resolved, row) for row in rows]

    def load_events_global(self, table: str) -> list[dict]:
        """Load events across all projects."""
        resolved = self._resolve_table(table)
        rows = self.conn.execute(f"SELECT * FROM {resolved} ORDER BY rowid").fetchall()
        return [self._row_to_event_dict(resolved, row) for row in rows]

    def count_events(self, project_id: str, table: str) -> int:
        resolved = self._resolve_table(table)
        row = self.conn.execute(
            f"SELECT COUNT(*) FROM {resolved} WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return row[0]

    def count_events_global(self, table: str) -> int:
        """Count events across all projects."""
        resolved = self._resolve_table(table)
        row = self.conn.execute(f"SELECT COUNT(*) FROM {resolved}").fetchone()
        return row[0]

    def _row_to_event_dict(self, table: str, row: sqlite3.Row) -> dict:
        """Convert a sqlite3.Row to a plain dict, deserializing JSON columns."""
        d = dict(row)
        d.pop("project_id", None)

        # Deserialize JSON array columns
        json_cols = {
            "reward_events": ["rules_active"],
            "sessions": ["rules_at_start", "rules_at_end", "selected_rules"],
            "mistakes": [],
        }

        for col in json_cols.get(table, []):
            val = d.get(col)
            if val is not None and isinstance(val, str):
                try:
                    d[col] = json.loads(val)
                except json.JSONDecodeError:
                    pass

        # Convert was_repeat int back to bool
        if "was_repeat" in d:
            d["was_repeat"] = bool(d["was_repeat"])

        return d

    # -- Bandit state -------------------------------------------------------

    def load_bandit_state(self, project_id: str) -> dict[str, dict[str, dict]]:
        rows = self.conn.execute(
            "SELECT * FROM bandit_arms WHERE project_id = ?",
            (project_id,),
        ).fetchall()

        result: dict[str, dict[str, dict]] = {}
        for row in rows:
            ctx = row["context"]
            rid = row["rule_id"]
            if ctx not in result:
                result[ctx] = {}
            result[ctx][rid] = {
                "alpha": row["alpha"],
                "beta": row["beta"],
                "is_seed": bool(row["is_seed"]),
                "updated_at": row["updated_at"],
            }
        return result

    def save_bandit_state(
        self, project_id: str, arms: dict[str, dict[str, dict]]
    ) -> None:
        # Atomic: clear and rewrite (compacted save) in one transaction
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                "DELETE FROM bandit_arms WHERE project_id = ?", (project_id,)
            )
            for context, rules in arms.items():
                for rule_id, params in rules.items():
                    self.conn.execute(
                        """\
                        INSERT INTO bandit_arms
                            (project_id, context, rule_id, alpha, beta, is_seed, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            project_id,
                            context,
                            rule_id,
                            params["alpha"],
                            params["beta"],
                            1 if params.get("is_seed") else 0,
                            params.get(
                                "updated_at",
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        ),
                    )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def append_bandit_update(
        self, project_id: str, context: str, rule_id: str, record: dict
    ) -> None:
        self.conn.execute(
            """\
            INSERT INTO bandit_arms
                (project_id, context, rule_id, alpha, beta, is_seed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (project_id, context, rule_id)
            DO UPDATE SET alpha = excluded.alpha,
                          beta = excluded.beta,
                          is_seed = excluded.is_seed,
                          updated_at = excluded.updated_at
            """,
            (
                project_id,
                context,
                rule_id,
                record["alpha"],
                record["beta"],
                1 if record.get("is_seed") else 0,
                record.get("updated_at", datetime.now(timezone.utc).isoformat()),
            ),
        )
        self.conn.commit()
