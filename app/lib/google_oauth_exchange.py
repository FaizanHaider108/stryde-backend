"""One-time codes to hand JWT tokens to the mobile app without long deep-link URLs."""

from __future__ import annotations

import secrets
import time
from threading import Lock
from typing import Any

EXCHANGE_TTL_SECONDS = 300

_store: dict[str, dict[str, Any]] = {}
_lock = Lock()


def _purge_expired(now: float | None = None) -> None:
    ts = now if now is not None else time.time()
    expired = [key for key, entry in _store.items() if entry.get("exp", 0) <= ts]
    for key in expired:
        _store.pop(key, None)


def create_google_oauth_exchange_code(
    access_token: str,
    refresh_token: str,
    after_path: str,
) -> str:
    code = secrets.token_urlsafe(18)
    with _lock:
        _purge_expired()
        _store[code] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "after_path": after_path,
            "exp": time.time() + EXCHANGE_TTL_SECONDS,
        }
    return code


def consume_google_oauth_exchange_code(code: str) -> dict[str, str]:
    normalized = (code or "").strip()
    if not normalized:
        raise ValueError("Missing exchange code")

    with _lock:
        _purge_expired()
        entry = _store.pop(normalized, None)

    if not entry or entry.get("exp", 0) <= time.time():
        raise ValueError("Sign-in session expired. Please try Google sign-in again.")

    return {
        "access_token": str(entry["access_token"]),
        "refresh_token": str(entry["refresh_token"]),
        "after_path": str(entry.get("after_path") or "/(tabs)/home"),
    }
