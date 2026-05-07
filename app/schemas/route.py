from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
import uuid

from app.models.route import EnvironmentEnum, TerrainEnum, ElevationProfileEnum

class RouteCoordinate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class RouteBase(BaseModel):
    name: Optional[str] = None
    distance_km: float = Field(gt=0.1, le=120)
    elevation_gain_m: Optional[float] = None
    start_lat: float = Field(ge=-90, le=90)
    start_lng: float = Field(ge=-180, le=180)
    start_address: Optional[str] = None
    end_lat: float = Field(ge=-90, le=90)
    end_lng: float = Field(ge=-180, le=180)
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
    map_data: List[RouteCoordinate]
    distance_km: float
    duration_seconds: float
    elevation_gain_m: Optional[float] = None
