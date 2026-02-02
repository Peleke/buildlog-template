# P2: MCP Nice-to-Have — 3 Tools

## Goal
Complete the MCP surface. These round out the tool set but aren't required for the core review/learning loops.

## Tools

### 1. `buildlog_gauntlet_generate(source_text, persona, output_dir?, dry_run?)`
- **Core op**: `gauntlet_generate(source_text, persona, output_dir?, dry_run?) -> GauntletGenerateResult`
- **Dataclass**: `GauntletGenerateResult(persona, rule_count, source_count, output_path, preview, message, error)`
- **What it does**: Runs seed engine pipeline with LLM to produce YAML seed rules from arbitrary source text
- **Extract from**: `cli.py` gauntlet generate command (lines ~1921-1982)
- **Key design**: Takes `source_text` as string (not file path) — MCP caller reads file, passes content
- **Edge cases**: no LLM backend → error, empty source → error, dry_run populates preview only

### 2. `buildlog_init(defaults?, no_claude_md?, no_mcp?)`
- **Core op**: `init_buildlog(project_dir, defaults?, no_claude_md?, no_mcp?) -> InitResult`
- **Dataclass**: `InitResult(initialized, buildlog_dir, claude_md_updated, mcp_registered, message, error)`
- **What it does**: Runs copier to scaffold buildlog/, creates .buildlog/, updates CLAUDE.md, registers MCP
- **Extract from**: `cli.py` init command (lines ~51-161)
- **Key design**: Always `defaults=True` in MCP context (non-interactive). Extract `get_template_dir()` to shared utility.
- **Edge cases**: already exists → error, copier missing → error, copier timeout (60s) → error, no CLAUDE.md → skip

### 3. `buildlog_update()`
- **Core op**: `update_buildlog(project_dir) -> UpdateResult`
- **Dataclass**: `UpdateResult(updated, message, error)`
- **What it does**: Runs `copier update --trust` to pull latest template changes
- **Extract from**: `cli.py` update command (lines ~631-658)
- **Edge cases**: copier fails → error, no .copier-answers.yml → error, timeout (120s) → error

## Shared Concern: `get_template_dir()`
Both init and update need this function, currently only in cli.py. Move to `buildlog/utils.py` or `buildlog/core/operations.py`.

## Files Modified

| File | Change |
|------|--------|
| `src/buildlog/core/operations.py` | Add 3 dataclasses + 3 functions + `__all__` |
| `src/buildlog/core/__init__.py` | Add exports |
| `src/buildlog/mcp/tools.py` | Add 3 wrapper functions |
| `src/buildlog/mcp/server.py` | Import + register 3 tools |
| `src/buildlog/mcp/__init__.py` | Update exports |
| `src/buildlog/cli.py` | Extract `get_template_dir()`, update expected tool count |

## Tests (16 cases)

**gauntlet_generate**: dry_run returns preview, no LLM → error, empty source → error, generates seed file (mocked LLM), returns dict
**init**: creates buildlog dir, fails if exists, updates CLAUDE.md, skips CLAUDE.md when opted out, returns dict, handles missing copier
**update**: succeeds (mocked), fails gracefully, handles timeout, handles missing copier, returns dict

## Dependencies
- **No hard dependency on P0 or P1.** All three tools are self-contained.
- `gauntlet_generate` requires LLM backend (Ollama/Anthropic) at runtime.

## Tool count after P2: 29 (26 + 3)

## Final tool count: 29 (15 original + 4 v0.10.0 + 3 P0 + 4 P1 + 3 P2)
