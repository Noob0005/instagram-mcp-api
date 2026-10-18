"""Extension artifacts: embedded copy matches public/extension, and the zips carry the right config."""
import base64
import io
import json
import os
import sys
import unittest
import zipfile

VERCEL = os.path.join(os.path.dirname(__file__), "..", "vercel-api")
sys.path.insert(0, VERCEL)

from admin_ui import extension_files, extension_pack  # noqa: E402


class ExtensionArtifactTests(unittest.TestCase):
    def test_embedded_files_match_public_folder(self):
        src = os.path.join(VERCEL, "public", "extension")
        for name, b64 in extension_files.FILES.items():
            with open(os.path.join(src, name), "rb") as fh:
                self.assertEqual(base64.b64decode(b64), fh.read(),
                                 f"{name} changed: run python vercel-api/build_extension.py")

    def test_configured_zip_contains_defaults(self):
        data = extension_pack.build("https://x.example", "mcpkey-1234567890abcdefghijklmnop", "a" * 43 + "=")
        z = zipfile.ZipFile(io.BytesIO(data))
        cfg = json.loads(z.read("defaults.json"))
        self.assertEqual(cfg["serverUrl"], "https://x.example")
        self.assertEqual(cfg["mcpKey"], "mcpkey-1234567890abcdefghijklmnop")
        self.assertIn("manifest.json", z.namelist())
        self.assertIn("CONFIGURED COPY", z.read("README.md").decode())

    def test_unconfigured_zip_has_no_keys(self):
        data = extension_pack.build("", "", "", configured=False)
        z = zipfile.ZipFile(io.BytesIO(data))
        self.assertNotIn("defaults.json", z.namelist())
        self.assertNotIn("CONFIGURED COPY", z.read("README.md").decode())


if __name__ == "__main__":
    unittest.main()
