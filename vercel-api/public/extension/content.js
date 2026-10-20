// Session Sync — floating panel. Injected into instagram.com and gemini.google.com (top page only).
// It asks the background worker for the status and starts syncs. It never reads cookies itself.
(function () {
  if (window.__sessionSyncLoaded) return; // one panel per page, even if the script is injected twice
  window.__sessionSyncLoaded = true;

  const SITES = [
    { id: "instagram", name: "Instagram", host: /(^|\.)instagram\.com$/ },
    { id: "gemini", name: "Gemini", host: /(^|\.)gemini\.google\.com$/ },
  ];
  const here = SITES.find((s) => s.host.test(location.hostname));

  const host = document.createElement("div");
  host.id = "session-sync-root";
  const root = host.attachShadow({ mode: "open" }); // open, so the page's own styles cannot reach in
  root.innerHTML = `
<style>
  .fab {
    position: fixed; right: 16px; bottom: 16px; width: 44px; height: 44px; border-radius: 50%;
    border: 1px solid #39ff88; background: #06140c; color: #39ff88; cursor: pointer;
    font: 700 16px/1 ui-monospace, Menlo, Consolas, monospace; box-shadow: 0 4px 16px rgba(0,0,0,.35);
    z-index: 2147483647; padding: 0;
  }
  .fab:focus-visible, button:focus-visible { outline: 2px solid #9dffc4; outline-offset: 2px; }
  .panel {
    position: fixed; right: 16px; bottom: 70px; width: 300px; max-width: calc(100vw - 32px);
    box-sizing: border-box; padding: 12px; border-radius: 10px; border: 1px solid #39ff88;
    background: #06140c; color: #d6ffe6; z-index: 2147483647; box-shadow: 0 8px 28px rgba(0,0,0,.45);
    font: 13px/1.4 ui-monospace, Menlo, Consolas, monospace;
  }
  .panel[hidden] { display: none; }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  h2 { margin: 0; font-size: 12px; letter-spacing: .08em; color: #39ff88; }
  .x { background: none; border: 0; color: #9dffc4; font-size: 18px; cursor: pointer; padding: 0 4px; }
  .row { border-top: 1px solid #1f4d33; padding: 8px 0; }
  .name { font-weight: 700; }
  .here { color: #9dffc4; font-weight: 400; }
  .state, .last { font-size: 12px; opacity: .85; }
  .last { opacity: .7; font-size: 11px; }
  .sync {
    margin-top: 6px; background: #0d2a19; color: #39ff88; border: 1px solid #39ff88;
    border-radius: 6px; padding: 5px 10px; cursor: pointer; font: inherit; font-size: 12px;
  }
  .msg { min-height: 1.4em; margin: 6px 0 2px; font-size: 12px; }
  .msg.ok { color: #7dffa8; }
  .msg.bad { color: #ff8a8a; }
  footer { display: flex; gap: 12px; border-top: 1px solid #1f4d33; padding-top: 8px; }
  .link { background: none; border: 0; color: #9dffc4; cursor: pointer; font: inherit; font-size: 12px; padding: 0; text-decoration: underline; }
</style>
<button class="fab" data-role="toggle" aria-label="Session Sync" aria-expanded="false" title="Session Sync">S</button>
<section class="panel" data-role="panel" hidden aria-label="Session Sync">
  <header><h2>SESSION // SYNC</h2><button class="x" data-role="close" aria-label="Close">×</button></header>
  <div data-role="rows"></div>
  <p class="msg" data-role="msg" aria-live="polite"></p>
  <footer>
    <button class="link" data-role="refresh">REFRESH</button>
    <button class="link" data-role="options">SETTINGS</button>
  </footer>
</section>`;
  document.documentElement.appendChild(host);

  const $ = (role) => root.querySelector(`[data-role="${role}"]`);
  const send = (msg) => chrome.runtime.sendMessage(msg);

  function setMsg(text, ok) {
    const m = $("msg");
    m.textContent = text;
    m.className = "msg " + (ok ? "ok" : "bad");
  }

  function reloadHint() {
    return "The extension was updated or reloaded. Reload this page.";
  }

  function ago(at) {
    if (!at) return "never";
    const min = Math.round((Date.now() - at) / 60000);
    if (min < 1) return "just now";
    if (min < 60) return min + " min ago";
    return Math.round(min / 60) + " h ago";
  }

  function render(status) {
    const rows = $("rows");
    rows.textContent = "";
    for (const site of SITES) {
      const s = (status && status[site.id]) || {};
      const row = document.createElement("div");
      row.className = "row";

      const name = document.createElement("div");
      name.className = "name";
      name.textContent = site.name;
      if (here && here.id === site.id) {
        const tag = document.createElement("span");
        tag.className = "here";
        tag.textContent = "  (this page)";
        name.appendChild(tag);
      }

      const state = document.createElement("div");
      state.className = "state";
      state.textContent = !s.configured
        ? "Not set up yet. Open SETTINGS."
        : s.loggedIn
          ? "Logged in in this browser."
          : "Not logged in in this browser.";

      const last = document.createElement("div");
      last.className = "last";
      const r = s.lastResult;
      last.textContent = "Last sync: " + ago(s.lastSyncAt) + (r && !r.ok ? " · failed: " + r.message : "");

      const btn = document.createElement("button");
      btn.className = "sync";
      btn.dataset.site = site.id;
      btn.textContent = "SYNC " + site.name.toUpperCase();

      row.append(name, state, last, btn);
      rows.appendChild(row);
    }
  }

  async function refresh() {
    try {
      render(await send({ type: "status" }));
    } catch (e) {
      setMsg(reloadHint(), false);
    }
  }

  async function syncSite(site) {
    setMsg("Syncing " + site + "…", true);
    try {
      const r = await send({ type: "syncSite", site });
      setMsg(r.message, r.ok);
    } catch (e) {
      setMsg(reloadHint(), false);
      return;
    }
    refresh();
  }

  function setOpen(open) {
    $("panel").hidden = !open;
    $("toggle").setAttribute("aria-expanded", String(open));
    if (open) refresh();
  }

  $("toggle").addEventListener("click", () => setOpen($("panel").hidden));
  $("close").addEventListener("click", () => setOpen(false));
  $("refresh").addEventListener("click", refresh);
  $("options").addEventListener("click", () => {
    try {
      send({ type: "openOptions" });
    } catch (e) {
      setMsg(reloadHint(), false);
    }
  });
  $("rows").addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("button.sync");
    if (btn) syncSite(btn.dataset.site);
  });
})();
