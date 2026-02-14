"""Git hook templates and installation logic for buildlog workflow enforcement."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import yaml

# Pre-commit hook: prevent commits to main/master
PRE_COMMIT_HOOK = """\
#!/bin/sh
# buildlog: prevent direct commits to main/master
branch=$(git branch --show-current)
if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    echo "\\033[31m[buildlog] Direct commits to $branch are not allowed.\\033[0m"
    echo "Create a feature branch: git checkout -b feat/your-feature"
    exit 1
fi
"""

# Post-commit hook: nudge toward buildlog_commit (or block if enforced)
POST_COMMIT_HOOK = """\
#!/bin/sh
# buildlog: remind to use buildlog_commit instead of raw git commit
if [ -z "$BUILDLOG_COMMIT" ]; then
    echo ""
    echo "\\033[33m[buildlog] Tip: use 'buildlog commit -m \"...\"' instead of 'git commit'\\033[0m"
    echo "  buildlog_commit wraps git and auto-logs to your journal entry."
fi
"""

# Pre-commit hook: enforce buildlog_commit (opt-in via BUILDLOG_ENFORCE=1)
# Users toggle this on with: export BUILDLOG_ENFORCE=1
# Or per-project in .envrc / .env / shell profile
ENFORCE_COMMIT_HOOK = """\
#!/bin/sh
# buildlog: block bare git commit when enforcement is enabled
# Set BUILDLOG_ENFORCE=1 to activate (e.g. in .envrc or shell profile)
# buildlog_commit() sets BUILDLOG_COMMIT=1 to bypass this hook.
if [ "${BUILDLOG_ENFORCE:-0}" = "1" ] && [ -z "$BUILDLOG_COMMIT" ]; then
    echo ""
    echo "\\033[31m[buildlog] git commit blocked — enforcement is active.\\033[0m"
    echo "  Use: buildlog commit -m \\"your message\\""
    echo "  Or:  BUILDLOG_COMMIT=1 git commit -m \\"your message\\""
    echo "  To disable: unset BUILDLOG_ENFORCE"
    exit 1
fi
"""

# Marker to identify buildlog-managed hook sections
_HOOK_MARKER = "# buildlog:"

# pre-commit-config.yaml entry for branch protection (string form for tests)
PRE_COMMIT_CONFIG_ENTRY = (
    "  - repo: local\n"
    "    hooks:\n"
    "      - id: prevent-commit-to-main\n"
    '        name: "buildlog: prevent commits to main/master"\n'
    "        entry: bash -c '\n"
    "          branch=$(git branch --show-current);\n"
    '          if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then\n'
    '            echo "[buildlog] Direct commits to $branch not allowed.";\n'
    "            exit 1;\n"
    "          fi'\n"
    "        language: system\n"
    "        always_run: true\n"
    "        pass_filenames: false\n"
)

# Dict form used for proper YAML manipulation in install_hooks()
_PRE_COMMIT_HOOK_DICT: dict = {
    "repo": "local",
    "hooks": [
        {
            "id": "prevent-commit-to-main",
            "name": "buildlog: prevent commits to main/master",
            "entry": (
                "bash -c '"
                "branch=$(git branch --show-current); "
                'if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then '
                'echo "[buildlog] Direct commits to $branch not allowed."; '
                "exit 1; "
                "fi'"
            ),
            "language": "system",
            "always_run": True,
            "pass_filenames": False,
        }
    ],
}


def _make_executable(path: Path) -> None:
    """Add executable permission to a file."""
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def install_hooks(
    project_dir: Path,
    no_hooks: bool = False,
) -> dict:
    """Install buildlog git hooks into a project.

    Strategy:
    1. If .pre-commit-config.yaml exists, append branch protection entry (if missing)
    2. Otherwise, install standalone .git/hooks/pre-commit (chains with existing)
    3. Always install .git/hooks/post-commit nudge (chains with existing)

    Args:
        project_dir: Project root directory.
        no_hooks: Skip hook installation entirely.

    Returns:
        Dict with installed hooks and messages.
    """
    if no_hooks:
        return {"installed": [], "message": "Hook installation skipped (--no-hooks)"}

    installed: list[str] = []
    messages: list[str] = []

    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return {
            "installed": [],
            "message": "Not a git repository — skipping hook installation",
        }

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    # --- Pre-commit: branch protection ---
    pre_commit_config = project_dir / ".pre-commit-config.yaml"
    if pre_commit_config.exists():
        content = pre_commit_config.read_text()
        if "prevent-commit-to-main" not in content:
            # Parse YAML, append our hook entry, write back
            config = yaml.safe_load(content) or {}
            repos = config.get("repos") or []
            repos.append(_PRE_COMMIT_HOOK_DICT)
            config["repos"] = repos
            pre_commit_config.write_text(
                yaml.dump(config, default_flow_style=False, sort_keys=False)
            )
            installed.append("pre-commit-config (branch protection)")
            messages.append(
                "Added branch protection to .pre-commit-config.yaml. "
                "Run 'pre-commit install' to activate."
            )
        else:
            messages.append("Branch protection already in .pre-commit-config.yaml")
    else:
        # Standalone hook
        _install_standalone_hook(
            hooks_dir / "pre-commit", PRE_COMMIT_HOOK, installed, messages
        )

    # --- Post-commit: buildlog_commit nudge ---
    _install_standalone_hook(
        hooks_dir / "post-commit", POST_COMMIT_HOOK, installed, messages
    )

    # --- Pre-commit: enforce buildlog_commit (opt-in via BUILDLOG_ENFORCE=1) ---
    # This chains with the existing pre-commit hook. The env var check means it's
    # a no-op unless the user explicitly opts in.
    _install_standalone_hook(
        hooks_dir / "pre-commit", ENFORCE_COMMIT_HOOK, installed, messages
    )

    return {
        "installed": installed,
        "message": "; ".join(messages) if messages else "Hooks up to date",
    }


def _install_standalone_hook(
    hook_path: Path,
    hook_content: str,
    installed: list[str],
    messages: list[str],
) -> None:
    """Install a standalone git hook, chaining with any existing hook."""
    hook_name = hook_path.name

    if hook_path.exists():
        existing = hook_path.read_text()
        # Use the specific marker line from this hook (e.g. "# buildlog: prevent direct")
        # to allow multiple buildlog hooks in the same file.
        specific_marker = next(
            (
                line.strip()
                for line in hook_content.splitlines()
                if line.strip().startswith(_HOOK_MARKER)
            ),
            _HOOK_MARKER,
        )
        if specific_marker in existing:
            messages.append(f"{hook_name}: buildlog hook already installed")
            return
        # Chain: append our hook after existing content (strip shebang line)
        lines = hook_content.split("\n", 1)
        body = lines[1] if len(lines) > 1 else hook_content
        with open(hook_path, "a") as f:
            f.write("\n" + body)
        installed.append(f"{hook_name} (appended)")
        messages.append(f"{hook_name}: appended buildlog hook to existing")
    else:
        hook_path.write_text(hook_content)
        installed.append(hook_name)
        messages.append(f"{hook_name}: installed")

    _make_executable(hook_path)
