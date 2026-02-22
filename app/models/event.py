"""Event model and attendees association table.

Fields are grouped: PK, foreign keys, attributes, timestamps, then relationships.
"""
import enum
import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Uuid, Table, Enum, func
from sqlalchemy.orm import relationship
from ..lib.db import Base


class PaceIntensity(str, enum.Enum):
    """Intensity/pace categories for an Event."""
    easy = "Easy"
    tempo = "Tempo"
    intervals = "Intervals"


# Association Table for RSVPs (attendees)
event_attendees = Table(
    "event_attendees",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("event_id", Uuid, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("joined_at", DateTime(timezone=True), server_default=func.now()),
)


class Event(Base):
    """A community event hosted by a Club. Contains timing and route info."""
    __tablename__ = "events"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Foreign keys
    club_id = Column(Uuid, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    route_id = Column(Uuid, ForeignKey("routes.id", ondelete="RESTRICT"), nullable=False)

    # Attributes
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    pace_intensity = Column(Enum(PaceIntensity), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    club = relationship("Club", back_populates="events")
    creator = relationship("User", foreign_keys=[creator_id], back_populates="created_events")
    route = relationship("Route", back_populates="events")
    attendees = relationship("User", secondary=event_attendees, back_populates="attended_events")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
