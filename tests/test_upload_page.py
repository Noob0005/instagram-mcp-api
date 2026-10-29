"""Regression: the upload page must be embedded in the bundle (no runtime file read)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vercel-api"))

from admin_ui.upload_page import UPLOAD_HTML  # noqa: E402


class UploadPageEmbeddedTests(unittest.TestCase):
    def test_page_is_embedded_and_calls_the_api(self):
        self.assertIn("<title>Upload</title>", UPLOAD_HTML)
        self.assertIn("'/api/upload'", UPLOAD_HTML)
        self.assertIn("/api/blob-token", UPLOAD_HTML)

    def test_page_has_progress_list_view_rename_delete_and_settings(self):
        # Per-file progress while uploading.
        self.assertIn("onUploadProgress", UPLOAD_HTML)
        # My uploads: list, thumbnails, view, rename, delete, retention settings.
        for needle in ("action: 'list'", "action: 'rename'", "action: 'delete'",
                       "action: 'settings'", "action: 'settings_save'",
                       "mediaUrl(u.id, 'thumb')", "mediaUrl(u.id, 'file')"):
            self.assertIn(needle, UPLOAD_HTML)

    def test_page_never_puts_the_key_in_the_html_source(self):
        # The key comes from the URL or sessionStorage at runtime, never baked into the page.
        self.assertNotIn("MCP_AUTH_KEY", UPLOAD_HTML)
        self.assertNotIn("innerHTML", UPLOAD_HTML)

    def test_no_runtime_file_dependency(self):
        here = os.path.join(os.path.dirname(__file__), "..", "vercel-api", "api", "mcp_server_asgi.py")
        with open(here, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("public\" / \"upload.html", src)


if __name__ == "__main__":
    unittest.main()
