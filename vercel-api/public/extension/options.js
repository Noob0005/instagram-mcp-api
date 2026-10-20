const $ = (id) => document.getElementById(id);

function show(message, ok) {
  $("out").textContent = message;
  $("out").className = ok ? "ok" : "bad";
}

function lastText(at, result) {
  return (at ? new Date(at).toLocaleString() : "never") +
    (result && !result.ok ? "  (last attempt failed: " + result.message + ")" : "");
}

async function load() {
  let { config = {}, state = {} } = await chrome.storage.local.get(["config", "state"]);
  if (!config.mcpKey) {
    // pre-configured download: show the values it ships with (the background applies them too)
    try {
      const r = await fetch(chrome.runtime.getURL("defaults.json"));
      if (r.ok) config = { ...(await r.json()), ...config };
    } catch (e) { /* none */ }
  }
  $("serverUrl").value = config.serverUrl || "";
  $("mcpKey").value = config.mcpKey || "";
  $("encKey").value = config.encKey || "";
  $("username").value = config.username || "";
  $("geminiUrl").value = config.geminiUrl || "";
  $("geminiKey").value = config.geminiKey || "";
  $("intervalMin").value = String(config.intervalMin || 60);
  $("last").textContent = lastText(state.lastSyncAt, state.lastResult);
  const gem = state.gemini || {};
  $("lastGemini").textContent = lastText(gem.lastSyncAt, gem.lastResult);
}

$("save").addEventListener("click", async () => {
  const config = {
    serverUrl: $("serverUrl").value.trim(),
    mcpKey: $("mcpKey").value.trim(),
    encKey: $("encKey").value.trim(),
    username: $("username").value.trim(),
    geminiUrl: $("geminiUrl").value.trim(),
    geminiKey: $("geminiKey").value.trim(),
    intervalMin: Number($("intervalMin").value) || 60,
  };
  const httpsOrLocal = (u) => !u || /^https:\/\//.test(u) || /^http:\/\/localhost/.test(u);
  if (!httpsOrLocal(config.serverUrl) || !httpsOrLocal(config.geminiUrl)) {
    show("Server URLs must start with https://", false);
    return;
  }
  await chrome.storage.local.set({ config });
  show("Saved.", true);
});

$("test").addEventListener("click", async () => {
  const r = await chrome.runtime.sendMessage({ type: "ping" });
  show(r.message, r.ok);
});

$("sync").addEventListener("click", async () => {
  show("Syncing Instagram…", true);
  const r = await chrome.runtime.sendMessage({ type: "syncNow" });
  show(r.message, r.ok);
  load();
});

$("syncGemini").addEventListener("click", async () => {
  show("Syncing Gemini…", true);
  const r = await chrome.runtime.sendMessage({ type: "syncSite", site: "gemini" });
  show(r.message, r.ok);
  load();
});

load();
