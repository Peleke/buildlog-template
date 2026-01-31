# Philosophy

## Principles

1. **Falsifiability over impressiveness** — If you can't prove it wrong, it's not a claim
2. **Measurement over intuition** — "Feels better" is not evidence
3. **Mechanisms over magic** — Explain how it works or admit you don't know
4. **Boring over exciting** — Proven frameworks beat novel demos
5. **Honesty over marketing** — State limitations. Invite scrutiny.

## What This Is Not

**This is not AGI.** This is not "agents that truly learn." This is not a revolution.

This is:

- A structured way to capture engineering knowledge
- A bandit framework for rule selection
- Infrastructure to measure whether it works

Boring? Maybe. But boring things that work beat exciting things that don't.

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
