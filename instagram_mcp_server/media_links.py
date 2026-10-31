"""
media_links.py
--------------
Signed, expiring links that let a browser see one staged upload.

preview_upload returns one of these, so an assistant that cannot display images (or a
browser-based one, such as Gemini in task mode) can still open the picture.

A link carries an HMAC made with a key derived from MCP_AUTH_KEY. The key itself never
appears in the link. A link opens exactly one file (the photo, or its stored preview), only
until it expires, and only while the upload is still staged. Whoever holds the link can see
that one file until then, so share links only with services you trust.

Link shape:  <origin>/api/upload?file=<id>&exp=<unix seconds>&sig=<hex>
             (thumb=<id> instead of file=<id> for the stored preview)
"""

import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

DEFAULT_HOURS = 24
MAX_HOURS = 168  # one week
# A function response is limited to about 4.5 MB on Vercel, so bigger files cannot be viewed.
MAX_VIEW_BYTES = 4 * 1024 * 1024
_LABEL = b"instagram-mcp media link v1"
_KINDS = ("file", "thumb")


class LinkError(RuntimeError):
    """A link cannot be made because the server has no key to sign with."""


def hours() -> float:
    """How long a new link lasts: INSTAGRAM_MCP_VIEW_LINK_HOURS, kept between 0.1 and one week."""
    try:
        value = float(os.environ.get("INSTAGRAM_MCP_VIEW_LINK_HOURS", DEFAULT_HOURS))
    except ValueError:
        value = DEFAULT_HOURS
    return min(max(value, 0.1), MAX_HOURS)


def _signing_key() -> bytes:
    key = (os.environ.get("MCP_AUTH_KEY") or "").strip()
    if not key:
        raise LinkError("MCP_AUTH_KEY is not set, so view links cannot be signed")
    # Derived, so a signature never reveals the server key.
    return hmac.new(key.encode("utf-8"), _LABEL, hashlib.sha256).digest()


def _signature(kind: str, upload_id: str, exp: int) -> str:
    message = f"{kind}:{upload_id}:{exp}".encode("utf-8")
    return hmac.new(_signing_key(), message, hashlib.sha256).hexdigest()


def make_link(kind: str, upload_id: str, origin: str, now: float = None) -> str:
    """A link to the photo ('file') or its stored preview ('thumb') of one upload."""
    if kind not in _KINDS:
        raise ValueError(f"kind must be 'file' or 'thumb', not {kind!r}")
    exp = int((time.time() if now is None else now) + hours() * 3600)
    query = urlencode({kind: upload_id, "exp": exp, "sig": _signature(kind, upload_id, exp)})
    return f"{origin.rstrip('/')}/api/upload?{query}"


def link_is_valid(kind: str, upload_id: str, exp: str, sig: str) -> bool:
    """True when the signature matches this kind and id, and the link has not expired."""
    if kind not in _KINDS or not upload_id or not exp or not sig:
        return False
    try:
        expiry = int(exp)
        if expiry < time.time():
            return False
        expected = _signature(kind, upload_id, expiry)
    except (ValueError, LinkError):
        return False
    return hmac.compare_digest(expected.encode("ascii"), sig.encode("utf-8", "ignore"))
