# CONTEXT.md — Instagram MCP Server (read this FIRST)

> ## STRICT RULE FOR ALL AI AGENTS (MANDATORY)
> 1. **After EVERY code change**, append/update the `## Progress Log` section at the
>    bottom of THIS file: date, what changed, which files, test result.
> 2. When a task finishes, **fold its progress entries** into `## Done` (1 line each)
>    and **delete the verbose progress lines** so this file stays lean.
> 3. Keep `## Remaining / Known Issues` current: add new items, remove fixed ones.
> 4. NEVER let this file grow past ~250 lines. Summarize, don't append endlessly.
> 5. A new AI session must be able to resume work by reading ONLY this file
>    (+ the file it is about to edit). Do NOT re-read the whole codebase.
> 6. **WORK STYLE (user's standing request): ONE roadmap step at a time.** Finish it,
>    test, commit, push, report in a few lines, then STOP and wait. Never batch several
>    steps in one turn. Keep replies and tool output short: grep / Read line ranges
>    instead of whole files. This avoids hitting usage limits.
> 7. Hygiene: `export PYTHONDONTWRITEBYTECODE=1`; never commit `__pycache__`/`.pyc`;
>    after editing `instagram_mcp_server/` run `bash vercel-api/sync_package.sh` and commit
>    `vercel-api/_vendor/`; push with `git fetch --depth=1 origin main; git push origin main`.
>    Claude's sandbox cannot reach vercel.com / blob / instagram.com: real deploy checks are the user's.

## 1. What this project is
Local-first **Model Context Protocol (MCP) server for full Instagram account control**
via AI agents. Built with **FastMCP + instagrapi (private API)**. 104 tools: posting
(local file/URL/base64/inbox), stories, reels, DMs (text/photo/video), comments +
replies, likes, follows, discovery, notes, scheduling queue, risk/safety guardrails.
Transports: **stdio** (default), **Streamable HTTP `/mcp`**, **legacy SSE `/sse`**.
Runs on Windows / Linux / macOS / Termux (Android).

## 2. Tech / versions (verified)
- Python `>=3.10`. Deps: `fastmcp>=3.0.0,<5`, `instagrapi>=2.18,<4`
  (3.x default; **Termux must use 2.x** — `curl_cffi` has no Android wheels),
  `pillow>=10`, `requests>=2.31`. Server also uses `uvicorn` for `scripts/serve.py`.
- `instagram_mcp_server/mcp_server.py` (~165 KB, **104 `@mcp.tool()`**), 105 unit tests
  in `tests/test_helpers.py` (offline/hermetic, ~0.5 s, must make ZERO network calls).
- Code has a 2.x/3.x compat layer: `_search_locations_by_name()` (prefers 3.x
  `location_search_name`, falls back to 2.x `location_search(name)`), plus guards for
  `story_delete`, `media_edit` usertags, `extra_data`, dict-vs-list
## 3. File map (only these ship to GitHub)
```
instagram_mcp_server/   mcp_server.py (all tools), instagram_client.py (auth/session),
                        __main__.py (CLI: --transport/--host/--port/--path),
                        __init__.py, py.typed
scripts/                setup.py (interactive installer, Termux-aware), serve.py
                        (auth-gated HTTP: /mcp + /inbox upload page + /healthz),
                        save_image.py, watch_clipboard.py, run_scheduler.py,
                        export_session_json.py, extract_sessionid.py,
                        run_http/sse .cmd/.sh
tests/test_helpers.py   105 offline unit tests (mock Client, temp .env/session)
start.cmd / start.sh    venv bootstrap -> scripts/setup.py (menu: Start / Change setup)
mcp_server.py, instagram_client.py (root) — thin shims, NOT real code
pyproject.toml, requirements.txt, LICENSE, MANIFEST.in
README.md, SETUP_SSE_HTTP.md, CONTEXT.md (this file)
vercel-api/             SERVERLESS DEPLOYMENT (see §4b): api/ (main.py dispatcher, upload.py,
                        blob-token.js, cleanup.py, mcp_server_asgi.py), admin_ui/ (dashboard),
                        public/upload.html, vercel.json, requirements.txt, package.json,
                        sync_package.sh. _vendor/ = synced copy of instagram_mcp_server (commit it).
instagram_mcp_server/   also: blob_store.py, session_store.py, upload_store.py, media_validation.py
```
EXCLUDE from bundle: `.venv/`, `__pycache__/`, `dist/`, `build/`, `*.egg-info/`,
`.env*`, `*.log`, `logs/`, `photos/`, `*.zip`, `vercel-api/_vendor/`.

## 4. Key behaviors an AI must know
- **Login chain**: saved session (`~/.instagram_mcp_session.json`) → cookie
  `INSTAGRAM_MCP_SESSIONID` → username+password fallback (5-min re-login throttle;
  Safe Mode 30 min). Session file chmod 0600. 2FA via `instagram_complete_2fa`,
  challenge via `challenge_code_handler` in `instagram_client.py`.
- **Image intake (4 ways)**: absolute path, http(s) URL, base64/`data:` URI
  (`instagram_upload_image`, chat-size ~300 KB), inbox folder
  (`~/instagram-mcp-inbox`, `instagram_inbox_status`, `"latest"`). Browser upload at
  `/inbox?auth=KEY` via `serve.py`; `save_image.py` (clipboard→inbox),
- **Framing**: `aspect=auto|portrait(4:5→1080×1350)|square|landscape|keep`;
  EXIF-rotate, alpha→white JPEG, ≤8 MB. `dry_run=True` previews caption/framing.
  `instagram_inspect_image` previews without login.
- **Safety guardrails**: per-class pacing + jitter, 10 comments/hr, daily write cap,
  red-action cap, 10-min duplicate suppression (disk-persisted), auto-pause on
  rate-limit, red/orange/green risk prefixes, `instagram_get_risk_categories`.
  **Deletes/unsends need preview→confirm** (preview ≤10 min old).
- **Upload link is domain-agnostic**: `/inbox` = MCP URL with `/mcp`→`/inbox`
  (`serve._origin()` uses Host + X-Forwarded headers). Never hardcode IPs.
- **Server instructions** (FastMCP `instructions=`) teach the model the image flow,
  dry-run→approve→publish, reply-by-username, delete-approval, pacing, risk map.
- **Photo/GIF comments are NOT possible**: instagrapi 3.0.20 `media_comment()` is
  text-only; no library implements the undocumented attachment payload. Do NOT guess it.

## 4b. Vercel deployment (vercel-api/, region bom1)
- Routes (vercel.json): `/` & `/admin` dashboard, `/upload` page, `/mcp` MCP, `/healthz`;
  all go through `api/main.py` (admin -> upload -> cleanup -> mcp ASGI). Don't name a file `api/mcp.py`.
- Dashboard (`admin_ui/`): login (ADMIN_USERNAME/PASSWORD else MCP key), env checklist,
  copyable MCP URL, endpoint tester, Instagram session form (cookie/password/2FA/challenge). Dark terminal theme.
- Storage: PRIVATE Vercel Blob via official `vercel` SDK (`blob_store.py`). Session Fernet-encrypted at
  `<prefix>/sessions/<name>.json`. Uploads: browser -> Blob directly using short-lived token from
  `api/blob-token.js` (never exposes BLOB_READ_WRITE_TOKEN), then `/api/upload commit`.
- MCP tools added: list_uploads, preview_upload, post_upload (deletes Blob after posting),
  delete_upload, list_problems. Cron `/api/cleanup` daily 04:00 purges uploads >7 days.
- Env tiers: required MCP_AUTH_KEY, BLOB_READ_WRITE_TOKEN, SESSION_ENCRYPTION_KEY (Fernet 44-char b64, NOT hex),
  CRON_SECRET; recommended ADMIN_USERNAME/PASSWORD; rest optional. Never set MCP_ALLOW_UNAUTHENTICATED.
- Hobby limits: maxDuration 60 s, daily cron only, Blob 1 GB. Counters/dedupe/queue still in /tmp (ephemeral).

## 5. Done (1 line each)
- 104 tools, auth chain, guardrails, image pipeline, installers (local project; 105 original tests).
- Vercel: dispatcher, Blob-backed encrypted session, upload page + client tokens, validation/conversion,
  new upload tools, cleanup cron, admin dashboard (PR merged + repaired). 134 tests total.
- Blob layer rewritten on real SDK (overwrite=True); token leak closed; .gitignore bytecode rules.

## 6. ROADMAP / Remaining (do ONE step per turn, in order)
1. [x] Dashboard.  2. [x] Blob repair + token leak fix.
3. [x] Fixed 2 failing tests (monotonic-clock bug in _try_env_relogin; all 134 pass).
4. [x] Removed 14 tracked .pyc files from git.
5. [skipped by user] Upstash Redis (env KV_REST_API_URL/TOKEN) for counters/dedupe/queue; add to dashboard checklist.
6. [x] Reels from a public URL: must be real MP4 (H.264+AAC) or rejected with an error (`_reject_non_mp4`, tests/test_reel_url.py). No ffmpeg on Vercel; local-path reels unchanged.
7. [x] Rewrote vercel-api/README.md (dashboard-first setup, env tiers, reels rules, troubleshooting).
8. [ ] USER: create Private Blob store, GEN a valid Fernet key in dashboard, redeploy, add IG session in
       dashboard, run endpoint tester, test upload + post_upload on a SECONDARY account; report errors.
9. [ ] Dashboard endpoint tester uses the dashboard's MCP key by default (DONE in progress; verify live).
10. [x] AI instructions: for user photos/videos, send them to the /upload page (dashboard link), never base64 from chat.
11. [x] Dashboard UI redesign: CRT scanlines/flicker/roll bar, green/cyan/red/white palette, 2 columns on desktop, single column on phones (checked with Playwright at 1280 and 390px).
12. [~] Routing fixed: /healthz and /upload now reach the right handler via ?route= (rewrite replaced the path). /upload page now needs ?auth=. Still open: /api/upload 405 (needs Network-tab details).
13. [x] Browser-made thumbnails (canvas photos / first video frame for reels) stored as thumb_pathname; preview_upload uses it; set_upload_caption tool. 140 tests.
14. [x] Dashboard regrouped: collapsible env groups (required/recommended open, optional/danger collapsed), SHOW/COPY only for MCP_AUTH_KEY and SESSION_ENCRYPTION_KEY, configured extension download on the dashboard (admin=extension, keys filled in), public keyless zip link kept. Verified with Playwright at 1280 and 390px.
15. [ ] USER: redeploy, download the configured extension from the dashboard, load it unpacked in Chrome, log into instagram.com, press SYNC NOW, report errors (Firefox temporary add-on flow too).
16. [x] Carousel from /upload photos: post_upload_album(upload_ids, caption, dry_run). Photos only; every photo is validated before anything posts; Blob copies deleted on success. 168 tests pass.
17. [x] Dashboard redesign: Home overview + section cards; Connect, Environment, Instagram and Tests each on their own page (hash routing). Checked with Playwright at 1280 and 390px.
18. [x] Extension autosync: loading an instagram.com tab syncs the sessionid in the background, at most once per interval (failed attempts retry after 10 min). Interval prompt and notification permission removed. 178 tests pass.
19. [ ] USER: reinstall the extension (or reload it) and open instagram.com; check the options page shows a last sync time.
20. [ ] Carousel with per-slide AI images: confirm the image step and where the images are generated.
LESSON: anything read from disk at runtime must be inside a .py module (Vercel bundles only .py/imports). Verify deployed paths, not local ones.
Chat attachments are NOT sent to the server (sandbox can't reach Vercel; base64 too big). Use upload page.
Other: uploads index read-modify-write race; Termux pydantic fix unconfirmed; photo/GIF comments blocked upstream.

## 7. Commands
- Tests (offline): `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests` (137 tests, all pass; needs `pip install fastmcp instagrapi pillow requests cryptography vercel`)
- Local dashboard: `uvicorn --app-dir vercel-api/api main:app --port 8765` (+ Playwright/Chromium in /opt/pw-browsers)
- Local server: `python -m instagram_mcp_server` | `python scripts/serve.py --host 0.0.0.0 --port 8080`

## Progress Log (fold into §5/§6 when done — keep SHORT)
- 2026-10-19: Dashboard routes: admin-only pre-configured extension zip (admin=extension) and secret reveal for MCP_AUTH_KEY/SESSION_ENCRYPTION_KEY only (admin=secret).
- 2026-10-19: Extension: defaults.json applied on install (pre-configured zip); build_extension.py regenerates public zip + admin_ui/extension_files.py. Run it after editing public/extension.
- 2026-10-19: Browser extension (Chrome + Firefox) in vercel-api/public/extension with zip + README; dashboard link; cross-language Fernet test. Sync prompt at most once per interval.
- 2026-10-19: Browser extension plan step 1 done: POST /api/session-sync (Fernet payload, MCP key auth, reuses dashboard cookie login). 148 tests.
- 2026-10-10: Upload page was read from public/ at runtime, which Vercel does not bundle (upload_page_missing). Now embedded in admin_ui/upload_page.py; public/upload.html removed.
- 2026-10-10: Step 11 done: dashboard redesign (140 tests pass).
- 2026-10-10: Step 13 done: thumbnails + set_upload_caption (140 tests). Steps 10, 12 done.
- 2026-10-10: Endpoint tester now uses dashboard key by default (23 admin tests pass).
- 2026-10-10: Step 7 done: README rewritten.
- 2026-10-10: Step 6 done: URL reels validated as MP4 (137 tests). Step 5 skipped.
- 2026-10-10: Step 4 done: untracked .pyc files.
- 2026-10-10: Step 3 done: relogin cooldown treated fresh container (monotonic<300s) as throttled; fixed.
- 2026-10-10: Dashboard + Blob repair done and pushed; CONTEXT.md rewritten (rules 6/7, §4b, roadmap).
- 2026-10-19: Dashboard rebuilt (admin_ui/page.py): grouped env checklist with collapsible sections, reveal for the two secrets, configured extension download on the dashboard. 159 tests pass.
- 2026-10-19: Carousel of staged photos via post_upload_album (mcp_server.py, _vendor synced). 168 tests pass.
- 2026-10-19: Dashboard split into pages (Home, Connect, Environment, Instagram, Tests). 168 tests pass.
- 2026-10-20: Extension autosync on instagram.com (tests/test_extension_autosync.py runs the real background.js in Node). 178 tests pass.
- 2026-10-28: Upload retention: 48 h default, saved in Blob (upload_settings.py), cron + purge use it; upload API actions settings / settings_save. Fixed shared-list bug in local upload index defaults. 200 tests pass.
- 2026-10-28: Upload page rebuilt (per-file progress, My uploads with view/rename/delete, retention settings). API: list, rename, delete, GET thumb/file reads. 214 tests pass.
- 2026-10-28: upload_from_url MCP tool (instagram_mcp_server/url_upload.py): server downloads a link into Blob, returns id + preview image; falls back to page/thumbnail preview when the file is blocked. Public-address check on every hop. 236 tests pass.
