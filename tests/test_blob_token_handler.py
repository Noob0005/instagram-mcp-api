"""Regression: the upload token endpoint must answer through (req, res).

Vercel's Node runtime ignores a Response returned by a Web-style handler, so the request hung
until the 300 s timeout and every upload stalled.
"""
import os
import unittest

HANDLER = os.path.join(os.path.dirname(__file__), "..", "vercel-api", "api", "blob-token.js")


class BlobTokenHandlerTests(unittest.TestCase):
    def setUp(self):
        with open(HANDLER, encoding="utf-8") as fh:
            self.src = fh.read()

    def test_handler_uses_node_req_res_signature(self):
        self.assertIn("export default async function handler(req, res)", self.src)
        self.assertIn("res.end(", self.src)

    def test_handler_does_not_return_a_web_response(self):
        self.assertNotIn("return Response.json", self.src)
        self.assertNotIn("new Response(", self.src)


if __name__ == "__main__":
    unittest.main()
