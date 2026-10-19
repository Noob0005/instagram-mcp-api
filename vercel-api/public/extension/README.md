# Instagram MCP Sync — browser extension

This extension sends your Instagram login cookie (`sessionid`) from **your own browser** to
**your own** Instagram MCP server on Vercel, so the server stays logged in when Instagram
rotates or expires the cookie. The cookie is encrypted in the browser first, using the same
key as the server's `SESSION_ENCRYPTION_KEY`, and the request also needs your MCP key.

It works in Chrome and Firefox (desktop). The sync prompt appears when you open the browser,
and at most once every 30 / 60 / 120 minutes (you choose). If you synced recently, it stays quiet.

## What you need before you start

From your Vercel project (or the dashboard at `https://<your-project>.vercel.app/`):

| Value | Where it comes from |
| --- | --- |
| Server URL | Your deployment address, for example `https://instagram-mcp-api.vercel.app` (no trailing slash) |
| MCP key | `MCP_AUTH_KEY`, shown in the dashboard's Connect panel |
| Encryption key | `SESSION_ENCRYPTION_KEY`. It must be exactly the same value as on Vercel. |

A 44-character key ending in `=` is a Fernet key. If you don't have one, press **GEN** in the
dashboard, save it in Vercel, and redeploy.

## Step 1 — Download the extension

Download **instagram-mcp-sync.zip** from the same site:

`https://<your-project>.vercel.app/extension/instagram-mcp-sync.zip`

Unzip it into a folder you will keep, for example `Documents/instagram-mcp-sync`.
Don't delete the folder afterwards, because the browser loads the extension from it.

**Tip:** the download button on your dashboard gives you a *pre-configured* copy. It already
contains your server address and keys, so you can skip Step 3. Keep that file private.

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
2. Fill in the **Server URL**, **MCP key** and **Encryption key**. Add your Instagram username
   if you like; it's only a label.
3. Choose how often the sync prompt may appear (30 minutes, 1 hour or 2 hours).
4. Press **SAVE**, then **TEST SERVER**. You should see "Server reachable".
5. Log in to **instagram.com** in this same browser. Solve any captcha there.
6. Press **SYNC NOW**. You should see "Synced as @yourname".

## Day to day

- When you open the browser and the last sync is older than your chosen interval, a
  notification asks **Sync Instagram session?**. Click **Sync now**, or click the notification
  to open the options page.
- If you pick **Later**, or ignore it, the prompt won't come back until the interval has passed.
- The badge shows `!` when a sync is due and `X` when no Instagram login was found in this browser.
- If you change your Instagram password or log out of Instagram, sync fails. Log in again on
  instagram.com, then press SYNC NOW.

## Security notes

- **Your keys are stored in plain text in this browser profile.** Anyone who can use your
  browser profile can read them. Don't use this on a shared computer.
- The extension asks for access to **every https site** because it has to send data to your server. You can
  narrow `host_permissions` in `manifest.json` to only your server URL if you're comfortable
  editing it.
- The server only accepts a sync when the MCP key matches. It never sends the cookie back
  to the browser, and it doesn't write the cookie to logs.
- Keep your MCP key and encryption key private. If either leaks, press GEN in the dashboard,
  update Vercel, redeploy, and update the extension.

## Troubleshooting

| Message | What to do |
| --- | --- |
| No Instagram sessionid in this browser | Log in at instagram.com in this browser, then press SYNC NOW |
| The server rejected the MCP key | Check the MCP key matches `MCP_AUTH_KEY` on Vercel |
| The server could not decrypt the payload | The encryption key must match `SESSION_ENCRYPTION_KEY` on Vercel exactly |
| Encryption key is not a valid Fernet key | Use the 44-character key from GEN |
| Could not reach the server | Check the Server URL and that the deployment is live |
