# Roadmap

## Where buildlog is heading

buildlog started as a Thompson Sampling contextual bandit for engineering rule selection. Three layers turn it into something bigger: a system that discovers *what you know* across projects, finds patterns you didn't design, and gets contextually sharper over time.

Layers 1 and 2 build on the [global SQLite backend](guides/storage-architecture.md) shipped in v0.11.0. Layer 3 is implemented by [qortex](https://github.com/Peleke/qortex), which ships the knowledge graph, bandit learning, and full observability stack.

## Layer 1: Embedding Persistence

**Status:** Complete. Shipped in qortex v0.3.x.

Embeddings are persisted in vector indices (NumpyVectorIndex for dev, SqliteVecIndex for production) alongside metadata. KNN similarity search replaces pairwise recomputation. Three embedding backends supported: sentence-transformers (local, 384d), OpenAI, and Ollama -- all traced with `@traced` spans reporting model, batch size, and cache hit rates.

## Layer 2: Cross-Project Convergence

**Status:** Complete. Shipped in qortex v0.3.x.

On every new rule ingest, KNN search finds semantically similar rules across the entire graph. Reinforcement via edge promotion: online cosine-similarity edges that survive observation get promoted to persistent KG structure. Cross-project salience tracked through:

- Which domains/projects discovered the rule
- Edge confidence and observation count
- Thompson Sampling posteriors per context partition
- Whether the rule was human-validated or machine-extracted

The **KG coverage ratio** (visible in Grafana) tracks what percentage of the retrieval neighborhood is persistent vs online edges. Coverage trending upward means the graph is crystallizing.

## Layer 3: Knowledge Graph + Adaptive Learning

**Status:** Shipped (v0.5.0). Active development continues.

The hypothesis from the original roadmap proved out: clusters in embedding space correspond to emergent concepts, and edges between them encode structure that pure cosine similarity misses. qortex implements this as a full knowledge graph with Personalized PageRank, Thompson Sampling bandits, credit propagation, and a complete observability stack.

### What's shipped

| Component | Status | Version |
|-----------|--------|---------|
| Knowledge graph (InMemoryBackend + MemgraphBackend) | Shipped | v0.2.0 |
| Thompson Sampling bandit (select, observe, posteriors, context partitioning) | Shipped | v0.3.4 |
| Credit propagation (causal DAG, feedback flows to ancestor concepts) | Shipped, flag-gated | v0.3.4 |
| qortex-observe (standalone observability package) | Shipped | v0.5.0 |
| Full trace hierarchy (14 graph ops, vec layer, embeddings, learning) | Shipped | v0.5.0 |
| Unified metrics pipeline (36 metrics, declarative schema, OTel + Prometheus) | Shipped | v0.5.0 |
| Selective trace sampling (errors/slow always, normal at configurable rate) | Shipped | v0.5.0 |
| MCP server (36 tools, 6 learning tools) | Shipped | v0.4.0 |
| Framework adapters (Agno, CrewAI, LangChain, Mastra) | Shipped | v0.4.0 |

### What's next

**1. qortex-observe PyPI publish** ([qortex#108](https://github.com/Peleke/qortex/issues/108))

Publish `qortex-observe` as a standalone PyPI package so any consumer (openclaw, langchain-qortex, mastra-qortex) gets metrics + traces by calling `configure()`. Includes standalone CI, consumer migration, and a portable Docker Compose observability stack (Grafana + Prometheus + Jaeger + OTel Collector).

**2. L-MVA: Learned Minimal Viable Agent** ([qortex#96](https://github.com/Peleke/qortex/issues/96))

The outer bandit that discovers the minimum token budget maintaining quality, per task, per domain. An `InferenceTrace` event captures every selection: which rules, what budget tier, what reward. A `BudgetLearner` wraps the existing `Learner`: outer bandit picks budget tier, inner bandit picks rules under that budget. Both update from the same reward signal. This is the pitch: "the system learns how much context it needs."

Thompson Sampling works for both inner and outer bandits today. UCB1 and Track-and-Stop (SOCP-optimal allocation) are Strategy plugins that can drop in later without touching the BudgetLearner architecture.

**3. Production deployment: triple interface** ([qortex#63](https://github.com/Peleke/qortex/issues/63))

Single FastAPI app serving GraphQL (`/graphql`, federation v2 for MindMirror mesh), REST (`/api/v1/`), and MCP (`/mcp`, streamable HTTP for AI agents). All three wrap the same `LocalQortexClient`. One container, one Dockerfile, one health check. This is the biggest platform unlock -- qortex becomes a real service, not just a library.

**4. Causal DAG** ([qortex#3](https://github.com/Peleke/qortex/issues/3))

Credit propagation is already wired and flag-gated. The missing piece is structural causal discovery from graph topology. Deferred until L-MVA and deployment are solid, since the causal DAG feeds into credit assignment which feeds the bandit.

## Related

- [#100](https://github.com/Peleke/buildlog-template/issues/100) -- sqlite-vec + emergent rule graphs: full design document
- [#87](https://github.com/Peleke/buildlog-template/issues/87) -- qortex knowledge graph integration
- [qortex#108](https://github.com/Peleke/qortex/issues/108) -- qortex-observe PyPI publish
- [qortex#96](https://github.com/Peleke/qortex/issues/96) -- L-MVA (BudgetLearner)
- [qortex#63](https://github.com/Peleke/qortex/issues/63) -- Production deployment (triple interface)
- [qortex#3](https://github.com/Peleke/qortex/issues/3) -- Causal DAG
