"""Social feed models: Post, PostImage, Comment and like association tables."""
import uuid
from sqlalchemy import Column, String, Text, Integer, DateTime, Float, ForeignKey, Uuid, Table, func
from sqlalchemy.orm import relationship
from ..lib.db import Base


# Association Tables
post_likes = Table(
    "post_likes",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("post_id", Uuid, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

comment_likes = Table(
    "comment_likes",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True),
    Column("comment_id", Uuid, ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


class Post(Base):
    """A social post created by a user. May reference a `Run` or `Race`."""
    __tablename__ = "posts"

    # Primary key
    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)

    # Foreign key(s)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    run_id = Column(Uuid, ForeignKey("runs.id", ondelete="CASCADE"), nullable=True)
    race_id = Column(Uuid, ForeignKey("races.id", ondelete="CASCADE"), nullable=True)
    route_id = Column(Uuid, ForeignKey("routes.id", ondelete="SET NULL"), nullable=True)

    # Route snapshot for shared route posts. This keeps post data stable even if
    # the original saved route is later deleted by the user.
    route_snapshot_id = Column(Uuid, nullable=True)
    route_snapshot_name = Column(String, nullable=True)
    route_snapshot_distance_km = Column(Float, nullable=True)
    route_snapshot_elevation_gain_m = Column(Float, nullable=True)
    route_snapshot_start_lat = Column(Float, nullable=True)
    route_snapshot_start_lng = Column(Float, nullable=True)
    route_snapshot_end_lat = Column(Float, nullable=True)
    route_snapshot_end_lng = Column(Float, nullable=True)
    route_snapshot_map_data = Column(Text, nullable=True)

    # Content
    caption = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="posts")
    run = relationship("Run", back_populates="post")
    race = relationship("Race", back_populates="posts")
    route = relationship("Route", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    images = relationship("PostImage", back_populates="post", cascade="all, delete-orphan")
    liked_by = relationship("User", secondary=post_likes, back_populates="liked_posts")


class PostImage(Base):
    """Images attached to a `Post`."""
    __tablename__ = "post_images"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    post_id = Column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String, nullable=False)
    display_order = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    post = relationship("Post", back_populates="images")


class Comment(Base):
    """Comment on a `Post`. Can be liked by users."""
    __tablename__ = "comments"

    id = Column(Uuid, primary_key=True, index=True, default=uuid.uuid4)
    post_id = Column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Uuid, ForeignKey("users.uid", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    post = relationship("Post", back_populates="comments")
    user = relationship("User", back_populates="comments")
    liked_by = relationship("User", secondary=comment_likes, back_populates="liked_comments")
    post = relationship("Post", back_populates="comments")
