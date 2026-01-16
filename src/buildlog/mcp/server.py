"""Buildlog MCP server for Claude Code integration."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from buildlog.mcp.tools import (
    buildlog_diff,
    buildlog_promote,
    buildlog_reject,
    buildlog_status,
)

mcp = FastMCP("buildlog")

# Register tools
mcp.tool()(buildlog_status)
mcp.tool()(buildlog_promote)
mcp.tool()(buildlog_reject)
mcp.tool()(buildlog_diff)


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
