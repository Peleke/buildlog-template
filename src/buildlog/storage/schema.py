"""SQLite schema definitions and initialization.

All DDL lives here so that ``init_schema()`` is the single entry point
for creating or upgrading the global database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["SCHEMA_VERSION", "init_schema"]

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# DDL statements
# ---------------------------------------------------------------------------

_PRAGMAS = """\
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
"""

_CREATE_SCHEMA_VERSION = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

_CREATE_PROJECTS = """\
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    path        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

_CREATE_SKILL_DECISIONS = """\
CREATE TABLE IF NOT EXISTS skill_decisions (
    project_id  TEXT NOT NULL REFERENCES projects(id),
    skill_id    TEXT NOT NULL,
    decision    TEXT NOT NULL CHECK (decision IN ('promoted', 'rejected')),
    decided_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    metadata    TEXT,  -- JSON blob for per-ID metadata (e.g. promoted_at timestamps)
    PRIMARY KEY (project_id, skill_id)
);
"""

_CREATE_REVIEW_LEARNINGS = """\
CREATE TABLE IF NOT EXISTS review_learnings (
    project_id          TEXT NOT NULL REFERENCES projects(id),
    id                  TEXT NOT NULL,
    rule                TEXT NOT NULL,
    category            TEXT NOT NULL,
    severity            TEXT NOT NULL,
    source              TEXT NOT NULL,
    first_seen          TEXT NOT NULL,
    last_reinforced     TEXT NOT NULL,
    reinforcement_count INTEGER NOT NULL DEFAULT 1,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    functional_principle TEXT,
    PRIMARY KEY (project_id, id)
);
"""

_CREATE_REVIEW_HISTORY = """\
CREATE TABLE IF NOT EXISTS review_history (
    rowid               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          TEXT NOT NULL REFERENCES projects(id),
    timestamp           TEXT NOT NULL,
    source              TEXT,
    issues_count        INTEGER NOT NULL DEFAULT 0,
    new_learning_ids    TEXT,  -- JSON array
    reinforced_learning_ids TEXT  -- JSON array
);
CREATE INDEX IF NOT EXISTS idx_review_history_project
    ON review_history(project_id, timestamp DESC);
"""

_CREATE_ACTIVE_SESSIONS = """\
CREATE TABLE IF NOT EXISTS active_sessions (
    project_id  TEXT PRIMARY KEY REFERENCES projects(id),
    data        TEXT NOT NULL,  -- JSON blob
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

_CREATE_REWARD_EVENTS = """\
CREATE TABLE IF NOT EXISTS reward_events (
    project_id      TEXT NOT NULL REFERENCES projects(id),
    id              TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    reward_value    REAL NOT NULL,
    rules_active    TEXT,  -- JSON array
    revision_distance REAL,
    error_class     TEXT,
    notes           TEXT,
    source          TEXT,
    PRIMARY KEY (project_id, id)
);
CREATE INDEX IF NOT EXISTS idx_reward_events_ts
    ON reward_events(project_id, timestamp DESC);
"""

_CREATE_SESSIONS = """\
CREATE TABLE IF NOT EXISTS sessions (
    project_id      TEXT NOT NULL REFERENCES projects(id),
    id              TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    entry_file      TEXT,
    rules_at_start  TEXT,  -- JSON array
    rules_at_end    TEXT,  -- JSON array
    selected_rules  TEXT,  -- JSON array
    error_class     TEXT,
    notes           TEXT,
    PRIMARY KEY (project_id, id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_ts
    ON sessions(project_id, started_at DESC);
"""

_CREATE_MISTAKES = """\
CREATE TABLE IF NOT EXISTS mistakes (
    project_id      TEXT NOT NULL REFERENCES projects(id),
    id              TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    error_class     TEXT NOT NULL,
    description     TEXT NOT NULL,
    semantic_hash   TEXT NOT NULL,
    was_repeat      INTEGER NOT NULL DEFAULT 0,
    corrected_by_rule TEXT,
    PRIMARY KEY (project_id, id)
);
CREATE INDEX IF NOT EXISTS idx_mistakes_session
    ON mistakes(project_id, session_id);
CREATE INDEX IF NOT EXISTS idx_mistakes_hash
    ON mistakes(project_id, semantic_hash);
"""

_CREATE_BANDIT_ARMS = """\
CREATE TABLE IF NOT EXISTS bandit_arms (
    project_id  TEXT NOT NULL REFERENCES projects(id),
    context     TEXT NOT NULL,
    rule_id     TEXT NOT NULL,
    alpha       REAL NOT NULL DEFAULT 1.0,
    beta        REAL NOT NULL DEFAULT 1.0,
    is_seed     INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (project_id, context, rule_id)
);
CREATE INDEX IF NOT EXISTS idx_bandit_context
    ON bandit_arms(project_id, context);
"""

# Ordered list of all DDL blocks for schema v1.
_DDL_V1: list[str] = [
    _CREATE_SCHEMA_VERSION,
    _CREATE_PROJECTS,
    _CREATE_SKILL_DECISIONS,
    _CREATE_REVIEW_LEARNINGS,
    _CREATE_REVIEW_HISTORY,
    _CREATE_ACTIVE_SESSIONS,
    _CREATE_REWARD_EVENTS,
    _CREATE_SESSIONS,
    _CREATE_MISTAKES,
    _CREATE_BANDIT_ARMS,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_schema(conn: sqlite3.Connection) -> int:
    """Create or upgrade the schema to the current version.

    Args:
        conn: Open SQLite connection.

    Returns:
        The schema version after initialization.
    """
    # Apply pragmas (must be outside a transaction for WAL)
    for line in _PRAGMAS.strip().splitlines():
        conn.execute(line)

    # Check current version
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current_version = row[0] if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        current_version = 0

    if current_version >= SCHEMA_VERSION:
        return current_version

    # Apply v1 schema
    if current_version < 1:
        for ddl in _DDL_V1:
            conn.executescript(ddl)
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (1,),
        )
        conn.commit()

    return SCHEMA_VERSION


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the global database and ensure the schema is current.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An open ``sqlite3.Connection`` with schema initialized.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn
