"""preview_upload must always return something the client can show: an image, or plain text.

Image(content=...) is not accepted by this FastMCP version, so text results used to fail as a
tool error and reach the client as an empty payload.
"""
import asyncio
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image as PILImage  # noqa: E402
from fastmcp import Client  # noqa: E402

from instagram_mcp_server import mcp_server, upload_store  # noqa: E402

REC = {"id": "x1", "filename": "a.jpg", "kind": "photo"}


def _jpeg(size=(400, 300)):
    buf = io.BytesIO()
    PILImage.new("RGB", size, (30, 120, 200)).save(buf, "JPEG")
    return buf.getvalue()


async def _call(**patches):
    with mock.patch.object(upload_store, "get_upload", return_value=REC):
        with mock.patch.object(upload_store, "fetch_thumb", **patches.get("thumb", {"return_value": None})):
            with mock.patch.object(upload_store, "fetch_bytes", **patches.get("bytes", {"return_value": _jpeg()})):
                async with Client(mcp_server.mcp) as client:
                    return await client.call_tool("preview_upload", {"upload_id": "x1"})


class PreviewUploadTests(unittest.TestCase):
    def test_stored_thumbnail_comes_back_as_a_jpeg_image_with_a_note(self):
        result = asyncio.run(_call(thumb={"return_value": _jpeg((200, 150))}))
        self.assertEqual([type(b).__name__ for b in result.content], ["ImageContent", "TextContent"])
        self.assertFalse(result.is_error)
        note = result.content[1].text
        self.assertIn("a.jpg", note)
        self.assertIn("200x150", note)

    def test_original_is_used_when_no_thumbnail_exists(self):
        result = asyncio.run(_call(bytes={"return_value": _jpeg((4000, 3000))}))
        self.assertEqual([type(b).__name__ for b in result.content], ["ImageContent", "TextContent"])
        self.assertIn("512x384", result.content[1].text)  # shrunk to 512 px on the longest side

    def test_a_failed_read_returns_readable_text_not_a_tool_error(self):
        result = asyncio.run(_call(bytes={"side_effect": RuntimeError("store down")}))
        self.assertFalse(result.is_error)
        self.assertEqual([type(b).__name__ for b in result.content], ["TextContent"])
        self.assertIn("store down", result.content[0].text)


if __name__ == "__main__":
    unittest.main()
