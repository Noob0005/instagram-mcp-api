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
10. [ ] AI behaviour: when asked to upload a photo/video, give the login URL + /upload page, never try chat upload.
11. [ ] Dashboard UI redesign: old-CRT effect, green/cyan/red/white accents, responsive desktop + mobile.
12. [ ] Upload pipeline: fix /api/upload 405 + /healthz routing (needs user's Network-tab / curl output).
13. [ ] Browser-made thumbnails (canvas for photos, first video frame for reels) + set_upload_caption tool.
Chat attachments are NOT sent to the server (sandbox can't reach Vercel; base64 too big). Use upload page.
Other: uploads index read-modify-write race; Termux pydantic fix unconfirmed; photo/GIF comments blocked upstream.

## 7. Commands
- Tests (offline): `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests` (137 tests, all pass; needs `pip install fastmcp instagrapi pillow requests cryptography vercel`)
- Local dashboard: `uvicorn --app-dir vercel-api/api main:app --port 8765` (+ Playwright/Chromium in /opt/pw-browsers)
- Local server: `python -m instagram_mcp_server` | `python scripts/serve.py --host 0.0.0.0 --port 8080`

## Progress Log (fold into §5/§6 when done — keep SHORT)
- 2026-10-10: Endpoint tester now uses dashboard key by default (23 admin tests pass).
- 2026-10-10: Step 7 done: README rewritten.
- 2026-10-10: Step 6 done: URL reels validated as MP4 (137 tests). Step 5 skipped.
- 2026-10-10: Step 4 done: untracked .pyc files.
- 2026-10-10: Step 3 done: relogin cooldown treated fresh container (monotonic<300s) as throttled; fixed.
- 2026-10-10: Dashboard + Blob repair done and pushed; CONTEXT.md rewritten (rules 6/7, §4b, roadmap).
