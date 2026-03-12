> ⚠️ **Deprecation Notice**
>
> buildlog v1 is retired. It was an experimental RLHF lifecycle harness for Claude Code that captured programming mistakes, derived rules from human feedback, and dynamically injected them into context on commit. The learning loop worked, but the architecture was too tightly coupled to Claude Code's session model.
>
> A v2 is planned as a tightly scoped pipe layer in Rust, using [qortex](https://github.com/Peleke/qortex) as its backend. Design plan forthcoming.

---

# buildlog

### A measurable learning loop for AI-assisted work

**[Documentation](https://peleke.github.io/buildlog-template/)**

---

## The Problem

Every AI-assisted work session produces decisions, corrections, and outcomes. Almost all of it gets discarded. The next session starts from scratch with the same blind spots.

buildlog captures structured trajectories from real work, extracts decision patterns, and uses Thompson Sampling to select which patterns to surface. Then it measures whether that selection actually reduced mistakes.

## How It Works

### 1. Capture structured work trajectories

Each session is a dated entry documenting what you did, what went wrong, and what you learned -- a structured record of decisions and outcomes, not a chat transcript.

```bash
buildlog init               # scaffold a project
buildlog new my-feature      # start a session
# ... work ...
buildlog commit -m "feat: add auth"
```

### 2. Extract decision patterns as seeds

The seed engine watches your development patterns and extracts **seeds**: atomic observations about what works. A seed might be "always define interfaces before implementations" or "mock at the boundary, not the implementation." Each seed carries a category, a confidence score, and source provenance.

Extraction runs through a pipeline: `sources -> extractors -> categorizers -> generators`. Extractors range from regex-based (fast, cheap, brittle) to LLM-backed (accurate, expensive). The pipeline deduplicates semantically using embeddings.

### 3. Review with the gauntlet

The **gauntlet** is an automated quality gate with curated reviewer personas. It runs on your code and files findings categorized by severity. When a reviewer cites a rule in their review, that rule gets credited -- this is the sole feedback signal that drives learning.

### 4. Select which patterns to surface using Thompson Sampling

Seeds compete for inclusion in your agent's instruction set. The system treats each seed as an arm in a multi-armed bandit and uses **Thompson Sampling** (via [qortex-learning](https://github.com/Peleke/qortex)) to balance exploration (trying under-tested rules) against exploitation (surfacing rules with strong track records).

Each seed maintains a Beta posterior updated by gauntlet review outcomes. Over time, the system converges on the rules that actually reduce mistakes in your specific codebase and workflow, not rules that sound good in the abstract.

### 5. Render to every agent format

Selected rules are written into the instruction files your agents actually read:

- `CLAUDE.md` (Claude Code)
- `.cursorrules` (Cursor)
- `.github/copilot-instructions.md` (GitHub Copilot)
- Windsurf, Continue.dev, generic `settings.json`

```bash
buildlog skills   # render current policy to agent files
```

### 6. Close the loop

Track whether the selected rules are working. Run experiments, measure Repeated Mistake Rate (RMR) across sessions, and get statistical evidence -- not feelings -- about what improved.

```bash
buildlog experiment start
# ... work across sessions ...
buildlog experiment end
buildlog experiment report
```

## The Learning Loop

The feedback loop is fully closed and mechanically proven:

```
Gauntlet Review
    |
    v
gauntlet_process_issues()
    |-- credits rules cited by reviewers
    |-- persists credited rule IDs to SQLite (gauntlet_credits table)
    v
log_reward(outcome="accepted")
    |-- reads latest gauntlet_credits from SQLite
    |-- calls bandit.batch_update(rules, reward)
    v
qortex Learner (Thompson Sampling)
    |-- Beta(alpha, beta) posteriors shift
    |-- next select() favors rules with higher posteriors
```

**The gauntlet is the sole feedback source.** Rules get credited when cited in reviews, not from session selection. This eliminates the credit assignment problem: only rules that demonstrably contributed to review quality get reinforced.

Each gauntlet citation followed by a reward acceptance increments alpha in the Beta posterior. A rule that starts at Beta(1,1) with mean 0.5 (uniform prior / no evidence) converges toward 1.0 as it accumulates positive evidence, making it increasingly likely to be selected for future sessions.

## What Else Is In the Box

- **LLM-backed extraction:** when regex isn't enough, the seed engine can use OpenAI, Anthropic, or Ollama to extract patterns from code and logs. Metered backend tracks token usage and cost.
- **Global SQLite storage:** all buildlog data is stored in a single global database at `~/.buildlog/buildlog.db` (SQLite with WAL mode, schema v6). Project isolation via hashed project IDs derived from git remote URLs. Legacy per-project JSON/JSONL files are still supported as a fallback.
- **Migration and export:** `buildlog migrate` converts legacy JSON/JSONL files to the global database (idempotent, non-destructive). `buildlog export` dumps data back to JSONL for portability or backup.
- **Ambient emission protocol:** mistakes and learned rules are automatically emitted as JSON artifacts to `~/.buildlog/emissions/pending/` for offline ingestion by downstream systems (knowledge graphs, analytics). Fire-and-forget -- emission failure never breaks the primary operation.
- **Workflow enforcement:** `buildlog verify` checks your setup (CLAUDE.md workflow section, MCP registration, branch protection hooks) and `--fix` repairs it. `buildlog init` installs pre-commit hooks that prevent direct commits to main.
- **Interactive dashboard:** `buildlog viz` launches a [marimo](https://marimo.io) notebook in your browser with live visualizations of reward trends, bandit posteriors, session history, mistake analysis, and insight breakdowns.
- **MCP server:** buildlog exposes 35 tools as an MCP server so agents can query seeds, skills, and build history programmatically during sessions.
- **npm wrapper:** `npx @peleke.s/buildlog` for JS/TS projects. Thin shim that finds and invokes the Python CLI.

## Current Limits

This is v0.20, not the end state.

- **Extraction quality is uneven.** Regex extractors miss nuance; LLM extractors are accurate but expensive. The middle ground is still being found.
- **Single-agent only.** Multi-agent coordination (shared learning across agents) is designed but not implemented.
- **Long-horizon learning is not modeled.** The bandit operates per-session. Longer arcs of competence building need richer policy models.

### What's next

Two layers building on the global SQLite backend and qortex integration:

1. **Cross-project convergence** -- detect rules independently rediscovered across projects, track salience
2. **Emergent rule graphs** -- cluster embeddings into concept nodes, derive edges from co-occurrence and bandit correlation, contextual bandits with embedding-space context vectors (LinUCB)

Embedding persistence via sqlite-vec is already available through the qortex learning backend.

See the [full roadmap](https://peleke.github.io/buildlog-template/roadmap/) for details.

## Installation

**Requires Python >= 3.11**

### Always-On Mode (recommended)

We run buildlog as an **ambient data capture layer** across all projects. One command, works everywhere:

```bash
pipx install buildlog         # or: uv tool install buildlog
buildlog init-mcp --global -y # registers MCP + writes instructions to ~/.claude/CLAUDE.md
```

That's it. Claude Code now has all 35 buildlog tools **and knows how to use them** in every project you open. No per-project setup needed.

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

### Dependencies

Core dependencies installed automatically:

| Package | Purpose |
|---------|---------|
| `qortex-learning` | Thompson Sampling backend (default learning engine) |
| `mcp` | MCP server for Claude Code integration |
| `sqlite-vec` | Vector similarity for semantic deduplication |
| `numpy` | Numerical operations for bandit computations |

Optional extras:

```bash
pip install buildlog[viz]         # marimo dashboard + plotly
pip install buildlog[embeddings]  # local sentence-transformers
pip install buildlog[llm]         # Ollama + Anthropic extractors
pip install buildlog[openai]      # OpenAI embeddings
pip install buildlog[qortex-full] # full qortex KG + REST + MCP
pip install buildlog[all]         # everything
```

### Verify installation

```bash
buildlog mcp-test          # verify all 35 tools are registered
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

## Configuration

### Learning backend

buildlog defaults to `qortex-learning` for Thompson Sampling. To force the builtin bandit fallback:

```bash
export BUILDLOG_LEARNING_BACKEND=builtin
```

If `qortex-learning` is not installed, buildlog falls back to the builtin bandit automatically with a warning.

### Session ceremony

Sessions and experiments are optional. `log_mistake()` works without an active session, and the gauntlet can credit rules and update posteriors without any session ceremony.

## Documentation

| Section | Description |
|---------|------------|
| [Installation](https://peleke.github.io/buildlog-template/getting-started/installation/) | Setup, extras, and initialization |
| [Quick Start](https://peleke.github.io/buildlog-template/getting-started/quick-start/) | Full pipeline walkthrough |
| **[Learning Loop E2E](docs/LEARNING-LOOP-E2E.md)** | **Complete 13-step trace with code citations -- the proof** |
| [Core Concepts](https://peleke.github.io/buildlog-template/getting-started/concepts/) | The problem, the claim, and the metric |
| [Theory](https://peleke.github.io/buildlog-template/theory/) | From restaurant intuition to contextual bandits -- the full tutorial |
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
