"""Photos and carousel items go up at original size and quality by default (offline)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from instagram_mcp_server import mcp_server as srv  # noqa: E402


def _save(name, size, fmt, mode="RGB", color=(40, 120, 200), quality=90):
    d = Path(tempfile.mkdtemp())
    path = d / name
    im = Image.new(mode, size, color)
    if fmt == "JPEG":
        im.save(path, "JPEG", quality=quality)
    else:
        im.save(path, fmt)
    return path


class OriginalQualityTests(unittest.TestCase):
    def test_a_valid_jpeg_is_sent_byte_for_byte(self):
        src = _save("photo.jpg", (3000, 2000), "JPEG", quality=92)
        out, is_temp, info = srv._prepare_feed_image(src, "auto")
        self.assertFalse(is_temp)
        self.assertEqual(Path(out).read_bytes(), src.read_bytes())
        self.assertEqual(info["final_px"], "3000x2000")
        self.assertFalse(info["resized"])
        self.assertEqual(info["quality"], "original bytes")

    def test_a_png_keeps_its_resolution_and_is_encoded_at_top_quality(self):
        src = _save("shot.png", (2400, 1600), "PNG")
        out, is_temp, info = srv._prepare_feed_image(src, "auto")
        self.assertTrue(is_temp)
        with Image.open(out) as im:
            self.assertEqual(im.size, (2400, 1600))
            self.assertEqual(im.format, "JPEG")
        self.assertEqual(info["quality"], 100)
        self.assertFalse(info["resized"])

    def test_auto_crops_only_when_outside_instagram_window(self):
        src = _save("wide.jpg", (3000, 1000), "JPEG")
        out, _, info = srv._prepare_feed_image(src, "auto")
        with Image.open(out) as im:
            self.assertEqual(im.size, (1910, 1000))  # 1.91:1, not scaled
        self.assertTrue(info["cropped_to_instagram_frame"])
        self.assertFalse(info["resized"])

    def test_keep_never_crops_or_scales(self):
        src = _save("wide2.jpg", (3000, 1000), "JPEG")
        out, is_temp, info = srv._prepare_feed_image(src, "keep")
        self.assertFalse(is_temp)
        self.assertEqual(info["final_px"], "3000x1000")
        self.assertFalse(info["cropped_to_instagram_frame"])

    def test_named_frames_still_scale_to_1080(self):
        src = _save("big.jpg", (4000, 5000), "JPEG")
        out, _, info = srv._prepare_feed_image(src, "portrait")
        with Image.open(out) as im:
            self.assertEqual(im.size, (1080, 1350))
        self.assertTrue(info["resized"])

    def test_over_8mb_lowers_quality_only_as_far_as_needed(self):
        src = _save("gradient.png", (800, 800), "PNG")
        old = os.environ.get("INSTAGRAM_MCP_MAX_IMAGE_BYTES")
        os.environ["INSTAGRAM_MCP_MAX_IMAGE_BYTES"] = "60000"
        try:
            out, is_temp, info = srv._prepare_feed_image(src, "auto")
        finally:
            if old is None:
                os.environ.pop("INSTAGRAM_MCP_MAX_IMAGE_BYTES", None)
            else:
                os.environ["INSTAGRAM_MCP_MAX_IMAGE_BYTES"] = old
        self.assertTrue(is_temp)
        self.assertGreaterEqual(info["quality"], 90)
        with Image.open(out) as im:
            self.assertEqual(im.size, (800, 800))  # dimensions never change


if __name__ == "__main__":
    unittest.main()
