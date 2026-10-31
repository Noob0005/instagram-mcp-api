"""
upload_store.py
---------------
Staging area for media files uploaded through the browser /upload page.

Flow:
  1. The browser PUTs/POSTs the file directly to Vercel Blob (the /upload page
     asks the server for a signed Blob upload URL first), which bypasses
     Vercel's ~4.5 MB serverless request-body limit.
  2. The browser then registers the upload with the server, sending only
     metadata: caption, aspect ratio and kind (photo|reel). That lands here as
     an entry in the upload index (a private, hard-to-guess file in the Blob store).
  3. An agent lists pending files with the list_uploads tool, previews them
     with preview_upload, and publishes with post_upload — which downloads the
     bytes on the server, validates + converts them, posts to Instagram and
     deletes the Blob copy.
  4. Anything rejected (bad image, non-MP4 reel, corrupt file) is recorded in
     the problem log (a private, hard-to-guess file) and shown by list_problems.
  5. An upload that is not posted is deleted INSTAGRAM_MCP_UNPOSTED_HOURS after it was staged
     (48 by default): by the daily cron, and whenever the upload list is read. Uploads can also be
     deleted by hand (the upload Library, or the delete_uploads MCP tool).

Local/disk mode: when Blob is not configured, entries are kept in a JSON file
under the state dir and files are expected on local disk (`local_path`). This
keeps the tools usable on desktop/Termux without any cloud storage.
"""

import copy
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from instagram_mcp_server import blob_store

INDEX_DEFAULT: Dict[str, Any] = {"uploads": []}
PROBLEMS_DEFAULT: Dict[str, Any] = {"problems": []}


def _log(msg: str) -> None:
    print(f"[upload_store] {msg}", file=sys.stderr)


def blob_available() -> bool:
    return blob_store.blob_configured()


# ---------------------------------------------------------------------------
# Local fallback store (no Blob configured)
# ---------------------------------------------------------------------------

def _local_index_path() -> str:
    override = os.environ.get("INSTAGRAM_MCP_UPLOAD_INDEX_PATH", "").strip()
    if override:
        return override
    base = tempfile.gettempdir() if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") \
        else os.path.expanduser("~")
    return os.path.join(base, "instagram_mcp_uploads.json")


def _read_local(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _write_local(path: str, doc: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Upload records
# ---------------------------------------------------------------------------

def add_upload(*, filename: str, pathname: str, url: Optional[str], size: int,
               content_type: str, caption: str, aspect: str, kind: str,
               local_path: Optional[str] = None,
               thumb_pathname: Optional[str] = None) -> Dict[str, Any]:
    """Register one staged upload. Returns the created record."""
    rec = {
        "id": blob_store.new_upload_id(),
        "filename": blob_store.safe_filename(filename),
        "pathname": pathname,
        "url": None,  # not stored: a public Blob address would let anyone who reads the index open the photo
        "size": int(size or 0),
        "content_type": content_type,
        "caption": caption or "",
        "aspect": aspect or "auto",
        "kind": kind if kind in ("photo", "reel") else "photo",
        "uploaded_at": time.time(),
        "expires_at": time.time() + keep_hours() * 3600,
        "status": "pending",
        "local_path": local_path,
        "thumb_pathname": thumb_pathname or None,
    }

    def mutate(index):
        if isinstance(index, dict):
            items = index.get("uploads")
            if not isinstance(items, list):
                items = []
            items.insert(0, rec)
            index["uploads"] = items[:500]
            return index
        return None

    if blob_available():
        blob_store.update_json(blob_store.index_key(), mutate, copy.deepcopy(INDEX_DEFAULT))
    else:
        _mutate_local(mutate)
    return rec


UNPOSTED_HOURS_DEFAULT = 48


def keep_hours() -> float:
    """How long an upload that is not posted is kept: INSTAGRAM_MCP_UNPOSTED_HOURS (48 by default, 1 to 168)."""
    try:
        value = float(os.environ.get("INSTAGRAM_MCP_UNPOSTED_HOURS", UNPOSTED_HOURS_DEFAULT))
    except ValueError:
        value = UNPOSTED_HOURS_DEFAULT
    return min(max(value, 1.0), 168.0)


def expires_at_of(rec: Dict[str, Any]) -> float:
    """When an upload is deleted: the time stored with it, or uploaded_at plus the keep time."""
    stored = float(rec.get("expires_at") or 0)
    return stored if stored else float(rec.get("uploaded_at") or 0) + keep_hours() * 3600


def purge_expired(now: Optional[float] = None) -> Dict[str, Any]:
    """Delete uploads whose time is up: the file in the Blob store (or on disk), then the record.

    A posted upload's file is already gone, so only its record goes. A file that cannot be deleted keeps
    its record, so the next run tries again. Runs from the daily cron and before each upload list."""
    now = time.time() if now is None else now
    due = [u for u in list_uploads(status=None) if expires_at_of(u) <= now]
    removed: List[Any] = []
    failed: List[Dict[str, Any]] = []
    for rec in due:
        if rec.get("status") != "posted":
            try:
                delete_blob_file(rec)
            except Exception as exc:
                failed.append({"id": rec.get("id"), "error": str(exc)[:200]})
                continue
        removed.append(rec.get("id"))
    if removed:
        remove_uploads(removed)
    _log(f"purge: removed {len(removed)}, could not remove {len(failed)}")
    return {"removed": len(removed), "failed": failed, "keep_hours": keep_hours()}


def _mutate_local(mutate) -> None:
    """Apply `mutate` to the local index bucket only."""
    path = _local_index_path()
    doc = _read_local(path, {"index": copy.deepcopy(INDEX_DEFAULT), "problems": copy.deepcopy(PROBLEMS_DEFAULT)})
    index = doc.get("index") or copy.deepcopy(INDEX_DEFAULT)
    out = mutate(index)
    if out is not None:
        doc["index"] = out
    _write_local(path, doc)


def _mutate_local_problems(mutate) -> None:
    path = _local_index_path()
    doc = _read_local(path, {"index": copy.deepcopy(INDEX_DEFAULT), "problems": copy.deepcopy(PROBLEMS_DEFAULT)})
    problems = doc.get("problems") or copy.deepcopy(PROBLEMS_DEFAULT)
    out = mutate(problems)
    if out is not None:
        doc["problems"] = out
    _write_local(path, doc)


def list_uploads(status: Optional[str] = "pending") -> List[Dict[str, Any]]:
    if blob_available():
        doc = blob_store.get_json(blob_store.index_key(), copy.deepcopy(INDEX_DEFAULT)) or copy.deepcopy(INDEX_DEFAULT)
    else:
        doc = _read_local(_local_index_path(), {}).get("index") or copy.deepcopy(INDEX_DEFAULT)
    items = [u for u in (doc.get("uploads") or []) if isinstance(u, dict)]
    if status:
        items = [u for u in items if u.get("status", "pending") == status]
    return items


def get_upload(upload_id: str) -> Optional[Dict[str, Any]]:
    for u in list_uploads(status=None):
        if u.get("id") == upload_id:
            return u
    return None


def set_status(upload_id: str, status: str, note: str = "") -> bool:
    changed = {"v": False}

    def mutate(index):
        if not isinstance(index, dict):
            return None
        for u in index.get("uploads") or []:
            if u.get("id") == upload_id:
                u["status"] = status
                u["updated_at"] = time.time()
                if note:
                    u["note"] = note
                changed["v"] = True
        return index

    if blob_available():
        blob_store.update_json(blob_store.index_key(), mutate, copy.deepcopy(INDEX_DEFAULT))
    else:
        _mutate_local(mutate)
    return changed["v"]


def set_caption(upload_id: str, caption: str) -> bool:
    """Replace the caption of a pending upload. Returns True when the upload was found."""
    changed = {"v": False}

    def mutate(index):
        if not isinstance(index, dict):
            return None
        for u in index.get("uploads") or []:
            if u.get("id") == upload_id:
                u["caption"] = caption or ""
                u["updated_at"] = time.time()
                changed["v"] = True
        return index

    if blob_available():
        blob_store.update_json(blob_store.index_key(), mutate, copy.deepcopy(INDEX_DEFAULT))
    else:
        _mutate_local(mutate)
    return changed["v"]


def set_title(upload_id: str, title: str) -> bool:
    """Set the display name shown on the upload page. The stored file is not renamed. True when found."""
    changed = {"v": False}

    def mutate(index):
        if not isinstance(index, dict):
            return None
        for u in index.get("uploads") or []:
            if u.get("id") == upload_id:
                u["title"] = (title or "").strip()[:120]
                u["updated_at"] = time.time()
                changed["v"] = True
        return index

    if blob_available():
        blob_store.update_json(blob_store.index_key(), mutate, copy.deepcopy(INDEX_DEFAULT))
    else:
        _mutate_local(mutate)
    return changed["v"]


def fetch_thumb(rec: Dict[str, Any]) -> Optional[bytes]:
    """Return the stored thumbnail bytes, or None when the upload has none."""
    if not rec.get("thumb_pathname") or not blob_available():
        return None
    try:
        return blob_store.get_bytes(rec["thumb_pathname"])
    except Exception:
        return None


def remove_upload(upload_id: str) -> Optional[Dict[str, Any]]:
    """Drop a record from the index and return it (for deleting the Blob file)."""
    removed: List[Dict[str, Any]] = []

    def mutate(index):
        if not isinstance(index, dict):
            return None
        keep = []
        for u in index.get("uploads") or []:
            if u.get("id") == upload_id:
                removed.append(u)
            else:
                keep.append(u)
        index["uploads"] = keep
        return index

    if blob_available():
        blob_store.update_json(blob_store.index_key(), mutate, copy.deepcopy(INDEX_DEFAULT))
    else:
        _mutate_local(mutate)
    return removed[0] if removed else None


# ---------------------------------------------------------------------------
# Problem log
# ---------------------------------------------------------------------------

def add_problem(*, upload_id: Optional[str], filename: str, reason: str,
                stage: str = "validation", details: str = "") -> Dict[str, Any]:
    rec = {
        "id": blob_store.new_upload_id(),
        "upload_id": upload_id,
        "filename": filename,
        "reason": reason,
        "stage": stage,
        "details": details[:500],
        "at": time.time(),
    }

    def mutate(problems):
        if not isinstance(problems, dict):
            return None
        items = problems.get("problems")
        if not isinstance(items, list):
            items = []
        items.insert(0, rec)
        problems["problems"] = items[:200]
        return problems

    if blob_available():
        blob_store.update_json(blob_store.problems_key(), mutate, copy.deepcopy(PROBLEMS_DEFAULT))
    else:
        _mutate_local_problems(mutate)
    return rec


def list_problems(limit: int = 50) -> List[Dict[str, Any]]:
    if blob_available():
        doc = blob_store.get_json(blob_store.problems_key(), copy.deepcopy(PROBLEMS_DEFAULT)) or copy.deepcopy(PROBLEMS_DEFAULT)
    else:
        doc = _read_local(_local_index_path(), {}).get("problems") or copy.deepcopy(PROBLEMS_DEFAULT)
    items = [p for p in (doc.get("problems") or []) if isinstance(p, dict)]
    return items[:limit]


# ---------------------------------------------------------------------------
# Fetching bytes / cleanup
# ---------------------------------------------------------------------------

def fetch_bytes(rec: Dict[str, Any]) -> bytes:
    """Download the staged file (Blob) or read it from local disk."""
    local = rec.get("local_path")
    if local and os.path.exists(local):
        with open(local, "rb") as fh:
            return fh.read()
    if rec.get("pathname"):
        return blob_store.get_bytes(rec["pathname"])
    raise FileNotFoundError(f"Upload {rec.get('id')} has no stored file")


def delete_blob_file(rec: Dict[str, Any]) -> None:
    """Remove the staged media object itself (not the index record)."""
    target = rec.get("pathname") or rec.get("url")
    if blob_available():
        if rec.get("thumb_pathname"):
            try:
                blob_store.delete(rec["thumb_pathname"])
            except Exception:
                pass
        if target:
            blob_store.delete(target)
    if not target:
        return
    local = rec.get("local_path")
    if local:
        try:
            os.remove(local)
        except OSError:
            pass


def _storage_limit_gb() -> float:
    """The plan's storage allowance. Hobby includes 1 GB; override with INSTAGRAM_MCP_STORAGE_LIMIT_GB."""
    try:
        return max(0.001, float(os.environ.get("INSTAGRAM_MCP_STORAGE_LIMIT_GB", "1")))
    except ValueError:
        return 1.0


def storage_usage() -> Dict[str, Any]:
    """Bytes used by staged files (media and previews) against the storage allowance."""
    if blob_available():
        objects = blob_store.list_prefix(blob_store.PREFIX + "/uploads/")  # capped at 1000 objects
        used = sum(int(o.get("size") or 0) for o in objects)
        count = len(objects)
    else:
        items = list_uploads(status=None)
        used = sum(int(u.get("size") or 0) for u in items)
        count = len(items)
    limit_gb = _storage_limit_gb()
    limit = int(limit_gb * 1024 ** 3)
    return {
        "used_mb": round(used / 1024 ** 2, 1),
        "free_mb": round(max(0, limit - used) / 1024 ** 2, 1),
        "limit_gb": limit_gb,
        "percent_used": round(100 * used / limit, 1),
        "files": count,
        "count_is_capped": blob_available() and count >= 1000,
    }


def describe_uploads(upload_ids: List[str]) -> Dict[str, Any]:
    """What would be deleted for these ids. Nothing is changed."""
    by_id = {u.get("id"): u for u in list_uploads(status=None)}
    found, missing = [], []
    for upload_id in dict.fromkeys(upload_ids):  # dedupe, keep order
        rec = by_id.get(upload_id)
        if rec is None:
            missing.append(upload_id)
            continue
        found.append({
            "id": rec.get("id"), "filename": rec.get("filename"), "kind": rec.get("kind"),
            "size_mb": round(int(rec.get("size") or 0) / 1024 ** 2, 2),
            "caption": rec.get("caption") or "",
            "uploaded_at": float(rec.get("uploaded_at") or 0),
        })
    total = sum(f["size_mb"] for f in found)
    return {"files": found, "missing": missing, "total_mb": round(total, 2)}


def remove_uploads(upload_ids: List[str]) -> None:
    """Drop several records from the index in one write. The files must already be gone."""
    wanted = set(upload_ids)
    if not wanted:
        return

    def mutate(index):
        if not isinstance(index, dict):
            return None
        index["uploads"] = [u for u in (index.get("uploads") or []) if u.get("id") not in wanted]
        return index

    if blob_available():
        blob_store.update_json(blob_store.index_key(), mutate, copy.deepcopy(INDEX_DEFAULT))
    else:
        _mutate_local(mutate)


def delete_uploads(upload_ids: List[str]) -> Dict[str, Any]:
    """Delete the files and their records for these ids. Callers must have confirmed first.

    A file that cannot be deleted keeps its record, so it stays visible and can be retried.
    """
    by_id = {u.get("id"): u for u in list_uploads(status=None)}
    failed, gone = [], []
    for upload_id in dict.fromkeys(upload_ids):  # dedupe, keep order
        rec = by_id.get(upload_id)
        if rec is None:
            failed.append({"id": upload_id, "error": "no such upload"})
            continue
        try:
            delete_blob_file(rec)
        except Exception as exc:
            failed.append({"id": upload_id, "filename": rec.get("filename"), "error": str(exc)[:200]})
            continue
        gone.append(rec)
    if gone:
        remove_uploads([r.get("id") for r in gone])
    deleted = [{"id": r.get("id"), "filename": r.get("filename")} for r in gone]
    freed = sum(int(r.get("size") or 0) for r in gone)
    return {"deleted": deleted, "failed": failed, "freed_mb": round(freed / 1024 ** 2, 2)}

