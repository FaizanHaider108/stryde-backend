import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import relationship
from ..lib.db import Base

class Run(Base):
    __tablename__ = "runs"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    
    # Who ran it?
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    
    # Did they follow a specific community Route? (Nullable)
    route_id = Column(Uuid, ForeignKey("routes.id", ondelete="SET NULL"), nullable=True)
    
    # Core Athletic Metrics
    distance_km = Column(Float, nullable=False)
    duration_seconds = Column(Integer, nullable=False) # Storing seconds makes math/charts much easier!
    average_pace = Column(Float, nullable=True) # e.g., minutes per kilometer
    
    # Location Data (The actual physical execution)
    start_lat = Column(Float, nullable=False)
    start_lng = Column(Float, nullable=False)
    end_lat = Column(Float, nullable=False)
    end_lng = Column(Float, nullable=False)
    
    # The Encoded Polyline string of their exact GPS path
    map_data = Column(String, nullable=False) 
    
    # Timestamps
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="runs")
    route = relationship("Route", back_populates="completed_runs")
    # A single run can theoretically be shared multiple times (e.g., as a throwback)
    posts = relationship("Post", back_populates="run")
    
    # Connects to the social feed. uselist=False makes it a 1-to-1 relationship.
    # (A run can only be shared as a single post)
    post = relationship("Post", back_populates="run", uselist=False, cascade="all, delete-orphan")

    # Add to the columns:
    race_id = Column(Uuid, ForeignKey("races.id", ondelete="SET NULL"), nullable=True)
    race = relationship("Race", back_populates="runs")

    # Plan Workout Link (Nullable because not all runs are tied to a plan workout)
    plan_workout_id = Column(Uuid, ForeignKey("plan_workouts.id", ondelete="SET NULL"), nullable=True)
    plan_workout = relationship("PlanWorkout", back_populates="completed_runs")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
