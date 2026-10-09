"""Local entry point for the Instagram Control MCP server.

The real implementation lives in instagram_mcp_server/mcp_server.py (the
installed package). This shim keeps `python mcp_server.py` working from a repo
checkout while avoiding a second, drifting copy of the code.
"""

from instagram_mcp_server.mcp_server import mcp

if __name__ == "__main__":
    mcp.run()
