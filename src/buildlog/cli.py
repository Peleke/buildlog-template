"""CLI for buildlog - engineering notebook for AI-assisted development."""

import os
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import click

from buildlog.core import diff as core_diff
from buildlog.core import get_rewards, log_reward, promote, reject, status
from buildlog.distill import CATEGORIES, distill_all, format_output
from buildlog.skills import format_skills, generate_skills
from buildlog.stats import calculate_stats, format_dashboard, format_json


def get_template_dir() -> Path | None:
    """Get the template directory from package data.

    Returns the directory containing copier.yml, or None to fall back to GitHub.
    """
    # 1. Check if we're in development (template dir exists relative to package)
    # src/buildlog/cli.py -> src/buildlog -> src -> project root
    pkg_dir = Path(__file__).parent.parent.parent
    dev_copier = pkg_dir / "copier.yml"
    if dev_copier.exists():
        return pkg_dir

    # 2. Check installed location (site-packages/../share/buildlog)
    import sysconfig

    data_dir = Path(sysconfig.get_path("data")) / "share" / "buildlog"
    if (data_dir / "copier.yml").exists():
        return data_dir

    # 3. Fall back to using copier directly from GitHub
    return None


@click.group()
@click.version_option()
def main():
    """buildlog - Engineering notebook for AI-assisted development.

    Capture your work as publishable content. Include the fuckups.
    """
    pass


@main.command()
@click.option("--no-claude-md", is_flag=True, help="Don't update CLAUDE.md")
@click.option("--no-mcp", is_flag=True, help="Don't register MCP server")
@click.option("--no-hooks", is_flag=True, help="Don't install git hooks")
@click.option(
    "--defaults",
    is_flag=True,
    help="Use default values for all prompts (non-interactive)",
)
def init(no_claude_md: bool, no_mcp: bool, no_hooks: bool, defaults: bool):
    """Initialize buildlog in the current directory.

    Sets up the buildlog/ directory with templates and optionally
    adds instructions to CLAUDE.md.

    Use --defaults for non-interactive environments (CI, scripts, agents).
    """
    buildlog_dir = Path("buildlog")

    if buildlog_dir.exists():
        click.echo("buildlog/ directory already exists.", err=True)
        raise SystemExit(1)

    template_dir = get_template_dir()

    if template_dir:
        # Use local template
        click.echo("Initializing buildlog from local template...")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "copier",
                "copy",
                "--trust",
                *(["--defaults"] if defaults else []),
                *(["--data", "update_claude_md=false"] if no_claude_md else []),
                str(template_dir),
                ".",
            ],
        )
    else:
        # Fall back to GitHub
        click.echo("Initializing buildlog from GitHub...")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "copier",
                "copy",
                "--trust",
                *(["--defaults"] if defaults else []),
                *(["--data", "update_claude_md=false"] if no_claude_md else []),
                "gh:Peleke/buildlog-template",
                ".",
            ],
        )

    # Verify the buildlog directory was actually created
    if not buildlog_dir.exists():
        click.echo("Failed to initialize buildlog.", err=True)
        raise SystemExit(1)

    # Ensure .buildlog/ directory exists (copier skips dot-prefixed paths)
    dot_buildlog = buildlog_dir / ".buildlog"
    dot_buildlog.mkdir(exist_ok=True)
    (dot_buildlog / "seeds").mkdir(exist_ok=True)

    # Update CLAUDE.md if it exists and user didn't opt out
    if not no_claude_md:
        claude_md = Path("CLAUDE.md")
        if claude_md.exists():
            content = claude_md.read_text()
            if (
                "## buildlog Integration" not in content
                and "## Build Journal" not in content
            ):
                try:
                    from buildlog.constants import CLAUDE_MD_BUILDLOG_SECTION

                    section = CLAUDE_MD_BUILDLOG_SECTION
                except ImportError:
                    section = (
                        "\n## Build Journal\n\n"
                        "After completing significant work (features, debugging "
                        "sessions, deployments,\n"
                        "2+ hour focused sessions), write a build journal entry.\n\n"
                        "**Location:** `buildlog/YYYY-MM-DD-{slug}.md`\n"
                        "**Template:** `buildlog/_TEMPLATE.md`\n"
                    )
                with open(claude_md, "a") as f:
                    f.write(section)
                click.echo("Added buildlog Integration section to CLAUDE.md")

            # Inject workflow section if not present
            from buildlog.constants import (
                _WORKFLOW_SECTION_START,
                CLAUDE_MD_WORKFLOW_SECTION,
            )

            content = claude_md.read_text()
            if _WORKFLOW_SECTION_START not in content:
                with open(claude_md, "a") as f:
                    f.write("\n" + CLAUDE_MD_WORKFLOW_SECTION + "\n")
                click.echo("Added workflow section to CLAUDE.md")

    # Register MCP server unless opted out
    if not no_mcp:
        _init_mcp(skip_confirm=defaults)

    # Install git hooks unless opted out
    from buildlog.hooks import install_hooks

    hook_result = install_hooks(Path(".").resolve(), no_hooks=no_hooks)
    if hook_result["installed"]:
        for hook_name in hook_result["installed"]:
            click.echo(f"Installed git hook: {hook_name}")

    # Run verify at end of init
    from buildlog.core import verify_workflow

    verify_result = verify_workflow(
        project_dir=Path(".").resolve(), buildlog_dir=buildlog_dir
    )

    click.echo("\n✓ buildlog initialized!")
    click.echo()
    click.echo("How it works:")
    click.echo("  1. Write entries     buildlog new my-feature (or --quick)")
    click.echo("  2. Extract rules     buildlog skills")
    click.echo("  3. Promote to agent  buildlog promote <id> --target cursor")
    click.echo("  4. Measure learning  buildlog overview")
    click.echo()
    click.echo(
        "Targets: claude_md, cursor, copilot, windsurf, continue_dev, settings_json, skill"
    )

    if verify_result.warnings:
        click.echo()
        click.echo("Warnings:")
        for w in verify_result.warnings:
            click.echo(f"  [WARN] {w.message}")

    click.echo()
    click.echo("Start now: buildlog new my-first-task --quick")


def _init_mcp(
    settings_path: Path | None = None,
    global_mode: bool = False,
    skip_confirm: bool = False,
) -> None:
    """Register buildlog as an MCP server in settings.json.

    Args:
        settings_path: Path to settings.json. Defaults to .claude/settings.json
        global_mode: If True, also writes usage instructions to ~/.claude/CLAUDE.md
        skip_confirm: If True, skip confirmation prompts (non-interactive mode)
    """
    import json as json_module

    if settings_path is None:
        settings_path = Path(".claude") / "settings.json"

    location = "~/.claude.json" if global_mode else ".claude/settings.json"

    try:
        if settings_path.exists():
            try:
                data = json_module.loads(settings_path.read_text())
            except json_module.JSONDecodeError:
                click.echo(
                    f"Warning: {location} is malformed, skipping MCP registration",
                    err=True,
                )
                return
        else:
            data = {}

        if "mcpServers" not in data:
            data["mcpServers"] = {}

        # Get full path to buildlog-mcp. Claude Code's subprocess doesn't have
        # ~/.local/bin in PATH, so we need the absolute path.
        # For global mode, prefer ~/.local/bin (where pipx/uv tool installs).
        global_bin = Path.home() / ".local" / "bin" / "buildlog-mcp"
        if global_mode and global_bin.exists():
            mcp_command = str(global_bin)
        else:
            mcp_command = shutil.which("buildlog-mcp") or "buildlog-mcp"
        correct_config = {"command": mcp_command, "args": []}
        current_config = data["mcpServers"].get("buildlog")

        if current_config == correct_config:
            click.echo(f"buildlog MCP server already registered in {location}")
        else:
            # Prompt for confirmation before modifying disk
            if not skip_confirm:
                action = "Update" if current_config else "Create/modify"
                if not click.confirm(f"{action} {location}?"):
                    click.echo("Aborted.")
                    return

            data["mcpServers"]["buildlog"] = correct_config
            if not global_mode:
                settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json_module.dumps(data, indent=2) + "\n")
            if current_config is None:
                click.echo(f"Registered buildlog MCP server in {location}")
            else:
                click.echo(f"Updated buildlog MCP server config in {location}")

        # In global mode, also write/update ~/.claude/CLAUDE.md with usage instructions
        if global_mode:
            _init_global_claude_md(Path.home() / ".claude", skip_confirm=skip_confirm)
            click.echo(
                "Claude Code now has buildlog tools + instructions in all projects."
            )

    except Exception as e:
        click.echo(f"Warning: could not register MCP server: {e}", err=True)


def _init_global_claude_md(claude_dir: Path, skip_confirm: bool = False) -> None:
    """Write buildlog usage instructions to ~/.claude/CLAUDE.md.

    Creates or appends to the global CLAUDE.md so Claude knows how to use
    buildlog tools automatically in any project.

    Args:
        claude_dir: Path to ~/.claude directory
        skip_confirm: If True, skip confirmation prompts (non-interactive mode)
    """
    from buildlog.constants import CLAUDE_MD_GLOBAL_SECTION

    claude_md_path = claude_dir / "CLAUDE.md"

    try:
        if claude_md_path.exists():
            content = claude_md_path.read_text()
            # Check if buildlog section already exists
            if "## buildlog" in content:
                click.echo("buildlog instructions already in ~/.claude/CLAUDE.md")
                return
            # Prompt for confirmation before modifying disk
            if not skip_confirm:
                if not click.confirm(
                    "Append buildlog instructions to ~/.claude/CLAUDE.md?"
                ):
                    click.echo("Skipped CLAUDE.md update.")
                    return
            # Append to existing file
            with open(claude_md_path, "a") as f:
                f.write(CLAUDE_MD_GLOBAL_SECTION)
            click.echo("Added buildlog instructions to ~/.claude/CLAUDE.md")
        else:
            # Prompt for confirmation before creating new file
            if not skip_confirm:
                if not click.confirm(
                    "Create ~/.claude/CLAUDE.md with buildlog instructions?"
                ):
                    click.echo("Skipped CLAUDE.md creation.")
                    return
            # Create new file with header
            claude_dir.mkdir(parents=True, exist_ok=True)
            header = "# Global Claude Instructions\n\nThese instructions apply to all projects.\n"
            claude_md_path.write_text(header + CLAUDE_MD_GLOBAL_SECTION)
            click.echo("Created ~/.claude/CLAUDE.md with buildlog instructions")
    except Exception as e:
        click.echo(f"Warning: could not write CLAUDE.md: {e}", err=True)


@main.command("init-mcp")
@click.option(
    "--global",
    "global_",
    is_flag=True,
    help="Register globally in ~/.claude.json (works in any project)",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Skip confirmation prompts (non-interactive mode)",
)
def init_mcp(global_: bool, yes: bool):
    """Register buildlog as an MCP server for Claude Code.

    Creates or updates .claude/settings.json with the buildlog MCP
    server configuration. Idempotent — safe to run multiple times.

    Use --global to register in ~/.claude.json so buildlog
    tools are available in every project without per-project init.

    Examples:

        buildlog init-mcp              # local (current project)
        buildlog init-mcp --global     # global (all projects)
        buildlog init-mcp --global -y  # global, skip prompts
    """
    if global_:
        settings_path = Path.home() / ".claude.json"
        _init_mcp(settings_path=settings_path, global_mode=True, skip_confirm=yes)
    else:
        _init_mcp(skip_confirm=yes)


@main.command("mcp-test")
def mcp_test():
    """Verify the MCP server starts and all tools are registered.

    Checks that the buildlog-mcp server can be imported and lists
    all registered tools. Exits 0 if all 33 tools are found, 1 otherwise.

    Examples:

        buildlog mcp-test
    """
    try:
        from buildlog.mcp.server import mcp as mcp_server
    except ImportError:
        click.echo("MCP not installed. Run: pip install buildlog", err=True)
        raise SystemExit(1)

    try:
        # FastMCP stores tools internally
        tools = mcp_server._tool_manager._tools
        tool_names = sorted(tools.keys())
    except AttributeError:
        # Fallback: try to count via the public API pattern
        click.echo("Warning: could not inspect tools via internal API", err=True)
        tool_names = []

    expected = 32
    click.echo(f"buildlog MCP server: {len(tool_names)} tools registered")
    for name in tool_names:
        click.echo(f"  {name}")

    if len(tool_names) >= expected:
        click.echo(f"\nAll {expected} tools registered.")
        raise SystemExit(0)
    else:
        click.echo(f"\nExpected {expected} tools, found {len(tool_names)}.", err=True)
        raise SystemExit(1)


@main.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def overview(output_json: bool):
    """Show the full state of your buildlog at a glance.

    Entries, skills, promoted rules, experiments — everything in one view.
    Works even without buildlog init (shows uninitialized state).

    Examples:

        buildlog overview
        buildlog overview --json
    """
    import json as json_module

    buildlog_dir = Path("buildlog")

    # Handle uninitialized state gracefully
    if not buildlog_dir.exists():
        result = {
            "initialized": False,
            "entries": 0,
            "skills": {
                "total": 0,
                "by_confidence": {},
                "promoted": 0,
                "rejected": 0,
                "pending": 0,
            },
            "active_session": None,
            "render_targets": [],
            "message": "buildlog not initialized. Run 'buildlog init' to enable full features.",
        }
        if output_json:
            click.echo(json_module.dumps(result, indent=2))
        else:
            click.echo("buildlog overview")
            click.echo("=" * 40)
            click.echo("  Status:      Not initialized")
            click.echo()
            click.echo("Get started:")
            click.echo("  buildlog init --defaults    # Initialize buildlog")
            click.echo()
            click.echo("Or use globally without init:")
            click.echo("  buildlog init-mcp --global  # Register MCP server globally")
            click.echo(
                "  buildlog gauntlet list      # Review personas work without init"
            )
        return

    # Count entries
    entries = sorted(buildlog_dir.glob("20??-??-??-*.md"))

    # Try to get skills
    try:
        skill_set = generate_skills(buildlog_dir)
        total_skills = skill_set.total_skills
        by_confidence = {"high": 0, "medium": 0, "low": 0}
        for cat_skills in skill_set.skills.values():
            for s in cat_skills:
                by_confidence[s.confidence] += 1
    except Exception:
        total_skills = 0
        by_confidence = {"high": 0, "medium": 0, "low": 0}

    # Promoted/rejected counts
    promoted_path = buildlog_dir / ".buildlog" / "promoted.json"
    rejected_path = buildlog_dir / ".buildlog" / "rejected.json"
    promoted_count = 0
    rejected_count = 0
    if promoted_path.exists():
        try:
            data = json_module.loads(promoted_path.read_text())
            promoted_count = len(data.get("skill_ids", []))
        except (json_module.JSONDecodeError, OSError):
            pass
    if rejected_path.exists():
        try:
            data = json_module.loads(rejected_path.read_text())
            rejected_count = len(data.get("skill_ids", []))
        except (json_module.JSONDecodeError, OSError):
            pass

    # Active session?
    active_session_path = buildlog_dir / ".buildlog" / "active_session.json"
    active_session = None
    if active_session_path.exists():
        try:
            active_session = json_module.loads(active_session_path.read_text())
        except (json_module.JSONDecodeError, OSError):
            pass

    # Render targets with files
    from buildlog.render import RENDERERS

    result = {
        "initialized": True,
        "entries": len(entries),
        "skills": {
            "total": total_skills,
            "by_confidence": by_confidence,
            "promoted": promoted_count,
            "rejected": rejected_count,
            "pending": total_skills - promoted_count - rejected_count,
        },
        "active_session": active_session.get("id") if active_session else None,
        "render_targets": list(RENDERERS.keys()),
    }

    if output_json:
        click.echo(json_module.dumps(result, indent=2))
    else:
        click.echo("buildlog overview")
        click.echo("=" * 40)
        click.echo(f"  Entries:     {len(entries)}")
        click.echo(f"  Skills:      {total_skills}")
        if total_skills > 0:
            conf_parts = [f"{k}={v}" for k, v in by_confidence.items() if v > 0]
            click.echo(f"    confidence: {', '.join(conf_parts)}")
        click.echo(f"  Promoted:    {promoted_count}")
        click.echo(f"  Rejected:    {rejected_count}")
        pending = total_skills - promoted_count - rejected_count
        if pending > 0:
            click.echo(f"  Pending:     {pending}")
        if active_session:
            click.echo(f"  Session:     {active_session.get('id', '?')} (active)")
        click.echo()

        if len(entries) == 0:
            click.echo("Get started:")
            click.echo("  buildlog new my-first-task        # Full template")
            click.echo("  buildlog new my-first-task --quick # Short template")
        elif total_skills == 0:
            click.echo("Next steps:")
            click.echo(
                "  buildlog skills                    # Extract rules from entries"
            )
        elif promoted_count == 0:
            click.echo("Next steps:")
            click.echo("  buildlog status                    # See extracted skills")
            click.echo("  buildlog promote <id> --target cursor  # Push to your agent")
        else:
            click.echo("Targets: " + ", ".join(RENDERERS.keys()))


@main.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option(
    "--fix",
    is_flag=True,
    help="Attempt to fix issues (inject workflow section into CLAUDE.md)",
)
def verify(output_json: bool, fix: bool):
    """Verify that the buildlog workflow is correctly set up.

    Checks: buildlog/ exists, CLAUDE.md has workflow section, MCP registered,
    not on main branch, pre-commit hooks installed.

    Examples:

        buildlog verify
        buildlog verify --json
        buildlog verify --fix
    """
    import json as json_module
    from dataclasses import asdict

    from buildlog.core import verify_workflow

    project_dir = Path(".").resolve()
    buildlog_dir = project_dir / "buildlog"

    result = verify_workflow(project_dir=project_dir, buildlog_dir=buildlog_dir)

    if fix and not result.ok:
        _apply_workflow_fixes(project_dir, result)
        # Re-run after fixes
        result = verify_workflow(project_dir=project_dir, buildlog_dir=buildlog_dir)

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo("buildlog verify")
        click.echo("=" * 40)
        for check in result.passed:
            click.echo(f"  [PASS] {check.message}")
        for check in result.warnings:
            click.echo(f"  [WARN] {check.message}")
        for check in result.failed:
            click.echo(f"  [FAIL] {check.message}")
        click.echo()
        click.echo(f"  {result.summary}")
        if not result.ok:
            click.echo()
            click.echo("Run 'buildlog verify --fix' to attempt automatic fixes.")


def _apply_workflow_fixes(project_dir: Path, result) -> None:
    """Attempt to fix failed verify checks."""
    from buildlog.constants import CLAUDE_MD_WORKFLOW_SECTION

    for check in result.failed:
        if check.name == "workflow_section":
            claude_md = project_dir / "CLAUDE.md"
            if claude_md.exists():
                content = claude_md.read_text()
                content = content.rstrip() + "\n\n" + CLAUDE_MD_WORKFLOW_SECTION + "\n"
                claude_md.write_text(content)
                click.echo("  [FIX] Injected workflow section into CLAUDE.md")
            else:
                claude_md.write_text(
                    "# Development Guidelines\n\n" + CLAUDE_MD_WORKFLOW_SECTION + "\n"
                )
                click.echo("  [FIX] Created CLAUDE.md with workflow section")


@main.command()
@click.argument("slug")
@click.option(
    "--date", "-d", "entry_date", default=None, help="Date for entry (YYYY-MM-DD)"
)
@click.option(
    "--quick",
    is_flag=True,
    help="Use the short template (good for small tasks)",
)
def new(slug: str, entry_date: str | None, quick: bool):
    """Create a new buildlog entry.

    SLUG is a short identifier for the entry (e.g., 'auth-api', 'bugfix-login').

    Examples:

        buildlog new auth-api
        buildlog new bugfix-login --quick
        buildlog new runpod-deploy --date 2026-01-15
    """
    buildlog_dir = Path("buildlog")
    template_name = "_TEMPLATE_QUICK.md" if quick else "_TEMPLATE.md"
    template_file = buildlog_dir / template_name

    # Fall back to full template if quick template doesn't exist
    if quick and not template_file.exists():
        template_file = buildlog_dir / "_TEMPLATE.md"

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    if not template_file.exists():
        click.echo(
            "No _TEMPLATE.md found in buildlog/. Run 'buildlog init' first.", err=True
        )
        raise SystemExit(1)

    # Determine date
    if entry_date:
        try:
            # Validate date format AND range (month 1-12, day 1-31)
            parsed = datetime.strptime(entry_date, "%Y-%m-%d").date()
            date_str = parsed.isoformat()
        except ValueError:
            click.echo("Invalid date. Use YYYY-MM-DD with valid values.", err=True)
            raise SystemExit(1)
    else:
        date_str = date.today().isoformat()

    # Sanitize slug
    safe_slug = slug.lower().replace(" ", "-").replace("_", "-")
    safe_slug = "".join(c for c in safe_slug if c.isalnum() or c == "-")

    # Create entry
    entry_name = f"{date_str}-{safe_slug}.md"
    entry_path = buildlog_dir / entry_name

    if entry_path.exists():
        click.echo(f"Entry already exists: {entry_path}", err=True)
        raise SystemExit(1)

    # Copy template
    shutil.copy(template_file, entry_path)

    # Replace placeholder date in the new file
    content = entry_path.read_text()
    content = content.replace("[YYYY-MM-DD]", date_str)
    entry_path.write_text(content)

    click.echo(f"✓ Created {entry_path}")
    click.echo(f"\nOpen it: $EDITOR {entry_path}")


@main.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.option(
    "--slug",
    "-s",
    default=None,
    help="Entry slug (default: derived from branch name)",
)
@click.option(
    "--entry",
    "-e",
    type=click.Path(),
    default=None,
    help="Explicit entry file to append to",
)
@click.option(
    "--no-entry",
    is_flag=True,
    help="Skip buildlog entry update (just run git commit)",
)
@click.pass_context
def commit(ctx, slug: str | None, entry: str | None, no_entry: bool):
    """Commit code and update the buildlog entry in one step.

    Wraps `git commit` and appends commit context to today's buildlog
    entry. If no entry exists for today, creates one automatically.

    All unknown options/arguments are passed through to git commit.

    Examples:

        buildlog commit -m "feat: add LLM extractor"
        buildlog commit --slug llm-extractor -m "feat: add LLM extractor"
        buildlog commit --no-entry -m "chore: formatting"
    """
    buildlog_dir = Path("buildlog")

    # Build git commit command — extra args are passed through from Click context
    git_cmd = ["git", "commit", *ctx.args]

    # Run git commit first
    result = subprocess.run(git_cmd, capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)

    if result.returncode != 0:
        raise SystemExit(result.returncode)

    if no_entry or not buildlog_dir.exists():
        return

    # Get commit info from what we just committed
    try:
        commit_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        commit_msg = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        # diff-tree needs special handling for root commit
        diff_result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            capture_output=True,
            text=True,
        )
        if diff_result.returncode == 0 and diff_result.stdout.strip():
            files_changed = diff_result.stdout.strip()
        else:
            # Root commit fallback
            files_changed = subprocess.run(
                ["git", "diff", "--name-only", "--cached", "HEAD~1"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if not files_changed:
                # Truly initial commit — list all tracked files
                files_changed = subprocess.run(
                    ["git", "ls-tree", "--name-only", "-r", "HEAD"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
    except subprocess.CalledProcessError:
        click.echo("Warning: could not read commit info", err=True)
        return

    # Resolve entry file
    today = date.today().isoformat()
    entry_path = _resolve_entry_path(buildlog_dir, today, slug, entry)

    # Append commit block
    commit_block = f"\n### `{commit_hash}` — {commit_msg}\n\n"
    if files_changed:
        file_list = files_changed.split("\n")
        commit_block += "Files:\n"
        for f in file_list[:20]:  # cap at 20 to avoid noise
            commit_block += f"- `{f}`\n"
        if len(file_list) > 20:
            commit_block += f"- ...and {len(file_list) - 20} more\n"
    commit_block += "\n"

    # Ensure commits section exists, append to it
    if entry_path.exists():
        content = entry_path.read_text()
        if "## Commits" not in content:
            content = content.rstrip() + "\n\n## Commits\n"
        content += commit_block
    else:
        # Auto-create minimal entry
        content = f"# {today}\n\n## Commits\n{commit_block}"

    entry_path.write_text(content)
    click.echo(f"buildlog: updated {entry_path}")


def _resolve_entry_path(
    buildlog_dir: Path, today: str, slug: str | None, explicit: str | None
) -> Path:
    """Find or create the entry path for today."""
    if explicit:
        return Path(explicit)

    # Check for existing entry with today's date
    existing = list(buildlog_dir.glob(f"{today}-*.md"))
    if existing:
        return existing[0]

    # Derive slug from branch name if not provided
    if slug is None:
        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            # Clean branch name into slug
            slug = branch.split("/")[-1]  # strip prefix like feat/
            slug = slug.lower().replace("_", "-")
            slug = "".join(c for c in slug if c.isalnum() or c == "-")
        except subprocess.CalledProcessError:
            slug = "session"

    if not slug:
        slug = "session"

    return buildlog_dir / f"{today}-{slug}.md"


@main.command("list")
def list_entries():
    """List all buildlog entries."""
    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    entries = sorted(
        buildlog_dir.glob("20??-??-??-*.md"),
        reverse=True,  # Most recent first
    )

    if not entries:
        click.echo("No entries yet. Create one with: buildlog new my-feature")
        return

    click.echo(f"Found {len(entries)} entries:\n")
    for entry in entries:
        # Extract title from first line if possible
        try:
            first_line = entry.read_text().split("\n")[0]
            title = (
                first_line.replace("# Build Journal: ", "").replace("# ", "").strip()
            )
            if title == "[TITLE]":
                title = "(untitled)"
        except Exception:
            title = "(unreadable)"

        click.echo(f"  {entry.name}")
        click.echo(f"    {title}\n")


@main.command()
def update():
    """Update buildlog templates to latest version."""
    template_dir = get_template_dir()

    if template_dir:
        click.echo("Updating from local template...")
        try:
            subprocess.run(
                [sys.executable, "-m", "copier", "update", "--trust"], check=True
            )
        except subprocess.CalledProcessError:
            click.echo(
                "Failed to update. Try running 'copier update' directly.", err=True
            )
            raise SystemExit(1)
    else:
        click.echo("Updating from GitHub...")
        try:
            subprocess.run(
                [sys.executable, "-m", "copier", "update", "--trust"], check=True
            )
        except subprocess.CalledProcessError:
            click.echo(
                "Failed to update. Try running 'copier update' directly.", err=True
            )
            raise SystemExit(1)

    click.echo("\n✓ buildlog updated!")


@main.command()
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "yaml"]),
    default="json",
    help="Output format",
)
@click.option(
    "--since",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Only include entries from this date onward (YYYY-MM-DD)",
)
@click.option(
    "--category",
    type=click.Choice(CATEGORIES),
    help="Filter to a specific category",
)
@click.option(
    "--llm",
    is_flag=True,
    help="Use LLM-backed extraction (Ollama/Anthropic, falls back to regex)",
)
def distill(
    output: str | None,
    fmt: str,
    since: datetime | None,
    category: str | None,
    llm: bool,
):
    """Extract patterns from all buildlog entries.

    Parses the Improvements section of each buildlog entry and aggregates
    insights into structured output (JSON or YAML). Returns empty result if not initialized.

    Examples:

        buildlog distill                       # JSON to stdout
        buildlog distill -o patterns.json      # Write to file
        buildlog distill --format yaml         # YAML output
        buildlog distill --since 2026-01-01    # Filter by date
        buildlog distill --category workflow   # Filter by category
    """
    import json as json_module

    buildlog_dir = Path("buildlog")

    # Handle uninitialized state gracefully
    if not buildlog_dir.exists():
        empty_result = {
            "initialized": False,
            "patterns": [],
            "statistics": {"total_patterns": 0, "total_entries": 0},
            "message": "buildlog not initialized",
        }
        if fmt == "json":
            click.echo(json_module.dumps(empty_result, indent=2))
        else:
            click.echo(
                "# buildlog not initialized - run 'buildlog init' first\npatterns: []"
            )
        return

    # Convert datetime to date if provided
    since_date = since.date() if since else None

    # Run distillation
    try:
        result = distill_all(
            buildlog_dir, since=since_date, category_filter=category, llm=llm
        )
    except Exception as e:
        click.echo(f"Failed to distill entries: {e}", err=True)
        raise SystemExit(1)

    # Format output
    try:
        formatted = format_output(result, fmt)  # type: ignore[arg-type]
    except ImportError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    # Write output
    if output:
        output_path = Path(output)
        try:
            output_path.write_text(formatted, encoding="utf-8")
            click.echo(
                f"Wrote {result.statistics.get('total_patterns', 0)} patterns to {output_path}"
            )
        except Exception as e:
            click.echo(f"Failed to write output: {e}", err=True)
            raise SystemExit(1)
    else:
        click.echo(formatted)


@main.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option(
    "--detailed", is_flag=True, help="Show detailed breakdown including top sources"
)
@click.option(
    "--since",
    "since_date",
    default=None,
    help="Only include entries since date (YYYY-MM-DD)",
)
def stats(output_json: bool, detailed: bool, since_date: str | None):
    """Show buildlog statistics and analytics.

    Provides insights on buildlog usage, coverage, and quality.
    Returns empty stats if not initialized.

    Examples:

        buildlog stats              # Terminal dashboard
        buildlog stats --json       # JSON output for scripts
        buildlog stats --detailed   # Include top sources
        buildlog stats --since 2026-01-01
    """
    import json as json_module

    buildlog_dir = Path("buildlog")

    # Handle uninitialized state gracefully
    if not buildlog_dir.exists():
        empty_stats = {
            "initialized": False,
            "total_entries": 0,
            "total_patterns": 0,
            "categories": {},
            "date_range": None,
            "message": "buildlog not initialized",
        }
        if output_json:
            click.echo(json_module.dumps(empty_stats, indent=2))
        else:
            click.echo("buildlog stats")
            click.echo("=" * 40)
            click.echo("  Not initialized. Run 'buildlog init' first.")
        return

    # Parse since date if provided
    parsed_since = None
    if since_date:
        try:
            parsed_since = datetime.strptime(since_date, "%Y-%m-%d").date()
        except ValueError:
            click.echo("Invalid date format. Use YYYY-MM-DD.", err=True)
            raise SystemExit(1)

    # Calculate stats
    stats_data = calculate_stats(buildlog_dir, since_date=parsed_since)

    # Output in requested format
    if output_json:
        click.echo(format_json(stats_data))
    else:
        click.echo(format_dashboard(stats_data, detailed=detailed))


@main.command()
@click.option(
    "--port", default=2718, type=int, help="Port for marimo server (default: 2718)"
)
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
def viz(port: int, no_browser: bool):
    """Open the interactive buildlog dashboard in your browser.

    Launches a marimo notebook with live visualizations of your
    learning loop data: rewards, sessions, bandit posteriors, and more.

    Examples:

        buildlog viz                # Open dashboard
        buildlog viz --port 8080    # Custom port
        buildlog viz --no-browser   # Don't auto-open browser
    """
    import subprocess
    import sys

    buildlog_dir = Path("buildlog")
    notebook = Path(__file__).parent.parent.parent / "notebooks" / "dashboard.py"

    # Also check installed package location
    if not notebook.exists():
        # Try relative to CWD
        notebook = Path("notebooks") / "dashboard.py"

    if not notebook.exists():
        click.echo("Dashboard notebook not found.", err=True)
        click.echo("Expected at: notebooks/dashboard.py", err=True)
        raise SystemExit(1)

    env = {**os.environ, "BUILDLOG_DIR": str(buildlog_dir.resolve())}

    cmd = [sys.executable, "-m", "marimo", "run", str(notebook), "--port", str(port)]
    if no_browser:
        cmd.append("--headless")

    click.echo(f"Launching buildlog dashboard on port {port}...")
    click.echo(f"Data source: {buildlog_dir.resolve()}")

    try:
        subprocess.run(cmd, env=env, check=True)
    except KeyboardInterrupt:
        click.echo("\nDashboard stopped.")
    except FileNotFoundError:
        click.echo("marimo not found. Install with: pip install marimo", err=True)
        raise SystemExit(1)


@main.command()
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["yaml", "json", "markdown", "rules", "settings"]),
    default="yaml",
    help="Output format: yaml, json, markdown, rules (CLAUDE.md), settings (.claude/settings.json)",
)
@click.option(
    "--min-frequency",
    type=int,
    default=1,
    help="Only include skills seen at least this many times",
)
@click.option(
    "--since",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Only include entries from this date onward (YYYY-MM-DD)",
)
@click.option(
    "--embeddings",
    type=click.Choice(["token", "sentence-transformers", "openai"]),
    default=None,
    help="Embedding backend for semantic deduplication",
)
@click.option(
    "--llm",
    is_flag=True,
    help="Use LLM for extraction, canonical selection, and scoring (Ollama/Anthropic)",
)
def skills(
    output: str | None,
    fmt: str,
    min_frequency: int,
    since: datetime | None,
    embeddings: str | None,
    llm: bool = False,
):
    """Generate agent-consumable skills from buildlog patterns.

    Transforms distilled patterns into actionable rules with deduplication,
    confidence scoring, and stable IDs. Returns empty set if not initialized.

    Examples:

        buildlog skills                        # YAML to stdout
        buildlog skills -o skills.yml          # Write to file
        buildlog skills --format markdown      # For CLAUDE.md injection
        buildlog skills --min-frequency 2      # Only repeated patterns
        buildlog skills --embeddings sentence-transformers  # Semantic dedup

    Embedding backends:
        token (default): Fast, no dependencies, token-based similarity
        sentence-transformers: Local semantic embeddings (pip install buildlog[embeddings])
        openai: OpenAI API embeddings (requires OPENAI_API_KEY)
    """
    buildlog_dir = Path("buildlog")

    # Handle uninitialized state gracefully - return empty skill set
    if not buildlog_dir.exists():
        if fmt == "json":
            import json as json_module

            click.echo(
                json_module.dumps(
                    {
                        "initialized": False,
                        "skills": {},
                        "total_skills": 0,
                        "message": "buildlog not initialized",
                    },
                    indent=2,
                )
            )
        elif fmt == "yaml":
            click.echo(
                "# buildlog not initialized - run 'buildlog init' first\nskills: {}\ntotal_skills: 0"
            )
        else:
            click.echo(
                "No buildlog/ directory found. Run 'buildlog init' to extract skills."
            )
        return

    # Convert datetime to date if provided
    since_date = since.date() if since else None

    # Generate skills
    try:
        skill_set = generate_skills(
            buildlog_dir,
            min_frequency=min_frequency,
            since_date=since_date,
            embedding_backend=embeddings,
            llm=llm,
        )
    except ImportError as e:
        click.echo(f"Missing dependency: {e}", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"Failed to generate skills: {e}", err=True)
        raise SystemExit(1)

    # Format output
    try:
        formatted = format_skills(skill_set, fmt)  # type: ignore[arg-type]
    except ImportError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    # Write output
    if output:
        output_path = Path(output)
        try:
            output_path.write_text(formatted, encoding="utf-8")
            click.echo(
                f"Wrote {skill_set.total_skills} skills to {output_path} "
                f"(from {skill_set.source_entries} entries)"
            )
        except Exception as e:
            click.echo(f"Failed to write output: {e}", err=True)
            raise SystemExit(1)
    else:
        click.echo(formatted)


@main.command()
@click.argument("outcome", type=click.Choice(["accepted", "revision", "rejected"]))
@click.option(
    "--distance",
    "-d",
    type=float,
    help="Revision distance (0-1, 0=minor tweak, 1=complete redo)",
)
@click.option("--error-class", "-e", help="Category of error (e.g., missing_test)")
@click.option("--notes", "-n", help="Additional notes about the feedback")
@click.option("--rules", "-r", multiple=True, help="Active rule IDs")
@click.option("--session", "-s", help="Session ID to associate with")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def reward(
    outcome: str,
    distance: float | None,
    error_class: str | None,
    notes: str | None,
    rules: tuple[str, ...],
    session: str | None,
    output_json: bool,
):
    """Log a reward signal for the learning loop.

    Used to provide feedback on agent work for bandit learning.

    OUTCOME is one of:
      - accepted: Work was accepted as-is (reward=1.0)
      - revision: Work needed changes (reward=1-distance)
      - rejected: Work was rejected entirely (reward=0.0)

    Examples:

        buildlog reward accepted
        buildlog reward revision --distance 0.3 --error-class missing_test
        buildlog reward rejected --notes "Completely wrong approach"
        buildlog reward accepted --rules arch-123 --rules wf-456
    """
    import json as json_module
    from dataclasses import asdict

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    result = log_reward(
        buildlog_dir,
        outcome=outcome,  # type: ignore[arg-type]
        rules_active=list(rules) if rules else None,
        revision_distance=distance,
        error_class=error_class,
        notes=notes,
        source="cli",
        session_id=session,
    )

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(f"✓ {result.message}")
        click.echo(f"  Reward ID: {result.reward_id}")
        click.echo(f"  Total events: {result.total_events}")


@main.command()
@click.option("--limit", "-n", type=int, help="Limit number of events to show")
@click.option("--session", "-s", help="Filter to events from this session")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def rewards(limit: int | None, session: str | None, output_json: bool):
    """List reward events and summary statistics.

    Shows recent reward events and aggregate statistics useful for
    tracking learning progress.

    Examples:

        buildlog rewards              # Show all with summary
        buildlog rewards --limit 10   # Show 10 most recent
        buildlog rewards --json       # JSON output for scripts
    """
    import json as json_module

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    summary = get_rewards(buildlog_dir, limit=limit, session_id=session)

    if output_json:
        data = {
            "total_events": summary.total_events,
            "accepted": summary.accepted,
            "revisions": summary.revisions,
            "rejected": summary.rejected,
            "mean_reward": summary.mean_reward,
            "events": [e.to_dict() for e in summary.events],
        }
        click.echo(json_module.dumps(data, indent=2))
    else:
        # Summary header
        click.echo("Reward Signal Summary")
        click.echo("=" * 40)
        click.echo(f"Total events:  {summary.total_events}")
        click.echo(f"  Accepted:    {summary.accepted}")
        click.echo(f"  Revisions:   {summary.revisions}")
        click.echo(f"  Rejected:    {summary.rejected}")
        click.echo(f"Mean reward:   {summary.mean_reward:.3f}")
        click.echo()

        if summary.events:
            click.echo("Recent Events")
            click.echo("-" * 40)
            for event in summary.events:
                ts = event.timestamp.strftime("%Y-%m-%d %H:%M")
                outcome_str = event.outcome.upper()
                reward_str = f"r={event.reward_value:.2f}"
                click.echo(f"  [{ts}] {outcome_str} ({reward_str})")
                if event.error_class:
                    click.echo(f"           error_class: {event.error_class}")
                if event.notes:
                    click.echo(f"           notes: {event.notes}")
        else:
            click.echo("No reward events yet.")
            click.echo("Log your first with: buildlog reward accepted")


# -----------------------------------------------------------------------------
# Skill Management Commands (status, promote, reject, diff)
# -----------------------------------------------------------------------------


@main.command()
@click.option(
    "--min-confidence",
    type=click.Choice(["low", "medium", "high"]),
    default="low",
    help="Minimum confidence level to include",
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def status_cmd(min_confidence: str, output_json: bool):
    """Show extracted skills by category and confidence.

    Displays all skills extracted from buildlog entries, grouped by category,
    with confidence levels and promotion status. Returns empty state if not initialized.

    Examples:

        buildlog status
        buildlog status --min-confidence medium
        buildlog status --json
    """
    import json as json_module
    from dataclasses import asdict

    buildlog_dir = Path("buildlog")

    # Handle uninitialized state gracefully
    if not buildlog_dir.exists():
        empty_result = {
            "initialized": False,
            "total_skills": 0,
            "total_entries": 0,
            "skills": {},
            "by_confidence": {"high": 0, "medium": 0, "low": 0},
            "promotable_ids": [],
            "error": None,
        }
        if output_json:
            click.echo(json_module.dumps(empty_result, indent=2))
        else:
            click.echo("Skills: 0 total from 0 entries")
            click.echo("  buildlog not initialized. Run 'buildlog init' first.")
        return

    result = status(buildlog_dir, min_confidence=min_confidence)  # type: ignore[arg-type]

    if result.error:
        click.echo(f"Error: {result.error}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(
            f"Skills: {result.total_skills} total from {result.total_entries} entries"
        )
        conf_str = ", ".join(
            f"{k}={v}" for k, v in result.by_confidence.items() if v > 0
        )
        click.echo(f"  By confidence: {conf_str}")
        click.echo()
        for category, skills in result.skills.items():
            if not skills:
                continue
            click.echo(f"  {category} ({len(skills)})")
            for s in skills:
                conf = s.get("confidence", "?")
                click.echo(f"    [{conf}] {s['id']}: {s['rule'][:70]}")
        if result.promotable_ids:
            click.echo(f"\nPromotable: {', '.join(result.promotable_ids)}")


# Register with the name "status" (avoiding collision with Python builtin)
status_cmd.name = "status"


@main.command()
@click.argument("skill_ids", nargs=-1, required=True)
@click.option(
    "--target",
    type=click.Choice(
        [
            "claude_md",
            "settings_json",
            "skill",
            "cursor",
            "copilot",
            "windsurf",
            "continue_dev",
        ]
    ),
    default="claude_md",
    help="Where to write promoted rules",
)
@click.option(
    "--target-path", type=click.Path(), help="Custom path for the target file"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def promote_cmd(
    skill_ids: tuple[str, ...], target: str, target_path: str | None, output_json: bool
):
    """Promote skills to agent rules.

    Surface high-confidence skills to your agent via CLAUDE.md, settings.json,
    or Agent Skills.

    Examples:

        buildlog promote arch-b0fcb62a1e
        buildlog promote arch-123 wf-456 --target skill
        buildlog promote arch-123 --target settings_json --target-path .claude/settings.json
    """
    import json as json_module
    from dataclasses import asdict

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    result = promote(
        buildlog_dir,
        skill_ids=list(skill_ids),
        target=target,  # type: ignore[arg-type]
        target_path=Path(target_path) if target_path else None,
    )

    if result.error:
        click.echo(f"Error: {result.error}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(f"✓ {result.message}")
        if result.not_found_ids:
            click.echo(f"  Not found: {', '.join(result.not_found_ids)}")


promote_cmd.name = "promote"


@main.command("reject")
@click.argument("skill_ids", nargs=-1, required=True)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def reject_cmd(skill_ids: tuple[str, ...], output_json: bool):
    """Mark skills as rejected (false positives).

    Rejected skills won't be suggested for promotion again.

    Examples:

        buildlog reject arch-b0fcb62a1e
        buildlog reject dk-123 wf-456
    """
    import json as json_module
    from dataclasses import asdict

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    result = reject(buildlog_dir, skill_ids=list(skill_ids))

    if result.error:
        click.echo(f"Error: {result.error}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(f"✓ Rejected {len(result.rejected_ids)} skills")
        click.echo(f"  Total rejected: {result.total_rejected}")


@main.command("diff")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def diff_cmd(output_json: bool):
    """Show skills pending review (not yet promoted or rejected).

    Useful for seeing what's new since the last time you reviewed skills.
    Returns empty diff if not initialized.

    Examples:

        buildlog diff
        buildlog diff --json
    """
    import json as json_module
    from dataclasses import asdict

    buildlog_dir = Path("buildlog")

    # Handle uninitialized state gracefully
    if not buildlog_dir.exists():
        empty_result = {
            "initialized": False,
            "pending": {},
            "total_pending": 0,
            "already_promoted": 0,
            "already_rejected": 0,
            "error": None,
        }
        if output_json:
            click.echo(json_module.dumps(empty_result, indent=2))
        else:
            click.echo("Pending: 0 | Promoted: 0 | Rejected: 0")
            click.echo("  buildlog not initialized. Run 'buildlog init' first.")
        return

    result = core_diff(buildlog_dir)

    if result.error:
        click.echo(f"Error: {result.error}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(
            f"Pending: {result.total_pending} | "
            f"Promoted: {result.already_promoted} | "
            f"Rejected: {result.already_rejected}"
        )
        click.echo()
        for category, skills in result.pending.items():
            if not skills:
                continue
            click.echo(f"  {category} ({len(skills)})")
            for s in skills:
                conf = s.get("confidence", "?")
                click.echo(f"    [{conf}] {s['id']}: {s['rule'][:70]}")


# -----------------------------------------------------------------------------
# Experiment Commands (Session Tracking for Issue #21)
# -----------------------------------------------------------------------------


@main.group()
def experiment():
    """Commands for running learning experiments.

    Track sessions, log mistakes, and measure repeated-mistake rates
    to evaluate buildlog's effectiveness.

    Example workflow:

        buildlog experiment start --error-class missing_test
        # ... do work, log mistakes as you encounter them ...
        buildlog experiment log-mistake --class missing_test --description "..."
        buildlog experiment end
        buildlog experiment report
    """
    pass


@experiment.command("start")
@click.option(
    "--error-class",
    "-e",
    help="Error class being targeted (e.g., 'missing_test')",
)
@click.option("--notes", "-n", help="Notes about this session")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def experiment_start(
    error_class: str | None,
    notes: str | None,
    output_json: bool,
):
    """Start a new experiment session.

    This begins tracking for a learning experiment. Captures the current
    set of active rules to measure learning over time.

    Examples:

        buildlog experiment start
        buildlog experiment start --error-class missing_test
        buildlog experiment start --error-class validation_boundary --notes "Testing edge cases"
    """
    import json as json_module
    from dataclasses import asdict

    from buildlog.core import start_session

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    try:
        result = start_session(buildlog_dir, error_class=error_class, notes=notes)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(f"✓ {result.message}")
        if error_class:
            click.echo(f"  Error class: {error_class}")


@experiment.command("end")
@click.option("--entry-file", "-f", help="Corresponding buildlog entry file")
@click.option("--notes", "-n", help="Additional notes about this session")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def experiment_end(
    entry_file: str | None,
    notes: str | None,
    output_json: bool,
):
    """End the current experiment session.

    Finalizes the session and calculates metrics including:
    - Total mistakes logged
    - Repeated mistakes (from prior sessions)
    - Rules added during session

    Examples:

        buildlog experiment end
        buildlog experiment end --entry-file 2026-01-21.md
        buildlog experiment end --notes "Good session, learned 2 new rules"
    """
    import json as json_module
    from dataclasses import asdict

    from buildlog.core import end_session

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    try:
        result = end_session(buildlog_dir, entry_file=entry_file, notes=notes)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(f"✓ {result.message}")
        click.echo(f"  Duration: {result.duration_minutes} minutes")
        click.echo(
            f"  Mistakes: {result.mistakes_logged} ({result.repeated_mistakes} repeats)"
        )
        click.echo(f"  Rules: {result.rules_at_start} → {result.rules_at_end}")


@experiment.command("log-mistake")
@click.option(
    "--error-class",
    "error_class",
    required=True,
    help="Error class (e.g., 'missing_test', 'validation_boundary')",
)
@click.option(
    "--description",
    "-d",
    required=True,
    help="Description of the mistake",
)
@click.option(
    "--rule",
    "-r",
    "corrected_by_rule",
    help="Rule ID that should have prevented this",
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def experiment_log_mistake(
    error_class: str,
    description: str,
    corrected_by_rule: str | None,
    output_json: bool,
):
    """Log a mistake during the current session.

    Records the mistake and checks if it's a repeat of a prior mistake
    (from earlier sessions). This enables measuring repeated-mistake rates.

    Examples:

        buildlog experiment log-mistake --error-class missing_test -d "Forgot tests"
        buildlog experiment log-mistake --error-class validation -d "No max length" -r val-123
    """
    import json as json_module
    from dataclasses import asdict

    from buildlog.core import log_mistake

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    try:
        result = log_mistake(
            buildlog_dir,
            error_class=error_class,
            description=description,
            corrected_by_rule=corrected_by_rule,
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        if result.was_repeat:
            click.echo(f"⚠ REPEAT: {result.message}")
            click.echo(f"  Similar to: {result.similar_prior}")
        else:
            click.echo(f"✓ {result.message}")


@experiment.command("metrics")
@click.option(
    "--session", "-s", "session_id", help="Specific session ID (or aggregate)"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def experiment_metrics(session_id: str | None, output_json: bool):
    """Show metrics for a session or all sessions.

    Displays mistake rates and rule changes.

    Examples:

        buildlog experiment metrics                           # Aggregate metrics
        buildlog experiment metrics --session session-20260121-140000
    """
    import json as json_module
    from dataclasses import asdict

    from buildlog.core import get_session_metrics

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    try:
        metrics = get_session_metrics(buildlog_dir, session_id=session_id)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json_module.dumps(asdict(metrics), indent=2))
    else:
        click.echo(f"Session Metrics: {metrics.session_id}")
        click.echo("=" * 40)
        click.echo(f"Total mistakes:     {metrics.total_mistakes}")
        click.echo(f"Repeated mistakes:  {metrics.repeated_mistakes}")
        click.echo(f"Repeat rate:        {metrics.repeated_mistake_rate:.1%}")
        click.echo(f"Rules at start:     {metrics.rules_at_start}")
        click.echo(f"Rules at end:       {metrics.rules_at_end}")
        click.echo(f"Rules added:        {metrics.rules_added:+d}")


@experiment.command("report")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def experiment_report(output_json: bool):
    """Generate a comprehensive experiment report.

    Shows summary statistics, per-session breakdown, and error class analysis.

    Examples:

        buildlog experiment report
        buildlog experiment report --json > report.json
    """
    import json as json_module

    from buildlog.core import get_experiment_report

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    report = get_experiment_report(buildlog_dir)

    if output_json:
        click.echo(json_module.dumps(report, indent=2))
    else:
        summary = report["summary"]
        click.echo("Experiment Report")
        click.echo("=" * 50)
        click.echo(f"Total sessions:         {summary['total_sessions']}")
        click.echo(f"Total mistakes:         {summary['total_mistakes']}")
        click.echo(f"Repeated mistakes:      {summary['total_repeated']}")
        click.echo(f"Overall repeat rate:    {summary['overall_repeat_rate']:.1%}")
        click.echo()

        if report["sessions"]:
            click.echo("Per-Session Breakdown")
            click.echo("-" * 50)
            for sess in report["sessions"]:
                rate = sess["repeated_mistake_rate"]
                click.echo(f"  {sess['session_id']}")
                click.echo(
                    f"    Mistakes: {sess['total_mistakes']} ({sess['repeated_mistakes']} repeats, {rate:.0%})"
                )
                click.echo(f"    Rules added: {sess['rules_added']:+d}")
            click.echo()

        if report["error_classes"]:
            click.echo("Error Class Breakdown")
            click.echo("-" * 50)
            for ec, data in report["error_classes"].items():
                rate = data["repeated"] / data["total"] if data["total"] > 0 else 0
                click.echo(
                    f"  {ec}: {data['total']} mistakes ({data['repeated']} repeats, {rate:.0%})"
                )


# -----------------------------------------------------------------------------
# Gauntlet Commands (Review Personas)
# -----------------------------------------------------------------------------

PERSONAS = {
    "security_karen": "OWASP Top 10 security review",
    "test_terrorist": "Comprehensive testing coverage audit",
    "ruthless_reviewer": "Code quality and functional principles",
    "bragi": "Detect and flag LLM-ish prose patterns in markdown",
}


@main.group()
def gauntlet():
    """Run the review gauntlet with curated personas.

    The gauntlet runs your code through multiple ruthless reviewers,
    each with domain-specific rules loaded from seed files.

    Personas:
      - security_karen: OWASP security review (12 rules)
      - test_terrorist: Testing coverage audit (21 rules)
      - ruthless_reviewer: Code quality review (coming soon)

    Example workflow:

        buildlog gauntlet list                    # See available personas
        buildlog gauntlet rules --persona all    # Show all rules
        buildlog gauntlet prompt src/            # Generate review prompt
    """
    pass


@gauntlet.command("list")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def gauntlet_list(output_json: bool):
    """List available reviewer personas and their rule counts.

    Examples:

        buildlog gauntlet list
        buildlog gauntlet list --json
    """
    import json as json_module

    from buildlog.seeds import load_rules
    from buildlog.storage import get_backend

    try:
        backend, _ = get_backend()
    except Exception:
        backend = None

    seeds = load_rules(backend=backend)

    if not seeds:
        if output_json:
            click.echo('{"personas": {}, "total_rules": 0, "error": "No rules found"}')
        else:
            click.echo("No rules found.")
            click.echo("Seeds are bundled with buildlog - check your installation.")
        return

    if output_json:
        data = {
            "personas": {
                name: {
                    "description": PERSONAS.get(name, "Custom persona"),
                    "rules_count": len(sf.rules),
                    "version": sf.version,
                }
                for name, sf in seeds.items()
            },
            "total_rules": sum(len(sf.rules) for sf in seeds.values()),
        }
        click.echo(json_module.dumps(data, indent=2))
    else:
        click.echo("Review Gauntlet Personas")
        click.echo("=" * 50)

        if not seeds:
            click.echo("\nNo seed files found.")
            click.echo("Initialize with: buildlog init")
            click.echo("Or create seeds in: .buildlog/seeds/")
            return

        total = 0
        for name, sf in sorted(seeds.items()):
            desc = PERSONAS.get(name, "Custom persona")
            click.echo(f"\n  {name}")
            click.echo(f"    {desc}")
            click.echo(f"    Rules: {len(sf.rules)} (v{sf.version})")
            total += len(sf.rules)

        click.echo(f"\nTotal: {len(seeds)} personas, {total} rules")


@gauntlet.command("rules")
@click.option(
    "--persona",
    "-p",
    default="all",
    help="Persona to show rules for (or 'all')",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["yaml", "json", "markdown"]),
    default="yaml",
    help="Output format",
)
@click.option("--output", "-o", type=click.Path(), help="Output file")
def gauntlet_rules(persona: str, fmt: str, output: str | None):
    """Show rules for reviewer personas.

    Use this to see what rules are loaded for each persona,
    or export them for use in prompts.

    Examples:

        buildlog gauntlet rules                         # All rules (YAML)
        buildlog gauntlet rules -p security_karen       # Single persona
        buildlog gauntlet rules --format json -o rules.json
        buildlog gauntlet rules --format markdown       # For docs
    """
    import json as json_module

    from buildlog.seeds import load_rules
    from buildlog.storage import get_backend

    try:
        backend, _ = get_backend()
    except Exception:
        backend = None

    persona_filter = persona if persona != "all" else None
    seeds = load_rules(backend=backend, persona=persona_filter)

    if not seeds:
        if persona_filter:
            click.echo(f"No rules found for persona: {persona}", err=True)
        else:
            click.echo("No rules found.", err=True)
        raise SystemExit(1)

    # Filter personas (handles case where load_rules returned all and we need one)
    if persona != "all":
        if persona not in seeds:
            available = ", ".join(seeds.keys())
            click.echo(f"Unknown persona: {persona}", err=True)
            click.echo(f"Available: {available}", err=True)
            raise SystemExit(1)
        seeds = {persona: seeds[persona]}

    # Build output data
    if fmt == "json":
        data = {}
        for name, sf in seeds.items():
            data[name] = {
                "version": sf.version,
                "rules": [
                    {
                        "rule": r.rule,
                        "category": r.category,
                        "context": r.context,
                        "antipattern": r.antipattern,
                        "rationale": r.rationale,
                        "tags": r.tags,
                        "references": [
                            {"url": ref.url, "title": ref.title} for ref in r.references
                        ],
                    }
                    for r in sf.rules
                ],
            }
        formatted = json_module.dumps(data, indent=2)

    elif fmt == "markdown":
        lines = ["# Review Gauntlet Rules\n"]
        for name, sf in seeds.items():
            lines.append(f"## {name.replace('_', ' ').title()}\n")
            lines.append(f"*{len(sf.rules)} rules, v{sf.version}*\n")
            for i, r in enumerate(sf.rules, 1):
                lines.append(f"### {i}. {r.rule}\n")
                lines.append(f"**Category**: {r.category}  ")
                lines.append(f"**Tags**: {', '.join(r.tags)}\n")
                if r.context:
                    lines.append(f"**When**: {r.context}\n")
                if r.antipattern:
                    lines.append(f"**Antipattern**: {r.antipattern}\n")
                if r.rationale:
                    lines.append(f"**Why**: {r.rationale}\n")
                if r.references:
                    lines.append("**References**:")
                    for ref in r.references:
                        lines.append(f"- [{ref.title}]({ref.url})")
                lines.append("")
        formatted = "\n".join(lines)

    else:  # yaml
        import yaml as yaml_module

        data = {}
        for name, sf in seeds.items():
            data[name] = {
                "version": sf.version,
                "rules": [
                    {
                        "rule": r.rule,
                        "category": r.category,
                        "context": r.context,
                        "antipattern": r.antipattern,
                        "rationale": r.rationale,
                        "tags": r.tags,
                    }
                    for r in sf.rules
                ],
            }
        formatted = yaml_module.dump(data, default_flow_style=False, sort_keys=False)

    # Output
    if output:
        output_path = Path(output)
        output_path.write_text(formatted, encoding="utf-8")
        total = sum(len(sf.rules) for sf in seeds.values())
        click.echo(f"Wrote {total} rules to {output_path}")
    else:
        click.echo(formatted)


@gauntlet.command("prompt")
@click.argument("target", type=click.Path(exists=True))
@click.option(
    "--persona",
    "-p",
    multiple=True,
    help="Personas to include (default: all)",
)
@click.option("--output", "-o", type=click.Path(), help="Output file")
def gauntlet_prompt(target: str, persona: tuple[str, ...], output: str | None):
    """Generate a review prompt for the gauntlet.

    Creates a prompt with rules and target code that can be
    used with Claude or another LLM to run a review.

    Examples:

        buildlog gauntlet prompt src/
        buildlog gauntlet prompt src/api.py -p security_karen
        buildlog gauntlet prompt . -o review_prompt.md
    """
    from buildlog.seeds import load_rules
    from buildlog.storage import get_backend

    try:
        backend, _ = get_backend()
    except Exception:
        backend = None

    seeds = load_rules(backend=backend)

    if not seeds:
        click.echo("No rules found.", err=True)
        raise SystemExit(1)

    # Filter personas
    if persona:
        seeds = {k: v for k, v in seeds.items() if k in persona}
        if not seeds:
            click.echo(f"No matching personas: {', '.join(persona)}", err=True)
            raise SystemExit(1)

    # Build the prompt
    target_path = Path(target)
    lines = [
        "# Review Gauntlet Prompt\n",
        "You are running the Review Gauntlet. Apply these rules ruthlessly.\n",
        "## Target\n",
        f"Review: `{target_path}`\n",
        "## Reviewers and Rules\n",
    ]

    for name, sf in seeds.items():
        persona_name = name.replace("_", " ").title()
        lines.append(f"### {persona_name}\n")
        for r in sf.rules:
            lines.append(f"- **{r.rule}**")
            if r.antipattern:
                lines.append(f"  - Antipattern: {r.antipattern}")
        lines.append("")

    lines.extend(
        [
            "## Output Format\n",
            "For each issue found, output:\n",
            "```json",
            "{",
            '  "reviewer": "<persona>",',
            '  "severity": "critical|major|minor|nitpick",',
            '  "category": "<category>",',
            '  "location": "<file:line>",',
            '  "description": "<what is wrong>",',
            '  "rule_learned": "<generalizable rule>"',
            "}",
            "```\n",
            "## Instructions\n",
            "1. Read the target code thoroughly",
            "2. Apply each rule from each reviewer",
            "3. Report ALL violations found",
            "4. Be ruthless - this is the gauntlet",
            "",
        ]
    )

    formatted = "\n".join(lines)

    if output:
        output_path = Path(output)
        output_path.write_text(formatted, encoding="utf-8")
        click.echo(f"Wrote prompt to {output_path}")
    else:
        click.echo(formatted)


@gauntlet.command("learn")
@click.argument("issues_file", type=click.Path(exists=True))
@click.option("--source", "-s", help="Source identifier (e.g., 'gauntlet:PR#42')")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def gauntlet_learn(issues_file: str, source: str | None, output_json: bool):
    """Persist learnings from a gauntlet review.

    Takes a JSON file of issues (in the gauntlet output format)
    and calls learn_from_review to persist them.

    Examples:

        buildlog gauntlet learn review_issues.json
        buildlog gauntlet learn issues.json --source "gauntlet:2026-01-22"
    """
    import json as json_module
    from dataclasses import asdict

    from buildlog.core import learn_from_review

    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    # Load issues
    try:
        with open(issues_file) as f:
            data = json_module.load(f)
    except json_module.JSONDecodeError as e:
        click.echo(f"Invalid JSON: {e}", err=True)
        raise SystemExit(1)

    # Handle different formats
    if isinstance(data, list):
        issues = data
    elif isinstance(data, dict) and "all_issues" in data:
        issues = data["all_issues"]
    elif isinstance(data, dict) and "issues" in data:
        issues = data["issues"]
    else:
        click.echo(
            "Expected list of issues or dict with 'issues'/'all_issues'", err=True
        )
        raise SystemExit(1)

    if not issues:
        click.echo("No issues found in file.", err=True)
        raise SystemExit(1)

    # Learn from review
    result = learn_from_review(buildlog_dir, issues, source=source or "gauntlet")

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(f"✓ {result.message}")
        click.echo(f"  New learnings: {result.new_learnings}")
        click.echo(f"  Reinforced: {result.reinforced_learnings}")
        click.echo(f"  Total processed: {result.total_issues_processed}")


@gauntlet.command("generate")
@click.argument("source_text", type=click.Path(exists=True))
@click.option("--persona", "-p", required=True, help="Persona name for the seed file")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    default=".buildlog/seeds",
    help="Output directory for seed YAML",
)
@click.option("--dry-run", is_flag=True, help="Preview without writing")
def gauntlet_generate(source_text: str, persona: str, output_dir: str, dry_run: bool):
    """Generate seed rules from source text using LLM extraction.

    Runs the seed engine pipeline with LLMExtractor to produce
    a YAML seed file from arbitrary source content.

    Examples:

        buildlog gauntlet generate docs/security.md --persona security_karen
        buildlog gauntlet generate notes.txt -p test_terrorist --dry-run
    """
    import json as json_module

    from buildlog.llm import get_llm_backend
    from buildlog.seed_engine import Pipeline, Source, SourceType

    backend = get_llm_backend()
    if backend is None:
        click.echo(
            "No LLM backend available. Install ollama or set ANTHROPIC_API_KEY.",
            err=True,
        )
        raise SystemExit(1)

    content = Path(source_text).read_text()
    source = Source(
        name=Path(source_text).stem,
        url=f"file://{Path(source_text).resolve()}",
        source_type=SourceType.REFERENCE_DOC,
        domain=persona.split("_")[0] if "_" in persona else "general",
        description=content,
    )

    pipeline = Pipeline.with_llm(
        persona=persona,
        backend=backend,
        source_content={source.url: content},
    )

    if dry_run:
        preview = pipeline.dry_run([source])
        click.echo(json_module.dumps(preview, indent=2))
        return

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = pipeline.run([source], output_dir=out)
    click.echo(f"Generated {result.rule_count} rules for {persona}")
    if result.output_path:
        click.echo(f"Seed file: {result.output_path}")


@gauntlet.command("loop")
@click.argument("target", type=click.Path(exists=True))
@click.option(
    "--persona",
    "-p",
    multiple=True,
    help="Personas to run (default: all)",
)
@click.option(
    "--max-iterations",
    "-n",
    default=10,
    help="Maximum iterations to prevent infinite loops (default: 10)",
)
@click.option(
    "--stop-at",
    type=click.Choice(["criticals", "majors", "minors"]),
    default="minors",
    help="Stop after clearing this severity level (default: minors)",
)
@click.option(
    "--auto-gh-issues",
    is_flag=True,
    help="Create GitHub issues for remaining items when accepting risk",
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def gauntlet_loop(
    target: str,
    persona: tuple[str, ...],
    max_iterations: int,
    stop_at: str,
    auto_gh_issues: bool,
    output_json: bool,
):
    """Run the gauntlet loop: review, fix, repeat until clean.

    This command orchestrates the gauntlet loop workflow:

    1. Generate review prompt for target code
    2. Process issues and determine action
    3. On criticals: output fix instructions, expect re-run
    4. On majors only: checkpoint (ask to continue)
    5. On minors only: checkpoint (accept risk?)
    6. Optionally create GitHub issues for remaining items

    The loop is designed to be run interactively with an agent
    (Claude Code, Cursor, etc.) that does the actual fixing.

    Examples:

        buildlog gauntlet loop src/
        buildlog gauntlet loop tests/ --stop-at majors
        buildlog gauntlet loop . --auto-gh-issues
    """
    import json as json_module

    from buildlog.seeds import load_rules
    from buildlog.storage import get_backend

    try:
        backend, _ = get_backend()
    except Exception:
        backend = None

    seeds = load_rules(backend=backend)

    if not seeds:
        click.echo("No rules found.", err=True)
        raise SystemExit(1)

    # Filter personas
    if persona:
        seeds = {k: v for k, v in seeds.items() if k in persona}
        if not seeds:
            click.echo(f"No matching personas: {', '.join(persona)}", err=True)
            raise SystemExit(1)

    target_path = Path(target)

    # Generate persona rules summary
    rules_by_persona: dict[str, list[dict[str, str]]] = {}
    for name, sf in seeds.items():
        rules_by_persona[name] = [
            {"rule": r.rule, "antipattern": r.antipattern, "category": r.category}
            for r in sf.rules
        ]

    # Loop instructions
    instructions = [
        "1. Review the target code using the rules from each persona",
        "2. Report all violations as JSON issues with: severity, category, description, rule_learned, location",
        "3. Call `buildlog_gauntlet_issues` with the issues list to determine next action",
        "4. If action='fix_criticals': Fix critical+major issues, then re-run gauntlet",
        "5. If action='checkpoint_majors': Ask user whether to continue fixing majors",
        "6. If action='checkpoint_minors': Ask user whether to accept risk or continue",
        "7. If user accepts risk and --auto-gh-issues: Call `buildlog_gauntlet_accept_risk` with remaining issues",
        "8. Repeat until action='clean' or max_iterations reached",
    ]

    # Expected issue format
    issue_format = {
        "severity": "critical|major|minor|nitpick",
        "category": "security|testing|architectural|workflow|...",
        "description": "Concrete description of what's wrong",
        "rule_learned": "Generalizable rule for the future",
        "location": "file:line (optional)",
    }

    # Build the loop output
    output = {
        "command": "gauntlet_loop",
        "target": str(target_path),
        "personas": list(seeds.keys()),
        "max_iterations": max_iterations,
        "stop_at": stop_at,
        "auto_gh_issues": auto_gh_issues,
        "rules_by_persona": rules_by_persona,
        "instructions": instructions,
        "issue_format": issue_format,
    }

    if output_json:
        click.echo(json_module.dumps(output, indent=2))
    else:
        # Human-readable output
        click.echo("=" * 60)
        click.echo("GAUNTLET LOOP")
        click.echo("=" * 60)
        click.echo(f"\nTarget: {target_path}")
        click.echo(f"Personas: {', '.join(seeds.keys())}")
        click.echo(f"Max iterations: {max_iterations}")
        click.echo(f"Stop at: {stop_at}")
        click.echo(f"Auto GH issues: {auto_gh_issues}")

        click.echo("\n--- RULES ---")
        for name, rules in rules_by_persona.items():
            click.echo(f"\n## {name.replace('_', ' ').title()}")
            for r in rules:
                click.echo(f"  • {r['rule']}")

        click.echo("\n--- LOOP WORKFLOW ---")
        for instruction in instructions:
            click.echo(f"  {instruction}")

        click.echo("\n--- ISSUE FORMAT ---")
        click.echo(json_module.dumps(issue_format, indent=2))

        click.echo("\n" + "=" * 60)
        click.echo("Ready. Run gauntlet review and process issues.")
        click.echo("=" * 60)


# -----------------------------------------------------------------------------
# Storage Migration & Export Commands
# -----------------------------------------------------------------------------


@main.command()
@click.option(
    "--dry-run", is_flag=True, help="Show what would be migrated without writing"
)
@click.option(
    "--buildlog-dir",
    default="buildlog",
    type=click.Path(),
    help="Path to buildlog directory",
)
def migrate(dry_run: bool, buildlog_dir: str):
    """Migrate legacy JSON/JSONL files to the global SQLite database.

    Reads per-project files from buildlog/.buildlog/ and writes them into
    ~/.buildlog/buildlog.db. Original files are renamed to *.migrated
    (not deleted) for safety.

    Idempotent: safe to run multiple times.

    Examples:

        buildlog migrate
        buildlog migrate --dry-run
        buildlog migrate --buildlog-dir path/to/buildlog
    """
    from buildlog.storage.migrate import migrate_project

    bl_path = Path(buildlog_dir)
    lines = migrate_project(bl_path, dry_run=dry_run)
    for line in lines:
        click.echo(line)


@main.command("import-seed")
@click.argument("source", type=click.Path(exists=True))
@click.option(
    "--target-dir",
    type=click.Path(),
    default=None,
    help="Target directory for seed file (default: .buildlog/seeds)",
)
@click.option(
    "--buildlog-dir",
    type=click.Path(),
    default="buildlog",
    help="Path to buildlog directory",
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def import_seed(
    source: str, target_dir: str | None, buildlog_dir: str, output_json: bool
):
    """Import an external seed file (e.g. from qortex).

    Copies the seed file to the seeds directory and optionally triggers
    bandit decay if the graph_version has changed from a previous import.

    Examples:

        buildlog import-seed qortex-rules.yaml
        buildlog import-seed rules.yaml --target-dir .buildlog/seeds
    """
    import json as json_module
    from dataclasses import asdict

    from buildlog.seeds import import_seed_file

    try:
        result = import_seed_file(
            source_path=Path(source),
            target_dir=Path(target_dir) if target_dir else None,
            buildlog_dir=Path(buildlog_dir),
        )
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(f"✓ {result.message}")
        click.echo(f"  Target: {result.target_path}")
        if result.version_changed:
            click.echo(f"  Decayed: {result.decayed_rules} bandit arms")


@main.command("ingest-seeds")
@click.option("--source", default=None, help="Filter to a specific source name")
@click.option(
    "--buildlog-dir",
    type=click.Path(),
    default="buildlog",
    help="Path to buildlog directory",
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def ingest_seeds_cmd(source: str | None, buildlog_dir: str, output_json: bool):
    """Ingest pending seed files from external producers.

    Scans configured seed source directories (default: ~/.qortex/seeds/pending)
    for YAML seed files, validates and imports them, then moves files to
    processed/ or failed/ directories.

    Configure sources via ~/.buildlog/interop.yaml or use the default qortex layout.

    Examples:

        buildlog ingest-seeds
        buildlog ingest-seeds --source qortex
        buildlog ingest-seeds --json
    """
    import json as json_module
    from dataclasses import asdict

    from buildlog.interop import ingest_pending

    results = ingest_pending(
        source_name=source,
        buildlog_dir=Path(buildlog_dir),
    )

    if output_json:
        click.echo(json_module.dumps([asdict(r) for r in results], indent=2))
    else:
        for r in results:
            click.echo(r.message)
            for f in r.files:
                icon = {"ingested": "✓", "failed": "✗", "skipped": "⊘"}.get(
                    f.status, "?"
                )
                detail = f"  {icon} {f.file}"
                if f.persona:
                    detail += f" ({f.persona}, {f.rule_count} rules)"
                if f.error:
                    detail += f" — {f.error}"
                click.echo(detail)
        if not results:
            click.echo("No sources configured.")


@main.command("export")
@click.option(
    "--format",
    "fmt",
    default="jsonl",
    type=click.Choice(["jsonl"]),
    help="Export format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output directory (default: print to stdout)",
)
@click.option(
    "--project", type=str, default=None, help="Project ID to export (default: current)"
)
@click.option(
    "--tables",
    type=str,
    default=None,
    help=(
        "Comma-separated table names (default: all). "
        "Options: rewards, sessions, mistakes, bandit_state, learnings, skill_decisions"
    ),
)
def export_cmd(fmt: str, output: str | None, project: str | None, tables: str | None):
    """Export storage data to files.

    Exports event data from the storage backend (SQLite or legacy files)
    into JSONL files that match the legacy format.

    Examples:

        buildlog export
        buildlog export -o ./backup/
        buildlog export --tables rewards,sessions
        buildlog export --project abc123def456
    """
    from buildlog.storage import get_backend
    from buildlog.storage.exporters import JsonlExporter

    backend, project_id = get_backend(Path("buildlog"))

    # Use current project if not specified
    target_project = project or project_id

    table_list = tables.split(",") if tables else None
    output_path = Path(output) if output else None

    exporter = JsonlExporter()
    try:
        summary = exporter.export(
            backend,
            project_id=target_project,
            output_path=output_path,
            tables=table_list,
        )
        click.echo(summary)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
