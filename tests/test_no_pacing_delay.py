"""Write actions run without an artificial pause by default.

Env overrides (INSTAGRAM_MCP_*_DELAY_MIN/_MAX), safe mode, and the optional request pause still work.
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from instagram_mcp_server import instagram_client, mcp_server as srv  # noqa: E402

KINDS = ("comment", "reply", "post", "like", "social", "dm", "engage", "save")


def _clean_env(extra=None):
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("INSTAGRAM_MCP_") and ("DELAY" in k or "SAFE_MODE" in k or "MAX_WRITES" in k))}
    env.update(extra or {})
    return mock.patch.dict(os.environ, env, clear=True)


class DefaultPacingTests(unittest.TestCase):
    def test_no_action_pauses_by_default(self):
        with _clean_env(), mock.patch.object(srv, "_count_write"), mock.patch.object(srv.time, "sleep") as sleep:
            for kind in KINDS:
                self.assertEqual(srv._pace_action(kind), 0, kind)
        sleep.assert_not_called()

    def test_an_explicit_env_range_still_pauses(self):
        with _clean_env({"INSTAGRAM_MCP_POST_DELAY_MIN": "2", "INSTAGRAM_MCP_POST_DELAY_MAX": "2"}), \
                mock.patch.object(srv, "_count_write"), mock.patch.object(srv.time, "sleep") as sleep:
            self.assertEqual(srv._pace_action("post"), 2)
        sleep.assert_called_once_with(2.0)

    def test_safe_mode_still_adds_long_pauses(self):
        with _clean_env({"INSTAGRAM_MCP_SAFE_MODE": "1"}), \
                mock.patch.object(srv, "_count_write"), mock.patch.object(srv.time, "sleep") as sleep:
            waited = srv._pace_action("post")
        self.assertTrue(300 <= waited <= 900, waited)
        sleep.assert_called_once()


class RequestPauseTests(unittest.TestCase):
    def test_request_pause_is_off_by_default(self):
        with _clean_env():
            self.assertEqual(instagram_client._request_delay_range(), [0, 0.0])

    def test_request_pause_can_be_turned_on(self):
        with _clean_env({"INSTAGRAM_MCP_REQUEST_DELAY_MAX": "1.5"}):
            self.assertEqual(instagram_client._request_delay_range(), [0, 1.5])

    def test_a_bad_value_means_no_pause(self):
        with _clean_env({"INSTAGRAM_MCP_REQUEST_DELAY_MAX": "soon"}):
            self.assertEqual(instagram_client._request_delay_range(), [0, 0.0])


if __name__ == "__main__":
    unittest.main()
