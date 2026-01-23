<div align="center">

# buildlog

### The Only Agent Learning System You Can Prove Works

[![PyPI](https://img.shields.io/pypi/v/buildlog?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/buildlog/)
[![Python](https://img.shields.io/pypi/pyversions/buildlog?style=for-the-badge&logo=python&logoColor=white)](https://python.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/Peleke/buildlog-template/ci.yml?branch=main&style=for-the-badge&logo=github&label=CI)](https://github.com/Peleke/buildlog-template/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

**Falsifiable claims. Measurable outcomes. No vibes.**

<img src="assets/hero-banner-perfectdeliberate.png" alt="buildlog - The Only Agent Learning System You Can Prove Works" width="800"/>

> **RE: The art** — Yes, it's AI-generated. Yes, that's hypocritical for a project about rigor over vibes. Looking for an actual artist to pay for a real logo. If you know someone good, [open an issue](https://github.com/Peleke/buildlog-template/issues) or DM me. Budget exists.

[The Problem](#the-problem) · [The Claim](#the-claim) · [The Mechanism](#the-mechanism) · [Quick Start](#quick-start) · [Review Gauntlet](#review-gauntlet)

---

</div>

## The Problem

Everyone's building "agent memory." Blog posts announce breakthroughs. Tweets show impressive demos. Products ship with "learning" in the tagline.

Ask them one question: **How do you know it works?**

You'll get:
- "It feels smarter"
- "Users report better results"
- "The agent remembers things now"

That's not evidence. That's vibes.

Here's what a real answer looks like:

> "We track Repeated Mistake Rate (RMR) across sessions. Our null hypothesis is that the system makes no difference. After 50 sessions, RMR decreased from 34% to 12% (p < 0.01). The effect size is 0.65. Here's the data."

If you can't say something like that, you don't have agent learning. You have a demo.

---

## The Claim

**buildlog** makes a falsifiable claim:

> **H₀ (Null Hypothesis):** buildlog makes no measurable difference to agent behavior.
>
> **H₁ (Alternative):** Agents using buildlog-learned rules have lower Repeated Mistake Rate than baseline.

We provide the infrastructure to **reject or fail to reject** this hypothesis with your own data.

If buildlog doesn't work, the numbers will show it. That's the point.

---

## The Metric: Repeated Mistake Rate (RMR)

```
RMR = (Mistakes that match previous mistakes) / (Total mistakes logged)
```

A mistake "matches" if it has the same semantic signature—same error class, similar description, same root cause showing up again.

**Why RMR?**
- **Observable**: You can count it
- **Attributable**: Lower RMR after rule injection = signal
- **Meaningful**: Repeating mistakes is the actual pain point

RMR is not the only metric that matters. But it's one we can measure, and measurement is where science starts.

---

## The Mechanism

buildlog is building toward **contextual bandits** for automatic rule selection. Here's where we are:

### What Exists Today (v0.8)

```
┌─────────────────────────────────────────────────────────────────┐
│                    CURRENT INFRASTRUCTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✅ Rule extraction     From entries, reviews, curated seeds   │
│  ✅ Confidence scoring  Frequency + recency based              │
│  ✅ Reward logging      Accept/reject/revision signals         │
│  ✅ Experiment tracking Sessions, mistakes, RMR calculation    │
│  ✅ Review gauntlet     Curated persona-based code review      │
│  ✅ Thompson Sampling   Automatic rule selection via bandit    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Thompson Sampling Bandit (NEW in v0.8)

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXTUAL BANDIT (IMPLEMENTED)              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Context (c):     Error class (e.g., "type-errors")            │
│  Arms (a):        Candidate rules to surface                   │
│  Reward (r):      Binary feedback from mistakes & rewards      │
│                                                                 │
│  Model:           Beta-Bernoulli (conjugate prior)             │
│  Policy:          Thompson Sampling (sample, don't exploit)    │
│  Learning:        Bayesian updates on every feedback signal    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**How it works:**

1. **Session starts** → Bandit samples from Beta distributions, selects top-k rules
2. **Mistake logged** → Selected rules get reward=0 (they didn't prevent the mistake)
3. **Explicit reward** → Rules get reward based on outcome (accepted=1, rejected=0)

**Why Thompson Sampling?**

The magic is in *sampling* instead of using the mean:
- Rules we're uncertain about have high-variance distributions
- High variance → occasional high samples → exploration
- As data accumulates, variance shrinks → exploitation

This naturally balances explore-exploit without tuning hyperparameters.

**Seed-boosted priors:**
Curated rules from gauntlet personas start with boosted priors (Beta(3,1) instead of Beta(1,1)), reflecting our belief that expert-curated rules are likely effective.

---

## The Pipeline

buildlog captures signal at every stage:

```mermaid
flowchart LR
    A["Work Sessions"] --> B["Structured Entries"]
    B --> C["Extracted Rules"]
    C --> D["Bandit Selection"]
    D --> E["Rule Surfaced"]
    E --> F["Human Feedback"]
    F --> G["Reward Logged"]
    G --> H["Bandit Updates"]
    H --> D

    style D fill:#4ecdc4,color:#fff
    style F fill:#ff6b6b,color:#fff
    style G fill:#4ecdc4,color:#fff
    style H fill:#4ecdc4,color:#fff
```

*Thompson Sampling closes the loop: rules are selected based on learned effectiveness, and feedback updates the model.*

### Stage 1: Capture
Document your work. Include the fuckups—they're the most valuable signal.

```bash
buildlog new auth-api
# Edit the markdown, document what happened
```

### Stage 2: Extract
Pull structured rules from your entries.

```bash
buildlog distill    # Extract patterns
buildlog skills     # Deduplicate into rules
```

### Stage 3: Promote
Surface rules to your agent via CLAUDE.md, settings.json, or Agent Skills.

```bash
buildlog promote --target skill
```

### Stage 4: Measure
Track what happens when rules are active.

```bash
buildlog experiment start --error-class "type-errors"
# ... work session ...
buildlog experiment log-mistake --error-class "type-errors" \
  --description "Forgot to handle null case"
buildlog experiment end
buildlog experiment report
```

### Stage 5: Learn
Log reward signals when rules help (or don't).

```python
# Via MCP
buildlog_log_reward(
    skill_id="arch-123",
    reward=1,           # 1 = helped, 0 = didn't help
    context="type-errors",
    outcome="Caught the bug before commit"
)
```

---

## Review Gauntlet

Run your code through ruthless reviewer personas, each with curated rules from authoritative sources.

```bash
# See available reviewers
buildlog gauntlet list

# Output:
# Review Gauntlet Personas
# ==================================================
#   security_karen
#     OWASP Top 10 security review
#     Rules: 13 (v1)
#
#   test_terrorist
#     Comprehensive testing coverage audit
#     Rules: 21 (v1)
#
# Total: 2 personas, 34 rules
```

### Reviewer Personas

| Persona | Focus | Rules |
|---------|-------|-------|
| **Security Karen** | OWASP Top 10, auth, injection, secrets | 13 |
| **Test Terrorist** | Coverage, property-based, metamorphic, contracts | 21 |
| **Ruthless Reviewer** | Code quality, FP principles | Coming soon |

Each rule includes:
- **Context**: When to apply it
- **Antipattern**: What violation looks like
- **Rationale**: Why it matters (with citations)

### Usage

```bash
# Generate a review prompt
buildlog gauntlet prompt src/api.py

# Export rules for manual review
buildlog gauntlet rules --format markdown -o review_checklist.md

# After running a review, persist learnings
buildlog gauntlet learn review_issues.json --source "PR#42"
```

### Gauntlet Loop (Agent Integration)

For AI agents, the gauntlet loop automates the fix-rerun cycle:

```bash
buildlog gauntlet loop src/ --persona security_karen --persona test_terrorist
```

The loop provides structured checkpoints:

| Severity | Action | Human Needed? |
|----------|--------|---------------|
| **Critical** | Agent fixes, reruns | No |
| **Major** | Checkpoint: continue? | Yes |
| **Minor** | Accept risk or fix? | Yes |
| **Clean** | Done | No |

MCP tools for agent integration:
- `buildlog_gauntlet_issues` — Report findings, get next action
- `buildlog_gauntlet_accept_risk` — Accept remaining issues (optionally create GitHub issues)

The gauntlet integrates with the learning loop—issues found become rules that accumulate confidence.

---

## Experiment Infrastructure

buildlog ships with infrastructure to run actual experiments:

```bash
# Start a tracked session
buildlog experiment start --error-class "api-design"

# Log mistakes as they happen
buildlog experiment log-mistake \
  --error-class "api-design" \
  --description "Returned 200 for error case"

# End session
buildlog experiment end

# Get metrics
buildlog experiment metrics

# Full report across all sessions
buildlog experiment report
```

The report includes:
- Total sessions, total mistakes
- Repeat rate (RMR)
- Mistakes by error class
- Rules that correlate with corrections

This is the data you need to make claims.

---

## Quick Start

```bash
# Install
pip install buildlog

# Initialize
buildlog init

# Create your first entry
buildlog new my-feature

# After a few entries, extract rules
buildlog distill
buildlog skills

# Start measuring
buildlog experiment start
# ... work ...
buildlog experiment end
buildlog experiment report
```

### MCP Server (Claude Code Integration)

```bash
pip install buildlog[mcp]
```

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "buildlog": {
      "command": "buildlog-mcp"
    }
  }
}
```

Available tools:
| Tool | Purpose |
|------|---------|
| `buildlog_status` | View rules by category and confidence |
| `buildlog_promote` | Surface rules to agent |
| `buildlog_reject` | Mark false positives |
| `buildlog_diff` | Rules pending review |
| `buildlog_learn_from_review` | Extract rules from code review |
| `buildlog_log_reward` | Record reward signal (updates bandit) |
| `buildlog_start_session` | Begin tracked session (bandit selects rules) |
| `buildlog_log_mistake` | Record mistake (negative feedback to bandit) |
| `buildlog_experiment_report` | Full experiment report |
| `buildlog_bandit_status` | View Thompson Sampling bandit state |
| `buildlog_gauntlet_issues` | Report gauntlet findings, get next action |
| `buildlog_gauntlet_accept_risk` | Accept remaining issues, optionally create GH issues |

### CLI Commands

```bash
buildlog init                    # Initialize buildlog
buildlog new <slug>              # Create entry
buildlog list                    # List entries
buildlog distill                 # Extract patterns
buildlog skills                  # Generate rules
buildlog stats                   # Usage statistics
buildlog reward <outcome>        # Log reward signal

# Experiments
buildlog experiment start        # Begin tracked session
buildlog experiment log-mistake  # Record mistake
buildlog experiment end          # End session
buildlog experiment report       # Full report

# Review Gauntlet
buildlog gauntlet list           # Show reviewers
buildlog gauntlet rules          # Export rules
buildlog gauntlet prompt <path>  # Generate review prompt
buildlog gauntlet learn <file>   # Persist learnings
buildlog gauntlet loop <path>    # Auto-fix loop with HITL checkpoints
```

---

## What This Is Not

**This is not AGI.** This is not "agents that truly learn." This is not a revolution.

This is:
- A structured way to capture engineering knowledge
- A bandit framework for rule selection
- Infrastructure to measure whether it works

Boring? Maybe. But boring things that work beat exciting things that don't.

---

## The Falsification Protocol

Want to test whether buildlog actually helps? Here's the protocol:

1. **Baseline**: Run N sessions without buildlog rules active. Log mistakes.
2. **Treatment**: Run N sessions with buildlog rules active. Log mistakes.
3. **Compare**: Calculate RMR for both conditions.
4. **Statistical test**: Two-proportion z-test or chi-squared.
5. **Report**: Effect size, confidence interval, p-value.

If p > 0.05, we fail to reject the null. buildlog didn't help. That's a valid outcome.

If p < 0.05, we have evidence of an effect. How big? Check the effect size.

This is how you know. Not vibes. Data.

---

## Theoretical Foundations

For the technically curious:

| Concept | Application in buildlog | Status |
|---------|------------------------|--------|
| **Confidence scoring** | Frequency + recency decay | ✅ Implemented |
| **Semantic hashing** | Mistake deduplication for RMR | ✅ Implemented |
| **Reward signals** | Binary feedback infrastructure | ✅ Implemented |
| **Thompson Sampling** | Rule selection under uncertainty | ✅ Implemented (v0.8) |
| **Beta-Bernoulli model** | Posterior updates from binary reward | ✅ Implemented (v0.8) |
| **Contextual bandits** | Context-dependent rule selection | ✅ Implemented (v0.8) |
| **Regret bounds** | O(√(KT log K)) theoretical guarantee | ✅ Follows from TS |

We're not inventing new math. We're applying proven frameworks to a new domain. The bandit implementation serves as a **canonical example** of Thompson Sampling with Beta-Bernoulli distributions—heavily documented for educational purposes.

---

## Honest Limitations

### Current Constraints

- **Single context feature**: Currently only error_class; file type, task category coming
- **CLI session commands**: Session management via MCP only (CLI exposure in progress)
- **Batch attribution**: All selected rules get same reward (individual attribution TBD)

### Hard Problems We're Working On

- **Credit assignment**: When multiple rules are active, which one helped?
- **Non-stationarity**: Developer skill changes over time
- **Cold start**: New rules have high uncertainty (mitigated by seed-boosted priors)
- **Context representation**: What features actually matter beyond error_class?

These are hard problems. We have directional ideas, not solutions. If you're a researcher working on bandit algorithms or causal inference, we'd love to talk.

---

## Philosophy

1. **Falsifiability over impressiveness** - If you can't prove it wrong, it's not a claim
2. **Measurement over intuition** - "Feels better" is not evidence
3. **Mechanisms over magic** - Explain how it works or admit you don't know
4. **Boring over exciting** - Proven frameworks beat novel demos
5. **Honesty over marketing** - State limitations. Invite scrutiny.

---

## Contributing

We're especially interested in:
- Better context representations for the bandit
- Credit assignment approaches
- Statistical methodology improvements
- Real-world experiment results (positive or negative)

```bash
git clone https://github.com/Peleke/buildlog-template
cd buildlog-template
pip install -e ".[dev]"
pytest
```

---

## License

MIT License — see [LICENSE](./LICENSE)

---

<div align="center">

**"Agent learning" without measurement is just prompt engineering with extra steps.**

**buildlog is measurement.**

[Back to top](#buildlog)

</div>
