import enum
import uuid
from sqlalchemy import Column, DateTime, String, Enum, func
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
