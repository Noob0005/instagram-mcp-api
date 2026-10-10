"""The browser upload page, embedded as a string so it ships inside the function.

Vercel only bundles .py files, so a file read from public/ at runtime is missing
in production (that caused the upload_page_missing error).
"""

UPLOAD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Upload to Instagram MCP</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.3rem; }
  .card { border: 1px solid #8884; border-radius: 12px; padding: 1rem; display: grid; gap: .75rem; }
  label { font-weight: 600; font-size: .9rem; }
  input, select, textarea { width: 100%; box-sizing: border-box; padding: .5rem; border-radius: 8px; border: 1px solid #8886; font: inherit; }
  textarea { min-height: 90px; }
  button { padding: .6rem 1rem; border: 0; border-radius: 8px; background: #e1306c; color: #fff; font: inherit; font-weight: 600; cursor: pointer; }
  button:disabled { opacity: .5; cursor: default; }
  #status { white-space: pre-wrap; font-size: .9rem; }
  .row { display: flex; gap: .75rem; }
  .row > div { flex: 1; }
  .hint { font-size: .8rem; opacity: .7; }
</style>
</head>
<body>
<h1>📤 New upload</h1>
<div class="card">
  <div>
    <label for="file">Photo or video</label>
    <input type="file" id="file" accept="image/*,video/mp4,video/quicktime,video/*">
    <div class="hint">Files go straight from your browser to Vercel Blob — no size limit.</div>
  </div>
  <div class="row">
    <div>
      <label for="kind">Type</label>
      <select id="kind">
        <option value="photo">Photo (feed post)</option>
        <option value="reel">Reel (video)</option>
      </select>
    </div>
    <div>
      <label for="aspect">Aspect ratio</label>
      <select id="aspect">
        <option value="auto">Auto (keep, crop if out of range)</option>
        <option value="square">Square 1:1</option>
        <option value="portrait">Portrait 4:5</option>
        <option value="landscape">Landscape 1.91:1</option>
        <option value="keep">Keep original (no crop)</option>
      </select>
    </div>
  </div>
  <div>
    <label for="caption">Caption</label>
    <textarea id="caption" placeholder="Stored with the file — the assistant posts it verbatim"></textarea>
  </div>
  <button id="go">Upload</button>
  <div id="status"></div>
</div>

<script>
// The page is served by the same function that serves /mcp and is protected by
// the MCP_AUTH_KEY gate (?auth=..., Bearer header, or X-Auth-Key). We reuse the
// auth that loaded the page for the JSON registration call.
const params = new URLSearchParams(location.search);
const AUTH = params.get('auth') || sessionStorage.getItem('mcp_auth') || '';
if (AUTH) sessionStorage.setItem('mcp_auth', AUTH);
const H = { 'X-Auth-Key': AUTH };
const statusEl = document.getElementById('status');
const say = (m) => { statusEl.textContent = m; };

async function jpost(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { ...H, 'Content-Type': 'application/json' },
                               body: JSON.stringify(body) });
  if (!r.ok) throw new Error((await r.text().catch(() => '')) || r.status + ' ' + r.statusText);
  return r.json();
}

// Small JPEG preview (max 512px) made in the browser: photos via the canvas, reels via the
// first video frame. The assistant looks at this to write captions. Returns null on failure.
async function makeThumb(file, kind) {
  const url = URL.createObjectURL(file);
  try {
    let source, w, h;
    if (kind === 'reel') {
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

document.getElementById('go').addEventListener('click', async () => {
  const f = document.getElementById('file').files[0];
  if (!f) return say('Pick a file first.');
  const kind = document.getElementById('kind').value;
  const aspect = document.getElementById('aspect').value;
  const caption = document.getElementById('caption').value;
  const btn = document.getElementById('go'); btn.disabled = true;
  try {
    // 1. Ask the server for a safe Blob pathname (no token is ever sent to the browser here).
    say('Preparing upload…');
    const slot = await jpost('/api/upload', { action: 'begin', filename: f.name,
                                              size: f.size, content_type: f.type, kind });
    // 2. Upload straight to Blob with a short-lived, single-file token from /api/blob-token.
    say('Uploading straight to Blob…');
    const { upload } = await import('https://esm.sh/@vercel/blob@2.8.1/client');
    const blob = await upload(slot.pathname, f, {
      access: slot.access || 'private',
      handleUploadUrl: slot.handle_upload_url || '/api/blob-token',
      clientPayload: JSON.stringify({ key: AUTH, kind }),
      contentType: f.type || undefined,
      multipart: f.size > 20 * 1024 * 1024,
      onUploadProgress: (e) => say('Uploading… ' + Math.round(e.percentage) + '%'),
    });
    const pathname = blob.pathname, url = blob.url;
    // 2b. Optional preview thumbnail. Failure is not fatal: the server can make one for photos.
    let thumbPathname = '';
    say('Making preview…');
    const thumb = await makeThumb(f, kind);
    if (thumb) {
      try {
        const tslot = await jpost('/api/upload', { action: 'begin', filename: 'thumb.jpg',
                                                   size: thumb.size, content_type: 'image/jpeg', kind });
        const tb = await upload(tslot.pathname, thumb, {
          access: tslot.access || 'private',
          handleUploadUrl: tslot.handle_upload_url || '/api/blob-token',
          clientPayload: JSON.stringify({ key: AUTH, kind }),
          contentType: 'image/jpeg',
        });
        thumbPathname = tb.pathname;
      } catch (e) { thumbPathname = ''; }
    }
    // 3. Register metadata only — the bytes never touch the serverless function.
    say('Registering…');
    await jpost('/api/upload', { action: 'commit', filename: f.name, pathname, url,
                                 size: f.size, content_type: f.type, kind, aspect, caption,
                                 thumb_pathname: thumbPathname });
    say('✅ Uploaded! Tell the assistant to run list_uploads — it will see this file with its caption.');
    document.getElementById('caption').value = '';
  } catch (e) {
    say('❌ ' + e.message);
  } finally { btn.disabled = false; }
});
</script>
</body>
</html>
"""
