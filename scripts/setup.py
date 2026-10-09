#!/usr/bin/env python3
"""Interactive setup for the Instagram Control MCP server (runs locally).

    Windows:                 start.cmd
    Linux / macOS / Termux:  bash start.sh
    manual:                  python scripts/setup.py [--defaults] [--dry-run] [--skip-install]

Steps
  1. install any missing Python dependencies (pip install -e .)
  2. ask for your Instagram login (username + sessionid cookie and/or password)
  3. create the auth key that is the last part of your client URL: /mcp?auth=<KEY>
  4. pick a pacing preset (how slowly the server acts for you)
  5. pick how the server listens — stdio, this PC only, or 0.0.0.0 for your own
     port-forwarding / LAN

Everything is stored in ./.env (git-ignored). Credentials are never echoed to
the screen, not even a single character.
"""
import argparse
import getpass
import importlib.util
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
DEFAULT_PORT = 8080
TOTAL_STEPS = 5
START_MODE_KEY = "MCP_START_MODE"     # stdio | local | network
START_PORT_KEY = "MCP_START_PORT"

DELAY_PRESET_DEFAULT = {
    "INSTAGRAM_MCP_COMMENT_DELAY_MIN": "5",  "INSTAGRAM_MCP_COMMENT_DELAY_MAX": "12",
    "INSTAGRAM_MCP_POST_DELAY_MIN": "15",    "INSTAGRAM_MCP_POST_DELAY_MAX": "40",
    "INSTAGRAM_MCP_LIKE_DELAY_MIN": "3",     "INSTAGRAM_MCP_LIKE_DELAY_MAX": "8",
    "INSTAGRAM_MCP_DM_DELAY_MIN": "4",       "INSTAGRAM_MCP_DM_DELAY_MAX": "10",
    "INSTAGRAM_MCP_SOCIAL_DELAY_MIN": "10",  "INSTAGRAM_MCP_SOCIAL_DELAY_MAX": "25",
    "INSTAGRAM_MCP_ACTION_DELAY_MIN": "2",   "INSTAGRAM_MCP_ACTION_DELAY_MAX": "6",
    "INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR": "10",
}

REQUIRED_MODULES = {           # import name -> pip package name
    "fastmcp": "fastmcp",
    "instagrapi": "instagrapi",
    "PIL": "pillow",
    "requests": "requests",
    "uvicorn": "uvicorn",
}


# ── .env helpers ─────────────────────────────────────────────────────────────

def read_env_lines() -> list:
    if not ENV_PATH.exists():
        return ["# Instagram MCP configuration (created by scripts/setup.py)", ""]
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def env_value(lines: list, key: str) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(key + "="):
            return stripped.split("=", 1)[1].strip()
    return ""


def upsert(lines: list, key: str, value: str) -> None:
    for i, line in enumerate(lines):
        if line.strip().startswith(key + "="):
            lines[i] = f"{key}={value}"
            return
    lines.append(f"{key}={value}")


def remove_key(lines: list, key: str) -> None:
    lines[:] = [ln for ln in lines if not ln.strip().startswith(key + "=")]


def write_env(lines: list) -> None:
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        os.chmod(ENV_PATH, 0o600)
    except OSError:
        pass


def secret_label(value: str) -> str:
    """Never echo credentials — not even one character, only the length."""
    return f"******** ({len(value)} chars)" if value else "(not set)"


# ── console UI (standard installer look) ─────────────────────────────────────

class UI:
    """Small ANSI helper: colour when attached to a terminal, plain text otherwise."""

    def __init__(self) -> None:
        try:  # never crash on a console or pipe that cannot encode the box glyphs
            sys.stdout.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        self.color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    def _paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    # headings ---------------------------------------------------------------
    def banner(self, title: str, subtitle: str = "") -> None:
        line = "─" * 60
        print()
        print(self._paint("36", line))
        print("  " + self._paint("1;36", title))
        if subtitle:
            print("  " + self._paint("2", subtitle))
        print(self._paint("36", line))

    def step(self, number: int, total: int, title: str) -> None:
        print()
        print(self._paint("1;34", f"── [{number}/{total}] {title} " + "─" * max(0, 40 - len(title))))

    def rule(self) -> None:
        print(self._paint("2", "  " + "─" * 58))

    # messages ---------------------------------------------------------------
    def info(self, text: str) -> None:
        print("      " + self._paint("2", text))

    def ok(self, text: str) -> None:
        print("      " + self._paint("32", f"✓ {text}"))

    def warn(self, text: str) -> None:
        print("      " + self._paint("33", f"! {text}"))

    def fail(self, text: str) -> None:
        print("      " + self._paint("31", f"✗ {text}"), file=sys.stderr)

    # input ------------------------------------------------------------------
    def prompt(self, question: str, default: str = "", hidden: bool = False) -> str:
        label = self._paint("1", f"? {question}")
        if default:
            label += self._paint("2", " [keep current]" if hidden else f" [{default}]")
        if hidden:
            value = getpass.getpass(f"      {label}: ").strip()
        else:
            value = input(f"      {label}: ").strip()
        return value or default

    def confirm(self, question: str, default: bool = True) -> bool:
        suffix = "Y/n" if default else "y/N"
        raw = input("      " + self._paint("1", f"? {question}")
                    + self._paint("2", f" [{suffix}]") + ": ").strip().lower()
        if not raw:
            return default
        return raw in ("y", "yes")

    def choose(self, question: str, options: list, default: int = 1) -> int:
        print("      " + self._paint("1", f"? {question}"))
        for i, option in enumerate(options, 1):
            tail = self._paint("2", "  (default)") if i == default else ""
            print(f"          {self._paint('1;36', str(i))}) {option}{tail}")
        while True:
            raw = input("          " + self._paint("2", "choice") + f" [{default}]: ").strip() or str(default)
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return int(raw)
            self.warn("enter one of the numbers above")

    def ask_int(self, question: str, default: int) -> int:
        while True:
            raw = self.prompt(question, str(default))
            if raw.lstrip("-").isdigit():
                return int(raw)
            self.warn("enter a whole number")


# ── client config snippets ───────────────────────────────────────────────────

def print_client_config_stdio(ui: UI, python_exe: str) -> None:
    exe = python_exe.replace("\\", "\\\\")
    ui.info("add this to your MCP client (Claude Desktop, Cursor, Cline, …):")
    print('          {\n            "mcpServers": {\n              "instagram-control": {\n'
          f'                "command": "{exe}",\n'
          '                "args": ["-m", "instagram_mcp_server"]\n'
          '              }\n            }\n          }')


def print_client_config_url(ui: UI, url: str) -> None:
    ui.info("add this to your MCP client (Claude Desktop, Cursor, Cline, …):")
    print('          {\n            "mcpServers": {\n'
          f'              "instagram-control": {{ "url": "{url}" }}\n'
          '            }\n          }')


# ── dependencies & auth key ──────────────────────────────────────────────────

def missing_dependencies() -> list:
    return [pkg for module, pkg in REQUIRED_MODULES.items()
            if importlib.util.find_spec(module) is None]


def is_termux() -> bool:
    return "com.termux" in sys.prefix or "ANDROID_ROOT" in os.environ


# ── Termux / Android install strategy ────────────────────────────────────────
# pydantic-core is a Rust extension and PyPI publishes no Android wheels, so on
# Termux pip falls back to a source build and dies with
#   "Target triple not supported by rustup: aarch64-unknown-linux-android"
# unless a Rust toolchain is present. Two supported routes, tried in order:
#
#   prebuilt — a community project republishes PEP 738 Android wheels
#              (Eutalix/android-pydantic-core, built in CI against Termux's own
#              python). Today they exist for pydantic-core 2.49.0, which pairs
#              with the pydantic 2.14.0b2 pre-release. Fast, no Rust needed.
#   rust     — `pkg install rust` and let pip compile pydantic-core. Slow
#              (10–40 min, ~1.5 GB free space) but uses no third-party wheels.
#
# instagrapi additionally pins pydantic==2.12.5 on Android (also wheel-less), so
# it is installed with --no-deps and its other runtime deps are listed here.
TERMUX_WHEEL_INDEX = "https://eutalix.github.io/android-pydantic-core/"
TERMUX_PYDANTIC_PREBUILT = "pydantic==2.14.0b2"
TERMUX_BUILD_PKGS = ["clang", "make", "binutils", "libjpeg-turbo", "libpng", "freetype", "zlib"]
TERMUX_INSTAGRAPI_DEPS = ["PySocks", "Pillow", "requests", "pycryptodomex"]

_SHELL_UNSAFE = set("<>|&,;\"'`$")


def echo_command(cmd: list) -> str:
    """Print a command that can be copied straight into a shell (quote metachars)."""
    parts = [f'"{arg}"' if (set(arg) & _SHELL_UNSAFE or " " in arg) else arg for arg in cmd]
    line = " ".join(parts)
    print("      " + line)
    return line


def termux_pkg_steps(with_rust: bool) -> list:
    """System packages needed to build the remaining wheels (Rust only if compiling)."""
    pkgs = list(TERMUX_BUILD_PKGS) + (["rust"] if with_rust else [])
    return [["pkg", "install", "-y", *pkgs]]


def termux_pip_steps(prebuilt: bool = True) -> list:
    """pip command sequence for Android/Termux, prebuilt Android wheels or source build."""
    py = sys.executable
    steps = []
    if prebuilt:
        steps.append([py, "-m", "pip", "install", TERMUX_PYDANTIC_PREBUILT, "--pre",
                      "--extra-index-url", TERMUX_WHEEL_INDEX, "--only-binary", "pydantic-core"])
    steps.append([py, "-m", "pip", "install", "fastmcp", "uvicorn", *TERMUX_INSTAGRAPI_DEPS])
    steps.append([py, "-m", "pip", "install", "instagrapi>=2.18,<3", "--no-deps"])
    steps.append([py, "-m", "pip", "install", "-e", str(ROOT), "--no-deps"])
    return steps


def _imports_ok(code: str) -> bool:
    return subprocess.call([sys.executable, "-c", code]) == 0


def install_dependencies(dry_run: bool = False, termux_mode: str = "auto") -> bool:
    """pip-install the project so the server can run (Termux gets Android-safe steps).

    termux_mode: "auto" (prebuilt wheels, fall back to compiling) | "prebuilt" | "rust".
    """
    if not is_termux():
        for cmd in ([sys.executable, "-m", "pip", "install", "-e", str(ROOT)],):
            echo_command(cmd)
            if not dry_run and subprocess.call(cmd) != 0:
                return False
        return True

    pkg = shutil.which("pkg")
    if pkg and termux_mode != "prebuilt":
        for cmd in termux_pkg_steps(with_rust=(termux_mode == "rust")):
            echo_command(cmd)
            if not dry_run:
                subprocess.call(cmd)  # best effort — most packages are already present

    if termux_mode in ("auto", "prebuilt"):
        if termux_mode == "auto":
            print("      trying prebuilt Android wheels for pydantic-core …")
        ok = True
        for cmd in termux_pip_steps(prebuilt=True):
            echo_command(cmd)
            if not dry_run and subprocess.call(cmd) != 0:
                ok = False
                break
        if ok and (dry_run or _imports_ok("import pydantic, pydantic_core")):
            return True
        if termux_mode == "prebuilt":
            return False
        print("      ! prebuilt wheels did not work — compiling pydantic-core with Rust next")
        print("        (this can take 10-40 min and needs ~1.5 GB free space)")

    if pkg:
        for cmd in termux_pkg_steps(with_rust=True):
            echo_command(cmd)
            if not dry_run:
                subprocess.call(cmd)
    for cmd in termux_pip_steps(prebuilt=False):
        echo_command(cmd)
        if not dry_run and subprocess.call(cmd) != 0:
            return False
    return True


def new_auth_key() -> str:
    """Strong key for the /mcp?auth=... part of the URL."""
    return secrets.token_urlsafe(24)


def detect_lan_ip() -> str:
    """Best-effort LAN IPv4 of this machine (used for client URLs). No packets are sent."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return ""


# ── start with the saved setup ───────────────────────────────────────────────

def has_previous_setup(lines: list) -> bool:
    """True when .env already holds a usable configuration."""
    return ENV_PATH.exists() and any(
        env_value(lines, key) for key in
        ("INSTAGRAM_MCP_USERNAME", "INSTAGRAM_MCP_SESSIONID", "INSTAGRAM_MCP_PASSWORD", "MCP_AUTH_KEY")
    )


def start_saved(ui: UI, lines: list) -> int:
    """Start the server exactly as configured before — no questions asked."""
    mode = env_value(lines, START_MODE_KEY)
    python_exe = sys.executable

    if not mode:
        ui.warn("this saved setup does not remember which mode to use yet")
        mode_choice = ui.choose(
            "How should the server listen from now on?",
            ["Stdio — your MCP client starts it (nothing listens on the network)",
             "Local HTTP — this PC only (127.0.0.1)",
             "Network HTTP — LAN or your own port-forwarding (0.0.0.0)"],
            default=1,
        )
        mode = {1: "stdio", 2: "local", 3: "network"}[mode_choice]
        upsert(lines, START_MODE_KEY, mode)
        if mode in ("local", "network"):
            upsert(lines, START_PORT_KEY, str(ui.ask_int("port", DEFAULT_PORT)))
        write_env(lines)
        ui.ok(f"remembered in .env: {START_MODE_KEY}={mode}")

    try:
        port = int(env_value(lines, START_PORT_KEY) or DEFAULT_PORT)
    except ValueError:
        port = DEFAULT_PORT
    auth_key = env_value(lines, "MCP_AUTH_KEY")

    if mode == "stdio":
        ui.ok("saved mode: stdio — your MCP client launches the server")
        ui.info("nothing runs in this window: with stdio the MCP client starts the")
        ui.info("server itself. Paste this into the client and you are done:")
        print_client_config_stdio(ui, python_exe)
        ui.info("you can close this window now — run this script again to change the setup")
        return 0

    if mode == "local":
        command = [python_exe, "-m", "instagram_mcp_server",
                   "--transport", "http", "--host", "127.0.0.1", "--port", str(port)]
        url = f"http://127.0.0.1:{port}/mcp"
    else:
        command = [python_exe, str(ROOT / "scripts" / "serve.py"), "--host", "0.0.0.0", "--port", str(port)]
        url = f"http://<your-host-or-domain>:{port}/mcp" + (f"?auth={auth_key}" if auth_key else "")

    ui.ok(f"saved mode: {mode} on port {port}")
    ui.info("client URL:  " + url)
    if mode == "network":
        ui.info("use the address you actually reach this PC through (LAN IP, port-forward or tunnel")
        ui.info("domain). the image-upload page is the same URL with /mcp replaced by /inbox.")
    ui.info("starting the server now — KEEP THIS WINDOW OPEN while you use it")
    ui.info("press Ctrl+C to stop the server")
    print()
    print("      " + " ".join(f'"{part}"' if " " in part else part for part in command))
    print()
    try:
        subprocess.call(command)
    except KeyboardInterrupt:
        print()
    ui.warn("server stopped — run this script again to start it or change the setup")
    return 0


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive setup for the Instagram MCP server")
    parser.add_argument("--defaults", action="store_true", help="accept all defaults without prompting")
    parser.add_argument("--dry-run", action="store_true", help="show the settings without writing .env or starting anything")
    parser.add_argument("--skip-install", action="store_true", help="do not check or install pip dependencies")
    parser.add_argument("--termux-mode", choices=("auto", "prebuilt", "rust"), default="auto",
                        help="Android/Termux only: auto (default), prebuilt wheels, or compile with Rust")
    args = parser.parse_args()

    ui = UI()
    if not args.defaults and not sys.stdin.isatty():
        ui.fail("this setup is interactive — run it in a terminal (or use --defaults --dry-run)")
        return 1

    lines = read_env_lines()
    writes = {}

    ui.banner("Instagram MCP server — setup",
              f"settings are saved to {ENV_PATH}")

    # previous setup → offer "start" or "change setup" ------------------------
    if has_previous_setup(lines) and not args.defaults and not args.dry_run:
        action = ui.choose(
            "A previous setup was found — what do you want to do?",
            ["Start the server with the saved setup",
             "Change the setup"],
            default=1,
        )
        if action == 1:
            return start_saved(ui, lines)
        ui.info("re-running the setup — press Enter to keep each saved value")

    # 1) dependencies --------------------------------------------------------
    ui.step(1, TOTAL_STEPS, "Dependencies")
    if args.skip_install:
        ui.info("skipped (--skip-install)")
    else:
        missing = missing_dependencies()
        if not missing:
            ui.ok("all required packages are installed")
        else:
            ui.info("missing: " + ", ".join(missing))
            if args.dry_run:
                install_dependencies(dry_run=True, termux_mode=args.termux_mode)
                ui.info("dry run — nothing installed")
            elif args.defaults or ui.confirm("Install them now?", True):
                ui.info("installing — this can take a minute (longer on Termux)")
                if not install_dependencies(termux_mode=args.termux_mode):
                    ui.fail("pip install failed — fix the error above and run this again")
                    if is_termux():
                        ui.info("Termux tips:")
                        ui.info("  • prebuilt pydantic-core wheels: python scripts/setup.py --termux-mode prebuilt")
                        ui.info("  • compile it yourself:          pkg install rust && python scripts/setup.py --termux-mode rust")
                        ui.info("  • compiling needs ~1.5 GB free space and: pkg install clang make binutils")
                    return 1
                still = missing_dependencies()
                if still:
                    ui.fail("still missing: " + ", ".join(still))
                    return 1
                ui.ok("dependencies installed")
            else:
                ui.warn("skipped — the server cannot start without them")

    # 2) Instagram login -----------------------------------------------------
    ui.step(2, TOTAL_STEPS, "Instagram login")
    username = env_value(lines, "INSTAGRAM_MCP_USERNAME")
    if not args.defaults:
        username = ui.prompt("Instagram username", username)
    writes["INSTAGRAM_MCP_USERNAME"] = username

    method = 3 if args.defaults else ui.choose(
        "How should the server sign in?",
        ["Session cookie (sessionid) — recommended, most stable",
         "Username + password",
         "Both (cookie first, password as fallback)"],
        default=1,
    )

    saved_sid = env_value(lines, "INSTAGRAM_MCP_SESSIONID")
    if saved_sid and (len(saved_sid) < 30 or ":" not in saved_sid):
        ui.warn("the saved sessionid looks invalid and will be replaced")
        saved_sid = ""
    if method in (1, 3):
        sid = saved_sid if args.defaults else ui.prompt("sessionid cookie value", saved_sid, hidden=True)
        if sid and (len(sid) < 30 or ":" not in sid) and not args.defaults:
            if not ui.confirm("That does not look like a sessionid — keep it anyway?", False):
                sid = ""
        writes["INSTAGRAM_MCP_SESSIONID"] = sid
        ui.ok(f"sessionid: {secret_label(sid)}")
    if method in (2, 3):
        saved_pw = env_value(lines, "INSTAGRAM_MCP_PASSWORD")
        pw = saved_pw if args.defaults else ui.prompt("Instagram password", saved_pw, hidden=True)
        writes["INSTAGRAM_MCP_PASSWORD"] = pw
        ui.ok(f"password: {secret_label(pw)}")
        ui.info("2FA: the AI will ask for a fresh code via instagram_complete_2fa when Instagram asks for it")

    stored_sid = writes.get("INSTAGRAM_MCP_SESSIONID", env_value(lines, "INSTAGRAM_MCP_SESSIONID"))
    stored_pw = writes.get("INSTAGRAM_MCP_PASSWORD", env_value(lines, "INSTAGRAM_MCP_PASSWORD"))
    if not stored_sid and not stored_pw:
        ui.warn("no cookie and no password — the server will start logged out")

    # 3) auth key ------------------------------------------------------------
    ui.step(3, TOTAL_STEPS, "Auth key")
    ui.info("your client URL ends with  /mcp?auth=<KEY>  — it protects the server")
    existing_key = env_value(lines, "MCP_AUTH_KEY")
    if args.defaults:
        auth_key = existing_key or new_auth_key()
    elif existing_key:
        ui.info(f"a key is already saved: {existing_key}")
        key_choice = ui.choose("Use that key?", ["Keep the saved key", "Generate a new one", "Type my own"], default=1)
        if key_choice == 2:
            auth_key = new_auth_key()
        elif key_choice == 3:
            auth_key = ui.prompt("auth key", "", hidden=True) or new_auth_key()
        else:
            auth_key = existing_key
    else:
        key_choice = ui.choose("Create the auth key?", ["Generate a strong one", "Type my own"], default=1)
        auth_key = ui.prompt("auth key", "", hidden=True) if key_choice == 2 else new_auth_key()
        auth_key = auth_key or new_auth_key()
    writes["MCP_AUTH_KEY"] = auth_key
    ui.ok(f"auth key: {auth_key}")

    # 4) pacing preset -------------------------------------------------------
    ui.step(4, TOTAL_STEPS, "Pacing")
    preset = 1 if args.defaults else ui.choose(
        "How slowly should the server act?",
        ["Defaults — snappy but still human-like (recommended)",
         "Safe mode — long delays and low caps (after an Instagram warning)",
         "Custom — I'll set the numbers"],
        default=1,
    )
    if preset == 1:
        writes.update(DELAY_PRESET_DEFAULT)
        writes["INSTAGRAM_MCP_SAFE_MODE"] = ""
        pacing = "defaults (comments 5–12 s, posts 15–40 s, max 10 comments/h)"
    elif preset == 2:
        writes["INSTAGRAM_MCP_SAFE_MODE"] = "1"
        for key in DELAY_PRESET_DEFAULT:
            writes[key] = ""
        pacing = "safe mode (very long delays, max 3 comments/h)"
    else:
        ui.info("press Enter to accept each suggested value")
        writes["INSTAGRAM_MCP_SAFE_MODE"] = ""
        writes["INSTAGRAM_MCP_COMMENT_DELAY_MIN"] = str(ui.ask_int("comment / reply delay — min seconds", 5))
        writes["INSTAGRAM_MCP_COMMENT_DELAY_MAX"] = str(ui.ask_int("comment / reply delay — max seconds", 12))
        writes["INSTAGRAM_MCP_POST_DELAY_MIN"] = str(ui.ask_int("post / upload delay — min seconds", 15))
        writes["INSTAGRAM_MCP_POST_DELAY_MAX"] = str(ui.ask_int("post / upload delay — max seconds", 40))
        writes["INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR"] = str(ui.ask_int("max comments per hour", 10))
        writes["INSTAGRAM_MCP_MAX_WRITES_PER_DAY"] = str(ui.ask_int("max write actions per day (0 = unlimited)", 0))
        pacing = (f"custom (comments {writes['INSTAGRAM_MCP_COMMENT_DELAY_MIN']}–{writes['INSTAGRAM_MCP_COMMENT_DELAY_MAX']} s, "
                  f"posts {writes['INSTAGRAM_MCP_POST_DELAY_MIN']}–{writes['INSTAGRAM_MCP_POST_DELAY_MAX']} s, "
                  f"max {writes['INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR']} comments/h)")
    ui.ok(pacing)

    # 5) server mode ---------------------------------------------------------
    ui.step(5, TOTAL_STEPS, "Server mode")
    mode = 1 if args.defaults else ui.choose(
        "How should the server listen?",
        ["Stdio — your MCP client starts it (nothing listens on the network)",
         "Local HTTP — this PC only (127.0.0.1)",
         "Network HTTP — LAN or your own port-forwarding (0.0.0.0)"],
        default=1,
    )
    port = DEFAULT_PORT
    host = "127.0.0.1"
    if mode in (2, 3):
        port = DEFAULT_PORT if args.defaults else ui.ask_int("port", DEFAULT_PORT)
        host = "127.0.0.1" if mode == 2 else "0.0.0.0"
    if mode == 3:
        ui.warn("anything that reaches this port can control your account if it knows the key")
        ui.info(f"your MCP client URL is  http://<your-host-or-domain>:{port}/mcp?auth={auth_key}")
        ui.info("use the address you actually reach this PC through: a LAN IP, your port-forward")
        ui.info("address, or your tunnel domain (Cloudflare / Tailscale / nginx).")
        ui.info("the image-upload page is the same URL with /mcp replaced by /inbox — the server")
        ui.info("reports the exact link automatically for whichever domain you connect through.")
        ui.info("port forwarding needs a public IP from your router/ISP; on mobile hotspots or")
        ui.info("CGNAT connections (many ISPs) inbound ports are unreachable — tunnel instead.")
        if len(auth_key) < 16 and not args.defaults and ui.confirm("Use a stronger auth key instead?", True):
            auth_key = new_auth_key()
            writes["MCP_AUTH_KEY"] = auth_key
            ui.ok(f"auth key: {auth_key}")

    # remember the choice so the next run can start straight away
    writes[START_MODE_KEY] = {1: "stdio", 2: "local", 3: "network"}[mode]
    if mode in (2, 3):
        writes[START_PORT_KEY] = str(port)

    # summary ----------------------------------------------------------------
    server_label = {1: "stdio (client-launched)",
                    2: f"http://127.0.0.1:{port}",
                    3: f"http://0.0.0.0:{port} (network)"}[mode]
    rows = [
        ("username", username or "(not set)"),
        ("sessionid", secret_label(writes.get("INSTAGRAM_MCP_SESSIONID", env_value(lines, "INSTAGRAM_MCP_SESSIONID")))),
        ("password", secret_label(writes.get("INSTAGRAM_MCP_PASSWORD", env_value(lines, "INSTAGRAM_MCP_PASSWORD")))),
        ("auth key", auth_key),
        ("pacing", pacing),
        ("server", server_label),
    ]
    print()
    ui.rule()
    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        print(f"      {name.ljust(width)} │ {value}")
    ui.rule()

    # save -------------------------------------------------------------------
    if args.dry_run:
        ui.info("dry run — nothing was written")
    else:
        if not args.defaults and not ui.confirm("Save these settings to .env?", True):
            ui.warn("nothing written")
            return 0
        for key, value in writes.items():
            if value == "":
                remove_key(lines, key)
            else:
                upsert(lines, key, value)
        write_env(lines)
        ui.ok(f"saved {ENV_PATH}")

    if not args.dry_run and not args.defaults and ui.confirm("Test the Instagram login now?", False):
        ui.info("Instagram may show a security prompt for a new device…")
        import instagram_mcp_server.mcp_server as srv
        print("      " + str(srv.ig.get_login_status()))

    # start ------------------------------------------------------------------
    print()
    python_exe = sys.executable
    if mode == 1:
        ui.ok("nothing to start — your MCP client launches the server over stdio")
        ui.info("nothing runs in this window: paste the config below into your client,")
        ui.info("then you can close it — the client starts the server itself")
        print_client_config_stdio(ui, python_exe)
    else:
        if mode == 2:
            command = [python_exe, "-m", "instagram_mcp_server",
                       "--transport", "http", "--host", host, "--port", str(port)]
            url = f"http://127.0.0.1:{port}/mcp"
        else:
            command = [python_exe, str(ROOT / "scripts" / "serve.py"), "--host", host, "--port", str(port)]
            url = f"http://<your-host-or-domain>:{port}/mcp?auth={auth_key}"
        ui.info("start command:")
        print("          " + " ".join(f'"{part}"' if " " in part else part for part in command))
        ui.info("client URL:")
        print(f"          {url}")
        print_client_config_url(ui, url)
        if not args.dry_run and not args.defaults and ui.confirm("Start the server now?", True):
            try:
                subprocess.call(command)
            except KeyboardInterrupt:
                print()

    print()
    ui.info("next time just run:  start.cmd  (Windows)  /  bash start.sh  (Linux, macOS, Termux)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n")
        sys.exit(130)