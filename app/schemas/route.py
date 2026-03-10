from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
import uuid

from app.models.route import EnvironmentEnum, TerrainEnum, ElevationProfileEnum

class RouteBase(BaseModel):
    name: Optional[str] = None
    distance_km: float
    elevation_gain_m: Optional[float] = None
    start_lat: float
    start_lng: float
    start_address: Optional[str] = None
    end_lat: float
    end_lng: float
    end_address: Optional[str] = None
    map_data: Optional[str] = None
    avoid_pollution: Optional[bool] = False
    environment: Optional[EnvironmentEnum] = None
    terrain: Optional[TerrainEnum] = None
    elevation_profile: Optional[ElevationProfileEnum] = None

class RouteSave(RouteBase):
    pass

class RouteCreate(RouteBase):
    pass

class RouteResponse(RouteBase):
    id: uuid.UUID
    creator_id: uuid.UUID
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class RouteCreateResponse(BaseModel):
    map_data: str  # The encoded polyline string or GeoJSON
    distance_meters: float
    duration_seconds: float
    # Optional: You can echo back the start/end coordinates if the frontend needs them
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
