# Context Changes Everything

## The restaurant problem, revisited

You've been using Thompson Sampling to pick restaurants for a month. You've converged on Restaurant A as the best option. Life is good.

Then your partner suggests a date night.

Restaurant A is a ramen counter with 12 seats and no reservations. It's incredible for a solo Tuesday dinner. It's terrible for a date.

**The best option depends on the context.**

This is obvious for restaurants. You already maintain mental categories: "date night places," "quick lunch spots," "group-friendly." You don't rank them on one universal scale — you rank them *per situation*.

The same is true for engineering rules.

## Rules aren't universally useful

Consider these rules:

- "Always check for null returns from database queries"
- "Prefer early returns over deeply nested conditionals"
- "Write integration tests before unit tests for API endpoints"

Rule 1 is critical when you're writing database code. Irrelevant when you're writing CSS.

Rule 2 is useful everywhere, but *especially* useful in complex control flow.

Rule 3 is valuable for API work. Counterproductive for pure utility functions.

A rule that prevents mistakes in one context might be noise in another. If you surface all 30 rules regardless of context, you're back to prompt bloat and developer fatigue.

## From bandits to contextual bandits

A standard bandit maintains one set of beliefs about each arm:

```
posteriors["rule-null-check"] = Beta(15, 3)   # good overall
```

A **contextual bandit** maintains beliefs *per context*:

```
posteriors["type-errors"]["rule-null-check"] = Beta(12, 2)   # great for type errors
posteriors["api-design"]["rule-null-check"]  = Beta(3, 5)    # mediocre for API design
posteriors["testing"]["rule-null-check"]     = Beta(1, 1)    # never tried in testing context
```

When you start a session, you tell the bandit what context you're in. It pulls the posteriors for *that context* and runs Thompson Sampling against them. The result: different rules surface for different situations.

## How buildlog implements this

In buildlog, context is currently the **error class** — a category like "type-errors," "api-design," or "testing."

### Starting a session

```bash
buildlog experiment start --error-class "type-errors"
```

The bandit loads posteriors for the "type-errors" context. Rules that have performed well in previous type-error sessions get high scores. Rules that are new to this context start at their prior.

### During the session

```bash
buildlog experiment log-mistake \
  --error-class "type-errors" \
  --description "Forgot to handle Optional return"
```

The bandit records: every rule that was active in this context failed to prevent this mistake. Their beta parameters increment (failure signal).

### After the session

```bash
buildlog experiment end
buildlog reward rule-null-check --outcome accepted
```

Rules that got positive feedback get their alpha incremented (success signal) in the "type-errors" context. Rules in other contexts are unaffected.

### The result

Over time, each context develops its own learned profile:

| Rule | type-errors | api-design | testing |
|------|-------------|------------|---------|
| null-check | Beta(12, 2) | Beta(3, 5) | Beta(1, 1) |
| early-return | Beta(8, 3) | Beta(6, 4) | Beta(5, 2) |
| test-first | Beta(2, 4) | Beta(10, 2) | Beta(7, 3) |

The bandit learns: surface null-check for type errors, surface test-first for API design, and keep exploring for testing contexts where data is sparse.

## The "oh shit" moment

Here's the thing: **this is exactly what you already do.** You already know that different situations call for different rules. You already adjust your approach based on context. You just do it with vibes and experience.

buildlog does the same thing, but:

- **Systematically** — every context gets tracked, every outcome gets recorded
- **With data** — not "I feel like null checks matter for type errors" but "Beta(12, 2) with mean 0.86 and a 95% credible interval of [0.68, 1.00]"
- **Automatically** — the bandit selects rules for you, no manual curation per context
- **Measurably** — you can see convergence, compare contexts, identify where you need more data

The gap between "I have intuition about what helps" and "I have statistical evidence for what helps, per-context, with uncertainty quantified" is the gap between vibes-based development and measured development.

That's what buildlog closes.

## What's next for context

Error class is the first context feature. It won't be the last. Future context dimensions could include:

| Context feature | What it captures | Status |
|----------------|-----------------|--------|
| Error class | What kind of mistake | Implemented |
| File type | Language/framework | Planned |
| Task category | Feature, bugfix, refactor | Planned |
| Project type | Web app, CLI, library | Research |
| Embedding similarity | Semantic match to past situations | Research ([#100](https://github.com/Peleke/buildlog-template/issues/100)) |

As context gets richer, the bandit gets sharper. The ultimate direction is **LinUCB** or **neural contextual bandits** where the context vector is an embedding of the current situation, and the bandit selects rules based on semantic similarity to situations where the rule previously helped.

But that's [the roadmap](../roadmap.md). The foundation — Beta-Bernoulli Thompson Sampling with per-context posteriors — is here now and working.

## Wrapping up

You started with a restaurant problem. You learned that every choice has a cost (regret), that you can track your beliefs precisely (Beta distributions), and that you can make decisions that naturally balance exploration and exploitation (Thompson Sampling).

Then you added context — because the best restaurant depends on the occasion, and the best engineering rule depends on the situation.

That's a contextual bandit. And that's what's running in your terminal every time buildlog selects which rules to surface.

The math isn't magic. It's formalized common sense. And now you have the vocabulary to read the code, verify the claims, and — if you want — extend it.

## Next steps

- [Core Concepts](../getting-started/concepts.md) — See how theory maps to buildlog's implementation
- [Experiments](../guides/experiments.md) — Run your own experiment to test whether it works
- [Roadmap](../roadmap.md) — Where this is heading: embedding search, rule graphs, and LinUCB
