import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationActor(BaseModel):
    uid: uuid.UUID
    full_name: str
    profile_image_s3_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    user_id: uuid.UUID
    actor: Optional[NotificationActor] = None
    club_id: Optional[uuid.UUID] = None
    event_id: Optional[uuid.UUID] = None
    post_id: Optional[uuid.UUID] = None
    comment_id: Optional[uuid.UUID] = None
    payload: Optional[dict] = None
    is_read: bool = False
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationReadResponse(BaseModel):
    id: uuid.UUID
    read_at: datetime


class NotificationReadRequest(BaseModel):
    notification_ids: list[uuid.UUID] = Field(default_factory=list)
