import uuid
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, ForeignKey, Uuid, Boolean, Date, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from ..lib.db import Base

# The Overview Plan Template
class Plan(Base):
    __tablename__ = "plans"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    
    # Is this a Stryde global plan, or a user's Custom AI plan?
    is_custom_ai = Column(Boolean, default=False, nullable=False)
    creator_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=True)
    
    # Metadata
    name = Column(String, nullable=False) # e.g., "Sub-4 Hour Marathon"
    description = Column(Text, nullable=True)
    target_distance = Column(String, nullable=False) # e.g., "26.2 km"
    total_runs = Column(Integer, nullable=False) # e.g., 30
    duration_weeks = Column(Integer, nullable=False) # e.g., 6
    experience_level = Column(String, nullable=True) # e.g., "Intermediate"

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", back_populates="created_plans")
    workouts = relationship("PlanWorkout", back_populates="plan", cascade="all, delete-orphan")
    enrollments = relationship("UserPlan", back_populates="plan", cascade="all, delete-orphan")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# The Day-by-Day Schedule
class PlanWorkout(Base):
    __tablename__ = "plan_workouts"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    plan_id = Column(Uuid, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    
    # Scheduling details
    week_number = Column(Integer, nullable=False) # e.g., 1
    day_name = Column(String, nullable=False) # e.g., "Monday"
    
    # Workout details (Screenshots 2 & 3)
    workout_type = Column(String, nullable=False) # e.g., "Easy Run", "Tempo Run", "Rest"
    title = Column(String, nullable=True) # e.g., "Run 1 - Monday"
    description = Column(Text, nullable=True)
    
    # Targets (Nullable because "Rest" days have no targets)
    target_distance_km = Column(Float, nullable=True)
    target_duration_seconds = Column(Integer, nullable=True)
    target_pace_kmh = Column(Float, nullable=True)
    
    # The Tempo/Variable Pace Graphic Data
    # Stores a JSON array like: [{"distance": "1km", "pace": "6km/hr", "type": "warm-up"}, ...]
    variable_pace_data = Column(JSONB, nullable=True) 

    # Relationships
    plan = relationship("Plan", back_populates="workouts")
    
    # Links to the actual physical runs the user does to complete this workout
    completed_runs = relationship("Run", back_populates="plan_workout")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# The Active Enrollment
class UserPlan(Base):
    __tablename__ = "user_plans"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    plan_id = Column(Uuid, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    
    # Timeline
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    # Allows a user to pause or abandon a plan
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="enrolled_plans")
    plan = relationship("Plan", back_populates="enrollments")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
