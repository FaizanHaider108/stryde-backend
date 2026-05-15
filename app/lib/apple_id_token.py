"""Verify Apple Sign In identity tokens (JWT) from native iOS clients."""

from __future__ import annotations

import os
from typing import Any

import jwt
from jwt import PyJWKClient

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"


class AppleTokenError(ValueError):
    """Raised when an Apple identity token is missing, misconfigured, or invalid."""


def _allowed_apple_client_ids() -> list[str]:
    """Comma-separated APPLE_CLIENT_ID values (bundle id; optionally host.exp.Exponent for Expo Go)."""
    raw = (os.getenv("APPLE_CLIENT_ID") or "").strip()
    return [part.strip() for part in raw.split(",") if part.strip()]


def verify_apple_identity_token(identity_token: str) -> dict[str, Any]:
    """
    Validate RS256 signature against Apple's JWKS and enforce iss / aud / exp.

    APPLE_CLIENT_ID is one or more comma-separated values. The token `aud` must match
    one of them. Use your iOS bundle id from app.json (expo.ios.bundleIdentifier). When
    testing Sign in with Apple inside Expo Go, Apple sets aud to host.exp.Exponent —
    add that as a second value for local dev only (omit in production).
    """
    allowed_ids = _allowed_apple_client_ids()
    if not allowed_ids:
        raise AppleTokenError("APPLE_CLIENT_ID is not configured on the server")

    if not identity_token or not isinstance(identity_token, str):
        raise AppleTokenError("Missing Apple identity token")

    try:
        jwks_client = PyJWKClient(APPLE_JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(identity_token)
        payload = jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=APPLE_ISSUER,
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppleTokenError("Apple identity token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AppleTokenError("Invalid Apple identity token") from exc

    aud = payload.get("aud")
    audiences = aud if isinstance(aud, list) else ([aud] if aud is not None else [])
    audiences = [a for a in audiences if isinstance(a, str)]
    if not any(cid in audiences for cid in allowed_ids):
        raise AppleTokenError(
            "Apple token audience does not match any configured APPLE_CLIENT_ID. "
            f"Token aud={audiences!r}, allowed={allowed_ids!r}. "
            "Use your ios.bundleIdentifier from app.json. If you use Expo Go, append "
            ",host.exp.Exponent to APPLE_CLIENT_ID for dev only; standalone builds use the bundle id only."
        )

    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise AppleTokenError("Apple token missing subject (sub)")

    return payload
