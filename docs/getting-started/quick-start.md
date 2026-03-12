# Quick Start

This walks through the full buildlog pipeline: capture, extract, promote, measure, learn.

!!! note "Upgrading from an older version?"
    If you have an existing project with legacy `.buildlog/` JSON/JSONL files, run
    `buildlog migrate` to move your data into the new global SQLite database. This is
    a one-time, non-destructive operation. See [Storage Architecture](../guides/storage-architecture.md)
    for details.

## Stage 1: Capture

Document your work. Include the mistakes — they're the most valuable signal.

```bash
buildlog new auth-api
# Edit the markdown, document what happened
```

## Stage 2: Extract

Pull structured rules from your entries.

```bash
buildlog distill    # Extract patterns
buildlog skills     # Deduplicate into rules
```

## Stage 3: Promote

Surface rules to your agent via CLAUDE.md, settings.json, or Agent Skills.

```bash
buildlog status                          # See what's ready
buildlog promote <skill-ids> --target skill  # Surface to agent
```

## Stage 4: Review with the gauntlet

The gauntlet is the primary feedback mechanism. It runs curated reviewer personas against your code and credits rules that reviewers cite.

```bash
buildlog gauntlet-loop --target src/
# Reviewers find issues, cite rules → rules get credited
# Fix issues, re-run until clean
```

## Stage 5: Close the loop

Log a reward signal after your work is reviewed and accepted. This updates the Thompson Sampling posteriors for every rule that was credited during the gauntlet.

```python
# Via MCP
buildlog_log_reward(
    outcome="accepted",
    notes="PR merged after gauntlet review"
)
```

## Optional: Longitudinal RMR tracking

For teams that want to measure Repeated Mistake Rate across many sessions over time:

```bash
buildlog experiment start --error-class "type-errors"
# ... work session ...
buildlog experiment log-mistake --error-class "type-errors" \
  --description "Forgot to handle null case"
buildlog experiment end
buildlog experiment report
```

This is not required for the learning loop to work. See the [Experiments guide](../guides/experiments.md) for details.

## The pipeline

![buildlog pipeline](../diagrams/pipeline.svg)

*Thompson Sampling closes the loop: rules are selected based on learned effectiveness, and feedback updates the model.*
