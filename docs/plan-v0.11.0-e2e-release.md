# E2E User Flow Tests + v0.11.0 Release Readiness

## Part 1: Create `tests/test_e2e_flows.py`

7 test classes covering every critical user flow. CI-runnable, no LLM required.

### Flow 1: Fresh Init (`TestFlowFreshInit`)
- Mock copier via `patch("subprocess.run")`
- `init_buildlog(tmp_path)` with CLAUDE.md pre-existing
- Assert: `buildlog/` created, `.buildlog/seeds/` exists
- Assert: CLAUDE.md contains all 29 tool names
- Assert: `.claude/settings.json` has `mcpServers.buildlog.command == "buildlog-mcp"`

### Flow 2: Commit → Entry Loop (`TestFlowCommitEntry`)
- Real git repo via subprocess
- `create_entry` → stage → `commit` → verify entry has commits section
- `list_entries` → count == 1, `get_overview` → entries == 1

### Flow 3: Gauntlet Review Loop (`TestFlowGauntletLoop`)
- `generate_gauntlet_prompt` → has rules
- `gauntlet_loop_config` → all fields populated
- `gauntlet_process_issues` with 3 mock issues → categorized, has next_action
- `gauntlet_accept_risk` → accepted
- `learn_from_review` → persisted to `.buildlog/review_learnings.json`

### Flow 4: Skill Extraction & Promotion (`TestFlowSkillPromotion`)
- `buildlog_distill` → patterns extracted
- `buildlog_skills` → total_skills >= 0
- `buildlog_stats` → has entries/insights
- `status` → skills listed
- `diff` → pending count
- `promote` → CLAUDE.md has rules markers

### Flow 5: Experiment Tracking (`TestFlowExperiment`)
- `start_session` → session_id, `active_session.json` exists
- `log_mistake` × 2 → `mistakes.jsonl` has 2 lines
- `end_session` → `active_session.json` gone
- `get_session_metrics` → total_mistakes == 2
- `get_experiment_report` → total_sessions >= 1

### Flow 6: MCP Server Completeness (`TestFlowMCPServer`)
- `await mcp.list_tools()` → 29 tools
- Each has `buildlog_` prefix, description > 10 chars, schema type == "object"
- All 29 names present

### Flow 7: Idempotent Init (`TestFlowIdempotentInit`)
- Double init → second returns "already exists" error
- Preserves other MCP servers in settings.json
- No duplicate buildlog entry

## Part 2: CHANGELOG entry for v0.11.0

Added under `[Unreleased]` in CHANGELOG.md.

## Part 3: Release prep

1. Write `tests/test_e2e_flows.py` ✅
2. Add CHANGELOG entry ✅
3. Commit to `feat/mcp-full-parity`
4. Create GitHub issue for tracking
5. Merge PR #75 to main
6. `./scripts/release.sh 0.11.0`
