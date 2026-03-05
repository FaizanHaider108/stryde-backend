from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
import uuid

from app.models.route import EnvironmentEnum, TerrainEnum, ElevationProfileEnum

class RouteCreate(BaseModel):
    name: str
    distance_km: float
    elevation_gain_m: Optional[float] = None
    start_lat: float
    start_lng: float
    start_address: Optional[str] = None
    end_lat: float
    end_lng: float
    end_address: Optional[str] = None
    map_data: str
    avoid_pollution: Optional[bool] = False
    environment: Optional[EnvironmentEnum] = None
    terrain: Optional[TerrainEnum] = None
    elevation_profile: Optional[ElevationProfileEnum] = None


class RouteResponse(RouteCreate):
    id: uuid.UUID
    creator_id: uuid.UUID
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
