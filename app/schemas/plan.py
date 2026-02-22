import uuid
from pydantic import BaseModel
from typing import Optional, List


class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    target_distance: Optional[float] = None
    total_runs: Optional[int] = None
    duration_weeks: Optional[int] = None
    experience_level: Optional[str] = None
    is_custom_ai: Optional[bool] = False

    class Config:
        orm_mode = True


class PlanWorkoutResponse(BaseModel):
    week_number: int
    day_name: str
    workout_type: str
    target_distance_km: Optional[float] = None
    variable_pace_data: Optional[dict] = None


class UserPlanResponse(BaseModel):
    plan_id: uuid.UUID
    start_date: Optional[str] = None
    is_active: Optional[bool] = True
    plan_completion_percentage: Optional[float] = 0.0
    target_hit_percentage: Optional[float] = 0.0
    workouts: Optional[List[PlanWorkoutResponse]] = []

    class Config:
        orm_mode = True
