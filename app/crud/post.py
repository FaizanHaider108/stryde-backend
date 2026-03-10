import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..models import Comment, Post, PostImage, Race, Run, User
from ..schemas.comment import CommentCreate, CommentResponse
from ..schemas.post import PostCreate, PostResponse


def _parse_post_id(post_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(post_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid post id") from exc


def _parse_comment_id(comment_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(comment_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid comment id") from exc


def _build_user_summary(user: User) -> dict:
    return {
        "uid": str(user.uid),
        "full_name": user.full_name,
        "profile_image_s3_key": user.profile_image_s3_key,
    }


def _build_run_summary(run: Optional[Run]) -> Optional[dict]:
    if not run:
        return None
    return {
        "id": run.id,
        "route_id": run.route_id,
        "race_id": run.race_id,
        "plan_workout_id": run.plan_workout_id,
        "distance_km": run.distance_km,
        "duration_seconds": run.duration_seconds,
        "average_pace": run.average_pace,
        "start_lat": run.start_lat,
        "start_lng": run.start_lng,
        "end_lat": run.end_lat,
        "end_lng": run.end_lng,
        "map_data": run.map_data,
        "start_time": run.start_time,
        "end_time": run.end_time,
    }


def _build_race_summary(race: Optional[Race]) -> Optional[dict]:
    if not race:
        return None
    return {
        "id": race.id,
        "name": race.name,
        "start_time": race.start_time,
        "location_text": race.location_text,
        "distance_km": race.distance_km,
        "distance_label": race.distance_label,
        "average_rating": race.average_rating,
        "review_count": race.review_count,
    }


def build_post_response(post: Post, current_user_id: Optional[uuid.UUID] = None) -> PostResponse:
    images = sorted(post.images or [], key=lambda image: image.display_order)
    likes = post.liked_by or []
    comments = post.comments or []
    is_liked = False
    if current_user_id:
        is_liked = any(str(u.uid) == str(current_user_id) for u in likes)

    return PostResponse(
        id=post.id,
        user_id=post.user_id,
        caption=post.caption,
        created_at=post.created_at,
        user=_build_user_summary(post.user),
        images=[image.image_url for image in images],
        run=_build_run_summary(post.run),
        race=_build_race_summary(post.race),
        likes_count=len(likes),
        comments_count=len(comments),
        is_liked_by_current_user=is_liked,
    )


def build_comment_response(comment: Comment, current_user_id: Optional[uuid.UUID] = None) -> CommentResponse:
    likes = comment.liked_by or []
    is_liked = False
    if current_user_id:
        is_liked = any(str(u.uid) == str(current_user_id) for u in likes)

    return CommentResponse(
        id=comment.id,
        text=comment.text,
        created_at=comment.created_at,
        user=_build_user_summary(comment.user),
        likes_count=len(likes),
        is_liked_by_current_user=is_liked,
    )


def get_post(db: Session, post_id: str) -> Optional[Post]:
    post_uuid = _parse_post_id(post_id)
    return db.query(Post).filter(Post.id == post_uuid).first()


def get_post_for_profile(db: Session, post_id: str, profile_uid: uuid.UUID) -> Optional[Post]:
    post_uuid = _parse_post_id(post_id)
    return db.query(Post).filter(Post.id == post_uuid, Post.user_id == profile_uid).first()


def list_user_posts(db: Session, user_id: uuid.UUID, current_user_id: Optional[uuid.UUID] = None) -> list[PostResponse]:
    posts = (
        db.query(Post)
        .options(
            selectinload(Post.user),
            selectinload(Post.images),
            selectinload(Post.comments),
            selectinload(Post.liked_by),
            selectinload(Post.run),
            selectinload(Post.race),
        )
        .filter(Post.user_id == user_id)
        .order_by(Post.created_at.desc())
        .all()
    )

    return [build_post_response(post, current_user_id) for post in posts]


def _ensure_run_shareable(db: Session, user: User, run_id: uuid.UUID) -> None:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    if run.user_id != user.uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Run does not belong to user")

    existing = db.query(Post).filter(Post.run_id == run_id).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run already shared")


def _ensure_race_shareable(db: Session, race_id: uuid.UUID) -> None:
    race = db.query(Race).filter(Race.id == race_id).first()
    if not race:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="race not found")


def create_post(db: Session, user: User, payload: PostCreate) -> Post:
    if bool(payload.run_id) == bool(payload.race_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of run_id or race_id must be provided",
        )

    if payload.run_id:
        _ensure_run_shareable(db, user, payload.run_id)
    if payload.race_id:
        _ensure_race_shareable(db, payload.race_id)

    post = Post(
        user_id=user.uid,
        run_id=payload.run_id,
        race_id=payload.race_id,
        caption=payload.caption,
    )

    try:
        db.add(post)
        db.flush()

        for index, image_url in enumerate(payload.images or []):
            db.add(PostImage(post_id=post.id, image_url=image_url, display_order=index))

        db.commit()
        db.refresh(post)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create post") from exc

    return post


def like_post(db: Session, user: User, post: Post) -> None:
    if user in (post.liked_by or []):
        return

    post.liked_by.append(user)
    try:
        db.add(post)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not like post") from exc


def list_post_comments(db: Session, post: Post, current_user_id: Optional[uuid.UUID] = None) -> list[CommentResponse]:
    comments = (
        db.query(Comment)
        .options(selectinload(Comment.user), selectinload(Comment.liked_by))
        .filter(Comment.post_id == post.id)
        .order_by(Comment.created_at.asc())
        .all()
    )

    return [build_comment_response(comment, current_user_id) for comment in comments]


def create_comment(db: Session, user: User, post: Post, payload: CommentCreate) -> Comment:
    comment = Comment(post_id=post.id, user_id=user.uid, text=payload.text)
    try:
        db.add(comment)
        db.commit()
        db.refresh(comment)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not add comment") from exc
    return comment


def get_comment_for_post(db: Session, post: Post, comment_id: str) -> Optional[Comment]:
    comment_uuid = _parse_comment_id(comment_id)
    return db.query(Comment).filter(Comment.id == comment_uuid, Comment.post_id == post.id).first()


def like_comment(db: Session, user: User, comment: Comment) -> None:
    if user in (comment.liked_by or []):
        return

    comment.liked_by.append(user)
    try:
        db.add(comment)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not like comment") from exc


def unlike_comment(db: Session, user: User, comment: Comment) -> None:
    if user not in (comment.liked_by or []):
        return

    comment.liked_by.remove(user)
    try:
        db.add(comment)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not unlike comment") from exc
