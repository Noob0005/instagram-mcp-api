#!/usr/bin/env bash
# Instagram MCP server - setup / start (Linux, macOS, Termux)
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

set +e
.venv/bin/python scripts/setup.py "$@"
rc=$?

# keep the window open when launched from a file manager (no terminal attached)
if [ ! -t 0 ]; then
  echo
  read -r -p "Press Enter to close..." _
fi
exit $rc
