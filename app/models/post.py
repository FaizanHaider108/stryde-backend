import uuid
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Uuid, Table, func
from sqlalchemy.orm import relationship
from ..lib.db import Base

# Association Table for Post Likes
post_likes = Table(
    "post_likes",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("post_id", Uuid, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now())
)

# Association Table for Comment Likes
comment_likes = Table(
    "comment_likes",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("comment_id", Uuid, ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now())
)

# The Core Post Model
class Post(Base):
    __tablename__ = "posts"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    
    caption = Column(Text, nullable=True) 
    
    # What is being shared? (Both are nullable)
    # If run_id is populated, the frontend renders the "Shared run" card
    run_id = Column(Uuid, ForeignKey("runs.id", ondelete="CASCADE"), nullable=True)
    # If race_id is populated, the frontend renders the "Shared race" card
    race_id = Column(Uuid, ForeignKey("races.id", ondelete="CASCADE"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # --- Relationships ---
    user = relationship("User", back_populates="posts")
    run = relationship("Run", back_populates="post")
    race = relationship("Race", back_populates="posts")
    
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    images = relationship("PostImage", back_populates="post", cascade="all, delete-orphan")
    
    liked_by = relationship("User", secondary=post_likes, back_populates="liked_posts")

# Post Images Model (For selfies/photos attached to the post)
class PostImage(Base):
    __tablename__ = "post_images"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    post_id = Column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    
    image_url = Column(String, nullable=False)
    
    # Optional: If you want to ensure images render in the exact order the user uploaded them
    display_order = Column(Integer, default=0) 
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    post = relationship("Post", back_populates="images")

# The Comment Model
class Comment(Base):
    __tablename__ = "comments"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    post_id = Column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    
    text = Column(Text, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    post = relationship("Post", back_populates="comments")
    user = relationship("User", back_populates="comments")
    # Relationship for liking a comment
    liked_by = relationship("User", secondary=comment_likes, back_populates="liked_comments")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
