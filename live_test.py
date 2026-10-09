"""Live smoke test for the Instagram Control MCP workflow.

Credentials are read from the environment (a local .env file is loaded when
present). NEVER hardcode credentials in this file.

Environment variables:
- INSTAGRAM_MCP_USERNAME      account username
- INSTAGRAM_MCP_SESSIONID     browser sessionid cookie (preferred)
- INSTAGRAM_MCP_PASSWORD      optional password login if the sessionid fails
- INSTAGRAM_MCP_2FA_CODE      optional 2FA code used with INSTAGRAM_MCP_PASSWORD
- INSTAGRAM_TEST_IMAGE        optional absolute path to a photo to post
- INSTAGRAM_TEST_CAPTION      caption for that post
- INSTAGRAM_TEST_TOPIC        optional topic to search and print
- INSTAGRAM_TEST_REPLY_COMMENT_ID / INSTAGRAM_TEST_REPLY_TEXT
                              optional public reply test on the latest post
- INSTAGRAM_MCP_COMMENT_DELAY_MIN/_MAX, POST_DELAY_MIN/_MAX
                              delay overrides (set to 0 for a fast test run)

Usage:  python live_test.py
"""

import os
import sys


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no extra dependency); existing env vars win."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip(chr(34)).strip(chr(39))
            if key and key not in os.environ:
                os.environ[key] = value


def main() -> int:
    load_dotenv()
    print("Live test: write actions are paced by INSTAGRAM_MCP_*_DELAY_* env vars.",
          file=sys.stderr)

    from instagram_mcp_server import mcp_server as srv

    status = srv.ig.get_login_status()
    print(f"login status: {status}", file=sys.stderr)
    if not status.get("logged_in"):
        password = os.environ.get("INSTAGRAM_MCP_PASSWORD")
        if password:
            result = srv.ig.login_with_credentials(
                os.environ.get("INSTAGRAM_MCP_USERNAME", ""),
                password,
                verification_code=os.environ.get("INSTAGRAM_MCP_2FA_CODE") or None,
            )
            print(f"credentials login: {result}", file=sys.stderr)
            status = srv.ig.get_login_status()
    if not status.get("logged_in"):
        print("Not logged in. Put INSTAGRAM_MCP_USERNAME / INSTAGRAM_MCP_SESSIONID "
              "into a local .env file (or the MCP client env block) and retry. "
              "Optionally set INSTAGRAM_MCP_PASSWORD (+ INSTAGRAM_MCP_2FA_CODE) to try "
              "password login instead of a sessionid.",
              file=sys.stderr)
        return 1

    image = os.environ.get("INSTAGRAM_TEST_IMAGE")
    if image:
        caption = os.environ.get(
            "INSTAGRAM_TEST_CAPTION",
            "Posted from the Instagram Control MCP smoke test. #mcp #test",
        )
        print("post_photo:", srv.instagram_post_photo(image, caption))

    medias = srv.ig.cl.user_medias(srv.ig.cl.user_id, 1)
    if not medias:
        print("No posts on this account yet.", file=sys.stderr)
        return 0

    latest = medias[0]
    print(f"latest post: {latest.id} https://www.instagram.com/p/{latest.code}/")
    print("comments 1-5:", srv.instagram_get_post_comments_range(latest.id, 1, 5))

    reply_id = os.environ.get("INSTAGRAM_TEST_REPLY_COMMENT_ID")
    reply_text = os.environ.get("INSTAGRAM_TEST_REPLY_TEXT")
    if reply_id and reply_text:
        print("reply:", srv.instagram_reply_to_comment(latest.id, reply_id, reply_text))

    topic = os.environ.get("INSTAGRAM_TEST_TOPIC")
    if topic:
        print("topic search:", srv.instagram_find_topic_content(topic, 3, "top"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
