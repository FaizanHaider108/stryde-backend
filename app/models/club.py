"""Club models: Club and ClubMember (association object).

Grouped attributes: primary keys, columns, timestamps, then relationships.
"""
import enum
import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, func, Uuid, Boolean
from sqlalchemy.orm import relationship

from ..lib.db import Base


class ClubRole(str, enum.Enum):
    """Role of a user within a club."""
    owner = "owner"
    admin = "admin"
    member = "member"


class ClubMember(Base):
    """Association object between `Club` and `User` storing membership metadata.

    Columns are grouped as: foreign keys, metadata, timestamps, relationships.
    """
    __tablename__ = "club_members"

    # Foreign keys (composite primary key)
    club_id = Column(Uuid, ForeignKey("clubs.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True)

    # Membership metadata
    role = Column(Enum(ClubRole), default=ClubRole.member, nullable=False)

    # Timestamps
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    club = relationship("Club", back_populates="members")
    user = relationship("User", back_populates="clubs")


class Club(Base):
    """A running club/community that users can join.

    Layout: primary key, descriptive columns, timestamps, relationships.
    """
    __tablename__ = "clubs"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Descriptive fields
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # Soft-delete flag
    is_deleted = Column(Boolean, nullable=False, server_default="false")

    # Relationships
    # Use an association object for members so we can store role/joined_at
    # Relationships
    members = relationship(
        "ClubMember", 
        back_populates="club", 
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    
    events = relationship(
        "Event", 
        back_populates="club", 
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    messages = relationship(
        "ClubMessage",
        back_populates="club",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Adding the invitations relationship explicitly
    invitations = relationship(
        "ClubInvitation",
        back_populates="club",
        cascade="all, delete-orphan",
        passive_deletes=True
    )