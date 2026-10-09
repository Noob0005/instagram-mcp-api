"""
Extract a clean `sessionid` cookie value from a pasted cookie blob.

Some tools copy the whole Cookie header (many cookies, URL-encoded). Paste that
whole string as INSTAGRAM_MCP_SESSIONID in .env and run:

    python scripts/extract_sessionid.py

The script prints the cookie names it found (never the values), extracts the
`sessionid` value and rewrites the .env line in place.
"""

import re
import sys
import urllib.parse
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
KEY = "INSTAGRAM_MCP_SESSIONID"


def main() -> int:
    if not ENV_PATH.exists():
        print(f"no .env found at {ENV_PATH}")
        return 1
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith(KEY):
            idx = i
            break
    if idx is None:
        print(f"{KEY} not found in .env")
        return 1

    raw = lines[idx].split("=", 1)[1].strip().strip('"').strip("'")
    decoded = urllib.parse.unquote(raw)
    pairs = [p.strip() for p in re.split(r"[;\s]+", decoded) if p.strip()]
    names, sid = [], None
    for p in pairs:
        if "=" in p:
            n, v = p.split("=", 1)
            names.append(n.strip())
            if n.strip().lower() == "sessionid":
                sid = v.strip().strip('"').strip("'")
    if sid is None:
        # The whole value may be the raw (possibly URL-encoded) sessionid itself.
        candidate = decoded.strip().strip('"').strip("'")
        if candidate and 30 <= len(candidate) <= 200 and ":" in candidate and "=" not in candidate:
            sid = candidate
    print("cookies found:", names)
    if sid is None:
        print("sessionid NOT FOUND - copy the sessionid cookie from DevTools instead")
        return 2
    print(f"sessionid length: {len(sid)} (colons present: {':' in sid})")
    if not (30 <= len(sid) <= 200):
        print("value does not look like a sessionid - not written")
        return 3
    lines[idx] = f"{KEY}={sid}"
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(".env updated with a clean sessionid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
