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
buildlog reward <outcome>        # Log reward signal
buildlog overview                # Project state at a glance
```

## MCP Registration

```bash
buildlog init-mcp                # Register MCP in .claude/settings.json (local)
buildlog init-mcp --global       # Register in ~/.claude.json (global)
buildlog init-mcp --global -y    # Global, skip confirmation prompts
buildlog mcp-test                # Verify all 31 tools are registered
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
buildlog export                  # Export data to JSONL files
buildlog export --format jsonl   # Explicit format (jsonl is the default)
buildlog export --output ./dump  # Write to a specific directory
buildlog export --project <id>   # Export only a specific project
buildlog export --tables rewards,skills  # Export specific tables only
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
| `--tables` | Comma-separated list of tables to export (exports all by default) |

See [Storage Architecture](storage-architecture.md) for details on the global SQLite backend and migration process.
