"""Route model representing a saved/created route with geometry and tags."""
import enum
import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Boolean, func, Uuid, Enum
from sqlalchemy.orm import relationship
from ..lib.db import Base

class EnvironmentEnum(str, enum.Enum):
    max_shade = "maximum shade"
    open_air = "open air"

class TerrainEnum(str, enum.Enum):
    paved = "paved"
    unpaved = "unpaved"

class ElevationProfileEnum(str, enum.Enum):
    flat = "flat"
    hilly = "hilly"


class Route(Base):
    """Path/route created or saved by users.

    Groups: PK, FK, geometry fields, tags, timestamps, relationships.
    """
    __tablename__ = "routes"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Ownership
    creator_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)

    # Basic info
    name = Column(String, nullable=False)
    distance_km = Column(Float, nullable=False)
    elevation_gain_m = Column(Float, nullable=True)

    # Coordinates
    start_lat = Column(Float, nullable=False)
    start_lng = Column(Float, nullable=False)
    start_address = Column(String, nullable=True)
    end_lat = Column(Float, nullable=False)
    end_lng = Column(Float, nullable=False)
    end_address = Column(String, nullable=True)

    # Geometry and tags
    map_data = Column(String, nullable=False)
    avoid_pollution = Column(Boolean, default=False)
    environment = Column(Enum(EnvironmentEnum), nullable=True)
    terrain = Column(Enum(TerrainEnum), nullable=True)
    elevation_profile = Column(Enum(ElevationProfileEnum), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", back_populates="saved_routes")
    events = relationship("Event", back_populates="route")
    completed_runs = relationship("Run", back_populates="route")