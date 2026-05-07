"""Run model — represents a user's recorded activity."""
import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import relationship
from ..lib.db import Base


class Run(Base):
    """A recorded run with metrics, geometry and optional links to Race/Plan."""
    __tablename__ = "runs"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Ownership
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)

    # Optional references
    route_id = Column(Uuid, ForeignKey("routes.id", ondelete="SET NULL"), nullable=True)
    race_id = Column(Uuid, ForeignKey("races.id", ondelete="SET NULL"), nullable=True)
    plan_workout_id = Column(Uuid, ForeignKey("plan_workouts.id", ondelete="SET NULL"), nullable=True)

    # Core athletic metrics
    distance_km = Column(Float, nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    average_pace = Column(Float, nullable=True)

    # Location / geometry
    start_lat = Column(Float, nullable=False)
    start_lng = Column(Float, nullable=False)
    end_lat = Column(Float, nullable=False)
    end_lng = Column(Float, nullable=False)
    map_data = Column(String, nullable=False)

    # Event times
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="runs")
    route = relationship("Route", back_populates="completed_runs")
    race = relationship("Race", back_populates="runs")
    plan_workout = relationship("PlanWorkout", back_populates="completed_runs")

    # Post relationship (a run can be shared as a single Post)
    posts = relationship("Post", back_populates="run")
    post = relationship("Post", back_populates="run", uselist=False, cascade="all, delete-orphan", overlaps="posts")
