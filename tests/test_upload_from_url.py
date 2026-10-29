"""upload_from_url: the server pulls a link into staged uploads; offline tests (no network, no Blob)."""
import io
import os
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from instagram_mcp_server import blob_store, upload_store, url_upload  # noqa: E402
from instagram_mcp_server.url_upload import UrlUploadError  # noqa: E402

PUBLIC = "93.184.216.34"


def public_only(host):
    return [PUBLIC] if host != "127.0.0.1" and host != "localhost" else ["127.0.0.1"]


def jpeg_bytes(size=(800, 600)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 90)).save(buf, "JPEG")
    return buf.getvalue()


def png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (20, 90, 200)).save(buf, "PNG")
    return buf.getvalue()


def mp4_bytes():
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


class FakeResp:
    def __init__(self, status=200, headers=None, chunks=()):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = list(chunks)

    def iter_content(self, _size):
        return iter(self._chunks)

    def close(self):
        pass


class CheckUrlTests(unittest.TestCase):
    def test_only_web_links_are_accepted(self):
        for bad in ("", "ftp://example.com/a.jpg", "file:///etc/passwd", "not a link"):
            with self.subTest(bad=bad), self.assertRaises(UrlUploadError):
                url_upload.check_url(bad)

    def test_private_and_local_addresses_are_refused(self):
        for host, addr in (("localhost", "127.0.0.1"), ("intranet.test", "10.0.0.5"),
                           ("meta.test", "169.254.169.254"), ("v6.test", "::1")):
            with self.subTest(host=host), mock.patch.object(url_upload, "_resolve", return_value=[addr]):
                with self.assertRaises(UrlUploadError) as ctx:
                    url_upload.check_url(f"https://{host}/a.jpg")
                self.assertIn("private or local", str(ctx.exception))

    def test_public_address_is_accepted(self):
        with mock.patch.object(url_upload, "_resolve", return_value=[PUBLIC]):
            self.assertEqual(url_upload.check_url("https://cdn.test/a.jpg"), "https://cdn.test/a.jpg")

    def test_unknown_host_is_a_plain_error(self):
        with mock.patch.object(url_upload, "_resolve", side_effect=socket.gaierror("nope")):
            with self.assertRaises(UrlUploadError) as ctx:
                url_upload.check_url("https://no-such-host.test/a.jpg")
        self.assertIn("Could not find the host", str(ctx.exception))


class FindOgImageTests(unittest.TestCase):
    def test_reads_og_image_either_attribute_order(self):
        page = ('<meta property="og:image" content="/a/b.jpg?x=1&amp;y=2">'
                '<meta content="https://cdn.test/i.png" name="twitter:image">')
        self.assertEqual(url_upload.find_og_image(page, "https://site.test/p/"),
                         "https://site.test/a/b.jpg?x=1&y=2")
        only_twitter = '<meta content="https://cdn.test/i.png" name="twitter:image">'
        self.assertEqual(url_upload.find_og_image(only_twitter, "https://site.test/"), "https://cdn.test/i.png")

    def test_no_image_means_none(self):
        self.assertIsNone(url_upload.find_og_image("<html><title>x</title></html>", "https://site.test/"))


class GetTests(unittest.TestCase):
    def run_get(self, responses, max_bytes=1000, resolver=public_only):
        def fake_get(url, **_kwargs):
            return responses[url]
        with mock.patch.object(url_upload, "_resolve", side_effect=resolver), \
                mock.patch.object(url_upload.requests, "get", side_effect=fake_get):
            return url_upload._get(responses.get("_start", next(iter(responses))),
                                   deadline=1e12, max_bytes=max_bytes)

    def test_a_redirect_to_a_private_address_is_refused(self):
        responses = {
            "https://ok.test/a": FakeResp(302, {"Location": "http://127.0.0.1/secret.jpg"}),
        }
        with self.assertRaises(UrlUploadError) as ctx:
            self.run_get(responses)
        self.assertIn("private or local", str(ctx.exception))

    def test_a_redirect_to_a_public_file_is_followed(self):
        responses = {
            "https://ok.test/a": FakeResp(301, {"Location": "https://cdn.test/final.jpg"}),
            "https://cdn.test/final.jpg": FakeResp(200, {"Content-Type": "image/jpeg; charset=x"},
                                                   [b"\xff\xd8\xff" + b"0" * 20]),
        }
        data, ctype, final = self.run_get(responses)
        self.assertEqual(final, "https://cdn.test/final.jpg")
        self.assertEqual(ctype, "image/jpeg")
        self.assertTrue(data.startswith(b"\xff\xd8\xff"))

    def test_declared_size_over_the_limit_is_refused_before_reading(self):
        responses = {"https://cdn.test/big.mp4": FakeResp(200, {"Content-Length": "999999"}, [b"x"])}
        with self.assertRaises(UrlUploadError) as ctx:
            self.run_get(responses, max_bytes=10)
        self.assertIn("bigger than", str(ctx.exception))

    def test_streamed_size_over_the_limit_is_refused(self):
        responses = {"https://cdn.test/big.mp4": FakeResp(200, {}, [b"x" * 8, b"x" * 8])}
        with self.assertRaises(UrlUploadError):
            self.run_get(responses, max_bytes=10)

    def test_http_error_says_what_happened(self):
        responses = {"https://cdn.test/a.jpg": FakeResp(403)}
        with self.assertRaises(UrlUploadError) as ctx:
            self.run_get(responses)
        self.assertIn("HTTP 403", str(ctx.exception))


class PullTests(unittest.TestCase):
    """pull() with the network, Blob and the upload index replaced by fakes."""

    def setUp(self):
        self.stored = []   # (key, content_type) for every Blob write
        self.added = []    # kwargs for every upload record
        patches = [
            mock.patch.object(url_upload, "_resolve", side_effect=public_only),
            mock.patch.object(blob_store, "blob_configured", return_value=True),
            mock.patch.object(blob_store, "put_bytes", side_effect=self._put),
            mock.patch.object(upload_store, "add_upload", side_effect=self._add),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _put(self, key, data, content_type="application/octet-stream", access=None):
        self.stored.append((key, content_type))
        return {"url": f"https://blob.test/{key}", "pathname": key, "size": len(data)}

    def _add(self, **kwargs):
        self.added.append(kwargs)
        return {"id": "rec1", **kwargs}

    def dispatch(self, mapping):
        """A fake _get: mapping[url] is bytes-ready (data, ctype), an exception, or missing (404)."""
        def fake(url, deadline, max_bytes):
            value = mapping.get(url)
            if value is None:
                raise UrlUploadError("The server refused the file (HTTP 404).")
            if isinstance(value, Exception):
                raise value
            data, ctype = value
            return data, ctype, url
        return mock.patch.object(url_upload, "_get", side_effect=fake)

    def test_a_photo_link_is_saved_with_a_preview(self):
        with self.dispatch({"https://cdn.test/files/beach.jpg": (jpeg_bytes(), "image/jpeg")}):
            result = url_upload.pull("https://cdn.test/files/beach.jpg", caption="  Sunset  ")
        self.assertTrue(result["ok"])
        self.assertTrue(result["preview"].startswith(b"\xff\xd8\xff"))
        self.assertIsNotNone(result["record"])
        self.assertEqual(len(self.stored), 2)  # the file and its preview
        self.assertTrue(all(key.startswith(blob_store.PREFIX + "/uploads/") for key, _ in self.stored))
        added = self.added[0]
        self.assertEqual(added["filename"], "beach.jpg")
        self.assertEqual(added["kind"], "photo")
        self.assertEqual(added["caption"], "Sunset")
        self.assertIsNotNone(added["thumb_pathname"])
        self.assertIn("Saved", result["message"])
        self.assertIn("Caption saved.", result["message"])
        self.assertIn("rec1", result["message"])

    def test_a_video_link_is_saved_as_a_reel_without_a_second_download(self):
        video_url = "https://cdn.test/clips/reel.mp4"
        calls = []

        def fake(url, deadline, max_bytes):
            calls.append(url)
            return mp4_bytes(), "video/mp4", url
        with mock.patch.object(url_upload, "_get", side_effect=fake):
            result = url_upload.pull(video_url)
        self.assertTrue(result["ok"])
        self.assertEqual(calls, [video_url])  # no page lookup for a file link
        self.assertIsNone(result["preview"])
        self.assertEqual(self.added[0]["kind"], "reel")
        self.assertIsNone(self.added[0]["thumb_pathname"])

    def test_a_kind_that_does_not_match_the_file_is_refused(self):
        with self.dispatch({"https://cdn.test/clips/reel.mp4": (mp4_bytes(), "video/mp4")}):
            with self.assertRaises(UrlUploadError) as ctx:
                url_upload.pull("https://cdn.test/clips/reel.mp4", kind="photo")
        self.assertIn("kind='reel'", str(ctx.exception))
        self.assertEqual(self.added, [])

    def test_a_blocked_file_still_gives_the_page_preview_and_stores_nothing(self):
        page = "https://site.test/post"
        html = b'<meta property="og:image" content="https://cdn.test/thumb.png">'
        with self.dispatch({
            "https://cdn.test/files/huge.mp4": UrlUploadError("The server refused the file (HTTP 403)."),
            page: (html, "text/html"),
            "https://cdn.test/thumb.png": (png_bytes(), "image/png"),
        }):
            result = url_upload.pull("https://cdn.test/files/huge.mp4", page_url=page)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["record"])
        self.assertTrue(result["preview"].startswith(b"\xff\xd8\xff"))
        self.assertIn("Nothing was stored", result["message"])
        self.assertEqual(self.stored, [])
        self.assertEqual(self.added, [])

    def test_a_blocked_file_with_no_page_or_thumbnail_says_so(self):
        with self.dispatch({"https://cdn.test/files/huge.mp4": UrlUploadError("HTTP 403")}):
            result = url_upload.pull("https://cdn.test/files/huge.mp4")
        self.assertFalse(result["ok"])
        self.assertIsNone(result["preview"])
        self.assertIn("No preview could be found", result["message"])
        self.assertEqual(self.added, [])

    def test_a_caller_thumbnail_is_used_when_the_file_is_blocked(self):
        with self.dispatch({
            "https://cdn.test/files/huge.mp4": UrlUploadError("The server could not be reached (Timeout)."),
            "https://cdn.test/hint.png": (png_bytes(), "image/png"),
        }):
            result = url_upload.pull("https://cdn.test/files/huge.mp4", thumb_url="https://cdn.test/hint.png")
        self.assertFalse(result["ok"])
        self.assertTrue(result["preview"].startswith(b"\xff\xd8\xff"))

    def test_a_web_page_link_is_not_mistaken_for_a_photo(self):
        page = "https://site.test/post"
        html = b'<meta property="og:image" content="https://cdn.test/thumb.png"><p>hello</p>'
        with self.dispatch({
            page: (html, "text/html"),
            "https://cdn.test/thumb.png": (png_bytes(), "image/png"),
        }):
            result = url_upload.pull(page)
        self.assertFalse(result["ok"])
        self.assertIn("not a photo or video", result["message"])
        self.assertEqual(self.added, [])

    def test_without_blob_storage_the_call_says_so(self):
        with mock.patch.object(blob_store, "blob_configured", return_value=False), \
                self.dispatch({"https://cdn.test/a.jpg": (jpeg_bytes(), "image/jpeg")}):
            with self.assertRaises(UrlUploadError) as ctx:
                url_upload.pull("https://cdn.test/a.jpg")
        self.assertIn("not connected", str(ctx.exception))

    def test_bad_options_are_refused_before_any_download(self):
        with self.dispatch({}), self.assertRaises(UrlUploadError):
            url_upload.pull("https://cdn.test/a.jpg", kind="story")
        with self.dispatch({}), self.assertRaises(UrlUploadError):
            url_upload.pull("https://cdn.test/a.jpg", aspect="round")


class BadLinkAndToolShapeTests(unittest.TestCase):
    def test_a_bad_link_is_refused_before_any_download(self):
        with mock.patch.object(url_upload, "_get", side_effect=AssertionError("must not download")):
            with self.assertRaises(UrlUploadError):
                url_upload.pull("ftp://example.com/a.jpg")
            with mock.patch.object(url_upload, "_resolve", return_value=["127.0.0.1"]):
                with self.assertRaises(UrlUploadError):
                    url_upload.pull("http://localhost/a.jpg")

    def test_the_mcp_tool_returns_text_or_an_image_with_text(self):
        import asyncio
        from fastmcp import Client
        from instagram_mcp_server import mcp_server

        async def call(args):
            async with Client(mcp_server.mcp) as client:
                return await client.call_tool("upload_from_url", args)

        bad = asyncio.run(call({"url": "ftp://example.com/a.jpg"}))
        self.assertEqual(bad.content[0].text.split(":")[0], "Could not use that link")

        preview = {"ok": False, "preview": jpeg_bytes((64, 48)), "record": None,
                   "message": "Preview only, nothing stored."}
        with mock.patch.object(url_upload, "pull", return_value=preview):
            res = asyncio.run(call({"url": "https://cdn.test/a.jpg", "page_url": "https://site.test/p"}))
        self.assertEqual([type(c).__name__ for c in res.content], ["ImageContent", "TextContent"])
        self.assertEqual(res.content[1].text, "Preview only, nothing stored.")

        saved = {"ok": True, "preview": None, "record": {"id": "r1"}, "message": "Saved."}
        with mock.patch.object(url_upload, "pull", return_value=saved):
            res = asyncio.run(call({"url": "https://cdn.test/a.jpg"}))
        self.assertEqual([c.text for c in res.content], ["Saved."])


if __name__ == "__main__":
    unittest.main()
