"""
Vercel cron function (daily): purge unposted /upload staging files older than 7 days.

vercel.json maps GET /api/cleanup to the cron schedule. The cron request is
authenticated with CRON_SECRET (Authorization: Bearer <CRON_SECRET>) — Vercel
sends it automatically when the secret is configured in project settings.
MCP_AUTH_KEY is also accepted for manual runs (?auth=...).

Env vars: BLOB_READ_WRITE_TOKEN (required), INSTAGRAM_MCP_UPLOAD_TTL_DAYS (default 7),
          CRON_SECRET or MCP_AUTH_KEY.
"""
import json
import os
import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent.parent / "_vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))


async def _send_json(send, status: int, payload: dict) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json")],
    })
    await send({"type": "http.response.body", "body": json.dumps(payload).encode()})


def _authorized(scope) -> bool:
    secrets = [os.environ.get("CRON_SECRET", ""), os.environ.get("MCP_AUTH_KEY", "")]
    secrets = [s for s in secrets if s]
    header = ""
    for key, value in scope.get("headers", []):
        if key.decode().lower() == "authorization":
            header = value.decode()
    if header.startswith("Bearer ") and header[7:].strip() in secrets:
        return True
    for part in scope.get("query_string", b"").decode("utf-8", "ignore").split("&"):
        if part.startswith("auth=") and part[5:] in secrets:
            return True
    # Vercel cron without explicit auth header still needs a secret; fail closed.
    return False


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        await send({"type": "lifespan.startup.complete"})
        return
    if scope["type"] != "http":
        return
    if not _authorized(scope):
        await _send_json(send, 401, {"error": "unauthorized",
                                     "hint": "set CRON_SECRET and let Vercel send Authorization: Bearer"})
        return

    days = int(os.environ.get("INSTAGRAM_MCP_UPLOAD_TTL_DAYS", "7"))
    try:
        from instagram_mcp_server import upload_store
        result = upload_store.purge_expired(days=days)
        await _send_json(send, 200, {"status": "ok", **result})
    except Exception as e:
        await _send_json(send, 500, {"status": "error", "detail": f"{type(e).__name__}: {e}"})
