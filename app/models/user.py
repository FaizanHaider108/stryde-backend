import enum
import uuid

from sqlalchemy import Column, Date, DateTime, Enum, Float, ForeignKey, String, func
from sqlalchemy.orm import relationship

from ..lib.db import Base


class RunnerType(str, enum.Enum):
    grinder = "grinder"
    social_stryder = "social stryder"
    goal_crusher = "goal crusher"
    flow_chaser = "flow chaser"

class AuthProvider(str, enum.Enum):
    credentials = "credentials"
    google = "google"
    apple = "apple"


class User(Base):
    __tablename__ = "users"

    uid = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    auth_provider = Column(Enum(AuthProvider), default=AuthProvider.credentials, nullable=False)
    runner_type = Column(Enum(RunnerType), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Gender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"
    prefer_not_to_say = "prefer_not_to_say"


class PersonalInfo(Base):
    __tablename__ = "personal_infos"

    uid = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_uid = Column(String(36), ForeignKey("users.uid"), unique=True, nullable=False)
    profile_image = Column(String, nullable=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(Enum(Gender), nullable=True)
    height = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # relationship to User
    user = relationship("User", back_populates="personal_info")

# attach relationship on User
User.personal_info = relationship("PersonalInfo", back_populates="user", uselist=False)
