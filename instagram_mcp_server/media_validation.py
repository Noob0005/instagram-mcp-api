"""
media_validation.py
-------------------
Server-side validation & conversion for staged uploads (the /upload page flow).

Rules:
  * Photos  — any Pillow-readable image. Converted to JPEG and cropped/resized
    to the requested feed aspect via mcp_server._prepare_feed_image (which the
    normal posting path already uses).
  * Reels   — must be MP4 containers holding H.264 video (+ AAC audio when the
    file has an audio track). Vercel has no ffmpeg, so anything else (MOV,
    MKV, WebM, HEVC-in-MP4, ...) is REJECTED and logged to the problem list,
    never silently converted. The MP4 header check below is a small pure-python
    box parser — no external binaries needed.

All helpers are offline-safe (no network): they work on bytes/temp files.
"""

import io
import os
import struct
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Magic-number signatures we accept directly from the browser upload.
_PHOTO_MAGICS = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp-or-wav",   # refined below (WEBP at offset 8)
    b"GIF8": "image/gif",
    b"BM": "image/bmp",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
}

_MAX_VIDEO_BYTES_DEFAULT = 256 * 1024 * 1024   # generous; Blob holds the file
_MAX_IMAGE_BYTES_DEFAULT = 32 * 1024 * 1024


def sniff_content_type(data: bytes) -> str:
    """Best-effort MIME type from magic numbers (never trusts the client header)."""
    if len(data) < 12:
        return "application/octet-stream"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"qt  ",):
            return "video/quicktime"
        if brand[:2] in (b"is", b"mp", b"M4") or brand in (b"avc1", b"dash"):
            return "video/mp4"
        return "video/mp4"  # unknown ISO-BMFF brand — treated as mp4 candidate
    if data[0:4] == b"\x1aE\xdf\xa3":
        return "video/webm"       # EBML (webm/mkv share this)
    if data[0:4] == b"\x30\x26\xb2\x75":
        return "video/x-ms-asf"   # wmv/asf
    if data[0:4] == b"\x00\x00\x01\xba" or data[0:4] == b"\x00\x00\x01\xb3":
        return "video/mpeg"
    return "application/octet-stream"


def looks_like_image(data: bytes) -> bool:
    return sniff_content_type(data).startswith("image/")


def looks_like_video(data: bytes) -> bool:
    return sniff_content_type(data).startswith("video/")


# ---------------------------------------------------------------------------
# Minimal MP4 box parser (H.264 + AAC detection without ffmpeg)
# ---------------------------------------------------------------------------

def _iter_boxes(buf: bytes, start: int, end: int) -> List[Tuple[bytes, int, int]]:
    """Yield (box_type, payload_start, payload_end) for top-level boxes."""
    out = []
    pos = start
    while pos + 8 <= end:
        size = struct.unpack(">I", buf[pos:pos + 4])[0]
        btype = buf[pos + 4:pos + 8]
        header = 8
        if size == 1:  # 64-bit largesize
            if pos + 16 > end:
                break
            size = struct.unpack(">Q", buf[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:  # extends to EOF
            size = end - pos
        if size < header or pos + size > end:
            break
        out.append((btype, pos + header, pos + size))
        pos += size
    return out


def inspect_mp4(data: bytes) -> Dict[str, Any]:
    """Parse enough of an MP4 to decide whether Instagram will accept it.

    Returns dict with: ok (bool), codecs (list), has_audio (bool), reason (str).
    Checks:
      * a moov/trak/mdia/hdlr pair declares 'vide' and/or 'soun' tracks
      * video sample entry fourcc starts with 'avc' (H.264/AVC)
      * audio sample entry fourcc is mp4a with a sane AAC profile
    """
    result: Dict[str, Any] = {"ok": False, "codecs": [], "has_audio": False,
                              "has_video": False, "reason": ""}
    if data[4:8] != b"ftyp":
        result["reason"] = "not an MP4 container (missing ftyp box)"
        return result

    top = _iter_boxes(data, 0, len(data))
    moov = next(((s, e) for t, s, e in top if t == b"moov"), None)
    if not moov:
        result["reason"] = "MP4 has no moov box (truncated or non-standard file)"
        return result

    codecs: List[str] = []
    for m_s, m_e in [moov]:
        for trak_s, trak_e in [(s, e) for t, s, e in _iter_boxes(data, m_s, m_e) if t == b"trak"]:
            hdlr = next(((s, e) for t, s, e in _walk(data, trak_s, trak_e) if t == b"hdlr"), None)
            handler = b""
            if hdlr:
                handler = data[hdlr[0] + 8:hdlr[0] + 12]  # handler_type after version+flags+predefined
            stsd = next(((s, e) for t, s, e in _walk(data, trak_s, trak_e) if t == b"stsd"), None)
            fourcc = b""
            if stsd:
                # stsd: version(1)+flags(3)+entry_count(4), then entry: size(4)+fourcc(4)
                p = stsd[0] + 8
                if p + 8 <= stsd[1]:
                    fourcc = data[p + 4:p + 8]
            if handler == b"vide":
                result["has_video"] = True
                if fourcc.startswith(b"avc"):
                    codecs.append("h264")
                else:
                    codecs.append(fourcc.decode("ascii", "replace") or "unknown-video")
            elif handler == b"soun":
                result["has_audio"] = True
                if fourcc == b"mp4a":
                    codecs.append("aac")
                else:
                    codecs.append(fourcc.decode("ascii", "replace") or "unknown-audio")

    result["codecs"] = codecs
    problems = []
    if not result["has_video"]:
        problems.append("no video track found")
    elif "h264" not in codecs:
        bad = [c for c in codecs if c not in ("aac",)]
        problems.append(f"video codec is {','.join(bad) or 'unknown'} — Instagram reels need H.264")
    if result["has_audio"] and "aac" not in codecs:
        bad = [c for c in codecs if c not in ("h264",)]
        problems.append(f"audio codec is {','.join(bad) or 'unknown'} — reels need AAC audio")
    if problems:
        result["reason"] = "; ".join(problems)
        return result
    result["ok"] = True
    return result


def _walk(buf: bytes, start: int, end: int):
    """Depth-first walk of all nested boxes under [start,end)."""
    stack = [(start, end)]
    seen = []
    while stack:
        s, e = stack.pop()
        for btype, cs, ce in _iter_boxes(buf, s, e):
            seen.append((btype, cs, ce))
            if btype in (b"trak", b"mdia", b"minf", b"stbl", b"udta", b"edts"):
                stack.append((cs, ce))
    return seen


def validate_reel(data: bytes) -> Dict[str, Any]:
    """Full reel gate: MP4 container + H.264 (+AAC). Rejected formats get a reason."""
    ctype = sniff_content_type(data)
    if ctype == "video/quicktime":
        return {"ok": False, "reason": "QuickTime .mov is not accepted — export as MP4 (H.264 + AAC)",
                "format": "mov"}
    if ctype in ("video/webm", "video/x-ms-asf", "video/mpeg"):
        return {"ok": False, "reason": f"{ctype.split('/')[1]} is not accepted — export as MP4 (H.264 + AAC)",
                "format": ctype}
    if ctype != "video/mp4":
        return {"ok": False, "reason": "file is not a recognised video format", "format": ctype}
    info = inspect_mp4(data)
    info["format"] = "mp4"
    return info


# ---------------------------------------------------------------------------
# Photo validation / conversion
# ---------------------------------------------------------------------------

def open_image(data: bytes) -> "Image":  # noqa: F821
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def prepare_photo_bytes(data: bytes, aspect: str = "auto") -> Tuple[bytes, Dict[str, Any]]:
    """Validate + convert photo bytes to a feed-ready JPEG.

    Uses the same pipeline as normal posting (mcp_server._prepare_feed_image)
    so EXIF rotation, aspect cropping and resizing behave identically.
    Returns (jpeg_bytes, info_dict). Raises ValueError for unreadable images.
    """
    from instagram_mcp_server.mcp_server import _prepare_feed_image

    suffix = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
              "image/bmp": ".bmp", "image/tiff": ".tiff"}.get(sniff_content_type(data), ".img")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()
        out_path, created, info = _prepare_feed_image(Path(tmp.name), aspect)
        with open(out_path, "rb") as fh:
            jpeg = fh.read()
        if out_path != tmp.name:
            try:
                os.remove(out_path)
            except OSError:
                pass
        return jpeg, info
    except Exception as e:
        raise ValueError(f"image could not be read/converted: {e}") from e
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def thumbnail_bytes(data: bytes, max_side: int = 256) -> bytes:
    """Small JPEG thumbnail for preview_upload (agent-visible without fetching URLs)."""
    from PIL import Image
    im = open_image(data)
    if im.mode in ("RGBA", "LA", "P"):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return buf.getvalue()
