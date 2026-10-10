"""Offline tests: reels from a public URL must be real MP4 files."""
import os
import tempfile
import unittest

from instagram_mcp_server import mcp_server as srv


def _tmp(data: bytes) -> str:
    fh = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    fh.write(data)
    fh.close()
    return fh.name


class ReelUrlTypeCheckTests(unittest.TestCase):
    def test_jpeg_bytes_rejected(self):
        path = _tmp(b"\xff\xd8\xff" + b"\x00" * 64)
        try:
            err = srv._reject_non_mp4(path)
            self.assertIsNotNone(err)
            self.assertIn("reel rejected", err)
            self.assertIn("mp4", err)
        finally:
            os.remove(path)

    def test_quicktime_mov_rejected(self):
        # ftyp box with brand 'qt  ' = QuickTime .mov
        path = _tmp(b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 40)
        try:
            err = srv._reject_non_mp4(path)
            self.assertIsNotNone(err)
            self.assertIn("QuickTime", err)
        finally:
            os.remove(path)


class InstagramPostReelUrlTests(unittest.TestCase):
    def setUp(self):
        self.orig = (srv._require_login, srv._pacing_error, srv._dedupe_guard,
                     srv._pace_action, srv._download_if_url, srv.ig)
        self.uploads = []

        class FakeCl:
            def clip_upload(inner, path, caption, location=None):
                self.uploads.append(path)
                raise AssertionError("clip_upload must not run for a rejected file")

        class FakeIG:
            cl = FakeCl()

        srv._require_login = lambda: None
        srv._pacing_error = lambda kind: None
        srv._dedupe_guard = lambda *a, **k: None
        srv._pace_action = lambda kind: 0
        srv.ig = FakeIG()

    def tearDown(self):
        (srv._require_login, srv._pacing_error, srv._dedupe_guard,
         srv._pace_action, srv._download_if_url, srv.ig) = self.orig

    def test_url_with_non_mp4_content_is_rejected_before_upload(self):
        path = _tmp(b"\xff\xd8\xff" + b"\x00" * 64)
        srv._download_if_url = lambda url, suffix=".mp4": path
        out = srv.instagram_post_reel("https://example.com/clip.mp4", "hi")
        self.assertTrue(out.startswith("Error: reel rejected"), out)
        self.assertEqual(self.uploads, [])
        self.assertFalse(os.path.exists(path))  # temp download cleaned up


if __name__ == "__main__":
    unittest.main()
