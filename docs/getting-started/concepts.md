# Core Concepts

## The Problem

Everyone's building "agent memory." Ask them one question: **How do you know it works?**

You'll get:

- "It feels smarter"
- "Users report better results"
- "The agent remembers things now"

That's not evidence. That's vibes.

Here's what a real answer looks like:

> "We track Repeated Mistake Rate (RMR) across sessions. Our null hypothesis is that the system makes no difference. After 50 sessions, RMR decreased from 34% to 12% (p < 0.01). The effect size is 0.65. Here's the data."

If you can't say something like that, you don't have agent learning. You have a demo.

## The Claim

**buildlog** makes a falsifiable claim:

> **H₀ (Null Hypothesis):** buildlog makes no measurable difference to agent behavior.
>
> **H₁ (Alternative):** Agents using buildlog-learned rules have lower Repeated Mistake Rate than baseline.

We provide the infrastructure to **reject or fail to reject** this hypothesis with your own data.

If buildlog doesn't work, the numbers will show it. That's the point.

## The Metric: Repeated Mistake Rate (RMR)

```
RMR = (Mistakes that match previous mistakes) / (Total mistakes logged)
```

A mistake "matches" if it has the same semantic signature — same error class, similar description, same root cause showing up again.

**Why RMR?**

- **Observable**: You can count it
- **Attributable**: Lower RMR after rule injection = signal
- **Meaningful**: Repeating mistakes is the actual pain point

RMR is not the only metric that matters. But it's one we can measure, and measurement is where science starts.

## The Mechanism

buildlog is building toward **contextual bandits** for automatic rule selection.

### What Exists Today

| Component | Description | Status |
|-----------|-------------|--------|
| Rule extraction | From entries, reviews, curated seeds | Implemented |
| Confidence scoring | Frequency + recency based | Implemented |
| Reward logging | Accept/reject/revision signals | Implemented |
| Experiment tracking | Sessions, mistakes, RMR calculation | Implemented |
| Review gauntlet | Curated persona-based code review (3 personas, 61 rules) | Implemented |
| Thompson Sampling | Automatic rule selection via bandit | Implemented |
| Posterior history | Per-rule convergence tracking over time | Implemented |

### Thompson Sampling Bandit

| Element | Detail |
|---------|--------|
| Context (c) | Error class (e.g., "type-errors") |
| Arms (a) | Candidate rules to surface |
| Reward (r) | Binary feedback from mistakes & rewards |
| Model | Beta-Bernoulli (conjugate prior) |
| Policy | Thompson Sampling (sample, don't exploit) |
| Learning | Bayesian updates on every feedback signal |

**How it works:**

1. **Session starts** — Bandit samples from Beta distributions, selects top-k rules
2. **Mistake logged** — Selected rules get reward=0 (they didn't prevent the mistake)
3. **Explicit reward** — Rules get reward based on outcome (accepted=1, rejected=0)

**Seed-boosted priors:** Curated rules from gauntlet personas start with boosted priors (Beta(3,1) instead of Beta(1,1)), reflecting our belief that expert-curated rules are likely effective.

## Theoretical Foundations

| Concept | Application in buildlog | Status |
|---------|------------------------|--------|
| Confidence scoring | Frequency + recency decay | Implemented |
| Semantic hashing | Mistake deduplication for RMR | Implemented |
| Reward signals | Binary feedback infrastructure | Implemented |
| Thompson Sampling | Rule selection under uncertainty | Implemented |
| Beta-Bernoulli model | Posterior updates from binary reward | Implemented |
| Contextual bandits | Context-dependent rule selection | Implemented |
| Regret bounds | O(sqrt(KT log K)) theoretical guarantee | Follows from TS |

We're not inventing new math. We're applying proven frameworks to a new domain.
