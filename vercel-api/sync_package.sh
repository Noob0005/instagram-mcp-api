#!/usr/bin/env bash
# Bash equivalent of sync_package.ps1: vendors the current MCP package into
# vercel-api/_vendor so the Vercel function can import it.
# Run after any change to instagram_mcp_server/ (Linux, macOS, Termux).
set -e

here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
src="$root/instagram_mcp_server"
dst="$here/_vendor/instagram_mcp_server"

[ -d "$src" ] || { echo "package not found: $src" >&2; exit 1; }

rm -rf "$dst"
mkdir -p "$dst"
cp "$src"/*.py "$dst"/
[ -f "$src/py.typed" ] && cp "$src/py.typed" "$dst"/ || true

echo "vendored package -> $dst"
ls -1 "$dst"
