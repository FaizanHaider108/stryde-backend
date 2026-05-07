"""Plan models: high-level plans, workouts and enrollments.

Group columns (PK, FKs, attributes, timestamps) and relationships for readability.
"""
import uuid
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, ForeignKey, Uuid, Boolean, Date, func, JSON
from sqlalchemy.orm import relationship
from ..lib.db import Base


class Plan(Base):
    """Overview plan template (global or user-created)."""
    __tablename__ = "plans"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Ownership / metadata
    is_custom_ai = Column(Boolean, default=False, nullable=False)
    creator_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=True)

    # Descriptive fields
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    target_distance = Column(String, nullable=False)
    total_runs = Column(Integer, nullable=False)
    duration_weeks = Column(Integer, nullable=False)
    experience_level = Column(String, nullable=True)
    goal_type = Column(String, nullable=True)  # 'marathon' or 'race'

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", back_populates="created_plans")
    workouts = relationship("PlanWorkout", back_populates="plan", cascade="all, delete-orphan")
    enrollments = relationship("UserPlan", back_populates="plan", cascade="all, delete-orphan")


class PlanWorkout(Base):
    """A single workout (day) within a `Plan`."""
    __tablename__ = "plan_workouts"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Foreign key to plan
    plan_id = Column(Uuid, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)

    # Scheduling
    week_number = Column(Integer, nullable=False)
    day_name = Column(String, nullable=False)

    # Workout details
    workout_type = Column(String, nullable=False)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    # Targets
    target_distance_km = Column(Float, nullable=True)
    target_duration_seconds = Column(Integer, nullable=True)
    target_pace_kmh = Column(Float, nullable=True)

    # Variable pace / display data
    variable_pace_data = Column(JSON, nullable=True)

    # Relationships
    plan = relationship("Plan", back_populates="workouts")
    completed_runs = relationship("Run", back_populates="plan_workout")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserPlan(Base):
    """A user's enrollment in a Plan (start/end dates and active flag)."""
    __tablename__ = "user_plans"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    plan_id = Column(Uuid, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)

    # Timeline
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="enrolled_plans")
    plan = relationship("Plan", back_populates="enrollments")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
