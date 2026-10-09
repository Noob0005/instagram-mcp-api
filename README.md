# 🤖 Instagram Control MCP Server

<div align="center">

[![PyPI version](https://img.shields.io/pypi/v/instagram-mcp-server.svg?color=orange&style=flat-square)](https://pypi.org/project/instagram-mcp-server/)
[![GitHub Release](https://img.shields.io/github/v/release/official-Arvind/instagram-mcp?color=blue&style=flat-square)](https://github.com/official-Arvind/instagram-mcp/releases)
[![License](https://img.shields.io/github/license/official-Arvind/instagram-mcp?style=flat-square)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple?style=flat-square)](https://modelcontextprotocol.io)

**A professional, full-fidelity Model Context Protocol (MCP) server enabling AI agents (like Claude Desktop, Cursor, and custom wrappers) to fully control and manage an Instagram account exactly like a human user.**

[Key Features](#-key-features) • [Installation](#-installation) • [Client Config](#%EF%B8%8F-client-configuration) • [Authentication](#-authentication-flow) • [Tool Reference](#-tool-reference) • [Safety Guide](#-rate-limits--safety)

</div>

---

## ⚡ Overview

The **Instagram Control MCP Server** bridges LLMs with the private Instagram Mobile API. By wrapping `instagrapi` and utilizing `FastMCP`, this integration gives AI agents a set of **104 granular tools** to perform everything from media publishing and direct messaging to relationship management, story uploads, scheduling, and hashtag explorations.

Unlike simple graph API wrappers, this server works with standard consumer accounts, automatically handles **session persistence**, supports **two-factor authentication (2FA)**, and resolves SMS/email challenge prompts interactively.

---

## 🛠️ Key Features

* 📦 **Production Ready** — Install directly via `pip` or run locally.
* 🔐 **Seamless Auth** — Session cookies, username/password, 2FA, and SMS/Email verification challenge handlers.
* 🚀 **Automatic Persistence** — Saves sessions locally to bypass repeat logins and prevent login flags.
* 📸 **Rich Media Posting** — Support for single-photo posts, carousel albums, video feeds, and Reels.
* 📖 **Interactive Stories** — Upload photos/videos directly to stories.
* 💬 **Frictionless Direct Messages** — Read threads, mark as seen, and send text, photo, or video messages.
* 👥 **Social & Engagement** — Bulletproof interactions: like, unlike, comment, follow, unfollow, block, and list followers.
* 🔍 **Context Discovery** — Search users, tags, locations, highlights, and similar profiles.

---

## 🚀 Installation

You can run this server either as a global package from **PyPI** or clone it for local modifications.

### Option A: Install from PyPI (Recommended)

Installs the package and registers a global CLI entry point `instagram-mcp`:

```bash
pip install instagram-mcp-server
```

### Option B: Local Setup (Development)

Clone the repository, create a virtual environment, and install dependencies:

```bash
git clone https://github.com/official-Arvind/instagram-mcp.git
cd instagram-mcp
python -m venv venv

# Windows
venv\Scripts\pip install -e .

# Mac/Linux
venv/bin/pip install -e .
```

---

### Option C: One-command setup (start.cmd / start.sh)

The first run creates the virtual environment (if needed) and starts a coloured,
step-by-step installer that:

1. checks and **installs any missing dependencies** (Termux gets Android-safe pins),
2. asks for your **username** and a `sessionid` cookie and/or password — never
   echoed to the screen, not even one character,
3. shows / creates the **auth key** that ends up in your client URL as
   `/mcp?auth=<KEY>`,
4. picks the **pacing preset** (defaults, Safe Mode or custom numbers),
5. picks how the server **listens** — `stdio`, `127.0.0.1` (this PC only) or
   `0.0.0.0` (LAN / your own port-forwarding).

It writes everything to `./.env` (git-ignored) and can start the server for you.
Re-run it any time; pressing Enter keeps the saved values. The project zip ships
without dependencies — the installer pulls them from PyPI.

On later runs it shows a small menu first:

1. **Start the server with the saved setup** — the saved mode/port (`MCP_START_MODE`,
   `MCP_START_PORT`) are read from `.env` and the server starts immediately, no
   questions (for stdio it just prints the client config again).
2. **Change the setup** — the full wizard again, with every saved value as the
   default.

On Windows, `start.cmd` keeps its window open ("Press any key to close") so you can
read the output. With `stdio` nothing stays running in that window by design — your
MCP client starts the server itself; in `local`/`network` mode the server keeps
running there until you press `Ctrl+C`. If a saved `.env` has no remembered mode
yet (an install from before this option existed), the script asks for it once and
stores it.

```bash
# Windows
start.cmd

# Linux / macOS / Termux
bash start.sh

# non-interactive preview of what would be written (writes nothing, installs nothing)
python scripts/setup.py --defaults --dry-run
```

For LAN or port-forwarded use, the installer's `0.0.0.0` mode runs
`scripts/serve.py`, which requires the auth key on every request — your client URL
is then `http://<host>:8080/mcp?auth=<key>`. Keep that key secret: it is the only
lock on the door once the port is reachable.

> **Port forwarding needs a public IPv4 from your ISP.** On mobile hotspots and
> CGNAT connections (common on many ISPs) no inbound connection can reach your PC
> at any port — no firewall or router setting can change that. In that case use a
> tunnel instead (`tailscale up` + `tailscale serve --bg 8080`, or
> `cloudflared tunnel --url http://127.0.0.1:8080`): both dial out, so they work
> behind CGNAT with no port forwarding. `/healthz` exists on `serve.py` only —
> the plain `--transport http` server has no such endpoint.

---

## 🧩 Platform support (Windows · Linux · macOS · Termux)

The server is pure Python 3.10+ and behaves the same everywhere — only the
launcher scripts and video tooling differ.

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .
.\.venv\Scripts\python -m instagram_mcp_server          # stdio
.\scripts\run_http.cmd                                   # HTTP on 127.0.0.1:8765
start.cmd                                                # guided setup / start
schtasks /Create /TN "InstagramMCP" /SC ONLOGON /TR "\"d:\path\to\scripts\run_http.cmd\""   # always-on
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m instagram_mcp_server                 # stdio
bash scripts/run_http.sh                                  # HTTP on 127.0.0.1:8765
bash start.sh                                             # guided setup / start
# background: nohup bash scripts/run_http.sh &   (or systemd / launchd)
```

### Termux (Android)

```bash
pkg update && pkg install python git libjpeg-turbo zlib ffmpeg cronie
git clone https://github.com/official-Arvind/instagram-mcp.git
cd instagram-mcp
python -m venv .venv
# instagrapi 3.x requires curl_cffi, which has no Android wheels -> use 2.x here:
.venv/bin/pip install "instagrapi>=2.18,<3" fastmcp pillow requests
.venv/bin/pip install -e . --no-deps
.venv/bin/python -m instagram_mcp_server                 # stdio
bash scripts/run_http.sh                                  # HTTP on 127.0.0.1:8765
bash start.sh                                             # guided setup / start
```

Termux notes:

- The code auto-detects both instagrapi **3.x** and **2.x** APIs (for example
  `location_search_name()` vs the legacy `location_search(name)`), so 2.x works fine.
- Keep it alive in the background: `termux-wake-lock` before starting the server.
- Scheduled posts: run `python scripts/run_scheduler.py` from `crond` (cronie) or
  `termux-job-scheduler`.
- Session/counters live in Termux's home (`~/.instagram_mcp_session.json`), exactly
  like Linux.
- Videos/Reels also need `ffmpeg` (installed above) plus the optional
  `moviepy==2.2.1` (`pip install --no-deps moviepy==2.2.1`).

### All platforms

- State files (session, counters, queue, dedupe) default to `~`; on serverless
  platforms they automatically move to the temp dir.
- The session file is written with owner-only permissions where the OS supports it.
- The MCP interface is identical (`stdio` / `--transport http` / `--transport sse`),
  so every client on every OS connects the same way.

---

## ⚙️ Client Configuration

Configure your favorite MCP host to locate the executable.

> Running a shared/remote server instead of stdio? See **[SETUP_SSE_HTTP.md](SETUP_SSE_HTTP.md)** for Streamable HTTP (`/mcp`) and SSE (`/sse`) setup, client configs (Cursor / Claude Code / `mcp-remote`) and security guidance.

> Want a hosted URL instead of running it locally? See **[vercel-api/README.md](vercel-api/README.md)** — deploy the same 78-tool server to Vercel with a protected `https://<project>.vercel.app/mcp?auth=<KEY>` endpoint.

### 1. Claude Desktop
Add the following to your `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "instagram-control": {
      "command": "instagram-mcp"
    }
  }
}
```

*If using a virtual environment manually, specify the absolute path to the executable:*
```json
{
  "mcpServers": {
    "instagram-control": {
      "command": "C:\\path\\to\\instagram-mcp\\venv\\Scripts\\instagram-mcp.exe"
    }
  }
}
```

### 2. Cursor IDE
1. Open **Settings** → **Features** → **MCP**.
2. Click **+ Add New MCP Server**.
3. Fill in the parameters:
   * **Name**: `instagram-control`
   * **Type**: `command`
   * **Command**: `instagram-mcp` *(or path to your virtual environment's executable)*

---

## 🔐 Authentication Flow

To allow your AI agent to operate your account, use one of the following methods.

### Method 1: Session Cookie (Recommended & Safest)
Bypasses credential inputs, avoids triggering 2FA blocks, and mimics your existing browser session.

1. Log in to Instagram on your desktop browser.
2. Open **Developer Tools (F12)** → Go to **Application** (Chrome) or **Storage** (Firefox) → **Cookies**.
3. Select `https://www.instagram.com` and copy the value of the `sessionid` cookie.
4. Instruct your agent:
   > *"Log in using session ID with username 'your_username' and session id 'copied_cookie_value'"*

### Method 2: Username & Password
If session cookies are not used, prompt the agent with your credentials:
```
instagram_login_with_credentials(username="your_username", password="your_password")
```
* **Two-Factor Auth**: If the login request triggers 2FA, the agent will receive a challenge response. Provide the code:
  `instagram_complete_2fa(code="123456")`
* **Security Verification**: If Instagram sends a challenge check (Email/SMS verification), provide the code:
  `instagram_complete_challenge(code="123456")`

### Session Lifecycle
On successful authentication, the server saves encrypted session cookies in `instagram_session.json` in the current directory. Subsequent runs will automatically recover this session without prompting for login.

---

## 📂 Tool Reference

The server exposes **104 specialized tools**. Here is the functional breakdown:

**New in this build** (Instagram's newer features):
`instagram_unlike_comment` · `instagram_pin_comment` · `instagram_check_comment`
(offensive-text preflight) · `instagram_get_comment_likers` ·
`instagram_react_to_dm` · `instagram_unsend_dm` · `instagram_mute_thread` ·
`instagram_search_dm_messages` · `instagram_like_story` ·
`instagram_get_story_polls` · `instagram_vote_story_poll` ·
`instagram_add_to_highlight` · `instagram_mute_user` ·
`instagram_remove_follower` · `instagram_handle_follow_request` ·
`instagram_manage_close_friends` · `instagram_follow_hashtag` ·
`instagram_save_to_collection` · `instagram_get_saved_collections` ·
`instagram_get_archived_posts` · `instagram_create_note` · `instagram_get_notes` ·
`instagram_delete_note`

> **Photo/GIF comments:** Instagram's app can attach a photo or GIF to a comment, but
> that write path is not implemented in any public private-API client yet (instagrapi
> 3.0.20 only *reads* inline media comment previews). The MCP server therefore cannot
> post them safely; everything else comment-related (text, replies, likes, pinning,
> preflight, likers) is available.

<details>
<summary><b>🔐 Authentication & Sessions</b></summary>

* `instagram_login_with_sessionid` — Authenticate via browser cookie session bypass.
* `instagram_login_with_credentials` — Authenticate using username + password.
* `instagram_complete_2fa` — Submit a 2-factor authentication code.
* `instagram_complete_challenge` — Submit SMS/Email challenge verification code.
* `instagram_get_login_status` — Query the state of the session lifecycle.
* `instagram_logout` — Clear local session data and disconnect.

</details>

<details>
<summary><b>📸 Media Posting & Content Management</b></summary>

* `instagram_post_photo` — Upload a single image (supports captions, tags, and locations).
* `instagram_post_album` — Upload carousel posts (up to 10 images).
* `instagram_post_video` — Upload standard video content.
* `instagram_post_reel` — Publish Reels (with custom thumbnails and cover pages).
* `instagram_delete_post` — Delete feed items by Media PK.
* `instagram_get_user_feed` — Retrieve published posts for any profile.
* `instagram_get_timeline_feed` — Fetch the home feed timeline.
* `instagram_get_media_info` — View exact JSON metadata for any post.
* `instagram_download_post` — Save media items directly to disk.

</details>

<details>
<summary><b>📖 Stories & Highlights</b></summary>

* `instagram_post_photo_story` — Publish a photo story (supports link/hashtag stickers).
* `instagram_post_video_story` — Publish a video story (supports link/hashtag stickers).
* `instagram_get_user_stories` — Fetch active stories on any target account.
* `instagram_delete_story` — Remove active stories.
* `instagram_get_story_viewers` — Fetch list of story viewers.
* `instagram_get_highlights` — Fetch highlight categories on a profile.
* `instagram_create_highlight` — Bundle selected active stories into a new highlight.
* `instagram_delete_highlight` — Remove custom highlights.

</details>

<details>
<summary><b>💬 Direct Messaging</b></summary>

* `instagram_get_direct_threads` — Fetch ongoing chat threads and inbox lists.
* `instagram_get_direct_messages` — Retrieve history/chat logs from a thread.
* `instagram_send_direct_message` — Dispatch text DMs.
* `instagram_send_dm_photo` — Send photo attachments inside a thread.
* `instagram_send_dm_video` — Send video attachments inside a thread.
* `instagram_mark_thread_seen` — Mark incoming messages as read.

</details>

<details>
<summary><b>❤️ Social Engagement</b></summary>

* `instagram_like_post` / `instagram_unlike_post` — Toggle likes on feed items.
* `instagram_save_post` / `instagram_unsave_post` — Toggle bookmarking.
* `instagram_comment_on_post` — Post a new comment.
* `instagram_reply_to_comment` — Thread replies under a comment ID.
* `instagram_delete_comment` — Delete comment instances.
* `instagram_like_comment` — Like comment targets.
* `instagram_get_post_comments` — List comments under a post.

</details>

<details>
<summary><b>👥 Profile & Relationships</b></summary>

* `instagram_get_profile` — Fetch metadata of any profile.
* `instagram_edit_profile` — Modify name, bio, and external links.
* `instagram_change_profile_picture` — Update profile photo.
* `instagram_follow_user` / `instagram_unfollow_user` — Toggle follow states.
* `instagram_get_followers` / `instagram_get_following` — Query social graphs.
* `instagram_block_user` / `instagram_unblock_user` — Manage blocklists.
* `instagram_get_blocked_users` — View current blocks.
* `instagram_get_notifications` — Read current activity notifications (likes, tags, comments).
* `instagram_get_pending_follow_requests` — List incoming follow requests.

</details>

---

## 🚀 Quickstarts for the common workflows

### 0. Getting an image to the server (path · URL · base64 · inbox)

The server runs on your PC, so it needs the image bytes — a picture pasted into a chat
window is not visible to it. Any of these work for every image tool
(`instagram_post_photo`, `instagram_post_album`, DM photos, stories):

> **Letting the AI do it:** `instagram_upload_image(<base64 or data:image data>)` copies the
> picture into the inbox and returns the path; `instagram_inbox_status()` shows what is
> waiting and which file `latest` points at. Tool arguments travel through the chat as
> **text**, so this is ideal for screenshots and small images (roughly ≤ 300 KB) — multi-MB
> camera photos cannot be text-encoded and should use options 4 or 5 below.

1. **Absolute path** — `C:\Users\you\Pictures\cat.png` (or `/home/you/cat.png`)
2. **Direct image URL** — `https://example.com/cat.jpg`
3. **Pasted data** — a `data:image/png;base64,…` string or the raw base64 blob
4. **Inbox folder** — drop the file into `~/instagram-mcp-inbox` and pass its name or `latest`:

```bash
python scripts/save_image.py             # saves the image on your clipboard into the inbox
python scripts/save_image.py C:\path\cat.png
python scripts/save_image.py --url https://example.com/cat.jpg
python scripts/save_image.py --list      # what is waiting in the inbox

python scripts/watch_clipboard.py        # keep running: every image you copy lands in the inbox
python scripts/watch_clipboard.py --folder ~/Pictures/Screenshots
```

5. **Upload page — works from any device (phone, tablet, another PC)**

   While `scripts/serve.py` is running, open the upload page in a browser: it is **the same
   URL you point your MCP client at, with `/mcp` replaced by `/inbox`** — e.g.
   `https://your-tunnel-domain/inbox?auth=<MCP_AUTH_KEY>` or
   `http://127.0.0.1:8080/inbox?auth=<MCP_AUTH_KEY>` on this PC. Nothing has to be
   configured: the server learns the domain from each request, so port-forwards, Cloudflare
   Tunnel, Tailscale and reverse proxies all produce a correct link. The exact URL is
   reported by `instagram_inbox_status` and in tool error messages. Uploads require the auth
   key, are capped at 25 MB (`INSTAGRAM_MCP_MAX_UPLOAD_BYTES`), filenames are sanitised, and
   files land in the same inbox folder — nothing outside it is ever written.

Then just say *"post the latest image in the inbox"*. `instagram_inspect_image("latest")`
shows the pixel size, ratio and exactly what each framing mode would upload — before
anything is posted.

**Framing (`aspect`) for feed posts** — Instagram accepts 1.91:1 … 4:5; anything outside
that window gets cropped by Instagram, so the server frames it locally instead:

| aspect | what you get |
| --- | --- |
| `auto` (default) | keeps your ratio when it is already valid, otherwise centre-crops to the nearest allowed edge |
| `portrait` | **4:5 → 1080×1350** — the tall feed posts you see on art/photo accounts |
| `square` | 1:1 → 1080×1080 |
| `landscape` | 1.91:1 → 1080×565 |
| `keep` | upload untouched (Instagram may crop it itself) |

Phone photos are EXIF-rotated automatically, transparency is flattened onto white, and
everything is re-encoded as high-quality JPEG (≤ 8 MB) for reliable uploads.

### 1. Post a locally generated image (no public URL needed)

> "Upload `C:\Users\me\Pictures\my_art.png` to my Instagram with a caption about it."

The AI calls `instagram_post_photo` with that absolute path. Local JPG/PNG/WebP
files are normalised to JPEG (and resized if needed) automatically — you never
need a public URL. Add `hashtags="..."` and `mentions="..."` and the server
appends them to the caption. (`instagram_post_photo_story`,
`instagram_post_video`, `instagram_post_reel` and `instagram_post_album` also
accept local paths.)

### 2. Read comments and reply to them

1. `instagram_get_recent_comments(amount_posts=5)` — comments across your latest
   posts in one call (each item has `comment_id` + `media_id_or_url`).
2. `instagram_get_post_comments_range(media_id_or_url=..., start_index=23, end_index=44)`
   — reads comments #23–#44 exactly as they appear on the post.
3. `instagram_reply_to_comment(media_id_or_url=..., comment_id=..., text=...)` —
   posts a public reply to that comment.

Tip: `instagram_get_post_comments(url, amount=50, sort_by="likes")` returns the
most-liked comments first — useful for choosing which comment to reply to.

### 2b. Reply to a specific person's comment (by username)

> "On this post (URL), reply to @someuser: '…'"

One tool call does it — no comment IDs needed:

`instagram_reply_to_comment_by_username(media_id_or_url=URL, username="someuser", text="…", comment_text_contains="optional part of their comment")`

### 2c. Comments on your own posts (excluding you)

`instagram_get_recent_comments(amount_posts=5)` excludes your own comments by
default, so you only see what other people wrote (pass `exclude_self=False` to
include yours).

### 2d. Draft → approve → post (image workflow)

> "Upload C:\...\art.png — draft the caption first"

The AI calls `instagram_post_photo(..., dry_run=True)` to show the final caption
and hashtags **without posting**; after you approve (or ask for changes), it
calls the same tool again without `dry_run` to publish.

### 3. Find posts/reels on a topic and comment publicly

1. `instagram_find_topic_content(topic="...", mode="top" | "recent" | "reels")`
   — trending/recent posts and reels for a topic (combines keyword + hashtags).
2. `instagram_search_posts(query="...")` — keyword search across posts.
3. `instagram_get_explore_reels(amount=10)` — random popular reels from Explore.
4. `instagram_comment_on_post(media_id_or_url=<result url>, text="...")`.

### 4. Scheduling posts & stories

Instagram's consumer API has no native scheduling, so the server ships a queue
plus a small publisher script:

1. `instagram_schedule_post(image_path_or_url="C:\...\pic.png", caption="…", scheduled_at="2026-10-05 18:30", kind="post")`
   — naive times use your local timezone; use `kind="story"` for stories and
   pass a `.mp4` path to schedule a video.
2. `instagram_get_scheduled_posts()` — show the queue (each item has an `id`).
3. `instagram_cancel_scheduled_post(id)` — remove an item (preview → your approval → confirm).

Let **Windows Task Scheduler** publish due items every minute:

```
schtasks /Create /TN "InstagramMCP Scheduler" /SC MINUTE /MO 1 /TR "\"d:\instagram-mcp-master\.venv\Scripts\python.exe\" \"d:\instagram-mcp-master\scripts\run_scheduler.py\""
```

(or run `python scripts/run_scheduler.py` manually / via cron on macOS & Linux —
the machine must be switched on at the scheduled time).

### 5. Deleting anything requires your approval

Every delete tool (`instagram_delete_post`, `instagram_delete_story`,
`instagram_delete_comment`, `instagram_delete_highlight`,
`instagram_cancel_scheduled_post`) refuses to run blind: the first call with
`confirm=False` returns exactly what would be deleted (URL, author, caption,
comment text, queue item…) so the AI can show it to you; only after you approve
does the AI call again with `confirm=True`. This is also written into the
server's instructions, so every connected AI follows the flow.

### 6. Anti-flag pacing (automatic)

Every write action waits a human-like random delay and reports it as
`paced_seconds` in the result. Comments/replies are also capped per hour, and
when Instagram returns a rate-limit/spam-feedback error the server pauses all
write actions before anything else is attempted.

| Env var | Default | Purpose |
| --- | --- | --- |
| `INSTAGRAM_MCP_COMMENT_DELAY_MIN` / `_MAX` | 5 / 12 | seconds waited before a comment/reply (Safe Mode: 90 / 240) |
| `INSTAGRAM_MCP_POST_DELAY_MIN` / `_MAX` | 15 / 40 | seconds waited before posting (Safe Mode: 300 / 900) |
| `INSTAGRAM_MCP_LIKE_DELAY_MIN` / `_MAX` | 3 / 8 | likes (Safe Mode: 60 / 180) |
| `INSTAGRAM_MCP_DM_DELAY_MIN` / `_MAX` | 4 / 10 | direct messages (Safe Mode: 120 / 300) |
| `INSTAGRAM_MCP_SOCIAL_DELAY_MIN` / `_MAX` | 10 / 25 | follows / blocks (Safe Mode: 300 / 600) |
| `INSTAGRAM_MCP_ACTION_DELAY_MIN` / `_MAX` | 2 / 6 | saves and other private actions |
| `INSTAGRAM_MCP_DEDUPE_WINDOW` | 600 | seconds an identical action (same target + content) is suppressed — protects against client-timeout retries double-sending |
| `INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR` | 10 | local cap for comments/replies |
| `INSTAGRAM_MCP_RATE_LIMIT_PAUSE` | 900 | pause length after Instagram rate-limits an action |
| `INSTAGRAM_MCP_USERNAME` / `INSTAGRAM_MCP_SESSIONID` | – | optional auto-login from the MCP client `env` block |
| `INSTAGRAM_MCP_PASSWORD` / `INSTAGRAM_MCP_2FA_CODE` | – | optional username+password login instead of a sessionid (sessionid is still preferred) |
| `INSTAGRAM_MCP_SESSION_PATH` | `~/.instagram_mcp_session.json` | where the saved session lives |
| `INSTAGRAM_MCP_LOGIN_CACHE_TTL` | 60 | how long the login check is cached |
| `INSTAGRAM_MCP_MAX_IMAGE_SIDE` / `_BYTES` | 1440 / 8 MB | image normalisation limits |

### Username + password fallback (when the cookie fails)

Put these lines in `.env` (it is git-ignored — never commit them):

```
INSTAGRAM_MCP_USERNAME=your_username
INSTAGRAM_MCP_PASSWORD=your_password
# optional: only useful when starting the server right away (TOTP codes expire in ~30s)
INSTAGRAM_MCP_2FA_CODE=123456
```

Login order: saved session → `INSTAGRAM_MCP_SESSIONID` cookie → username/password.
If the cookie is missing, expired, or rejected, the server automatically retries
with the password — both at startup and mid-run when a session drops (throttled to
one password attempt per 5 minutes; tune with `INSTAGRAM_MCP_RELOGIN_COOLDOWN`).

If your account has 2FA, start the server (it will report `needs_2fa`), then call
`instagram_complete_2fa` from your MCP client with a fresh code. SMS codes are
valid for several minutes, so `INSTAGRAM_MCP_2FA_CODE` can work if you start the
server immediately after receiving one.

**Never commit your session cookie.** Put it in the MCP client `env` block or a
local `.env` file (both stay out of the repo) — never in a tracked file.

The server itself also loads `./.env` at startup (existing environment variables
win; set `INSTAGRAM_MCP_ENV_FILE` to point at a different file), so a saved
cookie in `.env` auto-logs-in when you start the server from this directory.
If you pasted the whole cookie blob instead of just the sessionid value, run
`python scripts/extract_sessionid.py` to clean it up.

---

## 🔴 Tool risk categories (bot-detection exposure)

Every tool is classified: **red** (highest automation-flag risk), **orange**
(moderate), **green** (safe reads/utility). Ask the server any time:
`instagram_get_risk_categories` returns the full classification plus today's
red/write counts against the caps.

**Red tools** — public comments/replies on others, likes/unlikes, comment likes,
follows/unfollows, blocks/unblocks, DMs (text/photo/video), password logins, and
bulk discovery reads (search posts/users/hashtags, explore reels, timeline feed,
followers/following lists, location posts, similar accounts).

Red tools are:

- paced: likes 3–8 s (Safe Mode 60–180 s), DMs 4–10 s (Safe Mode 120–300 s),
  comments/replies 5–12 s (Safe Mode 90–240 s), follows/blocks 10–25 s
  (Safe Mode 300–600 s);
- duplicate-suppressed: an identical action (same target + content) inside
  `INSTAGRAM_MCP_DEDUPE_WINDOW` (default 600 s) is refused — so a client timeout
  followed by a retry can never double-send a DM/comment/post;
- counted against a **red daily cap** `INSTAGRAM_MCP_MAX_RED_ACTIONS_PER_DAY`
  (unlimited normally; **8/day in Safe Mode**);
- still subject to the comments/hour and total daily write caps.

**Orange tools** — own-account posting/editing/stories/scheduling, moderation
actions (archive/pin/disable comments/tag users), deletions (with the approval
flow), private saves, and moderate reads (a profile's feed/stories, likers,
tagged posts). Paced + counted against `INSTAGRAM_MCP_MAX_WRITES_PER_DAY`.

**Green tools** — login status, reading comments/comment ranges on a known post,
media info, downloads, queue management, the risk report itself: no meaningful
automation signal.

Per-class delay overrides (optional): `INSTAGRAM_MCP_LIKE_DELAY_MIN/_MAX`,
`INSTAGRAM_MCP_SOCIAL_DELAY_MIN/_MAX`, `INSTAGRAM_MCP_DM_DELAY_MIN/_MAX`,
`INSTAGRAM_MCP_COMMENT_DELAY_MIN/_MAX`, `INSTAGRAM_MCP_POST_DELAY_MIN/_MAX`,
`INSTAGRAM_MCP_ACTION_DELAY_MIN/_MAX` (saves and other private actions).

---

## 🛡️ Safe Mode & account-safety playbook

If Instagram ever warns you (*"We suspect automated behavior…"*), **stop all
automation immediately**, complete any in-app verification, and wait 24–72 hours
before using the server again. Then run with Safe Mode enabled:

```
INSTAGRAM_MCP_SAFE_MODE=1
```

Safe Mode tightens every guardrail (each value can still be overridden explicitly):

| Setting | Normal | Safe Mode |
| --- | --- | --- |
| Delay before comment/reply | 30–90 s | 90–240 s |
| Delay before posting | 60–180 s | 5–15 min |
| Delay before likes/follows/DMs | 5–15 s | 30–120 s |
| Comments/replies per hour | 10 | 3 |
| Total write actions per day | unlimited | 25 (`INSTAGRAM_MCP_MAX_WRITES_PER_DAY`) |
| Login check cache | 60 s | 300 s |
| Password re-login cooldown | 5 min | 30 min |

Operational rules that matter more than any setting:

1. **One stable identity.** Same machine + network; avoid VPN/proxy hopping and
   avoid logging in from many different places.
2. **Log in as little as possible.** Prefer the saved session, then a browser
   sessionid; use password login only as fallback. Every login is a "new device"
   to Instagram, and repeated logins are the #1 trigger for warnings/challenges.
3. **Feed the AI URLs** (posts/reels you choose). Skip bulk discovery — search,
   hashtag and explore endpoints are rate-limited/blocked on new accounts anyway.
4. **Short sessions, long breaks.** A few actions, then hours of rest. Never run
   unattended loops.
5. **Vary the text.** Identical repeated comments are flagged instantly.
6. **Warm up new accounts manually** for 1–2 weeks before automating.
7. **Accept the risk.** This uses Instagram's private API and violates their
   Terms — no tool can guarantee zero flags. For a fully sanctioned path, use a
   professional account with the official Graph API (publishing, comments and
   messaging with official limits).

---

## ⚠️ Rate Limits & Safety

Because this server connects using the private mobile client layer, it is subject to Instagram's rate limit filters. **To prevent account suspension or temporary blocks, adhere to these guidelines:**

1. **Avoid High-Frequency Actions** — Spread out posting, liking, and messaging. Do not script loops that execute multiple social actions in rapid succession.
2. **Mimic Human Timing** — If scripting routines, inject random delays (`random.uniform(20, 60)`) between events.
3. **Warm-Up New Accounts** — Freshly created profiles are flags for automation blocks. Use an established account or warm up a new account gradually.
4. **Use Cookie Sessions** — Cookie login triggers far fewer security flags than standard username/password authentication.

---

## 🛡️ Disclaimer

This software is for educational purposes only. It interacts with Instagram's private APIs and is **not** endorsed, affiliated with, or supported by Meta Platforms Inc. Continued automation may result in temporary limits, shadowbans, or permanent closure of your account. Use responsibly at your own risk.

---

## 📄 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for more details.
