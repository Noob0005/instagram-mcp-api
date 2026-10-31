"""The dashboard page. Kept as a Python string so it is always bundled with the function.

Plain, friendly layout: Home, Connect, Instagram, Settings and Advanced. Technical details
(environment variables, endpoint checks) live under Advanced only.
"""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<title>Instagram MCP</title>
<style>
:root{
  --bg:#f5f6f8; --card:#ffffff; --ink:#1c2026; --muted:#6b7280; --line:#e3e6eb; --soft:#f1f3f6;
  --accent:#e1306c; --accent-ink:#ffffff;
  --ok:#15803d; --ok-bg:#e8f7ee; --warn:#b45309; --warn-bg:#fdf3e4; --bad:#b91c1c; --bad-bg:#fdecec;
  --radius:16px; --shadow:0 1px 2px rgba(16,24,40,.06),0 6px 20px rgba(16,24,40,.05);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0f1115; --card:#171a21; --ink:#eef0f3; --muted:#9aa3b2; --line:#2a303b; --soft:#1d222b;
    --accent:#ff5a8f; --accent-ink:#130a0f;
    --ok:#4ade80; --ok-bg:#133222; --warn:#fbbf24; --warn-bg:#33270f; --bad:#f87171; --bad-bg:#3a1717;
    --shadow:none;
  }
}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0; min-height:100vh; background:var(--bg); color:var(--ink);
  font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; -webkit-text-size-adjust:100%}
.hidden{display:none !important}
.wrap{max-width:1040px; margin:0 auto; padding:18px 16px 40px}

/* header */
.top{position:sticky; top:0; z-index:20; background:var(--card); border-bottom:1px solid var(--line)}
.top-in{max-width:1040px; margin:0 auto; padding:12px 16px; display:flex; align-items:center; gap:12px}
.logo{width:36px; height:36px; border-radius:11px; background:var(--accent); color:var(--accent-ink);
  display:grid; place-items:center; font-weight:800; flex:0 0 auto}
.brand{font-weight:700; font-size:1.05rem; line-height:1.2; white-space:nowrap}
.brand small{display:block; font-weight:400; color:var(--muted); font-size:.82rem}
.top-actions{margin-left:auto; display:flex; gap:8px; align-items:center}
.top-actions .btn{white-space:nowrap}

/* navigation: a row under the header on desktop, a bottom bar on phones */
.tabs{max-width:1040px; margin:0 auto; padding:6px 16px 0; display:flex; gap:4px; border-bottom:1px solid var(--line)}
.tab{display:flex; align-items:center; gap:8px; padding:10px 12px; color:var(--muted); text-decoration:none;
  border-radius:10px 10px 0 0; font-weight:600; font-size:.95rem; position:relative;
  transition:color .2s ease, background .2s ease}
.tab:hover{color:var(--ink); background:var(--soft)}
.tab.on{color:var(--accent)}
.tab.on::after{content:""; position:absolute; left:10px; right:10px; bottom:-1px; height:3px; border-radius:3px; background:var(--accent)}
.ico{width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; flex:0 0 auto}

/* views and pages: fade and rise in when shown */
.view,.page{animation:rise .32s ease both}
@keyframes rise{from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none}}

.card{background:var(--card); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow);
  padding:20px; margin:0 0 14px; transition:box-shadow .25s ease}
.card h2{font-size:1.08rem; margin:0 0 6px}
.card > p:first-of-type{margin-top:0}
.muted{color:var(--muted)}
.small{font-size:.88rem}
.center{max-width:440px; margin:7vh auto 0}
.head{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap}

.btn{appearance:none; border:1px solid var(--line); background:var(--soft); color:var(--ink); border-radius:12px;
  padding:10px 16px; min-height:44px; font:inherit; font-weight:600; cursor:pointer; text-decoration:none;
  display:inline-flex; align-items:center; justify-content:center; gap:8px; touch-action:manipulation;
  transition:transform .15s ease, background .2s ease, opacity .2s ease}
.btn:hover{transform:translateY(-1px)}
.btn:active{transform:scale(.98)}
.btn.primary{background:var(--accent); border-color:var(--accent); color:var(--accent-ink)}
.btn.ghost{background:transparent}
.btn.small{min-height:36px; padding:6px 12px; font-size:.9rem}
.btn.big{width:100%; min-height:58px; font-size:1.1rem; border-radius:14px}
.btn:disabled{opacity:.5; cursor:default; transform:none}
.btn:focus-visible,.tab:focus-visible,.tile:focus-visible,input:focus-visible,summary:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.row{display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; align-items:center}
.row > .grow{flex:1 1 220px}

label{display:block; font-weight:600; font-size:.92rem; margin:14px 0 6px}
input{width:100%; min-height:44px; padding:10px 12px; border-radius:12px; border:1px solid var(--line);
  background:var(--bg); color:var(--ink); font:inherit; font-size:16px; transition:border-color .2s ease}
input:focus{outline:none; border-color:var(--accent)}

.pill{display:inline-flex; align-items:center; gap:6px; padding:4px 10px; border-radius:999px; font-size:.85rem;
  font-weight:600; background:var(--soft); color:var(--muted); white-space:nowrap}
.pill.ok{background:var(--ok-bg); color:var(--ok)}
.pill.warn{background:var(--warn-bg); color:var(--warn)}
.pill.bad{background:var(--bad-bg); color:var(--bad)}

.banner{padding:12px 14px; border-radius:12px; margin:0 0 12px; font-size:.95rem}
.banner.good{background:var(--ok-bg); color:var(--ok)}
.banner.warn{background:var(--warn-bg); color:var(--warn)}
.banner.bad{background:var(--bad-bg); color:var(--bad)}

/* home */
.hero h1{font-size:1.45rem; margin:0 0 6px; line-height:1.25}
.tiles{display:grid; gap:12px; grid-template-columns:1fr; margin-top:14px}
@media (min-width:720px){ .tiles{grid-template-columns:repeat(3,1fr)} }
.tile{display:block; width:100%; text-align:left; background:var(--card); color:var(--ink); text-decoration:none;
  border:1px solid var(--line); border-radius:var(--radius); padding:16px; box-shadow:var(--shadow);
  transition:transform .2s ease, box-shadow .2s ease, border-color .2s ease}
.tile:hover{transform:translateY(-2px); border-color:var(--accent)}
.tile b{display:block; margin-bottom:2px}
.tile .muted{font-size:.9rem}
.tile .pill{margin-top:10px}
ol.steps{margin:8px 0 0; padding-left:22px}
ol.steps li{margin:6px 0}

/* connect, instagram */
.addr{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.9rem; background:var(--bg); border:1px dashed var(--line);
  border-radius:12px; padding:12px; margin-top:12px; min-height:48px; word-break:break-all}
.seg{display:inline-flex; gap:4px; padding:4px; background:var(--soft); border-radius:12px; margin-top:12px; flex-wrap:wrap}
.seg button{appearance:none; border:0; background:transparent; color:var(--muted); font:inherit; font-weight:600;
  padding:8px 14px; border-radius:9px; cursor:pointer; min-height:38px; transition:background .2s ease, color .2s ease}
.seg button.on{background:var(--card); color:var(--ink); box-shadow:var(--shadow)}
.log{background:var(--bg); border:1px solid var(--line); border-radius:12px; padding:10px 12px; margin-top:14px;
  min-height:56px; max-height:280px; overflow:auto; white-space:pre-wrap; word-break:break-word; font-size:.92rem}
.log .ok{color:var(--ok)} .log .bad{color:var(--bad)} .log .warn{color:var(--warn)}
.log .t{color:var(--muted); margin-right:6px}

/* settings, advanced */
dl.kv{display:grid; grid-template-columns:max-content minmax(0,1fr); gap:8px 16px; margin:12px 0 0}
dl.kv dt{color:var(--muted)}
dl.kv dd{margin:0; overflow-wrap:anywhere}
details.group{border-top:1px solid var(--line); margin-top:12px; padding-top:4px}
details.group > summary{cursor:pointer; list-style:none; font-weight:600; padding:10px 0; display:flex; justify-content:space-between; gap:8px}
details.group > summary::-webkit-details-marker{display:none}
details.group > summary::after{content:"+"; color:var(--muted); font-size:1.25rem; line-height:1; transition:transform .2s ease}
details.group[open] > summary::after{transform:rotate(45deg)}
.erow{padding:12px 0; border-top:1px solid var(--line)}
.erow:first-of-type{border-top:0}
.eh{display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap}
.ename{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.9rem; overflow-wrap:anywhere}
.edesc{color:var(--muted); font-size:.88rem; margin-top:4px}
.enote{color:var(--warn); font-size:.88rem; margin-top:4px}
.eacts{display:flex; flex-wrap:wrap; gap:8px; margin-top:10px}
.valbox{font-family:ui-monospace,Menlo,Consolas,monospace; background:var(--bg); border:1px solid var(--line); border-radius:10px;
  padding:10px; margin-top:10px; word-break:break-all; font-size:.88rem}
.genout{margin-top:10px; display:flex; flex-direction:column; gap:8px}
.genout code{font-family:ui-monospace,Menlo,Consolas,monospace; background:var(--bg); border:1px solid var(--line);
  border-radius:10px; padding:10px; word-break:break-all; font-size:.88rem}
.hint{color:var(--muted); font-size:.88rem; margin:4px 0 0}
.errline{color:var(--bad); min-height:1.4em; margin:10px 0 0; font-size:.92rem}
.okline{color:var(--ok); min-height:1.4em; margin:10px 0 0; font-size:.92rem}

.toast{position:fixed; left:50%; bottom:92px; transform:translate(-50%,16px); opacity:0; background:var(--ink);
  color:var(--bg); padding:11px 16px; border-radius:12px; max-width:92vw; z-index:40; pointer-events:none;
  transition:opacity .25s ease, transform .25s ease}
.toast.show{opacity:1; transform:translate(-50%,0)}
@media (min-width:720px){ .toast{bottom:24px} }

/* phones: navigation becomes a bottom bar, content gets room above it */
@media (max-width:719px){
  .tabs{position:fixed; left:0; right:0; bottom:0; z-index:25; margin:0; padding:6px 6px calc(6px + env(safe-area-inset-bottom));
    background:var(--card); border-top:1px solid var(--line); border-bottom:0; justify-content:space-around}
  .tab{flex-direction:column; gap:2px; padding:6px 4px; font-size:.74rem; flex:1 1 0; min-width:0; border-radius:10px}
  .tab.on::after{display:none}
  .tab.on{background:var(--soft)}
  .ico{width:22px; height:22px}
  .wrap{padding:14px 12px 110px}
  .card{padding:18px 16px}
  .top-in{padding:10px 12px}
  .brand small{display:none}
  .btn.big{min-height:60px}
  .hide-m{display:none}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none !important; transition:none !important}
}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="i-home" viewBox="0 0 24 24"><path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/></symbol>
  <symbol id="i-link" viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"/></symbol>
  <symbol id="i-cam" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r=".6"/></symbol>
  <symbol id="i-sliders" viewBox="0 0 24 24"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h10M18 18h2"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="16" cy="18" r="2"/></symbol>
  <symbol id="i-grid" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></symbol>
  <symbol id="i-upload" viewBox="0 0 24 24"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></symbol>
</svg>

<header class="top">
  <div class="top-in">
    <div class="logo" aria-hidden="true">IG</div>
    <div class="brand">Instagram MCP<small>Send photos and videos, then post them with your AI assistant</small></div>
    <div class="top-actions">
      <a class="btn primary small hidden" id="uploadTop" href="/upload"><svg class="ico" aria-hidden="true"><use href="#i-upload"/></svg><span>Upload</span></a>
      <button class="btn ghost small hidden hide-m" id="logoutBtn" type="button">Sign out</button>
    </div>
  </div>
</header>

<nav class="tabs hidden" id="tabs" aria-label="Sections">
  <a class="tab" href="#home" data-go="home"><svg class="ico" aria-hidden="true"><use href="#i-home"/></svg><span>Home</span></a>
  <a class="tab" href="#connect" data-go="connect"><svg class="ico" aria-hidden="true"><use href="#i-link"/></svg><span>Connect</span></a>
  <a class="tab" href="#instagram" data-go="instagram"><svg class="ico" aria-hidden="true"><use href="#i-cam"/></svg><span>Instagram</span></a>
  <a class="tab" href="#settings" data-go="settings"><svg class="ico" aria-hidden="true"><use href="#i-sliders"/></svg><span>Settings</span></a>
  <a class="tab" href="#advanced" data-go="advanced"><svg class="ico" aria-hidden="true"><use href="#i-grid"/></svg><span>Advanced</span></a>
</nav>

<main class="wrap">
  <!-- SIGN IN -->
  <section id="login" class="view card center hidden" aria-labelledby="loginTitle">
    <h2 id="loginTitle">Sign in</h2>
    <form id="loginForm" autocomplete="on">
      <div id="fUser"><label for="u">Username</label><input id="u" name="username" autocomplete="username"></div>
      <div id="fPass"><label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password"></div>
      <div id="fKey" class="hidden"><label for="k">Access key</label><input id="k" name="key" type="password" autocomplete="off"></div>
      <div class="row"><button class="btn primary big" type="submit" id="loginBtn">Sign in</button></div>
      <div class="errline" id="loginErr" role="alert"></div>
    </form>
    <p class="hint" id="loginHint"></p>
  </section>

  <!-- FIRST SET-UP (no access configured yet) -->
  <section id="setup" class="view hidden">
    <div class="card">
      <h2>Almost ready</h2>
      <div class="banner bad" id="setupNote">Add the settings below in Vercel, then redeploy.</div>
      <p class="muted small">Vercel: your project, then Settings, then Environment Variables. After saving, redeploy and reload this page.</p>
      <div id="setupBanner"></div>
      <div id="setupRows"></div>
    </div>
  </section>

  <!-- THE DASHBOARD -->
  <div id="app" class="hidden">

    <section class="page" data-page="home">
      <div class="card hero">
        <h1>Your Instagram helper</h1>
        <p class="muted">Add photos and videos here. Your AI assistant can then post them to Instagram for you.</p>
        <div class="row"><a class="btn primary big" id="uploadBtn" href="/upload"><svg class="ico" aria-hidden="true"><use href="#i-upload"/></svg><span>Upload photos and videos</span></a></div>
        <p class="hint">Unposted uploads are deleted automatically after a set time (48 hours by default).</p>
      </div>

      <div class="tiles">
        <a class="tile" href="#instagram">
          <b>Instagram</b>
          <span class="muted">Sign in so posts can go out.</span><br>
          <span class="pill" id="homeIg">Checking</span>
        </a>
        <a class="tile" href="#connect">
          <b>Your AI app</b>
          <span class="muted">Add the address once, then ask your assistant to post.</span><br>
          <span class="pill ok">Address ready</span>
        </a>
        <a class="tile" href="#advanced">
          <b>Setup</b>
          <span class="muted">Checks that everything the server needs is in place.</span><br>
          <span class="pill" id="homeSetup">Checking</span>
        </a>
      </div>

      <div class="card" style="margin-top:14px">
        <h2>How it works</h2>
        <ol class="steps">
          <li>Sign in to Instagram (the Instagram page).</li>
          <li>Add your address to your AI app (the Connect page).</li>
          <li>Upload photos and videos, then ask your assistant to post them.</li>
        </ol>
      </div>
    </section>

    <section class="page" data-page="connect">
      <div class="card">
        <h2>1. Add this address to your AI app</h2>
        <p class="muted small">Paste it into your AI app as a custom connector. The address includes your access key, so keep it private.</p>
        <div class="addr" id="mcpUrl">Loading...</div>
        <div class="row">
          <button class="btn" id="revealBtn" type="button">Show address</button>
          <button class="btn primary" id="copyUrlBtn" type="button">Copy address</button>
        </div>
      </div>

      <div class="card">
        <h2>2. Keep Instagram signed in (optional)</h2>
        <p class="muted small">A browser extension can send your Instagram sign-in here automatically, so you rarely need to do it by hand. Install it on the computer where you are signed in to Instagram.</p>
        <div class="row">
          <a class="btn" href="/api/main?admin=extension" download>Download the extension</a>
        </div>
        <p class="hint">It already contains this server's address. Do not share the file.</p>
      </div>
    </section>

    <section class="page" data-page="instagram">
      <div class="card">
        <div class="head">
          <h2>Instagram</h2>
          <span class="pill" id="igPill">Checking</span>
        </div>
        <p class="muted small" id="igText">Checking your connection...</p>
      </div>

      <div class="card">
        <h2>Connect your account</h2>
        <div class="seg" role="tablist">
          <button id="tabCookie" class="on" type="button" role="tab" aria-selected="true">Simple</button>
          <button id="tabPass" type="button" role="tab" aria-selected="false">Username and password</button>
        </div>

        <div id="formCookie">
          <label for="sid">Session ID</label>
          <input id="sid" type="password" autocomplete="off">
          <label for="sun">Instagram username (optional)</label>
          <input id="sun" autocomplete="off">
          <p class="hint">Easiest: install the browser extension from the Connect page, and it does this for you. Or log in at instagram.com, then copy the value of the <b>sessionid</b> cookie from your browser's developer tools.</p>
          <div class="row"><button class="btn primary" id="saveCookie" type="button">Save connection</button></div>
        </div>

        <div id="formPass" class="hidden">
          <label for="iun">Instagram username</label>
          <input id="iun" autocomplete="off">
          <label for="ipw">Instagram password</label>
          <input id="ipw" type="password" autocomplete="off">
          <p class="hint">Only use this if the other way does not work. Logins from Vercel's servers often trigger a security check that cannot be completed here.</p>
          <div class="row"><button class="btn primary" id="savePass" type="button">Log in</button></div>
        </div>

        <div id="codeBox" class="hidden">
          <label for="code" id="codeLabel">Verification code</label>
          <div class="row">
            <input id="code" autocomplete="one-time-code" class="grow">
            <button class="btn primary" id="sendCode" type="button">Send code</button>
          </div>
        </div>

        <div class="row"><button class="btn" id="checkSession" type="button">Check connection</button></div>
        <div class="log" id="sessLog" aria-live="polite"></div>
      </div>
    </section>

    <section class="page" data-page="settings">
      <div class="card">
        <h2>Sign out</h2>
        <p class="muted small">Sign out of this dashboard on this device.</p>
        <div class="row"><button class="btn" id="logoutBtn2" type="button">Sign out</button></div>
      </div>
    </section>

    <section class="page" data-page="advanced">
      <div class="card">
        <h2>Setup checklist</h2>
        <p class="muted small">Values stay hidden. You can show or copy the two secrets the dashboard needs. After changing a setting in Vercel, redeploy.</p>
        <div id="envBanner"></div>
        <div id="envRows"></div>
      </div>

      <div class="card">
        <h2>Server details</h2>
        <dl class="kv">
          <dt>Sign-in</dt><dd id="kvMode">&mdash;</dd>
          <dt>Storage</dt><dd id="kvStorage">&mdash;</dd>
          <dt>Server</dt><dd id="kvOrigin">&mdash;</dd>
        </dl>
        <div class="row">
          <button class="btn small" id="copyHealthBtn" type="button">Copy health link</button>
          <button class="btn small" id="copyUploadBtn" type="button">Copy upload link</button>
        </div>
      </div>

      <div class="card">
        <h2>Check the server</h2>
        <p class="muted small">Runs a few requests against this server to confirm it answers. Leave the box empty to use this session's key.</p>
        <label for="tk">Optional: a different access key</label>
        <div class="row">
          <input id="tk" type="password" autocomplete="off" class="grow">
          <button class="btn primary" id="testBtn" type="button">Run checks</button>
        </div>
        <div class="log" id="testLog" aria-live="polite"></div>
      </div>
    </section>
  </div>
</main>

<script>
"use strict";
const $ = (s) => document.querySelector(s);
const show = (node, on) => node.classList.toggle("hidden", !on);
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
  setTimeout(() => { btn.textContent = old; }, 1400);
}
let toastTimer = 0;
function toast(message) {
  let t = $("#toast");
  if (!t) { t = el("div", "toast"); t.id = "toast"; document.body.appendChild(t); }
  t.textContent = message; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2800);
}
function logLine(box, cls, msg) {
  const d = el("div");
  d.appendChild(el("span", "t", new Date().toTimeString().slice(0, 8)));
  d.appendChild(el("span", cls, msg));
  box.appendChild(d); box.scrollTop = box.scrollHeight;
}

/* key generators (run in your browser; nothing is sent anywhere) */
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
// Secrets a logged-in admin may reveal (the server enforces the same list).
const SECRETS = {MCP_AUTH_KEY: true, SESSION_ENCRYPTION_KEY: true};

/* state (kept in memory only) */
let origin = location.origin;
let revealed = false;
let maskedUrl = "";
let fullUrl = "";
let accessKey = "";
let pendingCode = "";

/* navigation between sections */
const PAGES = ["home", "connect", "instagram", "settings", "advanced"];
function route() {
  const name = (location.hash || "#home").slice(1);
  const page = PAGES.includes(name) ? name : "home";
  document.querySelectorAll(".page").forEach((s) => show(s, s.dataset.page === page));
  document.querySelectorAll(".tab").forEach((t) => {
    const on = t.dataset.go === page;
    t.classList.toggle("on", on);
    if (on) t.setAttribute("aria-current", "page"); else t.removeAttribute("aria-current");
  });
}
window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });

function uploadHref() { return "/upload" + (accessKey ? "?auth=" + encodeURIComponent(accessKey) : ""); }

function setView(name) {
  show($("#login"), name === "login");
  show($("#setup"), name === "setup");
  show($("#app"), name === "app");
  show($("#tabs"), name === "app");
  show($("#logoutBtn"), name === "app");
  show($("#uploadTop"), name === "app");
}

async function boot() {
  setView("none");
  let info = null;
  try { info = (await api("info")).data; } catch (e) { info = null; }
  if (!info) {
    setView("setup");
    $("#setupNote").textContent = "Cannot reach the server. Reload the page to try again.";
    return;
  }
  if (info.mode === "none") {
    setView("setup");
    const s = (await api("status")).data;
    if (s && s.env) renderEnv(s.env, $("#setupBanner"), $("#setupRows"), false);
    return;
  }
  if (!info.authenticated) { showLogin(info.mode); return; }
  await loadApp();
}

function showLogin(mode) {
  setView("login");
  const pw = mode === "password";
  show($("#fUser"), pw); show($("#fPass"), pw); show($("#fKey"), !pw);
  $("#loginHint").textContent = pw
    ? "Use the username and password set in Vercel (ADMIN_USERNAME and ADMIN_PASSWORD)."
    : "Paste the access key from your Vercel settings (MCP_AUTH_KEY).";
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
  else $("#loginErr").textContent = r.data.error || "Sign-in failed. Please try again.";
});

async function loadApp() {
  const r = await api("status");
  if (r.status === 401) { boot(); return; }
  const s = r.data;
  origin = s.origin || location.origin;
  maskedUrl = s.mcp_url_masked || "";
  fullUrl = "";
  revealed = false;
  $("#revealBtn").textContent = "Show address";
  $("#mcpUrl").textContent = maskedUrl || "Set up the access key first (see Advanced).";
  setView("app");

  // The key is needed only for the upload link. It is read once per visit, held in memory, never stored.
  const rv = await api("reveal", {});
  accessKey = (rv.data && rv.data.key) || "";
  $("#uploadBtn").href = uploadHref();
  $("#uploadTop").href = uploadHref();

  const env = s.env || {};
  renderEnv(env, $("#envBanner"), $("#envRows"), true);
  const bad = env.required_bad || 0;
  const setup = $("#homeSetup");
  setup.className = "pill " + (bad ? "warn" : "ok");
  setup.textContent = bad ? bad + " to fix" : "All set";

  const st = s.storage || {};
  const where = st.backend === "blob" ? "Vercel Blob" : "temporary disk (lost on restart)";
  const summary = where + (st.encryption ? ", encrypted" : ", NOT encrypted") +
    (st.exists === false ? ", no session saved" : st.exists ? ", session saved" : "") +
    (st.error ? " (error: " + st.error + ")" : "");
  $("#kvStorage").textContent = summary;
  $("#kvMode").textContent = s.mode === "password" ? "Username and password" : "Access key";
  $("#kvOrigin").textContent = origin;
  renderSessionStatus(st);

  route();
}

function renderSessionStatus(st) {
  const pill = $("#igPill"), home = $("#homeIg"), text = $("#igText");
  if (st.exists) {
    pill.className = "pill ok"; pill.textContent = "Connected";
    home.className = "pill ok"; home.textContent = "Connected";
    text.textContent = "Your Instagram sign-in is saved. Posts can go out.";
  } else {
    pill.className = "pill warn"; pill.textContent = "Not connected";
    home.className = "pill warn"; home.textContent = "Not connected";
    text.textContent = "No Instagram sign-in is saved yet. Add one below so posts can go out.";
  }
}

/* setup checklist (Advanced, and the first-run screen) */
const TAGS = {ok: ["Set", "ok"], missing: ["Missing", "bad"], invalid: ["Needs fixing", "bad"],
  weak: ["Too weak", "warn"], danger: ["Remove it", "bad"], unset: ["Not set", ""]};

function renderEnv(env, bannerEl, rowsEl, canReveal) {
  const wasOpen = {};
  rowsEl.querySelectorAll("details.group").forEach((d) => { wasOpen[d.dataset.level] = d.open; });
  bannerEl.replaceChildren(); rowsEl.replaceChildren();

  const bad = env.required_bad;
  const b = el("div", "banner " + (bad ? "bad" : env.warnings ? "warn" : "good"));
  b.textContent = bad
    ? bad + " of " + env.required_total + " required settings still need attention."
    : env.warnings ? "Everything required is set. " + env.warnings + " suggestion(s) to review."
    : "Everything required is set.";
  bannerEl.appendChild(b);

  const groups = [
    ["required", "Required", true],
    ["recommended", "Recommended", true],
    ["optional", "Optional", false],
    ["danger", "Should not be set", false],
  ];
  for (const [level, title, openByDefault] of groups) {
    const rows = env.rows.filter((r) => r.level === level);
    if (!rows.length) continue;
    const setCount = rows.filter((r) => r.set).length;
    const summary = level === "danger"
      ? (setCount ? setCount + " set, remove them" : "none set (correct)")
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
  const row = el("div", "erow");
  const head = el("div", "eh");
  head.appendChild(el("span", "ename", r.name));
  const [label, tone] = TAGS[r.state] || [r.state, ""];
  head.appendChild(el("span", "pill " + tone, label));
  row.appendChild(head);
  row.appendChild(el("div", "edesc", r.desc));
  if (r.note) row.appendChild(el("div", "enote", r.note));

  const acts = el("div", "eacts");
  const valueBox = el("div", "valbox hidden");
  if (canReveal && SECRETS[r.name] && r.set) {
    const showBtn = el("button", "btn small", "Show");
    const copyBtn = el("button", "btn small", "Copy");
    let open = false;
    showBtn.type = "button"; copyBtn.type = "button";
    showBtn.addEventListener("click", async () => {
      if (open) {
        valueBox.textContent = ""; show(valueBox, false);
        showBtn.textContent = "Show"; open = false; return;
      }
      const res = await api("secret", {name: r.name});
      if (res.status === 401) { boot(); return; }
      valueBox.textContent = res.data.value || "(empty)";
      show(valueBox, true); showBtn.textContent = "Hide"; open = true;
    });
    copyBtn.addEventListener("click", async () => {
      const res = await api("secret", {name: r.name});
      if (res.status === 401) { boot(); return; }
      flash(copyBtn, (await copyText(res.data.value || "")) ? "Copied" : "Copy failed");
    });
    acts.appendChild(showBtn); acts.appendChild(copyBtn);
  }

  let genOut = null;
  if (GEN[r.name]) {
    const btn = el("button", "btn small", r.state === "ok" ? "Make a new one" : "Make one");
    btn.type = "button";
    genOut = el("div", "genout hidden");
    btn.addEventListener("click", () => {
      const v = GEN[r.name]();
      genOut.replaceChildren(); show(genOut, true);
      genOut.appendChild(el("code", "", v));
      const cp = el("button", "btn small", "Copy"); cp.type = "button";
      cp.addEventListener("click", async () => flash(cp, (await copyText(v)) ? "Copied" : "Copy failed"));
      genOut.appendChild(cp);
      genOut.appendChild(el("div", "hint", r.name === "SESSION_ENCRYPTION_KEY" && r.state === "ok"
        ? "Replacing this makes the saved Instagram session unreadable. You will need to connect Instagram again."
        : "Paste it into Vercel (Settings, Environment Variables, Production), then redeploy."));
    });
    acts.appendChild(btn);
  }
  if (acts.childNodes.length) row.appendChild(acts);
  if (genOut) row.appendChild(genOut);
  row.appendChild(valueBox);
  return row;
}

/* connect */
async function getReveal() { const r = await api("reveal", {}); return r.data; }
$("#revealBtn").addEventListener("click", async () => {
  if (revealed) {
    $("#mcpUrl").textContent = maskedUrl; revealed = false; $("#revealBtn").textContent = "Show address"; return;
  }
  const d = await getReveal();
  $("#mcpUrl").textContent = d.mcp_url || ""; fullUrl = d.mcp_url || "";
  revealed = true; $("#revealBtn").textContent = "Hide address";
});
$("#copyUrlBtn").addEventListener("click", async (e) => {
  const d = await getReveal();
  flash(e.target, (await copyText(d.mcp_url || "")) ? "Copied" : "Copy failed");
});
$("#copyHealthBtn").addEventListener("click", async (e) => {
  flash(e.target, (await copyText(origin + "/healthz")) ? "Copied" : "Copy failed");
});
$("#copyUploadBtn").addEventListener("click", async (e) => {
  flash(e.target, (await copyText(origin + uploadHref())) ? "Copied" : "Copy failed");
});

/* server checks (run in the browser, against this site) */
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
  if (!key) { logLine(box, "warn", "No access key is set on the server yet, so there is nothing to check. Set it in Vercel first."); return; }
  const hdr = (k) => ({"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
    "Authorization": "Bearer " + k});
  const rpc = (method, params, id) => JSON.stringify({jsonrpc: "2.0", id, method, params});
  const init = {protocolVersion: "2025-03-26", capabilities: {}, clientInfo: {name: "dashboard-test", version: "1"}};
  const tests = [
    ["Server is up (/healthz)", async () => { const r = await fetch("/healthz"); return [r.status === 200, "HTTP " + r.status]; }],
    ["Connector starts (/mcp)", async () => {
      const r = await fetch("/mcp", {method: "POST", headers: hdr(key), body: rpc("initialize", init, 1)});
      const j = parseRpc(await r.text()); const n = j && j.result && j.result.serverInfo && j.result.serverInfo.name;
      return [r.ok && !!n, "HTTP " + r.status + (n ? ", " + n : "")]; }],
    ["Tools are listed", async () => {
      const r = await fetch("/mcp", {method: "POST", headers: hdr(key), body: rpc("tools/list", {}, 2)});
      const j = parseRpc(await r.text()); const c = j && j.result && j.result.tools && j.result.tools.length;
      return [r.ok && c > 0, "HTTP " + r.status + (c ? ", " + c + " tools" : "")]; }],
    ["Wrong key is refused", async () => {
      const r = await fetch("/mcp", {method: "POST", headers: hdr(key + "x"), body: rpc("initialize", init, 3)});
      return [r.status === 401, "HTTP " + r.status + (r.status === 401 ? " (correct)" : " (should be 401)")]; }],
    ["Upload area accepts the key", async () => {
      const r = await fetch("/api/upload", {method: "POST", headers: {"Content-Type": "application/json", "X-Auth-Key": key},
        body: JSON.stringify({action: "list"})});
      return [r.status === 200, "HTTP " + r.status + (r.status === 401 ? " (key refused)" : "")]; }],
  ];
  let pass = 0;
  for (const [name, fn] of tests) {
    try {
      const [ok, info] = await fn();
      if (ok) pass++;
      logLine(box, ok ? "ok" : "bad", (ok ? "Pass: " : "Fail: ") + name + " (" + info + ")");
    } catch (e) { logLine(box, "bad", "Fail: " + name + " (" + e.message + ")"); }
  }
  logLine(box, pass === tests.length ? "ok" : "warn", pass + " of " + tests.length + " checks passed.");
});

/* instagram */
function setTab(cookie) {
  show($("#formCookie"), cookie); show($("#formPass"), !cookie);
  $("#tabCookie").className = cookie ? "on" : ""; $("#tabPass").className = cookie ? "" : "on";
  $("#tabCookie").setAttribute("aria-selected", String(cookie));
  $("#tabPass").setAttribute("aria-selected", String(!cookie));
}
$("#tabCookie").addEventListener("click", () => setTab(true));
$("#tabPass").addEventListener("click", () => setTab(false));
function report(r) {
  const box = $("#sessLog"); const d = r.data || {};
  if (r.status === 401) { boot(); return; }
  const cls = d.status === "success" ? "ok" : d.status === "error" ? "bad" : "warn";
  logLine(box, cls, (d.message || JSON.stringify(d)));
  pendingCode = d.status === "needs_2fa" ? "2fa" : d.status === "needs_challenge" ? "challenge" : "";
  show($("#codeBox"), !!pendingCode);
  $("#codeLabel").textContent = pendingCode === "2fa" ? "Code from your authenticator app" : "Code sent to your email or phone";
  if (d.status === "success") {
    $("#sid").value = ""; $("#ipw").value = "";
    toast("Instagram is connected.");
    loadApp();
  }
}
async function sessionCall(body, btn) {
  btn.disabled = true; logLine($("#sessLog"), "warn", "Working...");
  try { report(await api("session", body)); } finally { btn.disabled = false; }
}
$("#saveCookie").addEventListener("click", (e) => sessionCall({action: "cookie", sessionid: $("#sid").value, username: $("#sun").value}, e.target));
$("#savePass").addEventListener("click", (e) => sessionCall({action: "password", username: $("#iun").value, password: $("#ipw").value}, e.target));
$("#sendCode").addEventListener("click", (e) => sessionCall({action: pendingCode || "2fa", code: $("#code").value}, e.target));
$("#checkSession").addEventListener("click", (e) => sessionCall({action: "status"}, e.target));

/* sign out */
async function signOut() { await api("logout", {}); accessKey = ""; location.hash = ""; boot(); }
$("#logoutBtn").addEventListener("click", signOut);
$("#logoutBtn2").addEventListener("click", signOut);

route();
boot();
</script>
</body>
</html>
"""
