from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel

from ..models.user import RunnerType


class ClubCreate(BaseModel):
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    runner_type: Optional[RunnerType] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class ClubUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    runner_type: Optional[RunnerType] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


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
    runner_type: Optional[RunnerType] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Populated only when the search was performed with a lat/lng (distance from user).
    distance_km: Optional[float] = None
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


class ClubResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    member_count: Optional[int] = 0
    current_user_role: Optional[str] = None

    class Config:
        from_attributes = True
