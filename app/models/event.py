import enum
import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Uuid, Table, Enum, func
from sqlalchemy.orm import relationship
from ..lib.db import Base

# Enum for the Pace/Intensity
class PaceIntensity(str, enum.Enum):
    easy = "Easy"
    tempo = "Tempo"
    intervals = "Intervals"

# Association Table for RSVPs ("Members Joined")
event_attendees = Table(
    "event_attendees",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("event_id", Uuid, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("joined_at", DateTime(timezone=True), server_default=func.now())
)

# The Core Event Model
class Event(Base):
    __tablename__ = "events"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    
    # --- Foreign Keys ---
    club_id = Column(Uuid, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    
    # Route (Required)
    route_id = Column(Uuid, ForeignKey("routes.id", ondelete="RESTRICT"), nullable=False)
    
    # Details
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    pace_intensity = Column(Enum(PaceIntensity), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    club = relationship("Club", back_populates="events")
    
    # We specify foreign_keys here because User will have multiple relationships to Event
    creator = relationship("User", foreign_keys=[creator_id], back_populates="created_events")
    route = relationship("Route", back_populates="events")
    
    # The list of users attending
    attendees = relationship("User", secondary=event_attendees, back_populates="attended_events")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    