"""POST /api/session-sync — the browser extension pushes the Instagram sessionid here.

Auth: the MCP key (X-Auth-Key header or Authorization: Bearer).
Body: {"payload": "<Fernet token>"}. The token must be encrypted with the same key as
SESSION_ENCRYPTION_KEY, and its plaintext is JSON: {"sessionid": "...", "username": "..."}.
The sessionid is never echoed back or logged.
"""
import hmac
import json
import os
from typing import Any, Dict, Optional

AUTH_KEY = os.environ.get("MCP_AUTH_KEY", "")


def _header(scope, name: str) -> str:
    for key, value in scope.get("headers", []):
        if key.decode().lower() == name:
            return value.decode()
    return ""


def _authorized(scope) -> bool:
    key = os.environ.get("MCP_AUTH_KEY", "").strip()
    if not key:
        return False
    auth = _header(scope, "authorization")
    if auth.lower().startswith("bearer ") and hmac.compare_digest(auth[7:].strip(), key):
        return True
    return hmac.compare_digest(_header(scope, "x-auth-key").strip(), key)


async def _send_json(send, status: int, payload: Dict[str, Any]) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": json.dumps(payload).encode()})


async def _read_body(receive) -> bytes:
    chunks = []
    while True:
        msg = await receive()
        if msg.get("type") != "http.request":
            break
        chunks.append(msg.get("body", b""))
        if not msg.get("more_body"):
            break
        if sum(len(c) for c in chunks) > 64 * 1024:
            break
    return b"".join(chunks)


def decrypt_payload(token: str, key: Optional[str] = None) -> Dict[str, Any]:
    """Decrypt the extension's Fernet token. Raises ValueError on any problem."""
    from cryptography.fernet import Fernet, InvalidToken
    key = (key if key is not None else os.environ.get("SESSION_ENCRYPTION_KEY", "")).strip()
    if not key:
        raise RuntimeError("SESSION_ENCRYPTION_KEY is not set")
    try:
        plain = Fernet(key.encode()).decrypt(token.encode())
    except (InvalidToken, ValueError, TypeError) as e:
        raise ValueError("payload could not be decrypted with SESSION_ENCRYPTION_KEY") from e
    try:
        data = json.loads(plain.decode("utf-8"))
    except Exception as e:
        raise ValueError("payload is not valid JSON") from e
    if not isinstance(data, dict) or not str(data.get("sessionid", "")).strip():
        raise ValueError("payload has no sessionid")
    return data


async def handle(scope, receive, send) -> None:
    if scope.get("method", "GET").upper() != "POST":
        await _send_json(send, 405, {"error": "use POST"})
        return
    if not _authorized(scope):
        await _send_json(send, 401, {"error": "unauthorized", "hint": "send your MCP key in X-Auth-Key"})
        return
    try:
        body = json.loads((await _read_body(receive)).decode("utf-8") or "{}")
        token = str(body.get("payload", ""))
    except Exception:
        await _send_json(send, 400, {"error": "body must be JSON with a payload field"})
        return
    try:
        data = decrypt_payload(token)
    except RuntimeError as e:
        await _send_json(send, 500, {"error": "server_misconfigured", "hint": str(e)})
        return
    except ValueError as e:
        await _send_json(send, 400, {"error": "bad_payload", "hint": str(e)})
        return

    from admin_ui import handlers
    result = await handlers._instagram("cookie", {
        "sessionid": str(data.get("sessionid", "")),
        "username": str(data.get("username", "")),
    })
    safe = {"status": result.get("status"), "message": result.get("message", ""),
            "username": result.get("username") or data.get("username") or ""}
    await _send_json(send, 200, safe)
