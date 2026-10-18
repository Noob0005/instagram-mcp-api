const $ = (id) => document.getElementById(id);

function show(message, ok) {
  $("out").textContent = message;
  $("out").className = ok ? "ok" : "bad";
}

async function load() {
  const { config = {}, state = {} } = await chrome.storage.local.get(["config", "state"]);
  $("serverUrl").value = config.serverUrl || "";
  $("mcpKey").value = config.mcpKey || "";
  $("encKey").value = config.encKey || "";
  $("username").value = config.username || "";
  $("intervalMin").value = String(config.intervalMin || 60);
  $("last").textContent = state.lastSyncAt ? new Date(state.lastSyncAt).toLocaleString() : "never";
}

$("save").addEventListener("click", async () => {
  const config = {
    serverUrl: $("serverUrl").value.trim(),
    mcpKey: $("mcpKey").value.trim(),
    encKey: $("encKey").value.trim(),
    username: $("username").value.trim(),
    intervalMin: Number($("intervalMin").value) || 60,
  };
  if (!/^https:\/\//.test(config.serverUrl) && !/^http:\/\/localhost/.test(config.serverUrl)) {
    show("The server URL must start with https://", false);
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
  show("Syncing…", true);
  const r = await chrome.runtime.sendMessage({ type: "syncNow" });
  show(r.message, r.ok);
  load();
});

load();
