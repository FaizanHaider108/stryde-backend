import enum
import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, func, Uuid
from sqlalchemy.orm import relationship

from ..lib.db import Base

# Define the hierarchy of roles within a club
class ClubRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"

# This sits between User and Club to store the specific 'role' and 'joined_at' data
class ClubMember(Base):
    __tablename__ = "club_members"

    club_id = Column(Uuid, ForeignKey("clubs.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True)
    
    # Extra data stored on the relationship itself!
    role = Column(Enum(ClubRole), default=ClubRole.member, nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships back to the parent tables
    club = relationship("Club", back_populates="members")
    user = relationship("User", back_populates="clubs")


# Club Model - Represents a running club/community that users can join
class Club(Base):
    __tablename__ = "clubs"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True) # Text is better than String for long descriptions
    image_url = Column(String, nullable=True) # The icon/banner

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    # This points to the Association Object, NOT directly to the User.
    # cascade="all, delete-orphan" means if the club is deleted, all memberships are erased.
    members = relationship("ClubMember", back_populates="club", cascade="all, delete-orphan")
    
    # A club can host many events.
    events = relationship("Event", back_populates="club", cascade="all, delete-orphan")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    