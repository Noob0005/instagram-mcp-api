// Instagram Session Sync — background worker. Works in Chrome (service worker) and Firefox (background script).
// fernet.js is loaded first (importScripts in Chrome; listed in manifest-firefox.json for Firefox).
// The sessionid goes to your Instagram MCP server, encrypted with your Fernet key.
if (typeof importScripts === "function") importScripts("fernet.js");

const IG_URL = "https://www.instagram.com/";
const IG_PAGE = /^https:\/\/(www\.)?instagram\.com\//;
const DEFAULTS = { serverUrl: "", mcpKey: "", encKey: "", username: "", intervalMin: 60 };
const RETRY_MIN = 10; // after a failed automatic attempt, wait this long before trying again

let inFlight = false; // one automatic sync at a time

async function getConfig() {
  const { config = {} } = await chrome.storage.local.get("config");
  return { ...DEFAULTS, ...config };
}
async function getState() {
  const { state = {} } = await chrome.storage.local.get("state");
  return state;
}
async function setState(patch) {
  const s = await getState();
  await chrome.storage.local.set({ state: { ...s, ...patch } });
}
function ready(c) {
  return !!(c.serverUrl && c.mcpKey && c.encKey);
}
async function cookieValue(name) {
  try {
    const c = await chrome.cookies.get({ url: IG_URL, name });
    return c && c.value ? c.value : null;
  } catch (e) {
    return null;
  }
}

// A pre-configured download ships with defaults.json (server URL + keys). Apply it once, so the
// extension works straight after install. The public zip has no defaults.json: setup is manual.
async function applyDefaults() {
  const { config } = await chrome.storage.local.get("config");
  if (config && config.mcpKey) return;
  try {
    const r = await fetch(chrome.runtime.getURL("defaults.json"));
    if (!r.ok) return;
    const d = await r.json();
    if (d.serverUrl && d.mcpKey && d.encKey) {
      await chrome.storage.local.set({ config: { ...DEFAULTS, ...d } });
    }
  } catch (e) {
    // no defaults file: the user fills in the options page
  }
}

// Automatic sync: when an instagram.com page finishes loading, sync the login in the background.
// At most one successful sync per interval; after a failure, retry no sooner than RETRY_MIN.
async function autoSyncIfDue() {
  if (inFlight) return;
  const cfg = await getConfig();
  if (!ready(cfg)) return;
  const st = await getState();
  const now = Date.now();
  if (st.lastSyncAt && now - st.lastSyncAt < cfg.intervalMin * 60 * 1000) return;
  if (st.lastTryAt && now - st.lastTryAt < RETRY_MIN * 60 * 1000) return;
  inFlight = true;
  try {
    await runSync();
  } finally {
    inFlight = false;
  }
}

chrome.tabs.onUpdated.addListener((_tabId, info, tab) => {
  if (info.status !== "complete" || !tab || !tab.url) return;
  if (IG_PAGE.test(tab.url)) autoSyncIfDue().catch((e) => console.warn("Instagram sync:", e));
});

chrome.runtime.onStartup.addListener(() => { applyDefaults(); });
chrome.runtime.onInstalled.addListener(async (d) => {
  await applyDefaults();
  if (d.reason === "install") chrome.runtime.openOptionsPage();
});

// Shared by the button and the automatic sync: runs one sync and records the outcome.
async function runSync() {
  await setState({ lastTryAt: Date.now() });
  const r = await syncNow();
  await setState({ lastResult: { at: Date.now(), ok: r.ok, message: r.message } });
  await updateBadge();
  return r;
}

// The toolbar badge shows "!" while the last attempt failed.
async function updateBadge() {
  const s = await getState();
  const failed = !!(s.lastResult && !s.lastResult.ok);
  chrome.action.setBadgeText({ text: failed ? "!" : "" });
}

async function syncNow() {
  const cfg = await getConfig();
  if (!ready(cfg)) {
    return { ok: false, message: "Fill in the server URL, MCP key and encryption key first." };
  }
  const sessionid = await cookieValue("sessionid");
  if (!sessionid) {
    return { ok: false, message: "No Instagram sessionid in this browser. Log in at instagram.com first." };
  }
  let token;
  try {
    token = await fernetEncrypt(JSON.stringify({ sessionid, username: cfg.username || "" }), cfg.encKey);
  } catch (e) {
    return { ok: false, message: "Encryption key is not a valid Fernet key (44 characters, use GEN on the dashboard)." };
  }
  const base = cfg.serverUrl.replace(/\/+$/, "");
  let res;
  let data = {};
  try {
    res = await fetch(base + "/api/session-sync", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Auth-Key": cfg.mcpKey },
      body: JSON.stringify({ payload: token }),
    });
    data = await res.json().catch(() => ({}));
  } catch (e) {
    return { ok: false, message: "Could not reach " + base + ". Check the server URL." };
  }
  if (res.ok && data.status === "success") {
    await setState({ lastSyncAt: Date.now() });
    return { ok: true, message: "Synced" + (data.username ? " as @" + data.username : "") + "." };
  }
  if (res.status === 401) return { ok: false, message: "The server rejected the MCP key." };
  if (res.status === 400) return { ok: false, message: "The server could not decrypt the payload. Check the encryption key." };
  return { ok: false, message: data.message || data.hint || data.error || ("Server returned HTTP " + res.status) };
}

async function pingServer() {
  const cfg = await getConfig();
  if (!cfg.serverUrl) return { ok: false, message: "Set the server URL first." };
  try {
    const r = await fetch(cfg.serverUrl.replace(/\/+$/, "") + "/healthz");
    const j = await r.json().catch(() => ({}));
    if (r.ok && j.status === "ok") return { ok: true, message: "Server reachable (" + (j.server || "ok") + ")." };
    return { ok: false, message: "Server answered HTTP " + r.status + ". Check the URL." };
  } catch (e) {
    return { ok: false, message: "Could not reach the server URL." };
  }
}

// What the floating panel shows: whether the sync is set up, whether Instagram is logged in here, and the last result.
async function siteStatus() {
  const cfg = await getConfig();
  const st = await getState();
  return {
    configured: ready(cfg),
    loggedIn: !!(await cookieValue("sessionid")),
    lastSyncAt: st.lastSyncAt || null,
    lastResult: st.lastResult || null,
  };
}

// Messages from the floating panel and the options page. Each one gets exactly one reply.
function answer(promise, reply) {
  promise.then(reply, (e) => reply({ ok: false, message: "Extension error: " + (e && e.message) }));
  return true; // keep the channel open for the async reply
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (!msg) return false;
  if (msg.type === "syncNow") return answer(runSync(), reply);
  if (msg.type === "ping") return answer(pingServer(), reply);
  if (msg.type === "status") return answer(siteStatus(), reply);
  if (msg.type === "openOptions") {
    chrome.runtime.openOptionsPage();
    reply({ ok: true });
  }
  return false;
});
