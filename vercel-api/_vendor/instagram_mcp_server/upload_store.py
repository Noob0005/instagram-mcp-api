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
     an entry in <prefix>/uploads/index.json.
  3. An agent lists pending files with the list_uploads tool, previews them
     with preview_upload, and publishes with post_upload — which downloads the
     bytes on the server, validates + converts them, posts to Instagram and
     deletes the Blob copy.
  4. Anything rejected (bad image, non-MP4 reel, corrupt file) is recorded in
     <prefix>/uploads/problems.json and shown by list_problems.
  5. A daily cron (api/cleanup.py) drops unposted uploads older than 7 days.

Local/disk mode: when Blob is not configured, entries are kept in a JSON file
under the state dir and files are expected on local disk (`local_path`). This
keeps the tools usable on desktop/Termux without any cloud storage.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from instagram_mcp_server import blob_store

MAX_AGE_DAYS_DEFAULT = 7
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
               local_path: Optional[str] = None) -> Dict[str, Any]:
    """Register one staged upload. Returns the created record."""
    rec = {
        "id": blob_store.new_upload_id(),
        "filename": blob_store.safe_filename(filename),
        "pathname": pathname,
        "url": url,
        "size": int(size or 0),
        "content_type": content_type,
        "caption": caption or "",
        "aspect": aspect or "auto",
        "kind": kind if kind in ("photo", "reel") else "photo",
        "uploaded_at": time.time(),
        "status": "pending",
        "local_path": local_path,
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
        blob_store.update_json(blob_store.index_key(), mutate, INDEX_DEFAULT.copy())
    else:
        _mutate_local(mutate)
    return rec


def _mutate_local(mutate) -> None:
    """Apply `mutate` to the local index bucket only."""
    path = _local_index_path()
    doc = _read_local(path, {"index": INDEX_DEFAULT.copy(), "problems": PROBLEMS_DEFAULT.copy()})
    index = doc.get("index") or INDEX_DEFAULT.copy()
    out = mutate(index)
    if out is not None:
        doc["index"] = out
    _write_local(path, doc)


def _mutate_local_problems(mutate) -> None:
    path = _local_index_path()
    doc = _read_local(path, {"index": INDEX_DEFAULT.copy(), "problems": PROBLEMS_DEFAULT.copy()})
    problems = doc.get("problems") or PROBLEMS_DEFAULT.copy()
    out = mutate(problems)
    if out is not None:
        doc["problems"] = out
    _write_local(path, doc)


def list_uploads(status: Optional[str] = "pending") -> List[Dict[str, Any]]:
    if blob_available():
        doc = blob_store.get_json(blob_store.index_key(), INDEX_DEFAULT.copy()) or INDEX_DEFAULT.copy()
    else:
        doc = _read_local(_local_index_path(), {}).get("index") or INDEX_DEFAULT.copy()
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
        blob_store.update_json(blob_store.index_key(), mutate, INDEX_DEFAULT.copy())
    else:
        _mutate_local(mutate)
    return changed["v"]


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
        blob_store.update_json(blob_store.index_key(), mutate, INDEX_DEFAULT.copy())
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
        blob_store.update_json(blob_store.problems_key(), mutate, PROBLEMS_DEFAULT.copy())
    else:
        _mutate_local_problems(mutate)
    return rec


def list_problems(limit: int = 50) -> List[Dict[str, Any]]:
    if blob_available():
        doc = blob_store.get_json(blob_store.problems_key(), PROBLEMS_DEFAULT.copy()) or PROBLEMS_DEFAULT.copy()
    else:
        doc = _read_local(_local_index_path(), {}).get("problems") or PROBLEMS_DEFAULT.copy()
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
    if not target:
        return
    if blob_available():
        blob_store.delete(target)
    local = rec.get("local_path")
    if local:
        try:
            os.remove(local)
        except OSError:
            pass


def purge_expired(days: int = MAX_AGE_DAYS_DEFAULT) -> Dict[str, Any]:
    """Delete uploads older than `days` that were never posted. Cron-friendly."""
    cutoff = time.time() - days * 86400
    deleted: List[str] = []
    errors: List[str] = []

    def mutate(index):
        if not isinstance(index, dict):
            return None
        keep = []
        for u in index.get("uploads") or []:
            ts = float(u.get("uploaded_at") or 0)
            if ts < cutoff and u.get("status") != "posted":
                try:
                    delete_blob_file(u)
                    deleted.append(str(u.get("id")))
                except Exception as e:
                    errors.append(f"{u.get('id')}: {e}")
                    keep.append(u)  # keep the record so the next run can retry
            else:
                keep.append(u)
        index["uploads"] = keep
        return index

    if blob_available():
        blob_store.update_json(blob_store.index_key(), mutate, INDEX_DEFAULT.copy())
    else:
        _mutate_local(mutate)
    return {"deleted": deleted, "errors": errors, "cutoff_days": days}
