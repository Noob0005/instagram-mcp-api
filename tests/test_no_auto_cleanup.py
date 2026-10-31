"""Automatic cleanup is gone: no cron, no /api/cleanup route, no retention setting.

Uploads stay until someone deletes them by hand (the Library or the delete_uploads tool).
"""
import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "vercel-api"))


class NoAutoCleanupTests(unittest.TestCase):
    def test_vercel_config_has_no_cron(self):
        with open(os.path.join(ROOT, "vercel-api", "vercel.json"), encoding="utf-8") as fh:
            self.assertNotIn("crons", json.load(fh))

    def test_no_cleanup_function_or_route(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "vercel-api", "api", "cleanup.py")))
        with open(os.path.join(ROOT, "vercel-api", "api", "main.py"), encoding="utf-8") as fh:
            self.assertNotIn("/api/cleanup", fh.read())

    def test_store_has_no_purge_and_no_retention_module(self):
        from instagram_mcp_server import upload_store
        self.assertFalse(hasattr(upload_store, "purge_expired"))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "instagram_mcp_server", "upload_settings.py")))

    def test_dashboard_and_upload_page_do_not_mention_retention(self):
        from admin_ui.page import DASHBOARD_HTML
        from admin_ui.upload_page import UPLOAD_HTML
        for html in (DASHBOARD_HTML, UPLOAD_HTML):
            for word in ("upload_settings", "retention", "keepHours", "homeKeep", "openSettings", "settings_save"):
                self.assertNotIn(word, html)


if __name__ == "__main__":
    unittest.main()
