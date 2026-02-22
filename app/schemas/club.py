import uuid
from pydantic import BaseModel
from typing import Optional


class ClubCreate(BaseModel):
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None


class ClubResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    member_count: Optional[int] = 0
    current_user_role: Optional[str] = None

    class Config:
        orm_mode = True
