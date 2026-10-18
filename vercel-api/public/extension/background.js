// Instagram MCP Sync — background worker. Works in Chrome (service worker) and Firefox (background script).
// fernet.js is loaded first (importScripts in Chrome; listed in manifest-firefox.json for Firefox).
if (typeof importScripts === "function") importScripts("fernet.js");

const IG_URL = "https://www.instagram.com/";
const PROMPT_ID = "sync-prompt";
const DEFAULTS = { serverUrl: "", mcpKey: "", encKey: "", username: "", intervalMin: 60 };

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
function configured(c) {
  return !!(c.serverUrl && c.mcpKey && c.encKey);
}

// Ask at most once per interval, and only when the last sync is older than the interval.
// Opening the browser many times in a row therefore does not prompt again and again.
async function remindIfDue() {
  const cfg = await getConfig();
  if (!configured(cfg)) return;
  const st = await getState();
  const now = Date.now();
  const gap = cfg.intervalMin * 60 * 1000;
  const syncedRecently = st.lastSyncAt && now - st.lastSyncAt < gap;
  const promptedRecently = st.lastPromptAt && now - st.lastPromptAt < gap;
  if (syncedRecently || promptedRecently) return;
  await setState({ lastPromptAt: now });
  chrome.action.setBadgeText({ text: "!" });
  chrome.action.setBadgeBackgroundColor({ color: "#5ef0ff" });
  chrome.notifications.create(PROMPT_ID, {
    type: "basic",
    iconUrl: "icon.png",
    title: "Sync Instagram session?",
    message: "Send your Instagram login from this browser to your MCP server.",
    buttons: [{ title: "Sync now" }, { title: "Later" }],
  });
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

chrome.runtime.onStartup.addListener(() => { applyDefaults().then(remindIfDue); });
chrome.runtime.onInstalled.addListener(async (d) => {
  await applyDefaults();
  if (d.reason === "install") chrome.runtime.openOptionsPage();
});
chrome.notifications.onButtonClicked.addListener((id, index) => {
  if (id !== PROMPT_ID) return;
  chrome.notifications.clear(id);
  if (index === 0) syncNow();
});
chrome.notifications.onClicked.addListener((id) => {
  if (id === PROMPT_ID) chrome.runtime.openOptionsPage();
});

async function syncNow() {
  const cfg = await getConfig();
  if (!configured(cfg)) {
    return { ok: false, message: "Fill in the server URL, MCP key and encryption key first." };
  }
  let cookie = null;
  try {
    cookie = await chrome.cookies.get({ url: IG_URL, name: "sessionid" });
  } catch (e) {
    cookie = null;
  }
  if (!cookie || !cookie.value) {
    chrome.action.setBadgeText({ text: "X" });
    return { ok: false, message: "No Instagram sessionid in this browser. Log in at instagram.com first." };
  }
  let token;
  try {
    token = await fernetEncrypt(JSON.stringify({ sessionid: cookie.value, username: cfg.username || "" }), cfg.encKey);
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
    chrome.action.setBadgeText({ text: "" });
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
    return { ok: false, message: "Server answered HTTP " + r.status + " — check the URL." };
  } catch (e) {
    return { ok: false, message: "Could not reach the server URL." };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg && msg.type === "syncNow") { syncNow().then(reply); return true; }
  if (msg && msg.type === "ping") { pingServer().then(reply); return true; }
  return false;
});
