"""Username/password login with signed session cookies.

Users live in <data>/users.json with PBKDF2-SHA256 hashes. The signing
secret is generated once into <data>/secret.key. A fresh install gets the
default login admin / admin, which must be changed at first sign-in; after
that, only admins can add users.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path

COOKIE = "pf_session"
SESSION_TTL = 14 * 24 * 3600
_ITER = 240_000
_LOCK = threading.RLock()
_NAME = re.compile(r"^[A-Za-z0-9._@-]{3,64}$")
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"


class AuthError(Exception):
    pass


def _hash(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def _verify(password: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


class Auth:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "users.json"
        key = data_dir / "secret.key"
        if not key.exists():
            key.write_bytes(secrets.token_bytes(32))
            key.chmod(0o600)
        self.secret = key.read_bytes()

    # ---------- users ----------
    def _load(self) -> dict:
        with _LOCK:
            return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _save(self, users: dict) -> None:
        with _LOCK:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(users, indent=2))
            tmp.chmod(0o600)
            tmp.replace(self.path)

    def has_users(self) -> bool:
        return bool(self._load())

    def ensure_default_admin(self) -> bool:
        """Fresh install: create admin / admin, flagged so the password must be changed at first sign-in."""
        with _LOCK:
            if self._load():
                return False
            self._save({DEFAULT_USER: {"hash": _hash(DEFAULT_PASSWORD, secrets.token_bytes(16)), "admin": True,
                                       "created": time.time(), "must_change": True}})
            return True

    def default_login_active(self) -> bool:
        """True while the untouched default admin account still exists."""
        u = self._load().get(DEFAULT_USER)
        return bool(u and u.get("must_change"))

    def public(self, username: str) -> dict:
        u = self._load().get(username, {})
        return {"username": username, "admin": u.get("admin", False), "display_name": u.get("display_name") or "",
                "created": u.get("created"), "must_change": bool(u.get("must_change"))}

    def list_users(self) -> list[dict]:
        return [self.public(u) for u in sorted(self._load())]

    def set_display_name(self, username: str, display: str) -> None:
        display = " ".join((display or "").split())[:80]
        with _LOCK:
            users = self._load()
            if username not in users:
                raise AuthError("No such user")
            users[username]["display_name"] = display
            self._save(users)

    def rename(self, old: str, new: str) -> None:
        if not _NAME.match(new or ""):
            raise AuthError("Username must be 3-64 characters: letters, digits, . _ @ -")
        with _LOCK:
            users = self._load()
            if old not in users:
                raise AuthError("No such user")
            if new in users:
                raise AuthError("That username is already taken")
            users[new] = users.pop(old)
            self._save(users)

    def add_user(self, username: str, password: str, admin: bool = False) -> dict:
        if not _NAME.match(username or ""):
            raise AuthError("Username must be 3-64 characters: letters, digits, . _ @ -")
        if len(password or "") < 8:
            raise AuthError("Password must be at least 8 characters")
        with _LOCK:
            users = self._load()
            if username in users:
                raise AuthError("That username already exists")
            users[username] = {"hash": _hash(password, secrets.token_bytes(16)), "admin": admin, "created": time.time()}
            self._save(users)
        return {"username": username, "admin": admin}

    def delete_user(self, username: str) -> None:
        with _LOCK:
            users = self._load()
            if username not in users:
                raise AuthError("No such user")
            if users[username].get("admin") and sum(v.get("admin") for v in users.values()) <= 1:
                raise AuthError("Cannot delete the last admin")
            del users[username]
            self._save(users)

    def set_password(self, username: str, old: str | None, new: str) -> None:
        if len(new or "") < 8:
            raise AuthError("Password must be at least 8 characters")
        with _LOCK:
            users = self._load()
            u = users.get(username)
            if u is None or (old is not None and not _verify(old, u["hash"])):
                raise AuthError("Current password is wrong")
            if _verify(new, u["hash"]) or new == DEFAULT_PASSWORD:
                raise AuthError("Choose a new password that is different from the current one")
            u["hash"] = _hash(new, secrets.token_bytes(16))
            u.pop("must_change", None)
            u["sessions_after"] = time.time()  # log out other sessions
            self._save(users)

    def check(self, username: str, password: str) -> dict:
        u = self._load().get(username or "")
        # same cost whether or not the user exists
        if u is None:
            _verify(password or "", _hash("x", b"0" * 16))
            raise AuthError("Wrong username or password")
        if not _verify(password or "", u["hash"]):
            raise AuthError("Wrong username or password")
        return self.public(username)

    # ---------- sessions ----------
    def issue(self, username: str) -> str:
        payload = f"{username}|{int(time.time())}|{int(time.time()) + SESSION_TTL}"
        sig = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()

    def verify(self, token: str | None) -> dict | None:
        if not token:
            return None
        try:
            raw = base64.urlsafe_b64decode(token.encode()).decode()
            username, issued, exp, sig = raw.split("|")
        except (ValueError, UnicodeDecodeError):
            return None
        good = hmac.new(self.secret, f"{username}|{issued}|{exp}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(good, sig) or int(exp) < time.time():
            return None
        u = self._load().get(username)
        if u is None or int(issued) < u.get("sessions_after", 0) - 1:
            return None
        return {"username": username, "admin": u.get("admin", False), "display_name": u.get("display_name") or "",
                "must_change": bool(u.get("must_change"))}
