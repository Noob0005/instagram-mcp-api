"""The browser upload page, embedded as a string so it ships inside the function.

Vercel only bundles .py files, so a file read from public/ at runtime is missing in production.
The page talks to /api/upload (JSON actions and ?thumb= / ?file= reads) and to /api/blob-token
(short-lived upload tokens), both behind the same key as the page itself.
"""

UPLOAD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<title>Upload</title>
<style>
:root{
  --bg:#f6f7fb; --surface:#ffffff; --raised:#ffffff; --ink:#111827; --ink2:#374151; --muted:#6b7280;
  --line:#e5e7eb; --soft:#f3f4f6; --accent:#4f46e5; --accent-ink:#ffffff; --accent-soft:#eef2ff;
  --ok:#15803d; --ok-soft:#dcfce7; --bad:#b91c1c; --bad-soft:#fee2e2; --warn:#b45309; --warn-soft:#fef3c7;
  --r-lg:18px; --r:14px; --r-sm:10px;
  --shadow:0 1px 2px rgba(17,24,39,.05),0 8px 24px rgba(17,24,39,.06);
  --scrim:rgba(17,24,39,.45);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0b0d12; --surface:#141820; --raised:#1a1f2a; --ink:#f3f4f6; --ink2:#d1d5db; --muted:#9ca3af;
    --line:#252b38; --soft:#1c2230; --accent:#818cf8; --accent-ink:#0b0d12; --accent-soft:#1e2247;
    --ok:#4ade80; --ok-soft:#133222; --bad:#f87171; --bad-soft:#3a1717; --warn:#fbbf24; --warn-soft:#33270f;
    --shadow:none; --scrim:rgba(0,0,0,.6);
  }
}
*{box-sizing:border-box}
html,body{margin:0; background:var(--bg); color:var(--ink)}
body{font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; -webkit-font-smoothing:antialiased; min-height:100vh}
button,input,select{font:inherit; color:inherit}
.hidden{display:none !important}
.sr{position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap}
svg.i{width:18px; height:18px; fill:none; stroke:currentColor; stroke-width:1.9; stroke-linecap:round; stroke-linejoin:round; flex:0 0 auto}

/* app bar */
.bar{position:sticky; top:0; z-index:20; background:color-mix(in srgb,var(--surface) 88%,transparent);
  backdrop-filter:saturate(1.4) blur(10px); -webkit-backdrop-filter:saturate(1.4) blur(10px); border-bottom:1px solid var(--line)}
.bar-in{max-width:1120px; margin:0 auto; padding:12px 20px; display:flex; align-items:center; gap:12px}
.mark{width:34px; height:34px; border-radius:10px; background:var(--accent); color:var(--accent-ink); display:grid; place-items:center; font-weight:800; font-size:14px}
.title{font-weight:700; font-size:1.02rem; letter-spacing:-.01em}
.title small{display:block; font-weight:500; color:var(--muted); font-size:.8rem; letter-spacing:0}
.bar-end{margin-left:auto; display:flex; align-items:center; gap:8px}
.chip-keep{display:inline-flex; align-items:center; gap:6px; padding:6px 10px; border-radius:999px; background:var(--soft); color:var(--ink2); font-size:.82rem; font-weight:600; white-space:nowrap}
.icon-btn{width:40px; height:40px; border-radius:12px; border:1px solid var(--line); background:var(--surface); display:grid; place-items:center; cursor:pointer; color:var(--ink2); transition:background .2s,transform .15s}
.icon-btn:hover{background:var(--soft)}
.icon-btn:active{transform:scale(.96)}

/* segmented tabs */
.tabs{max-width:1120px; margin:0 auto; padding:14px 20px 0}
.seg{display:inline-grid; grid-auto-flow:column; gap:4px; padding:4px; background:var(--soft); border-radius:12px}
.seg button{border:0; background:transparent; padding:9px 16px; border-radius:9px; font-weight:600; color:var(--muted); cursor:pointer; display:flex; align-items:center; gap:8px; min-height:40px; transition:background .2s,color .2s}
.seg button[aria-selected="true"]{background:var(--surface); color:var(--ink); box-shadow:var(--shadow)}
.count{background:var(--accent-soft); color:var(--accent); border-radius:999px; padding:1px 8px; font-size:.78rem; font-weight:700}

main{max-width:1120px; margin:0 auto; padding:18px 20px 140px}
.panel{animation:rise .3s ease both}
@keyframes rise{from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none}}
.card{background:var(--surface); border:1px solid var(--line); border-radius:var(--r-lg); box-shadow:var(--shadow)}
.pad{padding:20px}
h2{font-size:1.02rem; margin:0; letter-spacing:-.01em}
.sub{color:var(--muted); font-size:.9rem; margin:4px 0 0}

/* drop zone */
.drop{display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; text-align:center; cursor:pointer;
  border:1.5px dashed color-mix(in srgb,var(--accent) 40%,var(--line)); border-radius:var(--r-lg); padding:38px 18px; background:var(--accent-soft);
  transition:border-color .2s,background .2s,transform .2s}
.drop:hover,.drop.over{border-color:var(--accent); transform:translateY(-1px)}
.drop .big{width:52px; height:52px; border-radius:16px; background:var(--surface); color:var(--accent); display:grid; place-items:center; box-shadow:var(--shadow); margin-bottom:6px}
.drop strong{font-size:1.02rem}
.drop span{color:var(--muted); font-size:.9rem}
:focus-visible{outline:2px solid var(--accent); outline-offset:2px}

/* queue */
.queue{display:grid; gap:10px; margin-top:16px}
.qitem{display:grid; grid-template-columns:56px minmax(0,1fr) auto; gap:14px; align-items:center; padding:12px; border:1px solid var(--line); border-radius:var(--r); background:var(--raised); animation:rise .25s ease both; transition:opacity .25s,transform .25s}
.qitem.removing{opacity:0; transform:translateX(10px)}
.thumb{width:56px; height:56px; border-radius:var(--r-sm); object-fit:cover; background:var(--soft); display:grid; place-items:center; color:var(--muted)}
.qmain{min-width:0}
.qrow{display:flex; gap:8px; align-items:baseline; justify-content:space-between}
.name{font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0}
.meta{color:var(--muted); font-size:.82rem; white-space:nowrap}
.bar-track{height:6px; background:var(--soft); border-radius:99px; overflow:hidden; margin:8px 0 6px}
.bar-track > i{display:block; height:100%; width:0; background:var(--accent); border-radius:99px; transition:width .3s ease}
.qitem.done .bar-track > i{background:var(--ok); width:100% !important}
.qitem.failed .bar-track > i{background:var(--bad)}
.status{font-size:.82rem; color:var(--muted)}
.qitem.done .status{color:var(--ok)}
.qitem.failed .status{color:var(--bad)}
.qitem input{margin-top:6px; min-height:36px; padding:6px 10px; font-size:.88rem}
.link{border:0; background:none; color:var(--muted); cursor:pointer; padding:6px; border-radius:8px; font-size:.85rem}
.link:hover{color:var(--ink); background:var(--soft)}

/* options */
details.opts{margin-top:16px; border-top:1px solid var(--line); padding-top:14px}
details.opts summary{cursor:pointer; color:var(--ink2); font-weight:600; list-style:none; display:flex; justify-content:space-between; align-items:center}
details.opts summary::-webkit-details-marker{display:none}
details.opts summary::after{content:"+"; color:var(--muted); font-size:1.2rem}
details.opts[open] summary::after{content:"–"}
.grid2{display:grid; gap:12px; grid-template-columns:1fr; margin-top:12px}
@media (min-width:640px){.grid2{grid-template-columns:200px 1fr}}
label.f{display:block; font-size:.85rem; font-weight:600; color:var(--ink2); margin:0 0 6px}
input,select{width:100%; min-height:44px; padding:10px 12px; border-radius:var(--r-sm); border:1px solid var(--line); background:var(--bg); outline:none; font-size:16px; transition:border-color .2s,box-shadow .2s}
input:focus,select:focus{border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft)}

/* buttons */
.btn{appearance:none; border:1px solid var(--line); background:var(--surface); color:var(--ink); border-radius:var(--r-sm); padding:10px 16px; min-height:42px; font-weight:600; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; gap:8px; transition:background .2s,transform .15s,opacity .2s; white-space:nowrap}
.btn:hover{background:var(--soft)}
.btn:active{transform:scale(.98)}
.btn:disabled{opacity:.45; cursor:default; transform:none}
.btn.primary{background:var(--accent); border-color:var(--accent); color:var(--accent-ink)}
.btn.primary:hover{filter:brightness(1.06); background:var(--accent)}
.btn.danger{color:var(--bad)}
.btn.danger.solid{background:var(--bad); border-color:var(--bad); color:#fff}

/* dock: the sticky action bar that appears when files are queued */
.dock{position:fixed; left:0; right:0; bottom:0; z-index:30; padding:12px 20px calc(12px + env(safe-area-inset-bottom));
  background:color-mix(in srgb,var(--surface) 92%,transparent); backdrop-filter:blur(10px); border-top:1px solid var(--line);
  transform:translateY(100%); transition:transform .3s ease}
.dock.show{transform:none}
.dock-in{max-width:1120px; margin:0 auto; display:flex; align-items:center; gap:12px}
.dock-text{min-width:0}
.dock-text b{display:block}
.dock-text span{color:var(--muted); font-size:.85rem}
.dock .btn.primary{margin-left:auto; min-width:140px}

/* library */
.toolbar{display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; margin-bottom:14px}
.search{position:relative; flex:1 1 240px; max-width:360px}
.search svg{position:absolute; left:12px; top:50%; transform:translateY(-50%); color:var(--muted)}
.search input{padding-left:38px; border-radius:999px}
.chips{display:flex; gap:6px; flex-wrap:wrap}
.chip{border:1px solid var(--line); background:var(--surface); border-radius:999px; padding:7px 14px; font-weight:600; font-size:.86rem; color:var(--ink2); cursor:pointer; min-height:36px}
.chip[aria-pressed="true"]{background:var(--ink); color:var(--surface); border-color:var(--ink)}
.grid{display:grid; gap:14px; grid-template-columns:repeat(2,minmax(0,1fr))}
@media (min-width:720px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (min-width:1000px){.grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
.tile{background:var(--surface); border:1px solid var(--line); border-radius:var(--r); overflow:hidden; display:flex; flex-direction:column; box-shadow:var(--shadow); animation:rise .3s ease both; transition:transform .2s,box-shadow .2s}
.tile:hover{transform:translateY(-2px)}
.pic{position:relative; aspect-ratio:4/5; background:var(--soft); display:grid; place-items:center; color:var(--muted); overflow:hidden}
.pic img{width:100%; height:100%; object-fit:cover; display:block}
.kind{position:absolute; top:8px; left:8px; background:rgba(17,24,39,.72); color:#fff; border-radius:999px; padding:2px 9px; font-size:.72rem; font-weight:700; letter-spacing:.02em}
.tb{padding:10px 12px 12px; min-width:0}
.tn{font-weight:650; overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.tm{color:var(--muted); font-size:.8rem; margin-top:2px}
.ta{display:flex; gap:4px; border-top:1px solid var(--line); padding:6px}
.ta button{flex:1; border:0; background:none; padding:8px 0; border-radius:8px; color:var(--ink2); cursor:pointer; display:grid; place-items:center; min-height:38px}
.ta button:hover{background:var(--soft); color:var(--ink)}
.ta button.del:hover{color:var(--bad)}
.libbar{display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:6px 12px; margin:2px 2px 12px; font-size:.9rem}
.storage{color:var(--muted); flex:1 1 200px}
.storage.warn{color:var(--bad); font-weight:650}
.selbar{position:sticky; top:8px; z-index:6; display:flex; align-items:center; gap:10px; flex-wrap:wrap; background:var(--raised); border:1px solid var(--line); border-radius:var(--r); padding:10px 12px; margin-bottom:14px; box-shadow:var(--shadow)}
.selbar .grow{flex:1}
.pick{position:absolute; top:8px; right:8px; z-index:2; width:32px; height:32px; border-radius:9px; background:rgba(255,255,255,.94); display:grid; place-items:center; box-shadow:0 1px 3px rgba(0,0,0,.25); cursor:pointer}
.pick input{width:18px; height:18px; margin:0; cursor:pointer}
.tile.picked{outline:2px solid #2563eb; outline-offset:-2px}
.dellist{margin:10px 0; padding-left:18px; max-height:40vh; overflow:auto; font-size:.9rem; color:var(--ink2)}
.skel{background:linear-gradient(90deg,var(--soft),var(--line),var(--soft)); background-size:200% 100%; animation:shim 1.2s linear infinite; border-radius:var(--r)}
@keyframes shim{to{background-position:-200% 0}}
.empty{text-align:center; padding:48px 16px; color:var(--muted)}
.empty .art{width:64px; height:64px; margin:0 auto 12px; border-radius:20px; background:var(--soft); display:grid; place-items:center; color:var(--accent)}
.empty b{color:var(--ink); display:block; margin-bottom:4px; font-size:1.02rem}

/* sheets (bottom on phones, centred on desktop) */
.scrim{position:fixed; inset:0; background:var(--scrim); z-index:40; opacity:0; visibility:hidden; transition:opacity .25s,visibility .25s; display:flex; align-items:flex-end; justify-content:center}
.scrim.open{opacity:1; visibility:visible}
.sheet{width:min(560px,100%); max-height:88vh; overflow:auto; background:var(--raised); border-radius:var(--r-lg) var(--r-lg) 0 0; padding:18px 18px calc(18px + env(safe-area-inset-bottom));
  transform:translateY(24px); transition:transform .28s cubic-bezier(.2,.8,.2,1); box-shadow:0 -10px 40px rgba(0,0,0,.2)}
.scrim.open .sheet{transform:none}
@media (min-width:640px){ .scrim{align-items:center} .sheet{border-radius:var(--r-lg); padding:22px} }
.sheet h3{margin:0 0 6px; font-size:1.05rem}
.sheet img,.sheet video{width:100%; border-radius:var(--r); display:block; background:var(--soft); max-height:70vh; object-fit:contain}
.sheet .row{display:flex; gap:8px; justify-content:flex-end; margin-top:16px; flex-wrap:wrap}
.presets{display:flex; flex-wrap:wrap; gap:8px; margin:12px 0}

/* toast */
.toast{position:fixed; left:50%; bottom:92px; transform:translate(-50%,14px); opacity:0; pointer-events:none; background:var(--ink); color:var(--surface); padding:11px 16px; border-radius:12px; max-width:92vw; z-index:60; transition:opacity .25s,transform .25s; box-shadow:var(--shadow)}
.toast.show{opacity:1; transform:translate(-50%,0)}
.toast.ok{background:var(--ok); color:#fff}
.toast.bad{background:var(--bad); color:#fff}
.notice{border-radius:var(--r-sm); padding:10px 12px; font-size:.9rem; margin-top:12px}
.notice.bad{background:var(--bad-soft); color:var(--bad)}
.notice.ok{background:var(--ok-soft); color:var(--ok)}
.notice.warn{background:var(--warn-soft); color:var(--warn)}

@media (max-width:640px){
  .bar-in{padding:10px 14px}
  .tabs,main{padding-left:14px; padding-right:14px}
  .chip-keep span.long{display:none}
  .title small{display:none}
  .dock{padding-left:14px; padding-right:14px}
}
.logbox{margin-top:16px; padding:0 16px 14px}
.logbox summary{cursor:pointer; list-style:none; display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px 12px; align-items:center; padding:14px 0; font-weight:700}
.logbox summary::-webkit-details-marker{display:none}
.logbox .sub-s{color:var(--muted); font-weight:500; font-size:.82rem}
.log-tools{display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px}
.log{margin:0; max-height:280px; overflow:auto; background:var(--soft); border:1px solid var(--line); border-radius:var(--r-sm);
  padding:10px 12px; min-height:72px; font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; white-space:pre-wrap; word-break:break-word; color:var(--ink2)}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none !important; transition:none !important}}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="i-up" viewBox="0 0 24 24"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></symbol>
  <symbol id="i-gear" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></symbol>
  <symbol id="i-img" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/></symbol>
  <symbol id="i-play" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="m10 9 5 3-5 3z"/></symbol>
  <symbol id="i-eye" viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></symbol>
  <symbol id="i-edit" viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></symbol>
  <symbol id="i-trash" viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></symbol>
  <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></symbol>
  <symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></symbol>
  <symbol id="i-x" viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></symbol>
  <symbol id="i-refresh" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.6-6.3L21 8"/><path d="M21 3v5h-5"/></symbol>
</svg>

<header class="bar">
  <div class="bar-in">
    <div class="mark" aria-hidden="true">IG</div>
    <div class="title">Uploads<small>Photos and reels for your next post</small></div>
    <div class="bar-end">
      <span class="chip-keep" id="keepChip" title="Unposted files are removed after this time"><svg class="i" aria-hidden="true"><use href="#i-clock"/></svg><span><span class="long">Kept </span><span id="keepHours">48</span>&nbsp;h</span></span>
      <button class="icon-btn" id="openSettings" type="button" aria-label="Retention settings"><svg class="i" aria-hidden="true"><use href="#i-gear"/></svg></button>
    </div>
  </div>
</header>

<div class="tabs">
  <div class="seg" role="tablist" aria-label="Uploads">
    <button type="button" role="tab" id="tabAdd" aria-selected="true" aria-controls="panelAdd"><svg class="i" aria-hidden="true"><use href="#i-up"/></svg>Add files</button>
    <button type="button" role="tab" id="tabLib" aria-selected="false" aria-controls="panelLib"><svg class="i" aria-hidden="true"><use href="#i-img"/></svg>Library <span class="count" id="libCount">0</span></button>
  </div>
</div>

<main>
  <!-- ADD FILES -->
  <section class="panel" id="panelAdd" role="tabpanel" aria-labelledby="tabAdd">
    <div class="card pad">
      <label class="drop" id="drop" tabindex="0">
        <input type="file" id="file" multiple accept="image/*,video/mp4,video/quicktime,video/*" hidden>
        <div class="big" aria-hidden="true"><svg class="i" style="width:24px;height:24px"><use href="#i-up"/></svg></div>
        <strong>Choose photos or videos</strong>
        <span>or drag them here. Each file uploads in parts, so large files are fine.</span>
      </label>

      <div class="queue" id="queue" aria-live="polite"></div>

      <details class="opts" id="opts">
        <summary>Photo settings</summary>
        <div class="grid2">
          <div>
            <label class="f" for="aspect">Shape</label>
            <select id="aspect">
              <option value="keep">Original, no changes (default)</option>
              <option value="auto">Fit Instagram's shapes (crop only if needed)</option>
              <option value="square">Square 1:1 (resized)</option>
              <option value="portrait">Portrait 4:5 (resized)</option>
              <option value="landscape">Landscape 1.91:1 (resized)</option>
            </select>
            <p class="sub">Original keeps every pixel and the full frame. Nothing is cropped or resized.</p>
          </div>
        </div>
      </details>
    </div>
    <details class="card logbox" id="logBox" open>
      <summary><span>Activity log</span><span class="sub-s">Updates live. Copy it into the chat if something goes wrong.</span></summary>
      <div class="log-tools">
        <button class="btn" id="logCheck" type="button">Check setup</button>
        <button class="btn primary" id="logCopy" type="button">Copy log</button>
        <button class="btn" id="logClear" type="button">Clear</button>
      </div>
      <pre class="log" id="log" tabindex="0"></pre>
    </details>
  </section>

  <!-- LIBRARY -->
  <section class="panel hidden" id="panelLib" role="tabpanel" aria-labelledby="tabLib">
    <div class="toolbar">
      <div class="search">
        <svg class="i" aria-hidden="true"><use href="#i-search"/></svg>
        <input type="search" id="search" placeholder="Search by name or caption" aria-label="Search uploads">
      </div>
      <div class="chips" role="group" aria-label="Filter">
        <button class="chip" type="button" data-f="all" aria-pressed="true">All</button>
        <button class="chip" type="button" data-f="photo" aria-pressed="false">Photos</button>
        <button class="chip" type="button" data-f="reel" aria-pressed="false">Reels</button>
        <button class="icon-btn" id="refresh" type="button" aria-label="Refresh"><svg class="i" aria-hidden="true"><use href="#i-refresh"/></svg></button>
      </div>
    </div>
    <div class="libbar">
      <span class="storage" id="storageLine" aria-live="polite">Checking storage...</span>
      <button class="link" id="selAll" type="button">Select all shown</button>
    </div>
    <div class="selbar hidden" id="selBar" role="region" aria-label="Selected files">
      <b id="selText">0 selected</b>
      <span class="grow"></span>
      <button class="link" id="selClear" type="button">Clear</button>
      <button class="btn danger solid" id="selDelete" type="button">Delete selected</button>
    </div>
    <div class="grid" id="grid"></div>
    <div class="empty hidden" id="libEmpty">
      <div class="art"><svg class="i" style="width:28px;height:28px"><use href="#i-img"/></svg></div>
      <b id="emptyTitle">Nothing waiting yet</b>
      <span id="emptyText">Files you upload appear here until you post them.</span>
    </div>
  </section>
</main>

<div class="dock" id="dock" role="region" aria-label="Upload">
  <div class="dock-in">
    <div class="dock-text"><b id="dockTitle">0 files ready</b><span id="dockSub"></span></div>
    <button class="link" id="clear" type="button" hidden>Clear finished</button>
    <button class="btn primary" id="start" type="button" disabled>Upload</button>
  </div>
</div>

<div class="scrim" id="scrim" aria-hidden="true">
  <div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="sheetTitle"></div>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
"use strict";
const params = new URLSearchParams(location.search);
const AUTH = params.get("auth") || sessionStorage.getItem("mcp_auth") || "";
if (AUTH) sessionStorage.setItem("mcp_auth", AUTH);
const H = {"X-Auth-Key": AUTH};
const $ = (id) => document.getElementById(id);
const DEFAULT_HOURS = 48;
const BUILD = "2026-10-31 manual delete";
const LOG_LIMIT = 500;
const logLines = [];
function redact(s) {
  let out = String(s);
  if (AUTH) out = out.split(AUTH).join("<key>");
  return out
    .replace(/vercel_blob_(client|rw)_[A-Za-z0-9_\-]+/g, "<token>")
    .replace(/([?&]auth=)[^&\s"']+/g, "$1<key>");
}
function errText(e) {
  if (e && e.message) return redact((e.name || "Error") + ": " + e.message);
  return redact(String(e));
}
function logLine(level, text) {
  const stamp = new Date().toLocaleTimeString([], {hour12: false});
  logLines.push(stamp + " " + level.toUpperCase().padEnd(5) + " " + redact(text));
  if (logLines.length > LOG_LIMIT) logLines.splice(0, logLines.length - LOG_LIMIT);
  const pre = document.getElementById("log");
  if (pre) { pre.textContent = logLines.join("\n"); pre.scrollTop = pre.scrollHeight; }
  if (level === "error") { const box = document.getElementById("logBox"); if (box) box.open = true; }
}
function shortUrl(url) {
  try {
    const u = new URL(url, location.href);
    const where = u.origin === location.origin ? u.pathname : u.host + u.pathname;
    const pn = u.searchParams.get("pathname");
    return redact(where + (pn ? "?pathname=" + decodeURIComponent(pn) : ""));
  } catch (e) { return redact(String(url)).slice(0, 160); }
}
const nativeFetch = window.fetch.bind(window);
window.fetch = async function (input, init) {
  const url = typeof input === "string" ? input : (input && input.url) || String(input);
  const watched = /\/api\/|\/upload-client\.js|vercel\.com\/api\/blob|blob\.vercel-storage/.test(url);
  if (!watched) return nativeFetch(input, init);
  const method = (init && init.method) || (input && input.method) || "GET";
  const label = method + " " + shortUrl(url);
  logLine("net", "-> " + label);
  try {
    const res = await nativeFetch(input, init);
    let snippet = "";
    if (!res.ok || /\/api\//.test(url)) {
      try { snippet = " " + (await res.clone().text()).slice(0, 240); } catch (e) { snippet = ""; }
    }
    logLine(res.ok ? "net" : "error", "<- " + res.status + " " + label + snippet);
    return res;
  } catch (e) {
    logLine("error", "x  " + label + " failed: " + errText(e));
    throw e;
  }
};

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
const icon = (name) => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("class", "i"); s.setAttribute("aria-hidden", "true");
  const u = document.createElementNS("http://www.w3.org/2000/svg", "use");
  u.setAttribute("href", "#i-" + name); s.appendChild(u); return s;
};

let toastTimer = 0;
function toast(message, tone) {
  const t = $("toast");
  t.textContent = message; t.className = "toast show" + (tone ? " " + tone : "");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}

async function api(body) {
  logLine("info", "action " + body.action + (body.filename ? " " + body.filename : ""));
  const r = await fetch('/api/upload', {
    method: "POST", headers: {...H, "Content-Type": "application/json"}, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 401) throw new Error("This link has no valid key. Open the upload page from your dashboard.");
    throw new Error(friendlyApi(data, r.status));
  }
  return data;
}

function friendlyApi(data, status) {
  if (data.error === "blob_not_configured") {
    return "File storage is not connected to this project yet. Connect Vercel Blob in the project settings, then try again.";
  }
  if (data.error === "server_error") return "The server hit a problem: " + (data.detail || "unknown error") + ". Try again in a moment.";
  return data.error || ("Something went wrong (" + status + ").");
}
function friendly(e) {
  const msg = (e && e.message) || "";
  if (/content.?type|not allowed/i.test(msg)) return "This file type is not supported. Use JPEG, PNG, WebP, GIF, MP4 or MOV.";
  if (/too large|maximum/i.test(msg)) return "This file is too large to upload.";
  if (/client token/i.test(msg)) return "The server did not approve this upload. Open the page again from your dashboard link. The activity log shows the exact reply.";
  return msg || "Upload failed. Try again.";
}

const mediaUrl = (id, what) => "/api/upload?" + what + "=" + encodeURIComponent(id) + "&auth=" + encodeURIComponent(AUTH);
const isVideo = (file) => (file.type || "").startsWith("video/") || /\.(mp4|mov|m4v)$/i.test(file.name);
const kindOf = (file) => (isVideo(file) ? "reel" : "photo");
const ALLOWED = ["image/jpeg", "image/png", "image/webp", "image/gif", "video/mp4", "video/quicktime", "video/x-m4v"];
const EXT_TYPES = {jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", gif: "image/gif",
  mp4: "video/mp4", mov: "video/quicktime", m4v: "video/x-m4v"};
function typeFor(file) {
  if (ALLOWED.includes(file.type)) return file.type;
  return EXT_TYPES[(file.name.split(".").pop() || "").toLowerCase()] || "";
}
const isMedia = (file) => !!typeFor(file);
function fmtSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}
function fmtUntil(seconds) {
  return new Date(seconds * 1000).toLocaleString([], {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"});
}

/* ---------- tabs ---------- */
function showTab(name) {
  const add = name === "add";
  $("panelAdd").classList.toggle("hidden", !add);
  $("panelLib").classList.toggle("hidden", add);
  $("tabAdd").setAttribute("aria-selected", String(add));
  $("tabLib").setAttribute("aria-selected", String(!add));
  if (!add) loadUploads();
}
$("tabAdd").addEventListener("click", () => showTab("add"));
$("tabLib").addEventListener("click", () => showTab("lib"));

/* ---------- queue ---------- */
const queue = [];
let busy = false;
let batch = {total: 0, index: 0};

function setState(item, state, text) {
  item.state = state;
  item.status.textContent = text;
  item.row.classList.remove("ready", "uploading", "done", "failed");
  item.row.classList.add(state);
  updateDock();
}
function setPct(item, pct) { item.bar.firstChild.style.width = Math.max(0, Math.min(100, pct)) + "%"; }

function renderItem(item) {
  const f = item.file;
  const thumb = isVideo(f)
    ? el("div", {class: "thumb", "aria-hidden": "true"}, icon("play"))
    : el("img", {class: "thumb", src: item.preview, alt: ""});
  const remove = el("button", {class: "link", type: "button", text: "Remove", onclick: () => removeItem(item)});
  const caption = el("input", {type: "text", maxlength: "2200", placeholder: "Caption for this file (optional)",
    "aria-label": "Caption for " + f.name, oninput: (e) => { item.caption = e.target.value; }});
  item.bar = el("div", {class: "bar-track"}, el("i"));
  item.status = el("div", {class: "status", text: "Ready to upload"});
  item.row = el("div", {class: "qitem ready"}, thumb,
    el("div", {class: "qmain"},
      el("div", {class: "qrow"}, el("span", {class: "name", text: f.name}), el("span", {class: "meta", text: fmtSize(f.size)})),
      item.bar, item.status, caption),
    remove);
  $("queue").append(item.row);
}

function removeItem(item) {
  if (item.state === "uploading") return;
  item.row.classList.add("removing");
  setTimeout(() => {
    item.row.remove();
    queue.splice(queue.indexOf(item), 1);
    if (item.preview) URL.revokeObjectURL(item.preview);
    updateDock();
  }, 240);
}

function addFiles(files) {
  let skipped = 0;
  for (const file of files) {
    if (!isMedia(file)) { skipped += 1; continue; }
    const item = {file, state: "ready", caption: "", preview: isVideo(file) ? "" : URL.createObjectURL(file)};
    queue.push(item);
    renderItem(item);
  }
  if (skipped) toast(skipped + (skipped === 1 ? " file was" : " files were") + " skipped. Use JPEG, PNG, WebP, GIF, MP4 or MOV (export HEIC photos as JPEG).", "bad");
  updateDock();
}

function updateDock() {
  const ready = queue.filter((i) => i.state === "ready" || i.state === "failed");
  const finished = queue.filter((i) => i.state === "done" || i.state === "failed");
  const bytes = ready.reduce((n, i) => n + i.file.size, 0);
  if (busy) {
    $("dockTitle").textContent = "Uploading " + batch.index + " of " + batch.total;
    $("dockSub").textContent = "Keep this page open until it finishes.";
  } else {
    $("dockTitle").textContent = ready.length ? ready.length + (ready.length === 1 ? " file ready" : " files ready") : (queue.length ? "All done" : "No files selected");
    $("dockSub").textContent = ready.length ? fmtSize(bytes) + " in total" : (queue.length ? "Uploaded files are in the Library." : "Choose photos or videos to begin.");
  }
  $("start").disabled = !ready.length || busy;
  $("start").textContent = busy ? "Uploading..." : "Upload";
  $("clear").hidden = !finished.length || busy;
  $("dock").classList.toggle("show", queue.length > 0);
}

/* ---------- uploading ---------- */
// A small JPEG preview (max 512 px). Failure is not fatal: the assistant can still work from the file.
async function makeThumb(file) {
  const url = URL.createObjectURL(file);
  try {
    let source, w, h;
    if (isVideo(file)) {
      source = await new Promise((resolve, reject) => {
        const v = document.createElement("video");
        v.muted = true; v.playsInline = true; v.preload = "auto";
        v.onloadeddata = () => { v.currentTime = Math.min(0.5, (v.duration || 1) / 2); };
        v.onseeked = () => resolve(v);
        v.onerror = () => reject(new Error("video frame unreadable"));
        v.src = url;
      });
      w = source.videoWidth; h = source.videoHeight;
    } else {
      source = await createImageBitmap(file); w = source.width; h = source.height;
    }
    const scale = Math.min(1, 512 / Math.max(w, h));
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(w * scale)); c.height = Math.max(1, Math.round(h * scale));
    c.getContext("2d").drawImage(source, 0, 0, c.width, c.height);
    return await new Promise((resolve) => c.toBlob(resolve, "image/jpeg", 0.8));
  } catch (e) {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function uploadItem(item) {
  const f = item.file;
  const kind = kindOf(f);
  logLine("info", "start " + f.name + " (" + kindOf(f) + ", " + f.size + " bytes, " + (typeFor(f) || "unknown type") + ")");
  setState(item, "uploading", "Preparing...");
  setPct(item, 0);
  const slot = await api({action: 'begin', filename: f.name, size: f.size,
    content_type: typeFor(f), kind});
  setState(item, "uploading", "Uploading...");
  const {upload} = await import("/upload-client.js");
  const blob = await upload(slot.pathname, f, {
    access: slot.access || "private",
    handleUploadUrl: slot.handle_upload_url || "/api/blob-token",
    clientPayload: JSON.stringify({key: AUTH, kind}),
    contentType: typeFor(f),
    multipart: f.size > 20 * 1024 * 1024,
    onUploadProgress: (e) => {
      if (item.state !== "uploading") return;
      setPct(item, e.percentage);
      const milestone = Math.floor(e.percentage / 25) * 25;
      if (milestone !== item.milestone) { item.milestone = milestone; logLine("info", f.name + " " + milestone + "%"); }
      item.status.textContent = "Uploading... " + Math.round(e.percentage) + "%";
    },
  });
  setState(item, "uploading", "Finishing...");
  let thumbPathname = "";
  const thumb = await makeThumb(f);
  if (thumb) {
    try {
      const ts = await api({action: 'begin', filename: "thumb.jpg", size: thumb.size, content_type: "image/jpeg", kind});
      const tb = await upload(ts.pathname, thumb, {
        access: ts.access || "private",
        handleUploadUrl: ts.handle_upload_url || "/api/blob-token",
        clientPayload: JSON.stringify({key: AUTH, kind}),
        contentType: "image/jpeg",
      });
      thumbPathname = tb.pathname;
    } catch (e) { thumbPathname = ""; logLine("warn", "preview not saved: " + errText(e)); }
  }
  const caption = (item.caption || "").trim();
  await api({action: 'commit', filename: f.name, pathname: blob.pathname, url: blob.url, size: f.size,
    content_type: typeFor(f), kind, aspect: $("aspect").value, caption, thumb_pathname: thumbPathname});
  setPct(item, 100);
  logLine("info", "done " + f.name);
  setState(item, "done", "Uploaded");
}

async function startAll() {
  if (busy) return;
  busy = true; updateDock();
  const pending = queue.filter((i) => i.state === "ready" || i.state === "failed");
  batch = {total: pending.length, index: 0};
  let ok = 0;
  for (const item of pending) {
    batch.index += 1;
    updateDock();
    try { await uploadItem(item); ok += 1; }
    catch (e) { logLine("error", item.file.name + " failed: " + errText(e)); setState(item, "failed", friendly(e)); }
  }
  busy = false; updateDock();
  if (ok) toast(ok === 1 ? "Uploaded. It is in your Library." : ok + " files uploaded. They are in your Library.", "ok");
  loadUploads();
}
$("start").addEventListener("click", startAll);
$("clear").addEventListener("click", () => {
  for (const item of queue.filter((i) => i.state === "done" || i.state === "failed")) {
    item.row.remove();
    if (item.preview) URL.revokeObjectURL(item.preview);
  }
  for (let i = queue.length - 1; i >= 0; i -= 1) {
    if (queue[i].state === "done" || queue[i].state === "failed") queue.splice(i, 1);
  }
  updateDock();
});

/* drop zone */
const drop = $("drop");
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } });
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); addFiles(e.dataTransfer.files); });
$("file").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });

/* ---------- library ---------- */
let uploads = [];
let filter = "all";
let query = "";
const picked = new Set();  // ids ticked in the Library

async function loadUploads() {
  if (!AUTH) return;
  $("grid").replaceChildren(...[0, 1, 2, 3].map(() => el("div", {class: "skel", style: "aspect-ratio:4/5"})));
  $("libEmpty").classList.add("hidden");
  try {
    const data = await api({action: 'list'});
    uploads = data.uploads || [];
    $("keepHours").textContent = data.retention_hours;
    for (const id of [...picked]) if (!uploads.some((u) => u.id === id)) picked.delete(id);
    renderLibrary();
    loadStorage();
  } catch (e) {
    $("grid").replaceChildren();
    logLine("error", "library: " + errText(e));
    showEmpty("Could not load your library", e.message);
    toast(e.message, "bad");
  }
}

function visible() {
  const q = query.trim().toLowerCase();
  return uploads.filter((u) => (filter === "all" || u.kind === (filter === "reel" ? "reel" : "photo"))
    && (!q || (u.title || u.filename || "").toLowerCase().includes(q) || (u.caption || "").toLowerCase().includes(q)));
}

function showEmpty(title, text) {
  $("emptyTitle").textContent = title;
  $("emptyText").textContent = text;
  $("libEmpty").classList.remove("hidden");
}

function renderLibrary() {
  $("libCount").textContent = uploads.length;
  const list = visible();
  $("grid").replaceChildren(...list.map(tile));
  if (!uploads.length) showEmpty("Nothing waiting yet", "Files you upload appear here until you post them.");
  else if (!list.length) showEmpty("No matches", "Try another search or filter.");
  else $("libEmpty").classList.add("hidden");
  updateSelBar();
}

function tile(u) {
  const pic = el("div", {class: "pic"});
  if (u.has_thumb) pic.append(el("img", {src: mediaUrl(u.id, 'thumb'), alt: "", loading: "lazy"}));
  else pic.append(el("div", {class: "thumb", "aria-hidden": "true", style: "width:44px;height:44px"}, icon(u.kind === "reel" ? "play" : "img")));
  pic.append(el("span", {class: "kind", text: u.kind === "reel" ? "REEL" : "PHOTO"}));
  const btn = (label, name, fn, extra) => el("button", {type: "button", class: extra || "", title: label, "aria-label": label, onclick: fn}, icon(name));
  const tick = el("input", {type: "checkbox", "aria-label": "Select " + (u.title || u.filename),
    checked: picked.has(u.id), onchange: (e) => setPicked(u.id, e.target.checked)});
  pic.append(el("label", {class: "pick", title: "Select"}, tick));
  return el("article", {class: picked.has(u.id) ? "tile picked" : "tile", "data-id": u.id},
    pic,
    el("div", {class: "tb"},
      el("div", {class: "tn", text: u.title || u.filename}),
      el("div", {class: "tm", text: fmtSize(u.size) + " · keep until " + fmtUntil(u.expires_at)})),
    el("div", {class: "ta"},
      btn("View", "eye", () => openView(u)),
      btn("Rename", "edit", () => openRename(u)),
      btn("Delete", "trash", () => openDelete(u), "del")));
}

document.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
  filter = chip.dataset.f;
  document.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
  renderLibrary();
}));
$("search").addEventListener("input", (e) => { query = e.target.value; renderLibrary(); });
$("refresh").addEventListener("click", loadUploads);

/* ---------- selection, storage and bulk delete ---------- */
const MAX_BULK = 200;  // matches the server limit

function setPicked(id, on) {
  if (on) picked.add(id); else picked.delete(id);
  const t = document.querySelector('.tile[data-id="' + CSS.escape(id) + '"]');
  if (t) t.classList.toggle("picked", on);
  updateSelBar();
}
function updateSelBar() {
  const chosen = uploads.filter((u) => picked.has(u.id));
  const shown = visible();
  const allOn = shown.length > 0 && shown.every((u) => picked.has(u.id));
  $("selBar").classList.toggle("hidden", chosen.length === 0);
  $("selText").textContent = chosen.length + " selected, "
    + fmtMB(chosen.reduce((s, u) => s + (u.size || 0), 0) / 1024 / 1024);
  $("selAll").textContent = allOn ? "Clear shown" : "Select all shown";
  $("selAll").disabled = shown.length === 0;
}
$("selAll").addEventListener("click", () => {
  const shown = visible();
  const allOn = shown.length > 0 && shown.every((u) => picked.has(u.id));
  shown.forEach((u) => (allOn ? picked.delete(u.id) : picked.add(u.id)));
  renderLibrary();
});
$("selClear").addEventListener("click", () => { picked.clear(); renderLibrary(); });
$("selDelete").addEventListener("click", openDeleteMany);

function fmtMB(mb) {
  const n = Number(mb) || 0;
  return n >= 1024 ? (n / 1024).toFixed(2) + " GB" : Math.round(n) + " MB";
}
async function loadStorage() {
  try { showStorage(await api({action: 'storage'})); }
  catch (e) { $("storageLine").textContent = "Storage: could not check (" + errText(e) + ")"; }
}
function showStorage(s) {
  const left = Math.max(0, Number(s.limit_gb) * 1024 - Number(s.used_mb));
  const line = $("storageLine");
  line.textContent = "Using " + fmtMB(s.used_mb) + " of " + s.limit_gb + " GB, " + fmtMB(left) + " left"
    + (s.count_is_capped ? " (over 1000 files, so the real total may be higher)" : "");
  line.classList.toggle("warn", Number(s.percent_used) >= 80);
}

function openDeleteMany() {
  const chosen = uploads.filter((u) => picked.has(u.id));
  if (!chosen.length) return;
  if (chosen.length > MAX_BULK) { toast("Delete at most " + MAX_BULK + " files at a time.", "bad"); return; }
  const n = chosen.length;
  const label = n + (n === 1 ? " file" : " files");
  const totalMB = chosen.reduce((s, u) => s + (u.size || 0), 0) / 1024 / 1024;
  const confirm = el("button", {class: "btn danger solid", type: "button", text: "Delete " + label, onclick: async () => {
    confirm.disabled = true;
    try {
      const data = await api({action: 'delete_many', ids: chosen.map((u) => u.id)});
      const done = data.deleted || [];
      const failed = data.failed || [];
      done.forEach((d) => picked.delete(d.id));
      closeSheet();
      if (done.length) toast("Deleted " + done.length + (done.length === 1 ? " file" : " files") + ". Freed " + fmtMB(data.freed_mb) + ".", "ok");
      if (failed.length) toast(failed.length + " could not be deleted. They are still in your library.", "bad");
      logLine(failed.length ? "error" : "info", "delete: " + done.length + " deleted, " + failed.length + " failed");
      loadUploads();
    } catch (e) {
      confirm.disabled = false;
      toast(e.message, "bad");
    }
  }});
  openSheet([
    el("h3", {id: "sheetTitle", text: "Delete " + label + "?"}),
    el("p", {class: "sub", text: "About " + fmtMB(totalMB) + " will be removed from storage right away. This cannot be undone."}),
    el("ul", {class: "dellist"}, chosen.slice(0, 50).map((u) => el("li", {text: (u.title || u.filename) + " · " + fmtSize(u.size)}))),
    n > 50 ? el("p", {class: "sub", text: "...and " + (n - 50) + " more."}) : null,
    el("div", {class: "row"}, el("button", {class: "btn", type: "button", text: "Keep them", onclick: closeSheet}), confirm),
  ]);
}

/* ---------- sheets ---------- */
function openSheet(children) {
  $("sheet").replaceChildren(...children.filter(Boolean));  // a null child would print as the word "null"
  $("scrim").classList.add("open");
  $("scrim").setAttribute("aria-hidden", "false");
  const first = $("sheet").querySelector("input, button");
  if (first) setTimeout(() => first.focus(), 60);
}
function closeSheet() {
  $("scrim").classList.remove("open");
  $("scrim").setAttribute("aria-hidden", "true");
}
$("scrim").addEventListener("click", (e) => { if (e.target === $("scrim")) closeSheet(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });

function openView(u) {
  const media = u.kind === "reel"
    ? el("video", {src: mediaUrl(u.id, 'file'), controls: true, playsinline: true, preload: "metadata"})
    : el("img", {src: mediaUrl(u.id, 'file'), alt: u.title || u.filename});
  const preview = u.has_thumb ? el("img", {src: mediaUrl(u.id, 'thumb'), alt: ""}) : null;
  const note = el("div", {class: "notice warn", text: "This file is too large to open here, so its preview is shown."});
  media.addEventListener("error", () => { media.replaceWith(...[preview, note].filter(Boolean)); });
  openSheet([
    el("h3", {id: "sheetTitle", text: u.title || u.filename}),
    el("div", {class: "meta", text: (u.kind === "reel" ? "Reel" : "Photo") + " · " + fmtSize(u.size)}),
    media,
    u.caption ? el("p", {class: "sub", text: "Caption: " + u.caption}) : null,
    el("div", {class: "row"}, el("button", {class: "btn", type: "button", text: "Close", onclick: closeSheet})),
  ]);
}

function openRename(u) {
  const input = el("input", {type: "text", maxlength: "120", value: u.title || u.filename, "aria-label": "New name"});
  const save = el("button", {class: "btn primary", type: "button", text: "Save", onclick: async () => {
    try {
      await api({action: 'rename', id: u.id, title: input.value});
      closeSheet(); toast("Renamed.", "ok"); loadUploads();
    } catch (e) { toast(e.message, "bad"); }
  }});
  openSheet([
    el("h3", {id: "sheetTitle", text: "Rename"}),
    el("p", {class: "sub", text: "This only changes the name shown here. The file itself stays the same."}),
    input,
    el("div", {class: "row"}, el("button", {class: "btn", type: "button", text: "Cancel", onclick: closeSheet}), save),
  ]);
  input.select();
}

function openDelete(u) {
  const confirm = el("button", {class: "btn danger solid", type: "button", text: "Delete", onclick: async () => {
    try {
      await api({action: 'delete', id: u.id});
      closeSheet(); toast("Deleted.", "ok"); loadUploads();
    } catch (e) { toast(e.message, "bad"); }
  }});
  openSheet([
    el("h3", {id: "sheetTitle", text: "Delete this file?"}),
    el("p", {class: "sub", text: (u.title || u.filename) + " will be removed from storage. This cannot be undone."}),
    el("div", {class: "row"}, el("button", {class: "btn", type: "button", text: "Keep it", onclick: closeSheet}), confirm),
  ]);
}

/* ---------- retention settings ---------- */
const PRESETS = [[24, "24 hours"], [48, "2 days"], [72, "3 days"], [168, "1 week"], [720, "30 days"]];
async function openSettings() {
  let current = DEFAULT_HOURS;
  try { current = (await api({action: 'settings'})).retention_hours; } catch (e) { /* show the default */ }
  const input = el("input", {type: "number", min: "1", max: "720", step: "1", inputmode: "numeric", value: current, "aria-label": "Hours"});
  const note = el("div", {class: "notice", style: "display:none"});
  const show = (msg, tone) => { note.className = "notice " + tone; note.textContent = msg; note.style.display = "block"; };
  const save = async (hours) => {
    try {
      const d = await api({action: 'settings_save', retention_hours: hours});
      input.value = d.retention_hours;
      $("keepHours").textContent = d.retention_hours;
      show("Saved. Unposted files are kept for " + d.retention_hours + " hours.", "ok");
      toast("Saved.", "ok");
    } catch (e) { show(e.message, "bad"); }
  };
  const presets = el("div", {class: "presets"}, PRESETS.map(([h, label]) =>
    el("button", {class: "chip", type: "button", "aria-pressed": String(h === Number(current)), text: label,
      onclick: () => { input.value = h; save(h); }})));
  openSheet([
    el("h3", {id: "sheetTitle", text: "Keep unposted files"}),
    el("p", {class: "sub", text: "Files you upload but do not post are removed automatically after this long."}),
    presets,
    el("label", {class: "f", for: "hoursIn", text: "Or enter hours (1 to 720)"}),
    Object.assign(input, {id: "hoursIn"}),
    note,
    el("div", {class: "row"},
      el("button", {class: "btn", type: "button", text: "Back to 48 hours", onclick: () => save(DEFAULT_HOURS)}),
      el("button", {class: "btn primary", type: "button", text: "Save", onclick: () => save(Number(input.value))})),
  ]);
}
$("openSettings").addEventListener("click", openSettings);

/* ---------- activity log ---------- */
async function runCheck() {
  logLine("info", "Check setup started");
  logLine("info", "page " + location.pathname + " | online " + navigator.onLine + " | " + navigator.userAgent.slice(0, 120));
  try { await import("/upload-client.js"); logLine("info", "upload library: loads OK"); }
  catch (e) { logLine("error", "upload library: FAILED to load: " + errText(e)); }
  try { const d = await api({action: "settings"}); logLine("info", "server: reachable, keeps unposted files " + d.retention_hours + " h"); }
  catch (e) { logLine("error", "server: " + errText(e)); }
  try {
    const r = await fetch("/api/blob-token", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({type: "blob.generate-client-token", payload: {pathname: "instagram-mcp/uploads/check/none.jpg",
        clientPayload: JSON.stringify({key: "check"}), multipart: false}})});
    const text = await r.text();
    logLine(r.status < 500 ? "info" : "error", "upload token endpoint: HTTP " + r.status + " " + text.slice(0, 200)
      + (r.status === 400 || r.status === 401 ? " (expected here: this check uses a fake key)" : ""));
  } catch (e) { logLine("error", "upload token endpoint: " + errText(e)); }
  logLine("info", "Check setup finished");
}
async function copyLog() {
  const text = logLines.join("\n") || "(the log is empty)";
  try {
    await navigator.clipboard.writeText(text);
    toast("Log copied. Paste it into the chat.", "ok");
  } catch (e) {
    const area = document.createElement("textarea");
    area.value = text; document.body.append(area); area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (x) { ok = false; }
    area.remove();
    toast(ok ? "Log copied. Paste it into the chat." : "Could not copy. Select the log text and copy it.", ok ? "ok" : "bad");
  }
}
$("logCopy").addEventListener("click", copyLog);
$("logCheck").addEventListener("click", runCheck);
$("logClear").addEventListener("click", () => { logLines.length = 0; logLine("info", "Log cleared"); });

/* ---------- start ---------- */
if (!AUTH) {
  $("dockSub").textContent = "This page needs its key. Open it from your dashboard.";
  $("start").disabled = true;
  $("tabLib").disabled = true;
} else {
  api({action: 'settings'}).then((d) => { $("keepHours").textContent = d.retention_hours; }).catch(() => {});
}
window.addEventListener("error", (e) => logLine("error", "page error: " + (e.message || "unknown")
  + (e.filename ? " at " + e.filename.split("/").pop() + ":" + e.lineno : "")));
window.addEventListener("unhandledrejection", (e) => logLine("error", "unhandled: " + errText(e.reason)));
logLine("info", "Page opened. Build " + BUILD + ". Key " + (AUTH ? "present (" + AUTH.length + " characters)" : "MISSING: open this page from the dashboard link") + ".");
updateDock();
</script>
</body>
</html>
"""
