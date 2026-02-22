from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

class RunCreate(BaseModel):
    route_id: Optional[uuid.UUID] = None
    distance_km: float
    duration_seconds: uuid.UUID
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    end_lat: Optional[float] = None
    end_lng: Optional[float] = None
    map_data: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    plan_workout_id: Optional[uuid.UUID] = None


class RunResponse(RunCreate):
    id: uuid.UUID
    average_pace: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True

