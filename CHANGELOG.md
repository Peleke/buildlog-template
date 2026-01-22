# Changelog

All notable changes to buildlog are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Peleke/buildlog-template/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/Peleke/buildlog-template/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/Peleke/buildlog-template/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Peleke/buildlog-template/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Peleke/buildlog-template/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Peleke/buildlog-template/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Peleke/buildlog-template/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Peleke/buildlog-template/releases/tag/v0.1.0
