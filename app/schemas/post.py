import uuid
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class PostCreate(BaseModel):
    caption: Optional[str] = None
    run_id: Optional[uuid.UUID] = None
    race_id: Optional[uuid.UUID] = None
    images: Optional[List[str]] = []


class PostResponse(BaseModel):
    id: uuid.UUID
    caption: Optional[str] = None
    created_at: Optional[datetime] = None
    user: Optional[dict] = None
    images: Optional[List[str]] = []
    run: Optional[dict] = None
    race: Optional[dict] = None
    likes_count: Optional[int] = 0
    comments_count: Optional[int] = 0
    is_liked_by_current_user: Optional[bool] = False

    class Config:
        orm_mode = True
