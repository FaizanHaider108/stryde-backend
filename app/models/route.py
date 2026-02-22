import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Boolean, func, Uuid
from sqlalchemy.orm import relationship
from ..lib.db import Base

class Route(Base):
    __tablename__ = "routes"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    creator_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    
    # Basic Info
    name = Column(String, nullable=False) # e.g., "5km Shaded Trail"
    distance_km = Column(Float, nullable=False)
    elevation_gain_m = Column(Float, nullable=True) # The elevation field you mentioned
    
    # The Coordinates (Floats are perfect for Lat/Lng)
    start_lat = Column(Float, nullable=False)
    start_lng = Column(Float, nullable=False)
    start_address = Column(String, nullable=True) # Optional: just for UI display
    
    end_lat = Column(Float, nullable=False)
    end_lng = Column(Float, nullable=False)
    end_address = Column(String, nullable=True)

    completed_runs = relationship("Run", back_populates="route")
    
    # The Encoded Polyline string from your routing API to draw the actual path
    map_data = Column(String, nullable=False) 
    
    # Generation Tags (Optional, but great for filtering/searching later)
    # Based on your Figma UI toggles
    avoid_pollution = Column(Boolean, default=False)
    environment = Column(String, nullable=True) # e.g., "shade" or "open_air"
    terrain = Column(String, nullable=True) # e.g., "pavement" or "trail"
    elevation_profile = Column(String, nullable=True) # e.g., "flat" or "hilly"

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", back_populates="saved_routes")
    
    # Events that use this specific track
    events = relationship("Event", back_populates="route")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
