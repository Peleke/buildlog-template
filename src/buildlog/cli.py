"""CLI for buildlog - engineering notebook for AI-assisted development."""

import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import click

from buildlog.distill import CATEGORIES, distill_all, format_output
from buildlog.skills import generate_skills, format_skills
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
def init(no_claude_md: bool):
    """Initialize buildlog in the current directory.

    Sets up the buildlog/ directory with templates and optionally
    adds instructions to CLAUDE.md.
    """
    buildlog_dir = Path("buildlog")

    if buildlog_dir.exists():
        click.echo("buildlog/ directory already exists.", err=True)
        raise SystemExit(1)

    template_dir = get_template_dir()

    if template_dir:
        # Use local template
        click.echo("Initializing buildlog from local template...")
        try:
            subprocess.run(
                [
                    sys.executable, "-m", "copier", "copy",
                    "--trust",
                    *(["--data", "update_claude_md=false"] if no_claude_md else []),
                    str(template_dir),
                    "."
                ],
                check=True
            )
        except subprocess.CalledProcessError:
            click.echo("Failed to initialize buildlog.", err=True)
            raise SystemExit(1)
    else:
        # Fall back to GitHub
        click.echo("Initializing buildlog from GitHub...")
        try:
            subprocess.run(
                [
                    sys.executable, "-m", "copier", "copy",
                    "--trust",
                    *(["--data", "update_claude_md=false"] if no_claude_md else []),
                    "gh:Peleke/buildlog-template",
                    "."
                ],
                check=True
            )
        except subprocess.CalledProcessError:
            click.echo("Failed to initialize buildlog.", err=True)
            raise SystemExit(1)

    click.echo("\n✓ buildlog initialized!")
    click.echo("\nNext: buildlog new my-feature")


@main.command()
@click.argument("slug")
@click.option("--date", "-d", "entry_date", default=None, help="Date for entry (YYYY-MM-DD)")
def new(slug: str, entry_date: str | None):
    """Create a new buildlog entry.

    SLUG is a short identifier for the entry (e.g., 'auth-api', 'bugfix-login').

    Examples:

        buildlog new auth-api
        buildlog new runpod-deploy --date 2026-01-15
    """
    buildlog_dir = Path("buildlog")
    template_file = buildlog_dir / "_TEMPLATE.md"

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    if not template_file.exists():
        click.echo("No _TEMPLATE.md found in buildlog/. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    # Determine date
    if entry_date:
        try:
            # Validate date format
            year, month, day = entry_date.split("-")
            date_str = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            click.echo("Invalid date format. Use YYYY-MM-DD.", err=True)
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


@main.command()
def list():
    """List all buildlog entries."""
    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    entries = sorted(
        buildlog_dir.glob("20??-??-??-*.md"),
        reverse=True  # Most recent first
    )

    if not entries:
        click.echo("No entries yet. Create one with: buildlog new my-feature")
        return

    click.echo(f"Found {len(entries)} entries:\n")
    for entry in entries:
        # Extract title from first line if possible
        try:
            first_line = entry.read_text().split("\n")[0]
            title = first_line.replace("# Build Journal: ", "").replace("# ", "").strip()
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
                [sys.executable, "-m", "copier", "update", "--trust"],
                check=True
            )
        except subprocess.CalledProcessError:
            click.echo("Failed to update. Try running 'copier update' directly.", err=True)
            raise SystemExit(1)
    else:
        click.echo("Updating from GitHub...")
        try:
            subprocess.run(
                [sys.executable, "-m", "copier", "update", "--trust"],
                check=True
            )
        except subprocess.CalledProcessError:
            click.echo("Failed to update. Try running 'copier update' directly.", err=True)
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
def distill(output: str | None, fmt: str, since: datetime | None, category: str | None):
    """Extract patterns from all buildlog entries.

    Parses the Improvements section of each buildlog entry and aggregates
    insights into structured output (JSON or YAML).

    Examples:

        buildlog distill                       # JSON to stdout
        buildlog distill -o patterns.json      # Write to file
        buildlog distill --format yaml         # YAML output
        buildlog distill --since 2026-01-01    # Filter by date
        buildlog distill --category workflow   # Filter by category
    """
    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    # Convert datetime to date if provided
    since_date = since.date() if since else None

    # Run distillation
    try:
        result = distill_all(buildlog_dir, since=since_date, category_filter=category)
    except Exception as e:
        click.echo(f"Failed to distill entries: {e}", err=True)
        raise SystemExit(1)

    # Format output
    try:
        formatted = format_output(result, fmt)
    except ImportError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    # Write output
    if output:
        output_path = Path(output)
        try:
            output_path.write_text(formatted, encoding="utf-8")
            click.echo(f"Wrote {result.statistics.get('total_patterns', 0)} patterns to {output_path}")
        except Exception as e:
            click.echo(f"Failed to write output: {e}", err=True)
            raise SystemExit(1)
    else:
        click.echo(formatted)


@main.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--detailed", is_flag=True, help="Show detailed breakdown including top sources")
@click.option("--since", "since_date", default=None, help="Only include entries since date (YYYY-MM-DD)")
def stats(output_json: bool, detailed: bool, since_date: str | None):
    """Show buildlog statistics and analytics.

    Provides insights on buildlog usage, coverage, and quality.

    Examples:

        buildlog stats              # Terminal dashboard
        buildlog stats --json       # JSON output for scripts
        buildlog stats --detailed   # Include top sources
        buildlog stats --since 2026-01-01
    """
    buildlog_dir = Path("buildlog")

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

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
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["yaml", "json", "markdown"]),
    default="yaml",
    help="Output format (default: yaml)",
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
def skills(
    output: str | None,
    fmt: str,
    min_frequency: int,
    since: datetime | None,
    embeddings: str | None,
):
    """Generate agent-consumable skills from buildlog patterns.

    Transforms distilled patterns into actionable rules with deduplication,
    confidence scoring, and stable IDs.

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

    if not buildlog_dir.exists():
        click.echo("No buildlog/ directory found. Run 'buildlog init' first.", err=True)
        raise SystemExit(1)

    # Convert datetime to date if provided
    since_date = since.date() if since else None

    # Generate skills
    try:
        skill_set = generate_skills(
            buildlog_dir,
            min_frequency=min_frequency,
            since_date=since_date,
            embedding_backend=embeddings,
        )
    except ImportError as e:
        click.echo(f"Missing dependency: {e}", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"Failed to generate skills: {e}", err=True)
        raise SystemExit(1)

    # Format output
    try:
        formatted = format_skills(skill_set, fmt)
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


if __name__ == "__main__":
    main()
