"""
Publish scheduled posts/stories created with instagram_schedule_post.

Run it manually, or let Windows Task Scheduler run it every minute:

  schtasks /Create /TN "InstagramMCP Scheduler" /SC MINUTE /MO 1 /TR "\"d:\\instagram-mcp-master\\.venv\\Scripts\\python.exe\" \"d:\\instagram-mcp-master\\scripts\\run_scheduler.py\""

The script loads the queue, publishes every due item through the same MCP tool
functions (pacing + error handling included), and marks items posted/failed.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from instagram_mcp_server import mcp_server as srv


def main() -> int:
    status = srv.ig.get_login_status()
    print(f"login: {status}")
    if not status.get("logged_in"):
        print("Not logged in - check .env (INSTAGRAM_MCP_SESSIONID) and retry.")
        return 1

    items = srv._load_queue()
    due = [it for it in items
           if it.get("status") == "pending" and (it.get("scheduled_epoch") or 0) <= time.time()]
    if not due:
        print(f"no due items ({len(items)} in queue)")
        return 0

    for it in due:
        kind = (it.get("kind") or "post").lower()
        path = str(it.get("image_path_or_url") or "")
        is_video = path.lower().endswith((".mp4", ".mov"))
        print(f"publishing {it.get('id')} ({kind}, video={is_video}) scheduled for {it.get('scheduled_at')}")
        try:
            if kind == "story":
                if is_video:
                    result = srv.instagram_post_video_story(
                        path, caption=it.get("caption") or None,
                        mentions=it.get("mentions"), hashtags=it.get("hashtags"),
                        location_name=it.get("location_name"),
                    )
                else:
                    result = srv.instagram_post_photo_story(
                        path, caption=it.get("caption") or None,
                        mentions=it.get("mentions"), hashtags=it.get("hashtags"),
                        location_name=it.get("location_name"),
                    )
            else:
                if is_video:
                    result = srv.instagram_post_video(
                        path, caption=it.get("caption") or "",
                        hashtags=it.get("hashtags"), mentions=it.get("mentions"),
                        location_name=it.get("location_name"),
                    )
                else:
                    result = srv.instagram_post_photo(
                        path, caption=it.get("caption") or "",
                        hashtags=it.get("hashtags"), mentions=it.get("mentions"),
                        location_name=it.get("location_name"),
                    )
            it["status"] = "posted" if "'status': 'success'" in str(result) else "failed"
            it["result"] = str(result)[:400]
        except Exception as e:
            it["status"] = "failed"
            it["result"] = f"{type(e).__name__}: {e}"[:400]
        it["published_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        print(f"  -> {it['status']}: {str(it.get('result'))[:160]}")

    srv._save_queue(items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
