"""Data exporters.

Implements the :class:`Exporter` protocol for different output formats.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from buildlog.storage.base import StorageBackend
from buildlog.storage.sqlite import SQLiteBackend

__all__ = ["JsonlExporter", "EXPORTABLE_TABLES"]

# Tables that use load_events (append-only event streams)
_EVENT_TABLES = ["rewards", "sessions", "mistakes"]

# Tables with specialized load methods
_SPECIAL_TABLES = ["bandit_state", "learnings", "skill_decisions"]

EXPORTABLE_TABLES = _EVENT_TABLES + _SPECIAL_TABLES


def _load_special_table(
    backend: StorageBackend, project_id: str | None, table: str
) -> list[dict]:
    """Load data from a non-event table using specialized backend methods.

    Args:
        backend: Storage backend to read from.
        project_id: Project identifier (required for special tables).
        table: One of 'bandit_state', 'learnings', 'skill_decisions'.

    Returns:
        List of flat dicts suitable for JSONL export.
    """
    pid = project_id or ""

    if table == "bandit_state":
        state = backend.load_bandit_state(pid)
        rows = []
        for context, rules in state.items():
            for rule_id, params in rules.items():
                rows.append(
                    {
                        "context": context,
                        "rule_id": rule_id,
                        "alpha": params.get("alpha", 1.0),
                        "beta": params.get("beta", 1.0),
                        "mean": round(
                            params.get("alpha", 1.0)
                            / (params.get("alpha", 1.0) + params.get("beta", 1.0)),
                            4,
                        ),
                        "is_seed": params.get("is_seed", False),
                        "updated_at": params.get("updated_at", ""),
                    }
                )
        return rows

    if table == "learnings":
        data = backend.load_learnings(pid)
        learnings = data.get("learnings", {})
        return [
            {"key": k, **v} if isinstance(v, dict) else {"key": k, "value": v}
            for k, v in learnings.items()
        ]

    if table == "skill_decisions":
        promoted = backend.load_id_set(pid, "promoted")
        rejected = backend.load_id_set(pid, "rejected")
        rows = []
        for sid in promoted:
            rows.append({"skill_id": sid, "decision": "promoted"})
        for sid in rejected:
            rows.append({"skill_id": sid, "decision": "rejected"})
        return rows

    raise ValueError(f"Unknown special table: {table}")


def _build_rules_join(seeds_dir: Path | None) -> list[dict]:
    """Build rules join table from seed files.

    Each row contains buildlog skill metadata joined with upstream
    provenance fields from the seed file.

    Args:
        seeds_dir: Path to seeds directory. None = auto-detect.

    Returns:
        List of dicts for rules.jsonl.
    """
    from buildlog.seeds import get_default_seeds_dir, load_all_seeds, seeds_to_skills

    if seeds_dir is None:
        seeds_dir = get_default_seeds_dir()
    if seeds_dir is None:
        return []

    all_seeds = load_all_seeds(seeds_dir)
    rows = []
    for persona, seed_file in all_seeds.items():
        skills = seeds_to_skills(seed_file)
        for skill in skills:
            row: dict = {
                "buildlog_id": skill.id,
                "rule": skill.rule,
                "category": skill.category,
                "confidence": skill.confidence,
                "persona": persona,
            }
            if skill.provenance:
                # Direct-mapped keys (no renaming needed)
                for key in (
                    "source_id",
                    "source_domain",
                    "source_derivation",
                    "graph_version",
                ):
                    if key in skill.provenance:
                        row[key] = skill.provenance[key]
                # Map provenance "confidence" to "source_confidence"
                # (provenance "source_confidence" takes priority if both exist)
                if "confidence" in skill.provenance:
                    row["source_confidence"] = skill.provenance["confidence"]
                if "source_confidence" in skill.provenance:
                    row["source_confidence"] = skill.provenance["source_confidence"]
            rows.append(row)

    return rows


class JsonlExporter:
    """Export data as JSONL files (same format as the legacy backend)."""

    name: str = "jsonl"

    def export(
        self,
        backend: StorageBackend,
        project_id: str | None = None,
        output_path: Path | None = None,
        tables: list[str] | None = None,
        include_manifest: bool = True,
        include_rules_join: bool = True,
        seeds_dir: Path | None = None,
    ) -> str:
        """Export events from a backend to JSONL files.

        Args:
            backend: Storage backend to read from.
            project_id: Limit to a single project.  ``None`` = all projects
                (requires :class:`SQLiteBackend`).
            output_path: Directory to write files into.  ``None`` = return
                data as a single string.
            tables: Subset of tables to export.  ``None`` = all.
            include_manifest: Generate manifest.json with export metadata.
            include_rules_join: Generate rules.jsonl join table from seeds.
            seeds_dir: Path to seeds directory for rules join.

        Returns:
            Summary message.
        """
        target_tables = tables or EXPORTABLE_TABLES
        for t in target_tables:
            if t not in EXPORTABLE_TABLES:
                raise ValueError(
                    f"Unknown table '{t}'. Must be one of {EXPORTABLE_TABLES}"
                )

        results: dict[str, list[dict]] = {}
        for table in target_tables:
            if table in _SPECIAL_TABLES:
                results[table] = _load_special_table(backend, project_id, table)
            elif project_id is not None:
                results[table] = backend.load_events(project_id, table)
            elif isinstance(backend, SQLiteBackend):
                results[table] = backend.load_events_global(table)
            else:
                results[table] = backend.load_events("", table)

        if output_path is not None:
            output_path.mkdir(parents=True, exist_ok=True)
            lines_written = 0
            for table, events in results.items():
                fpath = output_path / f"{table}.jsonl"
                with open(fpath, "w") as f:
                    for event in events:
                        f.write(json.dumps(event) + "\n")
                        lines_written += 1

            # Generate rules join table
            if include_rules_join:
                rules_rows = _build_rules_join(seeds_dir)
                if rules_rows:
                    rules_path = output_path / "rules.jsonl"
                    with open(rules_path, "w") as f:
                        for row in rules_rows:
                            f.write(json.dumps(row) + "\n")

            # Generate manifest
            if include_manifest:
                manifest = {
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "project_id": project_id,
                    "tables": {t: len(results[t]) for t in target_tables},
                }
                manifest_path = output_path / "manifest.json"
                with open(manifest_path, "w") as f:
                    json.dump(manifest, f, indent=2)

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
