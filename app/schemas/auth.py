from enum import Enum
import uuid
from pydantic import BaseModel, EmailStr
from typing import Optional
from .profile import PersonalInfoOut

class RunnerType(str, Enum):
    grinder = "grinder"
    social_stryder = "social stryder"
    goal_crusher = "goal crusher"
    flow_chaser = "flow chaser"


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    runner_type: RunnerType
    personal_info: Optional[PersonalInfoOut] = None
    

class UserSignIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    uid: uuid.UUID
    full_name: str
    email: EmailStr
    runner_type: RunnerType

    class Config:
        orm_mode = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class MessageResponse(BaseModel):
    message: str
