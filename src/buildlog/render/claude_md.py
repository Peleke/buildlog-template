"""Render skills to CLAUDE.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from buildlog.render.tracking import track_promoted
from buildlog.skills import _to_imperative

if TYPE_CHECKING:
    from buildlog.skills import Skill


class ClaudeMdRenderer:
    """Appends promoted skills to CLAUDE.md."""

    def __init__(self, path: Path | None = None, tracking_path: Path | None = None):
        """Initialize renderer.

        Args:
            path: Path to CLAUDE.md file. Defaults to CLAUDE.md in current directory.
            tracking_path: Path to promoted.json tracking file.
                Defaults to .buildlog/promoted.json relative to path.
        """
        self.path = path or Path("CLAUDE.md")
        if tracking_path is None:
            self.tracking_path = self.path.parent / ".buildlog" / "promoted.json"
        else:
            self.tracking_path = tracking_path

    def render(self, skills: list[Skill]) -> str:
        """Append skills to CLAUDE.md.

        Args:
            skills: List of skills to append.

        Returns:
            Confirmation message.
        """
        if not skills:
            return "No skills to promote"

        # Group by category
        by_category: dict[str, list[Skill]] = {}
        for skill in skills:
            by_category.setdefault(skill.category, []).append(skill)

        # Build section
        lines = [
            "",
            f"## Learned Rules (auto-generated {datetime.now().strftime('%Y-%m-%d')})",
            "",
        ]

        category_titles = {
            "architectural": "Architectural",
            "workflow": "Workflow",
            "tool_usage": "Tool Usage",
            "domain_knowledge": "Domain Knowledge",
        }

        for category, cat_skills in by_category.items():
            title = category_titles.get(category, category.replace("_", " ").title())
            lines.append(f"### {title}")
            lines.append("")
            for skill in cat_skills:
                rule = _to_imperative(skill.rule, skill.confidence)
                lines.append(f"- {rule}")
            lines.append("")

        content = "\n".join(lines)

        # Append to file
        if self.path.exists():
            existing = self.path.read_text()
            self.path.write_text(existing + content)
        else:
            self.path.write_text(content)

        # Track promoted skill IDs using shared utility
        track_promoted(skills, self.tracking_path)

        return f"Appended {len(skills)} rules to {self.path}"
