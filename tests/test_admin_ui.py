"""Offline tests for the admin dashboard (vercel-api/admin_ui). No network calls."""
import asyncio
import base64
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vercel-api"))

from admin_ui import core, handlers  # noqa: E402

FERNET = base64.urlsafe_b64encode(b"k" * 32).decode()
BASE_ENV = {
    "MCP_AUTH_KEY": "a" * 40,
    "BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_secret_value",
    "SESSION_ENCRYPTION_KEY": FERNET,
    "CRON_SECRET": "c" * 32,
}


def call(method, path, body=None, cookie="", query="", headers=None):
    """Drive the ASGI handler once; returns (status, headers dict, parsed body)."""
    raw = json.dumps(body).encode() if body is not None else b""
    hdrs = [(b"host", b"example.vercel.app"), (b"x-forwarded-proto", b"https")]
    if cookie:
        hdrs.append((b"cookie", f"{core.COOKIE_NAME}={cookie}".encode()))
    for k, v in (headers or {}).items():
        hdrs.append((k.encode(), v.encode()))
    scope = {"type": "http", "method": method, "path": path,
             "query_string": query.encode(), "headers": hdrs, "client": ("1.2.3.4", 1)}
    sent = []

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(msg):
        sent.append(msg)

    asyncio.run(handlers.handle(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    out_headers = {k.decode(): v.decode() for k, v in start["headers"]}
    try:
        parsed = json.loads(payload)
    except ValueError:
        parsed = payload.decode()
    return start["status"], out_headers, parsed


class EnvChecklistTests(unittest.TestCase):
    def test_all_required_present_is_clean(self):
        out = core.check_env(BASE_ENV)
        self.assertEqual(out["required_bad"], 0)

    def test_missing_required_is_flagged(self):
        out = core.check_env({})
        self.assertEqual(out["required_bad"], out["required_total"])
        row = next(r for r in out["rows"] if r["name"] == "MCP_AUTH_KEY")
        self.assertEqual(row["state"], "missing")

    def test_values_never_leak(self):
        text = json.dumps(core.check_env(BASE_ENV))
        for secret in ("vercel_blob_rw_secret_value", "a" * 40, FERNET, "c" * 32):
            self.assertNotIn(secret, text)

    def test_hex_key_is_not_a_valid_fernet_key(self):
        env = dict(BASE_ENV, SESSION_ENCRYPTION_KEY="ab" * 32)  # what token_hex(32) gives
        row = next(r for r in core.check_env(env)["rows"] if r["name"] == "SESSION_ENCRYPTION_KEY")
        self.assertEqual(row["state"], "invalid")
        self.assertEqual(core.check_env(env)["required_bad"], 1)

    def test_valid_fernet_key_accepted(self):
        self.assertTrue(core.valid_fernet_key(FERNET))
        self.assertFalse(core.valid_fernet_key("short"))

    def test_weak_key_and_danger_flag(self):
        env = dict(BASE_ENV, MCP_AUTH_KEY="short", MCP_ALLOW_UNAUTHENTICATED="1")
        rows = {r["name"]: r for r in core.check_env(env)["rows"]}
        self.assertEqual(rows["MCP_AUTH_KEY"]["state"], "weak")
        self.assertEqual(rows["MCP_ALLOW_UNAUTHENTICATED"]["state"], "danger")

    def test_optional_unset_is_not_a_problem(self):
        rows = {r["name"]: r for r in core.check_env(BASE_ENV)["rows"]}
        self.assertEqual(rows["INSTAGRAM_MCP_PASSWORD"]["state"], "unset")


class AuthTests(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(core.admin_mode({}), "none")
        self.assertEqual(core.admin_mode(BASE_ENV), "key")
        both = dict(BASE_ENV, ADMIN_USERNAME="boss", ADMIN_PASSWORD="pw-pw-pw-pw")
        self.assertEqual(core.admin_mode(both), "password")

    def test_password_login(self):
        env = dict(BASE_ENV, ADMIN_USERNAME="boss", ADMIN_PASSWORD="pw-pw-pw-pw")
        self.assertTrue(core.verify_login({"username": "boss", "password": "pw-pw-pw-pw"}, env))
        self.assertFalse(core.verify_login({"username": "boss", "password": "nope"}, env))
        self.assertFalse(core.verify_login({"key": env["MCP_AUTH_KEY"]}, env))  # key is not accepted here

    def test_key_login(self):
        self.assertTrue(core.verify_login({"key": " " + BASE_ENV["MCP_AUTH_KEY"] + " "}, BASE_ENV))
        self.assertFalse(core.verify_login({"key": "wrong"}, BASE_ENV))
        self.assertFalse(core.verify_login({}, {}))

    def test_token_roundtrip_expiry_and_tamper(self):
        tok = core.make_token(BASE_ENV, now=1000)
        self.assertTrue(core.verify_token(tok, BASE_ENV, now=1001))
        self.assertFalse(core.verify_token(tok, BASE_ENV, now=1000 + core.SESSION_SECONDS + 5))
        exp, _, sig = tok.partition(".")
        self.assertFalse(core.verify_token(f"{int(exp) + 999}.{sig}", BASE_ENV, now=1001))
        self.assertFalse(core.verify_token("garbage", BASE_ENV))
        self.assertFalse(core.verify_token(tok, dict(BASE_ENV, MCP_AUTH_KEY="b" * 40), now=1001))
        self.assertIsNone(core.make_token({}))

    def test_limiter_blocks_after_five_failures_then_expires(self):
        lim = core.LoginLimiter()
        for i in range(5):
            self.assertFalse(lim.blocked("ip", now=i))
            lim.fail("ip", now=i)
        self.assertTrue(lim.blocked("ip", now=10))
        self.assertFalse(lim.blocked("ip", now=10 + 601))
        lim.fail("x", now=0)
        lim.reset("x")
        self.assertFalse(lim.blocked("x", now=1))


class HelperTests(unittest.TestCase):
    def test_clean_sessionid(self):
        self.assertEqual(core.clean_sessionid(' "sessionid=123%3Aabc%3A27; Path=/" '), "123%3Aabc%3A27")
        self.assertEqual(core.clean_sessionid("123%3Aabc"), "123%3Aabc")
        self.assertEqual(core.clean_sessionid(""), "")

    def test_origin(self):
        self.assertEqual(core.origin_from_headers({"host": "a.b", "x-forwarded-proto": "https"}), "https://a.b")
        self.assertEqual(core.origin_from_headers({"x-forwarded-host": "c.d, e.f"}), "https://c.d")
        self.assertEqual(core.origin_from_headers({}), "")

    def test_resolve_routes(self):
        self.assertEqual(handlers.resolve("/"), ("page", ""))
        self.assertEqual(handlers.resolve("/api/admin/status"), ("api", "status"))
        self.assertEqual(handlers.resolve("/api/main", "admin=login"), ("api", "login"))
        self.assertEqual(handlers.resolve("/api/main", "route=admin"), ("page", ""))
        self.assertIsNone(handlers.resolve("/mcp"))
        self.assertIsNone(handlers.resolve("/api/main", ""))


class HandlerTests(unittest.TestCase):
    def setUp(self):
        handlers._limiter = core.LoginLimiter()
        patcher = mock.patch.dict(os.environ, BASE_ENV, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self):
        status, hdrs, _ = call("POST", "/api/admin/login", {"key": BASE_ENV["MCP_AUTH_KEY"]})
        self.assertEqual(status, 200)
        cookie = hdrs["set-cookie"]
        for flag in ("HttpOnly", "Secure", "SameSite=Strict"):
            self.assertIn(flag, cookie)
        return cookie.split(";")[0].split("=", 1)[1]

    def test_page_is_served_with_security_headers(self):
        status, hdrs, body = call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("ARCHIVE", body)
        self.assertIn("frame-ancestors 'none'", hdrs["content-security-policy"])
        self.assertEqual(hdrs["cache-control"], "no-store")
        for secret in BASE_ENV.values():
            self.assertNotIn(secret, body)

    def test_status_requires_login(self):
        status, _, _ = call("GET", "/api/admin/status")
        self.assertEqual(status, 401)
        status, _, _ = call("POST", "/api/admin/reveal", {})
        self.assertEqual(status, 401)
        status, _, _ = call("POST", "/api/admin/session", {"action": "status"})
        self.assertEqual(status, 401)

    def test_wrong_login_rejected_and_rate_limited(self):
        for _ in range(5):
            with mock.patch("admin_ui.handlers.asyncio.sleep", new=mock.AsyncMock()):
                status, _, _ = call("POST", "/api/admin/login", {"key": "bad"})
            self.assertEqual(status, 401)
        status, _, _ = call("POST", "/api/admin/login", {"key": BASE_ENV["MCP_AUTH_KEY"]})
        self.assertEqual(status, 429)

    def test_login_then_status_masks_url_and_reveal_returns_it(self):
        cookie = self.login()
        status, _, data = call("GET", "/api/admin/status", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data["mcp_url_masked"].split("?")[0], "https://example.vercel.app/mcp")
        self.assertNotIn(BASE_ENV["MCP_AUTH_KEY"], json.dumps(data))
        status, _, data = call("POST", "/api/admin/reveal", {}, cookie=cookie)
        self.assertEqual(data["mcp_url"], "https://example.vercel.app/mcp?auth=" + BASE_ENV["MCP_AUTH_KEY"])

    def test_query_style_api_route_works(self):
        status, _, data = call("GET", "/api/main", query="admin=info")
        self.assertEqual((status, data["mode"], data["authenticated"]), (200, "key", False))

    def test_session_cookie_action_normalises_and_calls_client(self):
        cookie = self.login()
        fake_ig = mock.Mock()
        fake_ig.login_with_sessionid.return_value = {"status": "success", "message": "ok"}
        fake_srv = mock.Mock(ig=fake_ig)
        with mock.patch.dict(sys.modules, {"instagram_mcp_server.mcp_server": fake_srv}), \
                mock.patch("instagram_mcp_server.mcp_server", fake_srv, create=True):
            status, _, data = call("POST", "/api/admin/session",
                                   {"action": "cookie", "sessionid": ' "sessionid=123%3Aabc;" ', "username": "me"},
                                   cookie=cookie)
        self.assertEqual((status, data["status"]), (200, "success"))
        fake_ig.login_with_sessionid.assert_called_once_with("me", "123%3Aabc")

    def test_session_rejects_empty_cookie_and_unknown_action(self):
        cookie = self.login()
        fake_srv = mock.Mock(ig=mock.Mock())
        with mock.patch.dict(sys.modules, {"instagram_mcp_server.mcp_server": fake_srv}), \
                mock.patch("instagram_mcp_server.mcp_server", fake_srv, create=True):
            _, _, data = call("POST", "/api/admin/session", {"action": "cookie", "sessionid": "  "}, cookie=cookie)
            self.assertEqual(data["status"], "error")
            status, _, _ = call("POST", "/api/admin/session", {"action": "rm -rf"}, cookie=cookie)
            self.assertEqual(status, 400)


class SetupModeTests(unittest.TestCase):
    def test_no_auth_configured_shows_checklist_but_no_login(self):
        handlers._limiter = core.LoginLimiter()
        with mock.patch.dict(os.environ, {}, clear=True):
            status, _, data = call("GET", "/api/admin/status")
            self.assertEqual(status, 200)
            self.assertTrue(data["setup_only"])
            self.assertEqual(data["env"]["required_bad"], data["env"]["required_total"])
            self.assertNotIn("mcp_url_masked", data)
            status, _, _ = call("POST", "/api/admin/login", {"key": ""})
            self.assertEqual(status, 503)


if __name__ == "__main__":
    unittest.main()
