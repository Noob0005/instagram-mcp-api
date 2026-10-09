"""
Print the saved Instagram session as JSON for INSTAGRAM_MCP_SESSION_JSON.

WARNING: the output is a full account credential (it can log in as you).
Never commit it, never paste it into a chat or screenshot — copy it straight
into your hosting provider's environment variables (e.g. Vercel project
settings), and treat it like a password.

Usage (from the repo root):
    .\.venv\Scripts\python.exe scripts\export_session_json.py
"""

import os
import sys
from pathlib import Path

session_path = os.environ.get("INSTAGRAM_MCP_SESSION_PATH") or os.path.join(
    os.path.expanduser("~"), ".instagram_mcp_session.json"
)

if not os.path.exists(session_path):
    print(f"No session file at {session_path}. Log in first (see README), then retry.", file=sys.stderr)
    sys.exit(1)

data = Path(session_path).read_text(encoding="utf-8").strip()
print(data)
print(f"[exported {len(data)} chars from {session_path}]", file=sys.stderr)
