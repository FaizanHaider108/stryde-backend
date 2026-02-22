import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import relationship
from ..lib.db import Base

class RunningExperience(Base):
    __tablename__ = "running_experiences"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    
    # The Resume Data
    title = Column(String, nullable=False) # e.g., 'Winner 15K Runner at Run Road'
    year = Column(Integer, nullable=False) # e.g., 2022
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship back to the user
    user = relationship("User", back_populates="experiences")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    