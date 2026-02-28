import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Uuid, func
from sqlalchemy.orm import relationship

from ..lib.db import Base


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class ClubInvitation(Base):
    __tablename__ = "club_invitations"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    club_id = Column(Uuid, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    inviter_id = Column(Uuid, ForeignKey("users.uid", ondelete="SET NULL"), nullable=True)
    invitee_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(InvitationStatus), default=InvitationStatus.pending, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    club = relationship("Club", back_populates="invitations")
    inviter = relationship("User", foreign_keys=[inviter_id])
    invitee = relationship("User", foreign_keys=[invitee_id])


class EventInvitation(Base):
    """Invitation to a specific Event within a Club.

    Stored separately from club invitations so event RSVP flows can be tracked.
    """
    __tablename__ = "event_invitations"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id = Column(Uuid, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    inviter_id = Column(Uuid, ForeignKey("users.uid", ondelete="SET NULL"), nullable=True)
    invitee_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(InvitationStatus), default=InvitationStatus.pending, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("Event")
    inviter = relationship("User", foreign_keys=[inviter_id])
    invitee = relationship("User", foreign_keys=[invitee_id])
