# 2026-02-05

## Commits

### `b1e63a0` — feat(storage): add storage package with StorageBackend protocol, SQLite + Legacy backends, migrate, and exporters

Files:
- `src/buildlog/storage/__init__.py`
- `src/buildlog/storage/base.py`
- `src/buildlog/storage/exporters.py`
- `src/buildlog/storage/legacy.py`
- `src/buildlog/storage/migrate.py`
- `src/buildlog/storage/schema.py`
- `src/buildlog/storage/sqlite.py`


### `c32bb10` — feat(storage): wire operations.py, experiments.py, and skills.py to use storage backend

Files:
- `src/buildlog/core/operations.py`
- `src/buildlog/engine/experiments.py`
- `src/buildlog/skills.py`


### `25bbd69` — feat(cli): add migrate and export commands, add sqlite-vec dependency

Files:
- `pyproject.toml`
- `src/buildlog/cli.py`


### `951de18` — feat(mcp): add buildlog_migrate and buildlog_export MCP tools

Files:
- `src/buildlog/mcp/server.py`
- `src/buildlog/mcp/tools.py`
- `tests/test_e2e_flows.py`
- `tests/test_e2e_v010.py`
- `tests/test_mcp_server.py`
- `tests/test_p2_nice_to_have.py`


### `a533b4d` — feat: add _file param alternatives to 4 MCP tools

Files:
- `src/buildlog/mcp/tools.py`


### `f01eaec` — chore: bump version 0.11.0 → 0.11.1

Files:
- `pyproject.toml`


### `a55d9a7` — docs: add CHANGELOG entry for v0.11.1, fix stale quick-start example

Files:
- `CHANGELOG.md`
- `docs/getting-started/quick-start.md`


### `48c1f98` — feat: B7 shared directory protocol — consumer-side ingest from external producers (#106)

Files:
- `src/buildlog/cli.py`
- `src/buildlog/constants.py`
- `src/buildlog/interop.py`
- `src/buildlog/mcp/server.py`
- `src/buildlog/mcp/tools.py`
- `tests/test_e2e_flows.py`
- `tests/test_e2e_v010.py`
- `tests/test_interop.py`
- `tests/test_mcp_server.py`
- `tests/test_p2_nice_to_have.py`


### `76c6248` — fix: gauntlet review findings -- extract _fail_file helper, add CLI tests, fix assertion gap

Files:
- `src/buildlog/interop.py`
- `tests/test_interop.py`
