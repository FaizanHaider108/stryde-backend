import uuid

from sqlalchemy import Column, DateTime, String, Uuid, func

from ..lib.db import Base


class GoogleOAuthExchange(Base):
    """
    Short-lived, one-time-use holder for tokens issued by the Google OAuth callback,
    handed to the mobile app via a poll (or, as a fallback, a deep-link xcode).

    Backed by the database (not an in-memory dict) because the Render free-tier
    instance spins down after idle periods and cold-starts on the next request,
    silently wiping any process-memory store — which left pending sign-ins polling
    forever with no way to recover the tokens the callback had already issued.
    """

    __tablename__ = "google_oauth_exchanges"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    xcode = Column(String, unique=True, index=True, nullable=False)
    poll_id = Column(String, unique=True, index=True, nullable=True)
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)
    after_path = Column(String, nullable=False, default="/(tabs)/home")
    error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
