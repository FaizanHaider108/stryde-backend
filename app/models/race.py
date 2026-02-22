import uuid
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, ForeignKey, Uuid, Table, func
from sqlalchemy.orm import relationship
from ..lib.db import Base

# Association Table for SAVED Races (The "Save Race" button)
saved_races = Table(
    "saved_races",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("race_id", Uuid, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
    Column("saved_at", DateTime(timezone=True), server_default=func.now())
)

# Association Table for REGISTERED Races (The "Register" button)
registered_races = Table(
    "registered_races",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("race_id", Uuid, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
    Column("registered_at", DateTime(timezone=True), server_default=func.now())
)

# The Core Race Model
class Race(Base):
    __tablename__ = "races"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    
    # --- Header Info ---
    name = Column(String, nullable=False, index=True) # e.g., "Chicago Marathon"
    cover_image_url = Column(String, nullable=True) # The hero image of the runners
    start_time = Column(DateTime(timezone=True), nullable=False)
    location_text = Column(String, nullable=False) # e.g., "Chicago, Illinois, USA"
    
    # --- Distance Handling ---
    distance_label = Column(String, nullable=False) # e.g., "Marathon", "Half Marathon", "5K"
    distance_km = Column(Float, nullable=False) # Store in KM internally for math (42.195), let frontend convert to Miles for UI
    
    # --- Course Details (Map & Elevation) ---
    map_data = Column(Text, nullable=False) # The encoded polyline to draw the course
    elevation_gain_m = Column(Float, nullable=True) # e.g., 84
    terrain_info = Column(String, nullable=True) # e.g., "Paved roads, urban environment"
    
    # --- Organizer & Metadata ---
    organizer_name = Column(String, nullable=True) # e.g., "Bank of America Chicago Marathon"
    registration_url = Column(String, nullable=True) # External link for the "Register" button
    
    # --- Ratings (Cached for fast loading) ---
    average_rating = Column(Float, default=0.0) 
    review_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # --- Relationships ---
    
    # Users who tapped "Save Race"
    saved_by = relationship("User", secondary=saved_races, back_populates="saved_races")
    
    # Users who tapped "Register"
    registered_participants = relationship("User", secondary=registered_races, back_populates="registered_races")
    
    # Links to the actual runs users submit on race day
    runs = relationship("Run", back_populates="race")
    # Links to all posts where users are talking about this race
    posts = relationship("Post", back_populates="race")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
