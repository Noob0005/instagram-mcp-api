"""
mcp_server.py
--------------
Instagram Control MCP Server — built with FastMCP + instagrapi.
Exposes 60+ tools covering EVERY Instagram action a human can perform.

FULL POST MANAGEMENT:
  caption, hashtags, @mentions in caption, user-tag people IN photos,
  location tags, alt text (accessibility), close-friends stories,
  story stickers (hashtag/mention/location/link), edit captions,
  disable/enable comments, archive/unarchive, pin/unpin, and more.
"""

import collections
import hashlib
import json
import os
import random
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Annotated, List, Optional
from urllib.parse import unquote, urlparse

import requests
from pydantic import Field

from fastmcp import FastMCP
from fastmcp.utilities.types import Image  # tool image returns
from instagram_mcp_server.instagram_client import InstagramClientWrapper

# ─────────────────────────────────────────────────────────────────────────────
# SERVER & CLIENT SETUP
# ─────────────────────────────────────────────────────────────────────────────

_IS_SERVERLESS = bool(
    os.environ.get("VERCEL")
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    or os.environ.get("FUNCTIONS_WORKER_RUNTIME")
)


def _state_dir() -> str:
    """Directory for runtime state files (session, counters, queue, dedupe).

    Serverless platforms (Vercel, Lambda) give each instance a read-only home
    directory, so the writable temp dir is used there instead.
    """
    if _IS_SERVERLESS:
        return tempfile.gettempdir()
    return os.path.expanduser("~")

mcp = FastMCP(
    "Instagram Control",
    instructions=(
        "Full Instagram account control server (104 tools: posts, reels, stories, highlights, "
        "comments, DMs, relations, saves, notes, scheduling, reads). "
        "Auto-restores session on startup — call instagram_get_login_status to verify; "
        "instagram_login_with_sessionid is the most reliable login. "
        "IMAGES FROM CHAT: a chat attachment is NOT visible to this server. Get the picture onto "
        "the machine first — instagram_upload_image(base64 or data:image data) for screenshots, "
        "an absolute path / http(s) URL, 'latest' for the newest inbox file, the browser upload "
        "page for phone photos (same domain as this server, /mcp → /inbox; the exact link appears "
        "in instagram_inbox_status and in any 'image not found' error), or "
        "scripts/save_image.py / watch_clipboard.py on this PC. Check waiting files with "
        "instagram_inbox_status; preview framing/size with instagram_inspect_image. "
        "POSTING: instagram_post_photo(image_path_or_url, caption, hashtags, mentions, "
        "tag_users_in_photo, location_name, alt_text, disable_comments, dry_run, aspect) — "
        "aspect 'auto' keeps a valid ratio, 'portrait' = 4:5 tall (1080x1350), 'square' = 1:1, "
        "'landscape' = 1.91:1. Always draft the caption, preview with dry_run=True, show it to the "
        "user, and publish (dry_run=False) only after they approve. Carousels: instagram_post_album; "
        "stories: instagram_post_photo_story / instagram_post_video_story; later: instagram_schedule_post. "
        "REPLYING: instagram_reply_to_comment_by_username(post_url, username, text) replies to a "
        "specific person without looking up ids; instagram_get_post_comments(url, 50, 'likes') shows "
        "the top comments; instagram_get_recent_comments excludes your own by default. "
        "NEWER FEATURES: comment tools (pin/unpin, unlike, likers, instagram_check_comment preflight), "
        "DM tools (react_to_dm, unsend_dm, mute_thread, search_dm_messages), story tools "
        "(like_story, get_story_polls + vote_story_poll, add_to_highlight), relations "
        "(mute_user, remove_follower, handle_follow_request, manage_close_friends, follow_hashtag), "
        "saves (save_to_collection, get_saved_collections, get_archived_posts) and Instagram Notes "
        "(create_note, get_notes, delete_note). "
        "All write actions are paced automatically (seconds reported as paced_seconds) and share "
        "hourly/daily caps — never repeat identical comments, and respect rate-limit pauses. "
        "DELETING: delete/unsend tools require preview + approval — call with confirm=False, show the "
        "details to the user, then call again with confirm=True only after they agree. "
        "RISK: tools are graded red/orange/green by bot-detection exposure — call "
        "instagram_get_risk_categories for the full list. Prefer green/orange workflows and use red "
        "tools (public comments on others, likes, follows, DMs, bulk discovery reads) sparingly."
    )
)

def _load_env_file() -> None:
    """Optionally load KEY=VALUE pairs from a .env file (no extra dependency).

    Search order: INSTAGRAM_MCP_ENV_FILE, then ./.env. Existing environment
    variables always win, so MCP client `env` blocks keep priority over the file.
    """
    candidates = [os.environ.get("INSTAGRAM_MCP_ENV_FILE"), os.path.join(os.getcwd(), ".env")]
    for candidate in candidates:
        if not candidate or not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key:
                        os.environ.setdefault(key, value)
            print(f"[instagram-mcp] loaded env file: {candidate}", file=sys.stderr)
        except Exception as e:
            print(f"[instagram-mcp] could not read env file {candidate}: {e}", file=sys.stderr)
        return


_load_env_file()

_SESSION_PATH = os.environ.get(
    "INSTAGRAM_MCP_SESSION_PATH",
    os.path.join(_state_dir(), ".instagram_mcp_session.json"),
)
ig = InstagramClientWrapper(session_path=_SESSION_PATH)
ig.init_from_saved_session()  # auto-restore on startup


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC URL TRACKING (tunnel / reverse-proxy aware)
# ─────────────────────────────────────────────────────────────────────────────
# The inbox upload link must be usable from the domain a client actually reached
# the server through — a tunnel domain, a reverse proxy, or a plain LAN address.
# The server cannot know its own public URL, so scripts/serve.py reports the
# origin (scheme + Host / X-Forwarded-*) of every incoming request here. Image
# hints then reuse that exact domain with "/mcp" swapped for "/inbox", so a
# port-forward, Cloudflare Tunnel or Tailscale URL works without any config.
_RUNTIME_ORIGIN = {"base": ""}


def note_request_base(scheme: str, host: str) -> None:
    """Remember the origin a client actually connected through (called per request)."""
    scheme = (scheme or "http").split(",")[0].strip().lower()
    host = (host or "").split(",")[0].strip()
    if scheme and host:
        _RUNTIME_ORIGIN["base"] = f"{scheme}://{host}"


def _inbox_from_base(raw: str) -> str:
    """Turn any base or MCP URL into the inbox URL: '…/mcp' -> '…/inbox'."""
    url = (raw or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/mcp"):
        url = url[: -len("/mcp")]
    if not url.endswith("/inbox"):
        url += "/inbox"
    return url


def _inbox_url() -> str:
    """Browser upload URL for the image inbox, whatever domain the client used.

    Preference: INSTAGRAM_MCP_PUBLIC_URL → origin of the last request (tunnel /
    reverse-proxy aware) → INSTAGRAM_MCP_INBOX_URL (startup fallback, LAN or
    loopback). The auth key is appended so the printed link works as-is.
    """
    explicit = os.environ.get("INSTAGRAM_MCP_PUBLIC_URL") or ""
    if explicit.strip():
        url = _inbox_from_base(explicit)
    elif _RUNTIME_ORIGIN["base"]:
        url = _inbox_from_base(_RUNTIME_ORIGIN["base"])
    else:
        return (os.environ.get("INSTAGRAM_MCP_INBOX_URL") or "").strip()
    key = (os.environ.get("MCP_AUTH_KEY") or "").strip()
    if key and "auth=" not in url:
        url += f"?auth={key}"
    return url


def _env_auto_login() -> None:
    """Auto-login from environment/.env (never logs secrets).

    Order: saved session (checked by init_from_saved_session) → sessionid cookie
    (INSTAGRAM_MCP_SESSIONID) → username + password (INSTAGRAM_MCP_USERNAME /
    INSTAGRAM_MCP_PASSWORD, optional INSTAGRAM_MCP_2FA_CODE).
    """
    try:
        if ig.get_login_status().get("logged_in"):
            return
        username = os.environ.get("INSTAGRAM_MCP_USERNAME", "")
        session_id = os.environ.get("INSTAGRAM_MCP_SESSIONID")
        if session_id:
            result = ig.login_with_sessionid(username, session_id)
            print(f"[instagram-mcp] env sessionid login: {result.get('status')}", file=sys.stderr)
            if result.get("status") == "success":
                return
        password = os.environ.get("INSTAGRAM_MCP_PASSWORD")
        if password:
            result = ig.login_with_credentials(
                username, password,
                verification_code=os.environ.get("INSTAGRAM_MCP_2FA_CODE") or None,
            )
            status = result.get("status")
            print(f"[instagram-mcp] env password login: {status}", file=sys.stderr)
            if status == "needs_2fa":
                print("[instagram-mcp] 2FA required — call instagram_complete_2fa with a fresh code.",
                      file=sys.stderr)
            elif status == "needs_challenge":
                print("[instagram-mcp] security challenge — call instagram_complete_challenge with "
                      "the code sent to your email/SMS.", file=sys.stderr)
    except Exception as e:  # never crash startup because of a bad credential
        print(f"[instagram-mcp] env auto-login failed: {e}", file=sys.stderr)


_env_auto_login()


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _require_login() -> Optional[str]:
    """Verify the session, cached briefly so tool calls don't double the API traffic.

    If the session is dead and INSTAGRAM_MCP_PASSWORD is configured, one
    throttled password re-login is attempted before giving up.
    """
    ttl = _login_cache_ttl()
    now = time.monotonic()
    if _login_cache["ok"] and now - _login_cache["checked_at"] < ttl:
        return None
    ok = ig.is_logged_in()
    if not ok and _try_env_relogin():
        ok = True
    now = time.monotonic()
    _login_cache["checked_at"] = now
    _login_cache["ok"] = ok
    if not ok:
        return "Error: Not logged in. Call instagram_login_with_sessionid or instagram_login_with_credentials first."
    return None

def _download_if_url(path_or_url: str, suffix: str = ".jpg") -> str:
    """Download remote URL to a temp local file. Returns local path."""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        r = requests.get(path_or_url, stream=True, timeout=30)
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "")
        if "mp4" in ct or "video" in ct:
            suffix = ".mp4"
        elif "png" in ct:
            suffix = ".png"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        for chunk in r.iter_content(8192):
            tmp.write(chunk)
        tmp.close()
        return tmp.name
    return path_or_url

def _reject_non_mp4(path: str) -> Optional[str]:
    """Reels from a public URL must really be MP4 (H.264 + AAC). Returns an error or None.

    Checks the file's bytes, not the URL or Content-Type, because those are unreliable.
    """
    from instagram_mcp_server import media_validation  # lazy: avoids an import cycle
    with open(path, "rb") as fh:
        info = media_validation.validate_reel(fh.read())
    if info.get("ok"):
        return None
    return ("Error: reel rejected: " + (info.get("reason") or "not an MP4 file")
            + ". Send a direct public link to an .mp4 file (H.264 video, AAC audio).")

def _cleanup(local: str, original: str):
    """Delete the temp file we created for a URL, data-URI or pasted base64 input."""
    raw = (original or "").strip()
    if raw.startswith(("http://", "https://", "data:")) or _looks_like_base64(raw):
        _remove_file(local)


_BASE64_RE = re.compile(r"^[A-Za-z0-9+/\s]+={0,2}$")
_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"RIFF", ".webp"),
)
_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif")


def _looks_like_base64(value: str) -> bool:
    """Heuristic: base64-shaped text with no path separators (pasted image data).

    The threshold is deliberately low so small pasted images/screenshots work; real
    image data is confirmed by the magic-byte check in `_decode_image_data`, and any
    filename with an extension or path separator is excluded by the charset rule.
    """
    compact = "".join(str(value).split())
    return len(compact) >= 64 and bool(_BASE64_RE.match(compact))


def _image_suffix(blob: bytes) -> str:
    for magic, suffix in _IMAGE_MAGIC:
        if blob.startswith(magic):
            return suffix
    return ""


def _write_image_temp(blob: bytes, suffix: str) -> str:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".img")
    with handle:
        handle.write(blob)
    return handle.name


def _decode_image_data(raw: str) -> str:
    """Decode `data:image/...;base64,...` or a raw base64 image into a temp file."""
    import base64
    if raw.startswith("data:"):
        header, _, payload = raw.partition(",")
        if "base64" not in header.lower():
            raise ValueError("Only base64 data URIs are supported (data:image/png;base64,...).")
    else:
        payload = raw
    compact = "".join(payload.split())
    try:
        blob = base64.b64decode(compact, validate=False)
    except Exception as exc:
        raise ValueError(f"Could not decode the pasted image data ({exc}).") from exc
    suffix = _image_suffix(blob)
    if not suffix:
        raise ValueError("The pasted data is not a JPEG/PNG/GIF/WebP image. Save the image as a "
                         "file and pass its absolute path instead.")
    return _write_image_temp(blob, suffix)


def _inbox_dir() -> Path:
    """Folder where images can be dropped for the server (INSTAGRAM_MCP_INBOX)."""
    configured = os.environ.get("INSTAGRAM_MCP_INBOX", "").strip()
    base = (Path(os.path.expandvars(os.path.expanduser(configured)))
            if configured else Path.home() / "instagram-mcp-inbox")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _find_in_inbox(raw: str) -> Optional[Path]:
    """Find an image inside the inbox: by name, or the newest one for 'latest'."""
    inbox = _inbox_dir()
    if str(raw).lower() in ("latest", "newest", "last", "recent"):
        candidates = [p for p in inbox.rglob("*") if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES]
        return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
    direct = inbox / raw
    if direct.is_file():
        return direct
    matches = [p for p in inbox.rglob(os.path.basename(raw)) if p.is_file()]
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def _safe_inbox_name(name: str) -> str:
    """Sanitise a filename so an upload can only ever land inside the inbox folder."""
    base = os.path.basename(str(name or "").replace("\\", "/")).strip() or "upload.jpg"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    if not os.path.splitext(base)[1]:
        base += ".jpg"
    return base[:120]


def _save_to_inbox(local_path: str, name: str = "") -> Path:
    """Save an image into the inbox folder (never overwrites — adds a timestamp)."""
    inbox = _inbox_dir()
    target = inbox / _safe_inbox_name(name or Path(local_path).name)
    if os.path.abspath(str(target)) == os.path.abspath(str(local_path)):
        return target  # already sitting in the inbox
    if target.exists():
        target = inbox / f"{time.strftime('%Y%m%d-%H%M%S')}-{target.name}"
    target.write_bytes(Path(local_path).read_bytes())
    return target

def _remove_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def _supports_kwarg(func, name: str) -> bool:
    """Check whether a client method accepts a keyword argument (version-safe)."""
    try:
        import inspect
        return name in inspect.signature(func).parameters
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG + PACING (human-like delays to avoid account flags)
# ─────────────────────────────────────────────────────────────────────────────

_login_cache = {"checked_at": 0.0, "ok": False}
_last_relogin_attempt = 0.0
_ACTION_LOCK_UNTIL = 0.0  # global pause, armed after Instagram rate-limit feedback
_COMMENT_ACTIONS = ("comment", "reply")
_COMMENT_HISTORY = collections.deque()  # monotonic timestamps of recent comments

def _cfg_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)

def _cfg_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)

def _safe_mode() -> bool:
    """INSTAGRAM_MCP_SAFE_MODE=1 applies very conservative defaults."""
    return str(os.environ.get("INSTAGRAM_MCP_SAFE_MODE", "")).strip().lower() in ("1", "true", "yes", "on")

_WRITE_COUNT_PATH = os.environ.get(
    "INSTAGRAM_MCP_WRITE_COUNT_PATH",
    os.path.join(_state_dir(), ".instagram_mcp_write_counts.json"),
)

def _comment_hourly_cap() -> int:
    if "INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR" in os.environ:
        return _cfg_int("INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR", 10)
    return 3 if _safe_mode() else 10

def _daily_write_cap() -> int:
    if "INSTAGRAM_MCP_MAX_WRITES_PER_DAY" in os.environ:
        return _cfg_int("INSTAGRAM_MCP_MAX_WRITES_PER_DAY", 0)
    return 25 if _safe_mode() else 0

def _load_write_count() -> dict:
    try:
        with open(_WRITE_COUNT_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        data = {}
    today = time.strftime("%Y-%m-%d")
    if not isinstance(data, dict) or data.get("date") != today:
        return {"date": today, "count": 0, "red": 0}
    try:
        return {"date": today,
                "count": int(data.get("count", 0) or 0),
                "red": int(data.get("red", 0) or 0)}
    except (TypeError, ValueError):
        return {"date": today, "count": 0, "red": 0}

def _count_write(is_red: bool = False) -> None:
    rec = _load_write_count()
    rec["count"] += 1
    if is_red:
        rec["red"] += 1
    try:
        with open(_WRITE_COUNT_PATH, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
    except Exception:
        pass

def _login_cache_ttl() -> float:
    if "INSTAGRAM_MCP_LOGIN_CACHE_TTL" in os.environ:
        return _cfg_float("INSTAGRAM_MCP_LOGIN_CACHE_TTL", 60.0)
    return 300.0 if _safe_mode() else 60.0

def _relogin_cooldown() -> float:
    if "INSTAGRAM_MCP_RELOGIN_COOLDOWN" in os.environ:
        return _cfg_float("INSTAGRAM_MCP_RELOGIN_COOLDOWN", 300.0)
    return 1800.0 if _safe_mode() else 300.0

# ─── Tool risk categories (bot-detection exposure) ───
_RED_ACTIONS = ("comment", "reply", "like", "social", "dm")

_TOOL_RISK_RED = {
    "instagram_comment_on_post": "public comment on someone else's post",
    "instagram_reply_to_comment": "public reply to a stranger's comment",
    "instagram_reply_to_comment_by_username": "public reply to a stranger's comment",
    "instagram_like_post": "mass liking is an automation signature",
    "instagram_unlike_post": "like churn is an automation signature",
    "instagram_like_comment": "mass liking is an automation signature",
    "instagram_follow_user": "follow/unfollow churn is the #1 automation signal",
    "instagram_unfollow_user": "follow/unfollow churn is the #1 automation signal",
    "instagram_block_user": "relationship churn is monitored",
    "instagram_unblock_user": "relationship churn is monitored",
    "instagram_send_direct_message": "DMs to strangers are heavily monitored",
    "instagram_send_dm_photo": "DMs to strangers are heavily monitored",
    "instagram_send_dm_video": "DMs to strangers are heavily monitored",
    "instagram_login_with_credentials": "each password login looks like a new device",
    "instagram_search_posts": "bulk search reads look like scraping",
    "instagram_find_topic_content": "bulk discovery reads look like scraping",
    "instagram_get_explore_reels": "explore scraping is a known signal",
    "instagram_search_users": "bulk user search looks like scraping",
    "instagram_search_hashtag": "bulk hashtag reads look like scraping",
    "instagram_get_hashtag_top_posts": "bulk hashtag reads look like scraping",
    "instagram_get_timeline_feed": "heavy feed reads trigger rate limits",
    "instagram_get_followers": "bulk follower scraping is monitored",
    "instagram_get_following": "bulk following scraping is monitored",
    "instagram_get_location_posts": "bulk location reads look like scraping",
    "instagram_get_similar_accounts": "suggestion scraping is monitored",
    "instagram_unlike_comment": "like churn is an automation signature",
    "instagram_react_to_dm": "DMs are heavily monitored",
    "instagram_unsend_dm": "DM activity is heavily monitored",
    "instagram_like_story": "liking stories is an automation signature",
    "instagram_vote_story_poll": "story engagement is monitored",
    "instagram_remove_follower": "relationship churn is monitored",
}

_TOOL_RISK_ORANGE = {
    "instagram_post_photo": "own-account posting; avoid rapid series",
    "instagram_post_video": "own-account posting; avoid rapid series",
    "instagram_post_reel": "own-account posting; avoid rapid series",
    "instagram_post_album": "own-account posting; avoid rapid series",
    "instagram_post_photo_story": "own-account posting; avoid rapid series",
    "instagram_post_video_story": "own-account posting; avoid rapid series",
    "instagram_schedule_post": "schedules a post/story for later",
    "instagram_edit_post_caption": "post editing is rate-limited",
    "instagram_edit_profile": "profile edits are rate-limited",
    "instagram_change_profile_picture": "profile edits are rate-limited",
    "instagram_delete_post": "deletions are monitored",
    "instagram_delete_story": "deletions are monitored",
    "instagram_delete_comment": "deletions are monitored",
    "instagram_delete_highlight": "deletions are monitored",
    "instagram_archive_post": "moderation action",
    "instagram_unarchive_post": "moderation action",
    "instagram_pin_post": "moderation action",
    "instagram_unpin_post": "moderation action",
    "instagram_disable_comments": "moderation action",
    "instagram_enable_comments": "moderation action",
    "instagram_tag_users_in_post": "moderation action",
    "instagram_save_post": "private bookmarking; low visibility",
    "instagram_unsave_post": "private bookmarking; low visibility",
    "instagram_get_user_feed": "reading another account's feed; keep volume low",
    "instagram_get_user_stories": "reading stories; keep volume low",
    "instagram_get_post_likers": "list scraping; keep volume low",
    "instagram_get_tagged_posts": "list scraping; keep volume low",
    "instagram_get_pending_follow_requests": "list scraping; keep volume low",
    "instagram_pin_comment": "own-post moderation action",
    "instagram_get_comment_likers": "list scraping; keep volume low",
    "instagram_save_to_collection": "private bookmarking; low visibility",
    "instagram_get_saved_collections": "own-account read",
    "instagram_get_archived_posts": "own-account read",
    "instagram_add_to_highlight": "own-account edit",
    "instagram_mute_thread": "inbox moderation",
    "instagram_search_dm_messages": "reading DMs; keep volume low",
    "instagram_get_story_polls": "reading stories; keep volume low",
    "instagram_mute_user": "quiet moderation action",
    "instagram_handle_follow_request": "own-account moderation",
    "instagram_manage_close_friends": "own-account list edit",
    "instagram_follow_hashtag": "follow churn is monitored",
    "instagram_create_note": "own-account post",
    "instagram_delete_note": "deletion is monitored",
    "instagram_mark_thread_seen": "writes DM state; keep volume low",
    "instagram_create_highlight": "moderation action",
}

def _red_daily_cap() -> int:
    if "INSTAGRAM_MCP_MAX_RED_ACTIONS_PER_DAY" in os.environ:
        return _cfg_int("INSTAGRAM_MCP_MAX_RED_ACTIONS_PER_DAY", 0)
    return 8 if _safe_mode() else 0

# ─── Duplicate suppression (client-timeout retry protection) ───
_DEDUPE_PATH = os.environ.get(
    "INSTAGRAM_MCP_DEDUPE_PATH",
    os.path.join(_state_dir(), ".instagram_mcp_recent_actions.json"),
)

def _load_recent_actions() -> dict:
    try:
        with open(_DEDUPE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _save_recent_actions(data: dict) -> None:
    try:
        with open(_DEDUPE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        pass

def _dedupe_guard(scope: str, target: str, payload: str) -> Optional[str]:
    """Refuse an identical action (same scope + target + payload) inside the window.

    Protects against duplicated sends when an MCP client times out and the user
    re-approves the same tool call — a retry after a timeout usually means the
    first attempt already succeeded. State persists on disk, so it also protects
    across client/server restarts. Disable with INSTAGRAM_MCP_DEDUPE_WINDOW=0.
    """
    window = _cfg_float("INSTAGRAM_MCP_DEDUPE_WINDOW", 600.0)
    if window <= 0:
        return None
    digest = hashlib.sha1(str(payload).encode("utf-8", "ignore")).hexdigest()[:16]
    key = f"{scope}:{target}:{digest}"
    now = time.time()
    data = {k: v for k, v in _load_recent_actions().items()
            if isinstance(v, (int, float)) and now - v < window}
    prev = data.get(key)
    if prev:
        remaining = int(window - (now - prev))
        return (f"Duplicate suppressed: the same {scope} for this target already ran "
                f"{int(now - prev)}s ago, so this call was skipped (a client-timeout retry would "
                f"have sent it twice). If the earlier attempt actually FAILED, wait ~{remaining}s "
                f"or set INSTAGRAM_MCP_DEDUPE_WINDOW=0 and retry.")
    data[key] = now
    _save_recent_actions(data)
    return None

def _pacing_error(action: str) -> Optional[str]:
    """Return an error message when a write action must NOT run yet, else None."""
    now = time.monotonic()
    remaining = _ACTION_LOCK_UNTIL - now
    if remaining > 0:
        until = time.strftime("%H:%M:%S", time.localtime(time.time() + remaining))
        return (f"Instagram temporarily blocked actions (rate limit / spam feedback). "
                f"Paused for ~{int(remaining)}s (until {until}). Wait and try again.")
    if action in _COMMENT_ACTIONS:
        cap = _comment_hourly_cap()
        window = 3600.0
        while _COMMENT_HISTORY and now - _COMMENT_HISTORY[0] > window:
            _COMMENT_HISTORY.popleft()
        if cap > 0 and len(_COMMENT_HISTORY) >= cap:
            wait = int(window - (now - _COMMENT_HISTORY[0])) + 1
            return (f"Local safety limit reached: max {cap} comments/replies per hour. "
                    f"Try again in ~{wait}s or raise INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR.")
    if action in _RED_ACTIONS:
        red_cap = _red_daily_cap()
        if red_cap > 0:
            rec = _load_write_count()
            if rec["red"] >= red_cap:
                return (f"Red-category daily cap reached ({red_cap}/day). Red tools (comments/replies on others, "
                        f"likes, follows, DMs, bulk discovery) are the main bot-detection triggers — wait until "
                        f"tomorrow or raise INSTAGRAM_MCP_MAX_RED_ACTIONS_PER_DAY deliberately.")
    cap = _daily_write_cap()
    if cap > 0:
        rec = _load_write_count()
        if rec["count"] >= cap:
            return (f"Daily write-action safety cap reached ({cap}/day). Increase "
                    f"INSTAGRAM_MCP_MAX_WRITES_PER_DAY or disable INSTAGRAM_MCP_SAFE_MODE to change this.")
    return None

def _pace_action(action: str) -> int:
    """Sleep a human-like, configurable delay before a write action.

    action: "comment"/"reply", "post", or "engage" (likes, saves, follows, DMs).
    Returns the number of seconds waited (reported in tool output).
    """
    if action in _COMMENT_ACTIONS:
        if "INSTAGRAM_MCP_COMMENT_DELAY_MIN" in os.environ or "INSTAGRAM_MCP_COMMENT_DELAY_MAX" in os.environ:
            lo = _cfg_float("INSTAGRAM_MCP_COMMENT_DELAY_MIN", 5.0)
            hi = _cfg_float("INSTAGRAM_MCP_COMMENT_DELAY_MAX", 12.0)
        elif _safe_mode():
            lo, hi = 90.0, 240.0
        else:
            lo, hi = 5.0, 12.0
    elif action == "post":
        if "INSTAGRAM_MCP_POST_DELAY_MIN" in os.environ or "INSTAGRAM_MCP_POST_DELAY_MAX" in os.environ:
            lo = _cfg_float("INSTAGRAM_MCP_POST_DELAY_MIN", 15.0)
            hi = _cfg_float("INSTAGRAM_MCP_POST_DELAY_MAX", 40.0)
        elif _safe_mode():
            lo, hi = 300.0, 900.0
        else:
            lo, hi = 15.0, 40.0
    elif action == "like":
        if "INSTAGRAM_MCP_LIKE_DELAY_MIN" in os.environ or "INSTAGRAM_MCP_LIKE_DELAY_MAX" in os.environ:
            lo = _cfg_float("INSTAGRAM_MCP_LIKE_DELAY_MIN", 3.0)
            hi = _cfg_float("INSTAGRAM_MCP_LIKE_DELAY_MAX", 8.0)
        elif _safe_mode():
            lo, hi = 60.0, 180.0
        else:
            lo, hi = 3.0, 8.0
    elif action == "social":
        if "INSTAGRAM_MCP_SOCIAL_DELAY_MIN" in os.environ or "INSTAGRAM_MCP_SOCIAL_DELAY_MAX" in os.environ:
            lo = _cfg_float("INSTAGRAM_MCP_SOCIAL_DELAY_MIN", 10.0)
            hi = _cfg_float("INSTAGRAM_MCP_SOCIAL_DELAY_MAX", 25.0)
        elif _safe_mode():
            lo, hi = 300.0, 600.0
        else:
            lo, hi = 10.0, 25.0
    elif action == "dm":
        if "INSTAGRAM_MCP_DM_DELAY_MIN" in os.environ or "INSTAGRAM_MCP_DM_DELAY_MAX" in os.environ:
            lo = _cfg_float("INSTAGRAM_MCP_DM_DELAY_MIN", 4.0)
            hi = _cfg_float("INSTAGRAM_MCP_DM_DELAY_MAX", 10.0)
        elif _safe_mode():
            lo, hi = 120.0, 300.0
        else:
            lo, hi = 4.0, 10.0
    else:
        if "INSTAGRAM_MCP_ACTION_DELAY_MIN" in os.environ or "INSTAGRAM_MCP_ACTION_DELAY_MAX" in os.environ:
            lo = _cfg_float("INSTAGRAM_MCP_ACTION_DELAY_MIN", 2.0)
            hi = _cfg_float("INSTAGRAM_MCP_ACTION_DELAY_MAX", 6.0)
        elif _safe_mode():
            lo, hi = 30.0, 120.0
        else:
            lo, hi = 2.0, 6.0
    if hi < lo:
        lo, hi = hi, lo
    delay = random.uniform(lo, hi) if hi > 0 else 0.0
    if delay > 0:
        time.sleep(delay)
    if action in _COMMENT_ACTIONS:
        _COMMENT_HISTORY.append(time.monotonic())
    _count_write(is_red=action in _RED_ACTIONS)
    return int(round(delay))

def _try_env_relogin() -> bool:
    """Fallback login with INSTAGRAM_MCP_USERNAME/PASSWORD when the session dies.

    Throttled (INSTAGRAM_MCP_RELOGIN_COOLDOWN, default 300s) so a dead cookie
    cannot turn every tool call into a password attempt.
    """
    global _last_relogin_attempt
    password = os.environ.get("INSTAGRAM_MCP_PASSWORD")
    if not password:
        return False
    now = time.monotonic()
    if _last_relogin_attempt and now - _last_relogin_attempt < _relogin_cooldown():
        return False
    _last_relogin_attempt = now
    username = os.environ.get("INSTAGRAM_MCP_USERNAME", "")
    code = os.environ.get("INSTAGRAM_MCP_2FA_CODE") or None
    try:
        result = ig.login_with_credentials(username, password, verification_code=code)
        status = result.get("status") if isinstance(result, dict) else None
        print(f"[instagram-mcp] session fallback login: {status}", file=sys.stderr)
        return status == "success"
    except Exception as e:
        print(f"[instagram-mcp] session fallback login failed: {e}", file=sys.stderr)
        return False

def _note_login_result(result) -> None:
    """Update the login cache immediately after a deliberate login action."""
    try:
        status = result.get("status") if isinstance(result, dict) else None
    except Exception:
        status = None
    _login_cache["checked_at"] = time.monotonic()
    _login_cache["ok"] = status == "success"

def _invalidate_login_cache() -> None:
    _login_cache["ok"] = False
    _login_cache["checked_at"] = 0.0

def _friendly_error(e: Exception, action: str) -> str:
    """Map common Instagram errors to actionable messages.

    Also arms a global pause window when Instagram reports rate limiting or
    spam feedback, so later write actions fail fast instead of hammering the API.
    """
    global _ACTION_LOCK_UNTIL
    msg = str(e)
    low = msg.lower()

    rate_limited = False
    try:
        from instagrapi.exceptions import PleaseWaitFewMinutes, RateLimitError
        rate_limited = isinstance(e, (PleaseWaitFewMinutes, RateLimitError))
    except Exception:
        pass

    if rate_limited or "wait a few minutes" in low or "rate limit" in low or "too many requests" in low:
        pause = _cfg_float("INSTAGRAM_MCP_RATE_LIMIT_PAUSE", 900.0)
        _ACTION_LOCK_UNTIL = time.monotonic() + pause
        return (f"Instagram rate-limited this action. Pausing write actions for ~{int(pause)}s "
                f"(INSTAGRAM_MCP_RATE_LIMIT_PAUSE). Original error: {msg}")

    if "feedback_required" in low or "action blocked" in low or "try again later" in low:
        pause = _cfg_float("INSTAGRAM_MCP_RATE_LIMIT_PAUSE", 900.0)
        _ACTION_LOCK_UNTIL = time.monotonic() + pause
        return (f"Instagram blocked this action (spam protection triggered). "
                f"Pausing write actions for ~{int(pause)}s. Original error: {msg}")

    if "commenting disabled" in low or "comments are disabled" in low:
        return "Comments are disabled on that post."

    if "login_required" in low or "login required" in low or "not logged in" in low:
        return ("Not logged in (or the session expired). Re-run instagram_login_with_sessionid "
                "or instagram_login_with_credentials.")

    return f"Error while {action}: {msg}"

def _build_usertags(usernames_csv: Optional[str]):
    """
    Convert a comma-separated string of @usernames into Usertag objects.
    Positions are distributed evenly across the image.
    """
    if not usernames_csv:
        return []
    from instagrapi.types import Usertag
    names = [u.strip().lstrip("@") for u in usernames_csv.split(",") if u.strip()]
    tags = []
    total = len(names)
    for i, name in enumerate(names):
        try:
            uid = ig.cl.user_id_from_username(name)
            user_info = ig.cl.user_info(uid)
            # Spread tags across the image horizontally
            x = round((i + 1) / (total + 1), 2)
            y = 0.5
            tags.append(Usertag(user=user_info, x=x, y=y))
        except Exception:
            pass  # Skip invalid usernames silently
    return tags

# ─────────────────────────────────────────────────────────────────────────────
# IMAGE / MEDIA SOURCE RESOLUTION
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_image_for_upload(path: Path):
    """Normalize a local image to JPEG so Instagram accepts it reliably.

    Handles PNG/WebP/BMP/TIFF (including transparency) and oversized images.
    Returns (path_str, temp_created).
    """
    from PIL import Image

    max_side = _cfg_int("INSTAGRAM_MCP_MAX_IMAGE_SIDE", 1440)
    max_bytes = _cfg_int("INSTAGRAM_MCP_MAX_IMAGE_BYTES", 8 * 1024 * 1024)

    with Image.open(path) as im:
        im.load()
        suffix = path.suffix.lower()
        needs_convert = suffix not in (".jpg", ".jpeg") or im.mode not in ("RGB", "L")
        needs_resize = max(im.size) > max_side
        size_ok = path.stat().st_size <= max_bytes
        if not needs_convert and not needs_resize and size_ok:
            return str(path), False

        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            background = Image.new("RGB", im.size, (255, 255, 255))
            background.paste(im, mask=im.split()[-1])
            im = background
        elif im.mode != "RGB":
            im = im.convert("RGB")

        if needs_resize:
            ratio = max_side / float(max(im.size))
            new_size = (max(1, int(im.width * ratio)), max(1, int(im.height * ratio)))
            im = im.resize(new_size, Image.LANCZOS)

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        quality = 95
        while True:
            im.save(tmp.name, format="JPEG", quality=quality, optimize=True)
            if os.path.getsize(tmp.name) <= max_bytes or quality <= 70:
                break
            quality -= 10
        return tmp.name, True


# Feed posts accept 1.91:1 (landscape) … 4:5 (portrait); anything outside that
# window is cropped by Instagram, so we crop/scale locally and keep full quality.
_FEED_RATIOS = {"square": 1.0, "portrait": 4 / 5, "landscape": 1.91}
_FEED_MIN_RATIO = 4 / 5
_FEED_MAX_RATIO = 1.91
_FEED_MAX_WIDTH = 1080


def _feed_info(original, final, mode, cropped, resized) -> dict:
    return {
        "aspect_mode": mode,
        "original_px": f"{original[0]}x{original[1]}",
        "final_px": f"{final[0]}x{final[1]}",
        "ratio": round(final[0] / float(final[1] or 1), 3),
        "cropped_to_instagram_frame": cropped,
        "resized": resized,
    }


def _prepare_feed_image(path: Path, aspect: str = "auto"):
    """Normalise a feed image to an Instagram-valid ratio/size.

    aspect:
      "auto"      keep the ratio when it is inside 4:5 … 1.91:1, otherwise centre-crop
                  to the nearest allowed edge
      "square"    1:1 (1080x1080)
      "portrait"  4:5 (1080x1350 — the tall feed posts Instagram's own app produces)
      "landscape" 1.91:1 (1080x565)
      "keep"      leave the ratio alone (Instagram may crop it for you)

    Returns (path_str, temp_created, info). Photos are also EXIF-rotated so phone
    pictures are not uploaded sideways.
    """
    from PIL import Image, ImageOps

    mode = str(aspect or "auto").strip().lower() or "auto"
    if mode not in ("auto", "keep", *_FEED_RATIOS):
        mode = "auto"

    max_side = _cfg_int("INSTAGRAM_MCP_MAX_IMAGE_SIDE", 1440)
    max_bytes = _cfg_int("INSTAGRAM_MCP_MAX_IMAGE_BYTES", 8 * 1024 * 1024)

    with Image.open(path) as opened:
        im = ImageOps.exif_transpose(opened)
        im.load()
        original_size = im.size

        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            im = background
        elif im.mode != "RGB":
            im = im.convert("RGB")

        ratio = im.width / float(im.height or 1)
        target = None
        if mode in _FEED_RATIOS:
            target = _FEED_RATIOS[mode]
        elif mode == "auto" and (ratio > _FEED_MAX_RATIO or ratio < _FEED_MIN_RATIO):
            target = _FEED_MAX_RATIO if ratio > _FEED_MAX_RATIO else _FEED_MIN_RATIO

        cropped = False
        if target:
            new_w, new_h = im.width, im.height
            if ratio > target:
                new_w = max(1, int(round(im.height * target)))
            elif ratio < target:
                new_h = max(1, int(round(im.width / target)))
            if (new_w, new_h) != im.size:
                left = (im.width - new_w) // 2
                top = (im.height - new_h) // 2
                im = im.crop((left, top, left + new_w, top + new_h))
                cropped = True

        resized = False
        if im.width > _FEED_MAX_WIDTH or max(im.size) > max_side:
            scale = min(_FEED_MAX_WIDTH / float(im.width), max_side / float(max(im.size)))
            if scale < 1:
                im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                               Image.LANCZOS)
                resized = True

        final_size = im.size
        info = _feed_info(original_size, final_size, mode, cropped, resized)

    already_jpeg = path.suffix.lower() in (".jpg", ".jpeg")
    if not cropped and not resized and already_jpeg:
        try:
            if path.stat().st_size <= max_bytes:
                return str(path), False, info
        except OSError:
            pass

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp.close()
    quality = 92
    while True:
        im.save(tmp.name, format="JPEG", quality=quality, optimize=True)
        if os.path.getsize(tmp.name) <= max_bytes or quality <= 70:
            break
        quality -= 10
    return tmp.name, True, info

def _resolve_image_source(path_or_url: str):
    """Resolve a local path, file:// URI, or http(s) URL to an uploadable local file.

    Returns (local_path, needs_cleanup). Local JPG/PNG/WebP images are validated
    and normalised to JPEG for maximum Instagram compatibility.
    """
    raw = (path_or_url or "").strip().strip('"').strip("'")
    if not raw:
        latest = _find_in_inbox("latest")
        if latest is None:
            raise ValueError(
                "No image was provided. Pass an absolute file path, an http(s) URL, "
                "base64 / data:image image data, or drop the image into "
                f"{_inbox_dir()} and pass 'latest'."
            )
        raw = str(latest)

    if raw.startswith("data:") or _looks_like_base64(raw):
        try:
            return _decode_image_data(raw), True
        except ValueError:
            if raw.startswith("data:"):
                raise
            # not actually image data — fall through and treat it as a path
    if raw.lower() in ("latest", "newest", "last", "recent"):
        hit = _find_in_inbox(raw)
        if hit:
            raw = str(hit)

    if raw.startswith(("http://", "https://")):
        return _download_if_url(raw, ".jpg"), True

    if raw.startswith("file://"):
        raw = unquote(urlparse(raw).path)
        if re.match(r"^/[A-Za-z]:", raw):  # Windows: /C:/path -> C:/path
            raw = raw[1:]

    local = os.path.expandvars(os.path.expanduser(raw))
    candidate = Path(local)
    if not candidate.is_file():
        inbox_hit = _find_in_inbox(raw)
        if inbox_hit:
            candidate = inbox_hit
        else:
            upload_hint = _inbox_url()
            raise FileNotFoundError(
                f"Local image not found: '{local}'. Four ways to give the server an image:\n"
                f"  1) absolute path  (e.g. C:\\Users\\you\\Pictures\\image.png)\n"
                f"  2) direct http(s) image URL\n"
                f"  3) base64 / data:image data pasted straight into the chat\n"
                f"  4) drop the file into the inbox and pass its name or 'latest':\n"
                f"     {_inbox_dir()}\n"
                f"     (scripts/save_image.py puts a clipboard image there for you)\n"
                + (f"  or open the upload page in any browser: {upload_hint}\n" if upload_hint else "")
            )
    try:
        return _normalize_image_for_upload(candidate)
    except Exception as e:
        raise ValueError(
            f"Could not read image '{candidate}': {e}. Supported formats: JPEG, PNG, WebP, BMP, TIFF."
        )

def _search_locations_by_name(location_name: str):
    """Search locations by name across instagrapi versions.

    instagrapi 3.x: location_search_name(name)
    instagrapi 2.x: location_search(name, lat=None, lng=None)
    """
    try:
        return ig.cl.location_search_name(location_name)
    except AttributeError:
        pass
    except Exception:
        return []
    try:
        return ig.cl.location_search(location_name)
    except Exception:
        return []

def _get_location(location_name: Optional[str]):
    """Resolve a location name to the first matching Location object."""
    if not location_name:
        return None
    results = _search_locations_by_name(location_name)
    return results[0] if results else None

def _fmt_user(u) -> dict:
    return {
        "pk": str(u.pk),
        "username": u.username,
        "full_name": u.full_name,
        "is_private": u.is_private,
        "is_verified": u.is_verified,
    }

def _fmt_media(m) -> dict:
    return {
        "id": str(m.pk),
        "code": m.code,
        "url": f"https://www.instagram.com/p/{m.code}/",
        "type": m.media_type,
        "product_type": getattr(m, "product_type", "") or "",
        "caption": (m.caption_text or "")[:200],
        "like_count": m.like_count,
        "comment_count": m.comment_count,
        "taken_at": str(m.taken_at),
        "user": m.user.username if m.user else None,
    }

def _build_caption(caption: Optional[str], hashtags: Optional[str], mentions: Optional[str]) -> str:
    """Append comma-separated mentions and hashtags to a caption."""
    full_caption = caption or ""
    if mentions:
        mention_str = " ".join([
            m.strip() if m.strip().startswith("@") else f"@{m.strip()}"
            for m in mentions.split(",") if m.strip()
        ])
        full_caption = f"{full_caption}\n\n{mention_str}".strip()
    if hashtags:
        tag_str = " ".join([
            h.strip() if h.strip().startswith("#") else f"#{h.strip()}"
            for h in hashtags.split(",") if h.strip()
        ])
        full_caption = f"{full_caption}\n\n{tag_str}".strip()
    return full_caption

def _fmt_comment(c) -> dict:
    """Format a Comment object for tool output (comment_id is reply-ready)."""
    data = {
        "comment_id": str(c.pk),
        "username": c.user.username if getattr(c, "user", None) else None,
        "text": c.text,
        "like_count": getattr(c, "like_count", 0),
        "created_at": str(c.created_at_utc) if getattr(c, "created_at_utc", None) else None,
    }
    replied_to = getattr(c, "replied_to_comment_id", None)
    if replied_to:
        data["replied_to_comment_id"] = str(replied_to)
    return data

def _fetch_comments_upto(media_id: str, count: int):
    """Fetch up to `count` top-level comments using the paginated chunk API."""
    collected: List = []
    cursor = None
    while len(collected) < count:
        chunk_size = min(50, count - len(collected))
        try:
            if cursor:
                items, cursor = ig.cl.media_comments_chunk(media_id, max_amount=chunk_size, min_id=cursor)
            else:
                items, cursor = ig.cl.media_comments_chunk(media_id, max_amount=chunk_size)
        except (AttributeError, TypeError):
            return ig.cl.media_comments(media_id, count)  # signature differs by version
        if not items:
            break
        collected.extend(items)
        if not cursor:
            break
    return collected[:count]

def _find_comment_by_username(media_id: str, username: str,
                              text_contains: Optional[str] = None,
                              prefer: str = "latest", max_scan: int = 150):
    """Find one comment by a username on a media item.

    Returns (comment, scanned_count) or (None, scanned_count). Scans the
    paginated comment chunks and stops early once a match is found (unless
    prefer="likes", which scans up to max_scan to compare like counts).
    """
    target = username.strip().lstrip("@").lower()
    needle = (text_contains or "").lower() or None
    scanned = 0
    cursor = None
    matches: List = []
    scan_all = str(prefer).lower() == "likes"
    while scanned < max_scan:
        chunk_size = min(50, max_scan - scanned)
        try:
            if cursor:
                items, cursor = ig.cl.media_comments_chunk(media_id, max_amount=chunk_size, min_id=cursor)
            else:
                items, cursor = ig.cl.media_comments_chunk(media_id, max_amount=chunk_size)
        except (AttributeError, TypeError):
            items, cursor = ig.cl.media_comments(media_id, max_scan), None
        if not items:
            break
        scanned += len(items)
        for c in items:
            user = getattr(c, "user", None)
            if not user or (user.username or "").lower() != target:
                continue
            if needle and needle not in (c.text or "").lower():
                continue
            matches.append(c)
        if matches and not scan_all:
            break
        if not cursor:
            break
    if not matches:
        return None, scanned
    if scan_all:
        matches.sort(key=lambda c: getattr(c, "like_count", 0) or 0, reverse=True)
    else:
        def _ts(c):
            t = getattr(c, "created_at_utc", None)
            try:
                return t.timestamp()
            except Exception:
                return 0
        matches.sort(key=_ts, reverse=True)
    return matches[0], scanned

# ─────────────────────────────────────────────────────────────────────────────
# DESTRUCTIVE ACTIONS: preview → user approval → confirm
# ─────────────────────────────────────────────────────────────────────────────

_PENDING_CONFIRMATIONS = {}  # (action, target) -> (monotonic_ts, details)
_CONFIRM_TTL = 600.0         # a preview stays valid for 10 minutes

def _deletion_preview(action: str, target: str, details: dict) -> str:
    """Register a pending confirmation and return the preview payload."""
    _PENDING_CONFIRMATIONS[(action, str(target))] = (time.monotonic(), details)
    return str({
        "status": "preview",
        "action": action,
        "requires_confirmation": True,
        "target": str(target),
        "details": details,
        "ask_user": ("Show these details to the user and ask for explicit approval. "
                     "Only if the user approves, call this tool again with confirm=True."),
    })

def _consume_confirmation(action: str, target: str):
    """Consume a pending confirmation. Returns (ok, error_message)."""
    key = (action, str(target))
    rec = _PENDING_CONFIRMATIONS.pop(key, None)
    if not rec:
        return False, ("Refused: no preview was shown for this target. Call again with confirm=False "
                       "first, show the details to the user, and get their approval before deleting.")
    ts, _ = rec
    if time.monotonic() - ts > _CONFIRM_TTL:
        return False, (f"Refused: the earlier preview expired ({int(_CONFIRM_TTL)}s). "
                       f"Call again with confirm=False and get fresh approval.")
    return True, ""

def _media_id_from_input(media_id_or_url: str) -> str:
    """Accept a raw media ID, a full media_id, or any Instagram post/reel URL.

    URLs are resolved with instagrapi's own parser first (handles /p/, /reel/,
    /reels/, /tv/, share links and query strings such as ?igsh=...).
    """
    value = (media_id_or_url or "").strip()
    if value.startswith(("http://", "https://")) or "instagram.com" in value:
        try:
            return ig.cl.media_id(ig.cl.media_pk_from_url(value))
        except Exception:
            pass
        match = re.search(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", value)
        if match:
            try:
                return ig.cl.media_id(ig.cl.media_pk_from_code(match.group(1)))
            except Exception as e:
                raise ValueError(f"Could not resolve Instagram URL '{value}': {e}")
        raise ValueError(
            f"Unrecognized Instagram URL: '{value}'. Pass a post/reel link or a numeric media ID."
        )
    return value


# ─────────────────────────────────────────────────────────────────────────────
# 1. AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_login_with_credentials(username: str, password: str) -> str:
    """
    🔴 HIGH-RISK (bot detection): every password login looks like a NEW DEVICE to
    Instagram — repeated logins trigger challenges and automation warnings.
    Prefer the saved session or instagram_login_with_sessionid.

    Log in using username + password.
    Returns 'needs_2fa' or 'needs_challenge' if verification is required
    (then call instagram_complete_2fa / instagram_complete_challenge).
    """
    result = ig.login_with_credentials(username, password)
    _note_login_result(result)
    return str(result)

@mcp.tool()
def instagram_login_with_sessionid(username: str, session_id: str) -> str:
    """
    Log in via browser sessionid cookie — most reliable, bypasses 2FA.
    Get it: Instagram.com → F12 → Application → Cookies → copy 'sessionid'.
    """
    result = ig.login_with_sessionid(username, session_id)
    _note_login_result(result)
    return str(result)

@mcp.tool()
def instagram_complete_2fa(code: str) -> str:
    """Submit the 2FA authenticator code after login returned 'needs_2fa'."""
    result = ig.complete_2fa(code)
    _note_login_result(result)
    return str(result)

@mcp.tool()
def instagram_complete_challenge(code: str) -> str:
    """Submit the email/SMS challenge code after login returned 'needs_challenge'."""
    result = ig.complete_challenge(code)
    _note_login_result(result)
    return str(result)

@mcp.tool()
def instagram_get_login_status() -> str:
    """Check if the server is authenticated and which account is active."""
    return str(ig.get_login_status())

@mcp.tool()
def instagram_logout() -> str:
    """
    Log out and delete the saved session file from disk (use when you want this machine to
    forget the account). Log back in with instagram_login_with_sessionid.
    """
    result = ig.logout()
    _invalidate_login_cache()
    return str(result)


# ─────────────────────────────────────────────────────────────────────────────
# 2. PROFILE
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_get_profile(username: Optional[str] = None) -> str:
    """
    Get full profile details for the logged-in account or any target username.
    Includes bio, follower/following counts, post count, website, verification status.
    """
    if err := _require_login(): return err
    try:
        target = username or ig.cl.username
        u = ig.cl.user_info_by_username(target)
        return str({
            "pk": str(u.pk),
            "username": u.username,
            "full_name": u.full_name,
            "biography": u.biography,
            "external_url": str(u.external_url) if u.external_url else None,
            "follower_count": u.follower_count,
            "following_count": u.following_count,
            "media_count": u.media_count,
            "is_private": u.is_private,
            "is_verified": u.is_verified,
            "is_business": u.is_business,
            "profile_pic_url": str(u.profile_pic_url),
            "category": u.category,
        })
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def instagram_edit_profile(full_name: Optional[str] = None,
                             biography: Optional[str] = None,
                             external_url: Optional[str] = None) -> str:
    """
    Edit the logged-in account's profile.
    - full_name: Display name
    - biography: Bio text (supports emojis, newlines, @mentions, #hashtags)
    - external_url: Website link in bio
    Only fields you provide are updated.
    """
    if err := _require_login(): return err
    try:
        u = ig.cl.user_info(ig.cl.user_id)
        ig.cl.account_edit(
            full_name=full_name or u.full_name,
            biography=biography if biography is not None else u.biography,
            external_url=external_url or str(u.external_url or ""),
        )
        return "Profile updated successfully."
    except Exception as e:
        return f"Error updating profile: {e}"

@mcp.tool()
def instagram_change_profile_picture(image_path_or_url: str) -> str:
    """Change the profile picture. Accepts local file path or image URL."""
    if err := _require_login(): return err
    local = None
    try:
        local = _download_if_url(image_path_or_url, ".jpg")
        ig.cl.account_change_picture(local)
        return "Profile picture changed successfully."
    except Exception as e:
        return f"Error: {e}"
    finally:
        if local: _cleanup(local, image_path_or_url)


# ─────────────────────────────────────────────────────────────────────────────
# 3. FULL POST CREATION & MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_post_photo(
    image_path_or_url: Annotated[str, Field(description=(
        "Image source: absolute file path, http(s) image URL, base64/data:image data, or an "
        "inbox name such as 'latest'. Use instagram_upload_image first when the picture "
        "arrived in the chat."))],
    caption: Annotated[str, Field(description="Caption text (write it for the user; hashtags go in their own parameter)")],
    hashtags: Annotated[Optional[str], Field(description="Comma-separated hashtags to append, e.g. '#ai, #art'")] = None,
    mentions: Annotated[Optional[str], Field(description="Comma-separated @usernames to mention in the caption")] = None,
    tag_users_in_photo: Annotated[Optional[str], Field(description="Comma-separated @usernames to physically TAG inside the photo")] = None,
    location_name: Annotated[Optional[str], Field(description="Location tag, e.g. 'Mumbai, India'")] = None,
    alt_text: Annotated[Optional[str], Field(description="Accessibility description of the picture (best effort)")] = None,
    disable_comments: Annotated[bool, Field(description="True = comments off for this post")] = False,
    dry_run: Annotated[bool, Field(description="True = preview the draft WITHOUT posting — always do this first and show it to the user")] = False,
    aspect: Annotated[str, Field(description="Framing: 'auto' (default), 'portrait' 4:5, 'square' 1:1, 'landscape' 1.91:1, 'keep'")] = "auto",
) -> str:
    """
    Post a photo to the Instagram feed with full caption control.

    ASPECT (how the picture is framed in the feed):
      "auto" (default) — keep the ratio when it is inside 4:5 … 1.91:1, otherwise
                         centre-crop to the nearest allowed edge
      "portrait"       — 4:5 tall feed post (1080x1350), like the big art accounts
      "square"         — classic 1:1 (1080x1080)
      "landscape"      — 1.91:1 wide
      "keep"           — upload untouched (Instagram may crop it itself)
    Four ways to supply the image: absolute path, http(s) URL, pasted base64 /
    data:image data, or a file in the inbox folder (its name or "latest").
    Use instagram_inspect_image first when the framing matters.

    IMAGE SOURCE: pass an ABSOLUTE LOCAL FILE PATH (e.g. "C:\\Users\\me\\Pictures\\art.png" on
    Windows, "/home/me/pictures/art.png" on Linux/macOS/Termux)
    — no public URL is required. A direct http(s) image URL also works. Local
    JPG/PNG/WebP files are automatically normalised to JPEG (and resized/cropped
    when needed) for maximum upload compatibility. Besides a path or URL you can
    also pass pasted base64 / data:image data, or a file dropped into the inbox
    folder (its name, or "latest" — scripts/save_image.py puts your clipboard
    image there). If the user asks you to write the caption, compose it yourself
    before calling this tool.

    Parameters:
    - image_path_or_url: Absolute local file path or direct image URL
    - caption: Main post caption/description text
    - hashtags: Comma-separated hashtags to append (e.g. "#python, #ai")
    - mentions: Comma-separated @usernames to mention in the caption
    - tag_users_in_photo: Comma-separated @usernames to physically TAG in the image
    - location_name: Location to tag (e.g. "New York, USA")
    - alt_text: Accessibility alt text (best effort; Instagram may ignore it)
    - disable_comments: Set True to disable comments on this post
    - dry_run: Set True to preview the final caption (and validate/normalise the
      image) WITHOUT posting — use this for the draft → approval → publish flow

    WORKFLOW: when the user provides an image and wants a caption, call this with
    dry_run=True and show the draft; publish only after the user approves it.
    """
    if err := _require_login(): return err
    if not dry_run:
        pause = _pacing_error("post")
        if pause: return pause
    local = None
    cleanup_local = False
    prepared = None
    prepared_cleanup = False
    try:
        local, cleanup_local = _resolve_image_source(image_path_or_url)
        prepared, prepared_cleanup, image_info = _prepare_feed_image(Path(local), aspect)
        full_caption = _build_caption(caption, hashtags, mentions)
        if dry_run:
            return str({
                "status": "preview",
                "dry_run": True,
                "image": image_info,
                "caption_preview": full_caption,
                "hashtags_param": hashtags,
                "mentions_param": mentions,
                "location_name": location_name,
                "tag_users_in_photo": tag_users_in_photo,
                "comments_disabled": disable_comments,
                "image_normalised_to_jpeg": cleanup_local,
                "next_step": ("Show this draft to the user (caption + hashtags). After they approve it, "
                              "call instagram_post_photo again with the same parameters and dry_run=False."),
            })
        dedupe = _dedupe_guard("post", "feed", f"{image_path_or_url}|{full_caption}")
        if dedupe:
            return dedupe
        waited = _pace_action("post")

        location = _get_location(location_name)
        usertags = _build_usertags(tag_users_in_photo)

        upload_kwargs = {"location": location, "usertags": usertags}
        if alt_text and _supports_kwarg(ig.cl.photo_upload, "extra_data"):
            upload_kwargs["extra_data"] = {"accessibility_caption": alt_text}
        media = ig.cl.photo_upload(prepared, full_caption, **upload_kwargs)

        if disable_comments:
            try:
                ig.cl.private_request(
                    f"media/{media.pk}/disable_comments/",
                    data=ig.cl.with_action_data({})
                )
            except Exception:
                pass  # Not critical — the post is already live

        return str({
            "status": "success",
            "media_id": str(media.pk),
            "url": f"https://www.instagram.com/p/{media.code}/",
            "image": image_info,
            "caption_preview": full_caption[:120],
            "location": location_name,
            "tagged_users": tag_users_in_photo,
            "comments_disabled": disable_comments,
            "alt_text_sent": bool(alt_text),
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, "posting the photo")
    finally:
        if prepared and prepared_cleanup and prepared != local:
            _remove_file(prepared)
        if local and cleanup_local:
            _remove_file(local)


@mcp.tool()
def instagram_upload_image(
    image_source: Annotated[str, Field(description=(
        "base64 or data:image data pasted from the chat (small images), an absolute file "
        "path, an http(s) URL, or 'latest' for the newest inbox image"))],
    filename: Annotated[str, Field(description="Optional name to save it as inside the inbox (sanitised, never overwrites)")] = "",
) -> str:
    """
    🟢 SAFE — local machine only: works without login and does NOT touch Instagram.

    Step 1 of the "image from chat" flow — park the picture on this computer so the
    posting tools can use it. Accepts:
      - base64 or `data:image/png;base64,…` data (great for screenshots/small images —
        keep them under ~300 KB, they have to travel through the chat as text)
      - an absolute file path, an http(s) image URL, or "latest" (newest inbox image)
    Saves a sanitised copy into the inbox folder and returns the exact path + size.

    Step 2 is posting, e.g.
    instagram_post_photo(image_path_or_url="latest", caption=..., aspect="portrait")
    (or instagram_post_photo_story / instagram_send_dm_photo).

    BIG photos (multi-MB camera shots) cannot be text-encoded in a chat — for those use
    the browser inbox page: the same domain you reach this server through, with /mcp
    replaced by /inbox (instagram_inbox_status reports the exact link), or
    scripts/save_image.py / scripts/watch_clipboard.py on this machine instead.
    """
    local = None
    cleanup = False
    try:
        local, cleanup = _resolve_image_source(image_source)
        size = os.path.getsize(local)
        limit = _cfg_int("INSTAGRAM_MCP_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)
        if size > limit:
            return (f"Error: that image is {size / 1048576:.1f} MB and the inbox accepts up to "
                    f"{limit // 1048576} MB.")
        target = _save_to_inbox(local, filename)
        dims = {}
        try:
            from PIL import Image
            with Image.open(target) as im:
                dims = {"px": f"{im.width}x{im.height}",
                        "ratio": round(im.width / float(im.height or 1), 3)}
        except Exception:
            dims = {}
        return str({
            "status": "saved_to_inbox",
            "saved_path": str(target),
            "filename": target.name,
            "bytes": size,
            "image": dims,
            "inbox_folder": str(_inbox_dir()),
            "next_step": ('call instagram_post_photo(image_path_or_url="latest", caption=..., '
                          'aspect="auto"|"portrait"|"square"|"landscape", dry_run=True) to preview, '
                          "then again with dry_run=False to publish"),
        })
    except Exception as e:
        return _friendly_error(e, "saving the image into the inbox")
    finally:
        if local and cleanup:
            _remove_file(local)


@mcp.tool()
def instagram_inbox_status(limit: int = 10) -> str:
    """
    🟢 SAFE — what images are waiting on this machine before posting?

    Lists the newest inbox files (name, size, modified time), which one "latest" points
    at, the folder path and the browser upload page. Call this when the user says they
    uploaded/sent a photo, to confirm it arrived and post the right one.
    """
    try:
        inbox = _inbox_dir()
        files = [p for p in inbox.rglob("*") if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        rows = [{
            "name": path.name,
            "path": str(path),
            "bytes": path.stat().st_size,
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime)),
        } for path in files[:max(1, int(limit))]]
        return str({
            "inbox_folder": str(inbox),
            "upload_page": _inbox_url() or (
                "(start scripts/serve.py for a browser upload page you can open from any device)"),
            "count": len(files),
            "latest": rows[0]["name"] if rows else None,
            "files": rows,
        })
    except Exception as e:
        return _friendly_error(e, "reading the inbox")


@mcp.tool()
def instagram_inspect_image(
    image_path_or_url: Annotated[str, Field(description="Local path, URL, pasted base64/data:image, inbox name or 'latest'")],
    aspect: Annotated[str, Field(description="Framing to preview: auto / portrait / square / landscape / keep")] = "auto",
) -> str:
    """
    🟢 SAFE — works without login, posts nothing.

    Check an image before posting: where it resolved from (path / URL / pasted
    base64 / inbox), its pixel size and ratio, and exactly what each aspect mode
    would upload ("auto" | "portrait" | "square" | "landscape" | "keep").
    """
    local = None
    cleanup_local = False
    try:
        local, cleanup_local = _resolve_image_source(image_path_or_url)
        previews = {}
        for mode in ("auto", "portrait", "square", "landscape", "keep"):
            path, is_temp, info = _prepare_feed_image(Path(local), mode)
            previews[mode] = info
            if is_temp:
                _remove_file(path)
        chosen = str(aspect or "auto").strip().lower()
        return str({
            "resolved_to": local,
            "downloaded_or_decoded_temp": cleanup_local,
            "would_upload_now": previews.get(chosen, previews["auto"]),
            "all_modes": previews,
        })
    except Exception as e:
        return _friendly_error(e, "inspecting the image")
    finally:
        if local and cleanup_local:
            _remove_file(local)


@mcp.tool()
def instagram_post_album(
    image_paths_or_urls: Annotated[List[str], Field(description=(
        "2–10 items: local paths, http(s) URLs, base64/data:image strings, or inbox "
        "names/'latest' — mixed sources are fine"))],
    caption: Annotated[str, Field(description="Caption text for the carousel")],
    hashtags: Annotated[Optional[str], Field(description="Comma-separated hashtags to append")] = None,
    mentions: Annotated[Optional[str], Field(description="Comma-separated @usernames to mention in the caption")] = None,
    location_name: Annotated[Optional[str], Field(description="Location tag, e.g. 'Paris, France'")] = None,
    disable_comments: Annotated[bool, Field(description="True = comments off for this carousel")] = False,
    aspect: Annotated[str, Field(description="Framing applied to every photo: auto/portrait/square/landscape/keep")] = "auto",
) -> str:
    """
    Post a carousel album (2–10 photos/videos) with full caption control.

    Parameters:
    - image_paths_or_urls: List of sources — local paths, URLs, base64/data:image
      strings or inbox names (up to 10 items)
    - aspect: framing for every photo: "auto" (default), "portrait" (4:5),
      "square" (1:1), "landscape" (1.91:1) or "keep"
    - caption: Main caption text
    - hashtags: Comma-separated hashtags (e.g. "#travel, #photography")
    - mentions: Comma-separated @mentions (e.g. "@friend1, @brand")
    - location_name: Location tag string
    - disable_comments: Set True to disable comments
    """
    if err := _require_login(): return err
    pause = _pacing_error("post")
    if pause: return pause
    if not 2 <= len(image_paths_or_urls) <= 10:
        return "Error: album posts need between 2 and 10 photos/videos."
    locals_ = []
    try:
        full_caption = _build_caption(caption, hashtags, mentions)
        dedupe = _dedupe_guard("post-album", "feed", f"{'|'.join(image_paths_or_urls)}|{full_caption}")
        if dedupe:
            return dedupe
        waited = _pace_action("post")

        paths = []
        for item in image_paths_or_urls[:10]:
            local, cleanup_item = _resolve_image_source(item)
            prepared_item, prepared_cleanup, _info = _prepare_feed_image(Path(local), aspect)
            locals_.append((local, item))
            if prepared_cleanup and prepared_item != local:
                locals_.append((prepared_item, "data:"))  # temp file we created
            paths.append(Path(prepared_item))

        location = _get_location(location_name)
        media = ig.cl.album_upload(paths, full_caption, location=location)

        if disable_comments:
            try:
                ig.cl.private_request(
                    f"media/{media.pk}/disable_comments/",
                    data=ig.cl.with_action_data({})
                )
            except Exception:
                pass

        return str({
            "status": "success",
            "media_id": str(media.pk),
            "url": f"https://www.instagram.com/p/{media.code}/",
            "items": len(paths),
            "caption_preview": full_caption[:100],
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, "posting the album")
    finally:
        for local, orig in locals_:
            _cleanup(local, orig)


@mcp.tool()
def instagram_post_video(
    video_path_or_url: str,
    caption: str,
    hashtags: Optional[str] = None,
    mentions: Optional[str] = None,
    location_name: Optional[str] = None,
    thumbnail_path_or_url: Optional[str] = None,
    alt_text: Optional[str] = None,
    disable_comments: bool = False,
) -> str:
    """
    Post a video to the feed with full caption control.

    Parameters:
    - video_path_or_url: Local path or URL to MP4 file
    - caption: Caption text
    - hashtags: Comma-separated hashtags
    - mentions: Comma-separated @mentions
    - location_name: Location to tag
    - thumbnail_path_or_url: Custom thumbnail image (optional)
    - alt_text: Accessibility description for the video
    - disable_comments: Set True to disable comments
    """
    if err := _require_login(): return err
    pause = _pacing_error("post")
    if pause: return pause
    local_v = local_t = None
    try:
        full_caption = _build_caption(caption, hashtags, mentions)
        dedupe = _dedupe_guard("post-video", "feed",
                               f"{video_path_or_url}|{full_caption}|{thumbnail_path_or_url}")
        if dedupe:
            return dedupe
        waited = _pace_action("post")

        local_v = _download_if_url(video_path_or_url, ".mp4")
        if thumbnail_path_or_url:
            local_t = _download_if_url(thumbnail_path_or_url, ".jpg")

        location = _get_location(location_name)
        upload_kwargs = {"thumbnail": local_t, "location": location}
        if alt_text and _supports_kwarg(ig.cl.video_upload, "extra_data"):
            upload_kwargs["extra_data"] = {"accessibility_caption": alt_text}
        media = ig.cl.video_upload(local_v, full_caption, **upload_kwargs)

        if disable_comments:
            try:
                ig.cl.private_request(
                    f"media/{media.pk}/disable_comments/",
                    data=ig.cl.with_action_data({})
                )
            except Exception:
                pass

        return str({
            "status": "success",
            "media_id": str(media.pk),
            "url": f"https://www.instagram.com/p/{media.code}/",
            "alt_text_sent": bool(alt_text),
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, "posting the video")
    finally:
        if local_v: _cleanup(local_v, video_path_or_url)
        if local_t and thumbnail_path_or_url: _cleanup(local_t, thumbnail_path_or_url)


@mcp.tool()
def instagram_post_reel(
    video_path_or_url: str,
    caption: str,
    hashtags: Optional[str] = None,
    mentions: Optional[str] = None,
    location_name: Optional[str] = None,
    disable_comments: bool = False,
) -> str:
    """
    Post a Reel with full caption control. Reels have the highest organic reach.

    Parameters:
    - video_path_or_url: Local path or URL to MP4 video
    - caption: Caption text
    - hashtags: Comma-separated hashtags (crucial for Reel discovery)
    - mentions: Comma-separated @mentions
    - location_name: Location tag
    - disable_comments: Set True to disable comments
    """
    if err := _require_login(): return err
    pause = _pacing_error("post")
    if pause: return pause
    local_v = None
    try:
        full_caption = _build_caption(caption, hashtags, mentions)
        dedupe = _dedupe_guard("post-reel", "feed", f"{video_path_or_url}|{full_caption}")
        if dedupe:
            return dedupe
        waited = _pace_action("post")

        local_v = _download_if_url(video_path_or_url, ".mp4")
        if video_path_or_url.startswith(("http://", "https://")):
            rejected = _reject_non_mp4(local_v)
            if rejected:
                return rejected
        location = _get_location(location_name)
        media = ig.cl.clip_upload(local_v, full_caption, location=location)

        if disable_comments:
            try:
                ig.cl.private_request(
                    f"media/{media.pk}/disable_comments/",
                    data=ig.cl.with_action_data({})
                )
            except Exception:
                pass

        return str({
            "status": "success",
            "media_id": str(media.pk),
            "url": f"https://www.instagram.com/reel/{media.code}/",
            "caption_preview": full_caption[:100],
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, "posting the Reel")
    finally:
        if local_v: _cleanup(local_v, video_path_or_url)


@mcp.tool()
def instagram_edit_post_caption(
    media_id_or_url: str,
    new_caption: str,
    hashtags: Optional[str] = None,
    mentions: Optional[str] = None,
) -> str:
    """
    Edit the caption of an existing post.

    Parameters:
    - media_id_or_url: Post media ID or full Instagram URL
    - new_caption: The new caption text (replaces the old one entirely)
    - hashtags: Hashtags to append to the new caption
    - mentions: @mentions to append to the new caption
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)

        full_caption = _build_caption(new_caption, hashtags, mentions)

        result = ig.cl.media_edit(mid, full_caption)
        return f"Caption updated successfully. New caption preview: '{full_caption[:100]}'"
    except Exception as e:
        return f"Error editing caption: {e}"


@mcp.tool()
def instagram_tag_users_in_post(media_id_or_url: str, usernames: str) -> str:
    """
    Tag one or more users physically IN a photo (people tags).
    NOTE: Instagram's API only supports setting usertags at upload time.
    Use the tag_users_in_photo parameter in instagram_post_photo/post_reel instead.
    This tool attempts a post-upload tag via the private endpoint.

    Parameters:
    - media_id_or_url: Post media ID or Instagram URL
    - usernames: Comma-separated @usernames to tag in the photo
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        usertags = _build_usertags(usernames)
        if not usertags:
            return "Error: Could not resolve any of the provided usernames."
        tagged = [ut.user.username for ut in usertags]
        try:
            media = ig.cl.media_info(mid)
            ig.cl.media_edit(mid, media.caption_text or "", usertags=usertags)
        except TypeError:
            # Fallback for builds without media_edit usertags support: send the
            # raw payload as JSON (Instagram expects {"in": [...]}).
            usertag_payload = json.dumps({
                "in": [{"user_id": str(ut.user.pk), "position": [ut.x, ut.y]} for ut in usertags]
            })
            ig.cl.private_request(
                f"media/{mid}/update_media/",
                data={**ig.cl.with_action_data({}), "usertags": usertag_payload},
            )
        return f"Tagged {len(tagged)} user(s): {', '.join(tagged)}."
    except Exception as e:
        return (_friendly_error(e, "tagging users") +
                " Tip: for guaranteed tags, use the tag_users_in_photo parameter when creating a new post.")


@mcp.tool()
def instagram_set_post_alt_text(media_id_or_url: str, alt_text: str) -> str:
    """
    Attempt to set accessibility alt text on an existing post via the private API.
    Alt text describes the image content for visually impaired users.

    Parameters:
    - media_id_or_url: Post media ID or full Instagram URL
    - alt_text: Text description of the image/video content
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        # Instagram private API endpoint for accessibility caption
        ig.cl.private_request(
            f"media/{mid}/update_media/",
            data={**ig.cl.with_action_data({}), "accessibility_caption": alt_text}
        )
        return (f"Alt text change requested: '{alt_text}'. Instagram does not reliably support "
                f"post-upload alt text — verify it in the app, or pass alt_text when posting.")
    except Exception as e:
        return _friendly_error(e, "setting alt text")


@mcp.tool()
def instagram_disable_comments(media_id_or_url: str) -> str:
    """
    Turn comments OFF for one of your posts (undo with instagram_enable_comments).
    Use it when a post is collecting spam or you want a comment-free drop.
    media_id_or_url accepts a post URL or a media id.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        ig.cl.private_request(
            f"media/{mid}/disable_comments/",
            data=ig.cl.with_action_data({})
        )
        return f"Comments disabled on post {mid}."
    except Exception as e:
        return f"Error disabling comments: {e}"


@mcp.tool()
def instagram_enable_comments(media_id_or_url: str) -> str:
    """
    Turn comments back ON for a post you disabled earlier (see instagram_disable_comments).
    media_id_or_url accepts a post URL or a media id.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        ig.cl.private_request(
            f"media/{mid}/enable_comments/",
            data=ig.cl.with_action_data({})
        )
        return f"Comments enabled on post {mid}."
    except Exception as e:
        return f"Error enabling comments: {e}"


@mcp.tool()
def instagram_archive_post(media_id_or_url: str) -> str:
    """
    Archive a post (hides it from your profile grid, but keeps it saved).
    Archived posts can be found in your Archive section.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        ig.cl.media_archive(mid)
        return f"Post {mid} archived successfully."
    except Exception as e:
        return f"Error archiving post: {e}"


@mcp.tool()
def instagram_unarchive_post(media_id_or_url: str) -> str:
    """
    Restore an archived post to your profile grid (the reverse of instagram_archive_post).
    List archived posts first with instagram_get_archived_posts.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        ig.cl.media_unarchive(mid)
        return f"Post {mid} unarchived successfully."
    except Exception as e:
        return f"Error unarchiving post: {e}"


@mcp.tool()
def instagram_pin_post(media_id_or_url: str) -> str:
    """
    Pin a post to the top of your profile grid.
    You can pin up to 3 posts on your profile.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        ig.cl.media_pin(mid)
        return f"Post {mid} pinned to profile."
    except Exception as e:
        return f"Error pinning post: {e}"


@mcp.tool()
def instagram_unpin_post(media_id_or_url: str) -> str:
    """Remove a pinned post from the top of your profile grid."""
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        ig.cl.media_unpin(mid)
        return f"Post {mid} unpinned."
    except Exception as e:
        return f"Error unpinning post: {e}"


@mcp.tool()
def instagram_delete_post(media_id_or_url: str, confirm: bool = False) -> str:
    """
    Permanently delete a post (cannot be undone).

    SAFETY FLOW: call first with confirm=False — the tool returns the post's URL,
    author and caption so you can show them to the user and ask for approval.
    Only after the user approves, call again with confirm=True (the preview stays
    valid for 10 minutes). confirm=True without a fresh preview is refused.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        if not confirm:
            m = ig.cl.media_info(mid)
            return _deletion_preview("delete_post", mid, {
                "url": f"https://www.instagram.com/p/{m.code}/",
                "author": m.user.username if m.user else None,
                "caption_preview": (m.caption_text or "")[:150],
                "like_count": m.like_count,
                "comment_count": m.comment_count,
                "taken_at": str(m.taken_at),
            })
        ok, msg = _consume_confirmation("delete_post", mid)
        if not ok:
            return msg
        ig.cl.media_delete(mid)
        return f"Deleted post {mid} permanently (user-approved)."
    except Exception as e:
        return _friendly_error(e, "deleting the post")


@mcp.tool()
def instagram_get_user_feed(username: Optional[str] = None, amount: int = 12) -> str:
    """Get recent posts from the logged-in account or any target username."""
    if err := _require_login(): return err
    try:
        target = username or ig.cl.username
        uid = ig.cl.user_id_from_username(target)
        medias = ig.cl.user_medias(uid, amount)
        return str([_fmt_media(m) for m in medias])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_timeline_feed(amount: int = 10) -> str:
    """Get the home timeline feed — posts from accounts you follow."""
    if err := _require_login(): return err
    try:
        feed = ig.cl.get_timeline_feed()
        items = feed.get("feed_items", [])
        results = []
        for item in items[:amount]:
            mi = item.get("media_or_ad", {})
            if mi:
                code = mi.get("code", "")
                cap = (mi.get("caption") or {}).get("text", "")
                results.append({
                    "url": f"https://www.instagram.com/p/{code}/",
                    "user": mi.get("user", {}).get("username", ""),
                    "caption": (cap or "")[:200],
                    "like_count": mi.get("like_count", 0),
                    "comment_count": mi.get("comment_count", 0),
                })
        return str(results)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_media_info(media_id_or_url: str) -> str:
    """
    Full details for any post/reel by URL or media id: caption, likes, comments, taken_at,
    owner, tagged users, resources. Use it before commenting, reposting or reporting numbers.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        m = ig.cl.media_info(mid)
        return str(_fmt_media(m))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_tagged_posts(username: Optional[str] = None, amount: int = 12) -> str:
    """
    Get posts where the logged-in account (or a target username) is tagged.
    """
    if err := _require_login(): return err
    try:
        target = username or ig.cl.username
        uid = ig.cl.user_id_from_username(target)
        medias = ig.cl.usertag_medias(uid, amount)
        return str([_fmt_media(m) for m in medias])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_saved_posts(amount: int = 20) -> str:
    """
    List the posts in your Saved collection (captions + urls), newest first.
    Add more with instagram_save_post or instagram_save_to_collection (named collections).
    """
    if err := _require_login(): return err
    try:
        # Any non-numeric collection name routes to the all-saved-posts endpoint
        # (feed/saved/posts/), which is what "All posts" means for saved media.
        medias = ig.cl.collection_medias("ALL_POSTS_AUTO_COLLECTION", amount=amount)
        return str([_fmt_media(m) for m in medias])
    except Exception as e:
        return _friendly_error(e, "fetching saved posts")


@mcp.tool()
def instagram_download_post(media_id_or_url: str, save_dir: Optional[str] = None) -> str:
    """
    Download a post's photo/video to local disk and return the saved path
    (use it to repost, archive, or feed the file into another tool such as
    instagram_post_photo or instagram_send_dm_photo).
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        dest = save_dir or os.path.join(os.path.expanduser("~"), "instagram_mcp_downloads")
        os.makedirs(dest, exist_ok=True)
        m = ig.cl.media_info(mid)
        if m.media_type == 2:
            path = ig.cl.video_download(mid, folder=dest)
        else:
            path = ig.cl.photo_download(mid, folder=dest)
        return f"Downloaded to: {path}"
    except Exception as e:
        return f"Error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. STORIES (WITH STICKERS)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_post_photo_story(
    image_path_or_url: str,
    caption: Optional[str] = None,
    mentions: Optional[str] = None,
    hashtags: Optional[str] = None,
    location_name: Optional[str] = None,
    link_url: Optional[str] = None,
) -> str:
    """
    Post a photo Story with optional caption and full sticker support.

    IMAGE SOURCE: an ABSOLUTE LOCAL FILE PATH works — no public URL required
    (JPG/PNG/WebP are normalised to JPEG automatically).

    Parameters:
    - image_path_or_url: Absolute local file path or image URL
    - caption: Optional story caption text
    - mentions: Comma-separated @usernames to add as mention stickers
    - hashtags: Comma-separated hashtags for hashtag stickers
    - location_name: Location sticker text
    - link_url: Link sticker URL (the swipe-up / link button on story)
    """
    if err := _require_login(): return err
    pause = _pacing_error("post")
    if pause: return pause
    local = None
    cleanup_local = False
    try:
        from instagrapi.types import StoryMention, StoryHashtag, StoryLocation, StoryLink, UserShort
        local, cleanup_local = _resolve_image_source(image_path_or_url)
        dedupe = _dedupe_guard("story", "story", f"{image_path_or_url}|{caption or ''}")
        if dedupe:
            return dedupe
        waited = _pace_action("post")

        story_mentions = []
        if mentions:
            for name in [m.strip().lstrip("@") for m in mentions.split(",") if m.strip()]:
                try:
                    uid = ig.cl.user_id_from_username(name)
                    user = ig.cl.user_info(uid)
                    story_mentions.append(StoryMention(user=user, x=0.5, y=0.5, width=0.5, height=0.1))
                except Exception:
                    pass

        story_hashtags = []
        if hashtags:
            for tag in [h.strip().lstrip("#") for h in hashtags.split(",") if h.strip()]:
                try:
                    hinfo = ig.cl.hashtag_info(tag)
                    story_hashtags.append(StoryHashtag(hashtag=hinfo, x=0.5, y=0.7, width=0.3, height=0.08))
                except Exception:
                    pass

        story_locations = []
        if location_name:
            loc = _get_location(location_name)
            if loc is not None:
                story_locations.append(StoryLocation(location=loc, x=0.5, y=0.85, width=0.4, height=0.08))

        story_links = []
        if link_url:
            story_links.append(StoryLink(webUri=link_url))

        m = ig.cl.photo_upload_to_story(
            local,
            caption or "",
            mentions=story_mentions,
            hashtags=story_hashtags,
            locations=story_locations,
            links=story_links,
        )
        return str({
            "status": "success",
            "media_id": str(m.pk),
            "stickers": {
                "mentions": [s.user.username for s in story_mentions],
                "hashtags": [s.hashtag.name for s in story_hashtags],
                "location": location_name,
                "link": link_url,
            },
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, "posting the story")
    finally:
        if local and cleanup_local:
            _remove_file(local)


@mcp.tool()
def instagram_post_video_story(
    video_path_or_url: str,
    caption: Optional[str] = None,
    mentions: Optional[str] = None,
    hashtags: Optional[str] = None,
    location_name: Optional[str] = None,
    link_url: Optional[str] = None,
) -> str:
    """
    Post a video Story with optional caption and full sticker support.

    VIDEO SOURCE: an ABSOLUTE LOCAL FILE PATH works — no public URL required.

    Parameters:
    - video_path_or_url: Absolute local path or URL to MP4
    - caption: Optional story caption text
    - mentions: Comma-separated @usernames for mention stickers
    - hashtags: Comma-separated hashtags for hashtag stickers
    - location_name: Location sticker text
    - link_url: Link sticker URL
    """
    if err := _require_login(): return err
    pause = _pacing_error("post")
    if pause: return pause
    local = None
    try:
        from instagrapi.types import StoryMention, StoryHashtag, StoryLocation, StoryLink
        local = _download_if_url(video_path_or_url, ".mp4")
        dedupe = _dedupe_guard("story-video", "story", f"{video_path_or_url}|{caption or ''}")
        if dedupe:
            return dedupe
        waited = _pace_action("post")

        story_mentions, story_hashtags, story_locations, story_links = [], [], [], []

        if mentions:
            for name in [m.strip().lstrip("@") for m in mentions.split(",") if m.strip()]:
                try:
                    uid = ig.cl.user_id_from_username(name)
                    user = ig.cl.user_info(uid)
                    story_mentions.append(StoryMention(user=user, x=0.5, y=0.5, width=0.5, height=0.1))
                except Exception:
                    pass
        if hashtags:
            for tag in [h.strip().lstrip("#") for h in hashtags.split(",") if h.strip()]:
                try:
                    hinfo = ig.cl.hashtag_info(tag)
                    story_hashtags.append(StoryHashtag(hashtag=hinfo, x=0.5, y=0.7, width=0.3, height=0.08))
                except Exception:
                    pass
        if location_name:
            loc = _get_location(location_name)
            if loc is not None:
                story_locations.append(StoryLocation(location=loc, x=0.5, y=0.85, width=0.4, height=0.08))
        if link_url:
            story_links.append(StoryLink(webUri=link_url))

        m = ig.cl.video_upload_to_story(
            local,
            caption or "",
            mentions=story_mentions,
            hashtags=story_hashtags,
            locations=story_locations,
            links=story_links,
        )
        return str({
            "status": "success",
            "media_id": str(m.pk),
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, "posting the video story")
    finally:
        if local: _cleanup(local, video_path_or_url)


@mcp.tool()
def instagram_get_user_stories(username: Optional[str] = None) -> str:
    """Get active stories for the logged-in account or a target username."""
    if err := _require_login(): return err
    try:
        target = username or ig.cl.username
        uid = ig.cl.user_id_from_username(target)
        stories = ig.cl.user_stories(uid)
        return str([{"pk": str(s.pk), "media_type": s.media_type, "taken_at": str(s.taken_at)} for s in stories])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_delete_story(story_id: str, confirm: bool = False) -> str:
    """
    Delete one of your active stories (cannot be undone).

    Same safety flow as posts: call with confirm=False first to see the story
    details and get the user's approval, then call again with confirm=True.
    """
    if err := _require_login(): return err
    try:
        if not confirm:
            details = {"story_id": story_id}
            try:
                s = ig.cl.story_info(story_id)
                details.update({
                    "media_type": getattr(s, "media_type", None),
                    "taken_at": str(getattr(s, "taken_at", "")),
                    "caption": (getattr(s, "caption_text", "") or "")[:150],
                })
            except Exception:
                pass
            return _deletion_preview("delete_story", story_id, details)
        ok, msg = _consume_confirmation("delete_story", story_id)
        if not ok:
            return msg
        try:
            ig.cl.story_delete(story_id)
        except AttributeError:
            ig.cl.media_delete(story_id)
        return f"Deleted story {story_id} (user-approved)."
    except Exception as e:
        return _friendly_error(e, "deleting the story")


@mcp.tool()
def instagram_get_story_viewers(story_id: str) -> str:
    """
    Who watched one of YOUR stories? Returns the viewer list (own stories only).
    Use it to see engagement on a specific story.
    """
    if err := _require_login(): return err
    try:
        viewers = ig.cl.story_viewers(story_id)
        return str([_fmt_user(v) for v in viewers])
    except Exception as e:
        return f"Error: {e}"


def _story_pk_from_input(value: str) -> str:
    """Accept a story pk, an Instagram story URL, or a username (their latest story)."""
    raw = str(value).strip()
    if raw.isdigit():
        return raw
    try:
        pk = ig.cl.story_pk_from_url(raw)
        if pk:
            return str(pk)
    except Exception:
        pass
    uid = ig.cl.user_id_from_username(raw.lstrip("@"))
    stories = ig.cl.user_stories(uid)
    if not stories:
        raise ValueError(f"@{raw} has no active story right now.")
    return str(stories[0].pk)


def _fmt_poll(poll) -> dict:
    """Best-effort normalisation of a story poll sticker across instagrapi versions."""
    data = poll if isinstance(poll, dict) else {
        key: getattr(poll, key, None)
        for key in ("poll_id", "id", "question", "text", "options", "finished", "viewer_vote")
    }
    options = data.get("options") or []
    labels = []
    for option in options:
        if isinstance(option, dict):
            labels.append(str(option.get("text") or option.get("title") or option))
        else:
            labels.append(str(option))
    return {
        "poll_id": str(data.get("poll_id") or data.get("id") or ""),
        "question": str(data.get("question") or data.get("text") or ""),
        "options": labels,
        "finished": data.get("finished"),
        "your_vote": data.get("viewer_vote"),
    }


@mcp.tool()
def instagram_like_story(story_id_or_username: str, like: bool = True) -> str:
    """
    🔴 HIGH-RISK (bot detection): engagement actions are monitored and counted against
    the red daily cap. Like (or unlike with like=False) a story.

    Pass a story id, a story URL, or a username (their most recent story is used).
    The story is also marked as seen.
    """
    if err := _require_login(): return err
    pause = _pacing_error("like")
    if pause: return pause
    try:
        sid = _story_pk_from_input(story_id_or_username)
        waited = _pace_action("like")
        if like:
            ig.cl.story_like(sid)
            return f"Liked story {sid} (paced {waited}s)."
        ig.cl.story_unlike(sid)
        return f"Unliked story {sid} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "liking the story")


@mcp.tool()
def instagram_get_story_polls(username: str) -> str:
    """
    List the active polls in a user's stories: story ids, poll ids, the question and the
    answer options — feed the ids to instagram_vote_story_poll.
    """
    if err := _require_login(): return err
    try:
        uid = ig.cl.user_id_from_username(username.lstrip("@"))
        stories = ig.cl.user_stories(uid)
        polls = []
        for story in stories:
            for poll in (getattr(story, "polls", None) or []):
                polls.append({"story_id": str(story.pk), "poll": _fmt_poll(poll)})
        return str({"username": username.lstrip("@"), "polls_found": len(polls), "polls": polls})
    except Exception as e:
        return _friendly_error(e, "reading the story polls")


@mcp.tool()
def instagram_vote_story_poll(story_id: str, poll_id: str, vote_index: int = 0) -> str:
    """
    🔴 HIGH-RISK (bot detection): story engagement is monitored.
    Vote in a story poll — vote_index is 0-based (0 = first option, 1 = second).
    Get story_id and poll_id from instagram_get_story_polls.
    """
    if err := _require_login(): return err
    pause = _pacing_error("like")
    if pause: return pause
    try:
        voter = getattr(ig.cl, "story_poll_vote", None)
        if not voter:
            return "This instagrapi version cannot vote in story polls."
        waited = _pace_action("like")
        voter(story_id, poll_id, int(vote_index))
        return f"Voted option {vote_index} in poll {poll_id} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "voting in the poll")


# ─────────────────────────────────────────────────────────────────────────────
# 5. HIGHLIGHTS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_get_highlights(username: Optional[str] = None) -> str:
    """Get story highlights for the logged-in account or a target username."""
    if err := _require_login(): return err
    try:
        target = username or ig.cl.username
        uid = ig.cl.user_id_from_username(target)
        highlights = ig.cl.user_highlights(uid)
        return str([{"pk": str(h.pk), "title": h.title, "media_count": h.media_count} for h in highlights])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_create_highlight(title: str, story_ids: List[str]) -> str:
    """Create a new story highlight collection from existing stories."""
    if err := _require_login(): return err
    try:
        try:
            h = ig.cl.highlight_create(title, story_ids)
        except TypeError:
            # Older instagrapi (2.x) required an explicit cover story id
            h = ig.cl.highlight_create(title, story_ids, story_ids[0])
        return f"Highlight '{title}' created. ID: {h.pk}"
    except Exception as e:
        return _friendly_error(e, "creating the highlight")


@mcp.tool()
def instagram_delete_highlight(highlight_id: str, confirm: bool = False) -> str:
    """
    Delete a highlights collection (cannot be undone).

    Same safety flow: preview with confirm=False, then confirm=True after the
    user approves.
    """
    if err := _require_login(): return err
    try:
        if not confirm:
            details = {"highlight_id": highlight_id}
            try:
                for h in ig.cl.user_highlights(ig.cl.user_id):
                    if str(h.pk) == str(highlight_id):
                        details.update({"title": h.title, "media_count": h.media_count})
                        break
            except Exception:
                pass
            return _deletion_preview("delete_highlight", highlight_id, details)
        ok, msg = _consume_confirmation("delete_highlight", highlight_id)
        if not ok:
            return msg
        ig.cl.highlight_delete(highlight_id)
        return f"Deleted highlight {highlight_id} (user-approved)."
    except Exception as e:
        return _friendly_error(e, "deleting the highlight")


# ─────────────────────────────────────────────────────────────────────────────
# 6. ENGAGEMENT — LIKES, COMMENTS, SAVES
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_like_post(media_id_or_url: str) -> str:
    """🔴 HIGH-RISK (bot detection): mass liking is an automation signature.
    Like a post by media ID or URL — paced heavily and counted against the red daily cap."""
    if err := _require_login(): return err
    pause = _pacing_error("like")
    if pause: return pause
    try:
        mid = _media_id_from_input(media_id_or_url)
        waited = _pace_action("like")
        ig.cl.media_like(mid)
        return f"Liked post {mid} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "liking the post")


@mcp.tool()
def instagram_unlike_post(media_id_or_url: str) -> str:
    """🔴 HIGH-RISK (bot detection): like/unlike churn is an automation signature.
    Remove a like from a post — paced heavily and counted against the red daily cap."""
    if err := _require_login(): return err
    pause = _pacing_error("like")
    if pause: return pause
    try:
        mid = _media_id_from_input(media_id_or_url)
        waited = _pace_action("like")
        ig.cl.media_unlike(mid)
        return f"Unliked post {mid} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "unliking the post")


@mcp.tool()
def instagram_save_post(media_id_or_url: str) -> str:
    """
    Save a post to your general Saved collection (private — nobody is notified).
    For a named collection use instagram_save_to_collection; list yours with
    instagram_get_saved_collections.
    """
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        mid = _media_id_from_input(media_id_or_url)
        waited = _pace_action("engage")
        ig.cl.media_save(mid)
        return f"Post {mid} saved (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "saving the post")


@mcp.tool()
def instagram_unsave_post(media_id_or_url: str) -> str:
    """
    Remove a post from your Saved collection (private, no notification).
    Undo by saving it again with instagram_save_post.
    """
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        mid = _media_id_from_input(media_id_or_url)
        waited = _pace_action("engage")
        ig.cl.media_unsave(mid)
        return f"Post {mid} unsaved (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "unsaving the post")


@mcp.tool()
def instagram_save_to_collection(media_id_or_url: str, collection_name: str) -> str:
    """
    Save a post into one of your named Saved collections. The collection must already
    exist in the app — list them with instagram_get_saved_collections.
    """
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        mid = _media_id_from_input(media_id_or_url)
        pk = ig.cl.collection_pk_by_name(collection_name)
        waited = _pace_action("engage")
        ig.cl.media_save(mid, pk)
        return f"Post {mid} saved to collection '{collection_name}' (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "saving to the collection")


@mcp.tool()
def instagram_get_saved_collections() -> str:
    """List your Saved collections (name + id) so you can save posts into them."""
    if err := _require_login(): return err
    try:
        collections = ig.cl.collections()
        return str([{"id": str(c.pk), "name": c.name,
                     "media_count": getattr(c, "media_count", None)} for c in collections])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_archived_posts(amount: int = 20) -> str:
    """
    List your archived posts (hidden from the grid but still saved).
    Bring one back to your profile with instagram_unarchive_post.
    """
    if err := _require_login(): return err
    try:
        medias = ig.cl.archive_medias(amount)
        return str([_fmt_media(m) for m in medias])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_add_to_highlight(highlight_id: str, story_ids: str) -> str:
    """
    Add one or more of your existing stories to an existing highlight collection.
    story_ids: comma-separated story ids (from instagram_get_user_stories).
    Highlight ids: instagram_get_highlights.
    """
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        ids = [s.strip() for s in str(story_ids).split(",") if s.strip()]
        if not ids:
            return "Error: provide at least one story id (comma-separated)."
        waited = _pace_action("engage")
        ig.cl.highlight_add_stories(highlight_id, ids)
        return f"Added {len(ids)} story(ies) to highlight {highlight_id} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "adding stories to the highlight")


@mcp.tool()
def instagram_get_post_likers(media_id_or_url: str) -> str:
    """
    Who liked a post? Returns usernames + ids so you can reply to or study your audience.
    This is a bulk read — keep the amount modest on very large posts.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        likers = ig.cl.media_likers(mid)
        return str([_fmt_user(u) for u in likers])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_comment_on_post(
    media_id_or_url: Annotated[str, Field(description="Post or reel URL (or media id) to comment on")],
    text: Annotated[str, Field(description="Public comment text. Never repeat identical text — it is the top spam signal")],
) -> str:
    """
    🔴 HIGH-RISK (bot detection): public comments on others' posts are the most
    watched action — paced heavily and counted against the red daily cap. Never
    repeat identical text.

    Post a PUBLIC comment on any post or reel — yours or anyone else's.

    Typical flow: find content with instagram_find_topic_content /
    instagram_search_posts / instagram_get_hashtag_top_posts, then pass the
    result's URL or media ID here. A human-like delay is applied automatically
    before commenting (INSTAGRAM_MCP_COMMENT_DELAY_MIN/MAX). Do not post the same
    text repeatedly — Instagram flags duplicate comments as spam.
    """
    if err := _require_login(): return err
    pause = _pacing_error("comment")
    if pause: return pause
    try:
        mid = _media_id_from_input(media_id_or_url)
        dedupe = _dedupe_guard("comment", media_id_or_url, text)
        if dedupe: return dedupe
        waited = _pace_action("comment")
        c = ig.cl.media_comment(mid, text)
        return str({
            "status": "success",
            "comment_id": str(c.pk),
            "media_id_or_url": media_id_or_url,
            "text": text,
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, "posting the comment")


@mcp.tool()
def instagram_reply_to_comment(media_id_or_url: str, comment_id: str, text: str) -> str:
    """
    🔴 HIGH-RISK (bot detection): public replies to strangers attract anti-spam
    checks — paced heavily and counted against the red daily cap.

    Publicly reply to a specific comment on a post or reel.

    Get comment_id from instagram_get_post_comments,
    instagram_get_post_comments_range, or instagram_get_recent_comments.
    A human-like delay is applied automatically before replying.
    """
    if err := _require_login(): return err
    cleaned = str(comment_id).strip()
    if not cleaned.isdigit():
        return ("Error: comment_id must be the numeric ID shown by the comment-reading "
                "tools (e.g. 17892345678901234).")
    pause = _pacing_error("reply")
    if pause: return pause
    try:
        mid = _media_id_from_input(media_id_or_url)
        dedupe = _dedupe_guard("reply", f"{mid}:{cleaned}", text)
        if dedupe: return dedupe
        waited = _pace_action("reply")
        c = ig.cl.media_comment(mid, text, replied_to_comment_id=int(cleaned))
        return str({
            "status": "success",
            "reply_id": str(c.pk),
            "replied_to_comment_id": cleaned,
            "media_id_or_url": media_id_or_url,
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, "posting the reply")


@mcp.tool()
def instagram_reply_to_comment_by_username(
    media_id_or_url: Annotated[str, Field(description="Post/reel URL or media id that holds the comment")],
    username: Annotated[str, Field(description="@username whose comment you are replying to (with or without @)")],
    text: Annotated[str, Field(description="Public reply text — never repeat identical text")],
    comment_text_contains: Optional[str] = None,
    prefer: str = "latest",
    max_scan: int = 150,
) -> str:
    """
    🔴 HIGH-RISK (bot detection): public replies to strangers attract anti-spam
    checks — paced heavily and counted against the red daily cap.

    Reply to a specific person's comment on a post or reel — just give the username.

    Use this when the user says "reply to @user on this post (URL)". The tool
    scans the post's comments to find that person's comment and posts a public
    reply — no manual comment-ID lookup needed.

    Parameters:
    - media_id_or_url: Post/reel URL or media ID
    - username: The person whose comment you are replying to (with or without @)
    - text: Your public reply text
    - comment_text_contains: Optional part of their comment text, to pick the
      right comment when the person commented more than once
    - prefer: "latest" (default) or "likes" — which comment to pick if several match
    - max_scan: How many comments to scan (max 500)
    """
    if err := _require_login(): return err
    cleaned = username.strip().lstrip("@")
    if not cleaned:
        return "Error: provide the username of the person to reply to."
    pause = _pacing_error("reply")
    if pause: return pause
    try:
        max_scan = max(10, min(int(max_scan), 500))
        mid = _media_id_from_input(media_id_or_url)
        comment, scanned = _find_comment_by_username(
            mid, cleaned, comment_text_contains, (prefer or "latest").lower(), max_scan
        )
        if comment is None:
            return (f"Could not find a comment from @{cleaned} in the first {scanned} comments. "
                    f"Use instagram_get_post_comments to inspect the post's comments, or pass "
                    f"comment_text_contains to narrow the match.")
        dedupe = _dedupe_guard("reply-user", f"{mid}:{cleaned}", text)
        if dedupe: return dedupe
        waited = _pace_action("reply")
        c = ig.cl.media_comment(mid, text, replied_to_comment_id=int(comment.pk))
        return str({
            "status": "success",
            "reply_id": str(c.pk),
            "replied_to_comment_id": str(comment.pk),
            "replied_to_username": cleaned,
            "replied_to_text": (comment.text or "")[:120],
            "comments_scanned": scanned,
            "media_id_or_url": media_id_or_url,
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, f"replying to @{cleaned}")


@mcp.tool()
def instagram_delete_comment(media_id_or_url: str, comment_id: str, confirm: bool = False) -> str:
    """
    Delete a comment (yours, or one left on your post; cannot be undone).

    Same safety flow: call with confirm=False first to show the user exactly what
    will be deleted (comment text + author when available), then call again with
    confirm=True after they approve.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        target = f"{mid}:{comment_id}"
        if not confirm:
            details = {"media_id_or_url": media_id_or_url, "comment_id": str(comment_id)}
            try:
                comments = ig.cl.media_comments(mid, 100)
                for c in comments:
                    if str(c.pk) == str(comment_id):
                        details["username"] = c.user.username if getattr(c, "user", None) else None
                        details["text"] = (c.text or "")[:150]
                        break
            except Exception:
                pass
            return _deletion_preview("delete_comment", target, details)
        ok, msg = _consume_confirmation("delete_comment", target)
        if not ok:
            return msg
        ig.cl.comment_bulk_delete(mid, [comment_id])
        return f"Deleted comment {comment_id} (user-approved)."
    except Exception as e:
        return _friendly_error(e, "deleting the comment")


@mcp.tool()
def instagram_like_comment(comment_id: str) -> str:
    """🔴 HIGH-RISK (bot detection): mass liking is an automation signature.
    Like a comment — paced heavily and counted against the red daily cap."""
    if err := _require_login(): return err
    pause = _pacing_error("like")
    if pause: return pause
    try:
        waited = _pace_action("like")
        ig.cl.comment_like(comment_id)
        return f"Comment {comment_id} liked (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "liking the comment")


@mcp.tool()
def instagram_unlike_comment(comment_id: str) -> str:
    """🔴 HIGH-RISK (bot detection): like/unlike churn is an automation signature.
    Remove a like from a comment — paced heavily and counted against the red daily cap."""
    if err := _require_login(): return err
    pause = _pacing_error("like")
    if pause: return pause
    try:
        waited = _pace_action("like")
        ig.cl.comment_unlike(comment_id)
        return f"Comment {comment_id} unliked (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "unliking the comment")


@mcp.tool()
def instagram_pin_comment(media_id_or_url: str, comment_id: str, pin: bool = True) -> str:
    """
    Pin or unpin a comment on YOUR OWN post (pin=True pins, pin=False unpins).
    One pinned comment per post — this is how you surface the best comment.
    Comment ids come from instagram_get_post_comments.
    """
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        mid = _media_id_from_input(media_id_or_url)
        waited = _pace_action("engage")
        if pin:
            ig.cl.comment_pin(mid, comment_id)
            return f"Comment {comment_id} pinned on post {mid} (paced {waited}s)."
        ig.cl.comment_unpin(mid, comment_id)
        return f"Comment {comment_id} unpinned on post {mid} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "pinning the comment")


@mcp.tool()
def instagram_check_comment(media_id_or_url: str, text: str) -> str:
    """
    🟢 SAFE preflight: ask Instagram whether a comment text would be flagged as
    offensive/spam BEFORE posting it. Use this when the wording is edgy or a previous
    comment was rejected — then post with instagram_comment_on_post.
    Returns is_offensive plus the raw API response when available.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        checker = (getattr(ig.cl, "media_check_offensive_comment_v2", None)
                   or getattr(ig.cl, "media_check_offensive_comment", None))
        if not checker:
            return ("This instagrapi version has no offensive-comment preflight — "
                    "post the comment and read Instagram's response instead.")
        result = checker(mid, text)
        if isinstance(result, dict):
            return str({"is_offensive": result.get("is_offensive"), "response": result})
        return f"is_offensive: {bool(result)}"
    except Exception as e:
        return _friendly_error(e, "checking the comment")


@mcp.tool()
def instagram_get_comment_likers(comment_id: str, amount: int = 20) -> str:
    """List the users who liked a comment (username + id). Keep the volume low."""
    if err := _require_login(): return err
    try:
        likers = ig.cl.comment_likers_gql(comment_id, amount)
        people = []
        for entry in likers:
            user = entry.get("user") if isinstance(entry, dict) else None
            if isinstance(user, dict):
                people.append({"username": user.get("username"),
                               "pk": str(user.get("pk") or user.get("id") or "")})
            else:
                people.append(entry if isinstance(entry, dict) else str(entry))
        return str({"comment_id": str(comment_id), "count": len(people), "likers": people})
    except Exception as e:
        return _friendly_error(e, "reading the comment likers")


@mcp.tool()
def instagram_get_post_comments(media_id_or_url: str, amount: int = 20, sort_by: str = "newest") -> str:
    """
    Get comments on a post or reel (username, text, likes, date).

    sort_by: "newest" (default, API order) or "likes" (most-liked comments first —
    useful for finding the comment everyone is engaging with before replying).
    Note: comments are fetched first and then sorted, so use a larger `amount`
    (e.g. 50–100) when you want the overall most-liked comments.

    Each item includes a `comment_id` you can pass to instagram_reply_to_comment.
    For a specific slice of comments (e.g. comments 23–44), use
    instagram_get_post_comments_range instead.
    """
    if err := _require_login(): return err
    try:
        mid = _media_id_from_input(media_id_or_url)
        comments = ig.cl.media_comments(mid, amount)
        if str(sort_by).lower() in ("likes", "like_count", "top"):
            comments = sorted(comments, key=lambda c: getattr(c, "like_count", 0) or 0, reverse=True)
        return str({
            "media_id_or_url": media_id_or_url,
            "returned_count": len(comments),
            "sort_by": sort_by,
            "comments": [_fmt_comment(c) for c in comments],
        })
    except Exception as e:
        return _friendly_error(e, "reading the comments")


@mcp.tool()
def instagram_get_recent_comments(amount_posts: int = 5, comments_per_post: int = 20, exclude_self: bool = True) -> str:
    """
    Fetch recent comments across your OWN latest posts in one call.

    exclude_self (default True) removes comments written by you, so the list
    shows what other people said on your posts — ready to reply to. Every item
    includes the post's `media_id_or_url` and each comment's `comment_id`
    for instagram_reply_to_comment.
    """
    if err := _require_login(): return err
    try:
        amount_posts = max(1, min(int(amount_posts), 20))
        comments_per_post = max(1, min(int(comments_per_post), 100))
        own_username = (ig.username or getattr(ig.cl, "username", None) or "").lower()
        medias = ig.cl.user_medias(ig.cl.user_id, amount_posts)
        posts = []
        for m in medias:
            try:
                comments = ig.cl.media_comments(m.id, comments_per_post)
            except Exception:
                comments = []
            if exclude_self and own_username:
                comments = [c for c in comments
                            if ((getattr(c, "user", None) and (c.user.username or "").lower()) != own_username)]
            posts.append({
                "media_id_or_url": m.id,
                "url": f"https://www.instagram.com/p/{m.code}/",
                "caption_preview": (m.caption_text or "")[:120],
                "comment_count": m.comment_count,
                "comments": [_fmt_comment(c) for c in comments],
            })
        return str({"posts": posts})
    except Exception as e:
        return _friendly_error(e, "reading recent comments")


@mcp.tool()
def instagram_get_post_comments_range(media_id_or_url: str, start_index: int = 1, end_index: int = 20) -> str:
    """
    Read a RANGE of comments on a specific post or reel.

    Indices are 1-based and inclusive: start_index=23, end_index=44 returns
    comments #23 through #44 exactly as they appear on the post. Each item
    includes a `comment_id` that can be publicly replied to with
    instagram_reply_to_comment, or you can comment on the post itself with
    instagram_comment_on_post.

    Parameters:
    - media_id_or_url: Post/reel URL or media ID
    - start_index: First comment number to return (1 = first comment)
    - end_index: Last comment number to return (max 200 comments per call)
    """
    if err := _require_login(): return err
    try:
        start_index = int(start_index)
        end_index = int(end_index)
        if start_index < 1 or end_index < start_index:
            return "Error: start_index must be >= 1 and <= end_index."
        if end_index - start_index + 1 > 200:
            return "Error: request at most 200 comments per call (raise end_index gradually)."
        mid = _media_id_from_input(media_id_or_url)
        comments = _fetch_comments_upto(mid, end_index)
        window = comments[start_index - 1:end_index]
        return str({
            "media_id_or_url": media_id_or_url,
            "start_index": start_index,
            "end_index": end_index,
            "total_fetched": len(comments),
            "returned_count": len(window),
            "next_start_index": end_index + 1,
            "comments": [_fmt_comment(c) for c in window],
        })
    except Exception as e:
        return _friendly_error(e, "reading the comment range")


# ─────────────────────────────────────────────────────────────────────────────
# 7. FOLLOWING & RELATIONS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_follow_user(username: str) -> str:
    """🔴 HIGH-RISK (bot detection): follow/unfollow churn is the #1 automation signal.
    Follow a user by username — paced heavily and counted against the red daily cap."""
    if err := _require_login(): return err
    pause = _pacing_error("social")
    if pause: return pause
    try:
        uid = ig.cl.user_id_from_username(username)
        waited = _pace_action("social")
        ig.cl.user_follow(uid)
        return f"Followed @{username} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "following the user")


@mcp.tool()
def instagram_unfollow_user(username: str) -> str:
    """🔴 HIGH-RISK (bot detection): follow/unfollow churn is the #1 automation signal.
    Unfollow a user by username — paced heavily and counted against the red daily cap."""
    if err := _require_login(): return err
    pause = _pacing_error("social")
    if pause: return pause
    try:
        uid = ig.cl.user_id_from_username(username)
        waited = _pace_action("social")
        ig.cl.user_unfollow(uid)
        return f"Unfollowed @{username} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "unfollowing the user")


@mcp.tool()
def instagram_get_followers(username: Optional[str] = None, amount: int = 50) -> str:
    """Get the followers list for the logged-in account or a target username."""
    if err := _require_login(): return err
    try:
        target = username or ig.cl.username
        uid = ig.cl.user_id_from_username(target)
        followers = ig.cl.user_followers(uid, amount=amount)
        return str([_fmt_user(u) for u in followers.values()])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_following(username: Optional[str] = None, amount: int = 50) -> str:
    """Get the accounts that the logged-in account (or target username) is following."""
    if err := _require_login(): return err
    try:
        target = username or ig.cl.username
        uid = ig.cl.user_id_from_username(target)
        following = ig.cl.user_following(uid, amount=amount)
        return str([_fmt_user(u) for u in following.values()])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_mute_user(username: str, posts: bool = True, stories: bool = True, unmute: bool = False) -> str:
    """
    Mute (or unmute with unmute=True) another account's posts and/or stories — the quiet
    way to stop seeing someone's content without unfollowing them (they are not notified).
    """
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        uid = ig.cl.user_id_from_username(username.lstrip("@"))
        waited = _pace_action("engage")
        done = []
        if posts:
            if unmute:
                ig.cl.unmute_posts_from_follow(uid)
            else:
                ig.cl.mute_posts_from_follow(uid)
            done.append("posts")
        if stories:
            if unmute:
                ig.cl.unmute_stories_from_follow(uid)
            else:
                ig.cl.mute_stories_from_follow(uid)
            done.append("stories")
        verb = "Unmuted" if unmute else "Muted"
        return f"{verb} {', '.join(done) or 'nothing (enable posts/stories)'} for @{username.lstrip('@')} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "muting the user")


@mcp.tool()
def instagram_remove_follower(username: str) -> str:
    """🔴 HIGH-RISK (bot detection): relationship churn is monitored.
    Remove someone from YOUR followers without blocking them — paced and counted
    against the red daily cap. They are not notified, but may notice."""
    if err := _require_login(): return err
    pause = _pacing_error("social")
    if pause: return pause
    try:
        uid = ig.cl.user_id_from_username(username.lstrip("@"))
        waited = _pace_action("social")
        ig.cl.user_remove_follower(uid)
        return f"Removed @{username.lstrip('@')} from your followers (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "removing the follower")


@mcp.tool()
def instagram_handle_follow_request(username: str, approve: bool = True) -> str:
    """
    Approve (approve=True) or decline (approve=False) a pending follow request on your
    private account. List the pending ones with instagram_get_pending_follow_requests.
    """
    if err := _require_login(): return err
    pause = _pacing_error("social")
    if pause: return pause
    try:
        uid = ig.cl.user_id_from_username(username.lstrip("@"))
        waited = _pace_action("social")
        if approve:
            ig.cl.user_follow_request_approve(uid)
            return f"Approved the follow request from @{username.lstrip('@')} (paced {waited}s)."
        ig.cl.user_follow_request_decline(uid)
        return f"Declined the follow request from @{username.lstrip('@')} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "handling the follow request")


@mcp.tool()
def instagram_manage_close_friends(username: str, add: bool = True) -> str:
    """
    Add (add=True) or remove (add=False) a user from your Close Friends list — the
    audience used by 'close friends only' stories.
    """
    if err := _require_login(): return err
    pause = _pacing_error("social")
    if pause: return pause
    try:
        uid = ig.cl.user_id_from_username(username.lstrip("@"))
        waited = _pace_action("social")
        if add:
            ig.cl.close_friend_add(uid)
            return f"Added @{username.lstrip('@')} to Close Friends (paced {waited}s)."
        ig.cl.close_friend_remove(uid)
        return f"Removed @{username.lstrip('@')} from Close Friends (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "updating Close Friends")


@mcp.tool()
def instagram_follow_hashtag(hashtag: str, follow: bool = True) -> str:
    """
    Follow (or unfollow with follow=False) a hashtag so its top posts reach your feed.
    Do not include the '#' symbol.
    """
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        tag = hashtag.lstrip("#")
        waited = _pace_action("engage")
        if follow:
            ig.cl.hashtag_follow(tag)
            return f"Following #{tag} (paced {waited}s)."
        ig.cl.hashtag_unfollow(tag)
        return f"Unfollowed #{tag} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "updating the hashtag follow")


@mcp.tool()
def instagram_create_note(text: str, audience: str = "mutual") -> str:
    """
    Post an Instagram Note — the short text bubble above your profile picture in DMs
    (shows for 24h). audience: "mutual" (mutual followers, default), "followers",
    "close_friends" or "everyone" (Instagram honours whichever your account supports).
    """
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        aud = None
        try:
            from instagrapi.mixins.note import NoteAudience
            member = {"mutual": "MUTUAL_FOLLOWERS", "followers": "FOLLOWERS",
                      "close_friends": "CLOSE_FRIENDS", "everyone": "EVERYONE"}.get(
                str(audience).lower(), "")
            aud = getattr(NoteAudience, member, None) if member else None
        except Exception:
            aud = None
        waited = _pace_action("engage")
        note = ig.cl.create_note(text) if aud is None else ig.cl.create_note(text, aud)
        return (f"Note posted (id {getattr(note, 'id', '?')}, audience {audience}) "
                f"(paced {waited}s).")
    except Exception as e:
        return _friendly_error(e, "posting the note")


@mcp.tool()
def instagram_get_notes() -> str:
    """Read the current Instagram Notes (short status bubbles) from people you follow."""
    if err := _require_login(): return err
    try:
        notes = ig.cl.get_notes()
        return str([{
            "id": str(getattr(n, "id", "")),
            "text": getattr(n, "text", ""),
            "user": getattr(getattr(n, "user", None), "username", None),
            "audience": str(getattr(n, "audience", "")),
        } for n in notes])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_delete_note(note_id: str) -> str:
    """Delete one of your own Instagram Notes (id from instagram_get_notes)."""
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        waited = _pace_action("engage")
        ig.cl.delete_note(int(note_id))
        return f"Note {note_id} deleted (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "deleting the note")


@mcp.tool()
def instagram_block_user(username: str) -> str:
    """🔴 HIGH-RISK (bot detection): relationship changes are monitored.
    Block a user by username — paced heavily and counted against the red daily cap."""
    if err := _require_login(): return err
    pause = _pacing_error("social")
    if pause: return pause
    try:
        uid = ig.cl.user_id_from_username(username)
        waited = _pace_action("social")
        ig.cl.user_block(uid)
        return f"Blocked @{username} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "blocking the user")


@mcp.tool()
def instagram_unblock_user(username: str) -> str:
    """🔴 HIGH-RISK (bot detection): relationship changes are monitored.
    Unblock a previously blocked user — paced heavily and counted against the red daily cap."""
    if err := _require_login(): return err
    pause = _pacing_error("social")
    if pause: return pause
    try:
        uid = ig.cl.user_id_from_username(username)
        waited = _pace_action("social")
        ig.cl.user_unblock(uid)
        return f"Unblocked @{username} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "unblocking the user")


@mcp.tool()
def instagram_get_blocked_users() -> str:
    """
    List every account you have blocked (usernames + ids).
    Unblock one with instagram_unblock_user.
    """
    if err := _require_login(): return err
    try:
        # Use the private API endpoint directly
        result = ig.cl.private_request("users/blocked_list/")
        users = result.get("blocked_list", [])
        return str([{"pk": str(u.get("pk")), "username": u.get("username")} for u in users])
    except Exception as e:
        return f"Error fetching blocked users: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 8. DIRECT MESSAGES
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_get_direct_threads(amount: int = 20) -> str:
    """Get recent DM threads with thread IDs, participants, and last activity."""
    if err := _require_login(): return err
    try:
        threads = ig.cl.direct_threads(amount)
        return str([{
            "thread_id": t.id,
            "title": t.thread_title or "",
            "participants": [u.username for u in (t.users or [])],
            "last_activity_at": str(t.last_activity_at),
            "muted": t.muted,
        } for t in threads])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_direct_messages(thread_id: str, amount: int = 30) -> str:
    """
    Read the messages in one DM thread, oldest→newest (amount limits how many recent ones).
    Get the thread_id from instagram_get_direct_threads; message ids feed
    instagram_react_to_dm / instagram_unsend_dm. Mark it read with instagram_mark_thread_seen.
    """
    if err := _require_login(): return err
    try:
        thread = ig.cl.direct_thread(thread_id)
        msgs = sorted(thread.messages, key=lambda m: m.timestamp)[-amount:]
        return str([{
            "id": m.id,
            "user_id": str(m.user_id),
            "type": m.item_type,
            "text": m.text,
            "timestamp": str(m.timestamp),
        } for m in msgs])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_send_direct_message(
    text: Annotated[str, Field(description="Message text to send")],
    username: Annotated[Optional[str], Field(description="Recipient @username — starts or continues a conversation")] = None,
    thread_id: Annotated[Optional[str], Field(description="Existing thread id (from instagram_get_direct_threads) to reply in")] = None,
) -> str:
    """
    🔴 HIGH-RISK (bot detection): DMs to strangers are heavily monitored and
    counted against the red daily cap. Prefer replying in existing threads.

    Send a text DM. Provide either:
    - username: to start or continue a conversation with a user.
    - thread_id: to reply in an existing thread
      (get thread ids from instagram_get_direct_threads).

    To read a conversation first, use instagram_get_direct_threads then
    instagram_get_direct_messages(thread_id). Photos/videos: instagram_send_dm_photo
    and instagram_send_dm_video accept local files.
    """
    if err := _require_login(): return err
    if not username and not thread_id:
        return "Error: Provide either username or thread_id."
    pause = _pacing_error("dm")
    if pause: return pause
    dedupe = _dedupe_guard("dm", str(thread_id or username), text)
    if dedupe: return dedupe
    try:
        waited = _pace_action("dm")
        if thread_id:
            msg = ig.cl.direct_send(text, thread_ids=[thread_id])
        else:
            uid = ig.cl.user_id_from_username(username)
            msg = ig.cl.direct_send(text, user_ids=[uid])
        tid = getattr(msg, "thread_id", None)
        return (f"Message sent. ID: {msg.id}"
                + (f" | thread_id: {tid}" if tid else "")
                + f" (paced {waited}s).")
    except Exception as e:
        return _friendly_error(e, "sending the DM")


@mcp.tool()
def instagram_send_dm_photo(image_path_or_url: str, username: Optional[str] = None,
                             thread_id: Optional[str] = None) -> str:
    """
    🔴 HIGH-RISK (bot detection): DMs to strangers are heavily monitored and
    counted against the red daily cap.

    Send a photo via DM (absolute local paths work — no public URL needed;
    PNG/WebP are normalised to JPEG automatically).

    Provide username (start/continue a chat) or thread_id (reply in a thread).
    """
    if err := _require_login(): return err
    if not username and not thread_id:
        return "Error: Provide either username or thread_id."
    pause = _pacing_error("dm")
    if pause: return pause
    local = None
    cleanup_local = False
    try:
        local, cleanup_local = _resolve_image_source(image_path_or_url)
        dedupe = _dedupe_guard("dm-photo", str(thread_id or username), image_path_or_url)
        if dedupe: return dedupe
        waited = _pace_action("dm")
        if thread_id:
            msg = ig.cl.direct_send_photo(local, thread_ids=[thread_id])
        else:
            uid = ig.cl.user_id_from_username(username)
            msg = ig.cl.direct_send_photo(local, user_ids=[uid])
        tid = getattr(msg, "thread_id", None)
        return (f"Photo DM sent. ID: {msg.id}"
                + (f" | thread_id: {tid}" if tid else "")
                + f" (paced {waited}s).")
    except Exception as e:
        return _friendly_error(e, "sending the photo DM")
    finally:
        if local and cleanup_local:
            _remove_file(local)


@mcp.tool()
def instagram_send_dm_video(video_path_or_url: str, username: Optional[str] = None,
                             thread_id: Optional[str] = None) -> str:
    """
    🔴 HIGH-RISK (bot detection): DMs to strangers are heavily monitored and
    counted against the red daily cap.

    Send a video via DM (absolute local .mp4 paths work).

    Provide username (start/continue a chat) or thread_id (reply in a thread).
    """
    if err := _require_login(): return err
    if not username and not thread_id:
        return "Error: Provide either username or thread_id."
    pause = _pacing_error("dm")
    if pause: return pause
    local = None
    try:
        local = _download_if_url(video_path_or_url, ".mp4")
        dedupe = _dedupe_guard("dm-video", str(thread_id or username), video_path_or_url)
        if dedupe: return dedupe
        waited = _pace_action("dm")
        if thread_id:
            msg = ig.cl.direct_send_video(local, thread_ids=[thread_id])
        else:
            uid = ig.cl.user_id_from_username(username)
            msg = ig.cl.direct_send_video(local, user_ids=[uid])
        tid = getattr(msg, "thread_id", None)
        return (f"Video DM sent. ID: {msg.id}"
                + (f" | thread_id: {tid}" if tid else "")
                + f" (paced {waited}s).")
    except Exception as e:
        return _friendly_error(e, "sending the video DM")
    finally:
        if local: _cleanup(local, video_path_or_url)


@mcp.tool()
def instagram_mark_thread_seen(thread_id: str) -> str:
    """
    Mark a DM thread as read (nothing is sent — it just clears the unread state).
    Use it after instagram_get_direct_messages once you have handled the conversation.
    """
    if err := _require_login(): return err
    try:
        ig.cl.direct_send_seen(thread_id)
        return f"Thread {thread_id} marked as seen."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_react_to_dm(thread_id: str, message_id: str, emoji: str = "❤", remove: bool = False) -> str:
    """
    🔴 HIGH-RISK (bot detection): DM activity is heavily monitored.
    React to a DM with an emoji (default ❤), or remove your reaction with remove=True.
    message_id comes from instagram_get_direct_messages.
    """
    if err := _require_login(): return err
    pause = _pacing_error("dm")
    if pause: return pause
    dedupe = _dedupe_guard("dm-reaction", str(thread_id), f"{message_id}:{emoji}:{remove}")
    if dedupe: return dedupe
    try:
        waited = _pace_action("dm")
        if remove:
            ig.cl.direct_delete_reaction(int(thread_id), int(message_id), emoji)
            return f"Reaction {emoji} removed from message {message_id} (paced {waited}s)."
        ig.cl.direct_send_reaction(int(thread_id), int(message_id), emoji)
        return f"Reacted {emoji} to message {message_id} (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "reacting to the DM")


@mcp.tool()
def instagram_unsend_dm(thread_id: str, message_id: str, confirm: bool = False) -> str:
    """
    🔴 HIGH-RISK (bot detection): DM activity is heavily monitored.
    Unsend (delete for everyone) one of YOUR messages in a thread — cannot be undone.

    SAFETY FLOW: call with confirm=False first to show the user which message will be
    removed, then call again with confirm=True only after they approve.
    """
    if err := _require_login(): return err
    target = f"{thread_id}:{message_id}"
    try:
        if not confirm:
            details = {"thread_id": str(thread_id), "message_id": str(message_id)}
            try:
                thread = ig.cl.direct_thread(thread_id)
                for m in thread.messages:
                    if str(m.id) == str(message_id):
                        details["text"] = (m.text or "")[:150]
                        details["sent_at"] = str(m.timestamp)
                        break
            except Exception:
                pass
            return _deletion_preview("unsend_dm", target, details)
        ok, msg = _consume_confirmation("unsend_dm", target)
        if not ok:
            return msg
        pause = _pacing_error("dm")
        if pause: return pause
        waited = _pace_action("dm")
        ig.cl.direct_message_unsend(int(thread_id), int(message_id))
        return f"Message {message_id} unsent (user-approved, paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "unsending the message")


@mcp.tool()
def instagram_mute_thread(thread_id: str, mute: bool = True) -> str:
    """Mute (or unmute with mute=False) a DM thread so it stops notifying you."""
    if err := _require_login(): return err
    pause = _pacing_error("engage")
    if pause: return pause
    try:
        waited = _pace_action("engage")
        if mute:
            ig.cl.direct_thread_mute(int(thread_id))
            return f"Thread {thread_id} muted (paced {waited}s)."
        ig.cl.direct_thread_unmute(int(thread_id))
        return f"Thread {thread_id} unmuted (paced {waited}s)."
    except Exception as e:
        return _friendly_error(e, "muting the thread")


@mcp.tool()
def instagram_search_dm_messages(query: str, amount: int = 20) -> str:
    """
    Search all your DM threads for a word or phrase. Each match includes the thread
    it belongs to, so you can open it with instagram_get_direct_messages.
    """
    if err := _require_login(): return err
    try:
        searcher = getattr(ig.cl, "direct_message_search", None)
        if not searcher:
            return "This instagrapi version has no DM search — read threads individually instead."
        hits = searcher(query)[:amount]
        matches = []
        for item in hits:
            msg, thread = item if isinstance(item, tuple) else (item, None)
            matches.append({
                "message_id": str(getattr(msg, "id", "")),
                "thread_id": str(getattr(thread, "id", "") or getattr(msg, "thread_id", "")),
                "text": getattr(msg, "text", None),
                "timestamp": str(getattr(msg, "timestamp", "")),
                "with": [u.username for u in (getattr(thread, "users", None) or [])],
            })
        return str({"query": query, "count": len(matches), "matches": matches})
    except Exception as e:
        return _friendly_error(e, "searching the DMs")


# ─────────────────────────────────────────────────────────────────────────────
# 9. SEARCH & EXPLORE
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_search_users(query: str, count: int = 10) -> str:
    """
    Search Instagram for users by name or username (returns username, id, follower info).
    Bulk read — keep the count low; get the exact handle first when the user knows it.
    """
    if err := _require_login(): return err
    try:
        results = ig.cl.search_users(query)[:count]
        return str([_fmt_user(u) for u in results])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_search_hashtag(hashtag: str, amount: int = 12) -> str:
    """Get recent posts for a hashtag. Do not include '#' symbol."""
    if err := _require_login(): return err
    try:
        medias = ig.cl.hashtag_medias_recent(hashtag.lstrip("#"), amount)
        return str([_fmt_media(m) for m in medias])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_hashtag_top_posts(hashtag: str, amount: int = 9) -> str:
    """Get trending/top posts for a hashtag. Do not include '#' symbol."""
    if err := _require_login(): return err
    try:
        medias = ig.cl.hashtag_medias_top(hashtag.lstrip("#"), amount)
        return str([_fmt_media(m) for m in medias])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_hashtag_info(hashtag: str) -> str:
    """Get information about a hashtag including total post count."""
    if err := _require_login(): return err
    try:
        info = ig.cl.hashtag_info(hashtag.lstrip("#"))
        return str({"name": info.name, "media_count": info.media_count, "id": str(info.id)})
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_similar_accounts(username: str) -> str:
    """Find accounts similar to a given username (Instagram's 'suggested for you')."""
    if err := _require_login(): return err
    try:
        uid = ig.cl.user_id_from_username(username)
        data = ig.cl.user_suggested_profiles(uid)
        # instagrapi returns a dict here (e.g. {"users": [...]}); tolerate both shapes.
        if isinstance(data, dict):
            users = data.get("users") or data.get("items") or []
        else:
            users = data or []
        return str([_fmt_user(u) for u in users])
    except Exception as e:
        return _friendly_error(e, "fetching similar accounts")


@mcp.tool()
def instagram_get_location_posts(location_name: str, amount: int = 12) -> str:
    """
    Get recent posts tagged at a location (city, venue, landmark).
    Bulk discovery read — keep the amount low. Location ids come from the name lookup
    this tool performs for you.
    """
    if err := _require_login(): return err
    try:
        results = _search_locations_by_name(location_name)
        if not results:
            return f"No location found for '{location_name}'"
        medias = ig.cl.location_medias_recent(results[0].pk, amount)
        return str([_fmt_media(m) for m in medias])
    except Exception as e:
        return _friendly_error(e, "fetching location posts")


@mcp.tool()
def instagram_search_posts(query: str, amount: int = 20) -> str:
    """
    Search posts/reels by keyword (Instagram's blended Top search).

    Results include `url` and `id`, ready to pass to instagram_comment_on_post,
    instagram_get_post_comments, or instagram_get_post_comments_range.
    """
    if err := _require_login(): return err
    try:
        amount = max(1, min(int(amount), 50))
        medias = ig.cl.media_search(query, amount)
        return str({
            "query": query,
            "count": len(medias),
            "results": [_fmt_media(m) for m in medias],
        })
    except Exception as e:
        return _friendly_error(e, f"searching posts for '{query}'")


@mcp.tool()
def instagram_find_topic_content(topic: str, amount: int = 10, mode: str = "top") -> str:
    """
    Find posts/reels about a topic so you can comment on them.

    mode: "top" (trending posts — default), "recent" (newest posts), or
    "reels" (reels only). Combines keyword search with the topic's hashtags
    and returns ready-to-use `url` / `id` for each result.
    """
    if err := _require_login(): return err
    try:
        amount = max(1, min(int(amount), 50))
        mode = (mode or "top").lower()
        if mode not in ("top", "recent", "reels"):
            return "Error: mode must be 'top', 'recent', or 'reels'."
        topic_clean = topic.strip().lstrip("#")
        found = []
        errors = []
        try:
            found.extend(ig.cl.media_search(topic_clean, amount))
        except Exception as e:
            errors.append(str(e))
        # Only fall back to hashtag lookups when the keyword search came up short:
        # every extra request increases the chance of Instagram throttling.
        if len(found) < amount:
            try:
                tags = ig.cl.search_hashtags(topic_clean)[:2]
            except Exception as e:
                tags = []
                errors.append(str(e))
            for tag in tags:
                try:
                    if mode == "reels":
                        found.extend(ig.cl.hashtag_medias_reels_v1(tag.name, amount))
                    elif mode == "recent":
                        found.extend(ig.cl.hashtag_medias_recent(tag.name, amount))
                    else:
                        found.extend(ig.cl.hashtag_medias_top(tag.name, amount))
                except Exception as e:
                    errors.append(str(e))
        seen, results = set(), []
        for m in found:
            if m.pk in seen:
                continue
            seen.add(m.pk)
            results.append(_fmt_media(m))
            if len(results) >= amount:
                break
        if not results:
            if errors:
                return _friendly_error(Exception(errors[-1]), f"finding content for '{topic}'")
            return f"No content found for topic '{topic}' (mode={mode})."
        return str({
            "topic": topic,
            "mode": mode,
            "count": len(results),
            "next_step": ("Comment with instagram_comment_on_post(media_id_or_url=URL, text=...) "
                          "or read comments with instagram_get_post_comments_range(...)."),
            "results": results,
        })
    except Exception as e:
        return _friendly_error(e, f"finding content for '{topic}'")


@mcp.tool()
def instagram_get_explore_reels(amount: int = 10) -> str:
    """Get reels from the Explore/Reels feed (random popular content)."""
    if err := _require_login(): return err
    try:
        amount = max(1, min(int(amount), 30))
        medias = ig.cl.explore_reels(amount)
        return str({"count": len(medias), "results": [_fmt_media(m) for m in medias]})
    except Exception as e:
        return _friendly_error(e, "fetching explore reels")


# ─────────────────────────────────────────────────────────────────────────────
# 10. NOTIFICATIONS & ACTIVITY
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def instagram_get_notifications(amount: int = 20) -> str:
    """Get recent activity — likes, comments, follows, mentions, tags."""
    if err := _require_login(): return err
    try:
        activity = ig.cl.news_inbox_v1()
        counts = activity.get("counts", {})
        stories = activity.get("new_stories", [])[:amount]
        items = [{
            "type": s.get("type"),
            "text": s.get("args", {}).get("text", ""),
            "timestamp": s.get("args", {}).get("timestamp"),
            "from": s.get("args", {}).get("profile_name"),
        } for s in stories]
        return str({"unread_counts": counts, "notifications": items})
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def instagram_get_pending_follow_requests() -> str:
    """Get pending follow requests for your account (relevant for private accounts)."""
    if err := _require_login(): return err
    try:
        users = ig.cl.user_follow_requests()
        return str([_fmt_user(u) for u in users])
    except Exception as e:
        return f"Error fetching pending requests: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULING QUEUE (published by scripts/run_scheduler.py)
# ─────────────────────────────────────────────────────────────────────────────

_QUEUE_PATH = os.environ.get(
    "INSTAGRAM_MCP_QUEUE_PATH",
    os.path.join(_state_dir(), ".instagram_mcp_queue.json"),
)

def _load_queue() -> list:
    try:
        with open(_QUEUE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        return []

def _save_queue(items: list) -> None:
    with open(_QUEUE_PATH, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=2, ensure_ascii=False)
    try:
        os.chmod(_QUEUE_PATH, 0o600)
    except OSError:
        pass

def _parse_schedule_time(scheduled_at: str):
    """Parse an ISO-8601 string; naive values are treated as this machine's local time."""
    from datetime import datetime
    dt = datetime.fromisoformat(str(scheduled_at).strip())
    if dt.tzinfo is None:
        dt = dt.astimezone()  # attach the local timezone
    return dt

@mcp.tool()
def instagram_schedule_post(
    image_path_or_url: Annotated[str, Field(description="Image source: path, URL, base64/data:image, or inbox name/'latest'")],
    caption: Annotated[str, Field(description="Caption text for the scheduled post")],
    scheduled_at: Annotated[str, Field(description="When to publish — 'YYYY-MM-DD HH:MM' (local time) or an ISO 8601 timestamp")],
    kind: Annotated[str, Field(description="'post' (feed photo, default) or 'story'")] = "post",
    hashtags: Optional[str] = None,
    mentions: Optional[str] = None,
    location_name: Optional[str] = None,
) -> str:
    """
    Schedule a post or story for later (published by scripts/run_scheduler.py).

    - image_path_or_url: absolute local path (photo, or .mp4/.mov video)
    - scheduled_at: ISO-8601, e.g. "2026-10-05 18:30" (naive values use local time)
      or with an offset like "2026-10-05T18:30:00+05:00"
    - kind: "post" (feed) or "story"
    - caption/hashtags/mentions/location_name: same meaning as instagram_post_photo

    The item lands in the scheduling queue; run scripts/run_scheduler.py (for
    example via Windows Task Scheduler every minute) to publish due items.
    """
    if err := _require_login(): return err
    try:
        when = _parse_schedule_time(scheduled_at)
        raw = (image_path_or_url or "").strip().strip('"').strip("'")
        kind = (kind or "post").lower()
        if kind not in ("post", "story"):
            return "Error: kind must be 'post' or 'story'."
        if not raw.lower().startswith(("http://", "https://")):
            p = Path(os.path.expandvars(os.path.expanduser(raw)))
            if not p.is_file():
                return f"Error: local file not found: {p}"
            raw = str(p)
        items = _load_queue()
        item = {
            "id": f"q{int(time.time())}{random.randint(100, 999)}",
            "kind": kind,
            "image_path_or_url": raw,
            "caption": caption or "",
            "hashtags": hashtags,
            "mentions": mentions,
            "location_name": location_name,
            "scheduled_at": when.isoformat(),
            "scheduled_epoch": when.timestamp(),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "status": "pending",
            "result": None,
        }
        items.append(item)
        _save_queue(items)
        return str({
            "status": "scheduled",
            "queue_id": item["id"],
            "kind": kind,
            "scheduled_at": item["scheduled_at"],
            "queue_file": _QUEUE_PATH,
            "note": "Run scripts/run_scheduler.py when due (e.g. Task Scheduler every minute).",
        })
    except Exception as e:
        return _friendly_error(e, "scheduling the post")


@mcp.tool()
def instagram_get_risk_categories() -> str:
    """
    List every tool by bot-detection risk: red (highest), orange, then green.

    Red tools (public comments/replies on others, likes, follows/blocks, DMs,
    password logins, bulk search/explore/hashtag reads) are the main triggers for
    Instagram automation flags. They are paced heavily and share a daily red cap
    (INSTAGRAM_MCP_MAX_RED_ACTIONS_PER_DAY; Safe Mode default: 8).

    Use this to plan safe usage — prefer URL-based workflows and green/orange tools.
    """
    try:
        all_tools = sorted(n for n, v in globals().items()
                           if n.startswith("instagram_") and callable(v))
        red = {n: _TOOL_RISK_RED[n] for n in all_tools if n in _TOOL_RISK_RED}
        orange = {n: _TOOL_RISK_ORANGE[n] for n in all_tools if n in _TOOL_RISK_ORANGE}
        green = [n for n in all_tools if n not in red and n not in orange]
        rec = _load_write_count()
        return str({
            "red": red,
            "orange": orange,
            "green": green,
            "red_actions_today": rec.get("red", 0),
            "red_daily_cap": _red_daily_cap(),
            "total_write_actions_today": rec.get("count", 0),
            "total_daily_cap": _daily_write_cap(),
            "advice": ("Red tools are the bot-detection triggers: keep them rare, vary text, never loop, "
                       "and prefer the user providing post/reel URLs."),
        })
    except Exception as e:
        return f"Error building the risk report: {e}"


@mcp.tool()
def instagram_get_scheduled_posts() -> str:
    """List the scheduling queue (pending items plus past results)."""
    try:
        items = _load_queue()
        now = time.time()
        for it in items:
            it["due_in_seconds"] = int((it.get("scheduled_epoch") or 0) - now)
        return str({"queue_file": _QUEUE_PATH, "count": len(items), "items": items})
    except Exception as e:
        return f"Error reading the queue: {e}"


@mcp.tool()
def instagram_cancel_scheduled_post(queue_id: str, confirm: bool = False) -> str:
    """
    Remove an item from the scheduling queue.

    Same safety flow as deletions: preview with confirm=False, then confirm=True
    after the user approves.
    """
    try:
        items = _load_queue()
        target = next((it for it in items if str(it.get("id")) == str(queue_id)), None)
        if target is None:
            return f"Error: no queue item with id {queue_id}."
        if not confirm:
            return _deletion_preview("cancel_scheduled_post", queue_id, {
                "kind": target.get("kind"),
                "image_path_or_url": target.get("image_path_or_url"),
                "caption_preview": (target.get("caption") or "")[:120],
                "scheduled_at": target.get("scheduled_at"),
                "status": target.get("status"),
            })
        ok, msg = _consume_confirmation("cancel_scheduled_post", queue_id)
        if not ok:
            return msg
        _save_queue([it for it in items if str(it.get("id")) != str(queue_id)])
        return f"Scheduled item {queue_id} cancelled (user-approved)."
    except Exception as e:
        return f"Error cancelling the scheduled item: {e}"

# ─────────────────────────────────────────────────────────────────────────────
# 12. BLOB UPLOAD STAGING (the /upload page)
#     Browser sends files straight to Vercel Blob (no 4.5 MB serverless body
#     limit); these tools list / preview / publish / delete them. Rejected
#     files land in the problem log (list_problems). Unposted uploads are
#     purged after 7 days by the daily cron (api/cleanup.py).
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_uploads(status: Optional[str] = "pending") -> str:
    """
    List files staged on the /upload browser page that are waiting to be posted.

    Shows each upload's id, filename, size, kind (photo/reel), aspect and the
    caption the user typed when uploading. status: 'pending' (default),
    'posted', 'rejected', or empty string for all records.
    """
    try:
        from instagram_mcp_server import upload_store
        st = None if (status or "") in ("", "all", None) else status
        items = upload_store.list_uploads(status=st)
        out = [{
            "id": u.get("id"),
            "filename": u.get("filename"),
            "kind": u.get("kind"),
            "aspect": u.get("aspect"),
            "size_bytes": u.get("size"),
            "caption": u.get("caption"),
            "status": u.get("status", "pending"),
            "uploaded_at": time.strftime("%Y-%m-%d %H:%M UTC",
                                         time.gmtime(float(u.get("uploaded_at") or 0))),
        } for u in items]
        return str({"count": len(out), "uploads": out,
                    "next_step": "preview_upload(id) to see a thumbnail, post_upload(id) to publish"})
    except Exception as e:
        return _friendly_error(e, "listing uploads")


@mcp.tool()
def preview_upload(upload_id: str) -> Image:
    """
    Return a small JPEG thumbnail of a staged upload so you can eyeball the
    photo without fetching its URL. Videos get a short metadata summary instead.
    """
    try:
        from instagram_mcp_server import upload_store, media_validation
        rec = upload_store.get_upload(upload_id)
        if not rec:
            raise FileNotFoundError(f"No upload with id {upload_id!r} — check list_uploads")
        data = upload_store.fetch_bytes(rec)
        ctype = media_validation.sniff_content_type(data)
        if ctype.startswith("image/"):
            thumb = media_validation.thumbnail_bytes(data, max_side=256)
            path = _write_image_temp(thumb, ".jpg")
            return Image(path=path, format="jpeg")
        info = media_validation.validate_reel(data)
        summary = (f"Video '{rec.get('filename')}': format={info.get('format')}, "
                   f"codecs={info.get('codecs')}, acceptable_for_reels={info.get('ok')}"
                   + (f", reason={info.get('reason')}" if not info.get("ok") else ""))
        return Image(content=summary.encode(), format="txt")
    except FileNotFoundError as e:
        return Image(content=str(e).encode(), format="txt")
    except Exception as e:
        return Image(content=f"Error previewing upload: {e}".encode(), format="txt")


@mcp.tool()
def post_upload(upload_id: str, dry_run: Annotated[bool, Field(
    description="True = validate & convert WITHOUT posting; shows what would happen")] = False) -> str:
    """
    Publish a file staged through the /upload page. The server downloads the
    bytes from Blob, validates and converts them (photos → feed-ready JPEG at
    the chosen aspect via Pillow; reels must already be MP4/H.264+AAC — other
    reel formats are rejected and logged, never converted, since Vercel has no
    ffmpeg), posts to Instagram with the stored caption, then DELETES the Blob
    copy on success. Failures are recorded in the problem log (list_problems).
    """
    try:
        from instagram_mcp_server import upload_store, media_validation
        rec = upload_store.get_upload(upload_id)
        if not rec:
            return f"Error: no upload with id {upload_id!r}. Use list_uploads first."
        data = upload_store.fetch_bytes(rec)
        caption = rec.get("caption") or ""
        aspect = rec.get("aspect") or "auto"
        kind = rec.get("kind") or "photo"

        # ---- validate & convert -------------------------------------------
        prepared_path = None
        cleanup = False
        info: dict = {}
        if kind == "reel":
            v = media_validation.validate_reel(data)
            if not v.get("ok"):
                upload_store.add_problem(upload_id=upload_id, filename=rec.get("filename", ""),
                                         reason=v.get("reason", "invalid reel"), stage="validation")
                upload_store.set_status(upload_id, "rejected", note=v.get("reason", ""))
                return str({"status": "rejected",
                            "reason": v.get("reason"),
                            "hint": "Reels must be MP4 (H.264 video + AAC audio). "
                                    "Other formats are logged in list_problems — re-export and re-upload.",
                            "logged": True})
            suffix = ".mp4" if media_validation.sniff_content_type(data) == "video/mp4" else ".img"
            prepared_path = _write_image_temp(data, suffix)
            cleanup = True
        else:
            try:
                jpeg, info = media_validation.prepare_photo_bytes(data, aspect)
            except ValueError as e:
                upload_store.add_problem(upload_id=upload_id, filename=rec.get("filename", ""),
                                         reason=str(e), stage="validation")
                upload_store.set_status(upload_id, "rejected", note=str(e))
                return str({"status": "rejected", "reason": str(e), "logged": True})
            prepared_path = _write_image_temp(jpeg, ".jpg")
            cleanup = True

        if dry_run:
            return str({"status": "preview", "dry_run": True, "upload_id": upload_id,
                        "kind": kind, "caption_preview": caption[:200], "aspect": aspect,
                        "conversion": info or {"container": "mp4", "codecs": ["h264"]},
                        "next_step": f"call post_upload('{upload_id}', dry_run=False) to publish"})

        # ---- require login & post -------------------------------------------
        if err := _require_login():
            return err
        pause = _pacing_error("post")
        if pause:
            return pause
        try:
            full_caption = caption
            waited = _pace_action("post")
            if kind == "reel":
                media = ig.cl.clip_upload(prepared_path, full_caption)
                url = f"https://www.instagram.com/reel/{media.code}/"
            else:
                media = ig.cl.photo_upload(prepared_path, full_caption)
                url = f"https://www.instagram.com/p/{media.code}/"
        except Exception as e:
            upload_store.add_problem(upload_id=upload_id, filename=rec.get("filename", ""),
                                     reason=f"Instagram upload failed: {e}", stage="posting")
            upload_store.set_status(upload_id, "failed", note=str(e)[:200])
            return _friendly_error(e, "posting the upload")
        finally:
            if prepared_path and cleanup:
                _remove_file(prepared_path)

        # ---- cleanup: Blob copy is no longer needed after a successful post --
        blob_deleted = True
        try:
            upload_store.delete_blob_file(rec)
        except Exception:
            blob_deleted = False
        upload_store.remove_upload(upload_id)
        return str({
            "status": "success", "kind": kind,
            "media_id": str(media.pk), "url": url,
            "caption_preview": full_caption[:120],
            "conversion": info or None,
            "blob_copy_deleted": blob_deleted,
            "paced_seconds": waited,
        })
    except Exception as e:
        return _friendly_error(e, "posting the upload")


@mcp.tool()
def delete_upload(upload_id: str) -> str:
    """
    Remove a staged upload: deletes the media file from Vercel Blob and drops
    it from the pending index. Use when the user says 'don't post that one'.
    """
    try:
        from instagram_mcp_server import upload_store
        rec = upload_store.get_upload(upload_id)
        if not rec:
            return f"Error: no upload with id {upload_id!r}."
        try:
            upload_store.delete_blob_file(rec)
        except Exception as e:
            return f"Error: could not delete the Blob file ({e}). The record was kept."
        upload_store.remove_upload(upload_id)
        return str({"status": "deleted", "id": upload_id, "filename": rec.get("filename")})
    except Exception as e:
        return _friendly_error(e, "deleting the upload")


@mcp.tool()
def list_problems(limit: int = 20) -> str:
    """
    Show uploads that were rejected (and why): wrong reel format, corrupt
    image, failed Instagram upload... Each entry names the file, the stage
    (validation/posting) and a human-readable reason. Tell the user which
    files need re-exporting/re-uploading.
    """
    try:
        from instagram_mcp_server import upload_store
        items = upload_store.list_problems(limit=max(1, min(int(limit or 20), 100)))
        out = [{
            "filename": p.get("filename"),
            "upload_id": p.get("upload_id"),
            "stage": p.get("stage"),
            "reason": p.get("reason"),
            "at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(float(p.get("at") or 0))),
        } for p in items]
        return str({"count": len(out), "problems": out})
    except Exception as e:
        return _friendly_error(e, "listing problems")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
