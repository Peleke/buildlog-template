"""Shared tracking utilities for render adapters."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from buildlog.skills import Skill

__all__ = ["track_promoted", "get_promoted_ids"]


def get_promoted_ids(tracking_path: Path) -> set[str]:
    """Get the set of already-promoted skill IDs.

    Args:
        tracking_path: Path to the tracking JSON file.

    Returns:
        Set of skill IDs that have been promoted.
    """
    if not tracking_path.exists():
        return set()

    try:
        tracking = json.loads(tracking_path.read_text())
        return set(tracking.get("skill_ids", []))
    except json.JSONDecodeError:
        return set()


def track_promoted(skills: list[Skill], tracking_path: Path) -> None:
    """Track which skills have been promoted.

    Writes skill IDs and promotion timestamps to a JSON file.
    Handles corrupt JSON gracefully by starting fresh.

    Args:
        skills: Skills that were promoted.
        tracking_path: Path to the tracking JSON file.
    """
    tracking_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing tracking data (handle corrupt JSON)
    tracking: dict = {"skill_ids": [], "promoted_at": {}}
    if tracking_path.exists():
        try:
            tracking = json.loads(tracking_path.read_text())
        except json.JSONDecodeError:
            pass  # Start fresh if corrupted

    # Add new skill IDs
    now = datetime.now().isoformat()
    for skill in skills:
        if skill.id not in tracking["skill_ids"]:
            tracking["skill_ids"].append(skill.id)
            tracking["promoted_at"][skill.id] = now

    tracking_path.write_text(json.dumps(tracking, indent=2))
