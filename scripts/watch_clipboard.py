#!/usr/bin/env python3
"""Auto-save images into the MCP inbox while this runs.

    python scripts/watch_clipboard.py                 # watch the clipboard (Windows/macOS)
    python scripts/watch_clipboard.py --folder PATH   # watch a folder (any OS, e.g. screenshots)
    python scripts/watch_clipboard.py --once          # grab the current clipboard image and exit

Copy or snip an image and it lands in the inbox a second later — then just tell the AI
"post the latest image in the inbox". Ctrl+C to stop.
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


def inbox_target(name: str) -> Path:
    target = inbox_dir() / Path(name).name
    if target.exists():
        target = inbox_dir() / f"{target.stem}-{time.strftime('%Y%m%d-%H%M%S')}{target.suffix}"
    return target


def save_bytes(blob: bytes, name: str) -> Path:
    target = inbox_target(name)
    target.write_bytes(blob)
    return target


def grab_clipboard():
    """Return ('image', PIL.Image) or ('files', [paths]) or None."""
    try:
        from PIL import ImageGrab
    except ImportError:
        print("Pillow is required for clipboard watching: pip install pillow", file=sys.stderr)
        return None
    try:
        grabbed = ImageGrab.grabclipboard()
    except Exception:
        return None
    if grabbed is None:
        return None
    if isinstance(grabbed, list):
        paths = [p for p in grabbed if Path(p).suffix.lower() in IMAGE_SUFFIXES]
        return ("files", paths) if paths else None
    return "image", grabbed


def watch_clipboard(interval: float, once: bool) -> int:
    import hashlib
    seen = set()
    print(f"Watching the clipboard… new images go to {inbox_dir()}  (Ctrl+C to stop)")
    while True:
        grabbed = grab_clipboard()
        if grabbed:
            kind, payload = grabbed
            if kind == "image":
                import io
                buffer = io.BytesIO()
                payload.convert("RGB").save(buffer, format="PNG")
                blob = buffer.getvalue()
                digest = hashlib.sha256(blob).hexdigest()
                if digest not in seen:
                    seen.add(digest)
                    target = save_bytes(blob, f"clipboard-{time.strftime('%Y%m%d-%H%M%S')}.png")
                    print(f"SAVED: {target}")
            else:
                for path in payload:
                    digest = f"file:{path}"
                    if digest not in seen:
                        seen.add(digest)
                        try:
                            target = inbox_target(Path(path).name)
                            shutil.copy2(path, target)
                            print(f"SAVED: {target}")
                        except OSError as exc:
                            print(f"  could not copy {path}: {exc}", file=sys.stderr)
        if once:
            return 0
        time.sleep(interval)


def watch_folder(folder: Path, interval: float) -> int:
    if not folder.is_dir():
        print(f"Not a folder: {folder}", file=sys.stderr)
        return 1
    print(f"Watching {folder}… copies go to {inbox_dir()}  (Ctrl+C to stop)")
    known = {p.name for p in folder.iterdir() if p.is_file()}
    while True:
        for path in folder.iterdir():
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES and path.name not in known:
                known.add(path.name)
                try:
                    target = inbox_target(path.name)
                    shutil.copy2(path, target)
                    print(f"SAVED: {target}")
                except OSError as exc:
                    print(f"  could not copy {path}: {exc}", file=sys.stderr)
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-save images into the Instagram MCP inbox")
    parser.add_argument("--folder", help="watch this folder instead of the clipboard")
    parser.add_argument("--interval", type=float, default=1.5, help="poll interval in seconds (default 1.5)")
    parser.add_argument("--once", action="store_true", help="save the current clipboard image and exit")
    args = parser.parse_args()

    try:
        if args.folder:
            return watch_folder(Path(os.path.expanduser(args.folder)), args.interval)
        return watch_clipboard(args.interval, args.once)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
