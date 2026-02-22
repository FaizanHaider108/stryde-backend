from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid


class RouteCreate(BaseModel):
    name: str
    distance_km: float
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    map_data: Optional[str] = None
    avoid_pollution: Optional[bool] = False
    environment: Optional[str] = None
    terrain: Optional[str] = None
    elevation_profile: Optional[str] = None


class RouteResponse(RouteCreate):
    id: uuid.UUID
    creator_id: uuid.UUID
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True
