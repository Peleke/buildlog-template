# Build Journal: Emissions Protocol — Validation + Docs Pass

**Date:** 2026-02-06
**Duration:** ~1 hour (continuation session)
**Status:** Complete

---

## The Goal

Close out the emissions protocol PR (#117) by addressing gauntlet findings: add strict input validation for `severity` and `relation_to_prior` fields, create tracking issues for accepted minors, and ensure all documentation reflects the new features.

---

## What We Built

### Components

| Component | Status | Notes |
|-----------|--------|-------|
| Input validation (severity) | Working | Rejects invalid values at API boundary |
| Input validation (relation_to_prior) | Working | Validates dict shape + chain type |
| 7 validation tests | Working | Covers valid/invalid/edge cases |
| GH issues #118-#121 | Created | Tracking accepted gauntlet minors |
| GH #115 comment | Added | Configurable accept_risk modes (auto/prompt/silent) |
| README updates | Working | Tool count fix, emission protocol mention |
| CHANGELOG [Unreleased] | Working | Schema v2, emissions, mappers, validation |
| MCP integration guide | Working | Emission notes on tool descriptions |
| constants.py | Working | Emissions in outputs section |

---

## The Journey

### Phase 1: Input Validation

Added validation at top of `log_mistake()` before any storage operations:
- `severity` must be one of `{low, medium, high, critical}` or None
- `relation_to_prior` must be a dict with `id` and `type` keys
- `type` must be one of `{escalation, same_pattern, regression, caused_by, part_of}`

All 7 tests pass. 1061 total suite green.

### Phase 2: GH Issue Triage

Created 4 issues from accepted gauntlet minors:
- #118: SQLite round-trip property test
- #119: Explicit JSON serializer (no default=str)
- #120: YAML config integration test
- #121: Module-level singleton evaluation

Added comment to #115 about configurable `accept_risk` behavior.

### Phase 3: Documentation Sweep

Thorough review found:
- README tool count mismatch (32 vs 33) — fixed
- Missing emissions in README "What Else" section — added
- Stale version "v0.11" in Current Limits — fixed to v0.12
- Missing CHANGELOG [Unreleased] section — added
- constants.py outputs missing emissions — added
- MCP integration guide missing emission notes — added

---

## Test Results

### Full Suite

**Command:**
```bash
uv run pytest tests/ -v
```

**Result:** 1061 passed, 3 skipped. Zero failures.

---

## Files Changed

```
src/buildlog/core/
└── operations.py          # Validation for severity + relation_to_prior
tests/
└── test_core_operations.py # 7 new validation tests
README.md                   # Tool count fix, emissions mention
CHANGELOG.md                # [Unreleased] section
src/buildlog/constants.py   # Emissions in outputs
docs/guides/
└── mcp-integration.md      # Emission notes on tools
```

---

## Improvements

### Workflow

- Run gauntlet findings through structured triage: fix what's quick, create issues for what's deferred
- The accept_risk → GH issue pipeline should be automated (tracked in #115)

### Architectural

- Input validation at the API boundary catches bad data early — worth doing for all enum-like fields

---

*Next: merge PR #117, then tackle #118-#121 follow-up issues*

## Commits

### `0e35ca6` — feat: workflow enforcement — CLAUDE_MD_WORKFLOW_SECTION + verify_workflow() + MCP tool + CLI

Files:
- `.claude/skills/bragi.md`
- `README.md`
- `src/buildlog/cli.py`
- `src/buildlog/constants.py`
- `src/buildlog/core/__init__.py`
- `src/buildlog/core/operations.py`
- `src/buildlog/mcp/server.py`
- `src/buildlog/mcp/tools.py`
- `tests/test_e2e_flows.py`
- `tests/test_e2e_v010.py`
- `tests/test_mcp_server.py`
- `tests/test_p2_nice_to_have.py`
- `tests/test_verify_workflow.py`


### `c0646f5` — feat: add citable rule IDs to gauntlet prompt and config (Touch 1)

Files:
- `src/buildlog/core/operations.py`
- `src/buildlog/seeds.py`


### `3375160` — feat: citation validation, aggregation, and per-rule bandit credit (Touch 2+3)

Files:
- `src/buildlog/core/operations.py`
- `src/buildlog/mcp/tools.py`


### `0e93826` — test: add 24 tests for rule-level attribution, update instruction count test

Files:
- `tests/test_p0_gauntlet.py`
- `tests/test_rule_attribution.py`
