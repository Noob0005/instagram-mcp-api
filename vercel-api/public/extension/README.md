# Session Sync — browser extension

This extension copies two logins from **your own browser** to **your own servers**, so they stay
logged in when the sites rotate or expire their cookies:

- **Instagram:** your `sessionid` cookie goes to your Instagram MCP server on Vercel. It is
  encrypted in the browser first, with the same key as the server's `SESSION_ENCRYPTION_KEY`, and
  the request also needs your MCP key.
- **Gemini:** your two Gemini cookies (`__Secure-1PSID` and `__Secure-1PSIDTS`) go to your Gemini
  Archive server. The request needs that server's sync key (`GEMINI_SYNC_KEY`).

It works in Chrome and Firefox (desktop). Whenever you open **instagram.com** or **gemini.google.com**
in this browser, it syncs that site's login in the background, at most once every 30 / 60 / 120
minutes (you choose, for each site separately). If you synced recently, it does nothing.

## What you need before you start

**Instagram** (from your Vercel project, or the dashboard at `https://<your-project>.vercel.app/`):

| Value | Where it comes from |
| --- | --- |
| Server URL | Your deployment address, for example `https://instagram-mcp-api.vercel.app` (no trailing slash) |
| MCP key | `MCP_AUTH_KEY`, shown in the dashboard's Connect panel |
| Encryption key | `SESSION_ENCRYPTION_KEY`. It must be exactly the same value as on Vercel. |

A 44-character key ending in `=` is a Fernet key. If you don't have one, press **GEN** in the
dashboard, save it in Vercel, and redeploy.

**Gemini** (from the Gemini Archive project on Vercel):

| Value | Where it comes from |
| --- | --- |
| Gemini server URL | Your Gemini Archive address, for example `https://webapi-your-project.vercel.app` |
| Sync key | `GEMINI_SYNC_KEY`. Set it in that project's Vercel settings (at least 24 characters, different from `APP_API_KEY`), then redeploy. |

You can use either site on its own. Leave the other one's fields empty.

## Step 1 — Download the extension

Download **instagram-mcp-sync.zip** from your Instagram MCP site:

`https://<your-project>.vercel.app/extension/instagram-mcp-sync.zip`

Unzip it into a folder you will keep, for example `Documents/session-sync`.
Don't delete the folder afterwards, because the browser loads the extension from it.

**Tip:** the download button on your dashboard gives you a *pre-configured* copy. It already
contains your Instagram server address and keys, so you can skip the Instagram part of Step 3.
Keep that file private.

## Step 2 — Install it

### Chrome, Edge or Brave

1. Open `chrome://extensions` (or `edge://extensions`, `brave://extensions`).
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select the unzipped folder.
4. Pin the extension from the puzzle icon if you want it visible.

### Firefox

1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on…**.
3. Select **`manifest-firefox.json`** inside the unzipped folder.

Firefox removes temporary add-ons when it restarts, so you'll repeat this step each time you
start Firefox. To make it permanent, the extension must be signed by Mozilla, which this
project doesn't do yet.

## Step 3 — Set it up

1. The options page opens after installation. If it doesn't, open the extension's **Options**
   (right-click its icon → Options, or `chrome://extensions` → Details → Extension options).
2. **Instagram:** fill in the **Server URL**, **MCP key** and **Encryption key**. Add your Instagram
   username if you like; it's only a label.
3. **Gemini:** fill in the **Gemini server URL** and **Sync key**.
4. Choose how often an automatic sync may run (30 minutes, 1 hour or 2 hours).
5. Press **SAVE**, then **TEST INSTAGRAM SERVER**. You should see "Server reachable".
6. Log in to **instagram.com** and/or **gemini.google.com** in this same browser. Solve any captcha there.
7. Press **SYNC INSTAGRAM** and/or **SYNC GEMINI**. You should see "Synced as @yourname" and
   "Gemini cookies saved."

## Day to day

- On instagram.com and gemini.google.com a round **S** button sits at the bottom right. Click it to
  see both sites: whether each is logged in here, when it last synced, and any failure. **SYNC
  INSTAGRAM** and **SYNC GEMINI** run that sync now. **SETTINGS** opens the options page. The button
  is added by the extension itself; the site's own pages are not changed.
- Open instagram.com or gemini.google.com (or reload it). If that site's last successful sync is
  older than your interval, the extension sends its login to your server. You don't need to click
  anything.
- The options page shows the last sync time for each site. If the last attempt failed, it shows why.
- The badge shows `!` while the last attempt of either site failed. After a failure the extension
  waits 10 minutes before trying that site again. Press the sync button to try straight away.
- If you're logged out of a site in this browser, its attempt fails and says so. Log in there, and
  the next visit syncs.
- If you change your Instagram password or log out of Instagram, sync fails. Log in again on
  instagram.com, then press SYNC INSTAGRAM.

## Security notes

- **Your keys are stored in plain text in this browser profile.** Anyone who can use your
  browser profile can read them. Don't use this on a shared computer.
- The extension asks for access to **every https site** because it has to send data to your servers.
  You can narrow `host_permissions` in `manifest.json` to only your server URLs if you're comfortable
  editing it.
- The Instagram server only accepts a sync when the MCP key matches. The Gemini server only accepts
  one when the sync key matches, and that key opens nothing else: the app key and a login do not
  work there. Neither server sends the cookies back to the browser.
- The Gemini cookies are sent over HTTPS, not encrypted in the browser as the Instagram one is.
- Keep your keys private. If one leaks, generate a new one (GEN on the dashboard for Instagram;
  for the sync key, pick a new long random value), update Vercel, redeploy, and update the extension.

## Troubleshooting

| Message | What to do |
| --- | --- |
| No Instagram sessionid in this browser | Log in at instagram.com in this browser, then press SYNC INSTAGRAM |
| The server rejected the MCP key | Check the MCP key matches `MCP_AUTH_KEY` on Vercel |
| The server could not decrypt the payload | The encryption key must match `SESSION_ENCRYPTION_KEY` on Vercel exactly |
| Encryption key is not a valid Fernet key | Use the 44-character key from GEN |
| No Gemini login in this browser | Log in at gemini.google.com in this browser, then press SYNC GEMINI |
| The Gemini server rejected the sync key | Check the sync key matches `GEMINI_SYNC_KEY` on the Gemini Archive project |
| The Gemini server has no GEMINI_SYNC_KEY set yet | Add `GEMINI_SYNC_KEY` in Vercel and redeploy that project |
| Could not reach the server | Check the server URL and that the deployment is live |
