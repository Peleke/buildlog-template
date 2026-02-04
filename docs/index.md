# buildlog

## Engineering insights that compound

Capture what works. Measure whether it actually helped. Drop what didn't.

---

buildlog extracts decision patterns from your AI-assisted work and uses Thompson Sampling to surface rules that reduce mistakes—then tracks whether they did. The feedback loop is statistical, not vibes-based.

## What buildlog does

- **Captures** engineering knowledge from work sessions as structured entries
- **Extracts** rules and patterns using distillation and deduplication
- **Selects** which rules to surface using a Thompson Sampling bandit
- **Measures** impact via Repeated Mistake Rate (RMR) across tracked experiments
- **Integrates** with Claude Code, Cursor, GitHub Copilot, Windsurf, and Continue.dev

## Quick start

```bash
uv pip install buildlog   # or: pip install buildlog (inside a venv)
buildlog init
buildlog new my-feature
# After a few entries:
buildlog distill
buildlog skills
buildlog experiment start
# ... work ...
buildlog experiment end
buildlog experiment report
```

## Next steps

- [Installation](getting-started/installation.md) — setup details and extras
- [Quick Start](getting-started/quick-start.md) — the full pipeline walkthrough
- [Core Concepts](getting-started/concepts.md) — the problem, the claim, and the metric
- [CLI Reference](guides/cli-reference.md) — every command documented
- [Theory](theory/00-background.md) — the math behind Thompson Sampling
