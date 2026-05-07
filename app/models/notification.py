"""Notification models for realtime updates."""
import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, JSON, Uuid, func
from sqlalchemy.orm import relationship

from ..lib.db import Base


class NotificationType(str, enum.Enum):
    club_invitation = "club_invitation"
    event_invitation = "event_invitation"
    follow = "follow"
    post_like = "post_like"
    post_comment = "post_comment"
    comment_like = "comment_like"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(Uuid, ForeignKey("users.uid", ondelete="SET NULL"), nullable=True, index=True)
    type = Column(Enum(NotificationType), nullable=False)

    club_id = Column(Uuid, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True, index=True)
    event_id = Column(Uuid, ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True)
    post_id = Column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True, index=True)
    comment_id = Column(Uuid, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True)

    payload = Column(JSON, nullable=True)

    is_read = Column(Boolean, nullable=False, server_default="false")
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id], back_populates="notifications")
    actor = relationship("User", foreign_keys=[actor_id], back_populates="sent_notifications")
