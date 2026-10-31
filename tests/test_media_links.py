"""Signed view links: each opens one upload, only until it expires, and never carries the server key."""
import os
import sys
import time
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from instagram_mcp_server import media_links  # noqa: E402

KEY = "test-key-for-media-links-0123456789"
ORIGIN = "https://insta.example"


def _parts(link):
    return {k: v[0] for k, v in parse_qs(urlsplit(link).query).items()}


class MediaLinkTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"MCP_AUTH_KEY": KEY})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("INSTAGRAM_MCP_VIEW_LINK_HOURS", None)

    def test_a_fresh_link_verifies_and_points_at_the_api_route(self):
        link = media_links.make_link("thumb", "abc123", ORIGIN)
        self.assertTrue(link.startswith("https://insta.example/api/upload?thumb=abc123&exp="))
        p = _parts(link)
        self.assertTrue(media_links.link_is_valid("thumb", "abc123", p["exp"], p["sig"]))

    def test_the_server_key_is_never_in_the_link(self):
        self.assertNotIn(KEY, media_links.make_link("file", "abc123", ORIGIN))

    def test_a_link_opens_only_its_own_upload_and_kind(self):
        p = _parts(media_links.make_link("thumb", "abc123", ORIGIN))
        self.assertFalse(media_links.link_is_valid("thumb", "other", p["exp"], p["sig"]))
        self.assertFalse(media_links.link_is_valid("file", "abc123", p["exp"], p["sig"]))

    def test_a_changed_expiry_or_signature_is_refused(self):
        p = _parts(media_links.make_link("thumb", "abc123", ORIGIN))
        self.assertFalse(media_links.link_is_valid("thumb", "abc123", str(int(p["exp"]) + 3600), p["sig"]))
        self.assertFalse(media_links.link_is_valid("thumb", "abc123", p["exp"], "0" * 64))

    def test_an_expired_link_is_refused(self):
        link = media_links.make_link("file", "abc123", ORIGIN, now=time.time() - 3 * 86400)
        p = _parts(link)
        self.assertFalse(media_links.link_is_valid("file", "abc123", p["exp"], p["sig"]))

    def test_without_a_server_key_no_link_is_made_or_accepted(self):
        with mock.patch.dict(os.environ, {"MCP_AUTH_KEY": ""}):
            with self.assertRaises(media_links.LinkError):
                media_links.make_link("thumb", "abc123", ORIGIN)
            self.assertFalse(media_links.link_is_valid("thumb", "abc123", str(int(time.time()) + 60), "ab"))

    def test_link_lifetime_is_configurable_and_kept_within_bounds(self):
        with mock.patch.dict(os.environ, {"INSTAGRAM_MCP_VIEW_LINK_HOURS": "1000"}):
            self.assertEqual(media_links.hours(), 168)
        with mock.patch.dict(os.environ, {"INSTAGRAM_MCP_VIEW_LINK_HOURS": "nonsense"}):
            self.assertEqual(media_links.hours(), 24)


if __name__ == "__main__":
    unittest.main()
