import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CommentCreate(BaseModel):
    text: str


class CommentUser(BaseModel):
    uid: str
    full_name: str
    profile_image_s3_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CommentResponse(BaseModel):
    id: uuid.UUID
    text: str
    created_at: Optional[datetime] = None
    user: Optional[CommentUser] = None
    likes_count: int = 0
    is_liked_by_current_user: bool = False

    model_config = ConfigDict(from_attributes=True)
