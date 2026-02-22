"""Running experience entries attached to a `User` (e.g. awards, achievements)."""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import relationship
from ..lib.db import Base


class RunningExperience(Base):
    """A single experience/credential for a runner.

    Grouping: PK, foreign key, attributes, timestamps, relationships.
    """
    __tablename__ = "running_experiences"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Foreign key to owning user
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)

    # Resume data
    title = Column(String, nullable=False)
    year = Column(Integer, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="experiences")
