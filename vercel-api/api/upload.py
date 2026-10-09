"""
Vercel Python function: browser upload endpoint for the /upload page.

The page itself (public/upload.html) is served by the MCP ASGI app (api/mcp_server_asgi.py) behind the
MCP_AUTH_KEY gate; this function handles the two JSON calls it makes:

  POST /api/upload {"action":"begin", filename, size, content_type, kind}
      -> returns instructions for uploading the bytes DIRECTLY to Vercel Blob
         (client-side form upload — bypasses the ~4.5 MB serverless body limit)

  POST /api/upload {"action":"commit", filename, pathname, url, size,
                    content_type, kind, aspect, caption}
      -> registers the staged file in the uploads index so the MCP tools
         (list_uploads / preview_upload / post_upload) can see it

Env vars: MCP_AUTH_KEY (same key as the MCP server), BLOB_READ_WRITE_TOKEN.
"""
import json
import os
import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent.parent / "_vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

AUTH_KEY = os.environ.get("MCP_AUTH_KEY", "")
MAX_UPLOAD_BYTES = int(os.environ.get("INSTAGRAM_MCP_MAX_UPLOAD_BYTES", str(256 * 1024 * 1024)))


async def _send_json(send, status: int, payload: dict) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"access-control-allow-origin", b"*"),
            (b"access-control-allow-headers", b"content-type,x-auth-key,authorization"),
            (b"access-control-allow-methods", b"POST, OPTIONS"),
        ],
    })
    await send({"type": "http.response.body", "body": json.dumps(payload).encode()})


def _authorized(scope) -> bool:
    if os.environ.get("MCP_ALLOW_UNAUTHENTICATED", "") == "1":
        return True
    if not AUTH_KEY:
        return False
    for key, value in scope.get("headers", []):
        name = key.decode().lower()
        if name == "x-auth-key" and value.decode() == AUTH_KEY:
            return True
        if name == "authorization" and value.decode().removeprefix("Bearer ").strip() == AUTH_KEY:
            return True
    for part in scope.get("query_string", b"").decode("utf-8", "ignore").split("&"):
        if part.startswith("auth=") and part[5:] == AUTH_KEY:
            return True
    return False


async def _read_body(receive) -> bytes:
    chunks = []
    while True:
        msg = await receive()
        if msg["type"] == "http.request":
            chunks.append(msg.get("body", b""))
            if not msg.get("more_body"):
                break
        elif msg["type"] == "http.disconnect":
            break
    return b"".join(chunks)


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        await send({"type": "lifespan.startup.complete"})
        return
    if scope["type"] != "http":
        return

    method = scope.get("method", "GET")
    if method == "OPTIONS":  # CORS preflight
        await _send_json(send, 204, {})
        return
    if method != "POST":
        await _send_json(send, 405, {"error": "use POST"})
        return
    if not _authorized(scope):
        await _send_json(send, 401, {"error": "unauthorized",
                                     "hint": "pass ?auth=<MCP_AUTH_KEY> or X-Auth-Key header"})
        return

    try:
        body = json.loads((await _read_body(receive)).decode("utf-8") or "{}")
    except Exception:
        await _send_json(send, 400, {"error": "body must be JSON"})
        return

    action = body.get("action", "")
    from instagram_mcp_server import blob_store, upload_store

    if action == "begin":
        filename = str(body.get("filename") or "file")
        size = int(body.get("size") or 0)
        if size > MAX_UPLOAD_BYTES:
            await _send_json(send, 413, {"error": f"file too large ({size} bytes)",
                                         "limit_bytes": MAX_UPLOAD_BYTES})
            return
        if not blob_store.blob_configured():
            await _send_json(send, 500, {
                "error": "blob_not_configured",
                "hint": "Connect Vercel Blob to the project and set BLOB_READ_WRITE_TOKEN",
            })
            return
        key = blob_store.upload_key(blob_store.new_upload_id(), filename)
        token = os.environ.get(blob_store.BLOB_TOKEN_ENV, "")
        try:
            from blob import create_client_upload_url  # type: ignore
            res = create_client_upload_url(key, token=token,
                                           max_size=max(size, 1) + 1024 * 1024,
                                           access="private",
                                           add_random_suffix=False)
            await _send_json(send, 200, {
                "mode": "signed_put",
                "upload_url": getattr(res, "upload_url", None) or getattr(res, "uploadUrl", None),
                "pathname": getattr(res, "pathname", key),
            })
        except ImportError:
            # No Python client-upload helper in this SDK version: fall back to
            # the browser form-upload contract (token goes to Blob only, never
            # to our function — the bytes skip the 4.5 MB serverless limit).
            await _send_json(send, 200, {
                "mode": "form",
                "target": "https://blob.vercel-storage.com/",
                "pathname": key,
                "form_data": {
                    "token": token,
                    "pathname": key,
                    "access": "private",
                    "addRandomSuffix": "false",
                    "contentType": str(body.get("content_type") or "application/octet-stream"),
                },
            })
        except Exception as e:
            await _send_json(send, 500, {"error": f"could not mint Blob upload URL: {e}"})
        return

    if action == "commit":
        pathname = str(body.get("pathname") or "")
        if not pathname.startswith(blob_store.PREFIX + "/uploads/"):
            await _send_json(send, 400, {"error": "pathname does not look like a staged upload"})
            return
        rec = upload_store.add_upload(
            filename=str(body.get("filename") or Path(pathname).name),
            pathname=pathname,
            url=body.get("url"),
            size=int(body.get("size") or 0),
            content_type=str(body.get("content_type") or "application/octet-stream"),
            caption=str(body.get("caption") or ""),
            aspect=str(body.get("aspect") or "auto"),
            kind=str(body.get("kind") or "photo"),
        )
        await _send_json(send, 200, {"ok": True, "id": rec["id"],
                                     "next": "ask the assistant to run list_uploads"})
        return

    await _send_json(send, 400, {"error": "unknown action", "actions": ["begin", "commit"]})
