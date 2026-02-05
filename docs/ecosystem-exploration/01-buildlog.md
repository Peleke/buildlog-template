# buildlog - Working Memory Layer

**Date Explored**: 2026-02-04
**Location**: /Users/peleke/Documents/Projects/buildlog-template
**Version**: 0.10.4
**Status**: Production

## Executive Summary

buildlog is a "measurable learning loop for AI-assisted work" - an engineering notebook + statistical framework for proving whether AI agents actually learn over time.

## Core Thesis

> "Every AI framework has memory storage, retrieval, and evaluation. None of them measure whether memory actually improves outcomes."

buildlog closes this gap by providing:
1. **Structured capture** of work trajectories (sessions, decisions, outcomes)
2. **Pattern extraction** as "seeds" (atomic rules)
3. **Selection policy** using Thompson Sampling bandits
4. **Measurement via Repeated Mistake Rate (RMR)** - statistical evidence of improvement

## Architecture

### Core Modules (41 Python files)

**Foundation:**
- `cli.py` (78KB) - Main CLI interface, 100+ commands
- `core/operations.py` - Core business logic exposed via MCP/CLI/HTTP
- `core/bandit.py` - Thompson Sampling contextual multi-armed bandit
- `constants.py` - Shared CLAUDE.md instructions

**Extraction & Pattern Recognition:**
- `seed_engine/` (7 files) - Pipeline for extracting rules from code/logs
- `distill.py` - Convert entries into patterns
- `skills.py` - Generate and manage skills

**Learning & Statistics:**
- `engine/experiments.py` - Session tracking, mistake logging, RMR calculation
- `engine/bandit.py` - Bandit state management
- `confidence.py` - Confidence scoring (frequency + recency)

**Rendering (Multi-Agent Support):**
- `render/` (7 files) - Render rules to every agent format:
  - CLAUDE.md for Claude Code
  - .cursorrules for Cursor
  - .github/copilot-instructions.md for Copilot
  - Windsurf, Continue.dev, settings.json

**Integration:**
- `mcp/server.py` - MCP server entry point (31 tools exposed)
- `mcp/tools.py` - Tool implementations

### Key Data Structures

**Entry** (journal entry):
- Date, slug, markdown content
- Sections: goals, commits, learnings, improvements

**Skill**:
- ID, title, description, category, confidence
- Condition (when applicable)
- Source reference

**Reward Event** (JSONL):
- Timestamp, rule_id, outcome (accepted/revision/rejected)
- Revision distance, error_class, notes

## Current Features

### 1. Global Always-On Mode
- `buildlog init-mcp --global` registers in `~/.claude.json`
- Creates `~/.claude/CLAUDE.md` with instructions
- Works without per-project init

### 2. Review Gauntlet with Personas
- **Security Karen**: OWASP Top 10, auth, injection, secrets (13 rules)
- **Test Terrorist**: Coverage, property-based, metamorphic, contracts (21 rules)
- **Bragi**: LLM prose patterns (9 rules)
- Auto-loop with severity-based checkpoints

### 3. Thompson Sampling Bandit
- Beta-Bernoulli conjugate model
- Contextual: per error_class
- Seed-boosted priors for expert-curated rules
- Exploration/exploitation tradeoff built-in

### 4. Experiment Tracking
- Session management with mistake logging
- RMR (Repeated Mistake Rate) calculation
- Statistical reporting across sessions

### 5. Skill Extraction & Promotion
- Regex-based extractors (fast, cheap)
- LLM-backed extractors (accurate, metered)
- Semantic deduplication via embeddings
- Promotion to all 5+ agent formats

## Open Issues (87 tracked)

**High Priority:**
- #87: Integrate qortex Knowledge Graph
- #79: Global Always-On Mode (Phase 3)
- #62: npm Publishing + PR Merge Sequence

**Medium Priority:**
- #47: Ontology Generation for Rule Categories
- #46: Real Source Fetching in Seed Engine
- #43: Thompson Sampling Tutorial Series

## Integration Points

### With qortex
- qortex provides external knowledge (long-term memory)
- buildlog provides learned patterns (working memory)
- YAML output format compatible with both

### With openclaw
- buildlog MCP server runs in sandbox
- Learning outcomes feed back as seeds
- Gauntlet findings become agent instructions

## Strategic Positioning

**The Core Claim:**
> "Every agent framework stores memories. None of them know if memories help. We built the measurement layer they forgot."

**Differentiation:**
- Only framework with statistical measurement of learning
- Thompson Sampling bandit built-in (not ad-hoc)
- Multi-agent support (render to any format)
- Honest about limitations (no hype)
