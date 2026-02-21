from enum import Enum
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    prefer_not_to_say = "prefer_not_to_say"


class PersonalInfoCreate(BaseModel):
    profile_image: Optional[str] = None
    full_name: str
    email: EmailStr
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    height: Optional[float] = None
    weight: Optional[float] = None


class PersonalInfoUpdate(BaseModel):
    profile_image: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    height: Optional[float] = None
    weight: Optional[float] = None


class PersonalInfoOut(BaseModel):
    uid: str
    user_uid: str
    profile_image: Optional[str]
    full_name: str
    email: EmailStr
    date_of_birth: Optional[date]
    gender: Optional[Gender]
    height: Optional[float]
    weight: Optional[float]

    class Config:
        orm_mode = True
