"""Club chat models: messages and read receipts."""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Text, Uuid, func
from sqlalchemy.orm import relationship

from ..lib.db import Base


class ClubMessage(Base):
    """Chat message posted inside a club."""
    __tablename__ = "club_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    club_id = Column(Uuid, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False, index=True)
    body = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    club = relationship("Club", back_populates="messages")
    sender = relationship("User", back_populates="club_messages")
    reads = relationship("ClubMessageRead", back_populates="message", cascade="all, delete-orphan")


class ClubMessageRead(Base):
    """Read receipt for a club message per user."""
    __tablename__ = "club_message_reads"

    message_id = Column(Uuid, ForeignKey("club_messages.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True)
    read_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("ClubMessage", back_populates="reads")
    user = relationship("User", back_populates="message_reads")
