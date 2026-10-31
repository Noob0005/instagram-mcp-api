"""Unposted uploads are deleted INSTAGRAM_MCP_UNPOSTED_HOURS (48 by default): by the daily cron, and when the list is read."""
import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "vercel-api", "api"))

# api/upload.py reads MCP_AUTH_KEY once, at import, so every module that imports it must agree on the key.
KEY = "test-key-for-upload-settings-0123"  # the key tests/test_upload_manage.py uses
os.environ["MCP_AUTH_KEY"] = KEY
from instagram_mcp_server import upload_store  # noqa: E402
import cleanup as cleanup_api  # noqa: E402
import upload as upload_api  # noqa: E402

HOUR = 3600
CRON = "cron-secret-0123456789abcdef"


def _run(app, method="GET", headers=(), query="", body=None):
    payload = json.dumps(body).encode() if body is not None else b""
    scope = {"type": "http", "method": method, "path": "/x", "headers": list(headers),
             "query_string": query.encode()}
    sent = []

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent[0]["status"], json.loads(sent[1]["body"].decode())


def _stage(name):
    return upload_store.add_upload(filename=name, pathname=f"instagram-mcp/uploads/{name}", url=None, size=3,
                                   content_type="image/jpeg", caption="", aspect="auto", kind="photo")


class KeepHoursTests(unittest.TestCase):
    def test_default_is_48_hours_and_the_setting_is_kept_in_bounds(self):
        with mock.patch.dict(os.environ, {"INSTAGRAM_MCP_UNPOSTED_HOURS": ""}):
            self.assertEqual(upload_store.keep_hours(), 48.0)
        with mock.patch.dict(os.environ, {"INSTAGRAM_MCP_UNPOSTED_HOURS": "500"}):
            self.assertEqual(upload_store.keep_hours(), 168.0)
        with mock.patch.dict(os.environ, {"INSTAGRAM_MCP_UNPOSTED_HOURS": "0.5"}):
            self.assertEqual(upload_store.keep_hours(), 1.0)
        with mock.patch.dict(os.environ, {"INSTAGRAM_MCP_UNPOSTED_HOURS": "soon"}):
            self.assertEqual(upload_store.keep_hours(), 48.0)


class ExpiryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        patcher = mock.patch.dict(os.environ, {
            "BLOB_READ_WRITE_TOKEN": "", "MCP_AUTH_KEY": KEY, "CRON_SECRET": CRON,
            "INSTAGRAM_MCP_UPLOAD_INDEX_PATH": os.path.join(tmp, "index.json"),
            "INSTAGRAM_MCP_UNPOSTED_HOURS": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _ids(self):
        return sorted(u["id"] for u in upload_store.list_uploads(status=None))

    def _make_past_due(self, rec):
        def mutate(index):
            for u in index["uploads"]:
                if u["id"] == rec["id"]:
                    u["expires_at"] = time.time() - 1
            return index
        upload_store._mutate_local(mutate)

    def test_a_new_upload_records_when_it_will_be_deleted(self):
        rec = _stage("a.jpg")
        self.assertAlmostEqual(rec["expires_at"] - rec["uploaded_at"], 48 * HOUR, delta=5)

    def test_purge_removes_only_uploads_past_their_time(self):
        old, fresh = _stage("old.jpg"), _stage("fresh.jpg")
        self._make_past_due(old)
        result = upload_store.purge_expired()
        self.assertEqual(result["removed"], 1)
        self.assertEqual(self._ids(), sorted([fresh["id"]]))

    def test_a_posted_upload_loses_its_record_without_touching_the_file(self):
        posted = _stage("posted.jpg")
        upload_store.set_status(posted["id"], "posted")
        self._make_past_due(posted)
        with mock.patch.object(upload_store, "delete_blob_file") as deleter:
            result = upload_store.purge_expired()
        deleter.assert_not_called()
        self.assertEqual(result["removed"], 1)
        self.assertEqual(self._ids(), [])

    def test_a_file_that_cannot_be_deleted_keeps_its_record_for_next_time(self):
        rec = _stage("stuck.jpg")
        self._make_past_due(rec)
        with mock.patch.object(upload_store, "delete_blob_file", side_effect=RuntimeError("blob busy")):
            result = upload_store.purge_expired()
        self.assertEqual(result["removed"], 0)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(self._ids(), [rec["id"]])

    def test_reading_the_upload_list_removes_what_is_past_its_time(self):
        old, fresh = _stage("old.jpg"), _stage("fresh.jpg")
        self._make_past_due(old)
        status, data = _run(upload_api.app, method="POST",
                            headers=[(b"x-auth-key", KEY.encode())], body={"action": "list"})
        self.assertEqual(status, 200)
        self.assertEqual([u["filename"] for u in data["uploads"]], ["fresh.jpg"])
        self.assertEqual(data["keep_hours"], 48.0)
        self.assertEqual(self._ids(), [fresh["id"]])


class CleanupCronTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"CRON_SECRET": CRON, "MCP_AUTH_KEY": KEY,
                                               "BLOB_READ_WRITE_TOKEN": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_cron_needs_its_bearer_secret(self):
        status, _ = _run(cleanup_api.app)
        self.assertEqual(status, 401)
        status, _ = _run(cleanup_api.app, headers=[(b"authorization", b"Bearer wrong")])
        self.assertEqual(status, 401)

    def test_the_server_key_in_the_url_is_not_accepted(self):
        status, _ = _run(cleanup_api.app, query=f"auth={KEY}")
        self.assertEqual(status, 401)

    def test_the_cron_with_its_secret_runs_the_purge(self):
        with mock.patch.object(upload_store, "purge_expired", return_value={"removed": 2, "failed": [],
                                                                            "keep_hours": 48.0}) as purge:
            status, data = _run(cleanup_api.app, headers=[(b"authorization", f"Bearer {CRON}".encode())])
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["removed"], 2)
        purge.assert_called_once()

    def test_vercel_runs_the_cleanup_once_a_day(self):
        with open(os.path.join(ROOT, "vercel-api", "vercel.json"), encoding="utf-8") as fh:
            config = json.load(fh)
        self.assertEqual(config["crons"], [{"path": "/api/cleanup", "schedule": "0 4 * * *"}])


if __name__ == "__main__":
    unittest.main()
