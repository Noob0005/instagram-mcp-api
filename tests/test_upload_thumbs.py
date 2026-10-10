"""Offline tests: upload thumbnails and caption editing (local index, no Blob)."""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ["INSTAGRAM_MCP_UPLOAD_INDEX_PATH"] = os.path.join(_TMP, "index.json")
os.environ.pop("BLOB_READ_WRITE_TOKEN", None)

from instagram_mcp_server import upload_store  # noqa: E402


class UploadThumbStoreTests(unittest.TestCase):
    def test_add_stores_thumb_and_caption_can_be_changed(self):
        rec = upload_store.add_upload(
            filename="cat.jpg", pathname="instagram-mcp/uploads/x_cat.jpg", url=None, size=10,
            content_type="image/jpeg", caption="old", aspect="auto", kind="photo",
            local_path=None, thumb_pathname="instagram-mcp/uploads/x_thumb.jpg")
        self.assertEqual(rec["thumb_pathname"], "instagram-mcp/uploads/x_thumb.jpg")
        self.assertTrue(upload_store.set_caption(rec["id"], "new caption"))
        self.assertEqual(upload_store.get_upload(rec["id"])["caption"], "new caption")

    def test_set_caption_unknown_id_returns_false(self):
        self.assertFalse(upload_store.set_caption("does-not-exist", "x"))

    def test_fetch_thumb_is_none_without_blob(self):
        rec = {"thumb_pathname": "instagram-mcp/uploads/x_thumb.jpg"}
        self.assertIsNone(upload_store.fetch_thumb(rec))


if __name__ == "__main__":
    unittest.main()
