"""Offline tests for the Blob layer (uses a fake `vercel.blob`; no network)."""
import inspect
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from instagram_mcp_server import blob_store  # noqa: E402


class NotFound(Exception):
    pass


def fake_sdk():
    sdk = types.SimpleNamespace(BlobNotFoundError=NotFound)
    sdk.store = {}

    def put(path, body, *, access, content_type, add_random_suffix, overwrite, token):
        if path in sdk.store and not overwrite:
            raise RuntimeError("exists")
        sdk.store[path] = bytes(body)
        return types.SimpleNamespace(url=f"https://s/{path}", pathname=path)

    def get(path, *, access, token, use_cache):
        if path not in sdk.store:
            raise NotFound()
        return types.SimpleNamespace(content=sdk.store[path], status_code=200)

    def delete(path, *, token):
        sdk.store.pop(path, None)

    def list_objects(*, prefix, limit, cursor, token):
        names = sorted(n for n in sdk.store if n.startswith(prefix))
        start = int(cursor or 0)
        page = names[start:start + 2]
        more = start + 2 < len(names)
        items = [types.SimpleNamespace(pathname=n, url=f"https://s/{n}", size=len(sdk.store[n]),
                                       uploaded_at=None) for n in page]
        return types.SimpleNamespace(blobs=items, has_more=more, cursor=str(start + 2) if more else None)

    sdk.put, sdk.get, sdk.delete, sdk.list_objects = put, get, delete, list_objects
    return sdk


class BlobStoreTests(unittest.TestCase):
    def setUp(self):
        self.sdk = fake_sdk()
        for p in (mock.patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "tok"}),
                  mock.patch.object(blob_store, "_sdk", return_value=self.sdk)):
            p.start()
            self.addCleanup(p.stop)

    def test_put_overwrites_existing_object(self):
        blob_store.put_bytes("a/b.json", b"1")
        blob_store.put_bytes("a/b.json", b"2")  # would raise if overwrite were not requested
        self.assertEqual(blob_store.get_bytes("a/b.json"), b"2")

    def test_missing_object_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            blob_store.get_bytes("nope")

    def test_json_roundtrip_and_update(self):
        self.assertEqual(blob_store.get_json("idx", default=[]), [])
        blob_store.update_json("idx", lambda d: d + [1], [])
        blob_store.update_json("idx", lambda d: d + [2], [])
        self.assertEqual(blob_store.get_json("idx"), [1, 2])

    def test_list_prefix_paginates_and_delete_removes(self):
        for i in range(5):
            blob_store.put_bytes(f"p/{i}", b"x")
        blob_store.put_bytes("other/1", b"x")
        self.assertEqual([o["pathname"] for o in blob_store.list_prefix("p/")], [f"p/{i}" for i in range(5)])
        blob_store.delete("p/0")
        self.assertFalse(blob_store.exists("p/0"))
        self.assertTrue(blob_store.exists("p/1"))

    def test_default_access_is_private(self):
        self.assertEqual(blob_store.BLOB_ACCESS, "private")


@unittest.skipUnless(__import__("importlib").util.find_spec("vercel"), "vercel SDK not installed")
class RealSdkContractTests(unittest.TestCase):
    """Guards against the SDK signature drifting away from what blob_store passes."""

    def test_signatures_accept_our_keyword_arguments(self):
        from vercel import blob
        want = {
            "put": {"access", "content_type", "add_random_suffix", "overwrite", "token"},
            "get": {"access", "token", "use_cache"},
            "delete": {"token"},
            "list_objects": {"prefix", "limit", "cursor", "token"},
        }
        for name, kwargs in want.items():
            params = set(inspect.signature(getattr(blob, name)).parameters)
            self.assertTrue(kwargs <= params, f"{name} is missing {kwargs - params}")
        self.assertTrue(hasattr(blob, "BlobNotFoundError"))


if __name__ == "__main__":
    unittest.main()
