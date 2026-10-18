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
  --bg:#020503; --line:#15351d; --faint:#24502f; --dim:#3fa15a;
  --fg:#7dff9e;            /* phosphor green: body text */
  --cyan:#5ef0ff;          /* headings, warnings, links */
  --red:#ff5c5c;           /* danger, missing */
  --white:#eefaf1;         /* values, emphasis */
  --mono:ui-monospace,"Cascadia Mono","SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box}
html{background:var(--bg); -webkit-text-size-adjust:100%}
body{
  margin:0; min-height:100vh; color:var(--fg); font:14px/1.55 var(--mono); overflow-x:hidden;
  background:
    radial-gradient(ellipse at 50% -15%, rgba(94,240,255,.10), transparent 55%),
    radial-gradient(ellipse at 50% 120%, rgba(125,255,158,.08), transparent 55%),
    var(--bg);
  text-shadow:0 0 6px rgba(125,255,158,.35);
}
body::before{ /* scanlines */
  content:""; position:fixed; inset:0; pointer-events:none; z-index:50;
  background:repeating-linear-gradient(0deg, rgba(0,0,0,.28) 0 1px, transparent 1px 3px);
}
body::after{ /* curved-glass vignette */
  content:""; position:fixed; inset:0; pointer-events:none; z-index:49;
  background:radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,.62) 100%);
  box-shadow:inset 0 0 90px rgba(0,0,0,.9);
}
.roll{ /* slow rolling refresh bar, like an old monitor */
  position:fixed; left:0; right:0; height:120px; top:-120px; pointer-events:none; z-index:51;
  background:linear-gradient(180deg, transparent, rgba(125,255,158,.05), transparent);
  animation:roll 7s linear infinite;
}
@keyframes roll{to{transform:translateY(calc(100vh + 240px))}}
main{max-width:1100px; margin:0 auto; padding:20px 16px 72px; position:relative; z-index:1;
  animation:flicker 6s steps(1) infinite}
@keyframes flicker{0%,92%,100%{opacity:1} 93%{opacity:.94} 95%{opacity:.99}}
header.top{display:flex; flex-wrap:wrap; justify-content:space-between; gap:6px 16px;
  align-items:baseline; border-bottom:1px solid var(--line); padding-bottom:12px; margin-bottom:18px}
.brand{font-size:clamp(14px,3.6vw,18px); letter-spacing:.2em; font-weight:700; color:var(--white);
  text-shadow:0 0 10px rgba(94,240,255,.55)}
.brand b{color:var(--cyan)}
.sys{color:var(--dim); font-size:12px; letter-spacing:.08em}
.cursor{display:inline-block; width:.6em; height:1.05em; background:var(--cyan);
  vertical-align:-.15em; margin-left:.2em; animation:blink 1.1s steps(1) infinite;
  box-shadow:0 0 8px var(--cyan)}
@keyframes blink{50%{opacity:0}}
.panel{position:relative; border:1px solid var(--line); margin:0 0 18px; padding:20px 16px 16px;
  background:linear-gradient(180deg, rgba(12,28,15,.8), rgba(5,11,6,.92));
  box-shadow:0 0 0 1px rgba(0,0,0,.6), 0 0 24px rgba(125,255,158,.05)}
.panel::before,.panel::after{content:""; position:absolute; width:14px; height:14px;
  border:2px solid var(--cyan); opacity:.8}
.panel::before{top:-1px; left:-1px; border-right:0; border-bottom:0}
.panel::after{bottom:-1px; right:-1px; border-left:0; border-top:0}
.panel > h2{margin:0 0 14px; font-size:12px; letter-spacing:.22em; color:var(--cyan); font-weight:700;
  text-shadow:0 0 8px rgba(94,240,255,.45)}
.panel > h2 em,details > summary em{color:var(--dim); font-style:normal; margin-right:.6em}
.hint{color:var(--dim); font-size:12px; margin:6px 0 0}
.hint a,.hint a:visited{color:var(--cyan)}
.banner{padding:10px 12px; border:1px solid; margin:0 0 14px; font-size:13px; letter-spacing:.03em}
.banner.good{border-color:var(--faint); color:var(--fg)}
.banner.bad{border-color:var(--red); color:var(--red); background:rgba(255,92,92,.08)}
.banner.warn{border-color:var(--cyan); color:var(--cyan); background:rgba(94,240,255,.06)}
.kv{display:grid; grid-template-columns:max-content minmax(0,1fr); gap:8px 16px; margin:14px 0 0; font-size:13px}
.kv dt{color:var(--cyan); letter-spacing:.14em; font-size:11px; padding-top:2px}
.kv dd{margin:0; color:var(--white); overflow-wrap:anywhere}
.sub{font-size:12px; letter-spacing:.2em; color:var(--white); margin:22px 0 6px; font-weight:700}
.btns{margin-top:12px}

/* collapsible sections */
details > summary{cursor:pointer; list-style:none; color:var(--cyan); letter-spacing:.22em;
  font-size:12px; font-weight:700; text-shadow:0 0 8px rgba(94,240,255,.45); padding:2px 0 4px}
details > summary::-webkit-details-marker{display:none}
details > summary::before{content:"\25B8  "; color:var(--dim)}
details[open] > summary::before{content:"\25BE  "}
details[open] > summary{margin-bottom:14px}
details.group{border-top:1px dashed var(--faint); margin-top:14px; padding-top:4px}
details.group > summary{color:var(--white); letter-spacing:.14em; font-size:11px; font-weight:400;
  text-shadow:none; padding:8px 0}
details.group[open] > summary{margin-bottom:4px}

/* environment rows */
.row{display:block; padding:12px 0; border-top:1px dashed var(--faint)}
.rowhead{display:flex; justify-content:space-between; align-items:baseline; gap:4px 12px; flex-wrap:wrap}
.row .name{overflow-wrap:anywhere; color:var(--white)}
.row .desc{color:var(--dim); font-size:12px; margin-top:4px}
.row .note{color:var(--cyan); font-size:12px; margin-top:2px}
.row .box{margin-top:10px}
.acts{display:flex; flex-wrap:wrap; gap:8px; margin-top:10px}
.genout{display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:8px; width:100%}
.genout code{word-break:break-all}
.genout .hint{width:100%; margin:0}
.tag{font-weight:700; letter-spacing:.06em; white-space:nowrap}
.tag.ok{color:var(--fg)} .tag.unset{color:var(--faint)}
.tag.missing,.tag.danger{color:var(--red)} .tag.invalid,.tag.weak{color:var(--white); background:rgba(94,240,255,.15); padding:0 4px}
.tag.danger{animation:blink 1.4s steps(1) infinite}

code,.box{font-family:var(--mono); background:#010301; border:1px solid var(--line);
  padding:8px 10px; word-break:break-all; color:var(--cyan); text-shadow:none}
button{font:inherit; cursor:pointer; color:var(--fg); background:transparent;
  border:1px solid var(--fg); padding:8px 14px; letter-spacing:.1em; font-size:12px;
  text-shadow:inherit; min-height:40px; touch-action:manipulation}
button:hover,button:focus-visible{background:var(--fg); color:#021004; outline:none; text-shadow:none}
button.alt{border-color:var(--cyan); color:var(--cyan)}
button.alt:hover,button.alt:focus-visible{background:var(--cyan); color:#021004}
button:disabled{opacity:.4; cursor:default}
button.on{background:var(--cyan); border-color:var(--cyan); color:#021004; text-shadow:none}
.btn{display:inline-flex; align-items:center; justify-content:center; min-height:44px; padding:0 16px;
  border:1px solid var(--cyan); color:var(--cyan); text-decoration:none; letter-spacing:.1em;
  font-size:12px; text-shadow:none}
.btn:hover,.btn:focus-visible{background:var(--cyan); color:#021004; outline:none}
input{font:inherit; color:var(--white); background:#010301; border:1px solid var(--line);
  padding:9px 10px; width:100%; min-height:42px; text-shadow:none; font-size:16px}
input:focus{outline:1px solid var(--cyan); border-color:var(--cyan)}
label{display:block; font-size:11px; letter-spacing:.16em; color:var(--cyan); margin:12px 0 4px}
.line{display:flex; flex-wrap:wrap; gap:8px; align-items:center}
.line .box{flex:1 1 260px}
.tabs{display:flex; flex-wrap:wrap; gap:8px; margin-bottom:6px}
.log{background:#010301; border:1px solid var(--line); padding:10px; margin:12px 0 0;
  min-height:72px; max-height:280px; overflow:auto; white-space:pre-wrap; word-break:break-word;
  font-size:12.5px; text-shadow:none}
.log .ok{color:var(--fg)} .log .bad{color:var(--red)} .log .warn{color:var(--cyan)}
.log .t{color:var(--faint)}
.center{max-width:460px; width:100%; margin:6vh auto 0}
.err{color:var(--red); min-height:1.4em; margin:10px 0 0; font-size:13px}
.hidden{display:none !important}
.foot{justify-content:space-between; margin-top:6px}

/* Two columns on wide screens; one column on phones */
@media (min-width:980px){
  #app{display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:0 18px; align-items:start}
  #app > .panel.wide, #app > .foot{grid-column:1 / -1}
}
@media (max-width:620px){
  main{padding:14px 12px 56px}
  .panel{padding:18px 12px 14px}
  .line > button, .line > input, .line > .btn{width:100%}
  .genout > button{width:100%}
  .acts > button{flex:1 1 140px}
  .foot{flex-direction:column; align-items:stretch; gap:10px}
  .row .box{font-size:12px}
  .log{max-height:45vh}
}
@media (pointer:coarse){ button{min-height:46px} }
@media (prefers-reduced-motion:reduce){ .cursor,.tag.danger,main,.roll{animation:none} }
</style>
</head>
<body>
<div class="roll" aria-hidden="true"></div>
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

  <!-- SETUP (no auth configured yet) -->
  <section id="setup" class="hidden">
    <div class="banner bad" id="setupNote">&#9888; DASHBOARD LOCKED: set MCP_AUTH_KEY (or ADMIN_USERNAME + ADMIN_PASSWORD)
      in Vercel &rarr; Settings &rarr; Environment Variables, redeploy, then reload.</div>
    <section class="panel">
      <h2><em>00</em>SETUP // ENVIRONMENT</h2>
      <div id="setupBanner"></div>
      <div id="setupRows"></div>
    </section>
  </section>

  <!-- DASHBOARD -->
  <div id="app" class="hidden">
    <section class="panel" id="pStatus">
      <h2><em>01</em>STATUS</h2>
      <div id="envBanner"></div>
      <dl class="kv">
        <dt>AUTH</dt><dd id="kvMode">&mdash;</dd>
        <dt>STORAGE</dt><dd id="kvStorage">&mdash;</dd>
        <dt>SERVER</dt><dd id="kvOrigin">&mdash;</dd>
      </dl>
    </section>

    <section class="panel" id="pConnect">
      <h2><em>02</em>CONNECT</h2>
      <p class="hint">Your MCP URL contains the key. Treat it like a password.</p>
      <div class="line" style="margin-top:12px">
        <div class="box" id="mcpUrl">&hellip;</div>
        <button id="revealBtn" class="alt">[ REVEAL ]</button>
      </div>
      <div class="line btns">
        <button id="copyUrlBtn">[ COPY MCP URL ]</button>
        <button class="alt" data-copy="health">[ COPY HEALTH URL ]</button>
        <button class="alt" data-copy="upload">[ COPY UPLOAD PAGE ]</button>
      </div>

      <h3 class="sub">BROWSER SYNC EXTENSION</h3>
      <p class="hint">Chrome or Firefox. It sends your Instagram login to this server, encrypted, so the session stays fresh.</p>
      <div class="line btns">
        <a class="btn" href="/api/main?admin=extension" download>[ DOWNLOAD CONFIGURED EXTENSION ]</a>
      </div>
      <p class="hint">Ready to use: this server's address and keys are already filled in. Don't share the file.</p>
      <p class="hint">Without keys: <a href="/extension/instagram-mcp-sync.zip">instagram-mcp-sync.zip</a>
        &middot; <a href="/extension/README.md">setup guide</a> (you enter the address and keys yourself).</p>
    </section>

    <section class="panel wide" id="pEnv">
      <h2><em>03</em>ENVIRONMENT</h2>
      <p class="hint">Values stay hidden. Press SHOW to reveal MCP_AUTH_KEY or SESSION_ENCRYPTION_KEY. Optional and
        dangerous groups are collapsed. After changing a variable in Vercel, redeploy.</p>
      <div id="envRows"></div>
    </section>

    <section class="panel" id="pTest">
      <details>
        <summary><em>04</em>ENDPOINT TEST</summary>
        <label for="tk">OPTIONAL: TYPE A DIFFERENT KEY TO TEST IT</label>
        <div class="line"><input id="tk" type="password" autocomplete="off" style="flex:1 1 220px">
          <button id="testBtn">[ RUN TESTS ]</button></div>
        <div class="log" id="testLog" aria-live="polite"></div>
        <p class="hint">Leave the box empty to test with the MCP key from your dashboard session. A wrong key should be rejected; the right key should pass.</p>
      </details>
    </section>

    <section class="panel" id="pSession">
      <details open>
        <summary><em>05</em>INSTAGRAM SESSION</summary>
        <div class="banner warn" id="storeBanner"></div>
        <div class="tabs">
          <button id="tabCookie" class="on">COOKIE</button>
          <button id="tabPass" class="alt">USERNAME + PASSWORD</button>
        </div>
        <div id="formCookie">
          <label for="sid">SESSIONID COOKIE</label><input id="sid" type="password" autocomplete="off">
          <label for="sun">USERNAME (OPTIONAL)</label><input id="sun" autocomplete="off">
          <p class="hint">Easiest: use the browser extension, which syncs this for you. Manual: log in at instagram.com, solve any captcha there, then copy the <b>sessionid</b> cookie (F12 &rarr; Application &rarr; Cookies).</p>
          <div class="line btns"><button id="saveCookie">[ SAVE SESSION ]</button></div>
        </div>
        <div id="formPass" class="hidden">
          <label for="iun">INSTAGRAM USERNAME</label><input id="iun" autocomplete="off">
          <label for="ipw">INSTAGRAM PASSWORD</label><input id="ipw" type="password" autocomplete="off">
          <p class="hint">Fallback only. Logins from Vercel's servers often trigger a security check, and a captcha cannot be solved here.</p>
          <div class="line btns"><button id="savePass">[ LOG IN ]</button></div>
        </div>
        <div id="codeBox" class="hidden">
          <label for="code" id="codeLabel">VERIFICATION CODE</label>
          <div class="line"><input id="code" autocomplete="one-time-code" style="flex:1 1 200px"><button id="sendCode">[ SUBMIT CODE ]</button></div>
        </div>
        <div class="line btns"><button class="alt" id="checkSession">[ CHECK STATUS ]</button></div>
        <div class="log" id="sessLog" aria-live="polite"></div>
      </details>
    </section>

    <div class="line foot">
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
// Secrets the dashboard may reveal to a logged-in admin (the server enforces the same list).
const SECRETS = {MCP_AUTH_KEY: true, SESSION_ENCRYPTION_KEY: true};

/* ---------- state ---------- */
let origin = location.origin;
let revealed = false;
let maskedUrl = "";
let pendingCode = "";

async function boot() {
  show($("#login"), false); show($("#setup"), false); show($("#app"), false);
  $("#node").textContent = location.host;
  let info = null;
  try { info = (await api("info")).data; } catch (e) { info = null; }
  if (!info) {
    show($("#setup"), true);
    $("#setupNote").textContent = "Cannot reach the server. Reload to try again.";
    return;
  }
  if (info.mode === "none") {
    show($("#setup"), true);
    const s = (await api("status")).data;
    if (s && s.env) renderEnv(s.env, $("#setupBanner"), $("#setupRows"), false);
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
  origin = s.origin || location.origin;
  maskedUrl = s.mcp_url_masked || "";
  revealed = false; $("#revealBtn").textContent = "[ REVEAL ]";
  $("#mcpUrl").textContent = maskedUrl;
  renderEnv(s.env, $("#envBanner"), $("#envRows"), true);
  const st = s.storage || {};
  const where = st.backend === "blob" ? "Vercel Blob" : "temporary disk (lost on restart)";
  const summary = where + (st.encryption ? ", encrypted" : ", NOT encrypted") +
    (st.exists === false ? ", no session saved" : st.exists ? ", session saved" : "") +
    (st.error ? " (error: " + st.error + ")" : "");
  $("#kvStorage").textContent = summary;
  $("#storeBanner").textContent = "Session storage: " + summary + ".";
  $("#kvMode").textContent = s.mode === "password" ? "username + password" : "MCP key";
  $("#kvOrigin").textContent = origin;
}

/* ---------- environment checklist ---------- */
const TAGS = {ok: "[ OK ]", missing: "[ ⚠ MISSING ]", invalid: "[ ⚠ INVALID ]",
  weak: "[ ⚠ WEAK ]", danger: "[ ⚠ DANGER ]", unset: "[ — UNSET ]"};

function renderEnv(env, bannerEl, rowsEl, canReveal) {
  // Remember which groups are open, so a refresh doesn't fold them back up.
  const wasOpen = {};
  rowsEl.querySelectorAll("details.group").forEach((d) => { wasOpen[d.dataset.level] = d.open; });
  bannerEl.replaceChildren(); rowsEl.replaceChildren();

  const bad = env.required_bad;
  const b = el("div", "banner " + (bad ? "bad" : env.warnings ? "warn" : "good"));
  b.textContent = bad
    ? "⚠ " + bad + " OF " + env.required_total + " REQUIRED VARIABLES NEED ATTENTION"
    : env.warnings ? "✔ REQUIRED VARIABLES PRESENT — " + env.warnings + " WARNING(S)"
    : "✔ ALL REQUIRED VARIABLES PRESENT";
  bannerEl.appendChild(b);

  const groups = [
    ["required", "REQUIRED", true],
    ["recommended", "RECOMMENDED", true],
    ["optional", "OPTIONAL", false],
    ["danger", "DANGEROUS", false],
  ];
  for (const [level, title, openByDefault] of groups) {
    const rows = env.rows.filter((r) => r.level === level);
    if (!rows.length) continue;
    const setCount = rows.filter((r) => r.set).length;
    const summary = level === "danger"
      ? (setCount ? "⚠ " + setCount + " SET — REMOVE IT" : "none set (correct)")
      : setCount + " of " + rows.length + " set";
    const d = el("details", "group");
    d.dataset.level = level;
    d.open = (level in wasOpen) ? wasOpen[level] : openByDefault;
    d.appendChild(el("summary", "", title + "  ·  " + summary));
    for (const r of rows) d.appendChild(envRow(r, canReveal));
    rowsEl.appendChild(d);
  }
}

function envRow(r, canReveal) {
  const row = el("div", "row");
  const head = el("div", "rowhead");
  head.appendChild(el("span", "name", r.name));
  head.appendChild(el("span", "tag " + r.state, TAGS[r.state] || r.state));
  row.appendChild(head);
  row.appendChild(el("div", "desc", r.desc));
  if (r.note) row.appendChild(el("div", "note", "⚠ " + r.note));

  const acts = el("div", "acts");
  const valueBox = el("div", "box hidden");
  if (canReveal && SECRETS[r.name] && r.set) {
    const showBtn = el("button", "alt", "[ SHOW ]");
    const copyBtn = el("button", "alt", "[ COPY ]");
    let open = false;
    showBtn.addEventListener("click", async () => {
      if (open) {
        valueBox.textContent = ""; show(valueBox, false);
        showBtn.textContent = "[ SHOW ]"; open = false; return;
      }
      const res = await api("secret", {name: r.name});
      if (res.status === 401) { boot(); return; }
      valueBox.textContent = res.data.value || "(empty)";
      show(valueBox, true); showBtn.textContent = "[ HIDE ]"; open = true;
    });
    copyBtn.addEventListener("click", async () => {
      const res = await api("secret", {name: r.name});
      if (res.status === 401) { boot(); return; }
      flash(copyBtn, (await copyText(res.data.value || "")) ? "COPIED" : "COPY FAILED");
    });
    acts.appendChild(showBtn); acts.appendChild(copyBtn);
  }

  let genOut = null;
  if (GEN[r.name]) {
    const btn = el("button", "alt", r.state === "ok" ? "[ REGENERATE ]" : "[ GEN ]");
    genOut = el("div", "genout hidden");
    btn.addEventListener("click", () => {
      const v = GEN[r.name]();
      genOut.replaceChildren(); show(genOut, true);
      genOut.appendChild(el("code", "", v));
      const cp = el("button", "", "[ COPY ]");
      cp.addEventListener("click", async () => flash(cp, (await copyText(v)) ? "COPIED" : "COPY FAILED"));
      genOut.appendChild(cp);
      genOut.appendChild(el("div", "hint", r.name === "SESSION_ENCRYPTION_KEY" && r.state === "ok"
        ? "Replacing this makes the saved Instagram session unreadable; you will need to add it again."
        : "Paste into Vercel → Settings → Environment Variables (Production), then redeploy."));
    });
    acts.appendChild(btn);
  }
  if (acts.childNodes.length) row.appendChild(acts);
  if (genOut) row.appendChild(genOut);
  row.appendChild(valueBox);
  return row;
}

/* ---------- connect panel ---------- */
async function getReveal() { const r = await api("reveal", {}); return r.data; }
$("#revealBtn").addEventListener("click", async () => {
  if (revealed) { $("#mcpUrl").textContent = maskedUrl; revealed = false; $("#revealBtn").textContent = "[ REVEAL ]"; return; }
  const d = await getReveal(); $("#mcpUrl").textContent = d.mcp_url || ""; revealed = true; $("#revealBtn").textContent = "[ HIDE ]";
});
$("#copyUrlBtn").addEventListener("click", async (e) => {
  const d = await getReveal();
  flash(e.target, (await copyText(d.mcp_url || "")) ? "COPIED" : "COPY FAILED");
});
document.querySelectorAll("[data-copy]").forEach((btn) => btn.addEventListener("click", async () => {
  const d = await getReveal(); const key = d.key ? encodeURIComponent(d.key) : "";
  const map = {health: origin + "/healthz", upload: origin + "/upload" + (key ? "?auth=" + key : "")};
  flash(btn, (await copyText(map[btn.dataset.copy])) ? "COPIED" : "COPY FAILED");
}));

/* ---------- endpoint tests (run in the browser, against this site) ---------- */
function parseRpc(text) {
  const line = text.split("\n").find((l) => l.startsWith("data:"));
  try { return JSON.parse(line ? line.slice(5) : text); } catch (e) { return null; }
}
$("#testBtn").addEventListener("click", async () => {
  const box = $("#testLog"); box.replaceChildren();
  let key = $("#tk").value.trim();
  if (!key) {
    try { const d = await getReveal(); key = (d && d.key) || ""; } catch (e) { key = ""; }
  }
  if (!key) { logLine(box, "warn", "No MCP_AUTH_KEY is set on the server, so there is nothing to test with. Set it in Vercel first."); return; }
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
function report(r) {
  const box = $("#sessLog"); const d = r.data || {};
  if (r.status === 401) { boot(); return; }
  const cls = d.status === "success" ? "ok" : d.status === "error" ? "bad" : "warn";
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
