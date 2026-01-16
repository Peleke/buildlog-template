"""Render adapters for different targets."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from buildlog.render.base import RenderTarget
from buildlog.render.claude_md import ClaudeMdRenderer
from buildlog.render.settings_json import SettingsJsonRenderer

__all__ = [
    "RenderTarget",
    "ClaudeMdRenderer",
    "SettingsJsonRenderer",
    "get_renderer",
]


def get_renderer(
    target: Literal["claude_md", "settings_json"],
    path: Path | None = None,
) -> ClaudeMdRenderer | SettingsJsonRenderer:
    """Get renderer for target.

    Args:
        target: Target format - "claude_md" or "settings_json".
        path: Optional custom path for the target file.

    Returns:
        Renderer instance.

    Raises:
        ValueError: If target is not recognized.
    """
    if target == "claude_md":
        return ClaudeMdRenderer(path=path)
    elif target == "settings_json":
        return SettingsJsonRenderer(path=path)
    else:
        raise ValueError(f"Unknown render target: {target}. Must be 'claude_md' or 'settings_json'")
