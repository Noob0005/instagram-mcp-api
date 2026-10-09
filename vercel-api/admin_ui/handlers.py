"""ASGI handlers for the admin dashboard (served at / and /api/admin/*)."""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qs

from . import core
from .page import DASHBOARD_HTML

_VENDOR = Path(__file__).resolve().parent.parent / "_vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

_limiter = core.LoginLimiter()
MAX_BODY = 64 * 1024

SECURITY_HEADERS = [
    (b"cache-control", b"no-store"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
]
CSP = (b"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
       b"connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; "
       b"form-action 'self'")


def resolve(path: str, query: str = ""):
    """Map a request to ('page', '') or ('api', route), or None if it is not ours.

    The page calls /api/main?admin=<route>, which hits this function directly and so does
    not depend on Vercel rewrites. /api/admin/<route> works too (handy for curl and tests).
    """
    qs = parse_qs(query or "")
    if path in ("/", "/admin", "/admin/"):
        return ("page", "")
    if path.startswith("/api/admin/"):
        return ("api", path[len("/api/admin/"):].strip("/"))
    if path.rstrip("/") == "/api/main":
        if qs.get("admin"):
            return ("api", qs["admin"][0].strip("/"))
        if qs.get("route") == ["admin"]:
            return ("page", "")
    return None


def is_admin_path(path: str, query: str = "") -> bool:
    return resolve(path, query) is not None


def _headers(scope) -> Dict[str, str]:
    return {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}


def _client_ip(scope) -> str:
    h = _headers(scope)
    fwd = h.get("x-forwarded-for", "").split(",")[0].strip()
    if fwd:
        return fwd
    client = scope.get("client")
    return client[0] if client else "unknown"


def _cookie_token(scope) -> str:
    for part in _headers(scope).get("cookie", "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == core.COOKIE_NAME:
            return value
    return ""


def _authed(scope) -> bool:
    return core.verify_token(_cookie_token(scope))


async def _send(send, status: int, body: bytes, ctype: bytes, extra=()) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", ctype)] + SECURITY_HEADERS + list(extra)})
    await send({"type": "http.response.body", "body": body})


async def _json(send, status: int, payload: dict, extra=()) -> None:
    await _send(send, status, json.dumps(payload).encode(), b"application/json", extra)


async def _read_json(receive) -> Optional[dict]:
    chunks, total = [], 0
    while True:
        msg = await receive()
        if msg["type"] == "http.disconnect":
            return None
        chunk = msg.get("body", b"")
        total += len(chunk)
        if total > MAX_BODY:
            return None
        chunks.append(chunk)
        if not msg.get("more_body"):
            break
    try:
        data = json.loads(b"".join(chunks).decode() or "{}")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _cookie_header(value: str, max_age: int) -> tuple:
    flags = f"{core.COOKIE_NAME}={value}; Path=/; Max-Age={max_age}; HttpOnly; Secure; SameSite=Strict"
    return (b"set-cookie", flags.encode())


def _mcp_url(scope, reveal: bool) -> str:
    key = os.environ.get("MCP_AUTH_KEY", "").strip()
    base = core.origin_from_headers(_headers(scope)) + "/mcp"
    if not key:
        return base
    return f"{base}?auth={key}" if reveal else f"{base}?auth={'•' * 12}"


async def _instagram(action: str, body: dict) -> dict:
    """Run an Instagram login action using the same client the MCP tools use."""
    try:
        from instagram_mcp_server import mcp_server as srv
    except Exception as e:  # keep the dashboard usable even if the server cannot start
        return {"status": "error",
                "message": f"MCP server module failed to load: {type(e).__name__}: {e}"}

    def run() -> dict:
        ig = srv.ig
        if action == "cookie":
            sid = core.clean_sessionid(str(body.get("sessionid", "")))
            if not sid:
                return {"status": "error", "message": "Paste the sessionid cookie value first."}
            result = ig.login_with_sessionid(str(body.get("username", "")).strip(), sid)
        elif action == "password":
            user, pw = str(body.get("username", "")).strip(), str(body.get("password", ""))
            if not user or not pw:
                return {"status": "error", "message": "Username and password are both required."}
            result = ig.login_with_credentials(user, pw)
        elif action == "2fa":
            result = ig.complete_2fa(str(body.get("code", "")).strip())
        elif action == "challenge":
            result = ig.complete_challenge(str(body.get("code", "")).strip())
        else:  # status
            return {"status": "info", **ig.get_login_status()}
        srv._note_login_result(result)
        return result

    try:
        return await asyncio.to_thread(run)
    except Exception as e:
        return {"status": "error", "message": f"{type(e).__name__}: {e}"}


def _storage_status() -> dict:
    try:
        from instagram_mcp_server import session_store
        return session_store.status()
    except Exception as e:
        return {"backend": "unknown", "error": f"{type(e).__name__}: {e}"}


async def handle(scope, receive, send) -> None:
    path = scope.get("path", "")
    method = scope.get("method", "GET").upper()
    target = resolve(path, scope.get("query_string", b"").decode("utf-8", "ignore"))
    if target is None:
        await _json(send, 404, {"error": "Not found."})
        return
    kind, route = target

    if kind == "page":
        if method != "GET":
            await _json(send, 405, {"error": "use GET"})
            return
        await _send(send, 200, DASHBOARD_HTML.encode(), b"text/html; charset=utf-8",
                    [(b"content-security-policy", CSP)])
        return

    mode = core.admin_mode()

    if route == "info" and method == "GET":
        await _json(send, 200, {"mode": mode, "authenticated": _authed(scope)})
        return

    if route == "login" and method == "POST":
        ip = _client_ip(scope)
        if _limiter.blocked(ip):
            await _json(send, 429, {"error": "Too many failed attempts. Wait 10 minutes."})
            return
        body = await _read_json(receive)
        if body is None:
            await _json(send, 400, {"error": "Body must be JSON."})
            return
        if mode == "none":
            await _json(send, 503, {"error": "Set MCP_AUTH_KEY (or ADMIN_USERNAME + ADMIN_PASSWORD) "
                                              "in Vercel, then redeploy."})
            return
        if not core.verify_login(body):
            _limiter.fail(ip)
            await asyncio.sleep(0.6)
            await _json(send, 401, {"error": "Invalid credentials."})
            return
        _limiter.reset(ip)
        token = core.make_token()
        await _json(send, 200, {"ok": True}, [_cookie_header(token, core.SESSION_SECONDS)])
        return

    if route == "logout" and method == "POST":
        await _json(send, 200, {"ok": True}, [_cookie_header("", 0)])
        return

    # Setup mode: with no auth configured there is nothing to protect yet, so show the
    # checklist (names and set/unset only) to help the first deployment get configured.
    if route == "status" and method == "GET" and mode == "none":
        await _json(send, 200, {"env": core.check_env(), "mode": mode, "setup_only": True})
        return

    if not _authed(scope):
        await _json(send, 401, {"error": "Login required."})
        return

    if route == "status" and method == "GET":
        await _json(send, 200, {
            "env": core.check_env(), "mode": mode,
            "mcp_url_masked": _mcp_url(scope, reveal=False),
            "storage": _storage_status(),
            "origin": core.origin_from_headers(_headers(scope)),
        })
        return

    if route == "reveal" and method == "POST":
        key = os.environ.get("MCP_AUTH_KEY", "").strip()
        await _json(send, 200, {"mcp_url": _mcp_url(scope, reveal=True), "key": key})
        return

    if route == "session" and method == "POST":
        body = await _read_json(receive)
        if body is None:
            await _json(send, 400, {"error": "Body must be JSON."})
            return
        action = str(body.get("action", "status"))
        if action not in ("cookie", "password", "2fa", "challenge", "status"):
            await _json(send, 400, {"error": "Unknown action."})
            return
        await _json(send, 200, await _instagram(action, body))
        return

    await _json(send, 404, {"error": "Not found."})
