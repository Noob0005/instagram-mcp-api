# Deploy the Instagram MCP server to Vercel

What you get: `https://<project>.vercel.app/mcp?auth=<MCP_AUTH_KEY>` — the full
MCP server (all 78 tools) over Streamable HTTP, gated by your auth key.
`/healthz` stays open for uptime checks.

## 0. How it works (read first)

- The function runs FastMCP in **stateless HTTP** mode (`stateless_http=True`),
  because Vercel instances have no persistent disk and no ASGI lifespan — this
  app starts FastMCP's lifespan lazily on the first request.
- `instagram_mcp_server` is **vendored** into `vercel-api/_vendor/` by
  `sync_package.ps1`. Re-run it after every change to the package.
- Auth accepts `?auth=KEY`, `Authorization: Bearer KEY`, or `X-Auth-Key KEY`
  (constant-time comparison). Without a valid key every request returns 401.

## 1. One-time prep

```powershell
cd d:\instagram-mcp-master\vercel-api
.\sync_package.ps1                                   # vendor the current package

cd d:\instagram-mcp-master
.\.venv\Scripts\python.exe scripts\export_session_json.py > session.json
# ^ one line of JSON = your saved login session. Treat it like a password.
```

## 2. Deploy

### Option A — Vercel CLI (fastest)

```powershell
npm i -g vercel
cd d:\instagram-mcp-master\vercel-api
vercel                                                   # first run: create/link the project
vercel env add MCP_AUTH_KEY production                   # paste a LONG random key (32+ chars)
vercel env add INSTAGRAM_MCP_SESSION_JSON production     # paste the session.json line
vercel --prod
```

### Option B — GitHub integration

1. Push this repo to GitHub.
2. Vercel → **Add New… → Project** → import the repo.
3. **Root Directory → `vercel-api`** (important — the folder is self-contained).
4. Settings → Environment Variables:
   - `MCP_AUTH_KEY` = long random string (e.g. `openssl rand -hex 24`)
   - `INSTAGRAM_MCP_SESSION_JSON` = the one-line JSON from step 1
5. Deploy → your endpoint is `https://<project>.vercel.app/mcp?auth=<MCP_AUTH_KEY>`

## 3. Client configuration

```json
{
  "mcpServers": {
    "instagram-control": {
      "url": "https://<project>.vercel.app/mcp?auth=<MCP_AUTH_KEY>"
    }
  }
}
```

Claude Code:

```bash
claude mcp add --transport http instagram-control "https://<project>.vercel.app/mcp?auth=<MCP_AUTH_KEY>"
```

Sanity check: open `https://<project>.vercel.app/healthz` → `{"status":"ok",...}`.

## 4. Environment variables

| Var | Required | Purpose |
| --- | --- | --- |
| `MCP_AUTH_KEY` | ✅ | protects every tool call, the `/upload` page and `/api/upload` |
| `BLOB_READ_WRITE_TOKEN` | ✅ | Vercel Blob token (Storage → Blob → Connect — Vercel injects it automatically). Powers the persistent session store, the upload staging area, the uploads index and the problem log |
| `SESSION_ENCRYPTION_KEY` | ✅ | Fernet key encrypting the session in Blob. Generate: `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `CRON_SECRET` | ✅ | authenticates the daily cleanup cron (Vercel sends it as `Authorization: Bearer`) |
| `INSTAGRAM_MCP_SESSION_JSON` | – | **first-time seed only**: used once when Blob has no session yet, then written to Blob and ignored afterwards (redeploys keep the rotated Blob session) |
| `INSTAGRAM_MCP_SESSION_NAME` | – | session file name in Blob (`sessions/<name>.json`), default `default` |
| `INSTAGRAM_MCP_BLOB_PREFIX` | – | top-level Blob key prefix, default `instagram-mcp` |
| `INSTAGRAM_MCP_UPLOAD_TTL_DAYS` | – | days before unposted uploads are purged by the cron, default `7` |
| `INSTAGRAM_MCP_MAX_UPLOAD_BYTES` | – | size gate on `/upload`, default `268435456` (256 MB) |
| `INSTAGRAM_MCP_DEDUPE_WINDOW` | – | retry-duplicate suppression (default 600 s) |
| `INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR` / `…WRITES_PER_DAY` / `…RED_ACTIONS_PER_DAY` | – | your usual safety caps |
| `INSTAGRAM_MCP_*_DELAY_*` | – | delay overrides — **keep them small here** (see caveats) |
| `INSTAGRAM_MCP_PASSWORD` | ⛔ avoid | on cold starts every login would look like a brand-new device |

### Session storage in Blob

The Instagram session (instagrapi settings JSON) is stored encrypted in Vercel
Blob at `<prefix>/sessions/<name>.json`. On cold start the server reads it from
Blob; whenever Instagram rotates the session (login, sessionid login, 2FA,
challenge) the new settings are written straight back. The
`INSTAGRAM_MCP_SESSION_JSON` env var is only a first-time seed — after the
initial write the env var is never consulted again, so redeploys no longer
clobber a rotated session. Without `BLOB_READ_WRITE_TOKEN` the server falls
back to the local session-file behaviour (desktop / Termux).

### Upload page (`/upload`) + Blob staging

`https://<project>.vercel.app/upload?auth=<MCP_AUTH_KEY>` — same auth gate as
the MCP endpoint. Pick a file, enter caption / aspect ratio / photo-or-reel;
the browser posts the bytes **directly to Vercel Blob**, which skips the
~4.5 MB serverless request-body limit. The file plus its metadata land in the
uploads index (`<prefix>/uploads/index.json`).

New MCP tools for the staging queue:

| Tool | What it does |
| --- | --- |
| `list_uploads` | pending files with captions, sizes, kind, status |
| `preview_upload` | returns a small JPEG thumbnail as an image (no URL fetching needed); text summary for reels |
| `post_upload` | downloads the staged file, validates & converts it, publishes to Instagram, deletes the Blob copy on success |
| `delete_upload` | removes a staged file from Blob without posting |
| `list_problems` | rejected files and why (bad format, failed post, etc.) |

Validation/conversion happens on the server: photos are converted to a
feed-ready JPEG at the requested aspect via Pillow (same pipeline as normal
posting). Reels must be MP4 (H.264 video + AAC audio) — Vercel has no ffmpeg,
so `.mov`/`.webm`/other containers are **rejected and logged** in the problem
log rather than converted. Cleanup: the Blob copy is deleted after a
successful post, and a daily cron (`vercel.json` → `/api/cleanup`, 04:00 UTC)
purges uploads older than `INSTAGRAM_MCP_UPLOAD_TTL_DAYS` (default 7) that
were never posted.

## 5. Security (very important)

- **The URL is a credential.** Anyone with `…/mcp?auth=KEY` can post, comment,
  DM and delete on your Instagram account. Don't share links/screenshots —
  Vercel and any proxy may log request paths/query strings.
- Use a long random key, and **rotate** it (change `MCP_AUTH_KEY`, redeploy) if it leaks.
- Prefer the `Authorization: Bearer` header when your client supports headers.
- Consider Vercel Deployment Protection / a custom domain + WAF for extra safety.
- Never set `MCP_ALLOW_UNAUTHENTICATED=1` on a public deployment.

## 6. Serverless caveats (by design)

- **State:** with `BLOB_READ_WRITE_TOKEN` set, the session and the upload
  staging area persist in Vercel Blob across cold starts and redeploys.
  Daily counters, dedupe records and the scheduling queue still live in
  `/tmp`, per instance; a cold start resets them. Caps are therefore
  best-effort here — keep activity low and occasional.
- **Function time limit:** `maxDuration: 60` in `vercel.json`. Default delays fit
  (posts ≤ 40 s). **Don't enable `INSTAGRAM_MCP_SAFE_MODE` here** — its 5–15 min
  post delays would exceed the limit. Use a VPS for long-delay Safe Mode.
- **No scheduler:** `scripts/run_scheduler.py` can't run on Vercel, and the queue
  is ephemeral — keep scheduled posting on your local machine / Task Scheduler.
- Cold start adds ~1–3 s; the first tool call also pays FastMCP's lifespan init.
- If the session expires, re-export `session.json` and update the env var.

## 7. Troubleshooting

| Symptom | Fix |
| --- | --- |
| 401 unauthorized | Wrong/missing `?auth=`; make sure the env var exists for **Production** |
| 500 server_misconfigured | `MCP_AUTH_KEY` missing in that environment |
| 500 lifespan_init_failed | Re-run `sync_package.ps1`, redeploy; report the detail text if it persists |
| 404 on /mcp | Root Directory not set to `vercel-api` |
| Tool timeouts | Lower delay env vars so each call stays well under 60 s |
| "Not logged in" | `INSTAGRAM_MCP_SESSION_JSON` missing/expired → re-export and update |

All the local guardrails still apply remotely: pacing, duplicate suppression,
delete approvals, risk categories and the hourly/daily caps.
