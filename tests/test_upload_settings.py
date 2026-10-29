"""Offline tests: upload retention (48 h default), the purge cutoff, and the settings API.

Local mode only (no Blob token), so nothing leaves the machine.
"""
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
os.environ["MCP_AUTH_KEY"] = "test-key-for-upload-settings-0123"
os.environ.pop("MCP_ALLOW_UNAUTHENTICATED", None)

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(_ROOT, "vercel-api", "api"))

from instagram_mcp_server import upload_settings, upload_store  # noqa: E402
import upload as upload_api  # noqa: E402  (vercel-api/api/upload.py)

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


def add_aged(name, hours_old, status="pending"):
    """One upload whose age is `hours_old` hours (the index stores the upload time)."""
    rec = upload_store.add_upload(
        filename=name, pathname=f"instagram-mcp/uploads/{name}", url=None, size=1,
        content_type="image/jpeg", caption="", aspect="auto", kind="photo")
    def mutate(index):
        for u in index["uploads"]:
            if u["id"] == rec["id"]:
                u["uploaded_at"] = time.time() - hours_old * HOUR
                u["status"] = status
        return index
    upload_store._mutate_local(mutate)
    return rec["id"]


def remaining():
    return sorted(u["filename"] for u in upload_store.list_uploads(status=None))


class RetentionSettingTests(unittest.TestCase):
    def setUp(self):
        reset()

    def test_the_default_is_48_hours(self):
        self.assertEqual(upload_settings.retention_hours(), 48)
        self.assertEqual(upload_settings.describe()["default_hours"], 48)

    def test_a_saved_value_is_used(self):
        upload_settings.set_retention_hours("72")
        self.assertEqual(upload_settings.retention_hours(), 72)

    def test_values_outside_the_limits_or_not_whole_are_refused(self):
        for bad in (0, 721, "abc", "48.5", True, None):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                upload_settings.set_retention_hours(bad)
        self.assertEqual(upload_settings.retention_hours(), 48)

    def test_a_damaged_settings_file_falls_back_to_the_default(self):
        with open(SETTINGS, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(upload_settings.retention_hours(), 48)


class PurgeCutoffTests(unittest.TestCase):
    def setUp(self):
        reset()

    def test_uploads_older_than_48_hours_are_purged_by_default(self):
        add_aged("old.jpg", 50)
        add_aged("recent.jpg", 30)
        add_aged("posted.jpg", 500, status="posted")
        result = upload_store.purge_expired()
        self.assertEqual(result["retention_hours"], 48)
        self.assertEqual(len(result["deleted"]), 1)
        self.assertEqual(remaining(), ["posted.jpg", "recent.jpg"])

    def test_a_longer_saved_retention_keeps_uploads_that_would_have_expired(self):
        add_aged("a.jpg", 50)
        add_aged("b.jpg", 80)
        upload_settings.set_retention_hours(72)
        upload_store.purge_expired()
        self.assertEqual(remaining(), ["a.jpg"])

    def test_the_purge_uses_the_value_it_is_given_when_one_is_passed(self):
        add_aged("a.jpg", 5)
        upload_store.purge_expired(hours=4)
        self.assertEqual(remaining(), [])


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        reset()

    def call(self, body, key=KEY):
        headers = [(b"content-type", b"application/json")]
        if key is not None:
            headers.append((b"x-auth-key", key.encode()))
        scope = {"type": "http", "method": "POST", "path": "/api/upload", "headers": headers, "query_string": b""}
        payload = json.dumps(body).encode()
        sent = []

        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}

        async def send(message):
            sent.append(message)

        asyncio.run(upload_api.app(scope, receive, send))
        status = sent[0]["status"]
        data = json.loads(sent[1]["body"].decode())
        return status, data

    def test_the_settings_need_the_upload_key(self):
        status, _ = self.call({"action": "settings"}, key=None)
        self.assertEqual(status, 401)
        status, _ = self.call({"action": "settings"}, key="wrong")
        self.assertEqual(status, 401)

    def test_the_page_can_read_the_retention(self):
        status, data = self.call({"action": "settings"})
        self.assertEqual(status, 200)
        self.assertEqual(data["retention_hours"], 48)

    def test_the_page_can_change_the_retention(self):
        status, data = self.call({"action": "settings_save", "retention_hours": 96})
        self.assertEqual(status, 200)
        self.assertEqual(data["retention_hours"], 96)
        self.assertEqual(self.call({"action": "settings"})[1]["retention_hours"], 96)

    def test_a_bad_value_is_refused_with_a_plain_message(self):
        status, data = self.call({"action": "settings_save", "retention_hours": 0})
        self.assertEqual(status, 400)
        self.assertIn("between 1 and 720", data["error"])
        self.assertEqual(data["retention_hours"], 48)


if __name__ == "__main__":
    unittest.main()
