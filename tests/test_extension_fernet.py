"""Cross-language check: the browser extension's Fernet token must decrypt in Python.

Skipped when Node.js is not installed. Runs the real vercel-api/public/extension/fernet.js.
"""
import json
import os
import shutil
import subprocess
import unittest

from cryptography.fernet import Fernet

HERE = os.path.dirname(__file__)
FERNET_JS = os.path.join(HERE, "..", "vercel-api", "public", "extension", "fernet.js")
NODE = shutil.which("node")

_DRIVER = """
const fs = require('fs'), vm = require('vm');
const ctx = { crypto: globalThis.crypto, TextEncoder, TextDecoder, atob, btoa, Date, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
ctx.fernetEncrypt(process.argv[3], process.argv[2]).then(t => process.stdout.write(t));
"""


@unittest.skipUnless(NODE, "node is not installed")
class ExtensionFernetTests(unittest.TestCase):
    def _encrypt_in_browser_code(self, key: str, plain: str) -> str:
        out = subprocess.run([NODE, "-e", _DRIVER, FERNET_JS, key, plain],
                             capture_output=True, text=True, timeout=60, check=True)
        return out.stdout.strip()

    def test_browser_token_decrypts_with_server_key(self):
        key = Fernet.generate_key().decode()
        payload = json.dumps({"sessionid": "abc%3Adef", "username": "demo"})
        token = self._encrypt_in_browser_code(key, payload)
        self.assertEqual(json.loads(Fernet(key.encode()).decrypt(token.encode()).decode()), json.loads(payload))

    def test_wrong_key_does_not_decrypt(self):
        from cryptography.fernet import InvalidToken
        key = Fernet.generate_key().decode()
        token = self._encrypt_in_browser_code(key, "{}")
        with self.assertRaises(InvalidToken):
            Fernet(Fernet.generate_key()).decrypt(token.encode())


if __name__ == "__main__":
    unittest.main()
