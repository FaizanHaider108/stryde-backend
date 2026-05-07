import uuid
from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class PlanWorkoutCreate(BaseModel):
    week_number: int
    day_name: str
    workout_type: str
    title: Optional[str] = None
    description: Optional[str] = None
    target_distance_km: Optional[float] = None
    target_duration_seconds: Optional[int] = None
    target_pace_kmh: Optional[float] = None
    variable_pace_data: Optional[dict] = None


class PlanWorkoutResponse(BaseModel):
    id: uuid.UUID
    week_number: int
    day_name: str
    workout_type: str
    title: Optional[str] = None
    description: Optional[str] = None
    target_distance_km: Optional[float] = None
    target_duration_seconds: Optional[int] = None
    target_pace_kmh: Optional[float] = None
    variable_pace_data: Optional[dict] = None

    class Config:
        from_attributes = True


class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    target_distance: str
    total_runs: int
    duration_weeks: int
    experience_level: str  # 'Beginner', 'Intermediate', 'Advanced', 'Pro'
    goal_type: str  # 'marathon' or 'race'


class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    target_distance: str
    total_runs: int
    duration_weeks: int
    experience_level: Optional[str] = None
    goal_type: Optional[str] = None
    key_workout_types: Optional[List[str]] = []
    is_custom_ai: Optional[bool] = False
    workouts: Optional[List[PlanWorkoutResponse]] = []

    class Config:
        from_attributes = True


class UserPlanCreate(BaseModel):
    plan_id: uuid.UUID
    start_date: Optional[date] = None


class UserPlanResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    start_date: date
    end_date: date
    is_active: bool
    plan: Optional[PlanResponse] = None
    plan_completion_percentage: Optional[float] = 0.0
    target_hit_percentage: Optional[float] = 0.0

    class Config:
        from_attributes = True


class CustomPlanGenerateRequest(BaseModel):
    goal_type: str
    ultimate_goal: Optional[str] = None
    target_pace_min_per_mile: Optional[float] = None
    start_date: date
    race_day: date
    off_days: List[str] = []
    long_run_day: Optional[str] = None
    experience_level: Optional[str] = "Intermediate"


class GeneratedWorkoutCreate(BaseModel):
    week_number: int
    day_name: str
    workout_type: str
    title: Optional[str] = None
    description: Optional[str] = None
    target_distance_km: Optional[float] = None
    target_duration_seconds: Optional[int] = None
    target_pace_kmh: Optional[float] = None
    variable_pace_data: Optional[dict] = None


class GeneratedPlanPayload(BaseModel):
    name: str
    description: Optional[str] = None
    target_distance: str
    total_runs: int
    duration_weeks: int
    experience_level: Optional[str] = None
    goal_type: Optional[str] = None
    key_workout_types: Optional[List[str]] = []
    workouts: List[GeneratedWorkoutCreate]
