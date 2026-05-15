import logging
import os
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, quote
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ...crud.auth import (
    authenticate_user,
    create_password_reset_token,
    create_user,
    get_user_by_email,
    login_social_user,
    login_social_user_apple,
    get_valid_password_reset_token,
    reset_password_with_token,
)
from ...lib.db import get_db
from ...lib.mailer import send_email
from ...lib.firebase_admin_client import verify_firebase_id_token
from ...lib.apple_id_token import AppleTokenError, verify_apple_identity_token
from ...lib.security import (
    RESET_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password_reset_token,
)
from ...schemas.auth import (
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    SocialLoginRequest,
    Token,
    UserCreate,
    UserOut,
    UserSignIn,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _build_reset_link(raw_token: str) -> str:
    """
    Build password reset link.
    - If RESET_PASSWORD_URL contains `{token}`, it will be replaced.
    - Otherwise token is appended as query param.
    - Falls back to app deep-link route.
    """
    reset_url_base = (
        os.getenv("RESET_PASSWORD_URL")
        or os.getenv("RESET_PASSWORD_DEEP_LINK")
        or "stride://screens/setPassword"
    ).strip().strip("'\"")

    if "{token}" in reset_url_base:
        return reset_url_base.replace("{token}", raw_token)

    parsed = urlparse(reset_url_base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["token"] = raw_token
    return urlunparse(parsed._replace(query=urlencode(query)))


def _build_reset_email_link(raw_token: str) -> str:
    """
    Build a clickable link that email clients reliably open.
    Priority:
    1) RESET_PASSWORD_EMAIL_URL (supports {token}).
    2) BACKEND_PUBLIC_URL + /api/v1/auth/password-reset/open?token=...
    3) direct app deep link fallback.
    """
    # Prefer explicit email link if configured.
    email_url_base = (os.getenv("RESET_PASSWORD_EMAIL_URL") or "").strip().strip("'\"")
    if email_url_base:
        if "{token}" in email_url_base:
            return email_url_base.replace("{token}", quote(raw_token))
        parsed = urlparse(email_url_base)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["token"] = raw_token
        return urlunparse(parsed._replace(query=urlencode(query)))

    # Default: app deep link is most reliable for opening the app directly.
    return _build_reset_link(raw_token)


def _build_reset_bridge_link(raw_token: str) -> str | None:
    """Optional HTTP bridge URL (useful as fallback in some clients)."""
    backend_public = (os.getenv("BACKEND_PUBLIC_URL") or "").strip().rstrip("/")
    if backend_public:
        return f"{backend_public}/api/v1/auth/password-reset/open?token={quote(raw_token)}"
    return None


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = get_user_by_email(db, user_in.email)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already sexists please try another one",
        )
    user = create_user(db, user_in)
    if not user:
        # Handles race condition where another request inserted same email
        raise HTTPException(
            status_code=400,
            detail="Email already sexists please try another one",
        )
    return user


@router.post("/signin", response_model=Token)
def signin(form_data: UserSignIn, db: Session = Depends(get_db)):
    # using UserSignIn for simplicity: expects email and password fields
    user = authenticate_user(db, form_data.email, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    payload = {"full_name": user.full_name, "email": user.email, "runner_type": user.runner_type.value}
    access_token = create_access_token(payload)
    refresh_token = create_refresh_token({"email": user.email})
    return {"access_token": access_token, "refresh_token": refresh_token}


@router.post("/refresh", response_model=Token)
def refresh_tokens(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    refresh_payload = decode_refresh_token(payload.refresh_token)
    email = refresh_payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    token_payload = {"full_name": user.full_name, "email": user.email, "runner_type": user.runner_type.value}
    access_token = create_access_token(token_payload)
    rotated_refresh_token = create_refresh_token({"email": user.email})
    return {"access_token": access_token, "refresh_token": rotated_refresh_token}


@router.post("/logout", response_model=MessageResponse)
def logout():
    # Stateless JWT logout: client discards tokens.
    return {"message": "Logged out successfully"}


@router.post("/social-login", response_model=Token)
async def social_login(request: SocialLoginRequest, db: Session = Depends(get_db)):
    if request.provider.value == "google":
        try:
            firebase_payload = verify_firebase_id_token(request.token)
            email = firebase_payload.get("email")
            full_name = (
                firebase_payload.get("name")
                or request.name_from_frontend
                or "Google User"
            )
            firebase_sign_in_provider = (
                (firebase_payload.get("firebase") or {}).get("sign_in_provider")
            )
            if not email:
                raise HTTPException(status_code=400, detail="Invalid Firebase token")
            if firebase_sign_in_provider not in {"google.com", "custom"}:
                raise HTTPException(status_code=400, detail="Unsupported Firebase sign-in provider")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid Firebase token") from exc

        user = login_social_user(
            db=db,
            email=email,
            full_name=full_name,
            runner_type=request.runner_type,
            provider=request.provider.value,
        )

        if not user:
            raise HTTPException(status_code=400, detail="Could not create social account")

        token_payload = {
            "full_name": user.full_name,
            "email": user.email,
            "runner_type": user.runner_type.value,
        }
        access_token = create_access_token(token_payload)
        refresh_token = create_refresh_token({"email": user.email})
        return {"access_token": access_token, "refresh_token": refresh_token}

    if request.provider.value == "apple":
        try:
            payload = verify_apple_identity_token(request.token)
            apple_sub = str(payload.get("sub"))
            email_from_apple = payload.get("email")
            if isinstance(email_from_apple, str):
                email_from_apple = email_from_apple.strip() or None
            else:
                email_from_apple = None
            full_name = (request.name_from_frontend or "").strip() or "Apple User"
            user = login_social_user_apple(
                db=db,
                apple_sub=apple_sub,
                email_from_apple=email_from_apple,
                full_name=full_name,
                runner_type=request.runner_type,
            )
            if not user:
                raise HTTPException(
                    status_code=400,
                    detail="Could not create or link Apple account (email may already be in use).",
                )
            token_payload = {
                "full_name": user.full_name,
                "email": user.email,
                "runner_type": user.runner_type.value,
            }
            access_token = create_access_token(token_payload)
            refresh_token = create_refresh_token({"email": user.email})
            return {"access_token": access_token, "refresh_token": refresh_token}
        except AppleTokenError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid Apple token") from exc

    raise HTTPException(status_code=400, detail="Unsupported provider")


@router.post("/password-reset/request", response_model=MessageResponse)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, payload.email)
    if user:
        raw_token, _reset_token = create_password_reset_token(db, user)
        reset_link = _build_reset_link(raw_token)  # stride://... deep link
        email_click_link = _build_reset_email_link(raw_token)
        bridge_link = _build_reset_bridge_link(raw_token)
        subject = os.getenv("PASSWORD_RESET_SUBJECT", "Reset your Stryde password")
        body_parts = [
            "We received a request to reset your password.\n\n",
            f"Open this reset link: {email_click_link}\n\n",
        ]
        if bridge_link:
            body_parts.append(f"If that doesn't work, open: {bridge_link}\n\n")
        body_parts.extend(
            [
                f"This link expires in {RESET_TOKEN_EXPIRE_MINUTES} minutes.\n",
                "If you did not request a password reset, you can ignore this email.",
            ]
        )
        body = "".join(body_parts)
        bridge_fallback_html = (
            f'<p>If that does not work, try this fallback page:<br /><a href="{bridge_link}">{bridge_link}</a></p>'
            if bridge_link
            else ""
        )
        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #201E1F; line-height: 1.5;">
            <p>We received a request to reset your password.</p>
            <p>
              <a
                href="{email_click_link}"
                style="display:inline-block;padding:12px 18px;background:#201E1F;color:#E5E0D8;text-decoration:none;border-radius:8px;"
              >
                Reset Password
              </a>
            </p>
            <p>
              If the button does not work, copy and open this link:<br />
              <a href="{email_click_link}">{email_click_link}</a>
            </p>
            {bridge_fallback_html}
            <p>Direct app link:<br /><a href="{reset_link}">{reset_link}</a></p>
            <p>This link expires in {RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>
            <p>If you did not request a password reset, you can ignore this email.</p>
          </body>
        </html>
        """.strip()
        try:
            send_email(user.email, subject, body, html_body=html_body)
        except Exception:
            logger.exception("Failed to send password reset email")

    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    token_hash = hash_password_reset_token(payload.token)
    reset_token = get_valid_password_reset_token(db, token_hash)
    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    reset_password_with_token(db, reset_token, payload.new_password)
    return {"message": "Password reset successful"}


@router.get("/password-reset/open", response_class=HTMLResponse)
def open_password_reset(token: str):
    app_link = _build_reset_link(token)
    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Open Stryde Reset</title>
      </head>
      <body style="font-family: Arial, sans-serif; padding: 24px;">
        <h3>Opening Stryde...</h3>
        <p>If the app does not open automatically, tap the button below.</p>
        <p>
          <a href="{app_link}" style="display:inline-block;padding:12px 18px;background:#201E1F;color:#E5E0D8;text-decoration:none;border-radius:8px;">
            Open Reset Screen
          </a>
        </p>
        <p style="word-break: break-all;">{app_link}</p>
        <script>
          window.location.href = "{app_link}";
        </script>
      </body>
    </html>
    """.strip()
    return HTMLResponse(content=html)

