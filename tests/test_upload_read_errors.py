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


class MissingFileAnsweredWith400Tests(unittest.TestCase):
    """The store answers a missing file with 400. That must start an empty document, but a file
    that is really there must still stop the write when it cannot be read."""

    def test_missing_file_with_400_starts_an_empty_document(self):
        put = mock.Mock()
        err = RuntimeError("Client error '400 Bad Request' for url .../index.json")
        with mock.patch.object(blob_store, "get_bytes", side_effect=err), \
                mock.patch.object(blob_store, "list_prefix", return_value=[]), \
                mock.patch.object(blob_store, "put_bytes", put):
            doc = blob_store.update_json("instagram-mcp/uploads/index.json",
                                         lambda d: d["uploads"].append({"id": "1"}),
                                         {"uploads": []})
        self.assertEqual(doc, {"uploads": [{"id": "1"}]})
        put.assert_called_once()

    def test_400_on_a_file_that_exists_still_stops_the_write(self):
        put = mock.Mock()
        err = RuntimeError("Client error '400 Bad Request' for url .../index.json")
        listing = [{"pathname": "instagram-mcp/uploads/index.json"}]
        with mock.patch.object(blob_store, "get_bytes", side_effect=err), \
                mock.patch.object(blob_store, "list_prefix", return_value=listing), \
                mock.patch.object(blob_store, "put_bytes", put):
            with self.assertRaises(RuntimeError):
                blob_store.update_json("instagram-mcp/uploads/index.json", lambda d: d, {"uploads": []})
        put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
