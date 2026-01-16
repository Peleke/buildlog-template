<div align="center">

# buildlog

**Engineering notebook for AI-assisted development.**

Capture your work as publishable content. Include the fuckups.

[![PyPI](https://img.shields.io/pypi/v/buildlog?style=flat-square)](https://pypi.org/project/buildlog/)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## Why

You're pairing with AI on real work. The insights from those sessions - the wrong turns, the fixes, the "oh shit" moments - are worth more than polished docs.

**buildlog** captures that signal as structured markdown you can actually use later.

---

## Install

```bash
pip install buildlog
```

---

## Usage

```bash
buildlog init              # Set up in your project
buildlog new auth-api      # Create today's entry
buildlog list              # See all entries
```

That's it. You get a `buildlog/` directory with templates. Fill them in as you work.

---

## What You Capture

Each entry has six required sections:

| Section | What Goes Here |
|---------|----------------|
| **The Goal** | What you're building and why |
| **What We Built** | Architecture diagram, components |
| **The Journey** | Chronological narrative *including mistakes* |
| **Test Results** | Actual commands, actual outputs |
| **Code Samples** | Key snippets with context |
| **Improvements** | Actionable learnings for next time |

The **Improvements** section is the secret sauce - it's structured for future extraction:

```markdown
### Architectural
- Should have used a plugin architecture from the start

### Workflow
- Write the integration test first to clarify the API contract

### Tool Usage
- Use `jwt.io` to decode tokens instead of console.log

### Domain Knowledge
- Supabase storage returns 400, not 404, for missing files
```

---

## Philosophy

1. **Write fast, not pretty** - Refrigerator to-do list energy
2. **Never delete mistakes** - They're the most valuable content
3. **Include the journey** - Wrong turns > polished outcomes
4. **Capture improvements** - Concrete learnings, not vague observations

---

## Quality Bar

Each entry should be publishable as a **$500+ tutorial**.

Real error messages. Honest about what didn't work. Code that runs.

---

## For AI Agents

Running `buildlog init` adds instructions to your `CLAUDE.md`:

```markdown
## Build Journal

After significant work, write a build journal entry.
Include mistakes. Fill out the Improvements section.
Ask: "Should I write a build journal entry for this?"
```

The Improvements section accumulates knowledge that can eventually feed back into agent behavior.

---

## Commands

| Command | Description |
|---------|-------------|
| `buildlog init` | Initialize in current directory |
| `buildlog new <slug>` | Create entry for today |
| `buildlog new <slug> --date 2026-01-15` | Create entry for specific date |
| `buildlog list` | List all entries |
| `buildlog update` | Update templates to latest |

---

## Alternative Install

Without the CLI, use Copier directly:

```bash
pipx run copier copy gh:Peleke/buildlog-template .
```

---

## License

MIT

