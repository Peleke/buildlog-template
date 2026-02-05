"""Storage backend protocol definitions.

Defines the StorageBackend protocol that all storage implementations must satisfy,
and the Exporter protocol for data export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for pluggable storage backends.

    Every method takes a ``project_id`` as its first argument so that a single
    backend instance (e.g. a global SQLite database) can serve multiple projects.

    The ``LegacyBackend`` ignores ``project_id`` because data is already scoped
    by ``buildlog_dir`` path.
    """

    # -- ID set operations (promoted.json / rejected.json) -------------------

    def load_id_set(self, project_id: str, collection: str) -> set[str]:
        """Load a set of IDs (e.g. promoted or rejected skill IDs).

        Args:
            project_id: Project identifier.
            collection: Either ``'promoted'`` or ``'rejected'``.

        Returns:
            Set of skill ID strings.
        """
        ...

    def save_id_set(
        self,
        project_id: str,
        collection: str,
        ids: set[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save a set of IDs with optional metadata.

        Args:
            project_id: Project identifier.
            collection: Either ``'promoted'`` or ``'rejected'``.
            ids: Set of skill ID strings.
            metadata: Optional per-ID metadata (e.g. timestamps).
        """
        ...

    # -- Review learnings ---------------------------------------------------

    def load_learnings(self, project_id: str) -> dict:
        """Load review learnings.

        Returns:
            Dictionary with ``'learnings'`` and ``'review_history'`` keys.
        """
        ...

    def save_learnings(self, project_id: str, data: dict) -> None:
        """Save review learnings.

        Args:
            data: Dictionary with ``'learnings'`` and ``'review_history'`` keys.
        """
        ...

    # -- Active session -----------------------------------------------------

    def load_active_session(self, project_id: str) -> dict | None:
        """Load active session data.

        Returns:
            Session dictionary, or None if no active session.
        """
        ...

    def save_active_session(self, project_id: str, data: dict) -> None:
        """Save active session data."""
        ...

    def delete_active_session(self, project_id: str) -> None:
        """Delete the active session marker."""
        ...

    # -- Event streams (JSONL: rewards, sessions, mistakes) -----------------

    def append_event(self, project_id: str, table: str, record: dict) -> None:
        """Append a single event record.

        Args:
            project_id: Project identifier.
            table: One of ``'rewards'``, ``'sessions'``, ``'mistakes'``.
            record: Serialized event dictionary.
        """
        ...

    def load_events(self, project_id: str, table: str) -> list[dict]:
        """Load all events for a project and table.

        Args:
            project_id: Project identifier.
            table: One of ``'rewards'``, ``'sessions'``, ``'mistakes'``.

        Returns:
            List of event dictionaries, ordered by insertion.
        """
        ...

    def count_events(self, project_id: str, table: str) -> int:
        """Count events for a project and table.

        Args:
            project_id: Project identifier.
            table: One of ``'rewards'``, ``'sessions'``, ``'mistakes'``.

        Returns:
            Number of events.
        """
        ...

    # -- Bandit state -------------------------------------------------------

    def load_bandit_state(self, project_id: str) -> dict[str, dict[str, dict]]:
        """Load and compact bandit arm state.

        Returns:
            Nested dict: ``{context: {rule_id: {alpha, beta, is_seed, updated_at}}}``
        """
        ...

    def save_bandit_state(
        self, project_id: str, arms: dict[str, dict[str, dict]]
    ) -> None:
        """Save full bandit state (compacted).

        Args:
            arms: Nested dict: ``{context: {rule_id: {alpha, beta, is_seed, updated_at}}}``
        """
        ...

    def append_bandit_update(
        self, project_id: str, context: str, rule_id: str, record: dict
    ) -> None:
        """Append a single bandit arm update.

        Args:
            context: Error class context.
            rule_id: Rule identifier.
            record: Arm state dict with alpha, beta, is_seed, updated_at.
        """
        ...


@runtime_checkable
class Exporter(Protocol):
    """Protocol for data export formats."""

    name: str

    def export(
        self,
        backend: StorageBackend,
        project_id: str | None = None,
        output_path: Path | None = None,
        tables: list[str] | None = None,
    ) -> str:
        """Export data from a backend.

        Args:
            backend: Storage backend to read from.
            project_id: Limit to a single project. None = all projects.
            output_path: Directory to write output files. None = return as string.
            tables: Limit to specific tables. None = all tables.

        Returns:
            Summary message describing what was exported.
        """
        ...
