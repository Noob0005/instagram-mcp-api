"""Offline check of the browser extension's automatic sync rules.

Runs the real vercel-api/public/extension/background.js (and fernet.js) inside Node with a fake
chrome.* API. Skipped when Node.js is not installed.
"""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(__file__)
EXT = os.path.join(HERE, "..", "vercel-api", "public", "extension")
NODE = shutil.which("node")

_DRIVER = r"""
const fs = require('fs'), vm = require('vm');
const [fernetPath, bgPath, encKey] = process.argv.slice(2);
const FERNET = fs.readFileSync(fernetPath, 'utf8');
const BG = fs.readFileSync(bgPath, 'utf8');
const IG = 'https://www.instagram.com/accounts/login/';
const OTHER = 'https://example.com/';
const MIN = 60 * 1000;
const flush = () => new Promise((r) => setTimeout(r, 30));

function world(o = {}) {
  const store = {};
  if (o.configured !== false) {
    store.config = {serverUrl: 'https://mcp.example.test', mcpKey: 'MCPKEY', encKey,
                    username: 'me', intervalMin: o.intervalMin || 60};
  }
  if (o.state) store.state = o.state;
  const cookie = 'cookie' in o ? o.cookie : {value: 'SID123'};
  const w = {store, fetches: [], badges: [], notes: [], tabListeners: [], messageListeners: []};
  const chrome = {
    storage: {local: {
      async get(keys) {
        const out = {};
        for (const k of [].concat(keys)) if (k in store) out[k] = JSON.parse(JSON.stringify(store[k]));
        return out;
      },
      async set(obj) { for (const k of Object.keys(obj)) store[k] = JSON.parse(JSON.stringify(obj[k])); },
    }},
    cookies: {async get() { return cookie; }},
    action: {setBadgeText(a) { w.badges.push(a.text); }, setBadgeBackgroundColor() {}},
    notifications: {create(...a) { w.notes.push(a); }},
    tabs: {onUpdated: {addListener(f) { w.tabListeners.push(f); }}},
    runtime: {
      onStartup: {addListener() {}},
      onInstalled: {addListener() {}},
      onMessage: {addListener(f) { w.messageListeners.push(f); }},
      getURL(p) { return 'chrome-extension://id/' + p; },
      openOptionsPage() {},
    },
  };
  const status = o.serverStatus || 200;
  const body = o.serverBody || {status: 'success', username: 'me'};
  const ctx = {
    chrome,
    fetch: async (url, opts) => { w.fetches.push({url, opts}); return {ok: status < 300, status, json: async () => body}; },
    crypto: globalThis.crypto, TextEncoder, TextDecoder, atob, btoa, console, Date, JSON, setTimeout,
  };
  vm.createContext(ctx);
  vm.runInContext(FERNET, ctx);
  vm.runInContext(BG, ctx);
  w.fire = async (url, status = 'complete') => {
    for (const f of w.tabListeners) f(1, {status}, {url});
    await flush();
  };
  w.send = (msg) => new Promise((resolve) => { w.messageListeners[0](msg, {}, resolve); });
  return w;
}

const out = {};
(async () => {
  let w = world(); await w.fire(OTHER);
  out.otherSite = w.fetches.length;

  w = world(); await w.fire(IG, 'loading');
  out.loading = w.fetches.length;

  w = world(); await w.fire(IG);
  out.firstLoad = w.fetches.length;
  out.firstUrl = w.fetches[0] && w.fetches[0].url;
  out.firstKeyHeader = w.fetches[0] && w.fetches[0].opts.headers['X-Auth-Key'];
  out.firstPayloadPrefix = w.fetches[0] && JSON.parse(w.fetches[0].opts.body).payload.slice(0, 6);
  out.firstLastResultOk = w.store.state.lastResult.ok;
  out.firstBadge = w.badges[w.badges.length - 1];
  out.firstNotes = w.notes.length;
  await w.fire(IG);
  out.secondLoadThrottled = w.fetches.length;

  w = world({state: {lastSyncAt: Date.now() - 61 * MIN}}); await w.fire(IG);
  out.staleSyncs = w.fetches.length;

  w = world({state: {lastSyncAt: Date.now() - 5 * MIN}}); await w.fire(IG);
  out.recentSyncs = w.fetches.length;

  w = world({configured: false}); await w.fire(IG);
  out.unconfigured = w.fetches.length;

  w = world({cookie: null}); await w.fire(IG);
  out.loggedOutBadge = w.badges[w.badges.length - 1];
  out.loggedOutMessage = w.store.state.lastResult.message;
  const firstTry = w.store.state.lastTryAt;
  await w.fire(IG);
  out.loggedOutRetryBlocked = w.store.state.lastTryAt === firstTry;
  w.store.state.lastTryAt = Date.now() - 11 * MIN;
  await w.fire(IG);
  out.loggedOutRetryAfterGap = w.store.state.lastTryAt > Date.now() - 60 * 1000;

  w = world({serverStatus: 401, serverBody: {error: 'unauthorized'}}); await w.fire(IG);
  out.rejectedMessage = w.store.state.lastResult.message;
  out.rejectedBadge = w.badges[w.badges.length - 1];

  w = world({state: {lastSyncAt: Date.now()}});
  const reply = await w.send({type: 'syncNow'});
  out.manualOk = reply.ok;
  out.manualFetches = w.fetches.length;
  out.manualNotes = w.notes.length;

  console.log(JSON.stringify(out));
})().catch((e) => { console.error((e && e.stack) || e); process.exit(1); });
"""


@unittest.skipUnless(NODE, "node is not installed")
class ExtensionAutoSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        driver = os.path.join(cls._tmp.name, "driver.js")
        with open(driver, "w", encoding="utf-8") as fh:
            fh.write(_DRIVER)
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        proc = subprocess.run(
            [NODE, driver, os.path.join(EXT, "fernet.js"), os.path.join(EXT, "background.js"), key],
            capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise AssertionError("driver failed: " + proc.stderr)
        cls.out = json.loads(proc.stdout)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_other_sites_do_not_sync(self):
        self.assertEqual(self.out["otherSite"], 0)

    def test_page_still_loading_does_not_sync(self):
        self.assertEqual(self.out["loading"], 0)

    def test_first_instagram_load_syncs_once_with_key_and_encrypted_payload(self):
        self.assertEqual(self.out["firstLoad"], 1)
        self.assertTrue(self.out["firstUrl"].endswith("/api/session-sync"))
        self.assertEqual(self.out["firstKeyHeader"], "MCPKEY")
        self.assertEqual(self.out["firstPayloadPrefix"], "gAAAAA")  # Fernet token, version 0x80
        self.assertTrue(self.out["firstLastResultOk"])
        self.assertEqual(self.out["firstBadge"], "")
        self.assertEqual(self.out["firstNotes"], 0)  # no notification prompt any more

    def test_second_load_inside_the_interval_is_throttled(self):
        self.assertEqual(self.out["secondLoadThrottled"], 1)

    def test_sync_runs_again_after_the_interval(self):
        self.assertEqual(self.out["staleSyncs"], 1)

    def test_recent_sync_is_not_repeated(self):
        self.assertEqual(self.out["recentSyncs"], 0)

    def test_unconfigured_extension_does_nothing(self):
        self.assertEqual(self.out["unconfigured"], 0)

    def test_logged_out_failure_is_recorded_and_retry_is_delayed(self):
        self.assertEqual(self.out["loggedOutBadge"], "!")
        self.assertIn("sessionid", self.out["loggedOutMessage"])
        self.assertTrue(self.out["loggedOutRetryBlocked"])
        self.assertTrue(self.out["loggedOutRetryAfterGap"])

    def test_rejected_key_is_reported(self):
        self.assertEqual(self.out["rejectedMessage"], "The server rejected the MCP key.")
        self.assertEqual(self.out["rejectedBadge"], "!")

    def test_manual_sync_ignores_the_interval(self):
        self.assertTrue(self.out["manualOk"])
        self.assertEqual(self.out["manualFetches"], 1)
        self.assertEqual(self.out["manualNotes"], 0)


if __name__ == "__main__":
    unittest.main()
