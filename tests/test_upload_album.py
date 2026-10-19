"""Offline tests: a carousel built from photos staged on the /upload page."""
import io
import os
import unittest
from unittest import mock

from PIL import Image

from instagram_mcp_server import mcp_server as srv
from instagram_mcp_server import upload_store


def _jpeg(color=(200, 80, 40), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


class _FakeCl:
    def __init__(self):
        self.calls = []

    def album_upload(self, paths, caption, **kwargs):
        self.calls.append({
            "paths": [str(p) for p in paths],
            "caption": caption,
            "existed": [os.path.exists(str(p)) for p in paths],
        })
        return mock.Mock(pk="123", code="ABC")


class PostUploadAlbumTests(unittest.TestCase):
    def setUp(self):
        self.saved = (srv._require_login, srv._pacing_error, srv._dedupe_guard, srv._pace_action, srv.ig)
        self.cl = _FakeCl()
        srv._require_login = lambda: None
        srv._pacing_error = lambda kind: None
        srv._dedupe_guard = lambda *a, **k: None
        srv._pace_action = lambda kind: 0

        class FakeIG:
            pass

        fake = FakeIG()
        fake.cl = self.cl
        srv.ig = fake

        self.records, self.bytes_by_id = {}, {}
        self.deleted, self.removed, self.problems, self.statuses = [], [], [], {}

        patches = [
            mock.patch.object(upload_store, "get_upload", side_effect=lambda uid: self.records.get(uid)),
            mock.patch.object(upload_store, "fetch_bytes", side_effect=lambda rec: self.bytes_by_id[rec["id"]]),
            mock.patch.object(upload_store, "delete_blob_file", side_effect=lambda rec: self.deleted.append(rec["id"])),
            mock.patch.object(upload_store, "remove_upload", side_effect=lambda uid: self.removed.append(uid)),
            mock.patch.object(upload_store, "add_problem", side_effect=lambda **kw: self.problems.append(kw)),
            mock.patch.object(upload_store, "set_status",
                              side_effect=lambda uid, status, note="": self.statuses.__setitem__(uid, status)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._restore)

    def _restore(self):
        (srv._require_login, srv._pacing_error, srv._dedupe_guard, srv._pace_action, srv.ig) = self.saved

    def _add(self, uid, data, kind="photo", caption="", aspect="auto"):
        self.records[uid] = {"id": uid, "kind": kind, "caption": caption, "aspect": aspect,
                             "filename": uid + ".jpg"}
        self.bytes_by_id[uid] = data

    def test_needs_two_to_ten_uploads(self):
        self._add("a", _jpeg())
        self.assertIn("between 2 and 10", srv.post_upload_album(["a"]))
        self.assertEqual(self.cl.calls, [])

    def test_same_upload_twice_is_refused(self):
        self._add("a", _jpeg())
        self._add("b", _jpeg())
        self.assertIn("more than once", srv.post_upload_album(["a", "a"]))
        self.assertEqual(self.cl.calls, [])

    def test_unknown_id_is_reported(self):
        self._add("a", _jpeg())
        self.assertIn("no upload with id", srv.post_upload_album(["a", "zzz"]))
        self.assertEqual(self.cl.calls, [])

    def test_reel_in_the_list_is_refused_and_nothing_is_posted(self):
        self._add("a", _jpeg())
        self._add("r", b"\x00" * 40, kind="reel")
        out = srv.post_upload_album(["a", "r"])
        self.assertIn("'status': 'rejected'", out)
        self.assertIn("reels can't be part of a carousel", out)
        self.assertEqual(self.cl.calls, [])
        self.assertEqual(self.deleted, [])

    def test_one_bad_photo_blocks_the_whole_carousel(self):
        self._add("good", _jpeg())
        self._add("bad", b"definitely not an image")
        out = srv.post_upload_album(["good", "bad"])
        self.assertIn("'status': 'rejected'", out)
        self.assertIn("'posted': False", out)
        self.assertEqual(self.cl.calls, [])
        self.assertEqual(self.statuses, {"bad": "rejected"})
        self.assertEqual([p["upload_id"] for p in self.problems], ["bad"])
        self.assertEqual(self.deleted, [])
        self.assertEqual(self.removed, [])

    def test_successful_carousel_posts_once_and_cleans_up(self):
        self._add("a", _jpeg(), caption="first caption")
        self._add("b", _jpeg(color=(10, 200, 10)), caption="ignored")
        out = srv.post_upload_album(["a", "b"])
        self.assertIn("'status': 'success'", out)
        self.assertIn("'items': 2", out)
        self.assertEqual(len(self.cl.calls), 1)
        call = self.cl.calls[0]
        self.assertEqual(call["caption"], "first caption")
        self.assertEqual(len(call["paths"]), 2)
        self.assertTrue(all(call["existed"]))  # converted files existed when Instagram got them
        self.assertFalse(any(os.path.exists(p) for p in call["paths"]))  # temp files removed afterwards
        self.assertEqual(sorted(self.deleted), ["a", "b"])
        self.assertEqual(sorted(self.removed), ["a", "b"])

    def test_explicit_caption_overrides_the_stored_one(self):
        self._add("a", _jpeg(), caption="stored")
        self._add("b", _jpeg())
        srv.post_upload_album(["a", "b"], caption="  my caption  ")
        self.assertEqual(self.cl.calls[0]["caption"], "my caption")

    def test_dry_run_converts_but_never_posts(self):
        self._add("a", _jpeg())
        self._add("b", _jpeg())
        out = srv.post_upload_album(["a", "b"], dry_run=True)
        self.assertIn("'status': 'preview'", out)
        self.assertEqual(self.cl.calls, [])
        self.assertEqual(self.deleted, [])

    def test_instagram_failure_marks_every_item_failed_and_keeps_blobs(self):
        class Boom:
            def album_upload(self, paths, caption, **kw):
                raise RuntimeError("instagram said no")

        srv.ig.cl = Boom()
        self._add("a", _jpeg())
        self._add("b", _jpeg())
        out = srv.post_upload_album(["a", "b"])
        self.assertNotIn("'status': 'success'", out)
        self.assertEqual(self.statuses, {"a": "failed", "b": "failed"})
        self.assertEqual(self.deleted, [])  # Blob copies kept so the user can retry
        self.assertEqual(self.removed, [])


if __name__ == "__main__":
    unittest.main()
