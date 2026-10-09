#!/usr/bin/env bash
# Start the Instagram Control MCP server over legacy SSE (port 8766).
# Works on Linux, macOS and Termux.
#
#   bash scripts/run_sse.sh
#
# Client URL: http://127.0.0.1:8766/sse
set -e
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
fi

mkdir -p logs
exec "$PY" -m instagram_mcp_server --transport sse --port 8766 >> logs/server.log 2>&1
