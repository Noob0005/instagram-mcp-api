"""A failing Blob read must not turn the upload page's list into a 500, and must never
be written back as an empty document (offline)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vercel-api", "_vendor"))

from instagram_mcp_server import blob_store  # noqa: E402


class ReadErrorTests(unittest.TestCase):
    def test_read_only_get_json_falls_back_to_default(self):
        with mock.patch.object(blob_store, "get_bytes", side_effect=RuntimeError("store down")):
            self.assertEqual(blob_store.get_json("x.json", {"a": 1}), {"a": 1})

    def test_update_json_refuses_to_write_back_after_a_failed_read(self):
        put = mock.Mock()
        with mock.patch.object(blob_store, "get_bytes", side_effect=RuntimeError("store down")), \
                mock.patch.object(blob_store, "put_bytes", put):
            with self.assertRaises(RuntimeError):
                blob_store.update_json("index.json", lambda doc: doc, {"uploads": []})
        put.assert_not_called()

    def test_missing_file_is_still_the_default_not_an_error(self):
        with mock.patch.object(blob_store, "get_bytes", side_effect=FileNotFoundError()):
            self.assertEqual(blob_store.get_json("missing.json", []), [])


if __name__ == "__main__":
    unittest.main()
