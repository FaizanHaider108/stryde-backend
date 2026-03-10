import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PostCreate(BaseModel):
    caption: Optional[str] = None
    run_id: Optional[uuid.UUID] = None
    race_id: Optional[uuid.UUID] = None
    images: list[str] = Field(default_factory=list)


class PostUser(BaseModel):
    uid: str
    full_name: str
    profile_image_s3_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RunSummary(BaseModel):
    id: uuid.UUID
    route_id: Optional[uuid.UUID] = None
    race_id: Optional[uuid.UUID] = None
    plan_workout_id: Optional[uuid.UUID] = None
    distance_km: float
    duration_seconds: int
    average_pace: Optional[float] = None
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    map_data: str
    start_time: datetime
    end_time: datetime

    model_config = ConfigDict(from_attributes=True)


class RaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    start_time: datetime
    location_text: str
    distance_km: float
    distance_label: str
    average_rating: Optional[float] = 0.0
    review_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class PostResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    caption: Optional[str] = None
    created_at: Optional[datetime] = None
    user: Optional[PostUser] = None
    images: list[str] = Field(default_factory=list)
    run: Optional[RunSummary] = None
    race: Optional[RaceSummary] = None
    likes_count: int = 0
    comments_count: int = 0
    is_liked_by_current_user: bool = False

    model_config = ConfigDict(from_attributes=True)
