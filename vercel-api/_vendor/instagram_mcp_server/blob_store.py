"""
blob_store.py
-------------
Vercel Blob storage helpers for the Instagram MCP server.

Everything here is lazy-imported and safe to use off-Vercel: when
BLOB_READ_WRITE_TOKEN is not configured every function raises RuntimeError
with a clear message, and `blob_configured()` returns False so callers can
fall back to local-disk behaviour (desktop / Termux deployments).

Used for:
  * session persistence  (Instagram settings JSON survives cold starts and
    redeploys; the INSTAGRAM_MCP_SESSION_JSON env var is only a first-time seed)
  * the /upload staging area (browser uploads files straight to Blob, which
    skips Vercel's ~4.5 MB serverless body limit)
  * the upload index + problem log (small JSON files in the same container)

The store is PUBLIC: anyone who learns a file's address can read it. So nothing is named after
what it holds. Photos get random names (uploads/<token>.<ext>); the session, index and problem log
get names only this server can derive from a secret (see _hidden_name).
  <prefix>/<hash>.json          encrypted Instagram session settings
  <prefix>/uploads/<token>.ext  a staged photo or reel (random name; the file name lives in the index)
  <prefix>/<hash>.json          upload index (pending uploads, captions, kind...)
  <prefix>/<hash>.json          rejected files with reasons
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BLOB_TOKEN_ENV = "BLOB_READ_WRITE_TOKEN"
PREFIX = os.environ.get("INSTAGRAM_MCP_BLOB_PREFIX", "").strip().strip("/") or "instagram-mcp"


def blob_configured() -> bool:
    """True when Vercel Blob credentials are present in the environment."""
    return bool(os.environ.get(BLOB_TOKEN_ENV, "").strip())


# Must match the Blob store's type. A PRIVATE store (recommended) never exposes files by URL.
BLOB_ACCESS = (os.environ.get("INSTAGRAM_MCP_BLOB_ACCESS", "private").strip().lower() or "private")


def _sdk():
    """Return the official `vercel.blob` module (package `vercel`)."""
    if not blob_configured():
        raise RuntimeError(
            "Vercel Blob is not configured: set BLOB_READ_WRITE_TOKEN in the "
            "project's environment variables (Vercel: Storage → Blob → Connect)."
        )
    try:
        from vercel import blob as vercel_blob
    except ImportError as e:  # pragma: no cover - dependency missing
        raise RuntimeError("The 'vercel' package is required for Blob support: pip install vercel") from e
    return vercel_blob


def _token() -> str:
    return os.environ[BLOB_TOKEN_ENV].strip()


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

_SAFE_RE = re.compile(r"[^A-Za-z0-9._@-]+")


def safe_filename(name: str, max_len: int = 60) -> str:
    """Reduce an arbitrary filename to something safe for a Blob key."""
    name = os.path.basename(name or "file")
    stem, dot, ext = name.partition(".")
    stem = _SAFE_RE.sub("_", stem)[:max_len] or "file"
    ext = _SAFE_RE.sub("", ext).lower()[:12]
    return f"{stem}.{ext}" if ext else stem


def _store_secret() -> Optional[str]:
    """The secret that names the store's private files: INSTAGRAM_MCP_STORE_SECRET, else MCP_AUTH_KEY.

    Keep it stable. A different secret gives different names, so the index and session would look missing."""
    return (os.environ.get("INSTAGRAM_MCP_STORE_SECRET") or os.environ.get("MCP_AUTH_KEY") or "").strip() or None


def _hidden_name(label: str) -> str:
    """A name only this server can work out. Anyone who can read a public file's address can read the file,
    so the names of files that are not photos must not be guessable."""
    secret = _store_secret()
    if not secret:
        if blob_configured():
            raise RuntimeError("Set INSTAGRAM_MCP_STORE_SECRET (or MCP_AUTH_KEY): it gives the Blob store's "
                               "private files unguessable names.")
        return label  # desktop/local mode: nothing is public, so a plain name is fine
    return hmac.new(secret.encode("utf-8"), label.encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def session_key(name: str = "default") -> str:
    return f"{PREFIX}/{_hidden_name('session:' + safe_filename(name))}.json"


def upload_key(upload_id: str, filename: str) -> str:
    """Where a staged photo is stored: a random name keeping only the extension. The file name lives in
    the index. upload_id is accepted for callers but is not part of the name."""
    name = safe_filename(filename)
    ext = name.rsplit(".", 1)[1] if "." in name else ""
    token = secrets.token_urlsafe(18)  # 24 characters, unguessable
    return f"{PREFIX}/uploads/{token}.{ext}" if ext else f"{PREFIX}/uploads/{token}"


def index_key() -> str:
    return f"{PREFIX}/{_hidden_name('index')}.json"


def problems_key() -> str:
    return f"{PREFIX}/{_hidden_name('problems')}.json"


def new_upload_id() -> str:
    return f"{int(time.time() * 1000):x}{os.urandom(3).hex()}"


# ---------------------------------------------------------------------------
# Low-level operations (sync — the SDK is synchronous)
# ---------------------------------------------------------------------------

def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream",
              access: Optional[str] = None) -> Dict[str, Any]:
    """Store bytes under `key`, replacing any existing object. Returns {url, pathname, size}."""
    res = _sdk().put(key, data, access=access or BLOB_ACCESS, content_type=content_type,
                     add_random_suffix=False, overwrite=True, token=_token())
    return {"url": res.url, "pathname": res.pathname, "size": len(data)}


def get_bytes(pathname_or_url: str) -> bytes:
    """Download a Blob's contents. Accepts a pathname or a full URL.

    use_cache=True means no `?cache=0` query is added: this store answers that query with
    400 Bad Request, so every read of an existing file failed and the library stayed empty."""
    sdk = _sdk()
    try:
        res = sdk.get(pathname_or_url, access=BLOB_ACCESS, token=_token(), use_cache=True)
    except sdk.BlobNotFoundError as e:
        raise FileNotFoundError(f"Blob object not found: {pathname_or_url}") from e
    if res is None or getattr(res, "status_code", 200) == 404 or res.content is None:
        raise FileNotFoundError(f"Blob object not found: {pathname_or_url}")
    return bytes(res.content)


def delete(pathname_or_url: str) -> None:
    """Delete one Blob object (or several, if given a list) by pathname or URL."""
    _sdk().delete(pathname_or_url, token=_token())


def exists(pathname: str) -> bool:
    """True when an object exists at exactly this pathname."""
    try:
        return any(item["pathname"] == pathname for item in list_prefix(pathname))
    except Exception:
        return False


def listing_blobs(result) -> List[Any]:
    return getattr(result, "blobs", None) or []


def list_prefix(prefix: str) -> List[Dict[str, Any]]:
    """List objects under a key prefix (paginated, capped at 1000)."""
    sdk = _sdk()
    out: List[Any] = []
    cursor: Optional[str] = None
    for _ in range(10):  # hard page cap
        res = sdk.list_objects(prefix=prefix, limit=100, cursor=cursor, token=_token())
        out.extend(listing_blobs(res))
        cursor = res.cursor if getattr(res, "has_more", False) else None
        if not cursor or len(out) >= 1000:
            break
    return [{"pathname": b.pathname, "url": b.url, "size": b.size, "uploaded_at": b.uploaded_at}
            for b in out]


# ---------------------------------------------------------------------------
# JSON documents (index / problem log) with read-modify-write helpers
# ---------------------------------------------------------------------------

def _missing_answer(exc: Exception) -> bool:
    """This store answers a missing file with 400 rather than 404, so either code can mean 'not there'."""
    code = getattr(getattr(exc, "response", None), "status_code", None)
    text = str(exc)
    return code in (400, 404) or "400 Bad Request" in text or "404 Not Found" in text


def _really_missing(pathname: str) -> bool:
    """A listing decides whether the file exists. If the listing itself fails, assume it exists."""
    try:
        return not any(item.get("pathname") == pathname for item in list_prefix(pathname))
    except Exception:
        return False


def get_json(pathname: str, default: Any = None, strict: bool = False) -> Any:
    """Read a JSON document. Read-only callers get `default` on any failure (logged);
    read-modify-write callers pass strict=True so a read error is never written back as empty."""
    try:
        raw = get_bytes(pathname)
    except FileNotFoundError:
        return default
    except Exception as e:
        if _missing_answer(e) and _really_missing(pathname):
            return default  # a file that does not exist yet (first upload, no settings saved)
        if strict:
            raise
        print(f"[blob_store] could not read {pathname}: {type(e).__name__}: {e}")
        return default
    if not raw.strip():
        return default
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return default


def put_json(pathname: str, value: Any) -> Dict[str, Any]:
    data = json.dumps(value, indent=0, sort_keys=False).encode("utf-8")
    return put_bytes(pathname, data, content_type="application/json")


def update_json(pathname: str, mutate, default: Any) -> Any:
    """Read a JSON doc, apply `mutate(doc)` and write it back. Returns the new doc."""
    doc = get_json(pathname, default, strict=True)
    if doc is None:
        doc = default
    mutated = mutate(doc)
    if mutated is not None:
        doc = mutated
    put_json(pathname, doc)
    return doc
