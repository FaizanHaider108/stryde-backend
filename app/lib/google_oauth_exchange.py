"""
One-time codes to hand JWT tokens to the mobile app without long deep-link URLs.

Backed by the database rather than an in-memory dict: Render's free-tier instance spins
down after idle periods and cold-starts on the next request, which silently wipes any
process-memory store. That left the callback issuing tokens seconds before the app's poll
loop ran, only for the poll to find nothing there and loop forever with no way to recover
tokens the callback had already issued.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models.google_oauth_exchange import GoogleOAuthExchange

EXCHANGE_TTL_SECONDS = 300


def _purge_expired(db: Session, now: datetime | None = None) -> None:
    ts = now or datetime.now(timezone.utc)
    db.query(GoogleOAuthExchange).filter(GoogleOAuthExchange.expires_at <= ts).delete(
        synchronize_session=False
    )


def create_google_oauth_exchange_code(
    db: Session,
    access_token: str,
    refresh_token: str,
    after_path: str,
    poll_id: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    _purge_expired(db, now)

    normalized_poll = (poll_id or "").strip() or None
    if normalized_poll:
        # poll_id is unique — clear out any stale row from an earlier attempt first.
        db.query(GoogleOAuthExchange).filter(
            GoogleOAuthExchange.poll_id == normalized_poll
        ).delete(synchronize_session=False)

    code = secrets.token_urlsafe(18)
    db.add(
        GoogleOAuthExchange(
            xcode=code,
            poll_id=normalized_poll,
            access_token=access_token,
            refresh_token=refresh_token,
            after_path=after_path,
            expires_at=now + timedelta(seconds=EXCHANGE_TTL_SECONDS),
        )
    )
    db.commit()
    return code


def register_google_oauth_poll_error(db: Session, poll_id: str, message: str) -> None:
    normalized_poll = (poll_id or "").strip()
    if not normalized_poll:
        return

    now = datetime.now(timezone.utc)
    _purge_expired(db, now)

    db.query(GoogleOAuthExchange).filter(
        GoogleOAuthExchange.poll_id == normalized_poll
    ).delete(synchronize_session=False)

    db.add(
        GoogleOAuthExchange(
            xcode=secrets.token_urlsafe(18),
            poll_id=normalized_poll,
            after_path="/(tabs)/home",
            error=message[:200],
            expires_at=now + timedelta(seconds=EXCHANGE_TTL_SECONDS),
        )
    )
    db.commit()


def consume_google_oauth_exchange_code(db: Session, code: str) -> dict[str, str]:
    normalized = (code or "").strip()
    if not normalized:
        raise ValueError("Missing exchange code")

    now = datetime.now(timezone.utc)
    _purge_expired(db, now)

    entry = (
        db.query(GoogleOAuthExchange)
        .filter(
            GoogleOAuthExchange.xcode == normalized,
            GoogleOAuthExchange.expires_at > now,
        )
        .first()
    )
    if not entry:
        raise ValueError("Sign-in session expired. Please try Google sign-in again.")

    error = entry.error
    access_token = entry.access_token
    refresh_token = entry.refresh_token
    after_path = entry.after_path or "/(tabs)/home"

    db.delete(entry)
    db.commit()

    if error:
        raise ValueError(str(error))

    return {
        "access_token": str(access_token),
        "refresh_token": str(refresh_token),
        "after_path": str(after_path),
    }


def poll_google_oauth_exchange(db: Session, poll_id: str) -> dict[str, str] | None:
    """Return token payload when ready, None while pending."""
    normalized_poll = (poll_id or "").strip()
    if not normalized_poll:
        return None

    now = datetime.now(timezone.utc)
    _purge_expired(db, now)

    entry = (
        db.query(GoogleOAuthExchange)
        .filter(
            GoogleOAuthExchange.poll_id == normalized_poll,
            GoogleOAuthExchange.expires_at > now,
        )
        .first()
    )
    if not entry:
        return None

    try:
        return consume_google_oauth_exchange_code(db, entry.xcode)
    except ValueError as exc:
        if str(exc) and "expired" not in str(exc).lower():
            raise
        return None
