"""Pull a photo or reel from a web link into staged uploads, without its bytes passing through chat.

The server downloads the file itself and stores it in Blob, then registers it like a file from the
Upload page. The assistant gets the new upload id plus a small preview image, so it can see what the
file shows and write a caption.

If the file cannot be saved (the host refuses the server, the file is too big, or the link is a web
page), the preview alone is returned: the page's own image, or a thumbnail the caller passes in. In
that case nothing is stored.

Safety: only http(s) links; every host, and every redirect hop, must resolve to public addresses.
This is a best-effort check, so DNS rebinding is not fully ruled out.
"""

from __future__ import annotations

import html as html_lib
import ipaddress
import os
import re
import socket
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

from instagram_mcp_server import blob_store, media_validation, upload_store

MAX_URL_BYTES = int(os.environ.get("INSTAGRAM_MCP_URL_UPLOAD_MAX_BYTES", str(100 * 1024 * 1024)))
MAX_PAGE_BYTES = 2 * 1024 * 1024       # HTML pages are only scanned for og:image
MAX_PREVIEW_BYTES = 10 * 1024 * 1024   # a preview image larger than this is not worth fetching
TOTAL_SECONDS = 45                     # the whole call, inside the function's time limit
MAX_REDIRECTS = 3
PREVIEW_SIDE = 512
USER_AGENT = "Mozilla/5.0 (compatible; InstagramMCP/1.0; upload-from-url)"

KINDS = ("auto", "photo", "reel")
ASPECTS = ("auto", "square", "portrait", "landscape", "keep")
_EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "video/mp4": ".mp4", "video/quicktime": ".mov",
}


class UrlUploadError(Exception):
    """A plain-language reason the link cannot be used."""


def _resolve(host: str):
    """Every address the host name resolves to. A hook, so tests need no network."""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def check_url(raw: str) -> str:
    """Return the link if it is a public http(s) address; raise UrlUploadError otherwise."""
    url = (raw or "").strip()
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UrlUploadError("Give a full web link that starts with https://")
    try:
        addresses = _resolve(parts.hostname)
    except OSError:
        raise UrlUploadError(f"Could not find the host {parts.hostname}.")
    for addr in addresses:
        try:
            public = ipaddress.ip_address(addr).is_global
        except ValueError:
            public = False
        if not public:
            raise UrlUploadError("That link points to a private or local address, which is not allowed.")
    return url


def _get(url: str, deadline: float, max_bytes: int) -> Tuple[bytes, str, str]:
    """Download one link, checking every redirect hop. Returns (bytes, content type, final url)."""
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        current = check_url(current)
        try:
            resp = requests.get(current, stream=True, timeout=(10, 20), allow_redirects=False,
                                headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        except requests.RequestException as exc:
            raise UrlUploadError(f"The server could not be reached ({type(exc).__name__}).")
        try:
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    raise UrlUploadError("The link redirects to nowhere.")
                current = urljoin(current, location)
                continue
            if resp.status_code >= 400:
                raise UrlUploadError(f"The server refused the file (HTTP {resp.status_code}).")
            declared = int(resp.headers.get("Content-Length") or 0)
            if declared > max_bytes:
                raise UrlUploadError(f"The file is bigger than {max_bytes // (1024 * 1024)} MB.")
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            buf = bytearray()
            for chunk in resp.iter_content(65536):
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise UrlUploadError(f"The file is bigger than {max_bytes // (1024 * 1024)} MB.")
                if time.monotonic() > deadline:
                    raise UrlUploadError("Downloading took too long.")
            return bytes(buf), ctype, current
        finally:
            resp.close()
    raise UrlUploadError("The link redirects too many times.")


def find_og_image(page_html: str, base_url: str) -> Optional[str]:
    """The page's social preview image (og:image or twitter:image), absolute, or None."""
    tags = re.findall(r"<meta\b[^>]*>", page_html, re.I)
    for tag in tags:
        key = re.search(r"(?:property|name)\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
        if not key or key.group(1).lower() not in ("og:image", "og:image:secure_url", "twitter:image"):
            continue
        content = re.search(r"content\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
        if content and content.group(1).strip():
            return urljoin(base_url, html_lib.unescape(content.group(1).strip()))
    return None


def _thumb_from_bytes(data: bytes) -> Optional[bytes]:
    try:
        return media_validation.thumbnail_bytes(data, max_side=PREVIEW_SIDE)
    except Exception:
        return None


def _preview_for(url: str, thumb_url: str, deadline: float, look_at_page: bool = True) -> Optional[bytes]:
    """A small JPEG preview: the caller's thumbnail, else the page's og:image. Never raises.

    look_at_page is False when the link is already a media file (no page to scan)."""
    candidates = []
    if thumb_url:
        candidates.append(thumb_url)
    elif look_at_page:
        try:
            page, _ctype, final = _get(url, deadline, MAX_PAGE_BYTES)
            found = find_og_image(page.decode("utf-8", "replace"), final)
            if found:
                candidates.append(found)
        except UrlUploadError:
            pass
    for candidate in candidates:
        try:
            image, _ctype, _final = _get(candidate, deadline, MAX_PREVIEW_BYTES)
        except UrlUploadError:
            continue
        thumb = _thumb_from_bytes(image)
        if thumb:
            return thumb
    return None


def _name_for(final_url: str, content_type: str, filename: str) -> str:
    if filename.strip():
        return blob_store.safe_filename(filename.strip())
    base = os.path.basename(urlparse(final_url).path) or "upload"
    if "." not in base:
        base += _EXT.get(content_type, ".bin")
    return blob_store.safe_filename(base)


def _preview_only(url: str, thumb_url: str, deadline: float, reason: str,
                  page_url: str = "") -> Dict[str, Any]:
    # The page the file lives on (e.g. a share page) is often readable when the file itself is not.
    preview = _preview_for(page_url or url, thumb_url, deadline)
    if preview:
        note = ("The image above is a preview from the link, so you can see what it shows. "
                "Nothing was stored.")
    else:
        note = "No preview could be found either. Nothing was stored."
    return {
        "ok": False,
        "preview": preview,
        "record": None,
        "message": (f"Could not save the file: {reason} {note} To save it, pass a direct image or video "
                    "link, or ask the person to upload it on the Upload page."),
    }


def pull(url: str, *, caption: str = "", kind: str = "auto", aspect: str = "auto",
         filename: str = "", thumb_url: str = "", page_url: str = "") -> Dict[str, Any]:
    """Download a link into staged uploads. Returns {ok, message, preview (JPEG bytes or None), record}."""
    kind = (kind or "auto").strip().lower()
    aspect = (aspect or "auto").strip().lower()
    if kind not in KINDS:
        raise UrlUploadError("kind must be auto, photo or reel.")
    if aspect not in ASPECTS:
        raise UrlUploadError("aspect must be auto, square, portrait, landscape or keep.")
    url = check_url(url)  # a bad or private link is refused outright, with no preview attempt
    deadline = time.monotonic() + TOTAL_SECONDS

    try:
        data, _ctype, final = _get(url, deadline, MAX_URL_BYTES)
    except UrlUploadError as exc:
        return _preview_only(url, thumb_url, deadline, str(exc), page_url)

    real = media_validation.sniff_content_type(data)
    if not (real.startswith("image/") or real.startswith("video/")):
        return _preview_only(url, thumb_url, deadline,
                             "the link is not a photo or video file. It may be a web page.", page_url)

    file_kind = "reel" if real.startswith("video/") else "photo"
    if kind != "auto" and kind != file_kind:
        raise UrlUploadError(f"That file is a {file_kind}. Use kind='auto' or kind='{file_kind}'.")
    if not blob_store.blob_configured():
        raise UrlUploadError("Blob storage is not connected to this project, so files cannot be saved.")

    name = _name_for(final, real, filename)
    stored = blob_store.put_bytes(blob_store.upload_key(blob_store.new_upload_id(), name), data,
                                  content_type=real, access=blob_store.BLOB_ACCESS)
    preview = (_thumb_from_bytes(data) if file_kind == "photo"
               else _preview_for(url, thumb_url, deadline, look_at_page=False))
    thumb_pathname = None
    if preview:
        thumb = blob_store.put_bytes(blob_store.upload_key(blob_store.new_upload_id(), "thumb.jpg"),
                                     preview, content_type="image/jpeg", access=blob_store.BLOB_ACCESS)
        thumb_pathname = thumb["pathname"]

    rec = upload_store.add_upload(filename=name, pathname=stored["pathname"], url=stored.get("url"),
                                  size=len(data), content_type=real, caption=caption.strip(),
                                  aspect=aspect, kind=file_kind, thumb_pathname=thumb_pathname)
    size_mb = f"{len(data) / (1024 * 1024):.1f} MB"
    caption_note = "Caption saved." if caption.strip() else "No caption yet; set one with set_upload_caption."
    return {
        "ok": True,
        "preview": preview,
        "record": rec,
        "message": (f"Saved \"{name}\" as {file_kind} upload {rec['id']} ({size_mb}). {caption_note} "
                    f"Check it with preview_upload, then post_upload when it is ready."),
    }
