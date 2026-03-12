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

# Whitelist of columns that can be updated on gauntlet_rules.
_GAUNTLET_UPDATABLE: frozenset[str] = frozenset(
    {
        "rule",
        "category",
        "context",
        "antipattern",
        "rationale",
        "tags",
        "refs",
        "provenance",
        "version",
        "active",
        "seed_file_hash",
        "seed_filename",
    }
)


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

    def list_projects(self) -> list[dict]:
        """Return all registered projects as ``[{id, name, path}]``."""
        rows = self.conn.execute(
            "SELECT id, name, path FROM projects ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

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
        "gauntlet_credits": "gauntlet_credits",
    }

    # Whitelist of valid SQL table names — f-string interpolation is only
    # safe for values in this set.
    _VALID_SQL_TABLES = frozenset(
        {"reward_events", "sessions", "mistakes", "gauntlet_credits"}
    )

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

            rules_consulted = record.get("rules_consulted")
            if rules_consulted is not None and not isinstance(rules_consulted, str):
                rules_consulted = json.dumps(rules_consulted)

            self.conn.execute(
                """\
                INSERT OR REPLACE INTO mistakes
                    (project_id, id, session_id, timestamp, error_class,
                     description, semantic_hash, was_repeat, corrected_by_rule,
                     related_concepts, relation_to_prior, resolution_action,
                     context, severity, rules_consulted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    rules_consulted,
                ),
            )
        elif resolved == "gauntlet_credits":
            self.conn.execute(
                """\
                INSERT INTO gauntlet_credits
                    (project_id, timestamp, iteration, rules)
                VALUES (?, ?, ?, ?)
                """,
                (
                    project_id,
                    record["timestamp"],
                    record["iteration"],
                    json.dumps(record.get("rules", [])),
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
            "gauntlet_credits": ["rules"],
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

    # -- Gauntlet rules (global, no project_id) -----------------------------

    def load_gauntlet_rules(
        self,
        persona: str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if persona is not None:
            clauses.append("persona = ?")
            params.append(persona)
        if active_only:
            clauses.append("active = 1")

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM gauntlet_rules{where} ORDER BY persona, rowid",
            params,
        ).fetchall()

        return [self._gauntlet_row_to_dict(row) for row in rows]

    def save_gauntlet_rules_batch(
        self,
        rules: list[dict],
        seed_file_hash: str | None = None,
        seed_filename: str | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        for r in rules:
            self.conn.execute(
                """\
                INSERT INTO gauntlet_rules
                    (rule_id, persona, rule, category, context, antipattern,
                     rationale, tags, refs, provenance, version, active,
                     created_at, updated_at, seed_file_hash, seed_filename)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (rule_id)
                DO UPDATE SET
                    rule = excluded.rule,
                    category = excluded.category,
                    context = excluded.context,
                    antipattern = excluded.antipattern,
                    rationale = excluded.rationale,
                    tags = excluded.tags,
                    refs = excluded.refs,
                    provenance = excluded.provenance,
                    version = excluded.version,
                    active = excluded.active,
                    updated_at = excluded.updated_at,
                    seed_file_hash = excluded.seed_file_hash,
                    seed_filename = excluded.seed_filename
                """,
                (
                    r["rule_id"],
                    r["persona"],
                    r["rule"],
                    r["category"],
                    r.get("context", ""),
                    r.get("antipattern", ""),
                    r.get("rationale", ""),
                    json.dumps(r.get("tags", [])),
                    json.dumps(r.get("refs", [])),
                    json.dumps(r.get("provenance")) if r.get("provenance") else None,
                    r.get("version", 1),
                    1 if r.get("active", True) else 0,
                    r.get("created_at", now),
                    now,
                    seed_file_hash or r.get("seed_file_hash"),
                    seed_filename or r.get("seed_filename"),
                ),
            )
            count += 1
        self.conn.commit()
        return count

    def get_gauntlet_rule(self, rule_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM gauntlet_rules WHERE rule_id = ?",
            (rule_id,),
        ).fetchone()
        if row is None:
            return None
        return self._gauntlet_row_to_dict(row)

    def update_gauntlet_rule(self, rule_id: str, **fields: Any) -> bool:
        # Only allow whitelisted columns
        safe_fields = {k: v for k, v in fields.items() if k in _GAUNTLET_UPDATABLE}
        if not safe_fields:
            return False

        # Serialize JSON fields
        for col in ("tags", "refs", "provenance"):
            if col in safe_fields and not isinstance(safe_fields[col], str):
                safe_fields[col] = json.dumps(safe_fields[col])

        now = datetime.now(timezone.utc).isoformat()
        safe_fields["updated_at"] = now

        set_clause = ", ".join(f"{k} = ?" for k in safe_fields)
        params = list(safe_fields.values()) + [rule_id]
        cursor = self.conn.execute(
            f"UPDATE gauntlet_rules SET {set_clause} WHERE rule_id = ?",
            params,
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def deactivate_gauntlet_rule(self, rule_id: str) -> bool:
        return self.update_gauntlet_rule(rule_id, active=0)

    def count_gauntlet_rules(
        self,
        persona: str | None = None,
        active_only: bool = True,
    ) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if persona is not None:
            clauses.append("persona = ?")
            params.append(persona)
        if active_only:
            clauses.append("active = 1")

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        row = self.conn.execute(
            f"SELECT COUNT(*) FROM gauntlet_rules{where}",
            params,
        ).fetchone()
        return row[0]

    # -- Posterior snapshots --------------------------------------------------

    def append_posterior_snapshots(self, project_id: str, records: list[dict]) -> int:
        """Batch insert posterior snapshots. Returns count inserted."""
        ts = datetime.now(timezone.utc).isoformat()
        count = 0
        for rec in records:
            self.conn.execute(
                """\
                INSERT INTO posterior_snapshots
                    (project_id, timestamp, rule_id, alpha, beta, mean,
                     trigger, iteration, batch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    rec.get("timestamp", ts),
                    rec["rule_id"],
                    rec["alpha"],
                    rec["beta"],
                    rec["mean"],
                    rec["trigger"],
                    rec.get("iteration"),
                    rec.get("batch_id"),
                ),
            )
            count += 1
        self.conn.commit()
        return count

    def load_posterior_history(
        self,
        project_id: str,
        rule_id: str | None = None,
        since: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Load posterior snapshots ordered by timestamp ascending."""
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if rule_id is not None:
            clauses.append("rule_id = ?")
            params.append(rule_id)
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since)
        where = " AND ".join(clauses)
        params.append(limit)
        rows = self.conn.execute(
            f"SELECT * FROM posterior_snapshots WHERE {where} ORDER BY timestamp ASC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Emission edges ------------------------------------------------------

    # Whitelist of filterable columns for emission_edges queries.
    _EMISSION_EDGE_FILTERS = frozenset({"project_id", "relation_type"})

    def store_emission_edges(self, edges: list[dict]) -> int:
        """Bulk insert emission edges, skipping duplicates. Returns count stored."""
        stored = 0
        for edge in edges:
            try:
                props = edge.get("properties")
                if props is not None and not isinstance(props, str):
                    props = json.dumps(props)
                self.conn.execute(
                    """\
                    INSERT OR IGNORE INTO emission_edges
                        (source_id, target_id, relation_type, confidence,
                         artifact_type, project_id, emitted_at, consumed_at, properties)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge["source_id"],
                        edge["target_id"],
                        edge["relation_type"],
                        edge.get("confidence"),
                        edge["artifact_type"],
                        edge["project_id"],
                        edge["emitted_at"],
                        edge["consumed_at"],
                        props,
                    ),
                )
                stored += self.conn.execute("SELECT changes()").fetchone()[0]
            except sqlite3.IntegrityError:
                pass
        self.conn.commit()
        return stored

    def count_emission_edges(
        self,
        project_id: str | None = None,
        relation_type: str | None = None,
    ) -> int:
        """Count stored emission edges, optionally filtered."""
        clauses: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if relation_type is not None:
            clauses.append("relation_type = ?")
            params.append(relation_type)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        row = self.conn.execute(
            f"SELECT COUNT(*) FROM emission_edges{where}",
            params,
        ).fetchone()
        return row[0]

    def load_emission_edges(
        self,
        project_id: str | None = None,
        relation_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Load emission edges, optionally filtered."""
        clauses: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if relation_type is not None:
            clauses.append("relation_type = ?")
            params.append(relation_type)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self.conn.execute(
            f"SELECT * FROM emission_edges{where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            props = d.get("properties")
            if props is not None and isinstance(props, str):
                try:
                    d["properties"] = json.loads(props)
                except json.JSONDecodeError:
                    pass
            result.append(d)
        return result

    def _gauntlet_row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        # Deserialize JSON columns
        for col in ("tags", "refs"):
            val = d.get(col)
            if val is not None and isinstance(val, str):
                try:
                    d[col] = json.loads(val)
                except json.JSONDecodeError:
                    pass
        prov = d.get("provenance")
        if prov is not None and isinstance(prov, str):
            try:
                d["provenance"] = json.loads(prov)
            except json.JSONDecodeError:
                pass
        d["active"] = bool(d.get("active", 1))
        return d
