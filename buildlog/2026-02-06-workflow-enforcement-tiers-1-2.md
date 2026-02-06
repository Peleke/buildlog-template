# Build Journal: Workflow Enforcement — Tiers 1 + 2

**Date:** 2026-02-06
**Duration:** ~2 hours (continuation session)
**Status:** Complete

---

## The Goal

Close the workflow enforcement loop. buildlog captures data, but nothing enforced the workflow that generates that data. Agents (and humans) could skip the ceremony, commit directly to main, and bypass the gauntlet. This PR makes the workflow self-enforcing: hooks prevent commits to main, nudge toward `buildlog commit`, and `buildlog verify` checks that the full stack is set up.

Split from #115 into three tiers: Tier 1 (verify infrastructure), Tier 2 (hooks + enforcement), Tier 3 (configurable accept_risk — deferred to #124).

---

## What We Built

### Components

| Component | Status | Notes |
|-----------|--------|-------|
| CLAUDE_MD_WORKFLOW_SECTION constant | Working | 5-step workflow with markers for idempotent injection |
| verify_workflow() (6 checks) | Working | buildlog_dir, metadata_dir, workflow_section, mcp_registered, not_on_main, branch_protection |
| buildlog_verify MCP tool | Working | 34th tool |
| `buildlog verify` CLI | Working | --json and --fix flags |
| Pre-commit hook (branch protection) | Working | Blocks commits to main/master |
| Post-commit hook (nudge) | Working | Fires when BUILDLOG_COMMIT unset |
| BUILDLOG_COMMIT env var | Working | Set by commit() to suppress nudge |
| install_hooks() | Working | Chains with existing hooks, .pre-commit-config.yaml detection, idempotent |
| Symlink traversal protection | Working | Resolves ~/.claude.json, verifies path stays under $HOME |
| YAML parser for hook config | Working | yaml.safe_load/dump replaces string concat |
| 6 dogfood E2E tests | Working | Real git repos, real hooks, no mocks |
| 11 CLI integration tests | Working | CliRunner-based verify + init paths |
| 2 traversal protection tests | Working | Symlink escape + normal path |

---

## The Journey

### Phase 1: Tier 1 — Verify Infrastructure

Built the foundation: `CLAUDE_MD_WORKFLOW_SECTION` constant with start/end markers for idempotent injection, `verify_workflow()` with 6 checks, MCP wrapper, CLI command with --fix and --json.

The `--fix` flag detects missing workflow section and injects it into CLAUDE.md (creating the file if needed). `_quick_workflow_check()` provides a lightweight subset for `get_overview()`.

26 unit tests covering all check types and edge cases.

### Phase 2: Tier 2 — Hooks + Enforcement

Pre-commit hook blocks main/master. Post-commit hook checks `BUILDLOG_COMMIT` env var — if unset, prints a nudge toward `buildlog commit`. The `commit()` function sets `BUILDLOG_COMMIT=1` in subprocess env to suppress the nudge.

Hook chaining: `install_hooks()` detects existing hooks and appends (strips shebang). Detects `.pre-commit-config.yaml` and adds a YAML entry instead of standalone hook. All idempotent.

17 unit tests for hooks + constants + env var.

### Phase 3: Gauntlet Fixes

Gauntlet found 5 minors. Fixed 4, accepted 1 (em-dash in constants):

1. **Traversal protection**: `verify_workflow()` now resolves symlinks on `~/.claude.json` and verifies the resolved path stays under `$HOME` via `is_relative_to()`.
2. **YAML parser**: Replaced string concatenation with `yaml.safe_load()` + dict manipulation + `yaml.dump()` for `.pre-commit-config.yaml` modification.
3. **CLI integration tests**: 5 tests for `verify --fix` (basic output, JSON, fix injection, fix creates CLAUDE.md, idempotent).
4. **Init integration tests**: 4 tests for init hook+verify path (mock copier only, let real git + hooks through).

### Phase 4: Dogfood Tests

The real proof. 6 tests in real git repos with real hooks — no mocks:

- Pre-commit hook blocks commit on main (exit code != 0, "not allowed" in output)
- Pre-commit hook allows commit on feature branch
- Post-commit nudge fires without BUILDLOG_COMMIT
- Post-commit nudge silent with BUILDLOG_COMMIT=1
- verify --fix detect/repair/verify cycle
- Full init produces working enforcement (hooks installed + executable + CLAUDE.md injected + main blocked + feature branch works)

### Phase 5: Bragi Docs Review

Found and fixed:
- Tool count 33->34 across 4 docs
- buildlog_verify added to mcp-integration tool table
- verify command added to cli-reference
- CHANGELOG Unreleased link fixed (v0.10.2->v0.12.0)
- Workflow enforcement added to README feature list

---

## Test Results

### Full Suite

**Command:**
```bash
uv run pytest tests/ -v
```

**Result:** 1126 passed, 3 skipped. Zero failures.

### Dogfood Tests

**Command:**
```bash
uv run pytest tests/test_workflow_enforcement_dogfood.py -v
```

**Result:** 6/6 passed in 2.12s. Real git, real hooks, no mocks.

---

## Improvements

### Workflow

- Dogfood tests > integration tests for enforcement features. If the hook doesn't actually block `git commit`, a unit test won't catch it.
- The copier mock pattern (let real subprocess through, only intercept copier) is reusable: capture `subprocess.run` at class definition time, check command args in side_effect.

### Architectural

- `is_relative_to()` (Python 3.9+) is cleaner than string prefix comparison for path traversal checks.
- YAML dict constant + `yaml.dump()` is safer than string concat for config file modification — preserves structure, catches malformed input.

---

## Files Changed

```
src/buildlog/
├── constants.py             # CLAUDE_MD_WORKFLOW_SECTION + markers
├── hooks.py                 # NEW: pre/post-commit hooks, install_hooks(), YAML parser
├── core/
│   ├── __init__.py          # Export VerifyCheck, VerifyResult, verify_workflow
│   └── operations.py        # verify_workflow(), _quick_workflow_check(), traversal protection, BUILDLOG_COMMIT env
├── mcp/
│   ├── tools.py             # buildlog_verify() wrapper
│   └── server.py            # Register 34th tool
└── cli.py                   # verify command (--fix, --json), init hooks+verify, --no-hooks
tests/
├── test_workflow_enforcement_dogfood.py  # NEW: 6 dogfood E2E tests
├── test_verify_workflow.py              # 54 tests (26 unit + 11 CLI integration + 2 traversal + 15 existing)
├── test_hooks.py                        # 17 tests
├── test_e2e_v010.py                     # Tool list updated (34)
├── test_e2e_flows.py                    # Tool count updated
├── test_p2_nice_to_have.py              # Tool count updated
└── test_mcp_server.py                   # Tool count updated
docs/
├── guides/mcp-integration.md            # Tool count + buildlog_verify row
├── guides/cli-reference.md              # verify command + tool count
├── getting-started/installation.md      # Tool count
└── ecosystem-exploration/01-buildlog.md # Tool count
README.md                                # Workflow enforcement feature
CHANGELOG.md                             # Unreleased link fix
```

---

## Commits

### `0e35ca6` — feat: workflow enforcement — CLAUDE_MD_WORKFLOW_SECTION + verify_workflow() + MCP tool + CLI

### `768315b` — feat: git hooks + BUILDLOG_COMMIT env var for workflow enforcement

### `d3e6f5d` — fix: address gauntlet minors — traversal protection, YAML parser, CLI integration tests

### `a7aa8b2` — test: add dogfood E2E tests for workflow enforcement + fix doc issues

### `e0a2761` — docs: add workflow enforcement to README feature list

---

*Next: merge PR #125, close #122 + #123, then release v0.13.0*
