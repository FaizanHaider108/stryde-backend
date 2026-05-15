"""User model and related enums/association tables.

The class is organized for readability: primary key, identity/auth fields,
profile fields, resume fields, timestamps, then relationships.
"""
import enum
import uuid

from sqlalchemy import Table, ForeignKey, Column, Date, DateTime, Enum, Float, JSON, String, func, Uuid
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


class Gender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"
    prefer_not_to_say = "prefer_not_to_say"


# Association table for followers/followings (self-referential)
followers = Table(
    'followers',
    Base.metadata,
    Column('follower_id', Uuid, ForeignKey('users.uid'), primary_key=True),
    Column('followed_id', Uuid, ForeignKey('users.uid'), primary_key=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now()),
)


class User(Base):
    """Application user.

    Sections:
      - Primary key
      - Identity & auth
      - Profile fields
      - Resume fields
      - Timestamps
      - Relationships
    """
    __tablename__ = "users"

    # Primary key (UUID string)
    uid = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Identity & auth
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)
    auth_provider = Column(Enum(AuthProvider), default=AuthProvider.credentials, nullable=False)
    # Stable Apple account identifier from identity token `sub` (Sign in with Apple).
    apple_sub = Column(String(255), unique=True, index=True, nullable=True)

    # Profile fields
    # Image: store storage key only (URL derived externally)
    profile_image_s3_key = Column(String, nullable=True)
    runner_type = Column(Enum(RunnerType), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(Enum(Gender), nullable=True)
    height = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)

    # Resume fields
    location = Column(String, nullable=True)
    bio_title = Column(String, nullable=True)
    started_running_date = Column(Date, nullable=True)

    # Push notifications
    expo_push_token = Column(String, nullable=True)
    notification_prefs = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Social connections (self-referential many-to-many)
    following = relationship(
        "User",
        secondary=followers,
        primaryjoin=uid == followers.c.follower_id,
        secondaryjoin=uid == followers.c.followed_id,
        back_populates="followers",
    )

    # Reciprocal relation: users who follow this user
    followers = relationship(
        "User",
        secondary=followers,
        primaryjoin=uid == followers.c.followed_id,
        secondaryjoin=uid == followers.c.follower_id,
        back_populates="following",
    )

    # Relationships to other models (grouped for readability)
    clubs = relationship("ClubMember", back_populates="user", cascade="all, delete-orphan")
    runs = relationship("Run", back_populates="user", cascade="all, delete-orphan")
    saved_routes = relationship("Route", back_populates="creator", cascade="all, delete-orphan")

    password_reset_tokens = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="user", cascade="all, delete-orphan")
    liked_posts = relationship("Post", secondary="post_likes", back_populates="liked_by")
    liked_comments = relationship("Comment", secondary="comment_likes", back_populates="liked_by")

    club_messages = relationship("ClubMessage", back_populates="sender", cascade="all, delete-orphan")
    message_reads = relationship("ClubMessageRead", back_populates="user", cascade="all, delete-orphan")

    notifications = relationship(
        "Notification",
        foreign_keys="[Notification.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sent_notifications = relationship(
        "Notification",
        foreign_keys="[Notification.actor_id]",
        back_populates="actor",
    )

    # Event relations
    created_events = relationship("Event", foreign_keys="[Event.creator_id]", back_populates="creator", cascade="all, delete-orphan")
    attended_events = relationship("Event", secondary="event_attendees", back_populates="attendees")

    # Experiences, plans and races
    experiences = relationship("RunningExperience", back_populates="user", cascade="all, delete-orphan")
    created_plans = relationship("Plan", back_populates="creator", cascade="all, delete-orphan")
    enrolled_plans = relationship("UserPlan", back_populates="user", cascade="all, delete-orphan")
    saved_races = relationship("Race", secondary="saved_races", back_populates="saved_by")
    registered_races = relationship("Race", secondary="registered_races", back_populates="registered_participants")