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

**[Read the full documentation](https://peleke.github.io/buildlog-template/)** | **[Landing page](https://launchpad-git-buildlog-kwayet-fs-projects.vercel.app)**

</div>

---

## The Problem

Every AI-assisted work session produces decisions, corrections, and outcomes. Almost all of it gets discarded. The next session starts from scratch with the same blind spots.

buildlog captures structured trajectories from real work, extracts decision patterns, and uses Thompson Sampling to select which patterns to surface. Then it measures whether that selection actually reduced mistakes.

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

The seed engine watches your development patterns and extracts **seeds**: atomic observations about what works. A seed might be "always define interfaces before implementations" or "mock at the boundary, not the implementation." Each seed carries a category, a confidence score, and source provenance.

Extraction runs through a pipeline: `sources -> extractors -> categorizers -> generators`. Extractors range from regex-based (fast, cheap, brittle) to LLM-backed (accurate, expensive). The pipeline deduplicates semantically using embeddings.

### 3. Select which patterns to surface using Thompson Sampling

Seeds compete for inclusion in your agent's instruction set. The system treats each seed as an arm in a contextual bandit and uses **Thompson Sampling** to balance exploration (trying under-tested rules) against exploitation (surfacing rules with strong track records).

Each seed maintains a Beta posterior updated by observed outcomes. Over time, the system converges on the rules that actually reduce mistakes in your specific codebase and workflow, not rules that sound good in the abstract.

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

Track whether the selected rules are working. Run experiments, measure Repeated Mistake Rate (RMR) across sessions, and get statistical evidence, not feelings, about what improved.

```bash
buildlog experiment start
# ... work across sessions ...
buildlog experiment end
buildlog experiment report
```

## What Else Is In the Box

- **Review gauntlet:** automated quality gate with curated reviewer personas. Runs on commits (via Claude Code hooks or CI) and files GitHub issues for findings, categorized by severity.
- **LLM-backed extraction:** when regex isn't enough, the seed engine can use OpenAI, Anthropic, or Ollama to extract patterns from code and logs. Metered backend tracks token usage and cost.
- **Global SQLite storage:** all buildlog data is stored in a single global database at `~/.buildlog/buildlog.db` (SQLite with WAL mode). Project isolation via hashed project IDs derived from git remote URLs. Legacy per-project JSON/JSONL files are still supported as a fallback.
- **Migration and export:** `buildlog migrate` converts legacy JSON/JSONL files to the global database (idempotent, non-destructive). `buildlog export` dumps data back to JSONL for portability or backup.
- **Ambient emission protocol:** mistakes and learned rules are automatically emitted as JSON artifacts to `~/.buildlog/emissions/pending/` for offline ingestion by downstream systems (knowledge graphs, analytics). Fire-and-forget — emission failure never breaks the primary operation.
- **Workflow enforcement:** `buildlog verify` checks your setup (CLAUDE.md workflow section, MCP registration, branch protection hooks) and `--fix` repairs it. `buildlog init` installs pre-commit hooks that prevent direct commits to main and nudge toward `buildlog commit`.
- **Interactive dashboard:** `buildlog viz` launches a [marimo](https://marimo.io) notebook in your browser with live visualizations of reward trends, bandit posteriors, session history, mistake analysis, and insight breakdowns. All data comes from the global SQLite backend.
- **MCP server:** buildlog exposes itself as an MCP server so agents can query seeds, skills, and build history programmatically during sessions.
- **npm wrapper:** `npx @peleke.s/buildlog` for JS/TS projects. Thin shim that finds and invokes the Python CLI.

## Current Limits

This is v0.15, not the end state.

- **Extraction quality is uneven.** Regex extractors miss nuance; LLM extractors are accurate but expensive. The middle ground is still being found.
- **Feedback signals are coarse.** Repeated Mistake Rate works but requires manual tagging. Richer automatic signals (test outcomes, review results, revision distance) are on the roadmap.
- **Credit assignment is limited.** When multiple rules are active, the system doesn't yet isolate which one was responsible for an outcome.
- **Single-agent only.** Multi-agent coordination (shared learning across agents) is designed but not implemented.
- **Long-horizon learning is not modeled.** The bandit operates per-session. Longer arcs of competence building need richer policy models.

### What's next

Two layers building on the global SQLite backend and qortex integration:

1. **Cross-project convergence** — detect rules independently rediscovered across projects, track salience
2. **Emergent rule graphs** — cluster embeddings into concept nodes, derive edges from co-occurrence and bandit correlation, contextual bandits with embedding-space context vectors (LinUCB)

Embedding persistence via sqlite-vec is already available through the qortex learning backend.

See the [full roadmap](https://peleke.github.io/buildlog-template/roadmap/) for details.

## Installation

### Always-On Mode (recommended)

We run buildlog as an **ambient data capture layer** across all projects. One command, works everywhere:

```bash
pipx install buildlog         # or: uv tool install buildlog
buildlog init-mcp --global -y # registers MCP + writes instructions to ~/.claude/CLAUDE.md
```

That's it. Claude Code now has all 34 buildlog tools **and knows how to use them** in every project you open. No per-project setup needed.

The `--global` flag:
- Registers the MCP server in `~/.claude.json` (Claude Code's global config)
- Creates `~/.claude/CLAUDE.md` with usage instructions so Claude proactively uses buildlog
- Works immediately in any repo, even without a local `buildlog/` directory

The `-y` flag skips confirmation prompts (useful for scripts and CI).

This is how we use buildlog ourselves: always on, capturing structured trajectories from every session, feeding downstream systems that generate engineering logs, courses, and content.

### Per-project setup

If you prefer explicit per-project control:

```bash
pip install buildlog          # MCP server included by default
buildlog init --defaults      # scaffold buildlog/, register MCP, update CLAUDE.md
```

This creates a `buildlog/` directory with templates and configures Claude Code for that specific project.

### For JS/TS projects

```bash
npx @peleke.s/buildlog init
```

### Verify installation

```bash
buildlog mcp-test          # verify all 34 tools are registered
buildlog overview          # check project state (works without init in global mode)
```

## Quick Start

```bash
buildlog init --defaults      # scaffold + MCP + CLAUDE.md
buildlog new my-feature       # start a session
# ... work ...
buildlog commit -m "feat: add auth"
buildlog experiment start
# ... work across sessions ...
buildlog experiment end
buildlog experiment report
```

**Want the full picture?** The [Learning Loop E2E Trace](docs/LEARNING-LOOP-E2E.md) walks through all 13 steps with explicit code citations: installation, Thompson Sampling, gauntlet review, bandit updates, emission pipeline, cross-domain discovery via qortex, and rule re-export. Every claim above has a mechanical proof.

## Documentation

| Section | Description |
|---------|------------|
| [Installation](https://peleke.github.io/buildlog-template/getting-started/installation/) | Setup, extras, and initialization |
| [Quick Start](https://peleke.github.io/buildlog-template/getting-started/quick-start/) | Full pipeline walkthrough |
| **[Learning Loop E2E](docs/LEARNING-LOOP-E2E.md)** | **Complete 13-step trace with code citations — the proof** |
| [Core Concepts](https://peleke.github.io/buildlog-template/getting-started/concepts/) | The problem, the claim, and the metric |
| [Theory](https://peleke.github.io/buildlog-template/theory/) | From restaurant intuition to contextual bandits — the full tutorial |
| [CLI Reference](https://peleke.github.io/buildlog-template/guides/cli-reference/) | Every command documented |
| [MCP Integration](https://peleke.github.io/buildlog-template/guides/mcp-integration/) | Claude Code setup and available tools |
| [Storage Architecture](https://peleke.github.io/buildlog-template/guides/storage-architecture/) | Global SQLite backend, migration, and export |
| [Experiments](https://peleke.github.io/buildlog-template/guides/experiments/) | Running and measuring experiments |
| [Dashboard](https://peleke.github.io/buildlog-template/guides/dashboard/) | Interactive marimo dashboard (`buildlog viz`) |
| [Review Gauntlet](https://peleke.github.io/buildlog-template/guides/review-gauntlet/) | Reviewer personas and the gauntlet loop |
| [Multi-Agent Setup](https://peleke.github.io/buildlog-template/guides/multi-agent/) | Render rules to any AI coding agent |
| [Roadmap](https://peleke.github.io/buildlog-template/roadmap/) | Embeddings, cross-project convergence, rule graphs |
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
