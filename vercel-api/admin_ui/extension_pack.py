"""Builds the browser extension zip for the dashboard.

The pre-configured copy embeds the server address and keys (as defaults.json), so it must only
be served behind dashboard login. The public copy in /extension/ contains no keys.
"""
import base64
import io
import json
import zipfile

from admin_ui.extension_files import FILES

CONFIGURED_NOTE = (
    "# CONFIGURED COPY\n\n"
    "This copy already contains your server address and keys (defaults.json). Keep it private and "
    "don't upload it anywhere. The public copy asks you to type them in.\n\n---\n\n"
)


def build(server_url: str, mcp_key: str, enc_key: str, configured: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, b64 in FILES.items():
            data = base64.b64decode(b64)
            if configured and name == "README.md":
                data = CONFIGURED_NOTE.encode("utf-8") + data
            z.writestr(name, data)
        if configured:
            z.writestr("defaults.json", json.dumps(
                {"serverUrl": server_url, "mcpKey": mcp_key, "encKey": enc_key}, indent=2) + "\n")
    return buf.getvalue()
