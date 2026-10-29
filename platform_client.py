"""Talk to The_New_App platform: admin login, report upload, and a local record of what is online.

Login happens once a day on the website. Only the platform's login token is saved (in
.platform_session.json, readable by you only), never the password. The token is valid for 24 hours,
so the website and the daily auto upload can use it until it expires.
"""

import base64
import json
import os
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
SESSION_FILE = ROOT / ".platform_session.json"
HISTORY_FILE = ROOT / "upload_history.json"
RUN_LOG_DIR = ROOT / "logs" / "uploads"

PLATFORMS = {
    "local": {"label": "Local test", "api": os.environ.get("PLATFORM_LOCAL_API", "http://localhost:8083/api")},
    "production": {"label": "Production", "api": os.environ.get("PLATFORM_PRODUCTION_API", "https://yourtestresults.net/api")},
}


class NotConnected(Exception):
    """No valid login: never connected, token expired, or the platform rejected it."""


class PlatformError(Exception):
    """The platform could not be reached or answered with an error."""


def _token_expiry(token: str) -> datetime:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return datetime.fromtimestamp(json.loads(base64.urlsafe_b64decode(payload))["exp"])


def _write_private(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def login(platform: str, username: str, password: str) -> dict:
    if platform not in PLATFORMS:
        raise PlatformError(f"Unknown platform: {platform}")
    api = PLATFORMS[platform]["api"]
    try:
        r = httpx.post(f"{api}/login", json={"username": username, "password": password}, timeout=30)
    except httpx.HTTPError as e:
        raise PlatformError(f"Could not reach {api}: {e}") from e
    if r.status_code != 200:
        raise PlatformError(r.json().get("error", f"Login failed (HTTP {r.status_code})")
                            if r.headers.get("content-type", "").startswith("application/json")
                            else f"Login failed (HTTP {r.status_code})")
    body = r.json()
    if body.get("user", {}).get("domain_role") != "ADMINISTRATOR":
        raise PlatformError("This account is not an administrator, so it cannot upload reports.")
    session = {
        "platform": platform,
        "api": api,
        "username": username,
        "token": body["token"],
        "expires_at": _token_expiry(body["token"]).isoformat(timespec="seconds"),
    }
    _write_private(SESSION_FILE, session)
    return session


def load_session() -> dict | None:
    """The saved login, or None when there is none or it has expired."""
    try:
        session = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if datetime.fromisoformat(session["expires_at"]) <= datetime.now():
        logout()
        return None
    return session


def logout() -> None:
    SESSION_FILE.unlink(missing_ok=True)


def public_session(session: dict | None) -> dict:
    """Session info that is safe to show in the browser (no token)."""
    if not session:
        return {"connected": False}
    return {
        "connected": True,
        "platform": session["platform"],
        "label": PLATFORMS[session["platform"]]["label"],
        "username": session["username"],
        "expires_at": session["expires_at"],
    }


def upload_kit(session: dict, group: dict) -> dict:
    """Upload one kit's PDFs with its access code. Returns the platform's inserted/skipped/rejected lists."""
    handles = [open(f["path"], "rb") for f in group["files"]]
    try:
        files = [("files", (f["name"], h, "application/pdf")) for f, h in zip(group["files"], handles)]
        data = {"access_codes": [group["access_code"]] * len(handles)}
        r = httpx.post(f"{session['api']}/admin/reports/upload", files=files, data=data,
                       headers={"Authorization": f"Bearer {session['token']}"}, timeout=120)
    except httpx.HTTPError as e:
        raise PlatformError(f"Upload failed: {e}") from e
    finally:
        for h in handles:
            h.close()
    if r.status_code in (401, 403):
        logout()
        raise NotConnected("The login expired or is no longer an administrator. Please connect again.")
    if r.status_code != 200:
        raise PlatformError(f"Platform answered HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


# --- local record of upload results, per platform ---------------------------------------------

def load_history(platform: str) -> dict:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8")).get(platform, {})
    except (OSError, ValueError):
        return {}


def record_result(platform: str, kit: str, result: dict) -> dict:
    """Store the outcome of one kit upload and append it to today's run log. Returns per-file outcomes."""
    now = datetime.now().isoformat(timespec="seconds")
    outcomes = {}
    for name in result.get("inserted", []):
        outcomes[name] = {"result": "inserted", "at": now}
    for name in result.get("skipped", []):
        outcomes[name] = {"result": "skipped", "at": now}
    for entry in result.get("rejected", []):
        # The platform reports rejections as "<file>" or "<file> (<reason>)".
        name, _, reason = entry.partition(" (")
        outcomes[name] = {"result": "rejected", "reason": reason.rstrip(")") or "invalid file name", "at": now}

    try:
        everything = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        everything = {}
    everything.setdefault(platform, {}).update(outcomes)
    _write_private(HISTORY_FILE, everything)

    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (RUN_LOG_DIR / f"{datetime.now():%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"at": now, "platform": platform, "kit": kit, **result}) + "\n")
    return outcomes
