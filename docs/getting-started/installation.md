# Installation

## Requirements

- Python 3.10+
- A virtual environment (PEP 668 blocks system-level installs)

## Install

=== "uv (recommended)"

    ```bash
    uv pip install buildlog
    ```

=== "pip"

    ```bash
    pip install buildlog
    ```

## Optional extras

| Extra | What it adds | Install |
|-------|-------------|---------|
| `mcp` | MCP server for Claude Code integration | `pip install buildlog[mcp]` |
| `embeddings` | Local sentence-transformers for semantic dedup | `pip install buildlog[embeddings]` |
| `openai` | OpenAI embeddings for semantic dedup | `pip install buildlog[openai]` |
| `engine` | Documents the engine namespace (no extra deps) | `pip install buildlog[engine]` |
| `all` | Everything above | `pip install buildlog[all]` |
| `dev` | Development tools (pytest, black, mypy, etc.) | `pip install buildlog[dev]` |

## Initialize

```bash
buildlog init              # Interactive setup
buildlog init --defaults   # Non-interactive (CI-friendly)
```

This creates the `.buildlog/` directory in your project with default configuration.
