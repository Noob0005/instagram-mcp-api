"""
Vercel Python entrypoint.

Vercel's new Python runtime only auto-detects an ASGI entrypoint when it lives
in a default location (api/main.py, app.py, ...) with a variable named `app`.
The actual servers are implemented as raw ASGI apps in the sibling modules, so
this file dispatches to the right one based on the request path:

    /api/upload   -> api.upload:app   (media upload pipeline)
    /api/cleanup  -> api.cleanup:app  (daily cron: expire sessions/blobs)
    everything else (/api/main, /mcp, /healthz, /upload page) -> mcp_server_asgi:app

`vercel.json` rewrites /mcp and /healthz into this function; the MCP app is
path-agnostic (it normalises scope["path"] itself), so forwarding works
unchanged.  All sub-apps handle the ASGI "lifespan" scope type, so Vercel's
lifespan startup completes correctly through here.

NOTE: this module must NOT be named api/mcp.py — that shadows the installed
`mcp` package that FastMCP imports.
"""
import sys
from pathlib import Path

# Ensure sibling modules import cleanly regardless of how Vercel loads us.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cleanup  # noqa: E402
import mcp_server_asgi  # noqa: E402
import upload  # noqa: E402


async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope.get("path", "") or ""
        if path.startswith("/api/upload"):
            await upload.app(scope, receive, send)
            return
        if path.startswith("/api/cleanup"):
            await cleanup.app(scope, receive, send)
            return
    await mcp_server_asgi.app(scope, receive, send)
