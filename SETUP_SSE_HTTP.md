# Running the server over SSE or Streamable HTTP (network transports)

By default the server speaks **stdio** (your MCP client starts it as a child
process — the safest mode). This guide covers the two network transports so the
same server can be reached over `http://`:

| Transport | Endpoint (defaults) | Use it when |
| --- | --- | --- |
| `stdio` (default) | — | Claude Desktop, local clients, maximum safety |
| `http` (Streamable HTTP) | `http://127.0.0.1:8000/mcp` | Remote/LAN clients, modern clients, one shared server |
| `sse` (legacy SSE) | `http://127.0.0.1:8000/sse` | Older clients that only speak SSE |

MCP has moved from SSE to Streamable HTTP — prefer `http` unless a client
requires SSE. Every tool, guardrail, risk category, delete-approval flow and
login behaviour is identical on all transports.

## 1. Start the server

```powershell
# from the repo root, using the venv
$py = ".\.venv\Scripts\python.exe"

# Streamable HTTP on http://127.0.0.1:8000/mcp
& $py -m instagram_mcp_server --transport http

# custom port / path
& $py -m instagram_mcp_server --transport http --port 8765 --path /ig/mcp

# legacy SSE on http://127.0.0.1:8000/sse
& $py -m instagram_mcp_server --transport sse --port 8765

# full flag reference
& $py -m instagram_mcp_server --help
```

If the package is installed globally you can use the console script directly:
`instagram-mcp --transport http --port 8765`.

Convenience launchers are included (edit the paths inside if your repo lives
elsewhere): `scripts\run_http.cmd` and `scripts\run_sse.cmd`.

> **Exposing this to a LAN or the internet (port forwarding)?** The CLI above has
> **no authentication**. Use the guided `start.cmd` / `bash start.sh` (or
> `python scripts/serve.py --host 0.0.0.0 --port 8080` directly) instead: the
> installer creates an `MCP_AUTH_KEY` and the server then requires it on every
> request (`/mcp?auth=<key>`, or an `Authorization: Bearer <key>` / `X-Auth-Key`
> header). `/healthz` stays open for uptime checks.

Notes:
- The server reads `.env` from its **current working directory** — start it from
  the repo folder (or set the `INSTAGRAM_MCP_*` variables in the launcher) so your
  saved session/cookie/password are picked up.
- Defaults come from FastMCP and can also be set with env vars:
  `FASTMCP_HOST`, `FASTMCP_PORT`, `FASTMCP_STREAMABLE_HTTP_PATH`, `FASTMCP_SSE_PATH`,
  `FASTMCP_MESSAGE_PATH`.
- One process serves many clients; all tool calls share the single login session
  and are serialized by the pacing / risk-category guardrails.
- `/healthz` (open, for uptime checks) exists on `scripts/serve.py` only — the plain
  `--transport http` server has no such endpoint (it answers 404). In a **browser**
  open `http://127.0.0.1:8080/healthz` (or `https://<your-tunnel-domain>/healthz`): a
  bare `localhost` may resolve to IPv6 `[::1]` where nothing is listening, and some
  browsers auto-upgrade typed addresses to `https://`, which this plain HTTP
  server refuses.
- **Image uploads use the same URL.** The browser inbox page is your MCP URL with
  `/mcp` replaced by `/inbox` (`https://<domain>/inbox?auth=<key>`). `serve.py` derives
  the domain from each request (Host / `X-Forwarded-*`), so port-forwards, Cloudflare
  Tunnel, Tailscale and nginx all yield a correct link with no configuration; pass
  `--public-url https://your-domain` to pin it explicitly.

## 2. Point your client at it

Generic `mcp.json` (Cursor, Cline, VS Code, and similar):

```json
{
  "mcpServers": {
    "instagram-control": { "url": "http://127.0.0.1:8765/mcp" }
  }
}
```

For SSE clients use `"url": "http://127.0.0.1:8765/sse"`.

Claude Code CLI:

```bash
claude mcp add --transport http instagram-control http://127.0.0.1:8765/mcp
# or:  claude mcp add --transport sse instagram-control http://127.0.0.1:8765/sse
```

Claude Desktop has no native remote support — bridge it with `mcp-remote`:

```json
{
  "mcpServers": {
    "instagram-control": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://127.0.0.1:8765/mcp"]
    }
  }
}
```

Quick connectivity test (safe — it only lists tools and calls the local risk
report; no Instagram API calls):

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8765/mcp") as c:
        tools = await c.list_tools()
        print("tools:", len(tools))
        print(await c.call_tool("instagram_get_risk_categories", {}))

asyncio.run(main())
```

## 3. Security — read this before exposing anything

- The default bind is **127.0.0.1** (loopback only). Keep it that way unless you
  truly need remote access: this server can post, comment, DM and delete on your
  Instagram account, and these HTTP endpoints have **no built-in authentication**.
- For remote access, prefer a **private tunnel** over opening ports:
  - SSH: `ssh -L 8765:127.0.0.1:8765 user@your-machine`, then point the client at
    `http://127.0.0.1:8765/mcp` locally.
  - Tailscale/WireGuard: bind the server to the private interface
    (`--host <tailscale-ip>`) and reach it inside the private network.
- If you must open a LAN port, restrict it to the Private profile and consider a
  reverse proxy (Caddy/nginx) that terminates TLS and adds authentication:

```powershell
New-NetFirewallRule -DisplayName "Instagram MCP 8765" -Direction Inbound `
  -LocalPort 8765 -Protocol TCP -Action Allow -Profile Private
```

- FastMCP itself supports auth providers (`auth=` on `FastMCP(...)`,
  `AuthProvider`/`TokenVerifier`, OIDC providers) plus request-origin protection
  (`allowed_hosts`, `allowed_origins`, `host_origin_protection` via
  `run_http_async`). Those require a custom launcher; for most setups a tunnel or
  an authenticating reverse proxy is the simplest safe answer.

## 4. Keep it running (Windows)

`scripts\run_http.cmd` (already in the repo) contains:

```cmd
@echo off
cd /d d:\instagram-mcp-master
if not exist logs mkdir logs
.venv\Scripts\python.exe -m instagram_mcp_server --transport http --port 8765 >> logs\server.log 2>&1
```

Register it at logon:

```powershell
schtasks /Create /TN "InstagramMCP HTTP" /SC ONLOGON /TR "\"d:\instagram-mcp-master\scripts\run_http.cmd\""
```

A long-running server keeps one saved session alive — fewer logins, less
automation signal (see the Safe Mode playbook in the README).

## 5. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Client 404 / "not found" | Wrong path for the transport: `/mcp` for http, `/sse` for sse |
| Connection refused | Server not running, or bound to 127.0.0.1 while you connect from another machine |
| Port already in use | Pick another `--port` |
| Client connects but sees 0 tools | Re-check the client's transport type (http vs sse) |
| SSE client errors | Use `--transport sse` with the `/sse` URL (legacy; `http` is preferred) |
| Firewall prompt | Allow the Python executable on the **Private** profile only |

> Login, session persistence, risk categories, red/orange/green pacing, delete
> approvals and Safe Mode behave the same over stdio, http and sse.