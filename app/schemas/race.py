import uuid

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    cover_image_url: Optional[str] = None
    start_time: Optional[datetime] = None
    location_text: Optional[str] = None
    distance_label: Optional[str] = None
    distance_km: Optional[float] = None
    map_data: Optional[str] = None
    organizer_name: Optional[str] = None
    registration_url: Optional[str] = None
    is_saved_by_current_user: Optional[bool] = False
    is_registered_by_current_user: Optional[bool] = False

    class Config:
        orm_mode = True
