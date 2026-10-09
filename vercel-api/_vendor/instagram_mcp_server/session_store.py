"""
session_store.py
----------------
Persistent Instagram session storage for serverless deployments.

Why: Vercel instances are stateless — a saved session file disappears on every
cold start / redeploy, so Instagram logins had to be re-seeded through the
INSTAGRAM_MCP_SESSION_JSON environment variable after each deploy (and rotated
sessions were lost entirely).

Design:
  * The session (instagrapi settings JSON) lives in Vercel Blob at
    <prefix>/sessions/<name>.json, encrypted with SESSION_ENCRYPTION_KEY
    (a Fernet key; generate one with scripts/gen_session_key.py or
    `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`).
  * On cold start we READ from Blob. If Blob has nothing yet but the
    INSTAGRAM_MCP_SESSION_JSON env var is set, we use it as a FIRST-TIME SEED
    and immediately write it to Blob. From then on the env var is ignored —
    redeploys no longer clobber a rotated session.
  * Whenever Instagram rotates the session (login, sessionid login, 2FA,
    challenge), save() writes the new settings back to Blob.

Local/disk mode: when Blob is not configured (desktop, Termux) this module is
inert — InstagramClientWrapper keeps using its normal session file.

All network calls go through instagram_mcp_server.blob_store, which is mocked
in the offline test suite.
"""

import json
import os
import sys
import time
from typing import Any, Dict, Optional

from instagram_mcp_server import blob_store

SESSION_NAME = os.environ.get("INSTAGRAM_MCP_SESSION_NAME", "default").strip() or "default"


def _log(msg: str) -> None:
    print(f"[session_store] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------

def _get_fernet():
    """Return a Fernet instance for SESSION_ENCRYPTION_KEY, or None if unset."""
    key = os.environ.get("SESSION_ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        _log(f"SESSION_ENCRYPTION_KEY is not a valid Fernet key: {e}")
        return None


def encrypt_settings(settings_json: str) -> bytes:
    """Encrypt settings JSON; falls back to plaintext only if no key is set."""
    data = settings_json.encode("utf-8")
    f = _get_fernet()
    if f is None:
        _log("WARNING: SESSION_ENCRYPTION_KEY not set — storing the session UNENCRYPTED in Blob")
        return data
    return f.encrypt(data)


def decrypt_settings(blob_bytes: bytes) -> Optional[str]:
    """Decrypt a stored blob. Accepts legacy plaintext too (pre-key uploads)."""
    f = _get_fernet()
    if f is not None:
        try:
            return f.decrypt(blob_bytes).decode("utf-8")
        except Exception:
            pass  # fall through — maybe stored before a key was configured
    try:
        text = blob_bytes.decode("utf-8")
        json.loads(text)  # sanity check it really is the settings JSON
        return text
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Store interface
# ---------------------------------------------------------------------------

def available() -> bool:
    """True when sessions should be persisted to Blob in this deployment."""
    return blob_store.blob_configured()


def key_path() -> str:
    return blob_store.session_key(SESSION_NAME)


def load() -> Optional[Dict[str, Any]]:
    """Read the session settings dict from Blob.

    Falls back to the INSTAGRAM_MCP_SESSION_JSON env var ONLY when Blob holds
    nothing yet (first-time seed); the seed is then written up to Blob so the
    env var never needs updating again.
    Returns None when there is no usable session anywhere.
    """
    if not available():
        return None
    try:
        raw = blob_store.get_bytes(key_path())
        text = decrypt_settings(raw)
        if text:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            _log("Blob session payload is not a JSON object — ignoring")
    except FileNotFoundError:
        pass
    except Exception as e:
        _log(f"reading session from Blob failed: {type(e).__name__}: {e}")

    # First-time seed from the environment variable.
    seed = os.environ.get("INSTAGRAM_MCP_SESSION_JSON", "").strip()
    if seed:
        try:
            data = json.loads(seed)
        except Exception as e:
            _log(f"INSTAGRAM_MCP_SESSION_JSON seed is invalid: {e}")
            return None
        if isinstance(data, dict):
            try:
                save(data)
                _log("seeded session from INSTAGRAM_MCP_SESSION_JSON into Blob "
                     "(env var is now just a seed — redeploys keep the Blob copy)")
            except Exception as e:
                _log(f"seeding Blob session failed: {type(e).__name__}: {e}")
            return data
    return None


def save(settings: Dict[str, Any]) -> bool:
    """Write session settings to Blob (encrypted). Best-effort: logs failures."""
    if not available():
        return False
    try:
        payload = encrypt_settings(json.dumps(settings))
        blob_store.put_bytes(key_path(), payload, content_type="application/octet-stream")
        return True
    except Exception as e:
        _log(f"saving session to Blob failed: {type(e).__name__}: {e}")
        return False


def status() -> Dict[str, Any]:
    """Small diagnostic dict used by tools/tests (never includes secrets)."""
    out: Dict[str, Any] = {
        "backend": "blob" if available() else "local-file",
        "session_name": SESSION_NAME,
        "key_path": key_path() if available() else None,
        "encryption": bool(os.environ.get("SESSION_ENCRYPTION_KEY")),
    }
    if available():
        try:
            out["exists"] = blob_store.exists(key_path())
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"
    return out
