"""
Vercel Python function: browser upload endpoint for the /upload page.

The page itself (public/upload.html) is served by the MCP ASGI app (api/mcp_server_asgi.py) behind the
MCP_AUTH_KEY gate; this function handles the two JSON calls it makes:

  POST /api/upload {"action":"begin", filename, size, content_type, kind}
      -> returns a safe Blob pathname; the page then uploads DIRECTLY to Vercel Blob with a
         short-lived token from /api/blob-token (bypasses the ~4.5 MB serverless body limit)

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


async def _serve_media(scope, send) -> None:
    """GET /api/upload?thumb=<id> or ?file=<id>.

    Allowed with the key (X-Auth-Key header or ?auth=), or with a signed view link from
    preview_upload (?exp=...&sig=...). A signed link opens only the one file it names, only until
    it expires, and only while the upload is still staged. The server key never appears in one.
    """
    from urllib.parse import parse_qs
    from instagram_mcp_server import blob_store, media_links, upload_store
    query = parse_qs(scope.get("query_string", b"").decode("utf-8", "ignore"))
    if "thumb" in query:
        which, upload_id = "thumb", (query["thumb"][0] if query["thumb"] else "")
    elif "file" in query:
        which, upload_id = "file", (query["file"][0] if query["file"] else "")
    else:
        which, upload_id = "", ""
    signed = media_links.link_is_valid(which, upload_id,
                                       (query.get("exp") or [""])[0], (query.get("sig") or [""])[0])
    if not signed and not _authorized(scope):
        await _send_json(send, 401, {"error": "unauthorized"})
        return
    if not which:
        await _send_json(send, 400, {"error": "pass ?thumb=<id> or ?file=<id>"})
        return
    rec = upload_store.get_upload(upload_id) if upload_id else None
    if not rec:
        await _send_json(send, 404, {"error": "not found"})
        return
    if which == "thumb":
        data = upload_store.fetch_thumb(rec)
        if not data:
            await _send_json(send, 404, {"error": "no preview for this upload"})
            return
        content_type = "image/jpeg"
    else:
        if int(rec.get("size") or 0) > media_links.MAX_VIEW_BYTES:
            await _send_json(send, 413, {"error": "too_big_to_view",
                                         "hint": "This file is too big to open in the browser. Its preview is shown instead."})
            return
        try:
            data = blob_store.get_bytes(rec["pathname"])
        except Exception as exc:
            await _send_json(send, 502, {"error": f"could not read the file: {exc}"})
            return
        content_type = rec.get("content_type") or "application/octet-stream"
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", content_type.encode()),
                            (b"cache-control", b"private, max-age=300"),
                            (b"x-content-type-options", b"nosniff")]})
    await send({"type": "http.response.body", "body": data})


async def app(scope, receive, send):
    """Never leaks a bare 500: any unexpected error becomes JSON that names the problem and is logged."""
    try:
        await _app(scope, receive, send)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        if scope.get("type") == "http":
            await _send_json(send, 500, {
                "error": "server_error",
                "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
                "hint": "Check the Vercel function logs for this request.",
            })


async def _app(scope, receive, send):
    if scope["type"] == "lifespan":
        await send({"type": "lifespan.startup.complete"})
        return
    if scope["type"] != "http":
        return

    method = scope.get("method", "GET")
    if method == "OPTIONS":  # CORS preflight
        await _send_json(send, 204, {})
        return
    if method == "GET":
        await _serve_media(scope, send)
        return
    if method != "POST":
        await _send_json(send, 405, {"error": "use POST or GET"})
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

    if action == "list":
        items = []
        for u in upload_store.list_uploads(status="pending"):
            items.append({
                "id": u.get("id"), "filename": u.get("filename") or "", "title": u.get("title") or "",
                "kind": u.get("kind") or "photo", "size": int(u.get("size") or 0),
                "content_type": u.get("content_type") or "", "caption": u.get("caption") or "",
                "uploaded_at": float(u.get("uploaded_at") or 0),
                "has_thumb": bool(u.get("thumb_pathname")),
            })
        items.sort(key=lambda x: x["uploaded_at"], reverse=True)
        await _send_json(send, 200, {"ok": True, "uploads": items})
        return

    if action == "rename":
        upload_id = str(body.get("id") or "")
        if not upload_id:
            await _send_json(send, 400, {"ok": False, "error": "id is required"})
            return
        if not upload_store.set_title(upload_id, str(body.get("title") or "")):
            await _send_json(send, 404, {"ok": False, "error": "that upload no longer exists"})
            return
        await _send_json(send, 200, {"ok": True})
        return

    if action == "delete":
        upload_id = str(body.get("id") or "")
        rec = upload_store.get_upload(upload_id) if upload_id else None
        if not rec:
            await _send_json(send, 404, {"ok": False, "error": "that upload no longer exists"})
            return
        try:
            upload_store.delete_blob_file(rec)
        except Exception as exc:
            await _send_json(send, 500, {"ok": False, "error": f"could not delete the file: {exc}"})
            return
        upload_store.remove_upload(upload_id)
        await _send_json(send, 200, {"ok": True})
        return

    if action == "delete_many":
        ids = [str(i) for i in (body.get("ids") or []) if str(i).strip()]
        if not ids:
            await _send_json(send, 400, {"ok": False, "error": "pick at least one file"})
            return
        if len(ids) > 200:
            await _send_json(send, 400, {"ok": False, "error": "delete at most 200 files at a time"})
            return
        result = upload_store.delete_uploads(ids)
        await _send_json(send, 200, {"ok": True, **result})
        return

    if action == "storage":
        try:
            usage = upload_store.storage_usage()
        except Exception as exc:
            await _send_json(send, 500, {"ok": False, "error": f"could not check storage: {exc}"})
            return
        await _send_json(send, 200, {"ok": True, **usage})
        return

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
        # The browser uploads with a short-lived, single-file token minted by /api/blob-token
        # (a Node function using @vercel/blob). The long-lived BLOB_READ_WRITE_TOKEN never
        # leaves the server.
        await _send_json(send, 200, {
            "mode": "client_token",
            "pathname": key,
            "handle_upload_url": "/api/blob-token",
            "access": blob_store.BLOB_ACCESS,
        })
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
            thumb_pathname=(lambda t: t if t.startswith(blob_store.PREFIX + "/uploads/") else None)(
                str(body.get("thumb_pathname") or "")),
            kind=str(body.get("kind") or "photo"),
        )
        await _send_json(send, 200, {"ok": True, "id": rec["id"],
                                     "next": "ask the assistant to run list_uploads"})
        return

    await _send_json(send, 400, {"error": "unknown action",
                                 "actions": ["begin", "commit", "list", "rename", "delete",
                                             "delete_many", "storage"]})
