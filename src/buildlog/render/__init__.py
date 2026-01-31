"""Render adapters for different targets."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from buildlog.render.base import RenderTarget
from buildlog.render.claude_md import ClaudeMdRenderer
from buildlog.render.continue_dev import ContinueRenderer
from buildlog.render.copilot import CopilotRenderer
from buildlog.render.cursor import CursorRenderer
from buildlog.render.settings_json import SettingsJsonRenderer
from buildlog.render.skill import SkillRenderer
from buildlog.render.windsurf import WindsurfRenderer

if TYPE_CHECKING:
    from typing import Any

__all__ = [
    "RenderTarget",
    "ClaudeMdRenderer",
    "SettingsJsonRenderer",
    "SkillRenderer",
    "CursorRenderer",
    "CopilotRenderer",
    "WindsurfRenderer",
    "ContinueRenderer",
    "get_renderer",
    "RENDERERS",
    "RENDER_TARGETS",
]

# Registry of available renderers
# Using RenderTarget Protocol allows easy extension without modifying types
RENDERERS: dict[str, type[RenderTarget]] = {
    "claude_md": ClaudeMdRenderer,
    "settings_json": SettingsJsonRenderer,
    "skill": SkillRenderer,
    "cursor": CursorRenderer,
    "copilot": CopilotRenderer,
    "windsurf": WindsurfRenderer,
    "continue_dev": ContinueRenderer,
}

# Valid target names (useful for CLI choices and type hints)
RENDER_TARGETS = list(RENDERERS.keys())


def get_renderer(
    target: str,
    path: Path | None = None,
    **kwargs: Any,
) -> RenderTarget:
    """Get renderer for target.

    Args:
        target: Target format - one of: claude_md, settings_json, skill,
            cursor, copilot, windsurf, continue_dev.
        path: Optional custom path for the target file.
        **kwargs: Additional arguments passed to the renderer constructor.
            Common kwargs (accepted by all renderers):
                - tracking_path: Path to promoted.json for tracking promoted IDs.
            Skill-specific kwargs:
                - skill_name: Name of the skill directory (default: "buildlog-learned").
                  Must not contain path separators.

    Returns:
        Renderer instance implementing RenderTarget protocol.

    Raises:
        ValueError: If target is not recognized.
    """
    if target not in RENDERERS:
        available = ", ".join(f"'{k}'" for k in RENDERERS.keys())
        raise ValueError(
            f"Unknown render target: '{target}'. Must be one of: {available}"
        )

    renderer_cls = RENDERERS[target]
    return renderer_cls(path=path, **kwargs)  # type: ignore[call-arg]
