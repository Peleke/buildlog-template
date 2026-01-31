"""Render skills to GitHub Copilot instructions format.

Appends a learned rules section to .github/copilot-instructions.md.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from buildlog.render.tracking import get_promoted_ids, track_promoted
from buildlog.skills import _to_imperative

if TYPE_CHECKING:
    from buildlog.skills import Skill


class CopilotRenderer:
    """Appends promoted skills to .github/copilot-instructions.md."""

    def __init__(self, path: Path | None = None, tracking_path: Path | None = None):
        """Initialize renderer.

        Args:
            path: Path to copilot instructions file.
                Defaults to .github/copilot-instructions.md.
            tracking_path: Path to promoted.json tracking file.
                Defaults to .buildlog/promoted.json.
        """
        self.path = path or Path(".github/copilot-instructions.md")
        self.tracking_path = tracking_path or Path(".buildlog/promoted.json")

    def render(self, skills: list[Skill]) -> str:
        """Append skills to copilot-instructions.md.

        Filters out already-promoted skills and appends a new section.

        Args:
            skills: List of skills to render.

        Returns:
            Confirmation message.
        """
        if not skills:
            return "No skills to promote"

        # Filter out already-promoted skills
        already_promoted = get_promoted_ids(self.tracking_path)
        new_skills = [s for s in skills if s.id not in already_promoted]

        if not new_skills:
            return f"All {len(skills)} skills already promoted"

        # Group by category
        by_category: dict[str, list[Skill]] = {}
        for skill in new_skills:
            by_category.setdefault(skill.category, []).append(skill)

        category_titles = {
            "architectural": "Architectural",
            "workflow": "Workflow",
            "tool_usage": "Tool Usage",
            "domain_knowledge": "Domain Knowledge",
        }

        # Build section
        lines = [
            "",
            f"## Learned Rules (buildlog {datetime.now().strftime('%Y-%m-%d')})",
            "",
        ]

        for category, cat_skills in by_category.items():
            title = category_titles.get(category, category.replace("_", " ").title())
            lines.append(f"### {title}")
            lines.append("")
            for skill in cat_skills:
                rule = _to_imperative(skill.rule, skill.confidence)
                lines.append(f"- {rule}")
            lines.append("")

        content = "\n".join(lines)

        # Append to file (create if needed)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            existing = self.path.read_text()
            self.path.write_text(existing + content)
        else:
            self.path.write_text(content)

        # Track promoted skill IDs
        track_promoted(new_skills, self.tracking_path)

        skipped = len(skills) - len(new_skills)
        msg = f"Appended {len(new_skills)} rules to {self.path}"
        if skipped > 0:
            msg += f" ({skipped} already promoted, skipped)"
        return msg
