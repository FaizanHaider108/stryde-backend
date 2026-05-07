from enum import Enum
import uuid
from pydantic import BaseModel, EmailStr
from typing import Optional
from .profile import PersonalInfoCreate

class RunnerType(str, Enum):
    grinder = "grinder"
    social_stryder = "social stryder"
    goal_crusher = "goal crusher"
    flow_chaser = "flow chaser"


class SocialProvider(str, Enum):
    google = "google"
    apple = "apple"


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    runner_type: RunnerType
    personal_info: Optional[PersonalInfoCreate] = None

class UserSignIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    uid: uuid.UUID
    full_name: str
    email: EmailStr
    runner_type: RunnerType

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class SocialLoginRequest(BaseModel):
    provider: SocialProvider
    token: str
    runner_type: Optional[RunnerType] = None
    name_from_frontend: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class MessageResponse(BaseModel):
    message: str
