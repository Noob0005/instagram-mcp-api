"""The Blob store is public, so every file that is not a photo has a name only this server can work out."""
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from instagram_mcp_server import blob_store, upload_store  # noqa: E402

BLOB_ON = {"BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_test_token"}


class PrivateNameTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {**BLOB_ON, "MCP_AUTH_KEY": "secret-one-0123456789abcdef",
                                               "INSTAGRAM_MCP_STORE_SECRET": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_index_problem_log_and_session_names_are_hashes_not_words(self):
        for key in (blob_store.index_key(), blob_store.problems_key(), blob_store.session_key()):
            self.assertRegex(key, rf"^{re.escape(blob_store.PREFIX)}/[0-9a-f]{{40}}\.json$")
            self.assertNotIn("index", key)
            self.assertNotIn("problems", key)
            self.assertNotIn("default", key)

    def test_names_are_stable_for_one_secret_and_change_with_it(self):
        first = blob_store.index_key()
        self.assertEqual(first, blob_store.index_key())
        with mock.patch.dict(os.environ, {"MCP_AUTH_KEY": "a-different-secret-0123456789"}):
            self.assertNotEqual(first, blob_store.index_key())

    def test_a_separate_store_secret_takes_precedence(self):
        with mock.patch.dict(os.environ, {"INSTAGRAM_MCP_STORE_SECRET": "store-secret-0123456789abcdef"}):
            with_store = blob_store.index_key()
        self.assertNotEqual(with_store, blob_store.index_key())

    def test_a_photo_name_has_no_file_name_and_is_random(self):
        first = blob_store.upload_key("id1", "IMG 1042.JPG")
        second = blob_store.upload_key("id1", "IMG 1042.JPG")
        self.assertTrue(first.startswith(f"{blob_store.PREFIX}/uploads/"))
        self.assertTrue(first.endswith(".jpg"))
        self.assertNotIn("1042", first)
        self.assertNotIn("IMG", first)
        self.assertNotEqual(first, second)

    def test_blob_mode_without_any_secret_refuses_to_name_files(self):
        with mock.patch.dict(os.environ, {"MCP_AUTH_KEY": "", "INSTAGRAM_MCP_STORE_SECRET": ""}):
            with self.assertRaises(RuntimeError):
                blob_store.index_key()

    def test_local_mode_without_a_secret_uses_plain_names(self):
        env = {"BLOB_READ_WRITE_TOKEN": "", "MCP_AUTH_KEY": "", "INSTAGRAM_MCP_STORE_SECRET": ""}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(blob_store.index_key(), f"{blob_store.PREFIX}/index.json")

    def test_upload_records_do_not_store_the_public_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = os.path.join(tmp, "index.json")
            with mock.patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "",
                                              "INSTAGRAM_MCP_UPLOAD_INDEX_PATH": index}):
                rec = upload_store.add_upload(filename="a.jpg", pathname="instagram-mcp/uploads/x.jpg",
                                              url="https://public.example/x.jpg", size=3,
                                              content_type="image/jpeg", caption="", aspect="auto", kind="photo")
            self.assertIsNone(rec["url"])


if __name__ == "__main__":
    unittest.main()
