<div align="center">

# buildlog

### The Only Agent Learning System You Can Prove Works

[![PyPI](https://img.shields.io/pypi/v/buildlog?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/buildlog/)
[![Python](https://img.shields.io/pypi/pyversions/buildlog?style=for-the-badge&logo=python&logoColor=white)](https://python.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/Peleke/buildlog-template/ci.yml?branch=main&style=for-the-badge&logo=github&label=CI)](https://github.com/Peleke/buildlog-template/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue?style=for-the-badge&logo=github)](https://peleke.github.io/buildlog-template/)

**Falsifiable claims. Measurable outcomes. No vibes.**

<img src="assets/hero-banner-perfectdeliberate.png" alt="buildlog - The Only Agent Learning System You Can Prove Works" width="800"/>

> **RE: The art** — Yes, it's AI-generated. Yes, that's hypocritical for a project about rigor over vibes. Looking for an actual artist to pay for a real logo. If you know someone good, [open an issue](https://github.com/Peleke/buildlog-template/issues) or DM me. Budget exists.

**[Read the full documentation](https://peleke.github.io/buildlog-template/)**

</div>

---

Everyone's building "agent memory." Blog posts announce breakthroughs. Products ship with "learning" in the tagline. Ask them one question: **How do you know it works?**

buildlog gives you the infrastructure to answer with data. It captures engineering knowledge from work sessions, extracts rules, selects which rules to surface using a Thompson Sampling bandit, and measures impact via Repeated Mistake Rate (RMR) across tracked experiments.

## Features

- **Structured capture** — Document work sessions as entries with mistakes, decisions, and outcomes
- **Rule extraction** — Distill and deduplicate patterns into actionable rules
- **Thompson Sampling bandit** — Automatic rule selection that balances exploration and exploitation
- **Experiment tracking** — Sessions, mistakes, RMR calculation with statistical rigor
- **Review gauntlet** — Curated reviewer personas (Security Karen, Test Terrorist) with HITL checkpoints
- **Multi-agent support** — Render rules to Claude Code, Cursor, GitHub Copilot, Windsurf, Continue.dev
- **MCP server** — Full Claude Code integration via `buildlog-mcp`

## Quick Start

```bash
uv pip install buildlog   # or: pip install buildlog (inside a venv)
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

MIT License — see [LICENSE](./LICENSE)

---

<div align="center">

**"Agent learning" without measurement is just prompt engineering with extra steps.**

**buildlog is measurement.**

</div>
