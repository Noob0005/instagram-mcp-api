"""Pure helpers for the admin dashboard: no network, no heavy imports.

Kept separate from the ASGI handlers so they can be unit-tested offline.
Nothing here ever returns an environment variable's VALUE — only whether it is set.
"""
import base64
import hashlib
import hmac
import os
import time
from typing import Dict, List, Mapping, Optional

COOKIE_NAME = "igmcp_admin"
SESSION_SECONDS = 8 * 3600

# (name, level, group, description)
#   level: required | recommended | optional | danger
ENV_SPEC = [
    ("MCP_AUTH_KEY", "required", "Access",
     "Secret key that protects /mcp and the upload APIs. Clients connect with ?auth=<key>."),
    ("BLOB_READ_WRITE_TOKEN", "required", "Storage",
     "Added automatically when you connect a Vercel Blob store to this project."),
    ("SESSION_ENCRYPTION_KEY", "required", "Storage",
     "Fernet key that encrypts the Instagram session saved in Blob. Use the GEN button."),
    ("CRON_SECRET", "required", "Access",
     "Lets Vercel's daily cleanup cron authenticate itself."),
    ("ADMIN_USERNAME", "recommended", "Access",
     "Dashboard login name. Without ADMIN_USERNAME + ADMIN_PASSWORD the dashboard asks for the MCP key."),
    ("ADMIN_PASSWORD", "recommended", "Access",
     "Dashboard login password (10+ characters)."),
    ("INSTAGRAM_MCP_SESSION_NAME", "optional", "Session",
     "Name of the stored session. Defaults to 'default'."),
    ("INSTAGRAM_MCP_SESSION_JSON", "optional", "Session",
     "First-time seed only: full instagrapi settings JSON. Not needed if you use the dashboard form."),
    ("INSTAGRAM_MCP_SESSIONID", "optional", "Session",
     "Bare sessionid cookie for auto-login on cold start. The dashboard form is more reliable."),
    ("INSTAGRAM_MCP_USERNAME", "optional", "Session",
     "Instagram username, used with the sessionid or password auto-login."),
    ("INSTAGRAM_MCP_PASSWORD", "optional", "Session",
     "Avoid: every cold-start login from a new IP looks like a new device."),
    ("INSTAGRAM_MCP_UPLOAD_TTL_DAYS", "optional", "Tuning",
     "Days before unposted uploads are deleted. Defaults to 7."),
    ("INSTAGRAM_MCP_MAX_UPLOAD_BYTES", "optional", "Tuning",
     "Largest accepted upload. Defaults to 256 MB."),
    ("INSTAGRAM_MCP_DEDUPE_WINDOW", "optional", "Tuning",
     "Seconds during which an identical action is treated as a duplicate. Defaults to 600."),
    ("INSTAGRAM_MCP_MAX_COMMENTS_PER_HOUR", "optional", "Tuning", "Hourly comment cap."),
    ("INSTAGRAM_MCP_MAX_WRITES_PER_DAY", "optional", "Tuning", "Daily write-action cap."),
    ("MCP_ALLOW_UNAUTHENTICATED", "danger", "Access",
     "Never set this on a public deployment: it turns the key check off."),
]


def valid_fernet_key(value: str) -> bool:
    """A Fernet key is 32 random bytes, url-safe base64 encoded (44 characters)."""
    try:
        return len(base64.urlsafe_b64decode(value.strip().encode())) == 32
    except Exception:
        return False


def check_env(env: Optional[Mapping[str, str]] = None) -> Dict:
    """Return the checklist and a summary. Values are never included."""
    env = os.environ if env is None else env
    rows: List[Dict] = []
    for name, level, group, desc in ENV_SPEC:
        raw = (env.get(name) or "").strip()
        is_set = bool(raw)
        state, note = "ok", ""
        if level == "danger":
            if raw == "1":
                state, note = "danger", "Set to 1: the key check is OFF. Remove it now."
            else:
                state = "unset"  # not being set is the safe state
        elif not is_set:
            state = "missing" if level in ("required", "recommended") else "unset"
        else:
            if name == "SESSION_ENCRYPTION_KEY" and not valid_fernet_key(raw):
                state = "invalid"
                note = "Not a valid Fernet key, so the session is stored UNENCRYPTED. Use GEN to make one."
            elif name == "MCP_AUTH_KEY" and len(raw) < 24:
                state, note = "weak", "Under 24 characters. Use GEN for a strong key."
            elif name == "ADMIN_PASSWORD" and len(raw) < 10:
                state, note = "weak", "Under 10 characters."
        rows.append({"name": name, "level": level, "group": group, "desc": desc,
                     "set": is_set, "state": state, "note": note})

    problems = [r for r in rows if r["level"] == "required" and r["state"] != "ok"]
    warnings = [r for r in rows if r["state"] in ("invalid", "weak", "danger")
                or (r["level"] == "recommended" and r["state"] == "missing")]
    return {
        "rows": rows,
        "required_total": sum(1 for r in rows if r["level"] == "required"),
        "required_bad": len(problems),
        "warnings": len(warnings),
    }


def admin_mode(env: Optional[Mapping[str, str]] = None) -> str:
    """'password' when ADMIN_USERNAME+ADMIN_PASSWORD are set, 'key' when only MCP_AUTH_KEY is, else 'none'."""
    env = os.environ if env is None else env
    if (env.get("ADMIN_USERNAME") or "").strip() and (env.get("ADMIN_PASSWORD") or ""):
        return "password"
    if (env.get("MCP_AUTH_KEY") or "").strip():
        return "key"
    return "none"


def _eq(a: str, b: str) -> bool:
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


def verify_login(body: Mapping, env: Optional[Mapping[str, str]] = None) -> bool:
    """Check submitted credentials against the configured mode (constant-time)."""
    env = os.environ if env is None else env
    mode = admin_mode(env)
    if mode == "password":
        user_ok = _eq(str(body.get("username", "")), env.get("ADMIN_USERNAME", "").strip())
        pass_ok = _eq(str(body.get("password", "")), env.get("ADMIN_PASSWORD", ""))
        return user_ok and pass_ok
    if mode == "key":
        return _eq(str(body.get("key", "")).strip(), env.get("MCP_AUTH_KEY", "").strip())
    return False


def _secret(env: Mapping[str, str]) -> Optional[bytes]:
    parts = [env.get("ADMIN_PASSWORD", ""), env.get("MCP_AUTH_KEY", ""),
             env.get("SESSION_ENCRYPTION_KEY", "")]
    if not any(parts):
        return None
    return hashlib.sha256(("igmcp-admin-cookie|" + "|".join(parts)).encode()).digest()


def make_token(env: Optional[Mapping[str, str]] = None, now: Optional[float] = None) -> Optional[str]:
    env = os.environ if env is None else env
    secret = _secret(env)
    if secret is None:
        return None
    exp = int((time.time() if now is None else now) + SESSION_SECONDS)
    sig = hmac.new(secret, str(exp).encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def verify_token(token: str, env: Optional[Mapping[str, str]] = None,
                 now: Optional[float] = None) -> bool:
    env = os.environ if env is None else env
    secret = _secret(env)
    if secret is None or not token or "." not in token:
        return False
    exp_s, _, sig = token.partition(".")
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < (time.time() if now is None else now):
        return False
    good = hmac.new(secret, exp_s.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good)


class LoginLimiter:
    """Best-effort brute-force guard (per serverless instance): 5 failures / 10 minutes."""

    def __init__(self, max_fails: int = 5, window: int = 600):
        self.max_fails, self.window = max_fails, window
        self._fails: Dict[str, List[float]] = {}

    def _recent(self, ip: str, now: float) -> List[float]:
        recent = [t for t in self._fails.get(ip, []) if now - t < self.window]
        self._fails[ip] = recent
        return recent

    def blocked(self, ip: str, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return len(self._recent(ip, now)) >= self.max_fails

    def fail(self, ip: str, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self._recent(ip, now).append(now)

    def reset(self, ip: str) -> None:
        self._fails.pop(ip, None)


def clean_sessionid(raw: str) -> str:
    """Accept what people actually paste: quotes, 'sessionid=' prefix, trailing ';'."""
    value = (raw or "").strip().strip('"').strip("'").strip()
    if value.lower().startswith("sessionid="):
        value = value[len("sessionid="):]
    return value.split(";")[0].strip()


def origin_from_headers(headers: Mapping[str, str], default_scheme: str = "https") -> str:
    scheme = headers.get("x-forwarded-proto") or default_scheme
    host = headers.get("x-forwarded-host") or headers.get("host") or ""
    return f"{scheme.split(',')[0].strip()}://{host.split(',')[0].strip()}" if host else ""
