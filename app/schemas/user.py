from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class ExperienceCreate(BaseModel):
    title: str
    year: int


class UserUpdate(BaseModel):
    location: Optional[str] = None
    bio_title: Optional[str] = None
    profile_image_s3_key: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    runner_type: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None


class UserResponse(BaseModel):
    uid: str
    full_name: str
    profile_image_s3_key: Optional[str] = None
    runner_type: Optional[str] = None
    bio_title: Optional[str] = None

    class Config:
        orm_mode = True


class UserStatsResponse(BaseModel):
    uid: str
    record_5k: Optional[str] = None
    record_10k: Optional[str] = None
    record_half_marathon: Optional[str] = None
    record_marathon: Optional[str] = None
    longest_run_distance: Optional[float] = None
    fastest_mile_pace: Optional[str] = None
    total_distance: Optional[float] = None
    total_runs: Optional[int] = None
    total_time: Optional[int] = None
    average_pace: Optional[str] = None

    class Config:
        orm_mode = True


class RunningExperience(BaseModel):
    title: str
    year: int


class UserResumeResponse(BaseModel):
    uid: str
    email: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    location: Optional[str] = None
    total_marathons: Optional[int] = None
    total_half_marathons: Optional[int] = None
    years_running: Optional[int] = None
    longest_run_distance: Optional[float] = None
    experiences: Optional[List[RunningExperience]] = []

    class Config:
        orm_mode = True