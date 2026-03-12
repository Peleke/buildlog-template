# Experiments (Optional)

The gauntlet is buildlog's primary feedback mechanism. Every gauntlet run credits the rules its reviewers cite, and `log_reward()` updates the Thompson Sampling posteriors. **You do not need sessions or experiments for the learning loop to work.**

Experiments are an optional layer for teams that want **longitudinal RMR tracking** -- measuring Repeated Mistake Rate across many sessions over time to get statistical evidence about whether learned rules are reducing mistakes.

## Running an experiment

```bash
# Start a tracked session
buildlog experiment start --error-class "api-design"

# Log mistakes as they happen
buildlog experiment log-mistake \
  --error-class "api-design" \
  --description "Returned 200 for error case"

# End session
buildlog experiment end

# Get metrics for the current (or most recent) session
buildlog experiment metrics

# Full report across ALL sessions (aggregate RMR, per-session breakdown)
buildlog experiment report
```

## What the report includes

- Total sessions and total mistakes
- Repeat rate (RMR) — aggregate and per-session
- Per-session breakdown with timestamps
- Mistakes grouped by error class

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

## Relationship to the gauntlet

The gauntlet is the primary feedback loop. It credits rules when reviewers cite them, and `log_reward()` updates the bandit posteriors. This works without any session ceremony.

Experiments add a layer on top: when you start a session, the Thompson Sampling bandit selects which rules to surface based on learned effectiveness. As you log mistakes during the session, you build a longitudinal record of RMR that can be compared across baseline and treatment conditions.

Use experiments when you want to answer "did my rules reduce mistakes over N sessions?" Use the gauntlet loop alone when you just want the learning to happen.

See [Core Concepts](../getting-started/concepts.md#thompson-sampling-bandit) for the mathematical details, and the [Review Gauntlet](review-gauntlet.md) guide for the primary feedback loop.
