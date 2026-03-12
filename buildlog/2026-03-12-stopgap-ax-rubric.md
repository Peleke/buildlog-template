# Build Journal: Eating Our Own Cooking — ax-rubric vs buildlog

**Date:** 2026-03-12
**Duration:** Ongoing
**Status:** Partial

---

## The Goal

We wrote an article called ["I Don't Deliberate About This"](https://peleke.me/writing/ax-04-tool-descriptions) arguing that most MCP tool descriptions are invisible to agents. We published a rubric. We started building a distribution system for it (brunnr). Now it's time to use the rubric on our own tools and find out how bad it is.

Spoiler: mean score 2.3/5. Zero tools at 5/5. The tool that tracks whether agents are learning from their mistakes has a description so vague that no agent will ever call it voluntarily. Physician, heal thyself.

This is the buildlog side of issue #218 (Stopgap: Agent Experience Improvements). The work is also a live test case for the ax-rubric skill we're packaging in brunnr — and material for a follow-on to the AX article.

---

## What We Built

### The Audit

Ran the AX Description Rubric against all 32 registered buildlog MCP tools. Five binary criteria per tool: output shape, cost signal, trigger clarity, specificity, differentiation.

| Score | Count | Band |
|-------|-------|------|
| 5/5 | 0 | Habitual (never reached) |
| 4/5 | 3 | Habitual |
| 3/5 | 11 | Marginal |
| 2/5 | 11 | Invisible |
| 1/5 | 7 | Invisible |

**Mean: 2.3/5. Median: 2/5.**

### Systemic Failures

1. **Cost signal: 0/32 pass.** Not a single tool states expected response size. The article's principle #2 ("State the cost") fails across the board on our own tools.

2. **The distill/skills/status/diff cluster.** Four tools that all claim to return "patterns" or "skills" with no pipeline ordering in the descriptions. An agent seeing all 32 tools cannot distinguish them without reading source code. This is exactly the "category list" anti-pattern from the article.

3. **Trigger clarity defaults to passive voice.** "Use this to see...", "Useful for...", "Returns... for analysis." The article says "specify the trigger." We didn't.

### The Worst Offenders (1/5)

| Tool | Current first sentence | Why it's invisible |
|------|----------------------|-------------------|
| `buildlog_status` | "Get current skills extracted from buildlog entries." | Indistinguishable from `skills` and `distill` |
| `buildlog_diff` | "Show skills pending promotion or rejection." | No output shape, no trigger, no cost |
| `buildlog_distill` | "Extract patterns from all buildlog entries." | "patterns" = same word as 3 other tools |
| `buildlog_skills` | "Generate agent-consumable skills from buildlog patterns." | "patterns" → "skills" → "rules" used interchangeably |
| `buildlog_stats` | "Show buildlog statistics and analytics." | "insights" is meaningless |
| `buildlog_experiment_metrics` | "Get per-session or aggregate mistake rates and rule changes." | Overlaps `experiment_report` completely |
| `buildlog_experiment_report` | "Generate comprehensive report." | "comprehensive" = no shape |

### The Best (4/5)

| Tool | Why it works |
|------|-------------|
| `buildlog_log_reward` | Clear trigger ("after agent work"), specific action, well-differentiated. Missing only cost signal. |
| `buildlog_rewards` | Output shape documented, bounded by limit param. Missing only trigger. |
| `buildlog_gauntlet_issues` | Clear trigger ("after running a gauntlet review"), specific action, returns documented. Missing only cost signal. |

---

## The Journey

### Phase 1: Confirming the Obvious

**What we tried:** Ran the rubric against our own tools. Expected roughly 1/5 across the board because these descriptions were never deliberately designed — they were vibe-coded out of nowhere, docstrings written to satisfy a schema, not to inform a decision.

**What happened:** 2.3/5 average. Slightly better than expected, but the distribution tells the real story: 7 tools at 1/5 (invisible), 11 at 2/5 (still invisible), 11 at 3/5 (marginal). The three tools that scored 4/5 — `log_reward`, `rewards`, `gauntlet_issues` — are the ones we iterated on most because we actually use them in every session. The rest? Generated once, never revisited.

**The vibe-coding connection:** This is a microcosm of the entire vibe-coding phenomenon. The rubric was literally developed in relation to these specific tools — the anonymized example in the article ("Query the knowledge base for structured learnings, patterns, and skills relevant to your current work context") is a composite of real buildlog descriptions. We wrote an article criticizing exactly this pattern, published a rubric to detect it, and the tools that inspired the rubric still had the problem. Because nobody went back and applied the rubric. Because that's how vibe-coding works: you generate, you ship, you don't revisit. The rubric existing doesn't fix anything. Running it does.

**Lesson:** The gap between knowing and doing is a tool call. The rubric has to be in the workflow, not in the article.

### Phase 2: The Rewrite (WS-5)

**What we tried:** Rewrote all 32 docstrings following the 7 principles from the article.

**Key patterns applied:**
- Lead with the problem: "Need to decide which learned rules to promote?" not "Get current skills"
- State the cost: "Response: ~500 tokens" on every tool
- Specify the trigger: "Call after `buildlog_skills()` has run" not "Use this to see patterns"
- Bound the output: "Returns a dict with 4 category keys, each containing 0-20 skill objects" not "Returns skills"
- Differentiate: "For gauntlet reviews, use `buildlog_gauntlet_issues()` instead — it calls this internally"

---

## The Distribution Problem (brunnr)

We tried to package the ax-rubric as a distributable skill. Three attempts:

1. **Claude Code slash command in .claude/skills/**: Works locally, no distribution mechanism.
2. **npm package**: Agents can't install npm packages mid-session. Dead end.
3. **brunnr**: Built our own skill registry and distribution system. `brunnr install ax-rubric` installs the skill as a Claude Code slash command. `brunnr eval ax-rubric` runs it against test fixtures.

The gap: there is no standard way to distribute agent-facing skills across projects. MCP servers distribute tools. But a rubric isn't a tool — it's a prompt + evaluation logic + test fixtures. The industry hasn't solved this yet. We're solving it with brunnr, which treats skills as first-class distributable artifacts with their own eval harness.

---

## Improvements

### Architectural

- Tool descriptions are the smallest unit of agent experience design — but they're also the most neglected. We had 32 tools and spent zero intentional design effort on their descriptions. The descriptions were afterthoughts written to satisfy the MCP schema, not to help agents decide.
- The pipeline `distill → skills → status → diff → promote/reject` needs to be legible IN the descriptions, not just in the code. Agents don't read source.

### Workflow

- Run ax-rubric as a pre-merge check on any PR that adds or modifies MCP tools. If a tool scores below 4/5, the PR should not merge. This is exactly the kind of mechanical enforcement we advocate.
- The rubric evaluation should be part of the gauntlet itself — a meta-gauntlet persona that reviews tool descriptions.

### Tool Usage

- `buildlog_consume_emissions` exists in tools.py but isn't registered in server.py. Either register it with a good description or delete it. Zombie tools are worse than missing tools.

### Domain Knowledge

- Every tool description in every MCP server in every project is probably 2/5. This isn't a buildlog problem. It's an industry problem. The article was right; we just hadn't applied it to ourselves.
- The rubric's five criteria are necessary but not sufficient. Response design (so_what, token_cost in response, confidence scores) matters equally. Part II of the article should cover the response side.

---

## Files Changed

```
src/buildlog/mcp/
├── tools.py      # All 32 tool docstrings rewritten
└── server.py     # Register new gauntlet_rule_lookup tool
```

---

*Follow-on: AX article Part II — "We Used the Rubric on Our Own Tools and It Was Bad." Also: brunnr distribution story for the skill registry angle.*
