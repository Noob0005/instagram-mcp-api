"""The floating panel (vercel-api/public/extension/content.js), run in a real Chromium page.

The extension API is stubbed, so no extension is loaded and nothing goes to the network.
Skipped when Playwright or a Chromium it can start is not installed.
"""

import os
import unittest

HERE = os.path.dirname(__file__)
CONTENT = os.path.join(HERE, "..", "vercel-api", "public", "extension", "content.js")
CHROMIUM = "/opt/pw-browsers/chromium"  # pre-installed in this sandbox; Playwright's own build otherwise

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - depends on the machine
    sync_playwright = None

STUB = """
window.__sent = [];
window.__stub = {
  status: {
    instagram: { configured: true, loggedIn: true, lastSyncAt: Date.now() - 5 * 60000, lastResult: { ok: true, message: 'Synced.' } },
    gemini: { configured: true, loggedIn: false, lastSyncAt: null, lastResult: null },
  },
  syncReply: { ok: true, message: 'Gemini cookies saved.' },
  throwNow: false,
};
window.chrome = { runtime: {
  sendMessage(msg) {
    if (window.__stub.throwNow) throw new Error('Extension context invalidated.');
    window.__sent.push(msg);
    if (msg.type === 'status') return Promise.resolve(window.__stub.status);
    if (msg.type === 'syncSite') return Promise.resolve(window.__stub.syncReply);
    return Promise.resolve({});
  },
}};
"""

PANEL_TEXT = "() => document.getElementById('session-sync-root').shadowRoot.querySelector('[data-role=panel]').textContent"


def shadow(page, selector):
    return f"() => document.getElementById('session-sync-root').shadowRoot.querySelector({selector!r})"


@unittest.skipUnless(sync_playwright is not None, "playwright is not installed")
class FloatingPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._pw = sync_playwright().start()
        try:
            cls.browser = cls._pw.chromium.launch(executable_path=CHROMIUM if os.path.exists(CHROMIUM) else None)
        except Exception as exc:  # no browser on this machine
            cls._pw.stop()
            raise unittest.SkipTest(f"no Chromium available: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()

    def open_page(self, url="https://gemini.google.com/app/abc"):
        """A blank page that claims to be the Gemini site, with the panel script loaded once."""
        ctx = self.browser.new_context()
        page = ctx.new_page()
        self.addCleanup(ctx.close)
        page.add_init_script(STUB)
        page.route(url, lambda route: route.fulfill(body="<html><body><h1>page</h1></body></html>", content_type="text/html"))
        page.goto(url)
        page.add_script_tag(path=CONTENT)
        return page

    def test_one_floating_button_is_added_and_it_opens_the_panel(self):
        page = self.open_page()
        self.assertEqual(page.evaluate("() => document.querySelectorAll('#session-sync-root').length"), 1)
        self.assertTrue(page.evaluate(shadow(page, "[data-role=panel]") + ".hidden"))
        page.evaluate(shadow(page, "[data-role=toggle]") + ".click()")
        self.assertFalse(page.evaluate(shadow(page, "[data-role=panel]") + ".hidden"))
        self.assertIn({"type": "status"}, page.evaluate("() => window.__sent"))

    def test_the_panel_shows_each_site_and_whether_it_is_logged_in(self):
        page = self.open_page()
        page.evaluate(shadow(page, "[data-role=toggle]") + ".click()")
        page.wait_for_function("() => document.getElementById('session-sync-root').shadowRoot.querySelectorAll('.row').length === 2")
        text = page.evaluate(PANEL_TEXT)
        self.assertIn("Instagram", text)
        self.assertIn("Gemini  (this page)", text)  # this page is Gemini
        self.assertIn("Logged in in this browser.", text)
        self.assertIn("Not logged in in this browser.", text)
        self.assertIn("Last sync: 5 min ago", text)

    def test_a_sync_button_sends_its_site_and_shows_the_result(self):
        page = self.open_page()
        page.evaluate(shadow(page, "[data-role=toggle]") + ".click()")
        page.wait_for_function("() => document.getElementById('session-sync-root').shadowRoot.querySelectorAll('.row').length === 2")
        page.evaluate(shadow(page, "button.sync[data-site=gemini]") + ".click()")
        page.wait_for_function(
            "() => document.getElementById('session-sync-root').shadowRoot.querySelector('[data-role=msg]').textContent === 'Gemini cookies saved.'"
        )
        self.assertIn({"type": "syncSite", "site": "gemini"}, page.evaluate("() => window.__sent"))
        self.assertIn("ok", page.evaluate(shadow(page, "[data-role=msg]") + ".className"))

    def test_loading_the_script_twice_still_gives_one_button(self):
        page = self.open_page()
        page.add_script_tag(path=CONTENT)
        self.assertEqual(page.evaluate("() => document.querySelectorAll('#session-sync-root').length"), 1)

    def test_a_stale_extension_asks_for_a_reload(self):
        page = self.open_page()
        page.evaluate("() => { window.__stub.throwNow = true; }")
        page.evaluate(shadow(page, "[data-role=toggle]") + ".click()")
        page.wait_for_function(
            "() => document.getElementById('session-sync-root').shadowRoot.querySelector('[data-role=msg]').textContent.includes('Reload this page')"
        )
        self.assertIn("Reload this page", page.evaluate(shadow(page, "[data-role=msg]") + ".textContent"))

    def test_status_text_from_the_server_is_never_read_as_html(self):
        page = self.open_page()
        page.evaluate(
            "() => { window.__stub.status.gemini.lastResult = { ok: false, message: '<img src=x id=evil>' }; }"
        )
        page.evaluate(shadow(page, "[data-role=toggle]") + ".click()")
        page.wait_for_function("() => document.getElementById('session-sync-root').shadowRoot.querySelectorAll('.row').length === 2")
        self.assertEqual(page.evaluate("() => document.getElementById('session-sync-root').shadowRoot.querySelectorAll('img').length"), 0)
        self.assertIn("<img src=x id=evil>", page.evaluate(PANEL_TEXT))


if __name__ == "__main__":
    unittest.main()
