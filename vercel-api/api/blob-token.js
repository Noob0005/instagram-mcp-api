// Mints short-lived Vercel Blob client-upload tokens so the browser can upload large photos/reels
// straight to Blob without exposing BLOB_READ_WRITE_TOKEN. Requires the MCP key in clientPayload.
import { handleUpload } from '@vercel/blob/client';
import { timingSafeEqual } from 'node:crypto';

const PREFIX = (process.env.INSTAGRAM_MCP_BLOB_PREFIX || 'instagram-mcp').replace(/^\/+|\/+$/g, '');
const MAX_BYTES = Number(process.env.INSTAGRAM_MCP_MAX_UPLOAD_BYTES || 256 * 1024 * 1024);
const TYPES = [
  'image/jpeg', 'image/png', 'image/webp', 'image/gif',
  'video/mp4', 'video/quicktime', 'video/x-m4v',
];

function keyOk(candidate) {
  const secret = process.env.MCP_AUTH_KEY || '';
  if (!secret || !candidate) return false;
  const a = Buffer.from(String(candidate));
  const b = Buffer.from(secret);
  return a.length === b.length && timingSafeEqual(a, b);
}

export default async function handler(request) {
  if (request.method !== 'POST') {
    return Response.json({ error: 'use POST' }, { status: 405 });
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: 'body must be JSON' }, { status: 400 });
  }
  try {
    const result = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname, clientPayload) => {
        let payload = {};
        try { payload = JSON.parse(clientPayload || '{}'); } catch { /* handled below */ }
        if (!keyOk(payload.key)) throw new Error('unauthorized');
        if (!pathname.startsWith(`${PREFIX}/uploads/`) || pathname.includes('..')) {
          throw new Error('bad pathname');
        }
        return {
          allowedContentTypes: TYPES,
          maximumSizeInBytes: MAX_BYTES,
          addRandomSuffix: false,
          allowOverwrite: false,
        };
      },
    });
    return Response.json(result);
  } catch (e) {
    const status = e.message === 'unauthorized' ? 401 : 400;
    return Response.json({ error: e.message }, { status });
  }
}
