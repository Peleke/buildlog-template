<div align="center">

# buildlog

### A measurable learning loop for AI-assisted work

[![PyPI](https://img.shields.io/pypi/v/buildlog?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/buildlog/)
[![Python](https://img.shields.io/pypi/pyversions/buildlog?style=for-the-badge&logo=python&logoColor=white)](https://python.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/Peleke/buildlog-template/ci.yml?branch=main&style=for-the-badge&logo=github&label=CI)](https://github.com/Peleke/buildlog-template/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue?style=for-the-badge&logo=github)](https://peleke.github.io/buildlog-template/)

**Track what works. Prove it. Drop what doesn't.**

<img src="assets/hero-banner-perfectdeliberate.png" alt="buildlog - A measurable learning loop for AI-assisted work" width="800"/>

> **RE: The art.** Yes, it's AI-generated. Yes, that's hypocritical for a project about rigor over vibes. Looking for an actual artist to pay for a real logo. If you know someone good, [open an issue](https://github.com/Peleke/buildlog-template/issues) or DM me. Budget exists.

**[Read the full documentation](https://peleke.github.io/buildlog-template/)**

</div>

---

## The Problem

Most AI agents do not learn. They execute without retaining context. You can bolt on memory stores and tool routers, but if the system cannot demonstrably improve its decision-making over time, you have a persistent memory store, not a learning system.

Every AI-assisted work session produces a trajectory: goals, decisions, tool uses, corrections, outcomes. Almost all of this is discarded. The next session starts from scratch with the same blind spots.

buildlog exists to close that gap. It captures structured trajectories from real work, extracts decision patterns, and uses statistical methods to select which patterns to surface in future sessions — then measures whether that selection actually reduced mistakes.

buildlog measures whether the system actually got better, and proves it.

## How It Works

### 1. Capture structured work trajectories

Each session is a dated entry documenting what you did, what went wrong, and what you learned. Each session is a structured record of decisions and outcomes, not a chat transcript.

```bash
buildlog init          # scaffold a project
buildlog new my-feature   # start a session
# ... work ...
buildlog commit -m "feat: add auth"
```

### 2. Extract decision patterns as seeds

The seed engine watches your development patterns and extracts **seeds** — atomic observations about what works. A seed might be "always define interfaces before implementations" or "mock at the boundary, not the implementation." Each seed carries a category, a confidence score, and source provenance.

Extraction runs through a pipeline: `sources -> extractors -> categorizers -> generators`. Extractors range from regex-based (fast, cheap, brittle) to LLM-backed (accurate, expensive). The pipeline deduplicates semantically using embeddings.

### 3. Select which patterns to surface using Thompson Sampling

Seeds compete for inclusion in your agent's instruction set. The system treats each seed as an arm in a contextual bandit and uses **Thompson Sampling** to balance exploration (trying under-tested rules) against exploitation (surfacing rules with strong track records).

Each seed maintains a Beta posterior updated by observed outcomes. Over time, the system converges on the rules that actually reduce mistakes in your specific codebase and workflow — not rules that sound good in the abstract.

### 4. Render to every agent format

Selected rules are written into the instruction files your agents actually read:

- `CLAUDE.md` (Claude Code)
- `.cursorrules` (Cursor)
- `.github/copilot-instructions.md` (GitHub Copilot)
- Windsurf, Continue.dev, generic `settings.json`

The same knowledge base renders to every agent format.

```bash
buildlog skills   # render current policy to agent files
```

### 5. Close the loop with experiments

Track whether the selected rules are working. Run experiments, measure Repeated Mistake Rate (RMR) across sessions, and get statistical evidence — not feelings — about what improved.

```bash
buildlog experiment start
# ... work across sessions ...
buildlog experiment end
buildlog experiment report
```

## What Else Is In the Box

- **Review gauntlet:** automated quality gate with curated reviewer personas. Runs on commits (via Claude Code hooks or CI) and files GitHub issues for findings, categorized by severity.
- **LLM-backed extraction:** when regex isn't enough, the seed engine can use OpenAI, Anthropic, or Ollama to extract patterns from code and logs. Metered backend tracks token usage and cost.
- **MCP server:** buildlog exposes itself as an MCP server so agents can query seeds, skills, and build history programmatically during sessions.
- **npm wrapper:** `npx @peleke/buildlog` for JS/TS projects. Thin shim that finds and invokes the Python CLI.

## Current Limits

This is v0.8, not the end state.

- **Extraction quality is uneven.** Regex extractors miss nuance; LLM extractors are accurate but expensive. The middle ground is still being found.
- **Feedback signals are coarse.** Repeated Mistake Rate works but requires manual tagging. Richer automatic signals (test outcomes, review results, revision distance) are on the roadmap.
- **Credit assignment is limited.** When multiple rules are active, the system doesn't yet isolate which one was responsible for an outcome.
- **Single-agent only.** Multi-agent coordination (shared learning across agents) is designed but not implemented.
- **Long-horizon learning is not modeled.** The bandit operates per-session. Longer arcs of competence building need richer policy models.

The roadmap: contextual bandits (now) -> richer policy models -> longer-horizon RL -> multi-agent coordination. Each step builds on the same foundation: measuring whether rule changes actually reduce mistakes.

## Quick Start

```bash
uv pip install buildlog   # or: pip install buildlog
buildlog init
buildlog new my-feature
buildlog distill && buildlog skills
buildlog experiment start
# ... work ...
buildlog experiment end
buildlog experiment report
```

## Documentation

| Section | Description |
|---------|------------|
| [Installation](https://peleke.github.io/buildlog-template/getting-started/installation/) | Setup, extras, and initialization |
| [Quick Start](https://peleke.github.io/buildlog-template/getting-started/quick-start/) | Full pipeline walkthrough |
| [Core Concepts](https://peleke.github.io/buildlog-template/getting-started/concepts/) | The problem, the claim, and the metric |
| [CLI Reference](https://peleke.github.io/buildlog-template/guides/cli-reference/) | Every command documented |
| [MCP Integration](https://peleke.github.io/buildlog-template/guides/mcp-integration/) | Claude Code setup and available tools |
| [Experiments](https://peleke.github.io/buildlog-template/guides/experiments/) | Running and measuring experiments |
| [Review Gauntlet](https://peleke.github.io/buildlog-template/guides/review-gauntlet/) | Reviewer personas and the gauntlet loop |
| [Multi-Agent Setup](https://peleke.github.io/buildlog-template/guides/multi-agent/) | Render rules to any AI coding agent |
| [Theory](https://peleke.github.io/buildlog-template/theory/00-background/) | The math behind Thompson Sampling |
| [Philosophy](https://peleke.github.io/buildlog-template/philosophy/) | Principles and honest limitations |

## Contributing

```bash
git clone https://github.com/Peleke/buildlog-template
cd buildlog-template
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

We're especially interested in better context representations, credit assignment approaches, statistical methodology improvements, and real-world experiment results (positive or negative).

## License

MIT License. See [LICENSE](./LICENSE)
