"""Race model and association tables for save/register actions."""
import uuid
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, ForeignKey, Uuid, Table, func
from sqlalchemy.orm import relationship
from ..lib.db import Base


# Association tables for saves and registrations
saved_races = Table(
    "saved_races",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("race_id", Uuid, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
    Column("saved_at", DateTime(timezone=True), server_default=func.now()),
)

registered_races = Table(
    "registered_races",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("race_id", Uuid, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
    Column("registered_at", DateTime(timezone=True), server_default=func.now()),
)


class Race(Base):
    """Represents a race/event that users can browse, save and register for."""
    __tablename__ = "races"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Header / metadata
    name = Column(String, nullable=False, index=True)
    cover_image_url = Column(String, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    location_text = Column(String, nullable=False)

    # Distance info
    distance_label = Column(String, nullable=False)
    distance_km = Column(Float, nullable=False)

    # Course details
    map_data = Column(Text, nullable=False)
    elevation_gain_m = Column(Float, nullable=True)
    terrain_info = Column(String, nullable=True)

    # Organizer & external links
    organizer_name = Column(String, nullable=True)
    registration_url = Column(String, nullable=True)

    # Ratings cache
    average_rating = Column(Float, default=0.0)
    review_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    saved_by = relationship("User", secondary=saved_races, back_populates="saved_races")
    registered_participants = relationship("User", secondary=registered_races, back_populates="registered_races")
    runs = relationship("Run", back_populates="race")
    posts = relationship("Post", back_populates="race")
