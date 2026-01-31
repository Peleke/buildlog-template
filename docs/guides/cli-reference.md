# CLI Reference

## Core Commands

```bash
buildlog init                    # Initialize buildlog (--defaults for non-interactive)
buildlog new <slug>              # Create entry
buildlog list                    # List entries
buildlog distill                 # Extract patterns
buildlog skills                  # Generate rules
buildlog stats                   # Usage statistics
buildlog reward <outcome>        # Log reward signal
```

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
