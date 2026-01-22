"""CLI for buildlog - engineering notebook for AI-assisted development."""

import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import click

from buildlog.core import get_rewards, log_reward
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
                    sys.executable,
                    "-m",
                    "copier",
                    "copy",
                    "--trust",
                    *(["--data", "update_claude_md=false"] if no_claude_md else []),
                    str(template_dir),
                    ".",
                ],
                check=True,
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
                    sys.executable,
                    "-m",
                    "copier",
                    "copy",
                    "--trust",
                    *(["--data", "update_claude_md=false"] if no_claude_md else []),
                    "gh:Peleke/buildlog-template",
                    ".",
                ],
                check=True,
            )
        except subprocess.CalledProcessError:
            click.echo("Failed to initialize buildlog.", err=True)
            raise SystemExit(1)

    click.echo("\n✓ buildlog initialized!")
    click.echo("\nNext: buildlog new my-feature")


@main.command()
@click.argument("slug")
@click.option(
    "--date", "-d", "entry_date", default=None, help="Date for entry (YYYY-MM-DD)"
)
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
        click.echo(
            "No _TEMPLATE.md found in buildlog/. Run 'buildlog init' first.", err=True
        )
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
        buildlog_dir.glob("20??-??-??-*.md"), reverse=True  # Most recent first
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
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def reward(
    outcome: str,
    distance: float | None,
    error_class: str | None,
    notes: str | None,
    rules: tuple[str, ...],
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
    )

    if output_json:
        click.echo(json_module.dumps(asdict(result), indent=2))
    else:
        click.echo(f"✓ {result.message}")
        click.echo(f"  Reward ID: {result.reward_id}")
        click.echo(f"  Total events: {result.total_events}")


@main.command()
@click.option("--limit", "-n", type=int, help="Limit number of events to show")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def rewards(limit: int | None, output_json: bool):
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

    summary = get_rewards(buildlog_dir, limit=limit)

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
    "--class",
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

        buildlog experiment log-mistake --class missing_test -d "Forgot tests"
        buildlog experiment log-mistake --class validation -d "No max length" -r val-123
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


if __name__ == "__main__":
    main()
