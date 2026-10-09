#!/usr/bin/env python3
"""Put an image into the MCP inbox so the Instagram MCP server can post it.

The server runs on this machine and cannot read images from a chat window, so
park the picture here first and then just tell the AI "post the latest image in
the inbox" (or pass the printed path to instagram_post_photo).

    python scripts/save_image.py                    # clipboard image (Windows/macOS)
    python scripts/save_image.py C:\\path\\to\\pic.png  # copy a file into the inbox
    python scripts/save_image.py --url https://...    # download an image URL
    python scripts/save_image.py --list               # show what is waiting

Inbox folder: INSTAGRAM_MCP_INBOX, or ~/instagram-mcp-inbox by default.
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif")


def inbox_dir() -> Path:
    configured = os.environ.get("INSTAGRAM_MCP_INBOX", "").strip()
    base = (Path(os.path.expandvars(os.path.expanduser(configured)))
            if configured else Path.home() / "instagram-mcp-inbox")
    base.mkdir(parents=True, exist_ok=True)
    return base


def unique_target(name: str) -> Path:
    inbox = inbox_dir()
    target = inbox / Path(name).name
    if target.exists():
        target = inbox / f"{target.stem}-{time.strftime('%Y%m%d-%H%M%S')}{target.suffix}"
    return target


def save_clipboard() -> int:
    try:
        from PIL import ImageGrab
    except ImportError:
        print("Pillow is required for clipboard support: pip install pillow", file=sys.stderr)
        return 1
    try:
        grabbed = ImageGrab.grabclipboard()
    except Exception as exc:
        print(f"Clipboard read failed: {exc}", file=sys.stderr)
        return 1
    if grabbed is None:
        print("No image in the clipboard.\n"
              "- Windows: press Win+Shift+S, snip the picture, then run this again.\n"
              "- macOS:   copy an image (Cmd+C on a file or screenshot), then run again.\n"
              "- Linux/Termux: save the file and pass its path instead.", file=sys.stderr)
        return 1
    if isinstance(grabbed, list):  # copied files rather than bitmap data
        for item in grabbed:
            if Path(item).suffix.lower() in IMAGE_SUFFIXES:
                return save_file(Path(item))
        print("The clipboard holds no image file.", file=sys.stderr)
        return 1
    target = unique_target(f"clipboard-{time.strftime('%Y%m%d-%H%M%S')}.png")
    grabbed.save(target)
    print(f"SAVED: {target}")
    return 0


def save_file(source: Path) -> int:
    if not source.is_file():
        print(f"File not found: {source}", file=sys.stderr)
        return 1
    target = unique_target(source.name)
    shutil.copy2(source, target)
    print(f"SAVED: {target}")
    return 0


def save_url(url: str) -> int:
    import requests
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    name = Path(url.split("?")[0]).name or f"download-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    target = unique_target(name)
    target.write_bytes(response.content)
    print(f"SAVED: {target}")
    return 0


def list_inbox() -> int:
    files = [p for p in inbox_dir().rglob("*") if p.is_file()]
    if not files:
        print(f"Inbox is empty: {inbox_dir()}")
        return 0
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"Inbox: {inbox_dir()}")
    for path in files:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
        print(f"  {stamp}  {path.stat().st_size:>9,} B  {path.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Save an image into the Instagram MCP inbox")
    parser.add_argument("path", nargs="?", help="image file to copy into the inbox")
    parser.add_argument("--url", help="download this image URL into the inbox")
    parser.add_argument("--list", action="store_true", help="show the inbox contents")
    args = parser.parse_args()

    if args.list:
        return list_inbox()
    if args.url:
        return save_url(args.url)
    if args.path:
        return save_file(Path(os.path.expanduser(args.path)))
    return save_clipboard()


if __name__ == "__main__":
    sys.exit(main())
