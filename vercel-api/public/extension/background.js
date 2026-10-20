// Session sync — background worker. Works in Chrome (service worker) and Firefox (background script).
// fernet.js is loaded first (importScripts in Chrome; listed in manifest-firefox.json for Firefox).
// Instagram: the sessionid goes to your Instagram MCP server, encrypted with your Fernet key.
// Gemini: the two Gemini cookies go to your Gemini Archive server, with its sync key.
if (typeof importScripts === "function") importScripts("fernet.js");

const IG_URL = "https://www.instagram.com/";
const IG_PAGE = /^https:\/\/(www\.)?instagram\.com\//;
const GEMINI_URL = "https://gemini.google.com/";
const GEMINI_PAGE = /^https:\/\/gemini\.google\.com\//;
const GEMINI_COOKIES = ["__Secure-1PSID", "__Secure-1PSIDTS"];
const DEFAULTS = { serverUrl: "", mcpKey: "", encKey: "", username: "", intervalMin: 60, geminiUrl: "", geminiKey: "" };
const RETRY_MIN = 10; // after a failed automatic attempt, wait this long before trying again

const inFlight = { instagram: false, gemini: false }; // one automatic sync per site at a time

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
// Instagram keeps its timestamps at the top of "state"; Gemini keeps its own under state.gemini.
async function siteState(site) {
  const s = await getState();
  return site === "gemini" ? s.gemini || {} : s;
}
async function setSiteState(site, patch) {
  const s = await getState();
  if (site === "gemini") await setState({ gemini: { ...(s.gemini || {}), ...patch } });
  else await setState(patch);
}
function instagramReady(c) {
  return !!(c.serverUrl && c.mcpKey && c.encKey);
}
function geminiReady(c) {
  return !!(c.geminiUrl && c.geminiKey);
}
function siteReady(site, c) {
  return site === "gemini" ? geminiReady(c) : instagramReady(c);
}
async function cookieValue(url, name) {
  try {
    const c = await chrome.cookies.get({ url, name });
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

// Automatic sync: when an instagram.com or gemini.google.com page finishes loading, sync that
// site's login in the background. At most one successful sync per interval; after a failure,
// retry no sooner than RETRY_MIN.
async function autoSyncIfDue(site) {
  if (inFlight[site]) return;
  const cfg = await getConfig();
  if (!siteReady(site, cfg)) return;
  const st = await siteState(site);
  const now = Date.now();
  const gap = cfg.intervalMin * 60 * 1000;
  if (st.lastSyncAt && now - st.lastSyncAt < gap) return;
  if (st.lastTryAt && now - st.lastTryAt < RETRY_MIN * 60 * 1000) return;
  inFlight[site] = true;
  try {
    await runSync(site);
  } finally {
    inFlight[site] = false;
  }
}

chrome.tabs.onUpdated.addListener((_tabId, info, tab) => {
  if (info.status !== "complete" || !tab || !tab.url) return;
  if (IG_PAGE.test(tab.url)) autoSyncIfDue("instagram");
  else if (GEMINI_PAGE.test(tab.url)) autoSyncIfDue("gemini");
});

chrome.runtime.onStartup.addListener(() => { applyDefaults(); });
chrome.runtime.onInstalled.addListener(async (d) => {
  await applyDefaults();
  if (d.reason === "install") chrome.runtime.openOptionsPage();
});

// Shared by the buttons and the automatic sync: runs one site's sync and records the outcome.
async function runSync(site = "instagram") {
  await setSiteState(site, { lastTryAt: Date.now() });
  const r = site === "gemini" ? await syncGemini() : await syncNow();
  await setSiteState(site, { lastResult: { at: Date.now(), ok: r.ok, message: r.message } });
  await updateBadge();
  return r;
}

// The toolbar badge shows "!" while the last attempt of either site failed.
async function updateBadge() {
  const s = await getState();
  const failed = (x) => !!(x && x.lastResult && !x.lastResult.ok);
  chrome.action.setBadgeText({ text: failed(s) || failed(s.gemini) ? "!" : "" });
}

async function syncNow() {
  const cfg = await getConfig();
  if (!instagramReady(cfg)) {
    return { ok: false, message: "Fill in the server URL, MCP key and encryption key first." };
  }
  const sessionid = await cookieValue(IG_URL, "sessionid");
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

// Sends the Gemini cookies to the Gemini Archive server. Over HTTPS, with the server's sync key.
async function syncGemini() {
  const cfg = await getConfig();
  if (!geminiReady(cfg)) {
    return { ok: false, message: "Fill in the Gemini server URL and sync key first." };
  }
  const cookies = [];
  for (const name of GEMINI_COOKIES) {
    const value = await cookieValue(GEMINI_URL, name);
    if (value) cookies.push({ name, value });
  }
  if (!cookies.some((c) => c.name === "__Secure-1PSID")) {
    return { ok: false, message: "No Gemini login in this browser. Log in at gemini.google.com first." };
  }
  const base = cfg.geminiUrl.replace(/\/+$/, "");
  let res;
  let data = {};
  try {
    res = await fetch(base + "/api/session/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": cfg.geminiKey },
      body: JSON.stringify({ cookies: JSON.stringify(cookies) }),
    });
    data = await res.json().catch(() => ({}));
  } catch (e) {
    return { ok: false, message: "Could not reach " + base + ". Check the Gemini server URL." };
  }
  if (res.ok) {
    await setSiteState("gemini", { lastSyncAt: Date.now() });
    return { ok: true, message: "Gemini cookies saved." };
  }
  if (res.status === 401) return { ok: false, message: "The Gemini server rejected the sync key." };
  if (res.status === 503) return { ok: false, message: "The Gemini server has no GEMINI_SYNC_KEY set yet." };
  return { ok: false, message: data.detail || ("Gemini server returned HTTP " + res.status) };
}

async function pingServer() {
  const cfg = await getConfig();
  if (!cfg.serverUrl) return { ok: false, message: "Set the server URL first." };
  try {
    const r = await fetch(cfg.serverUrl.replace(/\/+$/, "") + "/healthz");
    const j = await r.json().catch(() => ({}));
    if (r.ok && j.status === "ok") return { ok: true, message: "Server reachable (" + (j.server || "ok") + ")." };
    return { ok: false, message: "Server answered HTTP " + r.status + " — check the URL." };
  } catch (e) {
    return { ok: false, message: "Could not reach the server URL." };
  }
}

// What the floating panel shows: whether each site is set up, logged in here, and its last result.
async function siteStatus() {
  const cfg = await getConfig();
  const s = await getState();
  const gem = s.gemini || {};
  return {
    instagram: {
      configured: instagramReady(cfg),
      loggedIn: !!(await cookieValue(IG_URL, "sessionid")),
      lastSyncAt: s.lastSyncAt || null,
      lastResult: s.lastResult || null,
    },
    gemini: {
      configured: geminiReady(cfg),
      loggedIn: !!(await cookieValue(GEMINI_URL, "__Secure-1PSID")),
      lastSyncAt: gem.lastSyncAt || null,
      lastResult: gem.lastResult || null,
    },
  };
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg && msg.type === "syncNow") { runSync("instagram").then(reply); return true; }
  if (msg && msg.type === "syncSite") { runSync(msg.site === "gemini" ? "gemini" : "instagram").then(reply); return true; }
  if (msg && msg.type === "ping") { pingServer().then(reply); return true; }
  if (msg && msg.type === "status") { siteStatus().then(reply); return true; }
  if (msg && msg.type === "openOptions") { chrome.runtime.openOptionsPage(); return false; }
  return false;
});
