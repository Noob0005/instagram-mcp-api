"""The Library's bulk delete and storage line: present in the page, and the page script parses.

The page script is checked with node so a syntax slip is caught here, not on the phone.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vercel-api"))

from admin_ui.upload_page import UPLOAD_HTML  # noqa: E402


class LibraryBulkDeleteMarkupTests(unittest.TestCase):
    def test_library_has_selection_bar_storage_line_and_the_api_calls(self):
        for marker in ('id="selBar"', 'id="storageLine"', 'id="selDelete"', 'id="selAll"',
                       "action: 'delete_many'", "action: 'storage'", "Delete selected",
                       'const BUILD = "2026-10-31'):
            self.assertIn(marker, UPLOAD_HTML)

    def test_each_tile_has_a_tick_box(self):
        self.assertIn('class: "pick"', UPLOAD_HTML)
        self.assertIn('type: "checkbox"', UPLOAD_HTML)


@unittest.skipUnless(shutil.which("node"), "node is needed to syntax-check the page script")
class PageScriptSyntaxTests(unittest.TestCase):
    def test_inline_script_parses(self):
        blocks = re.findall(r"<script>(.*?)</script>", UPLOAD_HTML, re.S)
        self.assertTrue(blocks)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        for i, block in enumerate(blocks):
            path = os.path.join(tmp, f"page{i}.js")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(block)
            result = subprocess.run(["node", "--check", path], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
