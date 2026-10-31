"""The Vercel entry point records the address a client reached it at, so signed view links point there.

On Vercel nothing else records it, so without this every preview came back with "No view link".
"""
import asyncio
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "vercel-api", "api"))

import mcp_server_asgi  # noqa: E402
from instagram_mcp_server import mcp_server  # noqa: E402


def _get(path, headers):
    scope = {"type": "http", "method": "GET", "path": path, "headers": headers, "query_string": b""}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(mcp_server_asgi.app(scope, receive, send))
    return sent[0]["status"]


class RequestOriginTests(unittest.TestCase):
    def setUp(self):
        mcp_server._RUNTIME_ORIGIN["base"] = ""
        patcher = mock.patch.dict(os.environ, {"MCP_AUTH_KEY": "test-origin-key-0123456789abcdef",
                                               "INSTAGRAM_MCP_PUBLIC_URL": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_request_records_the_scheme_and_host_it_came_in_on(self):
        status = _get("/healthz", [(b"host", b"insta.example"), (b"x-forwarded-proto", b"https")])
        self.assertEqual(status, 200)
        self.assertEqual(mcp_server._RUNTIME_ORIGIN["base"], "https://insta.example")

    def test_a_forwarded_host_wins_over_the_internal_host_header(self):
        _get("/healthz", [(b"host", b"internal.example"), (b"x-forwarded-host", b"public.example"),
                          (b"x-forwarded-proto", b"https")])
        self.assertEqual(mcp_server._RUNTIME_ORIGIN["base"], "https://public.example")

    def test_a_view_link_is_built_on_the_domain_the_request_used(self):
        _get("/healthz", [(b"host", b"insta.example"), (b"x-forwarded-proto", b"https")])
        link = mcp_server._view_link({"id": "x1", "size": 10})
        self.assertTrue(link.startswith("https://insta.example/api/upload?file=x1&exp="), link)


if __name__ == "__main__":
    unittest.main()
