"""
upload_settings.py
------------------
How long uploads stay before they are deleted (the "retention").

Default: 48 hours. The owner can change it on the upload settings page. The value is stored as a
small JSON document in Blob, next to the upload index. Without Blob (desktop/Termux, tests) a local
JSON file is used instead.

The daily cron (api/cleanup.py) reads this value and deletes unposted uploads older than it.
Changing the value applies to uploads that already exist, because the age is measured from upload time.
"""

import json
import os
import sys
import tempfile
from typing import Any, Dict

from instagram_mcp_server import blob_store

DEFAULT_RETENTION_HOURS = 48
MIN_RETENTION_HOURS = 1
MAX_RETENTION_HOURS = 24 * 30  # one month


def _log(msg: str) -> None:
    print(f"[upload_settings] {msg}", file=sys.stderr)


def settings_key() -> str:
    return f"{blob_store.PREFIX}/upload-settings.json"


def _local_path() -> str:
    override = os.environ.get("INSTAGRAM_MCP_UPLOAD_SETTINGS_PATH", "").strip()
    if override:
        return override
    base = tempfile.gettempdir() if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") \
        else os.path.expanduser("~")
    return os.path.join(base, "instagram_mcp_upload_settings.json")


def _read() -> Dict[str, Any]:
    if blob_store.blob_configured():
        doc = blob_store.get_json(settings_key(), None)
    else:
        try:
            with open(_local_path(), encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            doc = None
    return doc if isinstance(doc, dict) else {}


def _write(doc: Dict[str, Any]) -> None:
    if blob_store.blob_configured():
        blob_store.put_json(settings_key(), doc)
        return
    with open(_local_path(), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def retention_hours() -> int:
    """The saved retention in hours, or the default when nothing valid is saved."""
    value = _read().get("retention_hours")
    if isinstance(value, int) and not isinstance(value, bool) and MIN_RETENTION_HOURS <= value <= MAX_RETENTION_HOURS:
        return value
    return DEFAULT_RETENTION_HOURS


def describe() -> Dict[str, Any]:
    """Everything the settings page needs to show the current value and its limits."""
    return {
        "retention_hours": retention_hours(),
        "default_hours": DEFAULT_RETENTION_HOURS,
        "min_hours": MIN_RETENTION_HOURS,
        "max_hours": MAX_RETENTION_HOURS,
    }


def set_retention_hours(hours: Any) -> Dict[str, Any]:
    """Save a whole number of hours. Raises ValueError with a plain message when it is not allowed."""
    try:
        value = int(str(hours).strip())
    except (TypeError, ValueError):
        raise ValueError("Enter a whole number of hours.")
    if not MIN_RETENTION_HOURS <= value <= MAX_RETENTION_HOURS:
        raise ValueError(f"Choose between {MIN_RETENTION_HOURS} and {MAX_RETENTION_HOURS} hours.")
    _write({"retention_hours": value})
    _log(f"retention set to {value} h")
    return describe()
