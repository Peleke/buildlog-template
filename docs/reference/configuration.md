# Configuration Reference

This page documents buildlog's configuration surface: environment variables, config files, directory layout, and install extras.

## Environment Variables

| Variable | Default | Values | Effect |
|----------|---------|--------|--------|
| `BUILDLOG_LEARNING_BACKEND` | `"builtin"` | `"builtin"`, `"qortex"` | Which learning backend to use for Thompson Sampling. See [Learning Backends](../guides/learning-backends.md). |
| `BUILDLOG_COMMIT` | unset | `"1"` (any truthy value) | Set automatically by the pre-commit hook. When set, the hook allows the commit through. You should never need to set this manually. |

buildlog is configured primarily through files, not env vars.

## Config Files

### `~/.buildlog/buildlog.db`

The global SQLite database. All buildlog data for all projects lives here.

- **Created automatically** the first time buildlog runs in any project
- **SQLite WAL mode** for concurrent reads and safe writes
- **Project isolation** via hashed project IDs (SHA-256 of git remote URL or absolute path)
- **Location is not configurable.** It is always `~/.buildlog/buildlog.db`

If this file doesn't exist and you have legacy `.buildlog/*.json` files, buildlog falls back to reading those directly. Run `buildlog migrate` to move data into the global DB.

### `~/.buildlog/interop.yaml`

Configures external seed sources for the `buildlog_ingest_seeds` tool. If this file doesn't exist, buildlog uses a default configuration pointing to qortex.

**Default behavior (no file needed):**

```yaml
# This is what buildlog assumes when interop.yaml doesn't exist:
sources:
  - name: qortex
    pending_dir: ~/.qortex/seeds/pending
    processed_dir: ~/.qortex/seeds/processed
    failed_dir: ~/.qortex/seeds/failed
    signal_log: ~/.qortex/signals/projections.jsonl
```

**Custom configuration:**

```yaml
sources:
  - name: my-custom-source
    pending_dir: ~/my-source/seeds/pending
    processed_dir: ~/my-source/seeds/processed
    failed_dir: ~/my-source/seeds/failed
    signal_log: ~/my-source/signals/log.jsonl

  - name: team-shared
    pending_dir: /shared/team/seeds/pending
    processed_dir: /shared/team/seeds/processed
    failed_dir: /shared/team/seeds/failed

# Safety limits (optional, shown with defaults)
max_file_size: 1048576       # 1 MB max per seed file
max_rules_per_file: 500      # max rules in a single seed file
max_rule_text_length: 10000  # max chars per rule text
```

Each source follows the shared directory protocol:

- **pending/**: Producer drops seed YAML files here
- **processed/**: buildlog moves files here after successful ingest
- **failed/**: buildlog moves files here on failure, with a `.error` JSON sidecar

### `~/.claude.json`

Claude Code's global MCP configuration. buildlog registers itself here when you run `buildlog init-mcp --global`.

```json
{
  "mcpServers": {
    "buildlog": {
      "command": "buildlog-mcp",
      "args": []
    }
  }
}
```

You normally don't edit this by hand. `buildlog init-mcp --global -y` writes it.

### `~/.claude/CLAUDE.md`

Global instructions for Claude Code. buildlog appends a section here with tool usage instructions so Claude proactively uses buildlog in every session.

Written by `buildlog init-mcp --global -y`. Contains the core loop instructions and a tool quick-reference.

### `.claude/settings.json` (per-project)

Per-project MCP configuration. Written by `buildlog init-mcp` (without `--global`) or `buildlog init --defaults`.

```json
{
  "mcpServers": {
    "buildlog": {
      "command": "buildlog-mcp",
      "args": []
    }
  }
}
```

### `CLAUDE.md` (per-project)

Per-project agent instructions. `buildlog init --defaults` appends a buildlog integration section with tool documentation, workflow instructions, and reference file locations.

This file also receives promoted rules in a marker-delimited section:

```markdown
<!-- buildlog:rules:start -->
## Learned Rules (buildlog, updated 2026-02-13)
### Architectural
- Always define interfaces before implementations
<!-- buildlog:rules:end -->
```

And a workflow enforcement section:

```markdown
<!-- buildlog:workflow:start -->
## Standard Development Workflow (buildlog-enforced)
...
<!-- buildlog:workflow:end -->
```

Both sections are managed by buildlog and updated in-place using the HTML comment markers.

## Directory Layout

### Global (`~/.buildlog/`)

```
~/.buildlog/
├── buildlog.db          # global SQLite database
├── interop.yaml         # seed source configuration (optional)
└── emissions/
    ├── pending/         # emitted artifacts waiting for consumers
    ├── processed/       # consumed artifacts (moved by consumer)
    ├── failed/          # failed artifacts (moved by consumer)
    └── signal.jsonl     # append-only emission event log
```

### Per-project (`buildlog/`)

```
my-project/
├── buildlog/
│   ├── .buildlog/
│   │   ├── seeds/                  # seed YAML files (personas)
│   │   ├── promoted.json           # promoted skill IDs
│   │   ├── rejected.json           # rejected skill IDs
│   │   ├── review_learnings.json   # learnings from gauntlet reviews
│   │   ├── reward_events.jsonl     # legacy reward signals
│   │   ├── sessions.jsonl          # legacy session tracking
│   │   ├── mistakes.jsonl          # legacy mistake tracking
│   │   ├── active_session.json     # current active session
│   │   └── bandit_state.jsonl      # legacy Thompson Sampling state
│   ├── TEMPLATE.md                 # entry template
│   └── 2026-02-13-my-feature.md   # dated entries
├── CLAUDE.md
└── .claude/
    └── settings.json               # per-project MCP config
```

**Note:** The `.buildlog/*.jsonl` and `.buildlog/*.json` files are the legacy storage format. New installs use the global SQLite database at `~/.buildlog/buildlog.db`. Run `buildlog migrate` if you still have these files.

### Emissions directory (`~/.buildlog/emissions/`)

The emission protocol writes JSON artifacts for downstream consumers (e.g., knowledge graphs, analytics pipelines). Emission failures never break primary operations.

Artifact types:

- `mistake_manifest`: emitted when `buildlog_log_mistake()` is called
- `learned_rules`: emitted when `buildlog_learn_from_review()` is called

Artifacts are JSON files named `{type}_{project_id}_{timestamp}.json` in `pending/`. A consumer reads from `pending/`, processes, and moves to `processed/` or `failed/`.

## Seed File Format

Seed files are YAML files defining curated reviewer persona rules. They live in `.buildlog/seeds/` or are bundled with the buildlog package.

```yaml
persona: security_karen
version: 1
rules:
  - rule: "Parameterize all SQL queries"
    category: security
    context: "Any code constructing SQL from user input"
    antipattern: "String concatenation or f-strings with user data in SQL"
    rationale: "SQL injection is OWASP A03 - prevents data breach"
    tags: [sql, injection, owasp]
    references:
      - url: "https://owasp.org/Top10/A03_2021-Injection/"
        title: "OWASP A03:2021 Injection"
    provenance:                    # optional, for externally-generated rules
      id: "qortex:security:sql_injection"
      source_domain: "qortex"
      graph_version: "v2.1"
```

**Required fields per rule:** `rule`

**Optional fields per rule:** `category` (default: "general"), `context`, `antipattern`, `rationale`, `tags`, `references`, `provenance`

**Provenance:** When a seed rule has a `provenance.graph_version` field and the seed file is re-imported with a different version, buildlog decays the corresponding bandit arm. This prevents stale learned signal from persisting when the upstream source changes.

### Seed resolution order

buildlog looks for seed files in this order (first match wins):

1. `.buildlog/seeds/` (local project overrides)
2. `buildlog/.buildlog/seeds/` (buildlog template structure)
3. Package bundled seeds (installed with pip)

## Install Extras

buildlog has optional dependency groups for features that need extra packages.

### Decision tree: which extra do you need?

**Do you want semantic deduplication of rules?**

- Yes, and I want it offline (no API calls): `pip install buildlog[embeddings]`
- Yes, and I'm fine with API calls to OpenAI: `pip install buildlog[openai]`
- No, basic string matching is fine. The base install is enough.

**Do you want LLM-backed extraction (richer pattern extraction from entries)?**

- Yes, using a local model (Ollama): `pip install buildlog[ollama]`
- Yes, using Claude (Anthropic API): `pip install buildlog[anthropic]`
- Yes, both local and cloud: `pip install buildlog[llm]`
- No, regex extraction is fine. The base install is enough.

**Do you want the qortex learning backend?**

- Yes: `pip install buildlog[qortex]` (requires Python 3.11+)
- No, the builtin Thompson Sampling bandit is fine. The base install is enough.

**Do you want everything?**

- `pip install buildlog[all]`

### Full extras table

| Extra | What it adds | Dependencies | Python |
|-------|-------------|--------------|--------|
| `embeddings` | Local sentence-transformers for semantic dedup | `sentence-transformers>=2.2.0` | 3.11+ |
| `openai` | OpenAI embeddings for semantic dedup | `openai>=1.0.0` | 3.11+ |
| `ollama` | Local LLM extraction via Ollama | `ollama>=0.4.0` | 3.11+ |
| `anthropic` | Cloud LLM extraction via Anthropic Claude | `anthropic>=0.40.0` | 3.11+ |
| `llm` | Both `ollama` and `anthropic` | both | 3.11+ |
| `qortex` | Pluggable learning backend with credit propagation | `qortex>=0.3.6` | 3.11+ |
| `engine` | Documents the engine namespace (no extra deps) | none | 3.11+ |
| `mcp` | Kept for backwards compat (MCP is now a default dep) | none | 3.11+ |
| `all` | Everything above | all of the above | 3.11+ |
| `dev` | Development tools (pytest, black, mypy, etc.) | testing/linting stack | 3.11+ |

### Base dependencies (always installed)

These come with every `pip install buildlog`:

- `copier>=9.0.0`: template engine for `buildlog init`
- `click>=8.0.0`: CLI framework
- `pyyaml>=6.0.0`: seed file parsing
- `numpy>=1.21.0`: numerical operations
- `pymupdf>=1.26.7`: PDF processing
- `mcp>=1.0.0`: MCP server protocol
- `sqlite-vec>=0.1.6`: vector operations for SQLite

## Entry Points

buildlog registers two CLI entry points:

| Command | Entry Point | Purpose |
|---------|-------------|---------|
| `buildlog` | `buildlog.cli:main` | Main CLI for all commands |
| `buildlog-mcp` | `buildlog.mcp.server:main` | MCP server (launched by Claude Code) |

The `buildlog-mcp` entry point is what Claude Code invokes. You don't call it directly. It's registered in `~/.claude.json` or `.claude/settings.json`, and Claude Code manages its lifecycle.

## Agent Render Targets

When promoting rules, the `--target` flag controls where rules are written:

| Target | File | Agent |
|--------|------|-------|
| `claude_md` | `CLAUDE.md` | Claude Code |
| `cursor` | `.cursor/rules/buildlog-rules.mdc` | Cursor |
| `copilot` | `.github/copilot-instructions.md` | GitHub Copilot |
| `windsurf` | `.windsurf/rules/buildlog-rules.md` | Windsurf |
| `continue` | `.continue/rules/buildlog-rules.md` | Continue.dev |
| `settings_json` | `.vscode/settings.json` | VS Code (generic) |
| `skill` | Agent Skills format | Agent-agnostic |

The same knowledge base renders to every format.
