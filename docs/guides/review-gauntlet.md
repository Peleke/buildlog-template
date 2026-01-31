# Review Gauntlet

Run your code through ruthless reviewer personas, each with curated rules from authoritative sources.

## Available personas

```bash
buildlog gauntlet list
```

| Persona | Focus | Rules |
|---------|-------|-------|
| **Security Karen** | OWASP Top 10, auth, injection, secrets | 13 |
| **Test Terrorist** | Coverage, property-based, metamorphic, contracts | 21 |
| **Ruthless Reviewer** | Code quality, FP principles | Coming soon |

Each rule includes:

- **Context**: When to apply it
- **Antipattern**: What violation looks like
- **Rationale**: Why it matters (with citations)

## Usage

```bash
# Generate a review prompt
buildlog gauntlet prompt src/api.py

# Export rules for manual review
buildlog gauntlet rules --format markdown -o review_checklist.md

# After running a review, persist learnings
buildlog gauntlet learn review_issues.json --source "PR#42"
```

## Gauntlet Loop (Agent Integration)

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

## MCP tools for agent integration

- `buildlog_gauntlet_issues` — Report findings, get next action
- `buildlog_gauntlet_accept_risk` — Accept remaining issues (optionally create GitHub issues)

The gauntlet integrates with the learning loop — issues found become rules that accumulate confidence.
