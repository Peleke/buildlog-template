# Build Journal: Dogfooding the Auditor

**Date:** 2026-01-27
**Duration:** Extended session (multi-phase)
**Outcome:** Engine extraction + agent-agnostic renderers

## Context

Buildlog had grown into a tool with a CLI, MCP server, Thompson Sampling bandit, confidence scoring, and a gauntlet review loop. But the core algorithms were locked inside `core/operations.py` — a 2100-line file that coupled experiment tracking to skill generation, and renderers that only knew about Claude.

The goal: make buildlog's engine reusable by any tool, and its renderers work with any AI coding agent.

## What Happened

### Phase 1: The Audit

Asked Claude to RTFM buildlog's own documentation. It found six issues:
- Version mismatch between pyproject.toml and CLI
- `buildlog init --defaults` flag wasn't wired
- Four CLI subcommands referenced in docs but not implemented
- Flag naming inconsistency (`--class` vs `--error-class`)
- Confusing `metrics` vs `report` naming
- Install instructions referenced wrong extras

Every one of these was real. The agent-as-auditor pattern works.

### Phase 2: Engine Extraction

Created `src/buildlog/engine/` as a clean namespace:

```
engine/
├── __init__.py      # Public API
├── bandit.py        # Re-export from core/bandit.py
├── confidence.py    # Re-export from buildlog.confidence
├── embeddings.py    # Re-export from buildlog.embeddings
├── types.py         # Pure dataclasses (Skill, Session, Mistake, etc.)
└── experiments.py   # Session/mistake/reward — decoupled from generate_skills()
```

The key insight: `start_session()` in `core/operations.py` called `generate_skills()` to get the rule list before passing it to the bandit. This tight coupling meant you couldn't use the experiment engine without the full skill generation pipeline.

Fix: `engine/experiments.start_session()` accepts `available_rules: list[str]` as a parameter. The caller provides the rules however it wants. The engine doesn't care where they come from.

### Phase 3: Agent-Agnostic Renderers

Added four new renderers alongside the existing Claude targets:

| Target | File | Format |
|--------|------|--------|
| Cursor | `.cursor/rules/buildlog-rules.mdc` | YAML frontmatter + MD |
| GitHub Copilot | `.github/copilot-instructions.md` | Plain Markdown (append) |
| Windsurf | `.windsurf/rules/buildlog-rules.md` | Plain Markdown |
| Continue.dev | `.continue/rules/buildlog-rules.md` | YAML frontmatter + MD |

Rules are natural language — the only thing that changes between agents is the file format and path. The renderer registry pattern made this trivial to extend.

## Improvements

### Architectural
- Decouple experiment engine from skill generation (`available_rules` parameter)
- Re-export pattern preserves git blame while providing clean namespace
- Empty `[engine]` extra documents the namespace without adding deps

### Workflow
- Always run your own README before shipping
- Agent-as-auditor: have an AI read your docs as a new user would
- The audit found issues humans missed for weeks

## Mistakes

- Initially forgot that `start_session()` was coupled to `generate_skills()` — the extraction plan needed revision after reading the code
- Nearly duplicated helper functions between engine/experiments.py and core/operations.py before settling on the re-export + thin wrapper pattern

## AI Experience

This was a meta-exercise: using buildlog to build buildlog. The Thompson Sampling bandit that selects rules for sessions was itself being extracted into a reusable engine during a session that the bandit could track.

The agent-as-auditor pattern was the most valuable discovery. Having an AI read your documentation as a newcomer surfaces the exact gaps that familiarity blinds you to. Every issue it found was legitimate.

## Key Decisions

1. **Re-export, don't move**: Engine modules re-export from canonical locations to preserve git blame
2. **Accept `available_rules`**: The coupling fix that makes the engine truly agent-agnostic
3. **Registry pattern for renderers**: `RENDERERS` dict means adding a new agent is one import + one dict entry
4. **Empty extras**: `pip install buildlog[engine]` is documentation, not dependency management
