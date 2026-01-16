"""Render skills to .claude/settings.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from buildlog.skills import _to_imperative

if TYPE_CHECKING:
    from buildlog.skills import Skill


class SettingsJsonRenderer:
    """Merges promoted skills into .claude/settings.json."""

    def __init__(self, path: Path | None = None, tracking_path: Path | None = None):
        """Initialize renderer.

        Args:
            path: Path to settings.json file. Defaults to .claude/settings.json.
            tracking_path: Path to promoted.json tracking file.
                Defaults to .buildlog/promoted.json.
        """
        self.path = path or Path(".claude/settings.json")
        self.tracking_path = tracking_path or Path(".buildlog/promoted.json")

    def render(self, skills: list[Skill]) -> str:
        """Merge skills into settings.json rules array.

        Args:
            skills: List of skills to add.

        Returns:
            Confirmation message.
        """
        if not skills:
            return "No skills to promote"

        # Load existing settings
        if self.path.exists():
            settings = json.loads(self.path.read_text())
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            settings = {}

        # Get or create rules array
        rules: list[str] = settings.setdefault("rules", [])

        # Add new rules (converted to imperative form)
        added = 0
        for skill in skills:
            rule = _to_imperative(skill.rule, skill.confidence)
            if rule not in rules:
                rules.append(rule)
                added += 1

        # Update buildlog metadata
        settings["_buildlog"] = {
            "last_updated": datetime.now().isoformat(),
            "promoted_skill_ids": [s.id for s in skills],
        }

        # Write back
        self.path.write_text(json.dumps(settings, indent=2))

        # Track promoted skill IDs
        self._track_promoted(skills)

        return f"Added {added} rules to {self.path} ({len(skills) - added} duplicates skipped)"

    def _track_promoted(self, skills: list[Skill]) -> None:
        """Track which skills have been promoted."""
        self.tracking_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing tracking data
        if self.tracking_path.exists():
            tracking = json.loads(self.tracking_path.read_text())
        else:
            tracking = {"skill_ids": [], "promoted_at": {}}

        # Add new skill IDs
        now = datetime.now().isoformat()
        for skill in skills:
            if skill.id not in tracking["skill_ids"]:
                tracking["skill_ids"].append(skill.id)
                tracking["promoted_at"][skill.id] = now

        self.tracking_path.write_text(json.dumps(tracking, indent=2))
