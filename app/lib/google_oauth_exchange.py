"""One-time codes to hand JWT tokens to the mobile app without long deep-link URLs."""

from __future__ import annotations

import secrets
import time
from threading import Lock
from typing import Any

EXCHANGE_TTL_SECONDS = 300

_store: dict[str, dict[str, Any]] = {}
_poll_index: dict[str, str] = {}  # poll_id -> xcode
_lock = Lock()


def _purge_expired(now: float | None = None) -> None:
    ts = now if now is not None else time.time()
    expired = [key for key, entry in _store.items() if entry.get("exp", 0) <= ts]
    for key in expired:
        _store.pop(key, None)
    expired_polls = [
        poll_id
        for poll_id, xcode in list(_poll_index.items())
        if xcode not in _store
    ]
    for poll_id in expired_polls:
        _poll_index.pop(poll_id, None)


def create_google_oauth_exchange_code(
    access_token: str,
    refresh_token: str,
    after_path: str,
    poll_id: str | None = None,
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
        normalized_poll = (poll_id or "").strip()
        if normalized_poll:
            _poll_index[normalized_poll] = code
    return code


def register_google_oauth_poll_error(poll_id: str, message: str) -> None:
    normalized_poll = (poll_id or "").strip()
    if not normalized_poll:
        return
    code = secrets.token_urlsafe(18)
    with _lock:
        _purge_expired()
        _store[code] = {
            "error": message[:200],
            "exp": time.time() + EXCHANGE_TTL_SECONDS,
        }
        _poll_index[normalized_poll] = code


def consume_google_oauth_exchange_code(code: str) -> dict[str, str]:
    normalized = (code or "").strip()
    if not normalized:
        raise ValueError("Missing exchange code")

    with _lock:
        _purge_expired()
        entry = _store.pop(normalized, None)
        if entry:
            for poll_id, xcode in list(_poll_index.items()):
                if xcode == normalized:
                    _poll_index.pop(poll_id, None)

    if not entry or entry.get("exp", 0) <= time.time():
        raise ValueError("Sign-in session expired. Please try Google sign-in again.")

    if entry.get("error"):
        raise ValueError(str(entry["error"]))

    return {
        "access_token": str(entry["access_token"]),
        "refresh_token": str(entry["refresh_token"]),
        "after_path": str(entry.get("after_path") or "/(tabs)/home"),
    }


def poll_google_oauth_exchange(poll_id: str) -> dict[str, Any] | None:
    """Return token payload when ready, None while pending."""
    normalized_poll = (poll_id or "").strip()
    if not normalized_poll:
        return None

    with _lock:
        _purge_expired()
        xcode = _poll_index.get(normalized_poll)

    if not xcode:
        return None

    try:
        return consume_google_oauth_exchange_code(xcode)
    except ValueError as exc:
        if str(exc) and "expired" not in str(exc).lower():
            raise
        return None
