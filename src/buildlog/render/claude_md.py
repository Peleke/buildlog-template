"""Render skills to CLAUDE.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from buildlog.render.tracking import get_promoted_ids, track_promoted
from buildlog.skills import _to_imperative

if TYPE_CHECKING:
    from buildlog.skills import Skill

# Markers to identify the buildlog-managed section in CLAUDE.md
_SECTION_START = "<!-- buildlog:rules:start -->"
_SECTION_END = "<!-- buildlog:rules:end -->"


class ClaudeMdRenderer:
    """Manages a dedicated rules section in CLAUDE.md.

    Uses HTML comment markers to identify the buildlog-managed section.
    On each promote, the section is replaced (not appended) with ALL
    currently promoted rules, preventing duplicates.
    """

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
        """Write skills to CLAUDE.md, replacing the buildlog-managed section.

        On first run, appends a marked section. On subsequent runs, finds
        and replaces the marked section with updated rules. This prevents
        the duplicate accumulation that append-only causes.

        Args:
            skills: List of skills to write.

        Returns:
            Confirmation message.
        """
        if not skills:
            return "No skills to promote"

        # Filter out already-promoted skills for tracking purposes,
        # but we still rebuild the full section from ALL promoted skills
        already_promoted = get_promoted_ids(self.tracking_path)
        new_skills = [s for s in skills if s.id not in already_promoted]

        if not new_skills:
            return f"All {len(skills)} skills already promoted"

        # Track the new skills first so the section includes them
        track_promoted(new_skills, self.tracking_path)

        # Build the section content from ALL skills being promoted now
        # (not just new ones — we replace the entire section)
        all_skills = skills  # All skills passed in this call
        section = self._build_section(all_skills)

        # Read existing file
        if self.path.exists():
            existing = self.path.read_text()
        else:
            existing = ""

        # Replace or append the buildlog section
        if _SECTION_START in existing and _SECTION_END in existing:
            # Replace existing section
            start_idx = existing.index(_SECTION_START)
            end_idx = existing.index(_SECTION_END) + len(_SECTION_END)
            updated = existing[:start_idx] + section + existing[end_idx:]
        elif _SECTION_START in existing:
            # Malformed: start marker but no end. Replace from start to EOF.
            start_idx = existing.index(_SECTION_START)
            updated = existing[:start_idx] + section
        else:
            # No existing section — append
            updated = existing.rstrip() + "\n\n" + section + "\n"

        self.path.write_text(updated)

        skipped = len(skills) - len(new_skills)
        msg = f"Wrote {len(new_skills)} new rules to {self.path} ({len(all_skills)} total in section)"
        if skipped > 0:
            msg += f" ({skipped} already tracked)"
        return msg

    def _build_section(self, skills: list[Skill]) -> str:
        """Build the marked section content."""
        category_titles = {
            "architectural": "Architectural",
            "workflow": "Workflow",
            "tool_usage": "Tool Usage",
            "domain_knowledge": "Domain Knowledge",
        }

        # Group by category
        by_category: dict[str, list[Skill]] = {}
        for skill in skills:
            by_category.setdefault(skill.category, []).append(skill)

        lines = [
            _SECTION_START,
            "",
            f"## Learned Rules (buildlog, updated {datetime.now().strftime('%Y-%m-%d')})",
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

        lines.append(_SECTION_END)
        return "\n".join(lines)
