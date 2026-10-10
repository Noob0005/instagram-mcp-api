"""
Vercel Python function: Instagram Control MCP server over Streamable HTTP.

Endpoint:  https://<project>.vercel.app/mcp?auth=<MCP_AUTH_KEY>
Auth:      ?auth= query param, or `Authorization: Bearer <MCP_AUTH_KEY>`,
           or the `X-Auth-Key` header. /healthz is open (no tool access).

Env vars:  MCP_AUTH_KEY               required — long random string protecting all tools
           INSTAGRAM_MCP_SESSION_JSON saved session JSON (see vercel-api/README.md)
           INSTAGRAM_MCP_*            any normal tuning variables

Vercel instances are stateless and have no persistent disk / ASGI lifespan, so
this app runs FastMCP in `stateless_http=True` mode and starts FastMCP's
lifespan lazily on the first request.
"""
import contextlib
import hmac
import os
import sys
from pathlib import Path

# Make the vendored package importable (run sync_package.ps1 after package edits)
_VENDOR = Path(__file__).resolve().parent.parent / "_vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from instagram_mcp_server.mcp_server import mcp  # noqa: E402

UPLOAD_PAGE_PATH = str(Path(__file__).resolve().parent.parent / "public" / "upload.html")

MCP_PATH = "/api/main"  # path of this function on Vercel (vercel.json maps /mcp here)
AUTH_KEY = os.environ.get("MCP_AUTH_KEY", "")
ALLOW_UNAUTHENTICATED = os.environ.get("MCP_ALLOW_UNAUTHENTICATED", "") == "1"

mcp_app = mcp.http_app(path=MCP_PATH, stateless_http=True)

_lifespan_stack = None
_lifespan_error = None


async def _ensure_lifespan() -> None:
    """Start FastMCP's lifespan once per instance (Vercel runs no lifespan events)."""
    global _lifespan_stack, _lifespan_error
    if _lifespan_stack is not None or _lifespan_error:
        return
    try:
        stack = contextlib.AsyncExitStack()
        await stack.enter_async_context(mcp_app.lifespan(mcp_app))
        _lifespan_stack = stack
    except Exception as e:  # surfaced to the caller as a 500 for easy debugging
        _lifespan_error = f"{type(e).__name__}: {e}"


def _header(scope, name: str) -> str:
    for key, value in scope.get("headers", []):
        if key.decode().lower() == name:
            return value.decode()
    return ""


def _authorized(scope) -> bool:
    if ALLOW_UNAUTHENTICATED:
        return True
    if not AUTH_KEY:
        return False
    auth = _header(scope, "authorization")
    if auth.lower().startswith("bearer ") and hmac.compare_digest(auth[7:].strip(), AUTH_KEY):
        return True
    if hmac.compare_digest(_header(scope, "x-auth-key"), AUTH_KEY):
        return True
    for part in scope.get("query_string", b"").decode("utf-8", "ignore").split("&"):
        if part.startswith("auth=") and hmac.compare_digest(part[5:], AUTH_KEY):
            return True
    return False


async def _send_json(send, status: int, body: str, extra_headers=()) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json")] + list(extra_headers),
    })
    await send({"type": "http.response.body", "body": body.encode()})


async def app(scope, receive, send):
    """ASGI entry point (used by Vercel and by any ASGI server such as uvicorn)."""
    if scope["type"] == "lifespan":
        # A real ASGI server manages the lifespan — let FastMCP handle it normally.
        await mcp_app(scope, receive, send)
        return

    if scope["type"] == "http":
        path = scope.get("path", "")
        if path in ("/healthz", "/api/healthz"):
            await _send_json(send, 200, '{"status":"ok","server":"instagram-mcp","stateless":true}')
            return
        if path in ("/upload", "/upload/"):
            # Browser upload page — protected by the SAME MCP_AUTH_KEY gate.
            if not AUTH_KEY or not _authorized(scope):
                await _send_json(
                    send, 401,
                    '{"error":"unauthorized","hint":"open /upload?auth=<MCP_AUTH_KEY>"}',
                    extra_headers=[(b"www-authenticate", b"Bearer")],
                )
                return
            try:
                with open(UPLOAD_PAGE_PATH, "rb") as fh:
                    page = fh.read()
            except OSError:
                await _send_json(send, 500, '{"error":"upload_page_missing"}')
                return
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/html; charset=utf-8")],
            })
            await send({"type": "http.response.body", "body": page})
            return
        if path in ("/mcp", "/mcp/", "/api/main", "/api/main/"):
            # vercel.json rewrites /mcp here; normalise for direct calls too.
            scope = dict(scope)
            scope["path"] = MCP_PATH
            scope["raw_path"] = MCP_PATH.encode()
        if not AUTH_KEY and not ALLOW_UNAUTHENTICATED:
            await _send_json(send, 500, '{"error":"server_misconfigured","hint":"MCP_AUTH_KEY is not set"}')
            return
        if not _authorized(scope):
            await _send_json(
                send, 401,
                '{"error":"unauthorized","hint":"pass ?auth=<MCP_AUTH_KEY> or Authorization: Bearer <MCP_AUTH_KEY>"}',
                extra_headers=[(b"www-authenticate", b"Bearer")],
            )
            return
        if _lifespan_stack is None:
            await _ensure_lifespan()
            if _lifespan_error:
                detail = _lifespan_error.replace('"', "'")
                await _send_json(send, 500, '{"error":"lifespan_init_failed","detail":"%s"}' % detail)
                return

    await mcp_app(scope, receive, send)
