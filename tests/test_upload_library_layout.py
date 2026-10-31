"""The Library count loads when the page opens, and the action bar only shows on the Add tab.

These are markup checks: the browser layout itself was measured separately (desktop, laptop,
tablet and phone widths: count set on open, no horizontal overflow, bar hidden on the Library).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vercel-api"))

from admin_ui.upload_page import UPLOAD_HTML  # noqa: E402


class LibraryCountAndDockTests(unittest.TestCase):
    def test_library_count_is_loaded_when_the_page_opens(self):
        # Boot loads the list, so the Library count is right before the tab is opened.
        self.assertIn("loadUploads();  // fills the Library count before the tab is opened", UPLOAD_HTML)
        self.assertIn('id="libCount" aria-live="polite">…</span>', UPLOAD_HTML)

    def test_a_failed_load_shows_a_dash_not_a_stale_count(self):
        self.assertIn('$("libCount").textContent = "–";', UPLOAD_HTML)

    def test_the_action_bar_only_shows_on_the_add_tab(self):
        self.assertIn('$("dock").classList.toggle("show", queue.length > 0 && !libraryTabOpen());', UPLOAD_HTML)

    def test_the_grid_gains_columns_as_the_window_grows(self):
        for width in ("560px", "860px", "1160px"):
            self.assertIn(f"@media (min-width:{width})", UPLOAD_HTML)
        self.assertIn("main{max-width:1280px", UPLOAD_HTML)


if __name__ == "__main__":
    unittest.main()
