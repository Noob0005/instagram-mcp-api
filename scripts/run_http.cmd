@echo off
REM Start the Instagram Control MCP server over Streamable HTTP (port 8765).
REM Adjust the repo path below if it lives elsewhere.
cd /d d:\instagram-mcp-master
if not exist logs mkdir logs
.venv\Scripts\python.exe -m instagram_mcp_server --transport http --port 8765 >> logs\server.log 2>&1
