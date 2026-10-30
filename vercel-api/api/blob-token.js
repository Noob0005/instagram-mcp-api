// Mints short-lived Vercel Blob client-upload tokens so the browser can upload large photos/reels
// straight to Blob without exposing BLOB_READ_WRITE_TOKEN. Requires the MCP key in clientPayload.
//
// Written as a plain Node (req, res) handler. Vercel's Node runtime ignores a Response that a
// handler returns, so the earlier Web-style handler never answered and hung until the 300 s
// timeout (every upload stalled at "Uploading").
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

function send(res, status, payload) {
  res.statusCode = status;
  res.setHeader('content-type', 'application/json');
  res.end(JSON.stringify(payload));
}

function readBody(req) {
  // Vercel may already have parsed a JSON body; otherwise read the stream.
  if (req.body !== undefined && req.body !== null) {
    return Promise.resolve(typeof req.body === 'string' ? req.body : JSON.stringify(req.body));
  }
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return send(res, 405, { error: 'use POST' });

  let raw;
  try {
    raw = await readBody(req);
  } catch {
    return send(res, 400, { error: 'could not read the request' });
  }
  let body;
  try {
    body = JSON.parse(raw || '{}');
  } catch {
    return send(res, 400, { error: 'body must be JSON' });
  }

  // handleUpload wants a standard Request; rebuild one from the request we were given.
  const headers = {};
  for (const [k, v] of Object.entries(req.headers || {})) {
    if (typeof v === 'string' && k !== 'content-length') headers[k] = v;
  }
  const request = new Request(`https://${req.headers.host || 'localhost'}${req.url || '/api/blob-token'}`, {
    method: 'POST', headers, body: raw,
  });

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
    return send(res, 200, result);
  } catch (e) {
    const status = e.message === 'unauthorized' ? 401 : 400;
    return send(res, status, { error: e.message });
  }
}
