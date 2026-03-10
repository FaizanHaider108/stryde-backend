from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional
from uuid import UUID

class ExternalRaceSync(BaseModel):
    external_id: str = Field(..., description="The unique identifier from the external provider API.")
    external_provider: str = Field(default="xml_provider", description="The source of the data (e.g., runsignup, active).")
    name: str = Field(..., example="London Marathon 2026")
    start_time: datetime = Field(..., description="ISO 8601 formatted start date and time.")
    location_text: str = Field(..., example="London, UK")
    distance_km: float = Field(..., gt=0, description="Exact distance in kilometers.", example=42.195)
    distance_label: str = Field(..., example="Marathon")
    registration_url: Optional[str] = Field(default=None, description="External link for the user to register.")
    map_data: str = Field(default="{}", description="JSON string containing route coordinates or GPX data.")

class SyncResponse(BaseModel):
    message: str = Field(..., example="Race synced successfully")
    local_race_id: UUID = Field(..., description="The internal database UUID to be used as a foreign key.")

class RaceResponse(BaseModel):
    id: UUID
    name: str
    start_time: datetime
    location_text: str
    distance_km: float
    distance_label: str
    average_rating: float
    review_count: int
    
    model_config = ConfigDict(from_attributes=True)