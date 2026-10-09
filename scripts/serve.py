#!/usr/bin/env python3
"""Auth-gated Streamable HTTP server for the Instagram MCP server.

Use this instead of `--transport http` whenever the server can be reached from
other devices (LAN, Cloudflare Tunnel, Tailscale): every request must present
the shared key via `?auth=<key>`, `Authorization: Bearer <key>`, or `X-Auth-Key`.

The key comes from MCP_AUTH_KEY (environment or ./.env — scripts/setup.py writes it).

    python scripts/serve.py                  # 127.0.0.1:8765, key required
    python scripts/serve.py --port 9000
    python scripts/serve.py --no-auth        # loopback only — never tunnel this way

Health check: /healthz (open). Client URL: http://HOST:PORT/mcp?auth=KEY
Image inbox: the same URL with "/mcp" replaced by "/inbox" — the domain is taken from each
incoming request (Host / X-Forwarded-*), so tunnels, port-forwards and reverse proxies all
work with no extra configuration.
"""
import argparse
import hmac
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from instagram_mcp_server.mcp_server import (  # noqa: E402  (also loads ./.env)
    mcp,
    _inbox_dir,
    _inbox_from_base,
    note_request_base,
)


def _header(scope, name: str) -> str:
    for key, value in scope.get("headers", []):
        if key.decode().lower() == name:
            return value.decode()
    return ""


def _origin(scope) -> tuple:
    """Public scheme + host of a request, honouring proxy/tunnel headers.

    A tunnel terminates TLS and forwards plain HTTP with a rewritten Host header
    (plus X-Forwarded-*), so those are the only reliable way to learn the domain
    the user actually connected through.
    """
    scheme = _header(scope, "x-forwarded-proto") or scope.get("scheme") or "http"
    host = _header(scope, "x-forwarded-host") or _header(scope, "host")
    if not host:
        server = scope.get("server") or ()
        host = f"{server[0]}:{server[1]}" if len(server) == 2 and server[0] else ""
    return scheme, host


def _authorized(scope) -> bool:
    """True when the request carries the MCP_AUTH_KEY (query, Bearer, or header)."""
    if os.environ.get("MCP_ALLOW_UNAUTHENTICATED", "") == "1":
        return True
    key = os.environ.get("MCP_AUTH_KEY", "")
    if not key:
        return False
    auth = _header(scope, "authorization")
    if auth.lower().startswith("bearer ") and hmac.compare_digest(auth[7:].strip(), key):
        return True
    if hmac.compare_digest(_header(scope, "x-auth-key"), key):
        return True
    for part in scope.get("query_string", b"").decode("utf-8", "ignore").split("&"):
        if part.startswith("auth=") and hmac.compare_digest(part[5:], key):
            return True
    return False


async def _send_json(send, status: int, body: str) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json")],
    })
    await send({"type": "http.response.body", "body": body.encode()})


async def _send_html(send, status: int, body: str) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"text/html; charset=utf-8")],
    })
    await send({"type": "http.response.body", "body": body.encode()})


async def _read_body(receive, limit: int) -> bytes:
    """Collect an HTTP request body, refusing anything above `limit` bytes."""
    chunks = []
    total = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > limit:
            raise ValueError(f"upload too large (limit {limit // (1024 * 1024)} MB)")
        chunks.append(chunk)
        if not message.get("more_body"):
            return b"".join(chunks)


def _safe_filename(name: str) -> str:
    """Keep a filename local to the inbox: no paths, no traversal, sane extension."""
    import re as _re
    base = os.path.basename(str(name or "").replace("\\", "/")).strip() or "upload.jpg"
    base = _re.sub(r"[^A-Za-z0-9._-]", "_", base)
    if not os.path.splitext(base)[1]:
        base += ".jpg"
    return base[:120]


def _decode_inbox_payload(content_type: str, body: bytes, query: str):
    """Turn a POST body into (image_bytes, filename) — JSON/base64 or raw bytes."""
    import base64
    import json as _json
    import urllib.parse as _parse
    params = _parse.parse_qs(query or "")
    filename = (params.get("name") or [""])[0]
    if "application/json" in (content_type or "").lower():
        try:
            payload = _json.loads(body.decode("utf-8", "replace") or "{}")
        except ValueError as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc
        data = payload.get("data") or payload.get("image") or ""
        filename = payload.get("filename") or filename
        if isinstance(data, str):
            if data.startswith("data:"):
                _header, _, data = data.partition(",")
            try:
                return base64.b64decode("".join(data.split()), validate=False), filename
            except Exception as exc:
                raise ValueError(f"could not decode the base64 image data ({exc})") from exc
        if isinstance(data, list):
            return bytes(data), filename
        raise ValueError("JSON body needs a 'data' field with base64 image data.")
    return body, filename


def _inbox_listing() -> list:
    try:
        files = [p for p in _inbox_dir().rglob("*") if p.is_file()]
    except Exception:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "bytes": p.stat().st_size,
             "modified": int(p.stat().st_mtime)} for p in files[:25]]


_INBOX_PAGE = """<!doctype html>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Instagram MCP inbox</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;padding:24px;background:#111;color:#eee}
 h1{font-size:20px;margin:0 0 4px} p{color:#aaa;margin:4px 0 16px}
 input,button{font-size:16px} button{padding:10px 18px;border:0;border-radius:8px;
 background:#3897f0;color:#fff;font-weight:600} button:disabled{opacity:.5}
 #drop{border:2px dashed #444;border-radius:12px;padding:28px;text-align:center;margin:16px 0}
 #msg{margin-top:12px;white-space:pre-wrap} li{margin:2px 0;color:#bbb}
</style>
<h1>Instagram MCP inbox</h1>
<p>Pick a photo → it lands in <code>%INBOX%</code> on the server → then tell the AI
&ldquo;post the latest image in the inbox&rdquo;.</p>
<div id="drop"><input id="file" type="file" accept="image/*" multiple></div>
<button id="go" disabled>Upload to server</button>
<div id="msg"></div>
<h3>Waiting in the inbox</h3>
<ul id="list">%LIST%</ul>
<script>
const file=document.getElementById('file'),go=document.getElementById('go'),
      msg=document.getElementById('msg');
file.onchange=()=>{go.disabled=!file.files.length;};
go.onclick=async()=>{
  go.disabled=true;
  for (const f of file.files){
    msg.textContent='uploading '+f.name+' …';
    const data=await new Promise(r=>{const fr=new FileReader();fr.onload=()=>r(fr.result);fr.readAsDataURL(f);});
    try{
      const res=await fetch(location.pathname+location.search,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({filename:f.name,data:data})});
      const out=await res.json();
      msg.textContent=(out.saved_path?('saved: '+out.saved_path+'\\n'+out.hint):
                       ('failed: '+JSON.stringify(out)));
    }catch(e){msg.textContent='failed: '+e;}
  }
  setTimeout(()=>location.reload(),1500);
};
</script>
"""


async def _inbox_endpoint(scope, receive, send) -> None:
    """Upload page + API so any device (phone, tablet, laptop) can drop images in the inbox."""
    import json
    import time
    limit = int(os.environ.get("INSTAGRAM_MCP_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    if scope.get("method", "GET").upper() == "GET":
        listing = "".join(f"<li>{item['name']} — {item['bytes']:,} B</li>" for item in _inbox_listing())
        page = (_INBOX_PAGE.replace("%INBOX%", str(_inbox_dir()))
                .replace("%LIST%", listing or "<li>(empty)</li>"))
        await _send_html(send, 200, page)
        return
    try:
        body = await _read_body(receive, limit)
        blob, name = _decode_inbox_payload(
            _header(scope, "content-type"), body, scope.get("query_string", b"").decode("utf-8", "ignore")
        )
        if not blob:
            raise ValueError("the upload was empty")
        base = _safe_filename(name)
        target = _inbox_dir() / base
        if target.exists():
            target = _inbox_dir() / f"{time.strftime('%Y%m%d-%H%M%S')}-{base}"
        target.write_bytes(blob)
        await _send_json(send, 200, json.dumps({
            "status": "ok",
            "saved_path": str(target),
            "bytes": len(blob),
            "hint": ('now tell the AI: "post the latest image in the inbox" '
                     '(or call instagram_post_photo with image_path_or_url="latest")'),
        }))
    except Exception as exc:
        status = 413 if "too large" in str(exc) else 400
        await _send_json(send, status, json.dumps({"error": str(exc)}))


def build_app(inner, allow_no_auth: bool = False):
    """Wrap the FastMCP ASGI app with the key gate (and an open /healthz)."""

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            await inner(scope, receive, send)  # uvicorn manages the lifespan
            return
        if scope["type"] == "http":
            note_request_base(*_origin(scope))
            if scope.get("path", "").startswith("/healthz"):
                await _send_json(send, 200, '{"status":"ok","server":"instagram-mcp"}')
                return
            if not allow_no_auth:
                if not os.environ.get("MCP_AUTH_KEY") and os.environ.get("MCP_ALLOW_UNAUTHENTICATED", "") != "1":
                    await _send_json(
                        send, 500,
                        '{"error":"server_misconfigured","hint":"MCP_AUTH_KEY is missing — run scripts/setup.py"}',
                    )
                    return
                if not _authorized(scope):
                    await _send_json(
                        send, 401,
                        '{"error":"unauthorized","hint":"pass ?auth=<MCP_AUTH_KEY> or Authorization: Bearer <MCP_AUTH_KEY>"}',
                    )
                    return
            if scope.get("path", "").rstrip("/") in ("/inbox", "/upload"):
                await _inbox_endpoint(scope, receive, send)
                return
        await inner(scope, receive, send)

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Auth-gated HTTP server for the Instagram MCP server")
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="bind port (default 8765)")
    parser.add_argument("--path", default="/mcp", help="MCP endpoint path (default /mcp)")
    parser.add_argument("--no-auth", action="store_true",
                        help="disable the key gate — ONLY safe on loopback")
    parser.add_argument("--public-url", default="",
                        help="pin the public MCP/base URL (e.g. https://your-domain/mcp) used in "
                             "image-upload links; without it the URL follows the domain clients use")
    args = parser.parse_args()

    key = os.environ.get("MCP_AUTH_KEY", "")
    if not args.no_auth and not key:
        print("[serve] MCP_AUTH_KEY is not set. Run scripts/setup.py first, or pass --no-auth for loopback use.",
              file=sys.stderr)
        return 1

    import uvicorn

    inner = mcp.http_app(path=args.path)
    app = build_app(inner, allow_no_auth=args.no_auth)

    suffix = "" if args.no_auth else f"?auth={key}"
    public = (args.public_url or os.environ.get("INSTAGRAM_MCP_PUBLIC_URL") or "").strip()
    if public:
        os.environ["INSTAGRAM_MCP_PUBLIC_URL"] = public

    print(f"[serve] MCP endpoint : http://{args.host}:{args.port}{args.path}{suffix}", file=sys.stderr)
    print(f"[serve] local inbox  : http://127.0.0.1:{args.port}/inbox{suffix}   (this PC only)",
          file=sys.stderr)
    print(f"[serve] health check : http://127.0.0.1:{args.port}/healthz"
          f"  (use 127.0.0.1, not 'localhost' — the server listens on IPv4)", file=sys.stderr)
    if public:
        inbox_url = _inbox_from_base(public)
        if suffix and "auth=" not in inbox_url:
            inbox_url += suffix
        print(f"[serve] public inbox : {inbox_url}", file=sys.stderr)
    else:
        print("[serve] public inbox : no config needed — the upload link follows whatever domain a "
              "client connects through\n"
              f"                       (it is <your-domain>/inbox{suffix} — tunnels, port-forwards and "
              "reverse proxies all work).\n"
              "                       Pin it with --public-url https://your-domain if you prefer.",
              file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
