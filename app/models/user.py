import enum
import uuid

from sqlalchemy import Table, ForeignKey, Column, Date, DateTime, Enum, Float, String, func, Uuid
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

# Association table for followers/followingss
followers = Table(
    'followers',
    Base.metadata,
    Column('follower_id', Uuid, ForeignKey('users.uid'), primary_key=True),
    Column('followed_id', Uuid, ForeignKey('users.uid'), primary_key=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)

class User(Base):
    __tablename__ = "users"

    # Native Uuid
    uid = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    
    # Core Identity & Auth
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)
    auth_provider = Column(Enum(AuthProvider), default=AuthProvider.credentials, nullable=False)
    
    # Social & Physical Profile
    profile_image = Column(String, nullable=True)
    runner_type = Column(Enum(RunnerType), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(Enum(Gender), nullable=True)
    height = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)

    # Social Connections
    following = relationship(
        "User", 
        secondary=followers,
        primaryjoin=uid==followers.c.follower_id,
        secondaryjoin=uid==followers.c.followed_id,
        backref="followers" # This automatically creates user.followers
    )

    # Links the user to all the clubs they are a part of
    clubs = relationship("ClubMember", back_populates="user", cascade="all, delete-orphan")
    # Links to all the physical activities they have completed
    runs = relationship("Run", back_populates="user", cascade="all, delete-orphan")
    # Links to all the routes they have saved
    saved_routes = relationship("Route", back_populates="creator", cascade="all, delete-orphan")
    # Links related to posts and comments in the social feed
    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="user", cascade="all, delete-orphan")
    liked_posts = relationship("Post", secondary="post_likes", back_populates="liked_by")
    liked_comments = relationship("Comment", secondary="comment_likes", back_populates="liked_by")
    # Event relations
    created_events = relationship("Event", foreign_keys="[Event.creator_id]", back_populates="creator", cascade="all, delete-orphan")
    attended_events = relationship("Event", secondary="event_attendees", back_populates="attendees")

    # Resume fields
    location = Column(String, nullable=True) # e.g., "USA" or "Chicago, IL"
    bio_title = Column(String, nullable=True) # e.g., "Professional Runner"
    
    # Store the date they started running, NOT an integer.
    started_running_date = Column(Date, nullable=True) 

    # Relationship to the Experience model
    experiences = relationship("RunningExperience", back_populates="user", cascade="all, delete-orphan")

    # Links to Plans
    created_plans = relationship("Plan", back_populates="creator", cascade="all, delete-orphan")
    enrolled_plans = relationship("UserPlan", back_populates="user", cascade="all, delete-orphan")

    # Links to Races
    saved_races = relationship("Race", secondary="saved_races", back_populates="saved_by")
    registered_races = relationship("Race", secondary="registered_races", back_populates="registered_participants")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())