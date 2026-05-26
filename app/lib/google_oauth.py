"""Google OAuth (PKCE) for mobile — backend redirect so Expo Go avoids auth.expo.io."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from .security import ALGORITHM, SECRET_KEY

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


def _google_client_id() -> str:
    return (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or os.getenv("GOOGLE_WEB_CLIENT_ID") or "").strip()


def _google_client_secret() -> str:
    return (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()


def _google_oauth_public_url() -> str:
    """
    Base URL Google redirects to after sign-in (must be registered in Google Cloud).

    Web OAuth clients only allow https://… with a public domain, or http://localhost.
    LAN IPs (192.168.x.x) are rejected — use GOOGLE_OAUTH_PUBLIC_URL with ngrok/Render
    while keeping BACKEND_PUBLIC_URL as your LAN IP for the app API.
    """
    oauth_public = (os.getenv("GOOGLE_OAUTH_PUBLIC_URL") or "").strip().rstrip("/")
    if oauth_public:
        return oauth_public

    backend = (os.getenv("BACKEND_PUBLIC_URL") or "").strip().rstrip("/")
    if backend.startswith("https://"):
        return backend
    if backend.startswith("http://localhost") or backend.startswith("http://127.0.0.1"):
        return backend
    return backend


def google_oauth_configured() -> bool:
    public = _google_oauth_public_url()
    return bool(_google_client_id() and _google_client_secret() and public)


def google_callback_uri() -> str:
    public = _google_oauth_public_url()
    if not public:
        raise RuntimeError("GOOGLE_OAUTH_PUBLIC_URL or BACKEND_PUBLIC_URL is not configured")
    return f"{public}/api/v1/auth/google/callback"


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def create_google_oauth_state(after_path: str, app_return: str) -> str:
    """Signed state JWT embeds PKCE verifier, return URL, and after_path."""
    if not SECRET_KEY or not ALGORITHM:
        raise RuntimeError("JWT configuration missing")

    code_verifier = secrets.token_urlsafe(64)
    payload = {
        "cv": code_verifier,
        "after": after_path or "/(tabs)/home",
        "return": app_return,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_google_oauth_state(state: str) -> dict[str, Any]:
    if not SECRET_KEY or not ALGORITHM:
        raise ValueError("JWT configuration missing")
    return jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])


def build_google_authorization_url(state: str) -> str:
    client_id = _google_client_id()
    if not client_id:
        raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID is not configured")

    payload = decode_google_oauth_state(state)
    code_verifier = payload["cv"]

    params = {
        "client_id": client_id,
        "redirect_uri": google_callback_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": _pkce_challenge(code_verifier),
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _http_post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        logger.error("Google token exchange HTTP %s: %s", exc.code, raw)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": raw or "token_exchange_failed"}
        raise ValueError(payload.get("error_description") or payload.get("error") or "Google token exchange failed") from exc


def exchange_google_code(auth_code: str, code_verifier: str) -> dict[str, Any]:
    client_id = _google_client_id()
    client_secret = _google_client_secret()
    if not client_id or not client_secret:
        raise RuntimeError("Google OAuth client credentials are not configured on the server")

    return _http_post_form(
        GOOGLE_TOKEN_URL,
        {
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": google_callback_uri(),
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        },
    )


def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """Validate id_token audience and return claims (email, name, …)."""
    client_id = _google_client_id()
    url = f"{GOOGLE_TOKENINFO_URL}?{urllib.parse.urlencode({'id_token': id_token})}"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        logger.error("Google id_token verify failed: %s", raw)
        raise ValueError("Invalid Google identity token") from exc

    aud = payload.get("aud") or payload.get("azp")
    if aud != client_id:
        raise ValueError("Google token audience mismatch")

    email = payload.get("email")
    if not email:
        raise ValueError("Google did not return an email address")

    return payload


def append_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.update({k: v for k, v in params.items() if v})
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
