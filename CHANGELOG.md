# Changelog

All notable changes to buildlog are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Peleke/buildlog-template/compare/v0.10.2...HEAD
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
