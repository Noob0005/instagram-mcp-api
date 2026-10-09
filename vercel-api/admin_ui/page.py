"""The dashboard page. Kept as a Python string so it is always bundled with the function."""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Archive Terminal</title>
<style>
:root{
  --bg:#040704; --panel:#0a120b; --line:#1e3b21; --fg:#a6ffb8; --dim:#5a9a68;
  --faint:#31553a; --amber:#ffb454; --red:#ff5f5f; --cyan:#6be4ff;
  --mono:ui-monospace,"Cascadia Mono","SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box}
html{background:var(--bg)}
body{
  margin:0; min-height:100vh; color:var(--fg); font:14px/1.55 var(--mono);
  background:
    radial-gradient(ellipse at 50% -10%, rgba(80,255,130,.10), transparent 55%),
    radial-gradient(ellipse at 100% 100%, rgba(107,228,255,.05), transparent 50%),
    var(--bg);
  text-shadow:0 0 6px rgba(120,255,160,.25);
}
body::before{ /* scanlines */
  content:""; position:fixed; inset:0; pointer-events:none; z-index:50;
  background:repeating-linear-gradient(0deg, rgba(0,0,0,.22) 0 1px, transparent 1px 3px);
}
body::after{ /* vignette */
  content:""; position:fixed; inset:0; pointer-events:none; z-index:49;
  background:radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,.55));
}
main{max-width:920px; margin:0 auto; padding:24px 16px 64px; position:relative; z-index:1}
header.top{display:flex; flex-wrap:wrap; justify-content:space-between; gap:8px 16px;
  align-items:baseline; border-bottom:1px solid var(--line); padding-bottom:12px; margin-bottom:20px}
.brand{font-size:18px; letter-spacing:.22em; font-weight:700}
.brand b{color:var(--amber)}
.sys{color:var(--dim); font-size:12px; letter-spacing:.08em}
.cursor{display:inline-block; width:.6em; height:1.05em; background:var(--fg);
  vertical-align:-.15em; margin-left:.2em; animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
.panel{position:relative; border:1px solid var(--line); margin:0 0 20px; padding:20px 16px 16px;
  background:linear-gradient(180deg, rgba(14,30,17,.75), rgba(7,13,8,.9))}
.panel::before,.panel::after{content:""; position:absolute; width:12px; height:12px;
  border:2px solid var(--fg); opacity:.75}
.panel::before{top:-1px; left:-1px; border-right:0; border-bottom:0}
.panel::after{bottom:-1px; right:-1px; border-left:0; border-top:0}
.panel > h2{margin:0 0 14px; font-size:12px; letter-spacing:.24em; color:var(--amber); font-weight:700}
.panel > h2 em{color:var(--faint); font-style:normal; margin-right:.6em}
.hint{color:var(--dim); font-size:12px; margin:6px 0 0}
.banner{padding:10px 12px; border:1px solid; margin:0 0 14px; font-size:13px; letter-spacing:.04em}
.banner.good{border-color:var(--faint); color:var(--fg)}
.banner.bad{border-color:var(--red); color:var(--red); background:rgba(255,95,95,.07)}
.banner.warn{border-color:var(--amber); color:var(--amber); background:rgba(255,180,84,.07)}
.group{margin:16px 0 6px; font-size:11px; letter-spacing:.2em; color:var(--dim)}
.row{display:grid; grid-template-columns:minmax(0,1fr) auto; gap:4px 12px; align-items:start;
  padding:8px 0; border-top:1px dashed var(--faint)}
.row .name{overflow-wrap:anywhere; color:var(--fg)}
.row .desc{color:var(--dim); font-size:12px; grid-column:1 / 3}
.row .note{color:var(--amber); font-size:12px; grid-column:1 / 3}
.tag{font-weight:700; letter-spacing:.06em; white-space:nowrap}
.tag.ok{color:var(--fg)} .tag.unset{color:var(--faint)}
.tag.missing,.tag.danger{color:var(--red)} .tag.invalid,.tag.weak{color:var(--amber)}
.tag.danger{animation:blink 1.4s steps(1) infinite}
.gen{grid-column:1 / 3; margin-top:4px}
.genout{display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:6px}
code,.box{font-family:var(--mono); background:#020402; border:1px solid var(--line);
  padding:6px 8px; word-break:break-all; color:var(--cyan); text-shadow:none}
button{font:inherit; cursor:pointer; color:var(--fg); background:transparent;
  border:1px solid var(--fg); padding:6px 12px; letter-spacing:.1em; font-size:12px;
  text-shadow:inherit; min-height:34px}
button:hover,button:focus-visible{background:var(--fg); color:#031006; outline:none; text-shadow:none}
button.alt{border-color:var(--dim); color:var(--dim)}
button.alt:hover{background:var(--dim); color:#031006}
button:disabled{opacity:.4; cursor:default}
button.on{background:var(--fg); color:#031006; text-shadow:none}
input{font:inherit; color:var(--fg); background:#020402; border:1px solid var(--line);
  padding:8px 10px; width:100%; min-height:38px; text-shadow:none}
input:focus{outline:1px solid var(--fg); border-color:var(--fg)}
label{display:block; font-size:11px; letter-spacing:.18em; color:var(--dim); margin:12px 0 4px}
.line{display:flex; flex-wrap:wrap; gap:8px; align-items:center}
.line .box{flex:1 1 260px}
.tabs{display:flex; gap:8px; margin-bottom:6px}
.log{background:#020402; border:1px solid var(--line); padding:10px; margin:12px 0 0;
  min-height:72px; max-height:260px; overflow:auto; white-space:pre-wrap; word-break:break-word;
  font-size:12.5px; text-shadow:none}
.log .ok{color:var(--fg)} .log .bad{color:var(--red)} .log .warn{color:var(--amber)}
.log .t{color:var(--faint)}
.center{max-width:430px; margin:8vh auto 0}
.err{color:var(--red); min-height:1.4em; margin:10px 0 0; font-size:13px}
.hidden{display:none !important}
.ep{display:grid; grid-template-columns:56px 1fr auto; gap:4px 12px; padding:7px 0;
  border-top:1px dashed var(--faint); align-items:center}
.ep .m{color:var(--amber); font-size:12px}
@media (max-width:620px){
  .ep{grid-template-columns:48px 1fr} .ep button{grid-column:1 / 3}
}
@media (prefers-reduced-motion:reduce){.cursor,.tag.danger{animation:none}}
</style>
</head>
<body>
<main>
  <header class="top">
    <div class="brand">&#9612;ARCHIVE&nbsp;TERMINAL <b>//</b> INSTAGRAM-MCP<span class="cursor"></span></div>
    <div class="sys" id="sys">NODE: <span id="node">&mdash;</span></div>
  </header>

  <!-- LOGIN -->
  <section id="login" class="panel center hidden">
    <h2><em>00</em>AUTHENTICATION REQUIRED</h2>
    <form id="loginForm" autocomplete="on">
      <div id="fUser"><label for="u">USERNAME</label><input id="u" name="username" autocomplete="username"></div>
      <div id="fPass"><label for="p">PASSWORD</label><input id="p" name="password" type="password" autocomplete="current-password"></div>
      <div id="fKey" class="hidden"><label for="k">ACCESS KEY (MCP_AUTH_KEY)</label><input id="k" name="key" type="password" autocomplete="off"></div>
      <div class="line" style="margin-top:14px"><button type="submit" id="loginBtn">[ ENTER ]</button></div>
      <div class="err" id="loginErr" role="alert"></div>
    </form>
    <p class="hint" id="loginHint"></p>
  </section>

  <!-- SETUP (no auth configured) -->
  <section id="setup" class="hidden">
    <div class="banner bad">&#9888; DASHBOARD LOCKED: no MCP_AUTH_KEY is set. Add the required variables below in
    Vercel &rarr; Settings &rarr; Environment Variables, then redeploy.</div>
  </section>

  <!-- DASHBOARD -->
  <div id="app" class="hidden">
    <section class="panel" id="pEnv">
      <h2><em>01</em>SYSTEM CHECK // ENVIRONMENT</h2>
      <div id="envBanner"></div>
      <div id="envRows"></div>
      <p class="hint">Values are never shown here, only whether each variable is set. After changing variables in
      Vercel you must redeploy.</p>
    </section>

    <section class="panel" id="pConnect">
      <h2><em>02</em>CONNECT // MCP URL</h2>
      <div class="line">
        <div class="box" id="mcpUrl">&mdash;</div>
        <button id="revealBtn" class="alt">[ REVEAL ]</button>
        <button id="copyUrlBtn">[ COPY URL ]</button>
      </div>
      <p class="hint">Paste the full URL into your AI app as a custom MCP connector. Treat it like a password.</p>
      <div style="margin-top:14px">
        <div class="ep"><span class="m">ANY</span><span>/mcp</span><button class="alt" data-copy="mcp">[ COPY ]</button></div>
        <div class="ep"><span class="m">GET</span><span>/healthz</span><button class="alt" data-copy="health">[ COPY ]</button></div>
        <div class="ep"><span class="m">GET</span><span>/upload</span><button class="alt" data-copy="upload">[ COPY ]</button></div>
        <div class="ep"><span class="m">POST</span><span>/api/upload</span><span></span></div>
        <div class="ep"><span class="m">GET</span><span>/api/cleanup (cron)</span><span></span></div>
      </div>
    </section>

    <section class="panel" id="pTest">
      <h2><em>03</em>ENDPOINT TEST</h2>
      <label for="tk">TYPE YOUR MCP KEY TO TEST IT</label>
      <div class="line"><input id="tk" type="password" autocomplete="off" style="flex:1 1 260px">
        <button id="testBtn">[ RUN TESTS ]</button></div>
      <div class="log" id="testLog" aria-live="polite"></div>
      <p class="hint">Runs from your browser against this site. A wrong key should be rejected; the right key should pass.</p>
    </section>

    <section class="panel" id="pSession">
      <h2><em>04</em>INSTAGRAM SESSION</h2>
      <div class="banner warn" id="storeBanner"></div>
      <div class="tabs">
        <button id="tabCookie" class="on">COOKIE</button>
        <button id="tabPass" class="alt">USERNAME + PASSWORD</button>
      </div>
      <div id="formCookie">
        <label for="sid">SESSIONID COOKIE</label><input id="sid" type="password" autocomplete="off">
        <label for="sun">USERNAME (OPTIONAL)</label><input id="sun" autocomplete="off">
        <p class="hint">Log in at instagram.com in your own browser first and solve any captcha there. Then press F12 &rarr;
        Application &rarr; Cookies &rarr; instagram.com &rarr; copy the value of <b>sessionid</b>.</p>
        <div class="line" style="margin-top:12px"><button id="saveCookie">[ SAVE SESSION ]</button></div>
      </div>
      <div id="formPass" class="hidden">
        <label for="iun">INSTAGRAM USERNAME</label><input id="iun" autocomplete="off">
        <label for="ipw">INSTAGRAM PASSWORD</label><input id="ipw" type="password" autocomplete="off">
        <p class="hint">Fallback only. Logins from Vercel's servers often trigger a security check, and a captcha
        cannot be solved here.</p>
        <div class="line" style="margin-top:12px"><button id="savePass">[ LOG IN ]</button></div>
      </div>
      <div id="codeBox" class="hidden">
        <label for="code" id="codeLabel">VERIFICATION CODE</label>
        <div class="line"><input id="code" autocomplete="one-time-code" style="flex:1 1 200px"><button id="sendCode">[ SUBMIT CODE ]</button></div>
      </div>
      <div class="line" style="margin-top:12px"><button class="alt" id="checkSession">[ CHECK STATUS ]</button></div>
      <div class="log" id="sessLog" aria-live="polite"></div>
    </section>

    <div class="line" style="justify-content:space-between">
      <span class="hint">SESSION OPEN &middot; 8 HOURS</span>
      <button class="alt" id="logoutBtn">[ LOG OUT ]</button>
    </div>
  </div>
</main>

<script>
"use strict";
const $ = (s) => document.querySelector(s);
const show = (el, on) => el.classList.toggle("hidden", !on);
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
async function api(path, body) {
  const opt = body === undefined ? {} :
    {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const r = await fetch("/api/main?admin=" + encodeURIComponent(path), opt);
  let data = {};
  try { data = await r.json(); } catch (e) {}
  return {status: r.status, data};
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {}
  const ta = el("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  let ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
  ta.remove(); return ok;
}
function flash(btn, text) {
  const old = btn.textContent; btn.textContent = text;
  setTimeout(() => { btn.textContent = old; }, 1200);
}
function logLine(box, cls, msg) {
  const t = new Date().toTimeString().slice(0, 8);
  const d = el("div");
  d.appendChild(el("span", "t", t + "  "));
  d.appendChild(el("span", cls, msg));
  box.appendChild(d); box.scrollTop = box.scrollHeight;
}

/* ---------- key generators (run in your browser; nothing is sent anywhere) ---------- */
function rand(n) { const a = new Uint8Array(n); crypto.getRandomValues(a); return a; }
const hex = (a) => Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
function b64url(a) { return btoa(String.fromCharCode(...a)).replace(/\+/g, "-").replace(/\//g, "_"); }
function password(n) {
  const set = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_@#%";
  return Array.from(rand(n), (b) => set[b % set.length]).join("");
}
const GEN = {
  MCP_AUTH_KEY: () => hex(rand(32)),
  CRON_SECRET: () => hex(rand(32)),
  SESSION_ENCRYPTION_KEY: () => b64url(rand(32)),
  ADMIN_PASSWORD: () => password(24),
};

/* ---------- state ---------- */
let origin = location.origin;

async function boot() {
  show($("#login"), false); show($("#setup"), false); show($("#app"), false);
  $("#node").textContent = location.host;
  let info;
  try { info = (await api("info")).data; } catch (e) { info = null; }
  if (!info) { show($("#setup"), true); $("#setup").firstElementChild.textContent = "Cannot reach the server."; return; }
  if (info.mode === "none") {
    show($("#setup"), true);
    const s = (await api("status")).data;
    if (s && s.env) { show($("#app"), true); renderEnv(s.env); for (const id of ["#pConnect", "#pTest", "#pSession"]) show($(id), false); }
    return;
  }
  if (!info.authenticated) { showLogin(info.mode); return; }
  await loadApp();
}

function showLogin(mode) {
  show($("#login"), true);
  const pw = mode === "password";
  show($("#fUser"), pw); show($("#fPass"), pw); show($("#fKey"), !pw);
  $("#loginHint").textContent = pw
    ? "Sign in with ADMIN_USERNAME and ADMIN_PASSWORD."
    : "Paste your MCP_AUTH_KEY. Set ADMIN_USERNAME and ADMIN_PASSWORD to use a login name instead.";
  (pw ? $("#u") : $("#k")).focus();
}

$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pw = !$("#fUser").classList.contains("hidden");
  const body = pw ? {username: $("#u").value, password: $("#p").value} : {key: $("#k").value};
  $("#loginBtn").disabled = true; $("#loginErr").textContent = "";
  const r = await api("login", body);
  $("#loginBtn").disabled = false;
  if (r.status === 200) { $("#p").value = ""; $("#k").value = ""; boot(); }
  else $("#loginErr").textContent = "⚠ " + (r.data.error || "Login failed.");
});

async function loadApp() {
  const r = await api("status");
  if (r.status === 401) { boot(); return; }
  const s = r.data;
  show($("#app"), true);
  for (const id of ["#pConnect", "#pTest", "#pSession"]) show($(id), true);
  origin = s.origin || location.origin;
  $("#mcpUrl").textContent = s.mcp_url_masked;
  renderEnv(s.env);
  const st = s.storage || {};
  const b = $("#storeBanner");
  const where = st.backend === "blob" ? "Vercel Blob" : "this server's temporary disk (lost on restart)";
  b.textContent = "Session storage: " + where + (st.encryption ? ", encrypted." : ", NOT encrypted.") +
    (st.exists === false ? " No session saved yet." : st.exists ? " A session is saved." : "") +
    (st.error ? " Error: " + st.error : "");
}

/* ---------- environment checklist ---------- */
const TAGS = {ok: "[ OK ]", missing: "[ ⚠ MISSING ]", invalid: "[ ⚠ INVALID ]",
  weak: "[ ⚠ WEAK ]", danger: "[ ⚠ DANGER ]", unset: "[ — UNSET ]"};

function renderEnv(env) {
  const banner = $("#envBanner"); banner.replaceChildren();
  const bad = env.required_bad;
  const b = el("div", "banner " + (bad ? "bad" : env.warnings ? "warn" : "good"));
  b.textContent = bad
    ? "⚠ " + bad + " OF " + env.required_total + " REQUIRED VARIABLES NEED ATTENTION"
    : env.warnings ? "✔ ALL REQUIRED VARIABLES PRESENT — " + env.warnings + " WARNING(S) BELOW"
    : "✔ ALL REQUIRED VARIABLES PRESENT";
  banner.appendChild(b);

  const wrap = $("#envRows"); wrap.replaceChildren();
  const groups = [["required", "REQUIRED — you must set these"],
    ["recommended", "RECOMMENDED — strongly advised"],
    ["optional", "OPTIONAL — skip unless you need them"],
    ["danger", "DANGEROUS — never set"]];
  for (const [level, title] of groups) {
    const rows = env.rows.filter((r) => r.level === level);
    if (!rows.length) continue;
    wrap.appendChild(el("div", "group", "// " + title));
    for (const r of rows) {
      const row = el("div", "row");
      row.appendChild(el("div", "name", r.name));
      row.appendChild(el("div", "tag " + r.state, TAGS[r.state] || r.state));
      row.appendChild(el("div", "desc", r.desc));
      if (r.note) row.appendChild(el("div", "note", "⚠ " + r.note));
      if (GEN[r.name]) {
        const g = el("div", "gen");
        const btn = el("button", "alt", r.state === "ok" ? "[ REGENERATE ]" : "[ GEN ]");
        const out = el("div", "genout hidden");
        btn.addEventListener("click", () => {
          const v = GEN[r.name]();
          out.replaceChildren(); show(out, true);
          out.appendChild(el("code", "", v));
          const cp = el("button", "", "[ COPY ]");
          cp.addEventListener("click", async () => flash(cp, (await copyText(v)) ? "COPIED" : "COPY FAILED"));
          out.appendChild(cp);
          out.appendChild(el("div", "hint", r.name === "SESSION_ENCRYPTION_KEY" && r.state === "ok"
            ? "Replacing this makes the saved Instagram session unreadable; you will need to add it again."
            : "Paste into Vercel → Settings → Environment Variables (Production), then redeploy."));
        });
        g.appendChild(btn); g.appendChild(out); row.appendChild(g);
      }
      wrap.appendChild(row);
    }
  }
}

/* ---------- connect panel ---------- */
let revealed = false;
async function getReveal() { const r = await api("reveal", {}); return r.data; }
$("#revealBtn").addEventListener("click", async () => {
  if (revealed) { const s = (await api("status")).data; $("#mcpUrl").textContent = s.mcp_url_masked; revealed = false; $("#revealBtn").textContent = "[ REVEAL ]"; return; }
  const d = await getReveal(); $("#mcpUrl").textContent = d.mcp_url || ""; revealed = true; $("#revealBtn").textContent = "[ HIDE ]";
});
$("#copyUrlBtn").addEventListener("click", async (e) => {
  const d = await getReveal();
  flash(e.target, (await copyText(d.mcp_url || "")) ? "COPIED" : "COPY FAILED");
});
document.querySelectorAll("[data-copy]").forEach((btn) => btn.addEventListener("click", async () => {
  const d = await getReveal(); const key = d.key ? encodeURIComponent(d.key) : "";
  const map = {mcp: origin + "/mcp" + (key ? "?auth=" + key : ""), health: origin + "/healthz",
    upload: origin + "/upload" + (key ? "?auth=" + key : "")};
  flash(btn, (await copyText(map[btn.dataset.copy])) ? "COPIED" : "COPY FAILED");
}));

/* ---------- endpoint tests (run in the browser, against this site) ---------- */
function parseRpc(text) {
  const line = text.split("\n").find((l) => l.startsWith("data:"));
  try { return JSON.parse(line ? line.slice(5) : text); } catch (e) { return null; }
}
$("#testBtn").addEventListener("click", async () => {
  const key = $("#tk").value.trim(); const box = $("#testLog"); box.replaceChildren();
  if (!key) { logLine(box, "warn", "Type your MCP key in the box first."); return; }
  const hdr = (k) => ({"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
    "Authorization": "Bearer " + k});
  const rpc = (method, params, id) => JSON.stringify({jsonrpc: "2.0", id, method, params});
  const init = {protocolVersion: "2025-03-26", capabilities: {}, clientInfo: {name: "dashboard-test", version: "1"}};
  const tests = [
    ["GET  /healthz", async () => { const r = await fetch("/healthz"); return [r.status === 200, "HTTP " + r.status]; }],
    ["POST /mcp  initialize", async () => {
      const r = await fetch("/mcp", {method: "POST", headers: hdr(key), body: rpc("initialize", init, 1)});
      const j = parseRpc(await r.text()); const n = j && j.result && j.result.serverInfo && j.result.serverInfo.name;
      return [r.ok && !!n, "HTTP " + r.status + (n ? " server=" + n : "")]; }],
    ["POST /mcp  tools/list", async () => {
      const r = await fetch("/mcp", {method: "POST", headers: hdr(key), body: rpc("tools/list", {}, 2)});
      const j = parseRpc(await r.text()); const c = j && j.result && j.result.tools && j.result.tools.length;
      return [r.ok && c > 0, "HTTP " + r.status + (c ? " " + c + " tools" : "")]; }],
    ["POST /mcp  wrong key is rejected", async () => {
      const r = await fetch("/mcp", {method: "POST", headers: hdr(key + "x"), body: rpc("initialize", init, 3)});
      return [r.status === 401, "HTTP " + r.status + (r.status === 401 ? " (correct)" : " (should be 401)")]; }],
    ["POST /api/upload  key accepted", async () => {
      const r = await fetch("/api/upload", {method: "POST", headers: {"Content-Type": "application/json", "X-Auth-Key": key},
        body: JSON.stringify({action: "ping"})});
      return [r.status !== 401 && r.status < 500, "HTTP " + r.status + (r.status === 401 ? " (key rejected)" : "")]; }],
  ];
  let pass = 0;
  for (const [name, fn] of tests) {
    try { const [ok, info] = await fn(); if (ok) pass++; logLine(box, ok ? "ok" : "bad", (ok ? "[ PASS ] " : "[ FAIL ] ") + name + "  " + info); }
    catch (e) { logLine(box, "bad", "[ FAIL ] " + name + "  " + e.message); }
  }
  logLine(box, pass === tests.length ? "ok" : "warn", "-- " + pass + "/" + tests.length + " passed");
});

/* ---------- instagram session ---------- */
function setTab(cookie) {
  show($("#formCookie"), cookie); show($("#formPass"), !cookie);
  $("#tabCookie").className = cookie ? "on" : "alt"; $("#tabPass").className = cookie ? "alt" : "on";
}
$("#tabCookie").addEventListener("click", () => setTab(true));
$("#tabPass").addEventListener("click", () => setTab(false));
let pendingCode = "";
function report(r) {
  const box = $("#sessLog"); const d = r.data || {};
  const cls = d.status === "success" ? "ok" : d.status === "error" ? "bad" : "warn";
  if (r.status === 401) { boot(); return; }
  logLine(box, cls, (d.status || "result").toUpperCase() + ": " + (d.message || JSON.stringify(d)));
  pendingCode = d.status === "needs_2fa" ? "2fa" : d.status === "needs_challenge" ? "challenge" : "";
  show($("#codeBox"), !!pendingCode);
  $("#codeLabel").textContent = pendingCode === "2fa" ? "2FA CODE (AUTHENTICATOR APP)" : "CODE SENT TO EMAIL / SMS";
  if (d.status === "success") { $("#sid").value = ""; $("#ipw").value = ""; loadApp(); }
}
async function sessionCall(body, btn) {
  btn.disabled = true; logLine($("#sessLog"), "warn", "working...");
  try { report(await api("session", body)); } finally { btn.disabled = false; }
}
$("#saveCookie").addEventListener("click", (e) => sessionCall({action: "cookie", sessionid: $("#sid").value, username: $("#sun").value}, e.target));
$("#savePass").addEventListener("click", (e) => sessionCall({action: "password", username: $("#iun").value, password: $("#ipw").value}, e.target));
$("#sendCode").addEventListener("click", (e) => sessionCall({action: pendingCode || "2fa", code: $("#code").value}, e.target));
$("#checkSession").addEventListener("click", (e) => sessionCall({action: "status"}, e.target));

$("#logoutBtn").addEventListener("click", async () => { await api("logout", {}); boot(); });
boot();
</script>
</body>
</html>
"""
