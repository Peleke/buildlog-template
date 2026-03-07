# Changelog

All notable changes to buildlog are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.19.0] - 2026-03-07

### Added
- **qortex-learning as default backend**: Thompson Sampling via `qortex-learning` with persistent async bridge (`QortexLearner` adapter). Falls back to builtin bandit if not installed.
- **`gauntlet_credits` table (schema v6)**: Stores which rules were credited during gauntlet reviews in SQLite, enabling proper reward attribution.
- **Closed feedback loop**: Gauntlet credits rules -> SQLite -> `log_reward()` reads credits -> qortex posteriors update -> better rule selection. Mechanically proven end-to-end.

### Changed
- **Gauntlet is the sole feedback source**: `log_reward()` reads from `gauntlet_credits` table instead of session-selected rules. Only rules demonstrably consulted during review get reinforced.
- **Session ceremony is optional**: `log_mistake()` works without an active session (generates synthetic session ID).
- **Python >= 3.11 required** (was >= 3.10).
- **`qortex-learning>=0.1.0` is a required dependency** (was optional).
- Complete README rewrite reflecting the closed loop architecture.

### Fixed
- **Context mismatch**: Gauntlet credited with `context=None`, `log_reward` used `"general"` — different partitions. Both now use `None`.
- Dead code branch in `_run_async()` collapsed.
- Redundant `import threading` inside `_get_bridge_loop()` removed.
- Silent seed param drop in `QortexLearner.select()` now logged at DEBUG level.

## [0.18.4] - 2026-02-15

### Fixed
- **Gauntlet loop compact mode**: `buildlog_gauntlet_loop()` now strips the `prompt` field (~14k tokens) when `compact=True` (default). Previously only `rules_by_persona` was stripped. The caller has `valid_rule_ids` and `instructions` — use `compact=False` to get the full prompt.

## [0.18.2] - 2026-02-14

### Fixed
- **Enforcement wiring**: `install_hooks()` now adds enforcement to `.pre-commit-config.yaml` as a local hook (yaml path). The pre-commit framework uses `exec`, so appending to `.git/hooks/pre-commit` was dead code.
- **Always-on enforcement**: `BUILDLOG_ENFORCE` defaults to `1` (opt-out with `0`), not `0` (opt-in). Bare `git commit` is blocked everywhere.
- Claude Code `PreToolUse` hook preserved as agent-level enforcement surface
- Removed dead `TestInstallClaudeHooks` tests from previous approach
- Updated dogfood tests for always-on semantics (7 real-git-repo tests)
- CLI reference docs updated with enforcement section

## [0.18.1] - 2026-02-14

### Added
- **Learning Loop E2E documentation** (`docs/LEARNING-LOOP-E2E.md`): 13-step trace with explicit code citations covering installation through Thompson Sampling, gauntlet review, bandit updates, emission pipeline, cross-domain discovery via qortex, and rule re-export
- **Section 11: Cross-Domain Discovery & Rule Re-Export**: documents how qortex bridges domains that buildlog cannot see, with full projection pipeline coverage
- Full CLI reference for `qortex ingest emissions` with all flags
- Homepage updated with "See it working" showcase and "The ecosystem" section
- E2E doc featured in mkdocs nav, qortex integration guide added to nav
- README links to E2E doc in Quick Start and Documentation table

### Fixed
- Bragi gauntlet findings: em-dash overuse, self-referential pivots, AI vocab blocklist

## [0.18.0] - 2026-02-14

### Added
- **Marimo dashboard phase 2**: plotly dark theme, panel descriptions, design system
- **Emission edge enrichment** with real gauntlet rule IDs
- **Skill/gauntlet rule unification**: `promote()` inserts into `gauntlet_rules`, `_get_current_rules()` returns union

### Fixed
- **Rule unification P0+P1+P3**: ID alignment, seed detection, E2E test
- Total: 1,460 tests

## [0.17.0] - 2026-02-14

### Added
- **Auto data pipeline** — `end_session()` now auto-runs `distill_all()` and `generate_skills()` so dashboard data stays fresh without manual intervention
- **Session emission** — `end_session()` emits a `session_summary` artifact with typed edges (session→rule "uses", session→mistake "contains") for downstream consumers
- **Emission consumer** — `consume_pending_emissions()` processes pending artifacts, extracts edges into `emission_edges` SQLite table, moves files to processed/
- **emission_edges table** — schema v5 migration adds graph-relationship storage for cross-artifact edges (relation_type, confidence, properties)
- **MCP tool** — `buildlog_consume_emissions()` for manual emission processing
- **Emission health** — `EndSessionResult` and `OverviewResult` now report `pending_emissions`, `emissions_consumed`, `edges_stored`, `total_emission_edges`
- **LegacyBackend warning** — consumer warns when edge storage is unavailable due to legacy backend
- 32 new tests (consumer, auto-pipeline, emission edges, session emission)
- Total: 1,446 tests

### Fixed
- `auto_outcome` variable placement in `end_session()` (was using unreliable `dir()` hack)
- Signal log now records per-artifact edge count instead of cumulative
- `__version__` string synced with pyproject.toml (was stuck at 0.8.0)

## [0.16.0] - 2026-02-13

### Added
- **Enforcement system** — Claude Code hook + auto-reward + auto-migrate (#177)
- **Marimo interactive dashboard** — `buildlog viz` command (#174)
- **Session-end improvements report** in journal entries (#170)
- **Sparse dashboard data fix** — template heading, parser regex, backfill entries (#175, #180)

## [0.15.0] - 2026-02-13

### Added
- **LearningBackend protocol** — pluggable backend abstraction with `BuiltinBandit` (Thompson Sampling) and `QortexLearner` (qortex 0.4.0) adapters. `get_learning_backend()` factory reads `BUILDLOG_LEARNING_BACKEND` env var (#145-#150)
- **BanditPersistence protocol** — bandit state persists to SQLite (auto-detected) or JSONL (fallback). `JsonlPersistence`, `SqlitePersistence`, `resolve_bandit_persistence()` factory (#153)
- **Closed-loop gauntlet learning** — Thompson Sampling rule selection integrated into gauntlet loop with per-rule credit attribution from issue citations (#138)
- **qortex optional dependency** — `pip install buildlog[qortex]` for graph-enhanced rule retrieval
- 47 new tests (LearningBackend protocol, BanditPersistence, E2E interop)
- Total: 1239 tests

## [0.14.1] - 2026-02-07

### Added
- **Bragi v2** — 11 new prose anti-pattern rules from Wikipedia's "Signs of AI writing" field guide: inflated significance framing, superficial participle analysis, puffery language, AI vocabulary blocklist, copula avoidance, challenges-and-future-prospects formula, weasel words, synonym cycling, false ranges, hedging-then-inflating, notability assertion sections (#139)
- Anti-pattern catalog with tiered triage (must-fix / should-fix / ignore) and example rewrites at `bragi/anti-patterns/catalog.md`
- Wikipedia source references on new rules and 3 existing v1 rules

## [0.13.1] - 2026-02-07

### Added
- **Reward-session linking** — `session_id` field on `RewardEvent`, schema v3 migration. `log_reward()` auto-detects active session. MCP `buildlog_log_reward` and `buildlog_rewards` accept `session_id`. CLI `--session` filter on `buildlog reward` and `buildlog rewards` (#28)
- **Reward emission protocol** — new `reward_signal` artifact type emitted to `~/.buildlog/emissions/pending/`. Edges: SUPPORTS (accepted), CHALLENGES (rejected), directional for revisions. Session `part_of` edge when context available
- **npm wrapper help** — `--help` shows command summary when Python CLI not found, `--version` shows wrapper info. Package version synced to 0.13.0 (#78)
- 19 new tests: schema v3 migration, reward round-trip, emission structure, edge direction, boundary cases, integration
- Total: 1150 tests

### Fixed
- SQLite backend now persists all 5 enriched Mistake fields (was silently dropping them) (#118)
- Emission JSON serializer raises TypeError for unknown types instead of silent `default=str` (#119)
- `engine/experiments.py` `log_reward()`/`get_rewards()` synced with `session_id` support
- Removed dead `session_data` parameter from `_reward_to_emission()`
- Emission failure now logs at debug level instead of bare `except: pass`

### Changed
- Schema version 2 → 3 (adds `session_id` + index on `reward_events`)
- YAML emissions config integration tests verify disabled_mappers behavior (#120)
- Module-level `DEFAULT_REGISTRY` singleton documented as intentional (#121)

## [0.13.0] - 2026-02-06

### Added
- **Workflow enforcement** — `verify_workflow()` with 6 checks (buildlog dir, metadata dir, CLAUDE.md workflow section, MCP registration, branch check, hook detection). Exposed as `buildlog verify` CLI (with `--fix` and `--json` flags) and `buildlog_verify` MCP tool (34th tool)
- **Git hooks** — `install_hooks()` installs pre-commit (branch protection for main/master) and post-commit (nudge toward `buildlog commit`). Chains with existing hooks, detects `.pre-commit-config.yaml`, idempotent
- **BUILDLOG_COMMIT env var** — `commit()` sets `BUILDLOG_COMMIT=1` so the post-commit hook suppresses the nudge when using `buildlog commit`
- **CLAUDE_MD_WORKFLOW_SECTION** — 5-step workflow constant with markers (`<!-- buildlog:workflow:start/end -->`) for idempotent injection during `buildlog init` and `buildlog verify --fix`
- **Symlink traversal protection** — `verify_workflow()` resolves `~/.claude.json` and verifies the path stays under `$HOME`
- **Schema v2 enriched mistakes** — 5 new nullable columns (`related_concepts`, `relation_to_prior`, `resolution_action`, `context`, `severity`) for graph-ready mistake metadata
- **Ambient emission protocol** — fire-and-forget artifact emission to `~/.buildlog/emissions/pending/` for downstream systems. Two artifact types: `mistake_manifest` (from `log_mistake()`) and `learned_rules` (from `learn_from_review()`)
- **Edge mapper registry** — 6 pluggable mappers that transform mistakes into graph-compatible manifests with typed edges (`uses`, `challenges`, `supports`, `refines`, `similar_to`, `contradicts`, `requires`, `part_of`, `implements`). Configurable via `~/.buildlog/emissions.yaml`
- **Strict input validation** — `log_mistake()` now validates `severity` (must be low/medium/high/critical) and `relation_to_prior` structure (dict with valid chain type)
- **Self-healing template resolution** — `create_entry()` auto-provisions `_TEMPLATE.md` from bundled sources when missing
- **Qortex integration guide** — `docs/guides/qortex-integration.md` documenting bidirectional data flow, emission protocol, and manifest schemas
- 6 dogfood E2E tests (real git repos, real hooks), 11 CLI integration tests, 2 traversal protection tests
- 61 new tests across emissions, mappers, validation, and property-based testing
- Total: 1126 tests

### Changed
- `install_hooks()` uses YAML parser (`yaml.safe_load`/`yaml.dump`) instead of string concatenation for `.pre-commit-config.yaml` modification
- `buildlog init` now installs git hooks and runs `verify_workflow()` at end of setup. New `--no-hooks` flag to skip hook installation
- Tool count updated from 33 to 34 across all docs, source, and tests

## [0.12.0] - 2026-02-05

### Added
- **Cross-system provenance tracking** — `SeedRule` and `Skill` now carry `provenance: dict` from upstream sources (e.g. qortex knowledge graphs)
- **`buildlog import-seed`** CLI command and `buildlog_import_seed` MCP tool (33 tools total) — import curated seed files with version-aware bandit decay
- **Confidence-weighted seed boosting** — seeds with `provenance.confidence` get proportionally boosted priors in Thompson Sampling (`effective_boost = seed_boost * confidence`)
- **Version-aware bandit decay** — when a seed's `provenance.graph_version` changes on re-import, learned bandit signal is decayed 50% to reduce stale priors
- **Expanded export** — `buildlog export` now supports 6 tables: `rewards`, `sessions`, `mistakes`, `bandit_state`, `learnings`, `skill_decisions`
- **Export manifest** — `manifest.json` generated with `exported_at`, `project_id`, and per-table record counts
- **Rules join table** — `rules.jsonl` maps `buildlog_id` to upstream provenance fields (`source_id`, `source_domain`, `graph_version`, etc.)
- 30 new tests across seeds, skills, bandit, and export modules (966 total)
- **B7: Shared directory protocol** — `ingest_pending()` consumer-side ingest from external producers with 7-layer security validation
- **`buildlog ingest-seeds`** CLI command and `buildlog_ingest_seeds` MCP tool (33 tools total)
- **Signal log** — append-only JSONL event log for seed ingest observability
- **Error sidecars** — `.error` JSON files written next to failed seed files
- **Interop config** — `~/.buildlog/interop.yaml` for multi-source seed ingestion
- 31 new interop tests (997 total)
- SVG plots for theory docs (beta distributions, regret curves, Thompson Sampling convergence)

### Changed
- Default seed rule category changed from `"security"` to `"general"` (less opinionated default)
- `_get_seed_rule_ids()` now returns `(set[str], dict[str, float])` tuple with confidence map
- `ThompsonSamplingBandit.select()` accepts optional `seed_confidence_map` parameter
- `JsonlExporter.export()` accepts `include_manifest`, `include_rules_join`, `seeds_dir` params
- Tool count references updated from 31 to 33 across all docs, source, and tests

## [0.11.1] - 2026-02-05

### Added
- Optional `*_file` parameters on 4 MCP tools that accept large structured data
  - `buildlog_gauntlet_issues`: `issues_file` (alternative to `issues`)
  - `buildlog_learn_from_review`: `issues_file` (alternative to `issues`)
  - `buildlog_gauntlet_accept_risk`: `issues_file` (alternative to `remaining_issues`)
  - `buildlog_gauntlet_generate`: `source_file` (alternative to `source_text`)
- `_resolve_file_or_inline` and `_resolve_text_file_or_inline` helpers with mutual exclusion enforcement
- 19 new tests for file-based parameter resolution (48 total in test_mcp_tools.py)

### Fixed
- `buildlog_log_reward` example in quick-start guide used incorrect parameter names

## [0.11.0] - 2026-02-05

### Added
- **Global SQLite storage backend** at `~/.buildlog/buildlog.db` — replaces per-project JSON/JSONL files
- `StorageBackend` protocol with `SQLiteBackend` and `LegacyBackend` implementations
- Automatic backend resolution: new projects get SQLite, legacy files still work as fallback
- `buildlog migrate [--dry-run]` — migrate legacy files to global DB (non-destructive, idempotent)
- `buildlog export [--format jsonl] [--output DIR] [--tables ...]` — export data to JSONL
- `buildlog_migrate` and `buildlog_export` MCP tools (31 tools total)
- Thread-safe connection pooling for MCP server (long-running process)
- Transaction safety for multi-statement writes (BEGIN IMMEDIATE/COMMIT/ROLLBACK)
- Storage architecture documentation with Mermaid diagrams
- 58 new storage tests (908 total)

### Changed
- All storage operations now go through `StorageBackend` protocol
- Project IDs derived from git remote URL hash (portable) or absolute path hash (fallback)
- Tool count references updated from 29 to 31 across all docs, source, and tests
- `save_learnings()` uses timestamp-based dedup instead of fragile count-based approach
- Migration reports skipped records with line-level error detail

### Fixed
- Connection leak: `get_backend()` no longer opens a new connection per call
- `promote()` now persists to storage backend (was only writing to legacy tracking file)
- `save_id_set()` edge case with empty ID sets
- SQL table name interpolation hardened with whitelist assertion

## [0.10.5] - 2026-02-04

### Changed
- Documentation synced with v0.10.x changes
- Fixed `~/.claude/settings.json` → `~/.claude.json` in docs
- Added "Global Always-On Mode" section to installation guide
- Added `-y`/`--yes` flag documentation throughout
- Tightened hero copy in README and docs index

## [0.10.4] - 2026-02-04

### Added
- `init-mcp` now prompts for confirmation before modifying disk
- Added `-y`/`--yes` flag to skip prompts (non-interactive mode)
- `init --defaults` also skips MCP prompts for CI-friendliness

## [0.10.3] - 2026-02-04

### Fixed
- `buildlog init-mcp --global` now writes to `~/.claude.json` (correct location for Claude Code MCP servers)
- Previously wrote to `~/.claude/settings.json` which Claude Code doesn't read for MCP configs

## [0.10.2] - 2026-02-04

### Fixed
- npm OIDC trusted publishing: added missing `environment` configuration to workflow

## [0.10.1] - 2026-02-03

### Added
- **Global CLAUDE.md**: `buildlog init-mcp --global` now also creates `~/.claude/CLAUDE.md` with usage instructions, so Claude proactively uses buildlog tools
- Concise global instructions section with core loop, key tools table, and outputs list

### Changed
- README prominently features "Always-On Mode" as the recommended installation approach

## [0.10.0] - 2026-02-03

### Added
- **Full MCP/CLI parity**: 10 new MCP tools bringing total from 19 to 29
- P0 gauntlet loop: `buildlog_commit`, `buildlog_gauntlet_prompt`, `buildlog_gauntlet_loop`
- P1 learning pipeline: `buildlog_distill`, `buildlog_skills`, `buildlog_stats`, `buildlog_gauntlet_list_personas`
- P2 nice-to-have: `buildlog_gauntlet_generate`, `buildlog_init`, `buildlog_update`
- **Global always-on mode**: `buildlog init-mcp --global` registers MCP in `~/.claude/settings.json`
- **Graceful fallbacks**: Commands return useful state instead of erroring when `buildlog/` missing
- MCP is now a default dependency (no `[mcp]` extra needed)
- `buildlog init --defaults` auto-registers MCP server
- `buildlog mcp-test` verifies all 29 tools are registered
- 9 new core operations with result dataclasses
- E2E user flow test suite (7 flows, ~20 tests)
- 180+ new unit/integration tests (total: ~830)

### Changed
- CLAUDE.md constant references all 29 tools with workflow docs
- Documentation updated: README, MCP guide, installation guide
- Commands that required `buildlog/` now return empty/default state with `initialized: false`

### Fixed
- Stale "19 tools" references across docs and tests
- Root commit file detection in `commit()` (ls-tree fallback)

## [0.9.0] - 2026-02-01

### Added
- **Bragi persona**: LLM prose pattern detection with 9 rules (em-dash abuse, tricolons, performative honesty, rhythmic closers, etc.)
- **Bragi Claude Code skill**: interactive markdown review with 3 ranked rewrite suggestions per finding
- **Auto-gauntlet**: hybrid commit gate with Claude Code hooks
- **Thompson Sampling bandit**: rule selection via contextual bandits with Beta posteriors
- **Metered LLM backend**: token usage and cost tracking, pure Python statistics
- **npm wrapper**: `npx @peleke.s/buildlog` for JS/TS projects
- npm publish job in release workflow

### Changed
- README de-LLM-ified: removed all em dashes and LLM prose patterns (dogfooded via bragi)
- Package scope changed to `@peleke.s/buildlog` on npm

## [0.8.0] - 2026-01-31

### Added
- **LLM Extractor**: `LLMExtractor` wires `LLMBackend.extract_rules()` into the seed engine as a `RuleExtractor` implementation
- **`Pipeline.with_llm()`**: Convenience constructor for LLM-powered seed generation
- **`buildlog commit`**: Wraps `git commit` and appends commit context to today's buildlog entry automatically
- **`buildlog gauntlet generate`**: Generate seed rules from source text using LLM extraction
- **Ollama smoke tests**: Real LLM integration tests (skipped in CI, runnable locally with `--run-ollama`)
- E2E tests for full extract → seed → learn → persist loop

### Fixed
- Date validation in `buildlog new` now rejects invalid dates (e.g., month=99) using `datetime.strptime`
- `pytest_addoption` moved from test file to `conftest.py` (proper pytest hook location)
- Ollama availability check deferred to runtime instead of import time (faster test collection)
- Removed private attribute access in `LLMExtractor` metadata

## [0.7.0] - 2026-01-22

### Added
- Gauntlet Loop: Auto-fix criticals, HITL checkpoints for majors/minors
- MCP tools: `buildlog_gauntlet_issues`, `buildlog_gauntlet_accept_risk`
- CLI command: `buildlog gauntlet loop`
- Optional GitHub issue creation when accepting risk
- Defense-in-depth schema validation for seed files
- Input sanitization for subprocess calls

### Changed
- Consolidated release workflow (OIDC-only, version validation)

### Fixed
- Edge case handling for malformed JSONL, empty files, missing directories

## [0.6.1] - 2026-01-22

### Fixed
- Seeds now properly bundled in PyPI package
- `buildlog gauntlet` works immediately after `pip install buildlog`
- New `get_default_seeds_dir()` with priority: local > template > package

## [0.6.0] - 2026-01-22

### Added
- **Review Gauntlet CLI**: Run code through ruthless reviewer personas
  - `buildlog gauntlet list` - Show available reviewers
  - `buildlog gauntlet rules` - Export rules (YAML/JSON/markdown)
  - `buildlog gauntlet prompt` - Generate review prompt
  - `buildlog gauntlet learn` - Persist learnings from review
- **Reviewer Personas**:
  - Security Karen: OWASP Top 10, auth, injection, secrets (13 rules)
  - Test Terrorist: Coverage, property-based, metamorphic, contracts (21 rules)
- **Seed Engine**: Infrastructure for creating defensible reviewer personas
  - Source manifests for tracking authoritative references
  - YAML seed file generation with context, antipattern, rationale

## [0.5.0] - 2026-01-22

### Added
- Reward signal tracking for bandit learning
- Session tracking and experiment infrastructure
- Pitch-focused README with falsifiability manifesto

## [0.4.0] - 2026-01-17

### Added
- **Review Learning System**: Learn from code reviews in real-time
  - `buildlog_learn_from_review()` MCP tool
  - Rules extracted from reviews gain confidence through reinforcement
- **Reviewer Skills**: Four ruthless reviewer personas
  - Ruthless Reviewer, Test Terrorist, Security Karen, Review Gauntlet
  - Structured JSON output compatible with learning system

## [0.3.0] - 2026-01-17

### Added
- Continuous confidence scoring (0-1) for skills
- Confidence tiers: Speculative, Provisional, Stable, Entrenched
- ConfidenceMetrics tracking with serialization

### Changed
- Skills now have both discrete (high/medium/low) and continuous scores

### Fixed
- Edge case handling for negative days, timezone-naive, bounds validation

## [0.2.0] - 2026-01-16

### Added
- CI/CD workflow with linting and auto-publish

## [0.1.0] - 2026-01-16

### Added
- **Core CLI**:
  - `buildlog init` - Initialize in any project
  - `buildlog new` - Create structured entries
  - `buildlog distill` - Extract patterns from entries
  - `buildlog skills` - Generate deduplicated, scored skills
  - `buildlog stats` - Analytics and coverage metrics
- **MCP Server** (Claude Code integration):
  - `buildlog_status`, `buildlog_promote`, `buildlog_reject`, `buildlog_diff`
- **Embedding Backends**: Token-based, sentence-transformers, OpenAI

[Unreleased]: https://github.com/Peleke/buildlog-template/compare/v0.13.1...HEAD
[0.13.1]: https://github.com/Peleke/buildlog-template/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/Peleke/buildlog-template/compare/v0.12.0...v0.13.0
[0.10.2]: https://github.com/Peleke/buildlog-template/compare/v0.10.1...v0.10.2
[0.10.1]: https://github.com/Peleke/buildlog-template/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/Peleke/buildlog-template/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/Peleke/buildlog-template/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/Peleke/buildlog-template/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Peleke/buildlog-template/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/Peleke/buildlog-template/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/Peleke/buildlog-template/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Peleke/buildlog-template/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Peleke/buildlog-template/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Peleke/buildlog-template/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Peleke/buildlog-template/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Peleke/buildlog-template/releases/tag/v0.1.0
