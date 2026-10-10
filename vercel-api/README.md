# Instagram MCP server on Vercel

Serverless deployment of the Instagram MCP server. No PC has to stay on.

- **MCP endpoint:** `https://<project>.vercel.app/mcp?auth=<MCP_AUTH_KEY>` — every tool
  from `instagram_mcp_server`, over Streamable HTTP.
- **Dashboard:** `https://<project>.vercel.app/` — login, environment-variable checklist,
  copyable MCP URL, endpoint tester, and an Instagram session form.
- **Upload page:** `https://<project>.vercel.app/upload` — send photos/reels straight to Blob,
  then ask the AI to preview and post them.
- **Health check:** `/healthz` (open, no tool access).

## 1. Deploy

1. Push this repo to GitHub.
2. Vercel → **Add New… → Project** → import the repo.
3. **Root Directory → `vercel-api`** (the folder is self-contained).
4. **Region:** in Project Settings → Functions, set the function region to Mumbai (`bom1`).
5. **Storage → Blob → Connect** to this project. Vercel adds `BLOB_READ_WRITE_TOKEN`.
   Use a **private** store.
6. Settings → Environment Variables: add the **required** variables in §3.
7. Deploy. Open `https://<project>.vercel.app/`.

To deploy from a terminal instead: `npm i -g vercel`, then `vercel` (first run links
the project), `vercel env add <NAME> production` for each variable, and `vercel --prod`.

## 2. First login and session

1. Open the dashboard. Log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`. If those aren't set,
   log in with `MCP_AUTH_KEY` instead.
2. Press **GEN** next to each item in the checklist for `MCP_AUTH_KEY`, `CRON_SECRET`,
   `SESSION_ENCRYPTION_KEY` (must be a valid Fernet key) and `ADMIN_PASSWORD`.
   Paste them into Vercel, then redeploy.
3. In **Instagram Session**, paste your `sessionid` cookie (or username + password,
   and 2FA/challenge codes if asked). Use a secondary account first.
4. Run the **Endpoint Test** panel to check each endpoint with your key.

The session is saved encrypted in Blob at `<prefix>/sessions/<name>.json`. Redeploys
keep it. If Instagram revokes it, log in to the dashboard and enter a new cookie.
You don't need to edit env vars.

Lookup order on cold start: saved Blob session → `INSTAGRAM_MCP_SESSIONID` →
`INSTAGRAM_MCP_USERNAME` + `INSTAGRAM_MCP_PASSWORD`. Avoid the password option:
every cold-start login from a new IP looks like a new device.

## 3. Environment variables

The dashboard's checklist shows the same list and flags missing or weak values.

| Variable | Level | Purpose |
| --- | --- | --- |
| `MCP_AUTH_KEY` | required | Key for `/mcp`, `/upload` and the upload APIs. Press **GEN** (32+ chars). |
| `BLOB_READ_WRITE_TOKEN` | required | Added automatically by Storage → Blob. |
| `SESSION_ENCRYPTION_KEY` | required | Fernet key that encrypts the saved session. Must be a 44-character URL-safe base64 key — **not** `secrets.token_hex`. Press **GEN**. |
| `CRON_SECRET` | required | Lets the daily cleanup cron authenticate. Press **GEN**. |
| `ADMIN_USERNAME` | recommended | Dashboard login name. |
| `ADMIN_PASSWORD` | recommended | Dashboard password (10+ characters). Press **GEN**. |
| `INSTAGRAM_MCP_SESSION_NAME` | optional | Session name in Blob. Default `default`. |
| `INSTAGRAM_MCP_SESSIONID` | optional | Cookie seed for cold-start login. |
| `INSTAGRAM_MCP_SESSION_JSON` | optional | First-time seed only: an instagrapi settings JSON. Ignored once a session exists in Blob. |
| `INSTAGRAM_MCP_USERNAME` / `INSTAGRAM_MCP_PASSWORD` | optional | Last-resort login. Avoid the password. |
| `INSTAGRAM_MCP_UPLOAD_TTL_DAYS` | optional | Days before unposted uploads are purged. Default `7`. |
| `INSTAGRAM_MCP_MAX_UPLOAD_BYTES` | optional | Upload size limit. Default 256 MB. |
| `INSTAGRAM_MCP_BLOB_PREFIX` | optional | Top-level Blob key prefix. Default `instagram-mcp`. |
| `INSTAGRAM_MCP_BLOB_ACCESS` | optional | `private` (default, recommended) or `public`. Must match the store type. |
| `INSTAGRAM_MCP_DEDUPE_WINDOW` | optional | Duplicate-suppression window in seconds. Default 600. |
| `INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR`, `…_WRITES_PER_DAY` | optional | Safety caps. |
| `MCP_ALLOW_UNAUTHENTICATED` | **never set** | Turns the key check off. The dashboard flags it if set to `1`. |

## 4. Connect your AI client

The dashboard's **MCP URL** box has a copy button with the key already in the URL.

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

The key may also go in an `Authorization: Bearer <key>` or `X-Auth-Key` header if your client supports headers. Headers are safer than URLs in logs.

## 5. Uploading photos and reels

Open `/upload?auth=<MCP_AUTH_KEY>`, choose a file, and enter a caption and aspect. The
browser sends the bytes straight to Vercel Blob, which skips the ~4.5 MB request-body
limit. The file is added to the upload queue.

Then ask your AI to use these tools:

| Tool | What it does |
| --- | --- |
| `list_uploads` | Lists pending uploads with caption, size and kind. |
| `preview_upload` | Returns a small thumbnail so the AI can see the image. |
| `post_upload` | Validates and converts the file, posts it, then deletes the Blob copy. |
| `delete_upload` | Removes a staged file without posting. |
| `list_problems` | Shows rejected files and why. |

**Photos:** any common format. Converted to a feed-ready JPEG at the requested aspect.

**Reels (upload page):** must be MP4 with H.264 video and AAC audio. MOV, WebM and HEVC are
rejected and logged, not converted, because Vercel has no ffmpeg.

**Reels from a public URL** (`instagram_post_reel` with `https://…`): the file must really be
MP4 (H.264 + AAC). The check reads the file's bytes. Anything else returns
`Error: reel rejected: …` and nothing is uploaded.

**Cleanup:** the Blob copy is deleted after a successful post. A daily cron at 04:00 UTC
(`vercel.json` → `/api/cleanup`) purges unposted uploads older than `INSTAGRAM_MCP_UPLOAD_TTL_DAYS`.

## 6. Security

- **The URL is a credential.** Anyone with `…/mcp?auth=KEY` can post, comment, DM and
  delete on your account. Don't paste it in shared chats or screenshots.
- Rotate the key if it leaks: press GEN for a new `MCP_AUTH_KEY`, update Vercel, redeploy.
- The dashboard uses an HttpOnly, SameSite=Strict session cookie.
- Dashboard login is rate-limited (5 failures per 10 minutes per instance).
- Consider Vercel Deployment Protection or a custom domain with a WAF.
- Never set `MCP_ALLOW_UNAUTHENTICATED=1` on a public deployment.

## 7. Serverless limits

- **Time:** `maxDuration: 60` seconds per call. Keep delays small; long Safe Mode delays
  (minutes) won't fit. Use a server with a longer timeout for those.
- **State:** the session and the upload queue persist in Blob. Daily counters, duplicate
  records and the scheduling queue live in `/tmp` per instance and reset on cold start, so
  the caps are best-effort here.
- **Scheduler:** `scripts/run_scheduler.py` doesn't run on Vercel. Keep scheduled posting
  on a local machine.
- Cold start adds about 1–3 seconds.

## 8. Development

- After editing `instagram_mcp_server/`, run `bash vercel-api/sync_package.sh` (Windows:
  `sync_package.ps1`) to refresh `_vendor/`, then commit `_vendor/`.
- Tests (offline, no network): `python -m unittest discover -s tests` from the repo root.

## 9. Troubleshooting

| Symptom | Fix |
| --- | --- |
| 401 unauthorized | Wrong or missing `auth=` key. Check it matches `MCP_AUTH_KEY` in **Production**. |
| Dashboard login says invalid | Check `ADMIN_USERNAME`/`ADMIN_PASSWORD`. If they're unset, use `MCP_AUTH_KEY`. |
| Checklist says `SESSION_ENCRYPTION_KEY` invalid | Press **GEN** and use that value. Hex keys don't work. |
| Session "not logged in" | Enter a fresh `sessionid` in the dashboard's Instagram Session form. |
| `Error: reel rejected` | Export the reel as MP4 with H.264 video and AAC audio. |
| 404 on `/mcp` | Root Directory isn't set to `vercel-api`. |
| Tool timeouts | Lower the delay variables. Each call must finish within 60 s. |
| Stale behaviour after a code change | Run `sync_package.sh`, commit `_vendor/`, redeploy. |
