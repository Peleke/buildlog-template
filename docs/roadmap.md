# Roadmap

## Where buildlog is heading

buildlog is an agentic learning loop for AI coding tools. It captures what your agent gets right and wrong, selects which rules to surface with Thompson Sampling, and measures whether they reduce mistakes. v0.23 ships the core loop end-to-end. What follows is about making it sharper, faster, and cross-project.

## Recently Shipped

| Feature | Version | What it does |
|---------|---------|-------------|
| Bragi v3 | v0.22 | 27 LLM prose detection rules from ACL/COLING, PNAS, GPTZero research |
| `ensure_session()` | v0.23 | `buildlog_commit()` no longer blocks without manual `experiment start`. New users can install and commit immediately. |
| Gauntlet credit system | v0.21 | Rule citations in gauntlet findings drive posterior updates. Solves credit assignment. |
| Posterior history | v0.21 | Every gauntlet credit snapshots alpha/beta/mean per rule. Query convergence over time. |
| Category-aware RMR | v0.21 | Repeat detection uses `rules_consulted` overlap, not just description similarity. |
| Multi-agent render | v0.18 | Same rules render to CLAUDE.md, .cursor/rules/, copilot-instructions.md, .windsurf/rules/, .continue/rules/, settings.json. |
| Global SQLite | v0.11 | Single database at ~/.buildlog/buildlog.db. WAL mode. Project isolation via SHA-256. |
| Ambient emission protocol | v0.18 | Fire-and-forget JSON artifacts to ~/.buildlog/emissions/pending/ for downstream systems. |

## In Progress

### Dashboard visualization fixes ([#243](https://github.com/Peleke/buildlog-template/issues/243))

Four charts need work: rule labels should show human-readable text instead of `domain:hash`, RMR chart needs a minimum-count filter, error class chart conflates severity with category, rule growth chart is uninformative. All presentation-layer fixes in the marimo notebook.

### Session decoupling Phase 2-3 ([#237](https://github.com/Peleke/buildlog-template/issues/237))

Phase 1 shipped in v0.23 (`ensure_session()`). Remaining:

- **Phase 2**: Harden session-start hooks — log failures instead of swallowing them
- **Phase 3**: Session-independent RMR — compute directly from mistakes table with time windows, no session context required

## Planned

### Track-and-Stop ([#236](https://github.com/Peleke/buildlog-template/issues/236))

Optimal stopping for rule convergence. Rules that have converged (posterior CI width below threshold) stop consuming gauntlet citations. Based on Garivier & Kaufmann (2016). Frees exploration budget for uncertain rules. Includes schema migration (v8), convergence indicators in the dashboard, and integration with the gauntlet credit system.

### Cross-project convergence

Detect rules independently rediscovered across projects. Track cross-project salience. When the same pattern surfaces in three repos, that's a signal. Builds on the [global SQLite backend](guides/storage-architecture.md) and the emission protocol.

### Emergent rule graphs

Cluster embeddings into concept nodes. Derive edges from co-occurrence and bandit correlation. Contextual bandits with embedding-space context vectors (LinUCB). The embedding persistence layer is already shipped via qortex; this is the graph structure on top.

### L-MVA: Learned Minimal Viable Agent ([qortex#96](https://github.com/Peleke/qortex/issues/96))

Outer bandit that discovers the minimum token budget maintaining quality, per task, per domain. Inner bandit picks rules under that budget. Both update from the same reward signal.

## Related Issues

- [#243](https://github.com/Peleke/buildlog-template/issues/243) — Dashboard visualization bugs (4 charts)
- [#237](https://github.com/Peleke/buildlog-template/issues/237) — Session decoupling (Phase 2-3)
- [#236](https://github.com/Peleke/buildlog-template/issues/236) — Track-and-Stop optimal stopping
- [#100](https://github.com/Peleke/buildlog-template/issues/100) — sqlite-vec + emergent rule graphs
- [#87](https://github.com/Peleke/buildlog-template/issues/87) — qortex knowledge graph integration
- [qortex#96](https://github.com/Peleke/qortex/issues/96) — L-MVA (BudgetLearner)
- [qortex#63](https://github.com/Peleke/qortex/issues/63) — Production deployment (triple interface)
