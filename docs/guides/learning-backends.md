# Learning Backends

buildlog uses Thompson Sampling to decide which rules to surface in your agent's instruction set. The learning backend is the component that runs the bandit. It tracks Beta distributions per rule, samples from them during selection, and updates posteriors from feedback.

There are two backends. You pick one.

## Decision Tree

**Start here:**

1. Are you using qortex as a knowledge graph elsewhere in your stack?
    - **No.** Use `builtin`. Done.
    - **Yes.** Continue.

2. Do you need credit propagation from qortex's learning layer (e.g., shared bandits across multiple consumers)?
    - **No.** Use `builtin`. It's simpler and has zero extra dependencies.
    - **Yes.** Use `qortex`.

3. Are you on Python 3.11+?
    - **No.** Use `builtin`. qortex requires 3.11+.
    - **Yes.** Use `qortex`.

If you're unsure, use `builtin`. It's the default, it's fast, it works, and you can switch later without losing data.

## builtin (default)

The builtin backend wraps `ThompsonSamplingBandit`, which ships with buildlog. Zero extra dependencies.

### How it works

- State is stored in the global SQLite database at `~/.buildlog/buildlog.db`, with legacy JSONL files as fallback.
- SQLite persistence is preferred. Falls back to append-only JSONL with compaction on load.
- Seed rules (from gauntlet personas) start with boosted priors of `Beta(3, 1)`, reflecting the expectation that curated rules are more likely to be effective. Non-seed rules start with `Beta(1, 1)` (uniform, maximum uncertainty).
- Error class strings (e.g., `"type-errors"`, `"missing-test"`) partition the bandit state space. A rule can be great for type errors and useless for API design. Separate distributions per context let the system learn this.

### Setup

Nothing to do. This is the default.

```bash
pip install buildlog
# That's it. builtin backend is active.
```

No env var needed. If `BUILDLOG_LEARNING_BACKEND` is unset, buildlog uses `"builtin"`.

### Verify

```bash
buildlog bandit-status
```

```
Backend: sqlite
Contexts: 2
Total arms: 15
Total observations: 47

Top rules by context:

  type-errors:
    arch-a1b2c3d4e5  mean=0.78  CI=[0.61, 0.95]  obs=12  (seed)
    wf-f6g7h8i9j0    mean=0.65  CI=[0.44, 0.86]  obs=8

  missing-test:
    test-k1l2m3n4o5  mean=0.82  CI=[0.68, 0.96]  obs=15  (seed)
```

The `Backend: sqlite` line confirms builtin is active with SQLite persistence.

## qortex

The qortex backend wraps `qortex.learning.Learner`, which provides Thompson Sampling with additional features: OTEL tracing, credit propagation across consumers, and integration with qortex's knowledge graph.

### When to use it

- You're already running qortex as a knowledge graph
- You want shared learning state across multiple qortex consumers (buildlog, interlinear, MindMirror, etc.)
- You need audit trails via OpenTelemetry
- You want qortex-generated seed rules to carry provenance metadata that feeds back into the graph

### Setup

```bash
pip install buildlog[qortex]
```

Requires Python 3.11+. The `qortex` extra installs `qortex>=0.3.6`.

Set the env var:

```bash
export BUILDLOG_LEARNING_BACKEND=qortex
```

For persistent configuration, add it to your shell profile:

```bash
# ~/.bashrc or ~/.zshrc
export BUILDLOG_LEARNING_BACKEND=qortex
```

Or set it in your MCP server configuration so it's active when Claude Code launches buildlog:

```json
{
  "mcpServers": {
    "buildlog": {
      "command": "buildlog-mcp",
      "args": [],
      "env": {
        "BUILDLOG_LEARNING_BACKEND": "qortex"
      }
    }
  }
}
```

### Verify

```bash
buildlog bandit-status
```

```
Backend: qortex
Contexts: 2
...
```

The `Backend: qortex` line confirms the qortex backend is active.

### Behavioral differences

The qortex backend is API-compatible with builtin. All MCP tools, CLI commands, and workflows work identically. The differences are internal:

| Aspect | builtin | qortex |
|--------|---------|--------|
| State storage | SQLite or JSONL | qortex's own persistence |
| Context format | String passed through | String wrapped as `{"error_class": value}` |
| Seed boost | `Beta(1 + boost, 1)` | Configured via `LearnerConfig.seed_boost` |
| Arm decay | Direct parameter manipulation | Via qortex's `ArmState` dataclass |
| Credit propagation | None (standalone) | Shared across qortex consumers |
| OTEL tracing | None | Available if qortex is configured for it |
| Python requirement | 3.10+ | 3.11+ |

### Context translation

buildlog uses string contexts (error class names like `"type-errors"`). qortex uses dict contexts. The adapter translates automatically:

```python
# buildlog calls: backend.select(candidates, context="type-errors")
# qortex receives: learner.select(arms, context={"error_class": "type-errors"})
```

You don't need to do anything. The translation is handled by the `QortexLearner` adapter.

## Switching backends

You can switch between backends at any time. The bandit state is stored independently per backend, so:

- **builtin to qortex**: The qortex backend starts with fresh priors. Your builtin state is preserved in SQLite and will be used again if you switch back.
- **qortex to builtin**: The builtin backend loads its last saved state from SQLite. Learning that happened in qortex stays in qortex's store.

State is not migrated between backends because the backends may have different prior structures. Blind migration could produce invalid distributions.

If you need continuity, stay on one backend. If you're switching early (before significant learning has accumulated), the fresh start has minimal impact since there is little state to lose.

## Fallback behavior

If `BUILDLOG_LEARNING_BACKEND` is set to an unknown value, buildlog logs a warning and falls back to `"builtin"`:

```
WARNING: Unknown BUILDLOG_LEARNING_BACKEND='foo', falling back to 'builtin'
```

If `BUILDLOG_LEARNING_BACKEND=qortex` but qortex is not installed, buildlog raises an `ImportError` with instructions:

```
ImportError: qortex is required for the 'qortex' learning backend.
Install it with: pip install buildlog[qortex]
```

This is a hard error, not a fallback. If you set the backend to qortex, buildlog expects it to be available.

## Performance notes

Both backends are fast enough that you won't notice them in normal use. The bottleneck in buildlog is typically I/O (reading entries, writing files), not bandit computation.

- **builtin**: Selection is O(n) where n is the number of candidate rules. Sampling from a Beta distribution is a single `random.betavariate()` call. Updates are O(1) with an append to SQLite.
- **qortex**: Similar complexity, with additional overhead for context dict construction and qortex's internal bookkeeping. The difference is typically under 1ms.

For reference, selecting from 100 candidate rules takes <1ms on either backend.
