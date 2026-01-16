"""Base protocol for render targets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from buildlog.skills import Skill


class RenderTarget(Protocol):
    """Protocol for rendering skills to different targets."""

    def render(self, skills: list[Skill]) -> str:
        """Render skills and write to target.

        Args:
            skills: List of skills to render.

        Returns:
            Confirmation message describing what was written.
        """
        ...
