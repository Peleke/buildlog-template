"""Integration tests for buildlog MCP server.

Tests that the MCP server correctly exposes tools.
"""

import pytest

# Skip these tests if mcp is not installed
pytest.importorskip("mcp")


class TestMCPServerSetup:
    """Tests for MCP server configuration."""

    def test_server_imports(self):
        """Server module should import without error."""
        from buildlog.mcp.server import main, mcp

        assert mcp is not None
        assert callable(main)

    def test_server_has_name(self):
        """Server should have correct name."""
        from buildlog.mcp.server import mcp

        assert mcp.name == "buildlog"

    @pytest.mark.asyncio
    async def test_tools_are_registered(self):
        """All tools should be registered on the server."""
        from buildlog.mcp.server import mcp

        # Use public API to list tools
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]

        assert "buildlog_status" in tool_names
        assert "buildlog_promote" in tool_names
        assert "buildlog_reject" in tool_names
        assert "buildlog_diff" in tool_names


@pytest.mark.asyncio
async def test_list_tools():
    """Test that tools can be listed via MCP protocol."""
    from buildlog.mcp.server import mcp

    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]

    assert "buildlog_status" in tool_names
    assert "buildlog_promote" in tool_names
    assert "buildlog_reject" in tool_names
    assert "buildlog_diff" in tool_names


@pytest.mark.asyncio
async def test_tool_has_description():
    """Tools should have descriptions for MCP."""
    from buildlog.mcp.server import mcp

    tools = await mcp.list_tools()

    for tool in tools:
        assert tool.description, f"Tool {tool.name} missing description"
        # Descriptions should be meaningful
        assert len(tool.description) > 20, f"Tool {tool.name} has too short description"


@pytest.mark.asyncio
async def test_tool_has_input_schema():
    """Tools should have input schemas for MCP."""
    from buildlog.mcp.server import mcp

    tools = await mcp.list_tools()

    for tool in tools:
        assert tool.inputSchema is not None, f"Tool {tool.name} missing input schema"
        assert "type" in tool.inputSchema, f"Tool {tool.name} schema missing type"


# =============================================================================
# v0.10.0: 29-tool verification
# =============================================================================


@pytest.mark.asyncio
async def test_all_29_tools_registered():
    """Server should have exactly 29 tools registered."""
    from buildlog.mcp.server import mcp

    tools = await mcp.list_tools()
    assert (
        len(tools) == 29
    ), f"Expected 29 tools, got {len(tools)}: {[t.name for t in tools]}"


@pytest.mark.asyncio
async def test_new_tools_registered():
    """The 4 new v0.10.0 tools should be registered."""
    from buildlog.mcp.server import mcp

    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]

    assert "buildlog_gauntlet_rules" in tool_names
    assert "buildlog_overview" in tool_names
    assert "buildlog_entry_new" in tool_names
    assert "buildlog_entry_list" in tool_names
