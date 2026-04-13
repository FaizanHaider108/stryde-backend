import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MessageSender(BaseModel):
    uid: uuid.UUID
    full_name: str
    profile_image_s3_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MessageReadOut(BaseModel):
    user_id: uuid.UUID
    read_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClubMessageOut(BaseModel):
    id: uuid.UUID
    club_id: uuid.UUID
    sender_id: uuid.UUID
    sender: Optional[MessageSender] = None
    body: str
    created_at: datetime
    reads: list[MessageReadOut] = Field(default_factory=list)
    is_read_by_current_user: bool = False

    model_config = ConfigDict(from_attributes=True)


class MessageReadRequest(BaseModel):
    message_ids: Optional[list[uuid.UUID]] = None
    up_to: Optional[datetime] = None


class MessageReadResponse(BaseModel):
    message_ids: list[uuid.UUID] = Field(default_factory=list)
    read_at: datetime
