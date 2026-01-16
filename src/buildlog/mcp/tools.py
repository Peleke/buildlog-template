"""MCP tool implementations for buildlog.

These are thin wrappers around core operations.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Literal

from buildlog.core import diff, promote, reject, status


def buildlog_status(
    buildlog_dir: str = "buildlog",
    min_confidence: Literal["low", "medium", "high"] = "low",
) -> dict:
    """Get current skills extracted from buildlog entries.

    Returns skills grouped by category with confidence scores.
    Use this to see what patterns have emerged from your work.

    Args:
        buildlog_dir: Path to buildlog directory (default: ./buildlog)
        min_confidence: Minimum confidence level to include

    Returns:
        Dictionary with skills by category and summary statistics
    """
    result = status(Path(buildlog_dir), min_confidence)
    return asdict(result)


def buildlog_promote(
    skill_ids: list[str],
    target: Literal["claude_md", "settings_json"] = "claude_md",
    buildlog_dir: str = "buildlog",
) -> dict:
    """Promote skills to your agent's rules.

    Writes selected skills to CLAUDE.md or .claude/settings.json
    so your AI agent will follow these patterns.

    Args:
        skill_ids: List of skill IDs to promote (e.g., ["arch-b0fcb62a1e"])
        target: Where to write rules ("claude_md" or "settings_json")
        buildlog_dir: Path to buildlog directory

    Returns:
        Confirmation with promoted skills
    """
    result = promote(Path(buildlog_dir), skill_ids, target)
    return asdict(result)


def buildlog_reject(
    skill_ids: list[str],
    buildlog_dir: str = "buildlog",
) -> dict:
    """Mark skills as rejected so they won't be suggested again.

    Rejected skills are stored in .buildlog/rejected.json

    Args:
        skill_ids: List of skill IDs to reject
        buildlog_dir: Path to buildlog directory

    Returns:
        Confirmation with rejected skill IDs
    """
    result = reject(Path(buildlog_dir), skill_ids)
    return asdict(result)


def buildlog_diff(
    buildlog_dir: str = "buildlog",
) -> dict:
    """Show skills that haven't been promoted or rejected yet.

    Useful for seeing what's new since your last review.

    Args:
        buildlog_dir: Path to buildlog directory

    Returns:
        Dictionary with pending skills and counts
    """
    result = diff(Path(buildlog_dir))
    return asdict(result)
