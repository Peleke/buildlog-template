# Experiments

buildlog ships infrastructure to run actual experiments measuring whether learned rules reduce repeated mistakes.

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

## Bandit integration

When you start an experiment session, the Thompson Sampling bandit automatically selects which rules to surface based on learned effectiveness. As you log mistakes and rewards during the session, the bandit updates its posterior distributions.

See [Core Concepts](../getting-started/concepts.md#thompson-sampling-bandit) for the mathematical details.
