"""Data exporters.

Implements the :class:`Exporter` protocol for different output formats.
"""

from __future__ import annotations

import json
from pathlib import Path

from buildlog.storage.base import StorageBackend
from buildlog.storage.sqlite import SQLiteBackend

__all__ = ["JsonlExporter"]

_EXPORTABLE_TABLES = ["rewards", "sessions", "mistakes"]


class JsonlExporter:
    """Export data as JSONL files — same format as the legacy backend."""

    name: str = "jsonl"

    def export(
        self,
        backend: StorageBackend,
        project_id: str | None = None,
        output_path: Path | None = None,
        tables: list[str] | None = None,
    ) -> str:
        """Export events from a backend to JSONL files.

        Args:
            backend: Storage backend to read from.
            project_id: Limit to a single project.  ``None`` = all projects
                (requires :class:`SQLiteBackend`).
            output_path: Directory to write files into.  ``None`` = return
                data as a single string.
            tables: Subset of tables to export.  ``None`` = all.

        Returns:
            Summary message.
        """
        target_tables = tables or _EXPORTABLE_TABLES
        for t in target_tables:
            if t not in _EXPORTABLE_TABLES:
                raise ValueError(
                    f"Unknown table '{t}'. Must be one of {_EXPORTABLE_TABLES}"
                )

        results: dict[str, list[dict]] = {}
        for table in target_tables:
            if project_id is not None:
                events = backend.load_events(project_id, table)
            elif isinstance(backend, SQLiteBackend):
                events = backend.load_events_global(table)
            else:
                events = backend.load_events("", table)
            results[table] = events

        if output_path is not None:
            output_path.mkdir(parents=True, exist_ok=True)
            lines_written = 0
            for table, events in results.items():
                fpath = output_path / f"{table}.jsonl"
                with open(fpath, "w") as f:
                    for event in events:
                        f.write(json.dumps(event) + "\n")
                        lines_written += 1

            table_summary = ", ".join(f"{t}={len(results[t])}" for t in target_tables)
            return (
                f"Exported {lines_written} records to {output_path}/ "
                f"({table_summary})"
            )

        # No output path → return as string
        chunks: list[str] = []
        for table, events in results.items():
            chunks.append(f"--- {table} ---")
            for event in events:
                chunks.append(json.dumps(event))
        return "\n".join(chunks)
