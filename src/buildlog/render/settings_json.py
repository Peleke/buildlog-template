"""Render skills to .claude/settings.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from buildlog.render.tracking import track_promoted
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

        # Update buildlog metadata (accumulate, don't replace)
        buildlog_meta = settings.get("_buildlog", {"promoted_skill_ids": []})
        existing_ids = set(buildlog_meta.get("promoted_skill_ids", []))
        new_ids = existing_ids | {s.id for s in skills}
        settings["_buildlog"] = {
            "last_updated": datetime.now().isoformat(),
            "promoted_skill_ids": sorted(new_ids),
        }

        # Write back
        self.path.write_text(json.dumps(settings, indent=2))

        # Track promoted skill IDs using shared utility
        track_promoted(skills, self.tracking_path)

        return f"Added {added} rules to {self.path} ({len(skills) - added} duplicates skipped)"
