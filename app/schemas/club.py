from datetime import datetime
from enum import Enum
from typing import Optional
import uuid
from pydantic import BaseModel
from typing import Optional

from pydantic import BaseModel

class ClubCreate(BaseModel):
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None


class SimpleUser(BaseModel):
    uid: uuid.UUID
    full_name: str
    profile_image_s3_key: Optional[str] = None

    class Config:
        from_attributes = True


class ClubMemberOut(BaseModel):
    user: SimpleUser
    role: str
    joined_at: datetime

    class Config:
        from_attributes = True


class ClubOut(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_community: bool = False
    created_at: datetime
    members: list[ClubMemberOut] = []

    class Config:
        from_attributes = True


class InvitePayload(BaseModel):
    invitee_uid: str


class InvitationOut(BaseModel):
    id: uuid.UUID
    club_id: uuid.UUID
    inviter: Optional[SimpleUser]
    invitee: SimpleUser
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


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
        from_attributes = True
