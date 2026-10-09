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

Blob layout (all under one prefix):
  sessions/<name>.json          encrypted Instagram session settings
  uploads/<id>_<filename>       the staged media file itself
  uploads/index.json            list of pending uploads (id, caption, kind...)
  uploads/problems.json         rejected files with reasons
"""

import json
import os
import re
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


def session_key(name: str = "default") -> str:
    return f"{PREFIX}/sessions/{safe_filename(name)}.json"


def upload_key(upload_id: str, filename: str) -> str:
    return f"{PREFIX}/uploads/{upload_id}_{safe_filename(filename)}"


def index_key() -> str:
    return f"{PREFIX}/uploads/index.json"


def problems_key() -> str:
    return f"{PREFIX}/uploads/problems.json"


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
    """Download a Blob's contents (never from cache). Accepts a pathname or a full URL."""
    sdk = _sdk()
    try:
        res = sdk.get(pathname_or_url, access=BLOB_ACCESS, token=_token(), use_cache=False)
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

def get_json(pathname: str, default: Any = None) -> Any:
    try:
        raw = get_bytes(pathname)
    except FileNotFoundError:
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
    doc = get_json(pathname, default)
    if doc is None:
        doc = default
    mutated = mutate(doc)
    if mutated is not None:
        doc = mutated
    put_json(pathname, doc)
    return doc
