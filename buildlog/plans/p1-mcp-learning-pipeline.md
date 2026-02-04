# P1: MCP Learning Pipeline — 4 Tools

## Goal
Enable the learning pipeline via MCP. Without these, an agent cannot distill patterns, generate skills, view stats, or discover available personas.

## Tools

### 1. `buildlog_distill(since?, category?, llm?, buildlog_dir?)`
- **No new core op needed** — calls `distill_all()` from `buildlog.distill` directly
- **Returns**: `DistillResult.to_dict()` — `{extracted_at, entry_count, patterns, statistics}`
- **What it does**: Parses Improvements sections from entries, aggregates insights by category
- **Edge cases**: invalid date → error, invalid category → error, missing dir → error, LLM fallback is silent

### 2. `buildlog_skills(min_frequency?, since?, llm?, buildlog_dir?)`
- **No new core op needed** — calls `generate_skills()` from `buildlog.skills` directly
- **Returns**: `SkillSet.to_dict()` — `{generated_at, source_entries, total_skills, skills}`
- **What it does**: Transforms distilled patterns into actionable rules with dedup, confidence scoring, stable IDs
- **Edge cases**: invalid date → error, missing dir → error, min_frequency=99 → empty result

### 3. `buildlog_stats(since?, detailed?, buildlog_dir?)`
- **No new core op needed** — calls `calculate_stats()` + `stats_to_dict()` from `buildlog.stats`
- **Returns**: `{entries, insights, top_sources, pipeline, streak, warnings}`
- **What it does**: Analytics on entry counts, improvement coverage, categories, streaks, quality warnings
- **Edge cases**: `detailed=False` strips top_sources for compact responses, invalid date → error

### 4. `buildlog_gauntlet_list_personas(buildlog_dir?)`
- **No new core op needed** — calls `load_all_seeds()` from `buildlog.seeds`
- **Returns**: `{personas: {name: {rules_count, version}}, total_rules, total_personas}`
- **What it does**: Lists available reviewer personas with rule counts and versions
- **Edge cases**: no seeds dir → error, empty seeds → error

## Design Decision

These 4 tools call existing module functions directly (Option B) rather than adding wrappers in `operations.py`. The existing functions already return proper dataclasses with `to_dict()` methods. Adding another layer would be pure indirection.

## Files Modified

| File | Change |
|------|--------|
| `src/buildlog/mcp/tools.py` | Add 4 wrapper functions |
| `src/buildlog/mcp/server.py` | Import + register 4 tools |
| `src/buildlog/mcp/__init__.py` | Update exports |
| `tests/test_mcp_tools.py` | Add 4 test classes |

## Tests (22 cases)

**distill**: returns dict, has keys, missing dir → error, since filter, category filter, invalid date, invalid category
**skills**: returns dict, has keys, missing dir → error, min_frequency filters, invalid since
**stats**: returns dict, has keys, missing dir → error, detailed includes top_sources, not detailed omits, invalid since
**gauntlet_list_personas**: returns dict, has keys, personas have rule_counts

## Dependencies
- **No dependency on P0.** All 4 tools use existing modules that are already implemented.

## Tool count after P1: 26 (22 + 4)
