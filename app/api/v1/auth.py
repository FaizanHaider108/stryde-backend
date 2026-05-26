import logging
import os
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, quote
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
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
from ...crud.profile import build_profile_response
from ...lib.db import get_db
from ...lib.mailer import send_email
from ...lib.firebase_admin_client import verify_firebase_id_token
from ...lib.apple_id_token import AppleTokenError, verify_apple_identity_token
from ...lib.google_oauth import (
    append_query_params,
    build_google_authorization_url,
    create_google_oauth_state,
    decode_google_oauth_state,
    exchange_google_code,
    google_callback_uri,
    google_oauth_configured,
    google_oauth_setup,
    verify_google_id_token,
)
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
    SocialLoginResponse,
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
        or "stryde://screens/setPassword"
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
            detail="email already registered",
        )
    user = create_user(db, user_in)
    if not user:
        raise HTTPException(
            status_code=400,
            detail="email already registered",
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


@router.post("/social-login", response_model=SocialLoginResponse)
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
                logger.warning("Google social-login: Firebase token missing email")
                raise HTTPException(
                    status_code=400,
                    detail="Google did not provide an email address. Check your Google account settings.",
                )
            if firebase_sign_in_provider not in {"google.com", "custom"}:
                logger.warning(
                    "Google social-login: unsupported provider %s",
                    firebase_sign_in_provider,
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported Google sign-in provider: {firebase_sign_in_provider}",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Google social-login: Firebase token verification failed")
            raise HTTPException(
                status_code=400,
                detail="Invalid Google token. Sign out and try again.",
            ) from exc

        user = login_social_user(
            db=db,
            email=email,
            full_name=full_name,
            runner_type=request.runner_type,
            provider=request.provider.value,
        )

        if not user:
            logger.error("Google social-login: could not find or create user for %s", email)
            raise HTTPException(
                status_code=400,
                detail="Could not sign in with Google. Please try again.",
            )

        token_payload = {
            "full_name": user.full_name,
            "email": user.email,
            "runner_type": user.runner_type.value,
        }
        access_token = create_access_token(token_payload)
        refresh_token = create_refresh_token({"email": user.email})
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "profile": build_profile_response(user),
        }

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
                if email_from_apple:
                    existing = get_user_by_email(db, email_from_apple)
                    if existing and existing.apple_sub and existing.apple_sub != apple_sub:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "This email is linked to another Apple sign-in from a different app build. "
                                "Try signing in with your email and password, or contact support to merge accounts."
                            ),
                        )
                logger.error(
                    "Apple social-login failed for sub=%s email=%s",
                    apple_sub,
                    email_from_apple,
                )
                raise HTTPException(
                    status_code=400,
                    detail="Could not sign in with Apple. Please try again.",
                )
            token_payload = {
                "full_name": user.full_name,
                "email": user.email,
                "runner_type": user.runner_type.value,
            }
            access_token = create_access_token(token_payload)
            refresh_token = create_refresh_token({"email": user.email})
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "profile": build_profile_response(user),
            }
        except AppleTokenError as exc:
            logger.warning("Apple social-login token error: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Apple social-login failed")
            raise HTTPException(status_code=400, detail="Invalid Apple token") from exc

    raise HTTPException(status_code=400, detail="Unsupported provider")


@router.get("/google/setup")
def google_oauth_setup_info():
    """
    Returns the exact redirect_uri to register in Google Cloud Console (Web OAuth client).
    Open in a browser or curl after deploy to verify Render env matches Google Console.
    """
    info = google_oauth_setup()
    if not info["configured"]:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Google OAuth env vars missing on this server.",
                "required": [
                    "GOOGLE_OAUTH_CLIENT_ID",
                    "GOOGLE_OAUTH_CLIENT_SECRET",
                    "BACKEND_PUBLIC_URL=https://your-service.onrender.com (or GOOGLE_OAUTH_PUBLIC_URL)",
                ],
                **info,
            },
        )
    return {
        **info,
        "instructions": (
            "Google Cloud Console → APIs & Services → Credentials → "
            "OAuth 2.0 Client IDs → Web client (same client_id above) → "
            "Authorized redirect URIs → paste redirect_uri exactly (no trailing slash)."
        ),
    }


@router.get("/google/start")
def google_oauth_start(
    app_return: str,
    after_path: str = "/(tabs)/home",
):
    """
    Expo Go / LAN dev: browser opens here, Google redirects to our backend callback,
    then we deep-link back to the app with JWT tokens (skips broken auth.expo.io).
    """
    if not google_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google OAuth is not configured on the server. "
                "Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, and "
                "GOOGLE_OAUTH_PUBLIC_URL (https ngrok/Render URL — Google rejects 192.168.x.x)."
            ),
        )
    if not app_return.strip():
        raise HTTPException(status_code=400, detail="app_return is required")

    try:
        callback = google_callback_uri()
        logger.info("Google OAuth start — redirect_uri=%s", callback)
        state = create_google_oauth_state(after_path=after_path, app_return=app_return)
        return RedirectResponse(build_google_authorization_url(state), status_code=302)
    except Exception as exc:
        logger.exception("Google OAuth start failed")
        raise HTTPException(status_code=500, detail="Could not start Google sign-in") from exc


@router.get("/google/callback")
def google_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Exchange Google code, create/find user, redirect to app with Stryde JWT tokens."""
    app_return = "stryde://oauth/google"
    after_path = "/(tabs)/home"

    try:
        if not state:
            raise ValueError("Missing OAuth state")
        decoded = decode_google_oauth_state(state)
        app_return = str(decoded.get("return") or app_return)
        after_path = str(decoded.get("after") or after_path)
        code_verifier = str(decoded["cv"])

        if error:
            raise ValueError(error)
        if not code:
            raise ValueError("Google did not return an authorization code")

        token_payload = exchange_google_code(code, code_verifier)
        id_token = token_payload.get("id_token")
        if not id_token:
            raise ValueError("Google did not return an identity token")

        claims = verify_google_id_token(str(id_token))
        email = str(claims["email"])
        full_name = str(claims.get("name") or "Google User")

        user = login_social_user(
            db=db,
            email=email,
            full_name=full_name,
            runner_type="social stryder",
            provider="google",
        )
        if not user:
            raise ValueError("Could not sign in with Google")

        access_token = create_access_token(
            {
                "full_name": user.full_name,
                "email": user.email,
                "runner_type": user.runner_type.value,
            }
        )
        refresh_token = create_refresh_token({"email": user.email})

        logger.info("Google OAuth callback OK for %s — redirecting to app", email)

        redirect_url = append_query_params(
            app_return,
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "after_path": after_path,
            },
        )
        return RedirectResponse(redirect_url, status_code=302)
    except Exception as exc:
        logger.exception("Google OAuth callback failed")
        message = str(exc) if str(exc) else "Google sign-in failed"
        redirect_url = append_query_params(
            app_return,
            {"oauth_error": message[:200]},
        )
        return RedirectResponse(redirect_url, status_code=302)


@router.post("/password-reset/request", response_model=MessageResponse)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, payload.email)
    if user:
        raw_token, _reset_token = create_password_reset_token(db, user)
        reset_link = _build_reset_link(raw_token)  # stryde://... deep link
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

