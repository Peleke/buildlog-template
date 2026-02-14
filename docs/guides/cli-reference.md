# CLI Reference

## Core Commands

```bash
buildlog init                    # Initialize buildlog (--defaults for non-interactive)
buildlog init-mcp                # Register MCP server only
buildlog new <slug>              # Create entry
buildlog list                    # List entries
buildlog distill                 # Extract patterns
buildlog skills                  # Generate rules
buildlog stats                   # Usage statistics
buildlog viz                     # Interactive dashboard (marimo)
buildlog reward <outcome>        # Log reward signal
buildlog overview                # Project state at a glance
buildlog verify                  # Check workflow setup (hooks, CLAUDE.md, MCP)
buildlog verify --fix            # Auto-fix missing workflow section
buildlog verify --json           # Output as JSON
```

## Workflow Enforcement

`buildlog init` installs two enforcement layers automatically:

### Git Hooks (pre-commit framework)

When `.pre-commit-config.yaml` exists, `install_hooks()` adds two local hooks:

| Hook ID | What it does |
|---------|-------------|
| `prevent-commit-to-main` | Blocks commits to `main`/`master` |
| `enforce-buildlog-commit` | Blocks bare `git commit`. Use `buildlog commit` instead. |

Without a pre-commit config, both hooks install as standalone `.git/hooks/pre-commit` scripts.

The enforcement hook is always-on by default. `buildlog commit` sets `BUILDLOG_COMMIT=1` to bypass it.

| Env var | Effect |
|---------|--------|
| `BUILDLOG_COMMIT=1` | Allow this commit through (set by `buildlog commit`) |
| `BUILDLOG_ENFORCE=0` | Disable enforcement entirely (opt-out) |

Skip hook installation with `buildlog init --defaults --no-hooks`.

### Claude Code Hooks (agent-level)

`.claude/hooks/enforce-buildlog-commit.sh` is a `PreToolUse` hook that intercepts `git commit` in Bash tool calls. It blocks bare commits and directs agents to use `buildlog commit` instead. `BUILDLOG_COMMIT=1` and `--amend` are allowed through.

Wired via `.claude/settings.json` under `hooks.PreToolUse`.

## MCP Registration

```bash
buildlog init-mcp                # Register MCP in .claude/settings.json (local)
buildlog init-mcp --global       # Register in ~/.claude.json (global)
buildlog init-mcp --global -y    # Global, skip confirmation prompts
buildlog mcp-test                # Verify all 34 tools are registered
```

### Flags for `init-mcp`

| Flag | Effect |
|------|--------|
| `--global` | Write to `~/.claude.json` instead of `.claude/settings.json` |
| `-y`, `--yes` | Skip confirmation prompts (non-interactive mode) |

The `--global` flag also creates `~/.claude/CLAUDE.md` with usage instructions.

## Skill Management

```bash
buildlog status                  # Show skills by category and confidence
buildlog promote <ids> --target  # Promote skills to agent (claude_md, settings_json, skill)
buildlog reject <ids>            # Mark false positives
buildlog diff                    # Show skills pending review
```

### Promote targets

| Target | Where rules go |
|--------|---------------|
| `claude_md` | Appended to `CLAUDE.md` |
| `settings_json` | Written to `.claude/settings.json` |
| `skill` | Written as Agent Skills files |
| `cursor` | Written to `.cursor/rules/buildlog-rules.mdc` |
| `copilot` | Appended to `.github/copilot-instructions.md` |
| `windsurf` | Written to `.windsurf/rules/buildlog-rules.md` |
| `continue` | Written to `.continue/rules/buildlog-rules.md` |

## Experiments

```bash
buildlog experiment start        # Begin tracked session (bandit selects rules)
buildlog experiment log-mistake  # Record mistake (--error-class, -d)
buildlog experiment end          # End session
buildlog experiment metrics      # Single-session metrics
buildlog experiment report       # Full report across all sessions
```

`metrics` shows a single session; `report` shows the full picture across all sessions.

The report includes:

- Total sessions, total mistakes
- Repeat rate (RMR)
- Per-session breakdown
- Mistakes by error class

## Dashboard

```bash
buildlog viz                     # Open interactive dashboard in browser
buildlog viz --port 8080         # Custom port
buildlog viz --no-browser        # Headless mode (for CI or remote)
```

Launches a [marimo](https://marimo.io) notebook with live panels:

- **Overview**: entry counts, coverage, streak stats
- **Insights by Category**: distribution across architectural, workflow, tool usage, domain knowledge
- **Learning Loop**: reward event trends, outcome breakdown, running mean
- **Session History**: last 10 sessions with rule deltas
- **Mistake Analysis**: error class breakdown, repeat rate
- **Bandit Posteriors**: top 15 rules by mean, confidence intervals, status
- **Health**: top sources, quality warnings

## Review Gauntlet

```bash
buildlog gauntlet list           # Show reviewers
buildlog gauntlet rules          # Export rules
buildlog gauntlet prompt <path>  # Generate review prompt
buildlog gauntlet learn <file>   # Persist learnings
buildlog gauntlet loop <path>    # Auto-fix loop with HITL checkpoints
```

See [Review Gauntlet](review-gauntlet.md) for details on personas and the gauntlet loop.

## Storage

```bash
buildlog migrate                 # Migrate legacy JSON/JSONL to global SQLite DB
buildlog migrate --dry-run       # Preview what would be migrated without writing
buildlog export                  # Export all 6 tables to JSONL files
buildlog export --output ./dump  # Write to a specific directory
buildlog export --project <id>   # Export only a specific project
buildlog export --tables rewards,bandit_state  # Export specific tables only
buildlog import-seed seed.yaml   # Import external seed file
buildlog ingest-seeds            # Ingest pending files from external producers
```

### Flags for `migrate`

| Flag | Effect |
|------|--------|
| `--dry-run` | Show what would be migrated without making changes |

Migration is idempotent and non-destructive. Legacy files are renamed to `*.migrated` after successful migration, so they are preserved but no longer read by the system.

### Flags for `export`

| Flag | Effect |
|------|--------|
| `--format` | Output format (`jsonl` is currently the only supported format) |
| `--output` | Directory to write exported files (defaults to current directory) |
| `--project` | Export data for a specific project ID only |
| `--tables` | Comma-separated list of tables: `rewards`, `sessions`, `mistakes`, `bandit_state`, `learnings`, `skill_decisions` (exports all by default) |

Export also generates `manifest.json` (export metadata + record counts) and `rules.jsonl` (join table mapping buildlog IDs to upstream provenance fields).

### Flags for `import-seed`

| Flag | Effect |
|------|--------|
| `--target-dir` | Directory to copy seed file into (default: `.buildlog/seeds/`) |
| `--buildlog-dir` | Path to buildlog directory for bandit state (default: `buildlog`) |
| `--json` | Output result as JSON |

If the target seed file already exists, `import-seed` compares `provenance.graph_version` per rule. Changed versions trigger 50% decay of learned bandit signal for affected rules.

### Flags for `ingest-seeds`

| Flag | Effect |
|------|--------|
| `--source` | Filter to a specific source name (e.g. `qortex`) |
| `--buildlog-dir` | Path to buildlog directory (default: `buildlog`) |
| `--json` | Output as JSON |

Ingest scans configured seed source directories for pending YAML files, validates them, imports into the local seeds directory, and moves processed files. Configure sources via `~/.buildlog/interop.yaml` or use the default qortex layout.

See [Interop & Seed Ingestion](interop.md) for the full protocol and configuration reference.

See [Storage Architecture](storage-architecture.md) for details on the global SQLite backend and migration process.
