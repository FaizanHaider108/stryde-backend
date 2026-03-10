import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RunCreate(BaseModel):
    route_id: Optional[uuid.UUID] = None
    race_id: Optional[uuid.UUID] = None
    plan_workout_id: Optional[uuid.UUID] = None
    distance_km: float
    duration_seconds: int
    average_pace: Optional[float] = None
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    map_data: str
    start_time: datetime
    end_time: datetime


class RunResponse(RunCreate):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

