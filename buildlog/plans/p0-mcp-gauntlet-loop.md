# P0: MCP Gauntlet Loop — 3 Tools

## Goal
Close the gauntlet review loop via MCP. Without these, an agent cannot commit code, generate review prompts, or orchestrate the review→fix→repeat cycle.

## Tools

### 1. `buildlog_commit(message, slug?, no_entry?, extra_args?)`
- **Core op**: `commit(buildlog_dir, git_args, slug?, entry?, no_entry?, cwd?) -> CommitResult`
- **Dataclass**: `CommitResult(commit_hash, commit_message, files_changed, entry_path, entry_updated, message, error)`
- **What it does**: Runs `git commit`, extracts commit info, appends commit block to today's buildlog entry
- **Extract from**: `cli.py` commit command (lines ~540-620)
- **Helper needed**: `_resolve_entry_path_core(buildlog_dir, today, slug, explicit, cwd)` — extracted from CLI lines 561-598
- **Edge cases**: non-git dir → error, `no_entry=True` skips entry, creates entry if missing, `cwd` param for MCP process isolation

### 2. `buildlog_gauntlet_prompt(target, personas?)`
- **Core op**: `generate_gauntlet_prompt(target, personas?) -> GauntletPromptResult`
- **Dataclass**: `GauntletPromptResult(prompt, target, personas, total_rules, message, error)`
- **What it does**: Loads seed rules, combines with target path into a formatted review prompt with output format template
- **Extract from**: `cli.py` gauntlet prompt command (lines ~1808-1845)
- **Edge cases**: no seeds → error, invalid persona → error with available list

### 3. `buildlog_gauntlet_loop(target, personas?, max_iterations?, stop_at?, auto_gh_issues?)`
- **Core op**: `gauntlet_loop_config(target, personas?, max_iterations?, stop_at?, auto_gh_issues?) -> GauntletLoopConfigResult`
- **Dataclass**: `GauntletLoopConfigResult(target, personas, max_iterations, stop_at, auto_gh_issues, rules_by_persona, instructions, issue_format, prompt, message, error)`
- **What it does**: Returns everything an agent needs to run the review-fix-repeat loop (rules, prompt, instructions, issue format)
- **Note**: This is NOT the loop itself — it's the config. The agent executes the loop by calling gauntlet_issues/gauntlet_accept_risk.
- **Depends on**: `generate_gauntlet_prompt` (internal call, same file)

## Files Modified

| File | Change |
|------|--------|
| `src/buildlog/core/operations.py` | Add 3 dataclasses + 4 functions (incl. helper) + `__all__` |
| `src/buildlog/core/__init__.py` | Add exports |
| `src/buildlog/mcp/tools.py` | Add 3 wrapper functions |
| `src/buildlog/mcp/server.py` | Import + register 3 tools |
| `src/buildlog/mcp/__init__.py` | Update exports |

## Tests (13 cases)

**CommitResult**: git failure → error, success in git repo, updates entry, no_entry flag, creates entry if missing
**GauntletPromptResult**: returns prompt, filters personas, invalid persona → error, includes output format
**GauntletLoopConfigResult**: returns all fields, includes prompt, respects max_iterations, filters personas

## Dependencies
- None. P0 is standalone.

## Tool count after P0: 22 (19 + 3)
