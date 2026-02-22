import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from .route import RouteResponse


class EventCreate(BaseModel):
    club_id: uuid.UUID
    route_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    pace_intensity: Optional[str] = None


class EventResponse(EventCreate):
    id: uuid.UUID
    creator_id: uuid.UUID
    route: Optional[RouteResponse] = None
    attendee_count: Optional[int] = 0
    is_current_user_attending: Optional[bool] = False

    class Config:
        orm_mode = True
