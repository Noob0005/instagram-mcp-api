"""Unit tests for the Instagram MCP helper layer (no network access).

Run with:  python -m unittest discover -s tests
"""

import ast
import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

# Make the test suite fast, offline and hermetic: instant pacing, no saved
# session and no .env auto-login while importing the server module.
os.environ["INSTAGRAM_MCP_SESSION_PATH"] = os.path.join(tempfile.gettempdir(), "ig_mcp_test_session_missing.json")
os.environ["INSTAGRAM_MCP_SESSIONID"] = ""
os.environ["INSTAGRAM_MCP_COMMENT_DELAY_MIN"] = "0"
os.environ["INSTAGRAM_MCP_COMMENT_DELAY_MAX"] = "0"
os.environ["INSTAGRAM_MCP_POST_DELAY_MIN"] = "0"
os.environ["INSTAGRAM_MCP_POST_DELAY_MAX"] = "0"
os.environ["INSTAGRAM_MCP_ACTION_DELAY_MIN"] = "0"
os.environ["INSTAGRAM_MCP_ACTION_DELAY_MAX"] = "0"
os.environ["INSTAGRAM_MCP_LIKE_DELAY_MIN"] = "0"
os.environ["INSTAGRAM_MCP_LIKE_DELAY_MAX"] = "0"
os.environ["INSTAGRAM_MCP_SOCIAL_DELAY_MIN"] = "0"
os.environ["INSTAGRAM_MCP_SOCIAL_DELAY_MAX"] = "0"
os.environ["INSTAGRAM_MCP_DM_DELAY_MIN"] = "0"
os.environ["INSTAGRAM_MCP_DM_DELAY_MAX"] = "0"
# Keep test runs away from the real counters/dedupe state in the home folder
os.environ["INSTAGRAM_MCP_WRITE_COUNT_PATH"] = os.path.join(tempfile.gettempdir(), "ig_mcp_test_write_counts.json")
os.environ["INSTAGRAM_MCP_DEDUPE_PATH"] = os.path.join(tempfile.gettempdir(), "ig_mcp_test_recent_actions.json")
for _path in (os.environ["INSTAGRAM_MCP_WRITE_COUNT_PATH"], os.environ["INSTAGRAM_MCP_DEDUPE_PATH"]):
    try:
        os.remove(_path)
    except OSError:
        pass

# Never read the developer's real .env during tests and never attempt a login on
# import: point env loading at an empty file and blank the credential variables.
_EMPTY_ENV = os.path.join(tempfile.gettempdir(), "ig_mcp_test_empty.env")
with open(_EMPTY_ENV, "w", encoding="utf-8"):
    pass
os.environ["INSTAGRAM_MCP_ENV_FILE"] = _EMPTY_ENV
os.environ["INSTAGRAM_MCP_USERNAME"] = ""
os.environ["INSTAGRAM_MCP_PASSWORD"] = ""
os.environ["INSTAGRAM_MCP_2FA_CODE"] = ""
os.environ.pop("INSTAGRAM_MCP_SESSION_JSON", None)

# A previous run may have left a real session behind at the test session path —
# delete it so no test ever reuses (or renews) a live Instagram session.
try:
    os.remove(os.environ["INSTAGRAM_MCP_SESSION_PATH"])
except OSError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from instagram_mcp_server import mcp_server as srv  # noqa: E402


class CaptionTests(unittest.TestCase):
    def test_mentions_and_hashtags_appended(self):
        self.assertEqual(
            srv._build_caption("Hello", "#a, b", "nasa, @google"),
            "Hello\n\n@nasa @google\n\n#a #b",
        )

    def test_empty_caption(self):
        self.assertEqual(srv._build_caption(None, None, None), "")

    def test_only_hashtags(self):
        self.assertEqual(srv._build_caption("", "ai", None), "#ai")


class ImageNormalizationTests(unittest.TestCase):
    def test_png_with_alpha_becomes_jpeg(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "art.png"
            Image.new("RGBA", (64, 64), (255, 0, 0, 128)).save(png)
            out, created = srv._normalize_image_for_upload(png)
            self.assertTrue(created)
            self.assertTrue(out.lower().endswith(".jpg"))
            with Image.open(out) as im:
                self.assertEqual(im.mode, "RGB")
            os.remove(out)

    def test_small_jpeg_passes_through(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            jpg = Path(tmp) / "photo.jpg"
            Image.new("RGB", (100, 100), (1, 2, 3)).save(jpg, format="JPEG")
            out, created = srv._normalize_image_for_upload(jpg)
            self.assertFalse(created)
            self.assertEqual(out, str(jpg))


class ResolveImageSourceTests(unittest.TestCase):
    def test_missing_file_raises_clear_error(self):
        missing = os.path.join(tempfile.gettempdir(), "definitely_missing_image_12345.png")
        with self.assertRaises(FileNotFoundError):
            srv._resolve_image_source(missing)

    def test_file_uri_supported(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "x.jpg"
            Image.new("RGB", (10, 10), (0, 0, 0)).save(img, format="JPEG")
            out, created = srv._resolve_image_source(img.as_uri())
            self.assertTrue(os.path.exists(out))
            if created:
                os.remove(out)


class PacingTests(unittest.TestCase):
    def tearDown(self):
        srv._COMMENT_HISTORY.clear()
        srv._ACTION_LOCK_UNTIL = 0.0
        os.environ.pop("INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR", None)

    def test_comment_hourly_cap_blocks(self):
        os.environ["INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR"] = "2"
        srv._pace_action("comment")
        srv._pace_action("comment")
        self.assertIsNotNone(srv._pacing_error("comment"))

    def test_rate_limit_arms_global_pause(self):
        msg = srv._friendly_error(Exception("feedback_required"), "commenting")
        self.assertIn("blocked", msg.lower())
        self.assertIsNotNone(srv._pacing_error("engage"))


class CommentRangeTests(unittest.TestCase):
    class _FakeUser:
        def __init__(self, name):
            self.username = name

    class _FakeComment:
        def __init__(self, pk):
            self.pk = pk
            self.text = f"c{pk}"
            self.like_count = 0
            self.created_at_utc = None
            self.replied_to_comment_id = None
            self.user = CommentRangeTests._FakeUser(f"user{pk}")

    def test_window_slicing_23_to_44(self):
        fake = [self._FakeComment(i) for i in range(1, 51)]

        class FakeCl:
            def media_comments_chunk(self, media_id, max_amount=0, min_id=None):
                start = int(min_id or 0)
                chunk = fake[start:start + max_amount]
                nxt = start + max_amount if start + max_amount < len(fake) else None
                return chunk, nxt

            def media_comments(self, media_id, amount):
                return fake[:amount]

        original = srv.ig.cl
        srv.ig.cl = FakeCl()
        try:
            items = srv._fetch_comments_upto("123", 44)
            window = items[22:44]
            self.assertEqual([c.pk for c in window], list(range(23, 45)))
            self.assertEqual(srv._fmt_comment(window[0])["comment_id"], "23")
        finally:
            srv.ig.cl = original

    def test_short_post_returns_available(self):
        fake = [self._FakeComment(i) for i in range(1, 6)]

        class FakeCl:
            def media_comments_chunk(self, media_id, max_amount=0, min_id=None):
                return fake, None

            def media_comments(self, media_id, amount):
                return fake

        original = srv.ig.cl
        srv.ig.cl = FakeCl()
        try:
            items = srv._fetch_comments_upto("123", 20)
            self.assertEqual(len(items), 5)
        finally:
            srv.ig.cl = original


class ToolLevelTests(unittest.TestCase):
    """Exercise the actual tool functions with a fake instagrapi client."""

    class _FakeUser:
        def __init__(self, name="tester"):
            self.username = name

    class _FakeComment:
        def __init__(self, pk):
            self.pk = pk
            self.text = f"c{pk}"
            self.like_count = 3
            self.created_at_utc = None
            self.replied_to_comment_id = None
            self.user = ToolLevelTests._FakeUser()

    def setUp(self):
        srv._COMMENT_HISTORY.clear()
        srv._ACTION_LOCK_UNTIL = 0.0
        srv._login_cache["ok"] = True
        srv._login_cache["checked_at"] = time.monotonic()

    def tearDown(self):
        srv._login_cache["ok"] = False
        srv._login_cache["checked_at"] = 0.0
        srv._COMMENT_HISTORY.clear()
        srv._ACTION_LOCK_UNTIL = 0.0

    def test_comments_range_tool_returns_window(self):
        fake = [self._FakeComment(i) for i in range(1, 51)]

        class FakeCl:
            def media_comments_chunk(self, media_id, max_amount=0, min_id=None):
                start = int(min_id or 0)
                chunk = fake[start:start + max_amount]
                nxt = start + max_amount if start + max_amount < len(fake) else None
                return chunk, nxt

            def media_comments(self, media_id, amount):
                return fake[:amount]

            def media_pk_from_url(self, url):
                return "18000000000000000"

            def media_id(self, pk):
                return f"{pk}_1"

        original = srv.ig.cl
        srv.ig.cl = FakeCl()
        try:
            out = srv.instagram_get_post_comments_range("https://www.instagram.com/p/ABC123/", 23, 44)
            self.assertIn("'comment_id': '23'", out)
            self.assertIn("'returned_count': 22", out)
            self.assertIn("'next_start_index': 45", out)
        finally:
            srv.ig.cl = original

    def test_reply_rejects_non_numeric_comment_id(self):
        out = srv.instagram_reply_to_comment("12345", "abc", "hello")
        self.assertIn("numeric ID", out)

    def test_comment_on_post_reports_comment_id(self):
        class FakeComment:
            pk = 999

        class FakeCl:
            def media_comment(self, mid, text):
                return FakeComment()

            def media_pk_from_url(self, url):
                return "18000000000000000"

            def media_id(self, pk):
                return f"{pk}_1"

        original = srv.ig.cl
        srv.ig.cl = FakeCl()
        try:
            out = srv.instagram_comment_on_post("https://www.instagram.com/reel/XYZ987/", "nice!")
            self.assertIn("'comment_id': '999'", out)
            self.assertIn("paced_seconds", out)
        finally:
            srv.ig.cl = original


    def test_comments_sorted_by_likes(self):
        class FakeComment:
            def __init__(self, pk, likes):
                self.pk = pk
                self.text = f"c{pk}"
                self.like_count = likes
                self.created_at_utc = None
                self.replied_to_comment_id = None
                self.user = type("U", (), {"username": f"u{pk}"})()

        comments = [FakeComment(1, 2), FakeComment(2, 9), FakeComment(3, 5)]

        class FakeCl:
            def media_comments(self, mid, amount):
                return comments

            def media_pk_from_url(self, url):
                return "18000000000000000"

            def media_id(self, pk):
                return f"{pk}_1"

        original = srv.ig.cl
        srv.ig.cl = FakeCl()
        try:
            out = srv.instagram_get_post_comments("123", 10, "likes")
            self.assertLess(out.find("'comment_id': '2'"), out.find("'comment_id': '3'"))
            self.assertLess(out.find("'comment_id': '3'"), out.find("'comment_id': '1'"))
        finally:
            srv.ig.cl = original


    def test_reply_by_username_finds_and_replies(self):
        class FakeComment:
            def __init__(self, pk, username, text):
                self.pk = pk
                self.user = type("U", (), {"username": username})()
                self.text = text
                self.like_count = 0
                self.created_at_utc = None
                self.replied_to_comment_id = None

        comments = [
            FakeComment(11, "someone_else", "hello"),
            FakeComment(22, "target_user", "lol nice"),
            FakeComment(33, "target_user", "second one"),
        ]

        class FakeCl:
            def media_comments_chunk(self, media_id, max_amount=0, min_id=None):
                return comments, None

            def media_comment(self, mid, text, replied_to_comment_id=None):
                self.last = (mid, text, replied_to_comment_id)
                return type("C", (), {"pk": 999})()

        fake = FakeCl()
        original = srv.ig.cl
        srv.ig.cl = fake
        try:
            out = srv.instagram_reply_to_comment_by_username("123", "@target_user", "sarcastic reply")
            self.assertIn("'reply_id': '999'", out)
            self.assertIn("'replied_to_comment_id': '22'", out)
            self.assertEqual(fake.last, ("123", "sarcastic reply", 22))
        finally:
            srv.ig.cl = original

    def test_post_photo_dry_run_builds_caption_without_upload(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "a.png"
            Image.new("RGB", (10, 10)).save(img_path)

            class FakeCl:
                def photo_upload(self, *a, **k):
                    raise AssertionError("upload must not be called in dry_run")

            original = srv.ig.cl
            srv.ig.cl = FakeCl()
            try:
                out = srv.instagram_post_photo(
                    image_path_or_url=str(img_path), caption="Draft caption",
                    hashtags="ai, art", dry_run=True,
                )
                self.assertIn("'status': 'preview'", out)
                self.assertIn("Draft caption", out)
                self.assertIn("#ai #art", out)
            finally:
                srv.ig.cl = original

    def test_recent_comments_excludes_self(self):
        class FakeComment:
            def __init__(self, pk, username):
                self.pk = pk
                self.user = type("U", (), {"username": username})()
                self.text = "x"
                self.like_count = 0
                self.created_at_utc = None
                self.replied_to_comment_id = None

        class Media:
            id = "5_1"
            code = "abc"
            comment_count = 2
            caption_text = "cap"

        class FakeCl:
            user_id = "45651746757"

            def user_medias(self, uid, amount):
                return [Media()]

            def media_comments(self, mid, amount):
                return [FakeComment(1, "me_user"), FakeComment(2, "other_user")]

        original_cl = srv.ig.cl
        original_username = srv.ig.username
        srv.ig.cl = FakeCl()
        srv.ig.username = "me_user"
        try:
            out = srv.instagram_get_recent_comments(1, 10, True)
            self.assertIn("other_user", out)
            self.assertNotIn("me_user", out)
        finally:
            srv.ig.cl = original_cl
            srv.ig.username = original_username


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        srv._login_cache["ok"] = True
        srv._login_cache["checked_at"] = time.monotonic()
        self._orig_queue = srv._QUEUE_PATH
        self._tmp = tempfile.TemporaryDirectory()
        srv._QUEUE_PATH = os.path.join(self._tmp.name, "queue.json")

    def tearDown(self):
        srv._QUEUE_PATH = self._orig_queue
        srv._login_cache["ok"] = False
        srv._login_cache["checked_at"] = 0.0
        self._tmp.cleanup()

    def test_parse_schedule_time_naive_gets_timezone(self):
        dt = srv._parse_schedule_time("2030-01-02 03:04")
        self.assertIsNotNone(dt.tzinfo)

    def test_schedule_and_cancel_flow(self):
        from PIL import Image
        img_path = Path(self._tmp.name) / "sched.png"
        Image.new("RGB", (10, 10)).save(img_path)

        out = srv.instagram_schedule_post(str(img_path), "Scheduled caption", "2030-01-02 03:04", hashtags="ai")
        self.assertIn("'status': 'scheduled'", out)

        item = ast.literal_eval(srv.instagram_get_scheduled_posts())["items"][0]
        queue_id = item["id"]
        self.assertEqual(item["kind"], "post")

        refused = srv.instagram_cancel_scheduled_post(queue_id, confirm=True)
        self.assertIn("Refused", refused)

        preview = srv.instagram_cancel_scheduled_post(queue_id, confirm=False)
        self.assertIn("'status': 'preview'", preview)

        done = srv.instagram_cancel_scheduled_post(queue_id, confirm=True)
        self.assertIn("cancelled", done)
        self.assertEqual(ast.literal_eval(srv.instagram_get_scheduled_posts())["count"], 0)


class DeleteConfirmationTests(unittest.TestCase):
    def setUp(self):
        srv._login_cache["ok"] = True
        srv._login_cache["checked_at"] = time.monotonic()
        srv._PENDING_CONFIRMATIONS.clear()

    def tearDown(self):
        srv._login_cache["ok"] = False
        srv._login_cache["checked_at"] = 0.0
        srv._PENDING_CONFIRMATIONS.clear()

    def test_delete_post_refuses_without_preview(self):
        class FakeCl:
            def media_delete(self, mid):
                raise AssertionError("must not delete without a preview")

        original = srv.ig.cl
        srv.ig.cl = FakeCl()
        try:
            out = srv.instagram_delete_post("123", confirm=True)
            self.assertIn("Refused", out)
        finally:
            srv.ig.cl = original


class EnvReloginTests(unittest.TestCase):
    def setUp(self):
        os.environ["INSTAGRAM_MCP_USERNAME"] = "user"
        os.environ["INSTAGRAM_MCP_PASSWORD"] = "secret"
        srv._last_relogin_attempt = 0.0
        srv._login_cache["ok"] = False
        srv._login_cache["checked_at"] = 0.0

    def tearDown(self):
        os.environ.pop("INSTAGRAM_MCP_PASSWORD", None)
        os.environ.pop("INSTAGRAM_MCP_USERNAME", None)
        srv._last_relogin_attempt = 0.0
        srv._login_cache["ok"] = False
        srv._login_cache["checked_at"] = 0.0

    def test_require_login_recovers_with_env_password(self):
        calls = {}

        class FakeIG:
            def is_logged_in(self):
                return False

            def login_with_credentials(self, u, p, verification_code=None):
                calls["cred"] = (u, p, verification_code)
                return {"status": "success"}

        original = srv.ig
        srv.ig = FakeIG()
        try:
            self.assertIsNone(srv._require_login())
            self.assertEqual(calls["cred"], ("user", "secret", None))
            self.assertTrue(srv._login_cache["ok"])
        finally:
            srv.ig = original

    def test_relogin_attempt_is_throttled(self):
        class FakeIG:
            def __init__(self):
                self.attempts = 0

            def is_logged_in(self):
                return False

            def login_with_credentials(self, u, p, verification_code=None):
                self.attempts += 1
                return {"status": "error"}

        fake = FakeIG()
        original = srv.ig
        srv.ig = fake
        try:
            srv._require_login()
            srv._require_login()
            self.assertEqual(fake.attempts, 1)
        finally:
            srv.ig = original


class SafetyModeTests(unittest.TestCase):
    def setUp(self):
        self._orig_count_path = srv._WRITE_COUNT_PATH
        self._tmp = tempfile.TemporaryDirectory()
        srv._WRITE_COUNT_PATH = os.path.join(self._tmp.name, "counts.json")
        srv._COMMENT_HISTORY.clear()
        srv._ACTION_LOCK_UNTIL = 0.0
        srv._login_cache["ok"] = False
        srv._login_cache["checked_at"] = 0.0

    def tearDown(self):
        srv._WRITE_COUNT_PATH = self._orig_count_path
        self._tmp.cleanup()
        for name in ("INSTAGRAM_MCP_SAFE_MODE", "INSTAGRAM_MCP_MAX_WRITES_PER_DAY",
                     "INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR"):
            os.environ.pop(name, None)
        srv._COMMENT_HISTORY.clear()

    def test_safe_mode_conservative_caps(self):
        os.environ["INSTAGRAM_MCP_SAFE_MODE"] = "1"
        self.assertEqual(srv._comment_hourly_cap(), 3)
        self.assertEqual(srv._daily_write_cap(), 25)
        self.assertGreaterEqual(srv._login_cache_ttl(), 300.0)

    def test_explicit_env_overrides_safe_mode(self):
        os.environ["INSTAGRAM_MCP_SAFE_MODE"] = "1"
        os.environ["INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR"] = "7"
        self.assertEqual(srv._comment_hourly_cap(), 7)

    def test_daily_write_cap_blocks_after_limit(self):
        os.environ["INSTAGRAM_MCP_MAX_WRITES_PER_DAY"] = "1"
        self.assertIsNone(srv._pacing_error("engage"))
        srv._pace_action("engage")
        msg = srv._pacing_error("engage")
        self.assertIsNotNone(msg)
        self.assertIn("cap reached", msg)


class RiskCategoryTests(unittest.TestCase):
    def setUp(self):
        self._orig_count_path = srv._WRITE_COUNT_PATH
        self._tmp = tempfile.TemporaryDirectory()
        srv._WRITE_COUNT_PATH = os.path.join(self._tmp.name, "counts.json")
        srv._login_cache["ok"] = False
        srv._login_cache["checked_at"] = 0.0

    def tearDown(self):
        srv._WRITE_COUNT_PATH = self._orig_count_path
        self._tmp.cleanup()
        os.environ.pop("INSTAGRAM_MCP_MAX_RED_ACTIONS_PER_DAY", None)

    def test_registry_names_match_real_tools(self):
        tool_names = [n for n, v in vars(srv).items() if n.startswith("instagram_") and callable(v)]
        unknown = [n for n in list(srv._TOOL_RISK_RED) + list(srv._TOOL_RISK_ORANGE) if n not in tool_names]
        self.assertEqual(unknown, [])
        self.assertIn("instagram_comment_on_post", srv._TOOL_RISK_RED)
        self.assertIn("instagram_post_photo", srv._TOOL_RISK_ORANGE)

    def test_red_cap_blocks_red_actions_only(self):
        os.environ["INSTAGRAM_MCP_MAX_RED_ACTIONS_PER_DAY"] = "1"
        self.assertIsNone(srv._pacing_error("like"))
        srv._pace_action("like")
        msg = srv._pacing_error("like")
        self.assertIn("Red-category daily cap", msg)
        self.assertIsNone(srv._pacing_error("post"))

    def test_red_counter_increments(self):
        srv._pace_action("social")
        srv._pace_action("engage")
        rec = srv._load_write_count()
        self.assertEqual(rec["count"], 2)
        self.assertEqual(rec["red"], 1)


class DedupeGuardTests(unittest.TestCase):
    def setUp(self):
        self._orig = srv._DEDUPE_PATH
        self._tmp = tempfile.TemporaryDirectory()
        srv._DEDUPE_PATH = os.path.join(self._tmp.name, "recent.json")

    def tearDown(self):
        srv._DEDUPE_PATH = self._orig
        self._tmp.cleanup()
        os.environ.pop("INSTAGRAM_MCP_DEDUPE_WINDOW", None)

    def test_duplicate_is_blocked(self):
        self.assertIsNone(srv._dedupe_guard("dm", "alice", "hello"))
        msg = srv._dedupe_guard("dm", "alice", "hello")
        self.assertIn("Duplicate suppressed", msg)
        self.assertIsNone(srv._dedupe_guard("dm", "alice", "different text"))
        self.assertIsNone(srv._dedupe_guard("dm", "bob", "hello"))

    def test_window_zero_disables(self):
        os.environ["INSTAGRAM_MCP_DEDUPE_WINDOW"] = "0"
        self.assertIsNone(srv._dedupe_guard("dm", "alice", "hi"))
        self.assertIsNone(srv._dedupe_guard("dm", "alice", "hi"))

    def test_expired_entry_allows_again(self):
        os.environ["INSTAGRAM_MCP_DEDUPE_WINDOW"] = "0.01"
        self.assertIsNone(srv._dedupe_guard("dm", "alice", "yo"))
        time.sleep(0.05)
        self.assertIsNone(srv._dedupe_guard("dm", "alice", "yo"))


class ServerlessSupportTests(unittest.TestCase):
    def test_state_dir_uses_tempdir_when_serverless(self):
        original = srv._IS_SERVERLESS
        try:
            srv._IS_SERVERLESS = True
            self.assertEqual(srv._state_dir(), tempfile.gettempdir())
            srv._IS_SERVERLESS = False
            self.assertEqual(srv._state_dir(), os.path.expanduser("~"))
        finally:
            srv._IS_SERVERLESS = original

    def test_session_settings_from_env(self):
        from instagram_mcp_server import instagram_client as ic
        os.environ["INSTAGRAM_MCP_SESSION_JSON"] = '{"uuids": {"phone": "x"}}'
        try:
            self.assertEqual(ic._session_settings_from_env(), {"uuids": {"phone": "x"}})
        finally:
            os.environ.pop("INSTAGRAM_MCP_SESSION_JSON", None)
        self.assertIsNone(ic._session_settings_from_env())
        os.environ["INSTAGRAM_MCP_SESSION_JSON"] = "not json"
        try:
            self.assertIsNone(ic._session_settings_from_env())
        finally:
            os.environ.pop("INSTAGRAM_MCP_SESSION_JSON", None)


class LocationFallbackTests(unittest.TestCase):
    def setUp(self):
        self._orig = srv.ig.cl

    def tearDown(self):
        srv.ig.cl = self._orig

    def test_prefers_location_search_name(self):
        class FakeCl:
            def location_search_name(self, name):
                return ["NEW"]

            def location_search(self, name):
                raise AssertionError("legacy fallback must not run when the 3.x API exists")

        srv.ig.cl = FakeCl()
        self.assertEqual(srv._search_locations_by_name("Paris"), ["NEW"])

    def test_falls_back_to_legacy_location_search(self):
        calls = {}

        class FakeCl:
            def location_search(self, name):
                calls["name"] = name
                return ["LEGACY"]

        srv.ig.cl = FakeCl()
        self.assertEqual(srv._search_locations_by_name("Paris"), ["LEGACY"])
        self.assertEqual(calls["name"], "Paris")

    def test_get_location_handles_empty_and_none(self):
        class EmptyCl:
            def location_search_name(self, name):
                return []

        srv.ig.cl = EmptyCl()
        self.assertIsNone(srv._get_location("Nowhere"))
        self.assertIsNone(srv._get_location(None))


class ServeAuthGateTests(unittest.TestCase):
    """scripts/serve.py — the shared-key gate used when tunnelling the server."""

    @staticmethod
    def _scope(header=b"", query=b""):
        headers = []
        if header:
            name, _, value = header.partition(b":")
            headers.append((name.lower().strip(), value.strip()))
        return {"type": "http", "path": "/mcp", "headers": headers, "query_string": query}

    def setUp(self):
        import scripts.serve as serve
        self.serve = serve
        self._orig = os.environ.get("MCP_AUTH_KEY")
        os.environ["MCP_AUTH_KEY"] = "test-key-123"
        os.environ.pop("MCP_ALLOW_UNAUTHENTICATED", None)

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("MCP_AUTH_KEY", None)
        else:
            os.environ["MCP_AUTH_KEY"] = self._orig
        os.environ.pop("MCP_ALLOW_UNAUTHENTICATED", None)

    def test_accepts_query_param_bearer_and_header(self):
        self.assertTrue(self.serve._authorized(self._scope(query=b"auth=test-key-123")))
        self.assertTrue(self.serve._authorized(self._scope(header=b"Authorization: Bearer test-key-123")))
        self.assertTrue(self.serve._authorized(self._scope(header=b"X-Auth-Key: test-key-123")))

    def test_rejects_wrong_or_missing_key(self):
        self.assertFalse(self.serve._authorized(self._scope(query=b"auth=nope")))
        self.assertFalse(self.serve._authorized(self._scope(header=b"Authorization: Bearer nope")))
        self.assertFalse(self.serve._authorized(self._scope()))

    def test_missing_key_fails_closed(self):
        os.environ.pop("MCP_AUTH_KEY", None)
        self.assertFalse(self.serve._authorized(self._scope(query=b"auth=test-key-123")))

    def test_allow_unauthenticated_escape_hatch(self):
        os.environ["MCP_ALLOW_UNAUTHENTICATED"] = "1"
        self.assertTrue(self.serve._authorized(self._scope()))


class SetupWizardTests(unittest.TestCase):
    """scripts/setup.py — .env editing helpers and preset/server consistency."""

    def setUp(self):
        import scripts.setup as setup
        self.setup = setup
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_env_path = setup.ENV_PATH
        setup.ENV_PATH = Path(self._tmp.name) / ".env"

    def tearDown(self):
        self.setup.ENV_PATH = self._orig_env_path
        self._tmp.cleanup()

    def test_roundtrip_write_and_read(self):
        s = self.setup
        s.write_env(["# comment", "KEEP=1"])
        lines = s.read_env_lines()
        self.assertEqual(s.env_value(lines, "KEEP"), "1")
        s.upsert(lines, "NEW", "value")
        s.write_env(lines)
        self.assertEqual(s.env_value(s.read_env_lines(), "NEW"), "value")

    def test_upsert_replaces_existing_key_once(self):
        s = self.setup
        lines = ["INSTAGRAM_MCP_USERNAME=old", "# x"]
        s.upsert(lines, "INSTAGRAM_MCP_USERNAME", "new")
        self.assertEqual(s.env_value(lines, "INSTAGRAM_MCP_USERNAME"), "new")
        self.assertEqual(len([ln for ln in lines if ln.startswith("INSTAGRAM_MCP_USERNAME=")]), 1)

    def test_remove_key_ignores_comments(self):
        s = self.setup
        lines = ["A=1", "B=2", "# B=3"]
        s.remove_key(lines, "B")
        self.assertEqual(lines, ["A=1", "# B=3"])

    def test_secret_label_never_shows_characters(self):
        label = self.setup.secret_label("abcdefghijklmnop")
        self.assertEqual(label, "******** (16 chars)")
        self.assertEqual(self.setup.secret_label(""), "(not set)")

    def test_preset_keys_are_read_by_the_server(self):
        source = Path(srv.__file__).read_text(encoding="utf-8")
        for key in self.setup.DELAY_PRESET_DEFAULT:
            self.assertIn(key, source, f"{key} is not used by the server")


class SetupBootstrapTests(unittest.TestCase):
    """scripts/setup.py — dependency check, auth key and secret masking."""

    def setUp(self):
        import scripts.setup as setup
        self.setup = setup

    def test_auth_key_is_strong_and_unique(self):
        first, second = self.setup.new_auth_key(), self.setup.new_auth_key()
        self.assertGreaterEqual(len(first), 24)
        self.assertNotEqual(first, second)

    def test_missing_dependencies_returns_list(self):
        missing = self.setup.missing_dependencies()
        self.assertIsInstance(missing, list)
        self.assertNotIn("fastmcp", missing)  # this environment has it installed

    def test_install_dry_run_never_shells_out(self):
        self.assertTrue(self.setup.install_dependencies(dry_run=True))

    def test_is_termux_is_bool(self):
        self.assertIsInstance(self.setup.is_termux(), bool)


class SetupMenuTests(unittest.TestCase):
    """scripts/setup.py — repeat-run menu: start with the saved setup or change it."""

    def setUp(self):
        import scripts.setup as setup
        self.setup = setup
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_env_path = setup.ENV_PATH
        setup.ENV_PATH = Path(self._tmp.name) / ".env"
        self._orig_argv = sys.argv

    def tearDown(self):
        self.setup.ENV_PATH = self._orig_env_path
        sys.argv = self._orig_argv
        self._tmp.cleanup()

    def _run(self, answers):
        setup = self.setup
        setup.sys.argv = ["setup.py"]
        out = io.StringIO()
        fake_stdin = io.StringIO("")
        fake_stdin.isatty = lambda: True
        with mock.patch.object(setup.sys, "stdin", fake_stdin), \
                mock.patch("builtins.input", side_effect=answers), \
                mock.patch.object(setup.getpass, "getpass", side_effect=answers), \
                mock.patch.object(setup.sys, "stdout", out):
            code = setup.main()
        return code, out.getvalue()

    def test_first_run_remembers_the_start_mode(self):
        answers = [
            "menu_user",                    # username
            "1",                            # sign in: session cookie
            "1234567890:abcdefghijklmnopqrstuvwxyz1234567890",  # sessionid
            "1",                            # auth key: generate
            "1",                            # pacing: defaults
            "2",                            # server mode: local HTTP
            "",                             # port -> 8080
            "y",                            # save
            "n",                            # skip login test
            "n",                            # don't start now
        ]
        code, out = self._run(answers)
        self.assertEqual(code, 0)
        env_text = self.setup.ENV_PATH.read_text(encoding="utf-8")
        self.assertIn("MCP_START_MODE=local", env_text)
        self.assertIn("MCP_START_PORT=8080", env_text)
        self.assertIn("http://127.0.0.1:8080/mcp", out)

    def test_second_run_starts_with_saved_setup_without_touching_env(self):
        env_text = (
            "INSTAGRAM_MCP_USERNAME=menu_user\n"
            "INSTAGRAM_MCP_SESSIONID=1234567890:abcdefghijklmnopqrstuvwxyz1234567890\n"
            "MCP_AUTH_KEY=saved-key-123\n"
            "MCP_START_MODE=stdio\n"
            "MCP_START_PORT=8080\n"
        )
        self.setup.ENV_PATH.write_text(env_text, encoding="utf-8")
        before = self.setup.ENV_PATH.read_bytes()

        code, out = self._run(["1"])  # menu: start with the saved setup

        self.assertEqual(code, 0)
        self.assertIn("saved mode: stdio", out)
        self.assertIn("instagram_mcp_server", out)          # client config printed
        self.assertEqual(self.setup.ENV_PATH.read_bytes(), before)
        self.assertNotIn("How should the server sign in?", out)  # wizard skipped


    def test_saved_local_mode_launches_the_server_command(self):
        self.setup.ENV_PATH.write_text(
            "INSTAGRAM_MCP_USERNAME=menu_user\nMCP_START_MODE=local\nMCP_START_PORT=9999\n",
            encoding="utf-8",
        )
        with mock.patch.object(self.setup.subprocess, "call") as fake_call:
            code, out = self._run(["1"])
        self.assertEqual(code, 0)
        command = fake_call.call_args[0][0]
        self.assertEqual(command[command.index("--port") + 1], "9999")
        self.assertIn("127.0.0.1", command)
        self.assertIn("http://127.0.0.1:9999/mcp", out)

    def test_saved_network_mode_uses_serve_py_with_the_auth_key(self):
        self.setup.ENV_PATH.write_text(
            "INSTAGRAM_MCP_USERNAME=menu_user\nMCP_AUTH_KEY=secret123\n"
            "MCP_START_MODE=network\nMCP_START_PORT=9000\n",
            encoding="utf-8",
        )
        with mock.patch.object(self.setup.subprocess, "call") as fake_call:
            code, out = self._run(["1"])
        self.assertEqual(code, 0)
        command = " ".join(fake_call.call_args[0][0])
        self.assertIn("serve.py", command)
        self.assertIn("0.0.0.0", command)
        self.assertIn("?auth=secret123", out)


    def test_saved_setup_without_a_mode_asks_once_and_remembers_it(self):
        self.setup.ENV_PATH.write_text("INSTAGRAM_MCP_USERNAME=menu_user\n", encoding="utf-8")
        with mock.patch.object(self.setup.subprocess, "call") as fake_call:
            code, out = self._run(["1", "2", ""])  # start saved → local HTTP → default port
        self.assertEqual(code, 0)
        env_text = self.setup.ENV_PATH.read_text(encoding="utf-8")
        self.assertIn("MCP_START_MODE=local", env_text)
        self.assertIn("MCP_START_PORT=8080", env_text)
        command = fake_call.call_args[0][0]
        self.assertEqual(command[command.index("--port") + 1], "8080")
        self.assertIn("KEEP THIS WINDOW OPEN", out)


    def test_detect_lan_ip_shape(self):
        lan = self.setup.detect_lan_ip()
        self.assertIsInstance(lan, str)
        if lan:  # empty string is allowed when there is no usable route (offline machine)
            self.assertRegex(lan, r"^\d{1,3}(\.\d{1,3}){3}$")


class NewToolTests(unittest.TestCase):
    """The comment/DM/story/note tools added for Instagram's newer features."""

    def setUp(self):
        srv._login_cache["ok"] = True
        srv._login_cache["checked_at"] = time.monotonic()
        srv._PENDING_CONFIRMATIONS.clear()
        self._orig = srv.ig.cl

    def tearDown(self):
        srv.ig.cl = self._orig
        srv._PENDING_CONFIRMATIONS.clear()

    def test_unlike_comment_calls_api(self):
        calls = []

        class FakeCl:
            def comment_unlike(self, pk):
                calls.append(pk)
                return True

        srv.ig.cl = FakeCl()
        out = srv.instagram_unlike_comment("12345")
        self.assertEqual(calls, ["12345"])
        self.assertIn("unliked", out.lower())

    def test_pin_and_unpin_comment(self):
        calls = []

        class FakeCl:
            def comment_pin(self, mid, cid):
                calls.append(("pin", mid, cid))
                return True

            def comment_unpin(self, mid, cid):
                calls.append(("unpin", mid, cid))
                return True

        srv.ig.cl = FakeCl()
        srv.instagram_pin_comment("123456789", "99", pin=True)
        srv.instagram_pin_comment("123456789", "99", pin=False)
        self.assertEqual(calls, [("pin", "123456789", "99"), ("unpin", "123456789", "99")])

    def test_check_comment_reports_offensive_flag(self):
        class FakeCl:
            def media_check_offensive_comment_v2(self, mid, text):
                return {"is_offensive": True, "reason": "slur"}

        srv.ig.cl = FakeCl()
        out = srv.instagram_check_comment("123456789", "bad text")
        self.assertIn("'is_offensive': True", out)

    def test_react_to_dm_add_and_remove(self):
        calls = []

        class FakeCl:
            def direct_send_reaction(self, tid, mid, emoji):
                calls.append(("add", tid, mid, emoji))
                return True

            def direct_delete_reaction(self, tid, mid, emoji):
                calls.append(("del", tid, mid, emoji))
                return True

        srv.ig.cl = FakeCl()
        srv.instagram_react_to_dm("111", "222", "🔥")
        srv.instagram_react_to_dm("111", "222", "🔥", remove=True)
        self.assertEqual([c[0] for c in calls], ["add", "del"])
        self.assertEqual(calls[0][3], "🔥")

    def test_unsend_dm_requires_preview_then_confirms(self):
        calls = []

        class FakeCl:
            def direct_message_unsend(self, tid, mid):
                calls.append((tid, mid))
                return True

        srv.ig.cl = FakeCl()
        preview = srv.instagram_unsend_dm("111", "222", confirm=False)
        self.assertIn("'status': 'preview'", preview)
        self.assertEqual(calls, [])
        refused = srv.instagram_unsend_dm("111", "999", confirm=True)
        self.assertIn("Refused", refused)
        done = srv.instagram_unsend_dm("111", "222", confirm=True)
        self.assertIn("unsent", done)
        self.assertEqual(calls, [(111, 222)])

    def test_mute_user_posts_and_stories_both_directions(self):
        calls = []

        class FakeCl:
            def user_id_from_username(self, u):
                return "42"

            def mute_posts_from_follow(self, uid):
                calls.append("mute-posts")

            def mute_stories_from_follow(self, uid):
                calls.append("mute-stories")

            def unmute_posts_from_follow(self, uid):
                calls.append("unmute-posts")

            def unmute_stories_from_follow(self, uid):
                calls.append("unmute-stories")

        srv.ig.cl = FakeCl()
        srv.instagram_mute_user("someone")
        srv.instagram_mute_user("someone", unmute=True)
        self.assertEqual(calls, ["mute-posts", "mute-stories", "unmute-posts", "unmute-stories"])

    def test_like_story_resolves_username_to_latest_story(self):
        class FakeStory:
            pk = "555"

        class FakeCl:
            def story_pk_from_url(self, value):
                raise ValueError("not a url")

            def user_id_from_username(self, u):
                return "42"

            def user_stories(self, uid):
                return [FakeStory()]

            def story_like(self, sid):
                self.liked = sid
                return True

        fake = FakeCl()
        srv.ig.cl = fake
        out = srv.instagram_like_story("@someone")
        self.assertEqual(fake.liked, "555")
        self.assertIn("555", out)

    def test_get_story_polls_lists_options(self):
        class FakeStory:
            pk = "777"
            polls = [{"poll_id": "p1", "question": "Coffee or tea?",
                      "options": [{"text": "Coffee"}, {"text": "Tea"}], "finished": False}]

        class FakeCl:
            def user_id_from_username(self, u):
                return "42"

            def user_stories(self, uid):
                return [FakeStory()]

        srv.ig.cl = FakeCl()
        out = srv.instagram_get_story_polls("someone")
        for expected in ("Coffee or tea?", "Coffee", "Tea", "p1", "777"):
            self.assertIn(expected, out)

    def test_create_and_delete_note(self):
        calls = []

        class FakeNote:
            id = 9

        class FakeCl:
            def create_note(self, text, audience=None):
                calls.append(("create", text))
                return FakeNote()

            def delete_note(self, note_id):
                calls.append(("delete", note_id))
                return True

        srv.ig.cl = FakeCl()
        out = srv.instagram_create_note("listening to lo-fi")
        self.assertIn("Note posted", out)
        srv.instagram_delete_note("9")
        self.assertEqual(calls[0][0], "create")
        self.assertEqual(calls[1], ("delete", 9))

    def test_every_new_tool_is_registered_and_risk_classified(self):
        names = ["instagram_unlike_comment", "instagram_pin_comment", "instagram_get_comment_likers",
                 "instagram_save_to_collection", "instagram_get_saved_collections",
                 "instagram_get_archived_posts", "instagram_add_to_highlight", "instagram_react_to_dm",
                 "instagram_unsend_dm", "instagram_mute_thread", "instagram_search_dm_messages",
                 "instagram_like_story", "instagram_get_story_polls", "instagram_vote_story_poll",
                 "instagram_mute_user", "instagram_remove_follower", "instagram_handle_follow_request",
                 "instagram_manage_close_friends", "instagram_follow_hashtag", "instagram_create_note",
                 "instagram_delete_note"]
        for name in names:
            with self.subTest(tool=name):
                self.assertTrue(callable(getattr(srv, name, None)), f"{name} is missing")
                self.assertTrue(name in srv._TOOL_RISK_RED or name in srv._TOOL_RISK_ORANGE,
                                f"{name} has no risk category")

    def test_safe_new_tools_stay_green(self):
        for name in ("instagram_check_comment", "instagram_get_notes"):
            self.assertNotIn(name, srv._TOOL_RISK_RED)
            self.assertNotIn(name, srv._TOOL_RISK_ORANGE)


class ImagePipelineTests(unittest.TestCase):
    """Feed image preparation (4:5, 1:1, auto-crop) + base64 / inbox image sources."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_inbox = os.environ.get("INSTAGRAM_MCP_INBOX")
        os.environ["INSTAGRAM_MCP_INBOX"] = self._tmp.name
        srv._login_cache["ok"] = True
        srv._login_cache["checked_at"] = time.monotonic()
        self._orig_cl = srv.ig.cl

    def tearDown(self):
        srv.ig.cl = self._orig_cl
        if self._orig_inbox is None:
            os.environ.pop("INSTAGRAM_MCP_INBOX", None)
        else:
            os.environ["INSTAGRAM_MCP_INBOX"] = self._orig_inbox
        self._tmp.cleanup()

    def _make(self, name, size):
        from PIL import Image
        path = Path(self._tmp.name) / name
        Image.new("RGB", size, (200, 30, 30)).save(path)
        return path

    def test_portrait_crops_to_4x5(self):
        from PIL import Image
        path = self._make("tall.png", (800, 1600))
        prepared, is_temp, info = srv._prepare_feed_image(path, "portrait")
        self.assertTrue(is_temp)
        self.assertTrue(info["cropped_to_instagram_frame"])
        with Image.open(prepared) as im:
            self.assertEqual(im.size, (800, 1000))
            self.assertAlmostEqual(im.width / im.height, 0.8, places=3)

    def test_square_and_landscape_modes(self):
        from PIL import Image
        tall = self._make("wide.png", (800, 1600))
        prepared, _, _ = srv._prepare_feed_image(tall, "square")
        with Image.open(prepared) as im:
            self.assertEqual(im.size, (800, 800))
        landscape_src = self._make("lsrc.png", (1080, 1920))
        prepared2, _, _ = srv._prepare_feed_image(landscape_src, "landscape")
        with Image.open(prepared2) as im:
            self.assertEqual(im.size, (1080, 565))  # 1080 / 1.91
            self.assertAlmostEqual(im.width / im.height, 1.91, places=2)

    def test_auto_keeps_valid_ratio_and_crops_extremes(self):
        path = self._make("valid.png", (1080, 1350))  # exactly 4:5
        prepared, _is_temp, info = srv._prepare_feed_image(path, "auto")
        self.assertEqual(info["original_px"], "1080x1350")
        self.assertEqual(info["final_px"], "1080x1350")
        self.assertFalse(info["cropped_to_instagram_frame"])

        extreme = self._make("pano.png", (2000, 500))  # 4:1 panorama
        prepared2, _, info2 = srv._prepare_feed_image(extreme, "auto")
        self.assertTrue(info2["cropped_to_instagram_frame"])
        self.assertAlmostEqual(info2["ratio"], 1.91, places=2)

    def test_data_uri_and_raw_base64_resolve(self):
        import base64
        import io as _io
        from PIL import Image
        buf = _io.BytesIO()
        Image.new("RGB", (60, 90), (10, 120, 200)).save(buf, format="PNG")
        blob = base64.b64encode(buf.getvalue()).decode()
        for value in (f"data:image/png;base64,{blob}", blob):
            local, cleanup = srv._resolve_image_source(value)
            self.assertTrue(cleanup)
            self.assertTrue(os.path.isfile(local))
            with Image.open(local) as im:
                self.assertEqual(im.size, (60, 90))
            srv._remove_file(local)

    def test_inbox_lookup_by_name_latest_and_nested(self):
        from PIL import Image
        older = self._make("older.png", (100, 100))
        self._make("newer.png", (120, 120))
        os.utime(older, (1, 1))

        def resolved_size(source):
            local, _cleanup = srv._resolve_image_source(source)
            self.assertTrue(os.path.isfile(local))
            with Image.open(local) as im:
                return im.size

        self.assertEqual(resolved_size("latest"), (120, 120))   # newest wins
        self.assertEqual(resolved_size("older.png"), (100, 100))  # by name

        nested = Path(self._tmp.name) / "sub"
        nested.mkdir()
        Image.new("RGB", (10, 10)).save(nested / "deep.png")
        self.assertEqual(resolved_size("deep.png"), (10, 10))   # found in subfolder

    def test_portrait_from_huge_source_lands_on_1080x1350(self):
        from PIL import Image
        source = self._make("huge.jpg", (2000, 2500))
        prepared, is_temp, info = srv._prepare_feed_image(source, "portrait")
        self.assertTrue(is_temp)
        self.assertTrue(info["resized"])
        with Image.open(prepared) as im:
            self.assertEqual(im.size, (1080, 1350))  # the classic tall feed post

    def test_missing_image_error_lists_the_four_options(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            srv._resolve_image_source("definitely-not-here.png")
        message = str(ctx.exception)
        for hint in ("absolute path", "http(s)", "base64", "inbox"):
            self.assertIn(hint, message)

    def test_post_photo_dry_run_reports_framing(self):
        class FakeCl:
            def photo_upload(self, *a, **k):
                raise AssertionError("must not upload in dry_run")

        path = self._make("art.png", (800, 1600))
        srv.ig.cl = FakeCl()
        out = srv.instagram_post_photo(str(path), "hi", aspect="portrait", dry_run=True)
        self.assertIn("'aspect_mode': 'portrait'", out)
        self.assertIn("'ratio': 0.8", out)  # framed as 4:5 before upload
        self.assertIn("'cropped_to_instagram_frame': True", out)

    def test_inspect_image_reports_every_mode(self):
        path = self._make("sq.png", (500, 500))
        out = srv.instagram_inspect_image(str(path), aspect="portrait")
        self.assertIn("would_upload_now", out)
        for mode in ("auto", "portrait", "square", "landscape", "keep"):
            self.assertIn(f"'{mode}'", out)


class ServeInboxTests(unittest.TestCase):
    """scripts/serve.py — the /inbox upload endpoint helpers."""

    def setUp(self):
        import scripts.serve as serve
        self.serve = serve
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_inbox = os.environ.get("INSTAGRAM_MCP_INBOX")
        os.environ["INSTAGRAM_MCP_INBOX"] = self._tmp.name

    def tearDown(self):
        if self._orig_inbox is None:
            os.environ.pop("INSTAGRAM_MCP_INBOX", None)
        else:
            os.environ["INSTAGRAM_MCP_INBOX"] = self._orig_inbox
        self._tmp.cleanup()

    def test_safe_filename_strips_paths_and_adds_extension(self):
        self.assertEqual(self.serve._safe_filename("../../evil.png"), "evil.png")
        self.assertEqual(self.serve._safe_filename("a b!.jpg"), "a_b_.jpg")
        self.assertEqual(self.serve._safe_filename("noext"), "noext.jpg")

    def test_json_payload_accepts_data_uri(self):
        import base64
        blob = b"\x89PNG\r\n\x1a\n-fake-image-bytes"
        payload = '{"filename":"pic.png","data":"data:image/png;base64,' + base64.b64encode(blob).decode() + '"}'
        got, name = self.serve._decode_inbox_payload("application/json", payload.encode(), "")
        self.assertEqual(got, blob)
        self.assertEqual(name, "pic.png")

    def test_raw_body_uses_query_name(self):
        got, name = self.serve._decode_inbox_payload("image/jpeg", b"\xff\xd8\xffraw", "name=snap.jpg")
        self.assertEqual(got, b"\xff\xd8\xffraw")
        self.assertEqual(name, "snap.jpg")

    def test_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            self.serve._decode_inbox_payload("application/json", b"not json", "")

    def test_body_size_cap(self):
        import asyncio

        async def scenario():
            messages = [
                {"type": "http.request", "body": b"x" * 100, "more_body": True},
                {"type": "http.request", "body": b"x" * 100, "more_body": False},
            ]

            async def receive():
                return messages.pop(0)

            return await self.serve._read_body(receive, 150)

        with self.assertRaises(ValueError):
            asyncio.run(scenario())

    def test_inbox_listing_is_newest_first(self):
        older = Path(self._tmp.name) / "a.png"
        older.write_bytes(b"1")
        Path(self._tmp.name, "b.png").write_bytes(b"22")
        os.utime(older, (1, 1))
        listing = self.serve._inbox_listing()
        self.assertEqual(listing[0]["name"], "b.png")
        self.assertEqual(len(listing), 2)


class InboxToolTests(unittest.TestCase):
    """instagram_upload_image / instagram_inbox_status — chat → local folder → Instagram."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_inbox = os.environ.get("INSTAGRAM_MCP_INBOX")
        os.environ["INSTAGRAM_MCP_INBOX"] = self._tmp.name
        srv._login_cache["ok"] = True
        srv._login_cache["checked_at"] = time.monotonic()

    def tearDown(self):
        if self._orig_inbox is None:
            os.environ.pop("INSTAGRAM_MCP_INBOX", None)
        else:
            os.environ["INSTAGRAM_MCP_INBOX"] = self._orig_inbox
        self._tmp.cleanup()

    @staticmethod
    def _png_base64(size=(60, 40)):
        import base64
        import io as _io
        from PIL import Image
        buf = _io.BytesIO()
        Image.new("RGB", size, (5, 90, 160)).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def _parse(out):
        if not out.startswith("{"):
            raise AssertionError(f"tool did not return a dict: {out}")
        return ast.literal_eval(out)

    def test_upload_from_base64_saves_to_inbox(self):
        data = self._parse(srv.instagram_upload_image(self._png_base64(), filename="chat pic!.png"))
        self.assertEqual(data["status"], "saved_to_inbox")
        self.assertEqual(data["filename"], "chat_pic_.png")  # sanitised, no spaces
        self.assertTrue(os.path.isfile(data["saved_path"]))
        self.assertEqual(data["image"]["px"], "60x40")
        self.assertIn("dry_run=True", data["next_step"])

    def test_tiny_pasted_image_still_works(self):
        # 8x8 PNG -> ~120 chars of base64: must still be detected as pasted image data
        data = self._parse(srv.instagram_upload_image(self._png_base64((8, 8)), filename="dot.png"))
        self.assertEqual(data["status"], "saved_to_inbox")
        self.assertEqual(data["image"]["px"], "8x8")

    def test_latest_resolves_and_status_lists_newest_first(self):
        self._parse(srv.instagram_upload_image(self._png_base64(), filename="one.png"))
        self._parse(srv.instagram_upload_image(self._png_base64((80, 80)), filename="two.png"))

        status = self._parse(srv.instagram_inbox_status())
        self.assertEqual(status["count"], 2)
        self.assertEqual(status["latest"], "two.png")
        self.assertEqual(status["files"][0]["name"], "two.png")

        copied = self._parse(srv.instagram_upload_image("latest", filename="copy.png"))
        self.assertEqual(copied["filename"], "copy.png")
        self.assertTrue(os.path.isfile(copied["saved_path"]))

    def test_duplicate_name_is_timestamped_not_overwritten(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as outer:
            source = Path(outer) / "shot.png"
            Image.new("RGB", (30, 30), (200, 0, 0)).save(source)
            first = self._parse(srv.instagram_upload_image(str(source), filename="shot.png"))
            second = self._parse(srv.instagram_upload_image(str(source), filename="shot.png"))
            self.assertEqual(first["filename"], "shot.png")
            self.assertNotEqual(second["filename"], "shot.png")
            self.assertEqual(len(list(Path(self._tmp.name).glob("shot.png"))), 1)

    def test_status_reports_upload_page_and_empty_state(self):
        saved_base = srv._RUNTIME_ORIGIN["base"]
        srv._RUNTIME_ORIGIN["base"] = ""
        os.environ["INSTAGRAM_MCP_INBOX_URL"] = "http://example.test/inbox?auth=k"
        os.environ.pop("INSTAGRAM_MCP_PUBLIC_URL", None)
        try:
            status = ast.literal_eval(srv.instagram_inbox_status())
            self.assertEqual(status["upload_page"], "http://example.test/inbox?auth=k")
            self.assertIsNone(status["latest"])
            self.assertEqual(status["count"], 0)
        finally:
            srv._RUNTIME_ORIGIN["base"] = saved_base
            os.environ.pop("INSTAGRAM_MCP_INBOX_URL", None)

    def test_new_inbox_tools_are_green_and_registered(self):
        for name in ("instagram_upload_image", "instagram_inbox_status"):
            self.assertTrue(callable(getattr(srv, name, None)))
            self.assertNotIn(name, srv._TOOL_RISK_RED)
            self.assertNotIn(name, srv._TOOL_RISK_ORANGE)


class PublicInboxUrlTests(unittest.TestCase):
    """The upload link follows whichever domain the client actually connected through."""

    def setUp(self):
        import scripts.serve as serve
        self.serve = serve
        self._saved = {k: os.environ.get(k) for k in
                       ("INSTAGRAM_MCP_PUBLIC_URL", "INSTAGRAM_MCP_INBOX_URL", "MCP_AUTH_KEY")}
        self._saved_base = srv._RUNTIME_ORIGIN["base"]
        self._saved_inbox_env = os.environ.get("INSTAGRAM_MCP_INBOX")
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["INSTAGRAM_MCP_INBOX"] = self._tmp.name
        os.environ.pop("INSTAGRAM_MCP_PUBLIC_URL", None)
        os.environ.pop("INSTAGRAM_MCP_INBOX_URL", None)
        os.environ["MCP_AUTH_KEY"] = "KEY123"
        srv._RUNTIME_ORIGIN["base"] = ""

    def tearDown(self):
        srv._RUNTIME_ORIGIN["base"] = self._saved_base
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self._saved_inbox_env is None:
            os.environ.pop("INSTAGRAM_MCP_INBOX", None)
        else:
            os.environ["INSTAGRAM_MCP_INBOX"] = self._saved_inbox_env
        self._tmp.cleanup()

    def test_inbox_from_base_swaps_mcp_for_inbox(self):
        self.assertEqual(srv._inbox_from_base("https://d.example/mcp"), "https://d.example/inbox")
        self.assertEqual(srv._inbox_from_base("https://d.example"), "https://d.example/inbox")
        self.assertEqual(srv._inbox_from_base("https://d.example/inbox"), "https://d.example/inbox")
        self.assertEqual(srv._inbox_from_base(""), "")

    def test_last_request_origin_wins(self):
        srv.note_request_base("https", "my-tunnel.example.net")
        self.assertEqual(srv._inbox_url(), "https://my-tunnel.example.net/inbox?auth=KEY123")

    def test_request_origin_keeps_port_and_https(self):
        srv.note_request_base("HTTPS", "127.0.0.1:8443,")
        self.assertEqual(srv._inbox_url(), "https://127.0.0.1:8443/inbox?auth=KEY123")

    def test_explicit_public_url_overrides_request_origin(self):
        srv.note_request_base("https", "stale.example.net")
        os.environ["INSTAGRAM_MCP_PUBLIC_URL"] = "https://pinned.example/mcp"
        self.assertEqual(srv._inbox_url(), "https://pinned.example/inbox?auth=KEY123")

    def test_fallback_to_configured_inbox_url(self):
        os.environ["INSTAGRAM_MCP_INBOX_URL"] = "http://127.0.0.1:8080/inbox?auth=x"
        self.assertEqual(srv._inbox_url(), "http://127.0.0.1:8080/inbox?auth=x")

    def test_origin_prefers_forwarded_headers(self):
        scope = {
            "scheme": "http",
            "headers": [(b"host", b"internal:8080"), (b"x-forwarded-host", b"pub.example"),
                        (b"x-forwarded-proto", b"https")],
        }
        self.assertEqual(self.serve._origin(scope), ("https", "pub.example"))

    def test_serve_middleware_records_tunnel_headers(self):
        import asyncio
        seen = {}

        async def inner(scope, receive, send):
            seen["url"] = srv._inbox_url()

        app = self.serve.build_app(inner, allow_no_auth=True)
        scope = {
            "type": "http",
            "path": "/mcp",
            "method": "POST",
            "headers": [(b"host", b"tunnel.example.net"), (b"x-forwarded-proto", b"https")],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            pass

        asyncio.run(app(scope, receive, send))
        self.assertEqual(seen["url"], "https://tunnel.example.net/inbox?auth=KEY123")

    def test_inbox_status_reports_domain_based_link(self):
        srv.note_request_base("https", "tunnel.example.net")
        status = ast.literal_eval(srv.instagram_inbox_status())
        self.assertEqual(status["upload_page"], "https://tunnel.example.net/inbox?auth=KEY123")

    def test_missing_image_error_uses_connected_domain(self):
        srv.note_request_base("https", "tunnel.example.net")
        with self.assertRaises(FileNotFoundError) as ctx:
            srv._resolve_image_source("definitely-not-here-12345.png")
        self.assertIn("https://tunnel.example.net/inbox?auth=KEY123", str(ctx.exception))


class TermuxInstallPlanTests(unittest.TestCase):
    """Android/Termux: pydantic-core is Rust-only, so the plan must avoid a source build."""

    def setUp(self):
        import scripts.setup as setup
        self.setup = setup

    def test_prebuilt_route_uses_android_wheel_index(self):
        first = self.setup.termux_pip_steps(prebuilt=True)[0]
        self.assertIn("--extra-index-url", first)
        self.assertIn(self.setup.TERMUX_WHEEL_INDEX, first)
        self.assertIn("--only-binary", first)
        self.assertIn("pydantic-core", first)
        self.assertIn("--pre", first)  # the paired pydantic is a pre-release

    def test_instagrapi_is_installed_without_its_android_pydantic_pin(self):
        insta = [step for step in self.setup.termux_pip_steps(True)
                 if any(arg.startswith("instagrapi") for arg in step)]
        self.assertEqual(len(insta), 1)
        self.assertIn("--no-deps", insta[0])

    def test_instagrapi_runtime_deps_are_installed_explicitly(self):
        flat = " ".join(" ".join(step).lower() for step in self.setup.termux_pip_steps(True))
        for pkg in ("pysocks", "pillow", "requests", "pycryptodomex", "fastmcp", "uvicorn"):
            self.assertIn(pkg, flat)

    def test_rust_route_does_not_pin_pydantic(self):
        flat = " ".join(" ".join(step) for step in self.setup.termux_pip_steps(False))
        self.assertNotIn("pydantic", flat)
        self.assertIn("instagrapi", flat)

    def test_rust_installed_only_for_the_compile_route(self):
        self.assertNotIn("rust", self.setup.termux_pkg_steps(with_rust=False)[0])
        self.assertIn("rust", self.setup.termux_pkg_steps(with_rust=True)[0])
        self.assertIn("libjpeg-turbo", self.setup.termux_pkg_steps(with_rust=False)[0])

    def test_echoed_commands_are_shell_safe(self):
        line = self.setup.echo_command(["pip", "install", "instagrapi>=2.18,<3"])
        self.assertIn('"instagrapi>=2.18,<3"', line)

    def test_install_dependencies_defaults_to_auto(self):
        self.assertEqual(
            self.setup.install_dependencies.__defaults__[1], "auto")

    def test_termux_install_does_not_run_on_other_platforms(self):
        with mock.patch.object(self.setup, "is_termux", return_value=False), \
                mock.patch.object(self.setup.subprocess, "call", return_value=0) as call:
            self.assertTrue(self.setup.install_dependencies(dry_run=False))
        cmds = [c.args[0] for c in call.call_args_list]
        self.assertEqual(len(cmds), 1)
        self.assertIn("-e", cmds[0])


if __name__ == "__main__":
    unittest.main()
