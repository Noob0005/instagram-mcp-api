// Fernet encryption in the browser (WebCrypto), compatible with Python's cryptography.Fernet.
// Token = base64url( 0x80 | timestamp(8) | iv(16) | AES-128-CBC(ciphertext) | HMAC-SHA256(32) ).
// key = base64url(32 bytes): first 16 bytes sign, last 16 bytes encrypt.

function fernetB64urlToBytes(text) {
  const t = String(text).trim().replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(t + "=".repeat((4 - (t.length % 4)) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

function fernetBytesToB64url(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_");
}

async function fernetEncrypt(plainText, keyText, nowMs) {
  const key = fernetB64urlToBytes(keyText);
  if (key.length !== 32) throw new Error("Fernet key must decode to 32 bytes");
  const signKey = key.slice(0, 16);
  const encKey = key.slice(16, 32);
  const iv = crypto.getRandomValues(new Uint8Array(16));
  const ts = new Uint8Array(8);
  let t = Math.floor((nowMs || Date.now()) / 1000);
  for (let i = 7; i >= 0; i--) { ts[i] = t & 0xff; t = Math.floor(t / 256); }
  const aes = await crypto.subtle.importKey("raw", encKey, { name: "AES-CBC" }, false, ["encrypt"]);
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-CBC", iv: iv }, aes,
                                                        new TextEncoder().encode(plainText)));
  const body = new Uint8Array(25 + ct.length);
  body[0] = 0x80;
  body.set(ts, 1);
  body.set(iv, 9);
  body.set(ct, 25);
  const hk = await crypto.subtle.importKey("raw", signKey, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", hk, body));
  const token = new Uint8Array(body.length + mac.length);
  token.set(body);
  token.set(mac, body.length);
  return fernetBytesToB64url(token);
}
