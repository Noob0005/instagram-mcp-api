"""Manual delete and storage status (offline, local index, no Blob).

Covers: storage usage against the plan allowance, the preview that deletes nothing, the
confirmed delete (including partial failures and duplicate ids), and the two MCP tools.
"""
import ast
import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastmcp import Client  # noqa: E402

from instagram_mcp_server import mcp_server, upload_store  # noqa: E402

MB = 1024 ** 2
GB = 1024 ** 3


def add(name, size_bytes):
    rec = upload_store.add_upload(
        filename=name, pathname=f"instagram-mcp/uploads/{name}", url=None, size=size_bytes,
        content_type="image/jpeg", caption=f"caption for {name}", aspect="auto", kind="photo",
        thumb_pathname=None)
    return rec["id"]


def ids_left():
    return sorted(u["id"] for u in upload_store.list_uploads(status=None))


class _Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        env = {"INSTAGRAM_MCP_UPLOAD_INDEX_PATH": os.path.join(tmp, "index.json")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("BLOB_READ_WRITE_TOKEN", None)
        os.environ.pop("INSTAGRAM_MCP_STORAGE_LIMIT_GB", None)


class StorageUsageTests(_Base):
    def test_usage_is_summed_against_the_default_one_gb_allowance(self):
        add("a.jpg", 300 * MB)
        add("b.jpg", 200 * MB)
        s = upload_store.storage_usage()
        self.assertEqual(s["used_mb"], 500.0)
        self.assertEqual(s["limit_gb"], 1.0)
        self.assertEqual(s["free_mb"], 524.0)
        self.assertEqual(s["percent_used"], 48.8)
        self.assertEqual(s["files"], 2)
        self.assertFalse(s["count_is_capped"])

    def test_limit_can_be_changed_with_an_environment_variable(self):
        with mock.patch.dict(os.environ, {"INSTAGRAM_MCP_STORAGE_LIMIT_GB": "5"}):
            add("a.jpg", 1 * GB)
            s = upload_store.storage_usage()
        self.assertEqual(s["limit_gb"], 5.0)
        self.assertEqual(s["percent_used"], 20.0)

    def test_a_bad_limit_falls_back_to_one_gb(self):
        with mock.patch.dict(os.environ, {"INSTAGRAM_MCP_STORAGE_LIMIT_GB": "lots"}):
            self.assertEqual(upload_store.storage_usage()["limit_gb"], 1.0)

    def test_empty_store_has_nothing_used(self):
        s = upload_store.storage_usage()
        self.assertEqual((s["used_mb"], s["files"], s["free_mb"]), (0.0, 0, 1024.0))

    def test_blob_usage_sums_the_listed_objects_and_flags_the_1000_cap(self):
        objects = [{"pathname": f"instagram-mcp/uploads/{i}.jpg", "size": 1 * MB} for i in range(1000)]
        with mock.patch.object(upload_store, "blob_available", return_value=True), \
                mock.patch.object(upload_store.blob_store, "list_prefix", return_value=objects) as lp:
            s = upload_store.storage_usage()
        lp.assert_called_once_with("instagram-mcp/uploads/")
        self.assertEqual(s["used_mb"], 1000.0)
        self.assertEqual(s["files"], 1000)
        self.assertTrue(s["count_is_capped"])


class DescribeTests(_Base):
    def test_preview_lists_the_files_and_changes_nothing(self):
        a = add("a.jpg", 2 * MB)
        b = add("b.jpg", 3 * MB)
        p = upload_store.describe_uploads([a, "nope", b])
        self.assertEqual([f["id"] for f in p["files"]], [a, b])
        self.assertEqual(p["missing"], ["nope"])
        self.assertEqual(p["total_mb"], 5.0)
        self.assertEqual(p["files"][0]["caption"], "caption for a.jpg")
        self.assertEqual(ids_left(), sorted([a, b]))

    def test_duplicate_ids_are_counted_once(self):
        a = add("a.jpg", 2 * MB)
        p = upload_store.describe_uploads([a, a, a])
        self.assertEqual(len(p["files"]), 1)
        self.assertEqual(p["total_mb"], 2.0)


class DeleteTests(_Base):
    def test_confirmed_delete_removes_the_records_and_reports_space_freed(self):
        a = add("a.jpg", 2 * MB)
        b = add("b.jpg", 3 * MB)
        keep = add("keep.jpg", 4 * MB)
        r = upload_store.delete_uploads([a, b])
        self.assertEqual([d["id"] for d in r["deleted"]], [a, b])
        self.assertEqual(r["failed"], [])
        self.assertEqual(r["freed_mb"], 5.0)
        self.assertEqual(ids_left(), [keep])

    def test_unknown_id_is_reported_and_others_still_go(self):
        a = add("a.jpg", 1 * MB)
        r = upload_store.delete_uploads(["ghost", a])
        self.assertEqual([f["id"] for f in r["failed"]], ["ghost"])
        self.assertEqual([d["id"] for d in r["deleted"]], [a])
        self.assertEqual(ids_left(), [])

    def test_a_file_that_cannot_be_deleted_keeps_its_record(self):
        a = add("a.jpg", 1 * MB)
        b = add("b.jpg", 1 * MB)

        def flaky(rec):
            if rec["id"] == a:
                raise RuntimeError("store unavailable")

        with mock.patch.object(upload_store, "delete_blob_file", side_effect=flaky):
            r = upload_store.delete_uploads([a, b])
        self.assertEqual([f["id"] for f in r["failed"]], [a])
        self.assertIn("store unavailable", r["failed"][0]["error"])
        self.assertEqual([d["id"] for d in r["deleted"]], [b])
        self.assertEqual(ids_left(), [a])  # kept so the user can retry

    def test_duplicate_ids_delete_once(self):
        a = add("a.jpg", 1 * MB)
        r = upload_store.delete_uploads([a, a])
        self.assertEqual(len(r["deleted"]), 1)
        self.assertEqual(r["failed"], [])


def _parse(result):
    return ast.literal_eval(result.content[0].text)


async def _mcp(tool, args):
    async with Client(mcp_server.mcp) as client:
        return await client.call_tool(tool, args)


class McpToolTests(_Base):
    def test_storage_status_tells_the_user_what_is_left(self):
        add("a.jpg", 250 * MB)
        result = asyncio.run(_mcp("storage_status", {}))
        data = _parse(result)
        self.assertIn("250.0 MB used of 1 GB", data["summary"])
        self.assertEqual(data["files"], 1)

    def test_delete_without_confirm_deletes_nothing_and_shows_the_list(self):
        a = add("a.jpg", 2 * MB)
        b = add("b.jpg", 3 * MB)
        data = _parse(asyncio.run(_mcp("delete_uploads", {"upload_ids": [a, b]})))
        self.assertEqual(data["status"], "not_deleted_yet")
        self.assertEqual([f["filename"] for f in data["would_delete"]], ["a.jpg", "b.jpg"])
        self.assertEqual(data["would_delete"][0]["caption"], "caption for a.jpg")
        self.assertEqual(data["total_mb"], 5.0)
        self.assertIn("confirm=True", data["next_step"])
        self.assertEqual(ids_left(), sorted([a, b]))

    def test_delete_with_confirm_removes_only_the_chosen_files(self):
        a = add("a.jpg", 2 * MB)
        keep = add("keep.jpg", 4 * MB)
        data = _parse(asyncio.run(_mcp("delete_uploads", {"upload_ids": [a], "confirm": True})))
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["freed_mb"], 2.0)
        self.assertEqual(data["storage_used_mb"], 4.0)
        self.assertEqual(ids_left(), [keep])

    def test_empty_id_list_is_refused(self):
        data = _parse(asyncio.run(_mcp("delete_uploads", {"upload_ids": [], "confirm": True})))
        self.assertEqual(data["status"], "error")


if __name__ == "__main__":
    unittest.main()
