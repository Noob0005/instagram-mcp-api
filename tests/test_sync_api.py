"""Offline tests for POST /api/session-sync (extension -> server cookie sync)."""
import asyncio
import json
import os
import sys
import unittest

from cryptography.fernet import Fernet

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vercel-api"))

from admin_ui import sync_api  # noqa: E402
from admin_ui import handlers  # noqa: E402

KEY = Fernet.generate_key().decode()
MCP = "mcp-test-key-0123456789abcdefghij"


def _call(method, headers, body: bytes):
    out = {}

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            out["body"] = msg["body"].decode()

    scope = {"type": "http", "method": method,
             "headers": [(k.encode(), v.encode()) for k, v in headers]}
    asyncio.run(sync_api.handle(scope, receive, send))
    return out["status"], json.loads(out["body"])


class DecryptTests(unittest.TestCase):
    def test_roundtrip_and_fields(self):
        tok = Fernet(KEY.encode()).encrypt(json.dumps({"sessionid": "abc%3Ax", "username": "u"}).encode()).decode()
        data = sync_api.decrypt_payload(tok, key=KEY)
        self.assertEqual(data["sessionid"], "abc%3Ax")

    def test_wrong_key_rejected(self):
        tok = Fernet(KEY.encode()).encrypt(b'{"sessionid":"x"}').decode()
        with self.assertRaises(ValueError):
            sync_api.decrypt_payload(tok, key=Fernet.generate_key().decode())

    def test_missing_sessionid_rejected(self):
        tok = Fernet(KEY.encode()).encrypt(b'{"username":"u"}').decode()
        with self.assertRaises(ValueError):
            sync_api.decrypt_payload(tok, key=KEY)


class HandleTests(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("MCP_AUTH_KEY", "SESSION_ENCRYPTION_KEY")}
        os.environ["MCP_AUTH_KEY"] = MCP
        os.environ["SESSION_ENCRYPTION_KEY"] = KEY
        self._orig = handlers._instagram
        self.seen = {}

        async def fake(action, body):
            self.seen["action"] = action
            self.seen["sessionid"] = body.get("sessionid")
            return {"status": "success", "message": "ok", "username": "demo"}

        handlers._instagram = fake

    def tearDown(self):
        handlers._instagram = self._orig
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _payload(self, data: dict) -> bytes:
        return json.dumps({"payload": Fernet(KEY.encode()).encrypt(json.dumps(data).encode()).decode()}).encode()

    def test_get_is_405(self):
        status, _ = _call("GET", [], b"")
        self.assertEqual(status, 405)

    def test_no_key_is_401(self):
        status, _ = _call("POST", [], self._payload({"sessionid": "s"}))
        self.assertEqual(status, 401)

    def test_wrong_mcp_key_is_401(self):
        status, _ = _call("POST", [("x-auth-key", "nope")], self._payload({"sessionid": "s"}))
        self.assertEqual(status, 401)

    def test_valid_sync_logs_in_and_never_echoes_sessionid(self):
        secret = "SUPERSECRET-sessionid-value"
        status, out = _call("POST", [("x-auth-key", MCP)], self._payload({"sessionid": secret}))
        self.assertEqual(status, 200)
        self.assertEqual(self.seen, {"action": "cookie", "sessionid": secret})
        self.assertNotIn(secret, json.dumps(out))
        self.assertEqual(out["username"], "demo")

    def test_bad_payload_is_400(self):
        status, _ = _call("POST", [("x-auth-key", MCP)], json.dumps({"payload": "garbage"}).encode())
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
