# Multi-Agent Setup

buildlog renders rules to multiple AI coding agent formats. The rules are natural language — only the file format and path change between agents.

## Supported targets

| Agent | Target flag | Output path |
|-------|------------|-------------|
| Claude Code | `claude_md` | `CLAUDE.md` |
| Claude Code | `settings_json` | `.claude/settings.json` |
| Claude Code | `skill` | `.claude/skills/*.md` |
| Cursor | `cursor` | `.cursor/rules/buildlog-rules.mdc` |
| GitHub Copilot | `copilot` | `.github/copilot-instructions.md` |
| Windsurf | `windsurf` | `.windsurf/rules/buildlog-rules.md` |
| Continue.dev | `continue` | `.continue/rules/buildlog-rules.md` |

## Promoting rules to an agent

```bash
# Promote to Claude Code's CLAUDE.md
buildlog promote <skill-ids> --target claude_md

# Promote to Cursor
buildlog promote <skill-ids> --target cursor

# Promote to multiple targets at once
buildlog promote <skill-ids> --target claude_md --target cursor
```

## Format differences

| Agent | Format |
|-------|--------|
| Claude Code (CLAUDE.md) | Plain Markdown, appended to file |
| Claude Code (settings.json) | JSON configuration |
| Claude Code (skill) | Markdown with SKILL.md convention |
| Cursor | YAML frontmatter + Markdown (`.mdc`) |
| GitHub Copilot | Plain Markdown, appended to instructions file |
| Windsurf | Plain Markdown |
| Continue.dev | YAML frontmatter + Markdown |

## Adding a new agent

The renderer registry pattern makes this straightforward. Each renderer is a function that takes a list of rules and writes them to the appropriate file format and path. See the [Contributing guide](../development/contributing.md) for details.
