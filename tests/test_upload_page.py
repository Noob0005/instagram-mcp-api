"""Regression: the upload page must be embedded in the bundle (no runtime file read)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vercel-api"))

from admin_ui.upload_page import UPLOAD_HTML  # noqa: E402


class UploadPageEmbeddedTests(unittest.TestCase):
    def test_page_is_embedded_and_calls_the_api(self):
        self.assertIn("<title>Upload to Instagram MCP</title>", UPLOAD_HTML)
        self.assertIn("'/api/upload'", UPLOAD_HTML)
        self.assertIn("/api/blob-token", UPLOAD_HTML)

    def test_no_runtime_file_dependency(self):
        here = os.path.join(os.path.dirname(__file__), "..", "vercel-api", "api", "mcp_server_asgi.py")
        with open(here, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("public\" / \"upload.html", src)


if __name__ == "__main__":
    unittest.main()
