#!/bin/sh
# Rebuilds vercel-api/public/upload-client.js: the Vercel Blob browser client, bundled from the
# pinned npm version, so the Upload page never loads code from a third-party CDN.
set -e
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
printf "export { upload } from '@vercel/blob/client';\n" > "$tmp/entry.js"
cd "$tmp" && npm init -y >/dev/null && npm install --silent @vercel/blob@2.8.1 esbuild@0.24.0
./node_modules/.bin/esbuild entry.js --bundle --format=esm --platform=browser --minify \
  --banner:js="/* @vercel/blob 2.8.1 client, bundled for the Upload page. Rebuild with tools/build_upload_client.sh */" \
  --outfile="$root/public/upload-client.js"
rm -rf "$tmp"
echo "wrote $root/public/upload-client.js"
