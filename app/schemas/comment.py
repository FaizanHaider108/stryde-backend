import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CommentCreate(BaseModel):
    text: str


class CommentResponse(BaseModel):
    id: uuid.UUID
    text: str
    created_at: Optional[datetime] = None
    user: Optional[dict] = None
    likes_count: Optional[int] = 0
    is_liked_by_current_user: Optional[bool] = False

    class Config:
        orm_mode = True
