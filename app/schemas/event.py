import uuid
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

from .route import RouteResponse
from .club import SimpleUser


class EventCreate(BaseModel):
    route_id: uuid.UUID
    name: str
    description: Optional[str] = None
    start_time: datetime
    pace_intensity: str


class EventResponse(EventCreate):
    id: uuid.UUID
    creator_id: uuid.UUID
    route: Optional[RouteResponse] = None
    attendee_count: Optional[int] = 0
    is_current_user_attending: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)


class EventWithClubResponse(EventResponse):
    club_id: Optional[uuid.UUID] = None
    club_name: Optional[str] = None
    club_image_url: Optional[str] = None
    club_member_count: Optional[int] = None


class EventInvitationOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    inviter: Optional[SimpleUser]
    invitee: SimpleUser
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
