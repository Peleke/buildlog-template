<div align="center">

# buildlog

### Engineering Notebook for AI-Assisted Development

[![PyPI](https://img.shields.io/badge/PyPI-0.1.0-blue?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/buildlog/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

**Capture your work as publishable content. Include the fuckups.**

<img src="assets/hero.png" alt="Chaos to Order - buildlog transforms messy development sessions into structured knowledge" width="800"/>

[Quick Start](#-quick-start) · [The Pipeline](#-the-pipeline) · [Commands](#-commands) · [Philosophy](#-philosophy)

---

</div>

## The Problem

You're pairing with AI on real work. Hours of debugging, wrong turns, "oh shit" moments, and hard-won insights—all vanishing into chat history the moment you close the tab.

Meanwhile, your AI agent makes the same mistakes on similar problems because it has no memory of what you learned together.

## The Solution

**buildlog** captures the signal from AI-assisted development sessions and transforms it into:

1. **Publishable content** - Each entry is a $500+ tutorial draft
2. **Structured patterns** - Categorized insights ready for analysis
3. **Agent-consumable skills** - Deduplicated rules that can improve future AI behavior

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Raw Sessions  │ ──▶  │  Buildlog Entry │ ──▶  │  Agent Skills   │
│   (ephemeral)   │      │  (structured)   │      │  (actionable)   │
└─────────────────┘      └─────────────────┘      └─────────────────┘
     Chat logs            Markdown files          YAML/JSON rules
     Screen shares        with categories         that agents can
     Debugging noise      and improvements        actually use
```

---

## ✨ Features

### 📝 Structured Capture
Templates with six required sections ensure you never forget to document the mistakes that teach the most.

### 📊 Pattern Distillation
Extract categorized insights from all your entries into structured JSON/YAML for analysis.

### 🧠 Semantic Deduplication
"Run tests before commit" and "Always execute the test suite prior to committing" are the same insight. buildlog merges them.

### 🤖 Agent-Ready Skills
Generate rules your AI agent can consume—with stable IDs, confidence scores, and source tracking.

### 🔌 Pluggable Embeddings
Token-based similarity by default. Upgrade to sentence-transformers or OpenAI for semantic understanding.

---

## 🚀 Quick Start

```bash
# Install
pip install buildlog

# Initialize in your project
buildlog init

# Create an entry for today's work
buildlog new auth-api

# After a few entries, extract patterns
buildlog distill

# Generate agent-consumable skills
buildlog skills
```

---

## 🔄 The Pipeline

buildlog is a three-stage pipeline that transforms ephemeral work into durable knowledge:

### Stage 1: Capture (`buildlog new`)

Create structured entries as you work. Each entry has six sections:

| Section | Purpose |
|---------|---------|
| **The Goal** | What you're building and why |
| **What We Built** | Architecture diagram, components |
| **The Journey** | Chronological narrative *including mistakes* |
| **Test Results** | Actual commands, actual outputs |
| **Code Samples** | Key snippets with context |
| **Improvements** | Categorized learnings for next time |

The **Improvements** section is structured for machine extraction:

```markdown
### Architectural
- Always validate inputs at the boundary, not conditionally
- Use frozen dataclasses for immutable data containers

### Workflow
- Run the test suite after EVERY code change, not just at the end
- Write the integration test first to clarify the API contract

### Tool Usage
- The `patch` context manager for date mocking is cleaner than fixtures
- Use `jwt.io` to decode tokens instead of console.log

### Domain Knowledge
- `datetime.utcnow()` is deprecated in Python 3.12+
- Supabase storage returns 400, not 404, for missing files
```

### Stage 2: Distill (`buildlog distill`)

Extract all improvements across entries into structured data:

```bash
buildlog distill                    # JSON to stdout
buildlog distill -o patterns.yaml   # Write to file
buildlog distill --since 2026-01-01 # Filter by date
buildlog distill --category workflow # Filter by category
```

Output:
```json
{
  "patterns": {
    "architectural": [
      {"insight": "Always validate inputs at boundary...", "source": "2026-01-16-auth.md"}
    ],
    "workflow": [...],
    "tool_usage": [...],
    "domain_knowledge": [...]
  },
  "statistics": {
    "total_patterns": 47,
    "by_category": {"architectural": 12, "workflow": 15, ...}
  }
}
```

### Stage 3: Skills (`buildlog skills`)

Transform raw patterns into deduplicated, scored rules:

```bash
buildlog skills                           # YAML to stdout
buildlog skills -o skills.yml             # Write to file
buildlog skills --format markdown         # For CLAUDE.md injection
buildlog skills --min-frequency 2         # Only repeated patterns
buildlog skills --embeddings openai       # Semantic deduplication
```

Output:
```yaml
generated_at: '2026-01-16T12:00:00Z'
source_entries: 23
total_skills: 31
skills:
  architectural:
    - id: arch-b0fcb62a1e
      rule: Always validate inputs at the boundary, not conditionally
      frequency: 4
      confidence: high
      sources: [auth.md, api.md, validation.md, forms.md]
      tags: [api, error]
    - id: arch-0cda924aeb
      rule: Frozen dataclasses should be the default for data containers
      frequency: 2
      confidence: medium
      sources: [models.md, dto.md]
      tags: [python]
```

---

## 🧠 Patterns vs Skills

**Patterns** are raw extractions—every insight from every entry, exactly as written.

**Skills** are processed rules with:

| Property | Description |
|----------|-------------|
| **Stable ID** | Same rule always gets same ID (SHA-256 based) |
| **Deduplication** | Similar insights merged, frequency tracked |
| **Confidence** | high/medium/low based on frequency + recency |
| **Sources** | Which entries contributed to this skill |
| **Tags** | Auto-extracted technology/concept keywords |

### Deduplication in Action

Raw patterns from different entries:
```
- "Run tests before committing"
- "Always run the test suite before commit"
- "Execute tests prior to committing code"
```

After deduplication → **1 skill** with `frequency: 3`:
```yaml
- id: wf-96f12966f1
  rule: Run tests before committing
  frequency: 3
  confidence: high
```

---

## 🔌 Embedding Backends

Deduplication uses text similarity. Choose your backend:

| Backend | Install | Use Case |
|---------|---------|----------|
| `token` (default) | Built-in | Fast, free, good for obvious duplicates |
| `sentence-transformers` | `pip install buildlog[embeddings]` | Local semantic similarity, no API calls |
| `openai` | `pip install buildlog[openai]` | Best quality, requires API key |

```bash
# Token-based (default) - catches "run tests" ≈ "run testing"
buildlog skills

# Semantic - catches "use Redis for caching" ≈ "cache data in Redis"
buildlog skills --embeddings sentence-transformers

# OpenAI - best quality semantic matching
export OPENAI_API_KEY=...
buildlog skills --embeddings openai
```

### Comparison

| Input | Token | OpenAI |
|-------|:-----:|:------:|
| "Run tests before commit" ≈ "Run testing before committing" | ✅ Merged | ✅ Merged |
| "Use Redis for caching" ≈ "Cache data in Redis" | ❌ Separate | ✅ Merged |

---

## 🤖 Practical Usage: Making Your Life Easier

### 1. Inject Skills into CLAUDE.md

```bash
buildlog skills --format markdown >> CLAUDE.md
```

Your AI agent now has access to every lesson you've learned:

```markdown
## Learned Skills

Based on 23 buildlog entries, 31 actionable skills have emerged:

### Architectural (8 skills)
- 🟢 **Always validate inputs at the boundary** (seen 4x)
- 🟡 **Use frozen dataclasses for data containers** (seen 2x)

### Workflow (12 skills)
- 🟢 **Run tests after EVERY code change** (seen 5x)
...
```

### 2. Track Skill Evolution

Skills have stable IDs. Track which skills are reinforced over time:

```bash
# This week's new skills
buildlog skills --since 2026-01-10 -o this-week.yml

# Compare to baseline
diff baseline-skills.yml this-week.yml
```

### 3. Find Your Blind Spots

```bash
buildlog stats --detailed
```

```
📊 Buildlog Statistics
═══════════════════════════════════════

Entries: 23 total
Coverage: 87% with improvements

Category Breakdown:
  architectural:    12 insights (26%)
  workflow:         15 insights (33%)
  tool_usage:        8 insights (17%)
  domain_knowledge: 11 insights (24%)

⚠️  Warnings:
  - 3 entries have empty Improvements sections
```

### 4. Build a Personal Knowledge Base

```bash
# Weekly cron job
buildlog skills -o ~/.buildlog/skills-$(date +%Y-%m-%d).yml
```

Over time, you build a corpus of everything you've learned—searchable, diffable, and agent-consumable.

---

## 📋 Commands

| Command | Description |
|---------|-------------|
| `buildlog init` | Initialize in current directory |
| `buildlog new <slug>` | Create entry for today |
| `buildlog new <slug> --date 2026-01-15` | Create entry for specific date |
| `buildlog list` | List all entries |
| `buildlog distill` | Extract patterns from all entries |
| `buildlog stats` | Show statistics and analytics |
| `buildlog skills` | Generate agent-consumable skills |
| `buildlog update` | Update templates to latest |

### Skills Options

```bash
--output, -o PATH       # Write to file instead of stdout
--format [yaml|json|markdown]  # Output format (default: yaml)
--min-frequency N       # Only skills seen N+ times
--since YYYY-MM-DD      # Only entries from this date
--embeddings [token|sentence-transformers|openai]  # Similarity backend
```

---

## 🏗️ Architecture

```
buildlog/
├── cli.py              # Click CLI commands
├── distill.py          # Pattern extraction from markdown
├── stats.py            # Analytics and coverage metrics
├── skills.py           # Skill generation with deduplication
├── embeddings.py       # Pluggable similarity backends
├── core/               # Core business logic
│   └── operations.py   # status, promote, reject, diff
├── render/             # Output adapters
│   ├── claude_md.py    # Append rules to CLAUDE.md
│   └── settings_json.py# Merge rules into settings.json
└── mcp/                # MCP server (thin wrappers)
    ├── server.py       # FastMCP server setup
    └── tools.py        # Tool implementations

User's Project/
└── buildlog/
    ├── _TEMPLATE.md           # Entry template
    ├── 2026-01-15-auth-api.md
    ├── 2026-01-16-bugfix.md
    └── ...
```

### Data Flow

```
buildlog/*.md
      │
      ▼ parse markdown, extract Improvements
┌─────────────────┐
│  distill_all()  │ → patterns by category
└────────┬────────┘
         │
         ▼ deduplicate, score, tag
┌─────────────────┐
│ generate_skills()│ → SkillSet with stable IDs
└────────┬────────┘
         │
         ▼ format output
┌─────────────────┐
│ format_skills() │ → YAML / JSON / Markdown
└─────────────────┘
```

---

## 🧪 Installation Options

```bash
# Basic install
pip install buildlog

# With local semantic embeddings (offline)
pip install buildlog[embeddings]

# With OpenAI embeddings
pip install buildlog[openai]

# Everything
pip install buildlog[all]

# Development
pip install buildlog[dev]

# With MCP server for Claude Code integration
pip install buildlog[mcp]
```

---

## 🔗 MCP Server (Claude Code Integration)

The MCP server lets Claude Code interact with your buildlog skills directly. Your agent can review learned patterns, promote them to rules, or reject false positives—all through natural conversation.

### Setup

1. Install with MCP support:
   ```bash
   pip install buildlog[mcp]
   ```

2. Add to your Claude Desktop config (`~/.config/claude/claude_desktop_config.json`):
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

3. Restart Claude Desktop.

### Available Tools

| Tool | Description |
|------|-------------|
| `buildlog_status` | Get skills grouped by category with confidence scores |
| `buildlog_promote` | Write high-confidence skills to CLAUDE.md or settings.json |
| `buildlog_reject` | Mark skills to exclude from future suggestions |
| `buildlog_diff` | Show skills pending review (not yet promoted/rejected) |

### Example Conversation

```
You: What patterns have I learned?

Claude: [calls buildlog_status]
        Based on 23 buildlog entries, you have 31 skills:

        High confidence (ready to promote):
        - arch-b0fcb62a1e: "Always validate inputs at the boundary"
        - wf-96f12966f1: "Run tests before committing"

        Would you like me to add these to your CLAUDE.md?

You: Yes, promote the high-confidence ones.

Claude: [calls buildlog_promote]
        Added 8 rules to CLAUDE.md. These patterns will now
        influence my behavior in future sessions.
```

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     Claude Code Session                          │
│                                                                  │
│  1. Claude calls buildlog_status                                │
│     → Runs generate_skills() on-demand                          │
│     → Returns skills with confidence scores                     │
│                                                                  │
│  2. User reviews and approves                                   │
│                                                                  │
│  3. Claude calls buildlog_promote                               │
│     → Appends rules to CLAUDE.md                                │
│     → Tracks promoted IDs in .buildlog/promoted.json            │
└─────────────────────────────────────────────────────────────────┘
```

The MCP server is **stateless**—skills are generated fresh on each request from your buildlog entries. No daemon, no database, no background processes.

---

## 📜 Philosophy

### 1. Write Fast, Not Pretty
Refrigerator to-do list energy. Get it down before you forget.

### 2. Never Delete Mistakes
Wrong turns are the most valuable content. They're what makes tutorials actually useful.

### 3. Include the Journey
"We tried X, it failed because Y, so we did Z" > "We did Z"

### 4. Capture Improvements
Concrete learnings, not vague observations. "Always validate at boundary" > "validation is important"

### 5. Quality Bar
Each entry should be publishable as a **$500+ tutorial**. Real error messages. Honest about what didn't work. Code that runs.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](./LICENSE) for details.

---

<div align="center">

**Your AI pair programmer should learn from your mistakes.**

**buildlog makes that possible.**

[⬆ Back to top](#buildlog)

</div>
