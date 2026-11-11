"""Scaffold test: the MCP server builds with the right name."""
from mcp_server.server import create_server


def test_server_name():
    server = create_server()
    assert server.name == "resume-tailor"
