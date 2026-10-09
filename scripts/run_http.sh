#!/usr/bin/env bash
# Start the Instagram Control MCP server over Streamable HTTP (port 8765).
# Works on Linux, macOS and Termux.
#
#   bash scripts/run_http.sh          # foreground (Ctrl+C to stop)
#   nohup bash scripts/run_http.sh &  # background
#
# Client URL: http://127.0.0.1:8765/mcp
set -e
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
fi

mkdir -p logs
exec "$PY" -m instagram_mcp_server --transport http --port 8765 >> logs/server.log 2>&1
