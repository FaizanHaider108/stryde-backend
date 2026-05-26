from datetime import datetime, timedelta, timezone
import hashlib
import uuid

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..lib.security import (
    RESET_TOKEN_EXPIRE_MINUTES,
    generate_password_reset_token,
    get_password_hash,
    hash_password_reset_token,
    verify_password,
)
from ..models.password_reset import PasswordResetToken
from ..models.user import AuthProvider, RunnerType, User
from ..schemas.auth import UserCreate
from . import club as club_crud


def _normalize_email(email: str | None) -> str | None:
    if not email or not isinstance(email, str):
        return None
    normalized = email.strip().lower()
    return normalized or None


def get_user_by_email(db: Session, email: str):
    normalized = _normalize_email(email)
    if not normalized:
        return None
    return db.query(User).filter(func.lower(User.email) == normalized).first()


def get_user_by_apple_sub(db: Session, apple_sub: str):
    return db.query(User).filter(User.apple_sub == apple_sub).first()


def create_user(db: Session, user_in: UserCreate):
    normalized_email = _normalize_email(user_in.email)
    if not normalized_email:
        return None
    hashed = get_password_hash(user_in.password)
    user = User(
        full_name=user_in.full_name,
        email=normalized_email,
        password_hash=hashed,
        runner_type=RunnerType(user_in.runner_type.value if hasattr(user_in.runner_type, 'value') else user_in.runner_type),
        auth_provider=AuthProvider.credentials,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        # Auto-join the user to the community
        club_crud.auto_join_community(db, user)
    except IntegrityError:
        db.rollback()
        return None
    return user


def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not user.password_hash or not verify_password(password, user.password_hash):
        return None
    # Keep auth method in sync with the latest successful login path.
    if user.auth_provider != AuthProvider.credentials:
        user.auth_provider = AuthProvider.credentials
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def login_social_user(
    db: Session,
    email: str,
    full_name: str,
    runner_type,
    provider: str,
):
    """Find existing user by email and sign in, or create a new social account."""
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return None

    user = get_user_by_email(db, normalized_email)

    if user:
        if full_name and user.full_name != full_name:
            user.full_name = full_name

        user.auth_provider = AuthProvider(provider)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    resolved_runner_type = runner_type or RunnerType.social_stryder
    runner_value = resolved_runner_type.value if hasattr(resolved_runner_type, 'value') else resolved_runner_type

    user = User(
        full_name=full_name,
        email=normalized_email,
        password_hash=None,
        runner_type=RunnerType(runner_value),
        auth_provider=AuthProvider(provider),
    )
    db.add(user)

    try:
        db.commit()
        db.refresh(user)
        club_crud.auto_join_community(db, user)
        return user
    except IntegrityError:
        db.rollback()
        existing = get_user_by_email(db, normalized_email)
        if existing:
            if full_name and existing.full_name != full_name:
                existing.full_name = full_name
            existing.auth_provider = AuthProvider(provider)
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing
        return None


def _link_apple_to_existing_user(
    db: Session,
    existing: User,
    apple_sub: str,
    full_name: str,
    *,
    apple_email_matches: bool = False,
) -> User | None:
    """
    Sign in an existing account and attach this Apple ID.

    Apple issues a different `sub` per app/bundle (Expo Go vs TestFlight). When Apple
    returns an email that matches this account, treat it as the same person and re-link.
    """
    if existing.apple_sub and existing.apple_sub != apple_sub:
        if not apple_email_matches:
            return None
        # Same verified email — update Apple sub (e.g. moved from Expo Go to dev build).
        other = get_user_by_apple_sub(db, apple_sub)
        if other and other.uid != existing.uid:
            is_orphan_apple_row = (
                other.password_hash is None
                and other.auth_provider == AuthProvider.apple
                and (other.email.endswith("@example.com") or other.email.startswith("apple."))
            )
            if is_orphan_apple_row:
                db.delete(other)
                db.flush()
            else:
                return None
        existing.apple_sub = apple_sub
    elif not existing.apple_sub:
        existing.apple_sub = apple_sub

    existing.auth_provider = AuthProvider.apple
    if full_name and existing.full_name in ("Apple User", "") and full_name != "Apple User":
        existing.full_name = full_name
    db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


def _synthetic_apple_email(apple_sub: str) -> str:
    """Stable synthetic address (reserved example.com domain); local part stays short."""
    digest = hashlib.sha256(apple_sub.encode("utf-8")).hexdigest()[:32]
    return f"apple.{digest}@example.com"


def login_social_user_apple(
    db: Session,
    apple_sub: str,
    email_from_apple: str | None,
    full_name: str,
    runner_type,
):
    """
    Sign in with Apple: find by apple_sub or existing email, link when needed, or create once.

    This endpoint is used for both login and signup screens — an existing email always signs in;
    duplicate-email errors are only for email/password /signup.
    """
    user = get_user_by_apple_sub(db, apple_sub)
    if user:
        if full_name and user.full_name in ("Apple User", "") and full_name != "Apple User":
            user.full_name = full_name
        user.auth_provider = AuthProvider.apple
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    resolved_email = _normalize_email(email_from_apple)
    if resolved_email:
        existing = get_user_by_email(db, resolved_email)
        if existing:
            try:
                return _link_apple_to_existing_user(
                    db,
                    existing,
                    apple_sub,
                    full_name,
                    apple_email_matches=True,
                )
            except IntegrityError:
                db.rollback()
                linked = get_user_by_apple_sub(db, apple_sub)
                if linked:
                    return linked
                return None

    if not resolved_email:
        resolved_email = _synthetic_apple_email(apple_sub)
        while get_user_by_email(db, resolved_email):
            resolved_email = _synthetic_apple_email(f"{apple_sub}.{uuid.uuid4().hex[:8]}")

    resolved_runner_type = runner_type or RunnerType.social_stryder
    runner_value = resolved_runner_type.value if hasattr(resolved_runner_type, "value") else resolved_runner_type

    user = User(
        full_name=full_name or "Apple User",
        email=resolved_email,
        password_hash=None,
        runner_type=RunnerType(runner_value),
        auth_provider=AuthProvider.apple,
        apple_sub=apple_sub,
    )
    db.add(user)

    try:
        db.commit()
        db.refresh(user)
        club_crud.auto_join_community(db, user)
        return user
    except IntegrityError:
        db.rollback()
        linked = get_user_by_apple_sub(db, apple_sub)
        if linked:
            return linked
        if resolved_email:
            existing = get_user_by_email(db, resolved_email)
            if existing:
                try:
                    return _link_apple_to_existing_user(db, existing, apple_sub, full_name)
                except IntegrityError:
                    db.rollback()
                    return get_user_by_apple_sub(db, apple_sub)
        return None


def invalidate_password_reset_tokens(db: Session, user: User, now: datetime | None = None) -> None:
    timestamp = now or datetime.now(timezone.utc)
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.uid,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: timestamp}, synchronize_session=False)


def create_password_reset_token(db: Session, user: User, expires_in_minutes: int | None = None) -> tuple[str, PasswordResetToken]:
    now = datetime.now(timezone.utc)
    invalidate_password_reset_tokens(db, user, now=now)

    raw_token = generate_password_reset_token()
    token_hash = hash_password_reset_token(raw_token)
    expires_at = now + timedelta(minutes=expires_in_minutes or RESET_TOKEN_EXPIRE_MINUTES)

    reset_token = PasswordResetToken(
        user_id=user.uid,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(reset_token)
    db.commit()
    db.refresh(reset_token)

    return raw_token, reset_token


def get_valid_password_reset_token(db: Session, token_hash: str) -> PasswordResetToken | None:
    now = datetime.now(timezone.utc)
    return db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > now,
    ).first()


def reset_password_with_token(db: Session, reset_token: PasswordResetToken, new_password: str) -> User:
    user = reset_token.user
    if not user:
        raise ValueError("User not found for reset token")

    user.password_hash = get_password_hash(new_password)
    now = datetime.now(timezone.utc)
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.uid,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: now}, synchronize_session=False)

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


