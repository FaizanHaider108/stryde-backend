import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from ..lib.db import Base


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.uid"), nullable=False, unique=True, index=True)

    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    stripe_checkout_session_id = Column(String, nullable=True)

    status = Column(String, nullable=False, default="inactive")
    amount_cents = Column(Integer, nullable=False, default=1900)
    currency = Column(String, nullable=False, default="usd")
    is_active = Column(Boolean, nullable=False, default=False)
    current_period_end = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
