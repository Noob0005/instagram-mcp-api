"""Dashboard routes: pre-configured extension download and the secret reveal (login required)."""
import asyncio
import io
import json
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vercel-api"))

from admin_ui import core, handlers  # noqa: E402

KEY = "mcp-test-key-0123456789abcdefghij"
ENC = "a" * 43 + "="


def _run(path, query, method, cookie_token=None, body=b""):
    out = {"headers": {}}

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
            out["headers"] = {k.decode(): v.decode() for k, v in msg["headers"]}
        elif msg["type"] == "http.response.body":
            out["body"] = out.get("body", b"") + msg["body"]

    headers = [(b"host", b"example.test"), (b"x-forwarded-proto", b"https")]
    if cookie_token:
        headers.append((b"cookie", f"{core.COOKIE_NAME}={cookie_token}".encode()))
    scope = {"type": "http", "method": method, "path": path, "query_string": query.encode(),
             "headers": headers}
    asyncio.run(handlers.handle(scope, receive, send))
    return out


class AdminRouteTests(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("MCP_AUTH_KEY", "SESSION_ENCRYPTION_KEY")}
        os.environ["MCP_AUTH_KEY"] = KEY
        os.environ["SESSION_ENCRYPTION_KEY"] = ENC
        self.token = core.make_token()

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_extension_download_needs_login(self):
        out = _run("/api/main", "admin=extension", "GET")
        self.assertEqual(out["status"], 401)

    def test_extension_download_is_configured_zip(self):
        out = _run("/api/main", "admin=extension", "GET", cookie_token=self.token)
        self.assertEqual(out["status"], 200)
        self.assertIn("attachment", out["headers"]["content-disposition"])
        z = zipfile.ZipFile(io.BytesIO(out["body"]))
        cfg = json.loads(z.read("defaults.json"))
        self.assertEqual(cfg, {"serverUrl": "https://example.test", "mcpKey": KEY, "encKey": ENC})

    def test_secret_reveal_only_for_allowed_names(self):
        ok = _run("/api/main", "admin=secret", "POST", cookie_token=self.token,
                  body=json.dumps({"name": "SESSION_ENCRYPTION_KEY"}).encode())
        self.assertEqual(ok["status"], 200)
        self.assertEqual(json.loads(ok["body"])["value"], ENC)
        os.environ["CRON_SECRET"] = "should-not-leak"
        try:
            bad = _run("/api/main", "admin=secret", "POST", cookie_token=self.token,
                       body=json.dumps({"name": "CRON_SECRET"}).encode())
            self.assertEqual(bad["status"], 400)
            self.assertNotIn(b"should-not-leak", bad["body"])
        finally:
            os.environ.pop("CRON_SECRET", None)

    def test_secret_reveal_needs_login(self):
        out = _run("/api/main", "admin=secret", "POST",
                   body=json.dumps({"name": "MCP_AUTH_KEY"}).encode())
        self.assertEqual(out["status"], 401)


if __name__ == "__main__":
    unittest.main()
