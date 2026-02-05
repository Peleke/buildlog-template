# Roadmap

## Where buildlog is heading

buildlog today is a Thompson Sampling contextual bandit for engineering rule selection. What follows are the three layers that turn it into something bigger: a system that discovers *what you know* across projects, finds patterns you didn't design, and gets contextually sharper over time.

These layers build on the [global SQLite backend](guides/storage-architecture.md) shipped in v0.11.0.

## Layer 1: Embedding Persistence

**Status:** Engineering. Next up.

**The problem:** `buildlog distill` recomputes embeddings from scratch every run. This prevents cross-project deduplication and wastes computation.

**The solution:** Persist embeddings in sqlite-vec virtual tables alongside metadata (project, skill ID, rule text, embedding model, dimension). One KNN query replaces pairwise similarity.

| Decision | Options | Leaning |
|----------|---------|---------|
| Embedding backend | sentence-transformers (local, 384d) vs. OpenAI (1536d, API key) vs. Ollama | sentence-transformers (offline, no API key) |
| Embed what | Rule text only vs. rule + mistake descriptions | Start with rules, add mistakes later |
| Dimensions | Fixed vs. multi-dimension support | Fixed per model, table-per-model |

**Depends on:** sqlite-vec >= 0.1.6 (already in pyproject.toml)

## Layer 2: Cross-Project Convergence

**Status:** Engineering. The big win.

**The problem:** When `learn_from_review()` produces "always wrap multi-statement writes in transactions," buildlog only checks for duplicates within the current project.

**The solution:** On every new rule ingest, KNN search the *entire* global database. If a semantically similar rule exists in any project:

- **Reinforce** it (increment count, update timestamp) instead of creating a duplicate
- **Cross-link** the projects that independently discovered it
- **Track convergence** — how many independent projects arrived at the same rule?

A rule rediscovered across 5 projects is qualitatively different from one that appeared once. The reinforcement count becomes a **salience score**: rules that keep emerging independently are the most generalizable patterns.

### Salience metadata

Each rule accumulates:

- Which projects discovered it
- What error classes it emerged from
- Thompson Sampling posteriors per context
- Whether it was human-validated (promoted) or machine-extracted

## Layer 3: Emergent Rule Graphs

**Status:** Research direction.

**The hypothesis:** At sufficient data density, clusters in embedding space correspond to emergent concepts.

The progression:

1. Rules accumulate as points in embedding space
2. At density thresholds, centroids emerge (via HDBSCAN or KNN density estimation)
3. Each centroid is a **concept node** — not a single rule, but the *essence* multiple rules converge toward
4. Edges between nodes come from:
   - **Co-occurrence** within the same project
   - **Temporal sequence** (rule A tends to be discovered before rule B)
   - **Bandit correlation** (activating rule A improves outcomes when rule B is also active)

This gives a **knowledge graph that emerges from practice, not from taxonomy.** Nobody designs the categories — they form from repeated independent discovery.

### Connection to bandits

Thompson Sampling today uses per-context posteriors with error class as the context feature. The research direction is **LinUCB**: make the context vector an embedding of the current situation (error class + file type + project type + semantic similarity to past situations). The bandit then selects rules by contextual similarity to situations where the rule previously helped.

This is the bridge from "rules that worked" to "rules that work *in situations like this one*."

## What you could do with this

| Question | How to answer it |
|----------|-----------------|
| "What have I learned?" | Visualize the rule graph. Dense clusters = well-validated knowledge. |
| "What should I learn next?" | Sparse regions adjacent to dense clusters = unexplored territory near known patterns. |
| "What transfers across projects?" | High cross-project convergence = most generalizable rules. |
| "Am I getting better?" | Track cluster density over time. More density = more validated knowledge. |

## Implementation order

| Step | Layer | Type | Description |
|------|-------|------|-------------|
| 1 | 1 | Engineering | sqlite-vec table creation + embedding storage |
| 2 | 1 | Engineering | Replace pairwise dedup with KNN search |
| 3 | 2 | Engineering | Cross-project convergence tracking on ingest |
| 4 | 2 | Engineering | Salience scoring from convergence signals |
| 5 | 3 | Research | Centroid extraction via clustering |
| 6 | 3 | Research | Graph construction from co-occurrence + temporal + bandit signals |
| 7 | 3 | Research | LinUCB contextual bandit with embedding context vectors |

Steps 1-4 are shipping next. Steps 5-7 are experiments with explicit success/failure criteria.

## External integration: qortex

[qortex](https://github.com/Peleke/qortex) is a separate knowledge graph project. Once functional, buildlog will integrate with it via MCP for:

- **Rule import** — query qortex for rules relevant to a context
- **Feedback loop** — send reward signals back to qortex's confidence scoring
- **Checkpoint coordination** — synchronized rollback across both systems

This integration depends on qortex's MCP server milestone. See [#87](https://github.com/Peleke/buildlog-template/issues/87) for details.

## Related issues

- [#100](https://github.com/Peleke/buildlog-template/issues/100) — sqlite-vec + emergent rule graphs: full design document
- [#87](https://github.com/Peleke/buildlog-template/issues/87) — qortex knowledge graph integration
- [#43](https://github.com/Peleke/buildlog-template/issues/43) — Thompson Sampling tutorial series
