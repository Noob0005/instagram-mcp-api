"""Offline tests: the upload page's list, rename, delete and preview/view reads (local mode, no Blob)."""
import asyncio
import json
import os
import sys
import tempfile
import time
import unittest

_TMP = tempfile.mkdtemp()
os.environ["INSTAGRAM_MCP_UPLOAD_INDEX_PATH"] = os.path.join(_TMP, "index.json")
os.environ["INSTAGRAM_MCP_UPLOAD_SETTINGS_PATH"] = os.path.join(_TMP, "settings.json")
os.environ.pop("BLOB_READ_WRITE_TOKEN", None)
os.environ["MCP_AUTH_KEY"] = "test-key-for-upload-settings-0123"  # same value as test_upload_settings.py
os.environ.pop("MCP_ALLOW_UNAUTHENTICATED", None)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vercel-api", "api"))

from instagram_mcp_server import upload_settings, upload_store  # noqa: E402
import upload as upload_api  # noqa: E402

INDEX = os.environ["INSTAGRAM_MCP_UPLOAD_INDEX_PATH"]
SETTINGS = os.environ["INSTAGRAM_MCP_UPLOAD_SETTINGS_PATH"]
KEY = os.environ["MCP_AUTH_KEY"]
HOUR = 3600


def reset():
    # Read the paths now, not at import: both test modules set the same variables when they load.
    for var in ("INSTAGRAM_MCP_UPLOAD_INDEX_PATH", "INSTAGRAM_MCP_UPLOAD_SETTINGS_PATH"):
        path = os.environ[var]
        if os.path.exists(path):
            os.remove(path)


def add(name, hours_old=1, size=1, thumb=None):
    rec = upload_store.add_upload(
        filename=name, pathname=f"instagram-mcp/uploads/{name}", url=None, size=size,
        content_type="image/jpeg", caption="cap", aspect="auto", kind="photo",
        thumb_pathname=thumb)
    def mutate(index):
        for u in index["uploads"]:
            if u["id"] == rec["id"]:
                u["uploaded_at"] = time.time() - hours_old * HOUR
        return index
    upload_store._mutate_local(mutate)
    return rec["id"]


def call(method="POST", body=None, query="", key=KEY):
    headers = []
    if key is not None:
        headers.append((b"x-auth-key", key.encode()))
    scope = {"type": "http", "method": method, "path": "/api/upload", "headers": headers,
             "query_string": query.encode()}
    payload = json.dumps(body or {}).encode()
    sent = []

    async def receive():
        return {"type": "http.request", "body": payload if method == "POST" else b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(upload_api.app(scope, receive, send))
    status = sent[0]["status"]
    raw = sent[1]["body"]
    try:
        return status, json.loads(raw.decode())
    except ValueError:
        return status, raw


class ListTests(unittest.TestCase):
    def setUp(self):
        reset()

    def test_list_shows_pending_uploads_with_their_expiry(self):
        add("fresh.jpg", hours_old=1)
        status, data = call(body={"action": "list"})
        self.assertEqual(status, 200)
        self.assertEqual(data["retention_hours"], 48)
        self.assertEqual([u["filename"] for u in data["uploads"]], ["fresh.jpg"])
        item = data["uploads"][0]
        self.assertAlmostEqual(item["expires_at"] - item["uploaded_at"], 48 * HOUR, delta=5)
        self.assertFalse(item["has_thumb"])

    def test_list_removes_uploads_past_the_retention_first(self):
        add("old.jpg", hours_old=60)
        add("new.jpg", hours_old=2)
        _, data = call(body={"action": "list"})
        self.assertEqual([u["filename"] for u in data["uploads"]], ["new.jpg"])

    def test_a_changed_retention_changes_the_expiry_shown(self):
        add("a.jpg", hours_old=1)
        upload_settings.set_retention_hours(72)
        _, data = call(body={"action": "list"})
        item = data["uploads"][0]
        self.assertAlmostEqual(item["expires_at"] - item["uploaded_at"], 72 * HOUR, delta=5)


class RenameDeleteTests(unittest.TestCase):
    def setUp(self):
        reset()

    def test_rename_sets_the_display_name_and_keeps_the_file_name(self):
        uid = add("IMG_0042.jpg")
        status, _ = call(body={"action": "rename", "id": uid, "title": "  Beach day  "})
        self.assertEqual(status, 200)
        item = call(body={"action": "list"})[1]["uploads"][0]
        self.assertEqual(item["title"], "Beach day")
        self.assertEqual(item["filename"], "IMG_0042.jpg")

    def test_rename_an_unknown_upload_is_a_404(self):
        status, data = call(body={"action": "rename", "id": "nope", "title": "x"})
        self.assertEqual(status, 404)
        self.assertFalse(data["ok"])

    def test_delete_removes_the_upload(self):
        uid = add("gone.jpg")
        status, _ = call(body={"action": "delete", "id": uid})
        self.assertEqual(status, 200)
        self.assertEqual(call(body={"action": "list"})[1]["uploads"], [])

    def test_delete_an_unknown_upload_is_a_404(self):
        self.assertEqual(call(body={"action": "delete", "id": "nope"})[0], 404)


class MediaReadTests(unittest.TestCase):
    def setUp(self):
        reset()

    def test_media_needs_the_key(self):
        uid = add("a.jpg")
        self.assertEqual(call("GET", query=f"thumb={uid}", key=None)[0], 401)

    def test_a_thumbnail_is_404_when_the_upload_has_none(self):
        uid = add("a.jpg")
        self.assertEqual(call("GET", query=f"thumb={uid}")[0], 404)

    def test_reads_need_thumb_or_file_and_a_known_id(self):
        self.assertEqual(call("GET", query="")[0], 400)
        self.assertEqual(call("GET", query="file=missing")[0], 404)

    def test_a_file_too_big_for_the_function_gets_a_clear_answer(self):
        uid = add("big.mp4", size=6 * 1024 * 1024)
        status, data = call("GET", query=f"file={uid}")
        self.assertEqual(status, 413)
        self.assertEqual(data["error"], "too_big_to_view")

    def test_other_methods_are_refused(self):
        self.assertEqual(call("PUT", body={})[0], 405)


if __name__ == "__main__":
    unittest.main()
