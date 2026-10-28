"""The browser upload page, embedded as a string so it ships inside the function.

Vercel only bundles .py files, so a file read from public/ at runtime is missing in production.
The page talks to /api/upload (JSON actions and ?thumb= / ?file= reads) and to /api/blob-token
(short-lived upload tokens), both behind the same key as the page itself.
"""

UPLOAD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Upload</title>
<style>
  :root {
    --bg: #f5f6f8; --card: #ffffff; --ink: #1c2026; --muted: #6b7280; --line: #e3e6eb;
    --accent: #e1306c; --ok: #15803d; --bad: #b91c1c; --radius: 16px;
    --shadow: 0 1px 2px rgba(16, 24, 40, .06), 0 6px 20px rgba(16, 24, 40, .05);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0f1115; --card: #171a21; --ink: #eef0f3; --muted: #9aa3b2; --line: #2a303b;
      --accent: #ff5a8f; --ok: #22c55e; --bad: #f87171; --shadow: none;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  .wrap { max-width: 980px; margin: 0 auto; padding: 24px 16px 72px; }
  h1 { font-size: 1.6rem; margin: 0 0 4px; }
  h2 { font-size: 1.1rem; margin: 0; }
  h3 { margin: 0 0 6px; font-size: 1.05rem; }
  p { margin: 0 0 10px; }
  .muted { color: var(--muted); font-size: .92rem; }
  .card {
    background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 20px; box-shadow: var(--shadow); margin-top: 16px;
    animation: rise .35s ease both;
  }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
  .actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 14px; }

  .btn {
    appearance: none; border: 1px solid transparent; border-radius: 12px; padding: 10px 16px;
    font: inherit; font-weight: 600; cursor: pointer; background: var(--line); color: var(--ink);
    transition: transform .15s ease, opacity .2s ease, background .2s ease;
  }
  .btn:hover { transform: translateY(-1px); }
  .btn:active { transform: scale(.98); }
  .btn:disabled { opacity: .45; cursor: default; transform: none; }
  .btn.primary { background: var(--accent); color: #fff; }
  .btn.ghost { background: transparent; border-color: var(--line); }
  .btn.danger { background: transparent; color: var(--bad); border-color: var(--line); }
  .btn.small { padding: 6px 10px; font-size: .88rem; border-radius: 10px; }
  .btn:focus-visible, .drop:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }

  input[type=text], input[type=number], select {
    width: 100%; padding: 11px 12px; border-radius: 12px; border: 1px solid var(--line);
    background: var(--bg); color: var(--ink); font: inherit;
    transition: border-color .2s ease;
  }
  input:focus, select:focus { border-color: var(--accent); outline: none; }
  label.field { display: block; font-weight: 600; font-size: .92rem; margin: 0 0 6px; }
  .fields { display: grid; gap: 14px; grid-template-columns: 1fr; margin-top: 16px; }
  @media (min-width: 640px) { .fields { grid-template-columns: 1fr 2fr; } }

  .drop {
    display: block; text-align: center; cursor: pointer; border: 2px dashed var(--line);
    border-radius: 16px; padding: 30px 16px; transition: border-color .2s ease, background .2s ease;
  }
  .drop:hover, .drop.over { border-color: var(--accent); background: rgba(225, 48, 108, .06); }
  .drop strong { display: block; font-size: 1.05rem; margin-bottom: 4px; }
  .drop .big { font-size: 2rem; line-height: 1; margin-bottom: 8px; }

  .queue { margin-top: 12px; }
  .item {
    display: grid; grid-template-columns: 56px 1fr; gap: 12px; padding: 12px 0;
    border-top: 1px solid var(--line); animation: rise .3s ease both;
  }
  .item:first-child { border-top: 0; }
  .item.removing { opacity: 0; transform: translateX(8px); transition: opacity .25s ease, transform .25s ease; }
  .thumb {
    width: 56px; height: 56px; border-radius: 12px; object-fit: cover;
    background: var(--line); display: flex; align-items: center; justify-content: center; color: var(--muted);
  }
  .row1 { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
  .name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .bar { height: 8px; background: var(--line); border-radius: 99px; overflow: hidden; margin: 8px 0 6px; }
  .bar > i { display: block; height: 100%; width: 0; background: var(--accent); border-radius: 99px; transition: width .25s ease; }
  .item.done .bar > i { background: var(--ok); width: 100% !important; }
  .item.failed .bar > i { background: var(--bad); }
  .status { font-size: .88rem; color: var(--muted); }
  .item.done .status { color: var(--ok); }
  .item.failed .status { color: var(--bad); }
  .item input { margin-top: 6px; padding: 8px 10px; font-size: .92rem; border-radius: 10px; }

  .uploads { display: grid; gap: 14px; grid-template-columns: repeat(2, 1fr); margin-top: 14px; }
  @media (min-width: 640px) { .uploads { grid-template-columns: repeat(3, 1fr); } }
  @media (min-width: 920px) { .uploads { grid-template-columns: repeat(4, 1fr); } }
  .tile {
    border: 1px solid var(--line); border-radius: 14px; overflow: hidden; background: var(--card);
    display: flex; flex-direction: column; animation: rise .35s ease both;
    transition: transform .2s ease, box-shadow .2s ease;
  }
  .tile:hover { transform: translateY(-2px); box-shadow: var(--shadow); }
  .pic {
    aspect-ratio: 4 / 5; background: var(--line); display: flex; align-items: center; justify-content: center;
    color: var(--muted); font-size: 1.8rem; overflow: hidden;
  }
  .pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .tbody { padding: 10px 12px 4px; min-width: 0; }
  .tname { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tmeta { font-size: .8rem; color: var(--muted); margin-top: 2px; }
  .tacts { display: flex; gap: 6px; padding: 8px 10px 12px; flex-wrap: wrap; margin-top: auto; }
  .empty { text-align: center; color: var(--muted); padding: 26px 8px; display: none; }
  .empty.show { display: block; }

  details summary { cursor: pointer; list-style: none; display: flex; align-items: center; justify-content: space-between; }
  details summary::-webkit-details-marker { display: none; }
  details summary::after { content: "+"; font-size: 1.4rem; color: var(--muted); transition: transform .2s ease; }
  details[open] summary::after { transform: rotate(45deg); }
  details .inner { margin-top: 14px; }

  .overlay {
    position: fixed; inset: 0; background: rgba(8, 10, 14, .55); display: flex; align-items: center;
    justify-content: center; padding: 16px; visibility: hidden; opacity: 0;
    transition: opacity .2s ease, visibility .2s ease; z-index: 10;
  }
  .overlay.open { visibility: visible; opacity: 1; }
  .sheet {
    background: var(--card); color: var(--ink); border-radius: 18px; width: min(560px, 100%);
    max-height: 90vh; overflow: auto; padding: 18px; box-shadow: 0 20px 50px rgba(0, 0, 0, .3);
    transform: translateY(14px) scale(.98); transition: transform .22s ease;
  }
  .overlay.open .sheet { transform: none; }
  .sheet img, .sheet video { width: 100%; border-radius: 12px; display: block; background: var(--line); }

  .toast {
    position: fixed; left: 50%; bottom: 22px; transform: translate(-50%, 16px); opacity: 0;
    background: var(--ink); color: var(--bg); padding: 11px 16px; border-radius: 12px; max-width: 92vw;
    transition: opacity .25s ease, transform .25s ease; pointer-events: none; z-index: 20;
  }
  .toast.show { opacity: 1; transform: translate(-50%, 0); }

  @keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
  }
</style>
</head>
<body>
<main class="wrap">
  <header>
    <h1>Upload</h1>
    <p class="muted" id="intro">Send photos and videos for your Instagram posts.</p>
  </header>

  <section class="card" aria-labelledby="new-title">
    <h2 id="new-title">Add new files</h2>
    <label class="drop" id="drop" tabindex="0">
      <input type="file" id="file" multiple accept="image/*,video/mp4,video/quicktime,video/*" hidden>
      <div class="big" aria-hidden="true">+</div>
      <strong>Choose photos or videos</strong>
      <span class="muted">or drop them here</span>
    </label>
    <div class="queue" id="queue" aria-live="polite"></div>
    <div class="fields">
      <div>
        <label class="field" for="aspect">Shape</label>
        <select id="aspect">
          <option value="auto">Original size and quality (default)</option>
          <option value="square">Square</option>
          <option value="portrait">Portrait</option>
          <option value="landscape">Landscape</option>
          <option value="keep">Original, never cropped</option>
        </select>
      </div>
      <div>
        <label class="field" for="caption-all">Caption for every file (optional)</label>
        <input type="text" id="caption-all" maxlength="2200" placeholder="You can also write a caption under each file">
      </div>
    </div>
    <div class="actions">
      <button class="btn primary" id="start" disabled>Upload</button>
      <button class="btn ghost" id="clear" hidden>Clear finished</button>
    </div>
  </section>

  <section class="card" aria-labelledby="mine-title">
    <div class="head">
      <div>
        <h2 id="mine-title">My uploads</h2>
        <p class="muted" style="margin:4px 0 0">Waiting to be posted. Open a file to see it full size.</p>
      </div>
      <button class="btn ghost small" id="refresh">Refresh</button>
    </div>
    <div class="uploads" id="uploads"></div>
    <p class="empty" id="empty">Nothing waiting yet. Files you upload appear here.</p>
  </section>

  <section class="card" aria-labelledby="settings-title">
    <details id="settings">
      <summary><h2 id="settings-title">Settings</h2></summary>
      <div class="inner">
        <label class="field" for="hours">Keep files that are not posted for (hours)</label>
        <div class="actions" style="margin-top:0">
          <input type="number" id="hours" min="1" max="720" step="1" style="max-width:160px">
          <button class="btn primary" id="save-hours">Save</button>
          <button class="btn ghost" id="reset-hours">Back to 48 hours</button>
        </div>
        <p class="muted" id="hours-note" style="margin-top:10px"></p>
      </div>
    </details>
  </section>
</main>

<div class="overlay" id="overlay">
  <div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title"></div>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
// The page is protected by the upload key: ?auth=..., kept in sessionStorage after the first visit.
const params = new URLSearchParams(location.search);
const AUTH = params.get('auth') || sessionStorage.getItem('mcp_auth') || '';
if (AUTH) sessionStorage.setItem('mcp_auth', AUTH);
const H = { 'X-Auth-Key': AUTH };
const $ = (id) => document.getElementById(id);
const DEFAULT_HOURS = 48;

// Small DOM helper. Text is always set with textContent, never as HTML.
function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

let toastTimer = 0;
function toast(message) {
  const t = $('toast');
  t.textContent = message;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3400);
}

async function api(body) {
  const r = await fetch('/api/upload', {
    method: 'POST', headers: { ...H, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 401) throw new Error('This link has no valid key. Open the upload page from your dashboard.');
    throw new Error(data.error || ('Something went wrong (' + r.status + ').'));
  }
  return data;
}

const mediaUrl = (id, what) => '/api/upload?' + what + '=' + encodeURIComponent(id) + '&auth=' + encodeURIComponent(AUTH);
const isVideo = (file) => (file.type || '').startsWith('video/') || /\.(mp4|mov|m4v)$/i.test(file.name);
const kindOf = (file) => (isVideo(file) ? 'reel' : 'photo');
const isMedia = (file) => /^(image|video)\//.test(file.type) || /\.(jpe?g|png|webp|gif|heic|mp4|mov|m4v)$/i.test(file.name);

function fmtSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
// Times from the server are in seconds.
function fmtUntil(seconds) {
  return new Date(seconds * 1000).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

// ----- choosing files and the queue -------------------------------------------------------

const queue = [];

function setState(item, state, text) {
  item.state = state;
  item.status.textContent = text;
  item.row.classList.remove('ready', 'uploading', 'done', 'failed');
  item.row.classList.add(state);
  updateButtons();
}
function setPct(item, pct) {
  item.bar.firstChild.style.width = Math.max(0, Math.min(100, pct)) + '%';
}

function renderItem(item) {
  const f = item.file;
  const thumb = isVideo(f)
    ? el('div', { class: 'thumb', text: '▶', 'aria-hidden': 'true' })
    : el('img', { class: 'thumb', src: item.preview, alt: '' });
  const remove = el('button', {
    class: 'btn ghost small', type: 'button', text: 'Remove',
    onclick: () => removeItem(item),
  });
  const caption = el('input', {
    type: 'text', maxlength: '2200', placeholder: 'Caption for this file (optional)', 'aria-label': 'Caption for ' + f.name,
    oninput: (e) => { item.caption = e.target.value; },
  });
  item.bar = el('div', { class: 'bar' }, el('i'));
  item.status = el('div', { class: 'status', text: 'Ready' });
  item.row = el('div', { class: 'item ready' },
    thumb,
    el('div', null,
      el('div', { class: 'row1' }, el('span', { class: 'name', text: f.name }),
        el('span', { class: 'muted', text: fmtSize(f.size) }), remove),
      item.bar, item.status, caption));
  $('queue').append(item.row);
}

function removeItem(item) {
  if (item.state === 'uploading') return;
  item.row.classList.add('removing');
  setTimeout(() => {
    item.row.remove();
    queue.splice(queue.indexOf(item), 1);
    if (item.preview) URL.revokeObjectURL(item.preview);
    updateButtons();
  }, 260);
}

function addFiles(files) {
  let skipped = 0;
  for (const file of files) {
    if (!isMedia(file)) { skipped += 1; continue; }
    const item = { file, state: 'ready', caption: '', preview: isVideo(file) ? '' : URL.createObjectURL(file) };
    queue.push(item);
    renderItem(item);
  }
  if (skipped) toast(skipped + (skipped === 1 ? ' file is' : ' files are') + ' not a photo or video and was skipped.');
  updateButtons();
}

function updateButtons() {
  const ready = queue.some((i) => i.state === 'ready' || i.state === 'failed');
  const finished = queue.some((i) => i.state === 'done' || i.state === 'failed');
  $('start').disabled = !ready || busy;
  $('clear').hidden = !finished || busy;
}

// ----- uploading -------------------------------------------------------------------------

// A small JPEG preview (max 512 px). Photos use the canvas; videos use the first frame.
// Failure is not fatal: the assistant can still work from the file.
async function makeThumb(file) {
  const url = URL.createObjectURL(file);
  try {
    let source, w, h;
    if (isVideo(file)) {
      source = await new Promise((resolve, reject) => {
        const v = document.createElement('video');
        v.muted = true; v.playsInline = true; v.preload = 'auto';
        v.onloadeddata = () => { v.currentTime = Math.min(0.5, (v.duration || 1) / 2); };
        v.onseeked = () => resolve(v);
        v.onerror = () => reject(new Error('video frame unreadable'));
        v.src = url;
      });
      w = source.videoWidth; h = source.videoHeight;
    } else {
      source = await createImageBitmap(file); w = source.width; h = source.height;
    }
    const scale = Math.min(1, 512 / Math.max(w, h));
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(w * scale)); c.height = Math.max(1, Math.round(h * scale));
    c.getContext('2d').drawImage(source, 0, 0, c.width, c.height);
    return await new Promise((resolve) => c.toBlob(resolve, 'image/jpeg', 0.8));
  } catch (e) {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

let busy = false;

async function uploadItem(item) {
  const f = item.file;
  const kind = kindOf(f);
  setState(item, 'uploading', 'Preparing…');
  setPct(item, 0);
  // 1. Ask the server for a safe place in storage (no secret is sent to the browser).
  const slot = await api({ action: 'begin', filename: f.name, size: f.size,
                           content_type: f.type || 'application/octet-stream', kind });
  // 2. Upload straight to storage with a short-lived token from /api/blob-token, with live progress.
  setState(item, 'uploading', 'Uploading…');
  const { upload } = await import('https://esm.sh/@vercel/blob@2.8.1/client');
  const blob = await upload(slot.pathname, f, {
    access: slot.access || 'private',
    handleUploadUrl: slot.handle_upload_url || '/api/blob-token',
    clientPayload: JSON.stringify({ key: AUTH, kind }),
    contentType: f.type || undefined,
    multipart: f.size > 20 * 1024 * 1024,
    onUploadProgress: (e) => {
      setPct(item, e.percentage);
      item.status.textContent = 'Uploading… ' + Math.round(e.percentage) + '%';
    },
  });
  // 3. A preview image, so the assistant can see the file.
  setState(item, 'uploading', 'Finishing…');
  let thumbPathname = '';
  const thumb = await makeThumb(f);
  if (thumb) {
    try {
      const ts = await api({ action: 'begin', filename: 'thumb.jpg', size: thumb.size, content_type: 'image/jpeg', kind });
      const tb = await upload(ts.pathname, thumb, {
        access: ts.access || 'private',
        handleUploadUrl: ts.handle_upload_url || '/api/blob-token',
        clientPayload: JSON.stringify({ key: AUTH, kind }),
        contentType: 'image/jpeg',
      });
      thumbPathname = tb.pathname;
    } catch (e) { thumbPathname = ''; }
  }
  // 4. Register the file with its caption and shape. The bytes never pass through the server.
  const caption = (item.caption || '').trim() || $('caption-all').value.trim();
  await api({ action: 'commit', filename: f.name, pathname: blob.pathname, url: blob.url, size: f.size,
              content_type: f.type, kind, aspect: $('aspect').value, caption, thumb_pathname: thumbPathname });
  setPct(item, 100);
  setState(item, 'done', 'Uploaded');
}

async function startAll() {
  if (busy) return;
  busy = true;
  updateButtons();
  const pending = queue.filter((i) => i.state === 'ready' || i.state === 'failed');
  let ok = 0;
  for (const item of pending) {
    try {
      await uploadItem(item);
      ok += 1;
    } catch (e) {
      setState(item, 'failed', e.message || 'Upload failed. Try again.');
    }
  }
  busy = false;
  updateButtons();
  if (ok) toast(ok === 1 ? 'Uploaded. It is in My uploads below.' : ok + ' files uploaded. They are in My uploads below.');
  loadUploads();
}

// ----- my uploads -----------------------------------------------------------------------

let uploads = [];

async function loadUploads() {
  try {
    const data = await api({ action: 'list' });
    uploads = data.uploads || [];
    $('intro').textContent = 'Send photos and videos for your Instagram posts. Files that are not posted are removed after '
      + data.retention_hours + ' hours.';
    renderUploads();
  } catch (e) {
    toast(e.message);
  }
}

function renderUploads() {
  const box = $('uploads');
  box.replaceChildren(...uploads.map(tile));
  $('empty').classList.toggle('show', uploads.length === 0);
}

function tile(u) {
  const pic = el('div', { class: 'pic' });
  if (u.has_thumb) pic.append(el('img', { src: mediaUrl(u.id, 'thumb'), alt: '', loading: 'lazy' }));
  else pic.append(el('span', { text: u.kind === 'reel' ? '▶' : '🖼', 'aria-hidden': 'true' }));
  return el('article', { class: 'tile', 'data-id': u.id },
    pic,
    el('div', { class: 'tbody' },
      el('div', { class: 'tname', text: u.title || u.filename }),
      el('div', { class: 'tmeta', text: (u.kind === 'reel' ? 'Video' : 'Photo') + ' · ' + fmtSize(u.size) }),
      el('div', { class: 'tmeta', text: 'Keep until ' + fmtUntil(u.expires_at) })),
    el('div', { class: 'tacts' },
      el('button', { class: 'btn ghost small', type: 'button', text: 'View', onclick: () => openView(u) }),
      el('button', { class: 'btn ghost small', type: 'button', text: 'Rename', onclick: () => openRename(u) }),
      el('button', { class: 'btn danger small', type: 'button', text: 'Delete', onclick: () => openDelete(u) })));
}

// ----- dialogs ----------------------------------------------------------------------------

function openSheet(children) {
  $('sheet').replaceChildren(...children);
  $('overlay').classList.add('open');
  const first = $('sheet').querySelector('input, button');
  if (first) setTimeout(() => first.focus(), 60);
}
function closeSheet() {
  $('overlay').classList.remove('open');
}
$('overlay').addEventListener('click', (e) => { if (e.target === $('overlay')) closeSheet(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });

function openView(u) {
  const media = u.kind === 'reel'
    ? el('video', { src: mediaUrl(u.id, 'file'), controls: true, playsinline: true, preload: 'metadata' })
    : el('img', { src: mediaUrl(u.id, 'file'), alt: u.title || u.filename });
  const fallback = el('p', { class: 'muted', text: 'This file is too big to open here. Its preview is shown instead.' });
  const preview = u.has_thumb ? el('img', { src: mediaUrl(u.id, 'thumb'), alt: '' }) : null;
  media.addEventListener('error', () => {
    media.replaceWith(...[fallback, preview].filter(Boolean));
  });
  openSheet([
    el('h3', { id: 'sheet-title', text: u.title || u.filename }),
    media,
    u.caption ? el('p', { class: 'muted', text: 'Caption: ' + u.caption, style: 'margin-top:12px' }) : null,
    el('div', { class: 'actions' }, el('button', { class: 'btn ghost', type: 'button', text: 'Close', onclick: closeSheet })),
  ]);
}

function openRename(u) {
  const input = el('input', { type: 'text', maxlength: '120', value: u.title || u.filename, 'aria-label': 'New name' });
  const save = el('button', { class: 'btn primary', type: 'button', text: 'Save', onclick: async () => {
    try {
      await api({ action: 'rename', id: u.id, title: input.value });
      closeSheet();
      toast('Renamed.');
      loadUploads();
    } catch (e) { toast(e.message); }
  } });
  openSheet([
    el('h3', { id: 'sheet-title', text: 'Rename' }),
    el('p', { class: 'muted', text: 'This only changes the name shown here. The file itself stays the same.' }),
    input,
    el('div', { class: 'actions' }, save, el('button', { class: 'btn ghost', type: 'button', text: 'Cancel', onclick: closeSheet })),
  ]);
  input.select();
}

function openDelete(u) {
  const confirm = el('button', { class: 'btn danger', type: 'button', text: 'Delete', onclick: async () => {
    try {
      await api({ action: 'delete', id: u.id });
      closeSheet();
      toast('Deleted.');
      loadUploads();
    } catch (e) { toast(e.message); }
  } });
  openSheet([
    el('h3', { id: 'sheet-title', text: 'Delete this file?' }),
    el('p', { class: 'muted', text: (u.title || u.filename) + ' will be removed from storage. This cannot be undone.' }),
    el('div', { class: 'actions' }, confirm, el('button', { class: 'btn ghost', type: 'button', text: 'Keep it', onclick: closeSheet })),
  ]);
}

// ----- settings ---------------------------------------------------------------------------

async function loadSettings() {
  try {
    const d = await api({ action: 'settings' });
    $('hours').value = d.retention_hours;
    $('hours-note').textContent = 'Right now files stay for ' + d.retention_hours + ' hours. The default is ' + d.default_hours + '.';
  } catch (e) {
    $('hours-note').textContent = e.message;
  }
}

async function saveHours(value) {
  try {
    const d = await api({ action: 'settings_save', retention_hours: value });
    $('hours').value = d.retention_hours;
    $('hours-note').textContent = 'Saved. Files now stay for ' + d.retention_hours + ' hours.';
    toast('Saved.');
    loadUploads();
  } catch (e) {
    $('hours-note').textContent = e.message;
  }
}

$('save-hours').addEventListener('click', () => saveHours(Number($('hours').value)));
$('reset-hours').addEventListener('click', () => { $('hours').value = DEFAULT_HOURS; saveHours(DEFAULT_HOURS); });

// ----- wiring -------------------------------------------------------------------------------

const drop = $('drop');
drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('file').click(); } });
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); addFiles(e.dataTransfer.files); });
$('file').addEventListener('change', (e) => { addFiles(e.target.files); e.target.value = ''; });
$('start').addEventListener('click', startAll);
$('clear').addEventListener('click', () => {
  for (const item of queue.filter((i) => i.state === 'done' || i.state === 'failed')) {
    item.row.remove();
    if (item.preview) URL.revokeObjectURL(item.preview);
  }
  for (let i = queue.length - 1; i >= 0; i -= 1) {
    if (queue[i].state === 'done' || queue[i].state === 'failed') queue.splice(i, 1);
  }
  updateButtons();
});
$('refresh').addEventListener('click', loadUploads);

if (!AUTH) {
  $('intro').textContent = 'This page needs its key. Open it from your dashboard.';
  $('start').disabled = true;
} else {
  loadSettings();
  loadUploads();
}
</script>
</body>
</html>
"""
