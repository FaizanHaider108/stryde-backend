import logging
import os
import urllib.parse
from datetime import datetime, timezone
import importlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...lib.db import get_db
from ...lib.google_oauth import append_query_params
from ...lib.security import get_current_user
from ...models.subscription import UserSubscription
from ...models.user import User

router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])
logger = logging.getLogger(__name__)


def _stripe_get(obj, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _configure_stripe():
    stripe = importlib.import_module("stripe")
    stripe_secret = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not stripe_secret:
        raise HTTPException(status_code=500, detail="Stripe is not configured")
    stripe.api_key = stripe_secret
    return stripe


def _get_or_create_subscription_row(db: Session, user: User) -> UserSubscription:
    sub = db.query(UserSubscription).filter(UserSubscription.user_id == user.uid).first()
    if sub:
        return sub
    sub = UserSubscription(user_id=user.uid)
    db.add(sub)
    db.flush()
    return sub


def _compute_effective_status(
    subscription: UserSubscription,
) -> tuple[bool, str, datetime | None]:
    period_end = subscription.current_period_end
    now_utc = datetime.now(timezone.utc)
    is_period_valid = period_end is None or period_end > now_utc
    is_status_active = subscription.status in {"active", "trialing"}
    is_active = bool(subscription.is_active and is_status_active and is_period_valid)

    if not is_period_valid:
        return False, "expired", period_end
    return is_active, subscription.status or "inactive", period_end


def _resolve_backend_public_url() -> str:
    url = (
        os.getenv("BACKEND_PUBLIC_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or os.getenv("GOOGLE_OAUTH_PUBLIC_URL")
        or ""
    ).strip().rstrip("/")
    if not url.startswith("https://"):
        raise HTTPException(
            status_code=500,
            detail="BACKEND_PUBLIC_URL must be set to your public https URL (required for Stripe checkout redirects)",
        )
    return url


def _default_app_return() -> str:
    app_scheme = os.getenv("APP_SCHEME", "stryde")
    return f"{app_scheme}://screens/subscription"


def _is_allowed_app_return(url: str) -> bool:
    parsed = urllib.parse.urlparse(url.strip())
    return parsed.scheme in {"stryde", "exp"}


def _build_stripe_redirect_urls(app_return: str) -> tuple[str, str]:
    """Stripe only accepts https success/cancel URLs — bridge through the backend, then deep-link to the app."""
    backend = _resolve_backend_public_url()
    encoded_return = urllib.parse.quote(app_return, safe="")
    success_url = (
        f"{backend}/api/v1/subscription/checkout-return"
        f"?checkout=success&session_id={{CHECKOUT_SESSION_ID}}&app_return={encoded_return}"
    )
    cancel_url = (
        f"{backend}/api/v1/subscription/checkout-return"
        f"?checkout=cancel&app_return={encoded_return}"
    )
    return success_url, cancel_url


class CheckoutSessionIn(BaseModel):
    """Mobile app sends app_return (deep link) so Stripe can redirect via this backend."""

    app_return: str | None = None
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutSessionOut(BaseModel):
    checkout_url: str
    session_id: str


class ConfirmSubscriptionIn(BaseModel):
    session_id: str


class SubscriptionStatusOut(BaseModel):
    is_active: bool
    status: str
    current_period_end: datetime | None = None


@router.post("/checkout-session", response_model=CheckoutSessionOut)
def create_checkout_session(
    payload: CheckoutSessionIn = CheckoutSessionIn(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        stripe = _configure_stripe()
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Stripe dependency is not installed on server") from exc
    subscription = _get_or_create_subscription_row(db, current_user)

    app_return = (payload.app_return or "").strip()
    if not app_return:
        legacy_success = (payload.success_url or "").strip()
        if legacy_success.startswith(("stryde://", "exp://")):
            app_return = legacy_success.split("?")[0]
    if not app_return or not _is_allowed_app_return(app_return):
        app_return = _default_app_return()

    success_url, cancel_url = _build_stripe_redirect_urls(app_return)
    logger.info(
        "checkout-session user=%s app_return=%s success_url=%s",
        current_user.email,
        app_return,
        success_url,
    )

    customer_id = subscription.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            name=current_user.full_name,
            metadata={"user_id": str(current_user.uid)},
        )
        customer_id = customer.id
        subscription.stripe_customer_id = customer_id

    stripe_price_id = os.getenv("STRIPE_PRICE_ID", "").strip()

    if stripe_price_id:
        line_items = [{"price": stripe_price_id, "quantity": 1}]
    else:
        line_items = [
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Stryde Premium"},
                    "unit_amount": 1900,
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }
        ]

    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
        client_reference_id=str(current_user.uid),
        metadata={"user_id": str(current_user.uid)},
    )

    subscription.stripe_checkout_session_id = checkout_session.id
    db.commit()

    return CheckoutSessionOut(
        checkout_url=checkout_session.url,
        session_id=checkout_session.id,
    )


@router.get("/checkout-return")
def checkout_return(
    checkout: str = "cancel",
    session_id: str | None = None,
    app_return: str | None = None,
):
    """Stripe success/cancel landing page — redirects into the mobile app deep link."""
    target = urllib.parse.unquote((app_return or "").strip())
    if not target or not _is_allowed_app_return(target):
        target = _default_app_return()

    params: dict[str, str] = {"checkout": checkout}
    if checkout == "success" and session_id:
        params["session_id"] = session_id

    redirect_url = append_query_params(target, params)
    logger.info("checkout-return redirect checkout=%s target=%s", checkout, redirect_url[:120])
    return RedirectResponse(redirect_url, status_code=302)


def _stripe_subscription_id(session) -> str | None:
    raw = _stripe_get(session, "subscription")
    if not raw:
        return None
    if isinstance(raw, str):
        return raw
    return _stripe_get(raw, "id")


@router.post("/confirm", response_model=SubscriptionStatusOut)
def confirm_subscription(
    payload: ConfirmSubscriptionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        stripe = _configure_stripe()
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Stripe dependency is not installed on server") from exc
    subscription = _get_or_create_subscription_row(db, current_user)

    session = stripe.checkout.Session.retrieve(
        payload.session_id,
        expand=["subscription"],
    )
    if not session:
        raise HTTPException(status_code=400, detail="Invalid checkout session")

    session_metadata = _stripe_get(session, "metadata", {}) or {}
    user_id_from_session = _stripe_get(session_metadata, "user_id") or _stripe_get(session, "client_reference_id")
    if user_id_from_session and str(user_id_from_session) != str(current_user.uid):
        raise HTTPException(status_code=403, detail="This checkout session does not belong to you")

    subscription_id = _stripe_subscription_id(session)
    payment_status = _stripe_get(session, "payment_status")
    checkout_status = _stripe_get(session, "status")

    session_paid = checkout_status == "complete" and payment_status in {"paid", "no_payment_required"}
    is_active = session_paid
    status_value = "active" if session_paid else (checkout_status or "incomplete")
    current_period_end = None

    if subscription_id:
        stripe_sub = _stripe_get(session, "subscription")
        if stripe_sub is None or isinstance(stripe_sub, str):
            stripe_sub = stripe.Subscription.retrieve(subscription_id)
        subscription_id = _stripe_get(stripe_sub, "id") or subscription_id
        sub_status = _stripe_get(stripe_sub, "status")
        if sub_status:
            status_value = sub_status
        current_period_end_ts = _stripe_get(stripe_sub, "current_period_end")
        if current_period_end_ts:
            current_period_end = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)
        if sub_status in {"active", "trialing"}:
            is_active = True
        elif session_paid:
            # Checkout finished — treat as active even if Stripe sub status lags briefly.
            is_active = True
            if status_value in {None, "", "incomplete", "open"}:
                status_value = "active"

    subscription.stripe_checkout_session_id = payload.session_id
    subscription.stripe_subscription_id = subscription_id
    subscription.status = status_value or "inactive"
    subscription.is_active = is_active
    subscription.current_period_end = current_period_end
    db.commit()

    logger.info(
        "subscription confirm session_id=%s checkout_status=%s payment_status=%s "
        "stripe_sub_id=%s status_value=%s is_active=%s user=%s",
        payload.session_id,
        checkout_status,
        payment_status,
        subscription_id,
        status_value,
        is_active,
        current_user.email,
    )

    return SubscriptionStatusOut(
        is_active=subscription.is_active,
        status=subscription.status,
        current_period_end=subscription.current_period_end,
    )


@router.get("/me", response_model=SubscriptionStatusOut)
def get_subscription_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subscription = db.query(UserSubscription).filter(UserSubscription.user_id == current_user.uid).first()
    if not subscription:
        return SubscriptionStatusOut(is_active=False, status="inactive", current_period_end=None)

    effective_is_active, effective_status, period_end = _compute_effective_status(subscription)
    if subscription.is_active != effective_is_active or subscription.status != effective_status:
        subscription.is_active = effective_is_active
        subscription.status = effective_status
        db.commit()

    return SubscriptionStatusOut(
        is_active=effective_is_active,
        status=effective_status,
        current_period_end=period_end,
    )
