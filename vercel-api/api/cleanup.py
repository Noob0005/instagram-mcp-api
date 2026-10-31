"""
Vercel cron function, daily at 04:00 UTC: delete unposted /upload files whose time is up.

An upload is deleted INSTAGRAM_MCP_UNPOSTED_HOURS after it was staged (default 48). Listing uploads
also removes expired ones. Hobby plans run cron once a day, so an unlisted file can live up to about a
day longer. vercel.json schedules GET /api/cleanup.

Vercel sends `Authorization: Bearer <CRON_SECRET>` on cron runs when CRON_SECRET is set. That header is
the only credential accepted here: a key in the URL would end up in logs.
"""
import hmac
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
    accepted = [s for s in (os.environ.get("CRON_SECRET", ""), os.environ.get("MCP_AUTH_KEY", "")) if s]
    header = ""
    for key, value in scope.get("headers", []):
        if key.decode().lower() == "authorization":
            header = value.decode()
    if not header.startswith("Bearer "):
        return False
    token = header[7:].strip()
    return any(hmac.compare_digest(token.encode(), s.encode()) for s in accepted)


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
    try:
        from instagram_mcp_server import upload_store
        result = upload_store.purge_expired()
        await _send_json(send, 200, {"status": "ok", **result})
    except Exception as e:
        await _send_json(send, 500, {"status": "error", "detail": f"{type(e).__name__}: {e}"})
