import os
from datetime import datetime, timezone
import importlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models.subscription import UserSubscription
from ...models.user import User

router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])


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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        stripe = _configure_stripe()
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Stripe dependency is not installed on server") from exc
    subscription = _get_or_create_subscription_row(db, current_user)

    app_scheme = os.getenv("APP_SCHEME", "stride")
    success_url = f"{app_scheme}://screens/subscription?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{app_scheme}://screens/subscription?checkout=cancel"

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
                    "product_data": {"name": "Stride Premium"},
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

    session = stripe.checkout.Session.retrieve(payload.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Invalid checkout session")

    session_metadata = _stripe_get(session, "metadata", {}) or {}
    user_id_from_session = _stripe_get(session_metadata, "user_id") or _stripe_get(session, "client_reference_id")
    if user_id_from_session and str(user_id_from_session) != str(current_user.uid):
        raise HTTPException(status_code=403, detail="This checkout session does not belong to you")

    subscription_id = _stripe_get(session, "subscription")
    payment_status = _stripe_get(session, "payment_status")
    checkout_status = _stripe_get(session, "status")

    is_active = checkout_status == "complete" and payment_status in {"paid", "no_payment_required"}
    status_value = "active" if is_active else "incomplete"
    current_period_end = None

    if subscription_id:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        subscription_id = stripe_sub.id
        status_value = stripe_sub.status or status_value
        current_period_end_ts = _stripe_get(stripe_sub, "current_period_end")
        if current_period_end_ts:
            current_period_end = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)
        is_active = status_value in {"active", "trialing"}

    subscription.stripe_checkout_session_id = payload.session_id
    subscription.stripe_subscription_id = subscription_id
    subscription.status = status_value
    subscription.is_active = is_active
    subscription.current_period_end = current_period_end
    db.commit()

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
