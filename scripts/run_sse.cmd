@echo off
REM Start the Instagram Control MCP server over legacy SSE (port 8766).
REM Adjust the repo path below if it lives elsewhere.
cd /d d:\instagram-mcp-master
if not exist logs mkdir logs
.venv\Scripts\python.exe -m instagram_mcp_server --transport sse --port 8766 >> logs\server.log 2>&1
