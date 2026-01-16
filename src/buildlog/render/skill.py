"""Render skills to Anthropic Agent Skills format.

Creates .claude/skills/buildlog-learned/SKILL.md that can be loaded
on-demand by Claude Code and other Anthropic tools.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from buildlog.render.tracking import track_promoted

if TYPE_CHECKING:
    from buildlog.skills import Skill


class SkillRenderer:
    """Creates .claude/skills/buildlog-learned/SKILL.md

    This renderer produces Anthropic Agent Skills format, which allows
    for on-demand loading of project-specific patterns by Claude.
    """

    def __init__(
        self,
        path: Path | None = None,
        tracking_path: Path | None = None,
        skill_name: str = "buildlog-learned",
    ):
        """Initialize renderer.

        Args:
            path: Path to SKILL.md file. Defaults to .claude/skills/{skill_name}/SKILL.md.
            tracking_path: Path to promoted.json tracking file.
                Defaults to .buildlog/promoted.json.
            skill_name: Name of the skill directory. Defaults to "buildlog-learned".
                Must not contain path separators or parent references.

        Raises:
            ValueError: If skill_name contains path traversal characters.
        """
        # Security: Validate skill_name to prevent path traversal
        if "/" in skill_name or "\\" in skill_name or ".." in skill_name:
            raise ValueError(
                f"Invalid skill_name: {skill_name!r}. "
                "Must not contain path separators or '..'."
            )
        self.skill_name = skill_name
        self.path = path or Path(f".claude/skills/{skill_name}/SKILL.md")
        self.tracking_path = tracking_path or Path(".buildlog/promoted.json")

    def render(self, skills: list[Skill]) -> str:
        """Render skills to SKILL.md format.

        Args:
            skills: List of skills to render.

        Returns:
            Confirmation message describing what was written.
        """
        if not skills:
            return "No skills to promote"

        # Group by confidence, then category
        by_confidence: dict[str, dict[str, list[Skill]]] = {
            "high": {},
            "medium": {},
            "low": {},
        }
        for skill in skills:
            conf = skill.confidence
            cat = skill.category
            by_confidence[conf].setdefault(cat, []).append(skill)

        # Build SKILL.md content
        categories = sorted(set(s.category for s in skills))
        category_display = ", ".join(self._category_title(c) for c in categories)

        lines = [
            "---",
            f"name: {self.skill_name}",
            f"description: Project-specific patterns learned from development history. "
            f"Use when writing code, making architectural decisions, reviewing PRs, "
            f"or ensuring consistency. Contains {len(skills)} rules across "
            f"{category_display}.",
            "---",
            "",
            "# Learned Patterns",
            "",
            f"*{len(skills)} rules extracted from buildlog entries on "
            f"{datetime.now().strftime('%Y-%m-%d')}*",
            "",
        ]

        # High confidence = Must Follow
        if by_confidence["high"]:
            lines.extend(
                self._render_confidence_section(
                    "Must Follow (High Confidence)",
                    "These patterns have been reinforced multiple times.",
                    by_confidence["high"],
                )
            )

        # Medium confidence = Should Consider
        if by_confidence["medium"]:
            lines.extend(
                self._render_confidence_section(
                    "Should Consider (Medium Confidence)",
                    "These patterns appear frequently but may have exceptions.",
                    by_confidence["medium"],
                )
            )

        # Low confidence = Worth Knowing
        if by_confidence["low"]:
            lines.extend(
                self._render_confidence_section(
                    "Worth Knowing (Low Confidence)",
                    "Emerging patterns worth being aware of.",
                    by_confidence["low"],
                )
            )

        content = "\n".join(lines)

        # Write file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content)

        # Track promoted using shared utility
        track_promoted(skills, self.tracking_path)

        return f"Created skill at {self.path}"

    def _category_title(self, category: str) -> str:
        """Convert category slug to display title."""
        titles = {
            "architectural": "Architectural",
            "workflow": "Workflow",
            "tool_usage": "Tool Usage",
            "domain_knowledge": "Domain Knowledge",
        }
        return titles.get(category, category.replace("_", " ").title())

    def _render_confidence_section(
        self,
        title: str,
        description: str,
        by_category: dict[str, list[Skill]],
    ) -> list[str]:
        """Render a confidence-level section.

        Args:
            title: Section title (e.g., "Must Follow (High Confidence)").
            description: Description of what this confidence level means.
            by_category: Skills grouped by category.

        Returns:
            List of markdown lines for this section.
        """
        lines = [f"## {title}", "", description, ""]

        for category, cat_skills in sorted(by_category.items()):
            cat_title = self._category_title(category)
            lines.append(f"### {cat_title}")
            lines.append("")
            for skill in cat_skills:
                # Don't add confidence prefix - section already indicates confidence
                lines.append(f"- {skill.rule}")
            lines.append("")

        return lines
