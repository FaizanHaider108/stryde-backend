import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..models import Notification, NotificationType, User
from ..schemas.notification import NotificationActor, NotificationOut


def _build_actor(user: Optional[User]) -> Optional[NotificationActor]:
    if not user:
        return None
    return NotificationActor(
        uid=user.uid,
        full_name=user.full_name,
        profile_image_s3_key=user.profile_image_s3_key,
    )


def build_notification_out(notification: Notification) -> NotificationOut:
    return NotificationOut(
        id=notification.id,
        type=notification.type.value if hasattr(notification.type, "value") else str(notification.type),
        user_id=notification.user_id,
        actor=_build_actor(notification.actor),
        club_id=notification.club_id,
        event_id=notification.event_id,
        post_id=notification.post_id,
        comment_id=notification.comment_id,
        payload=notification.payload,
        is_read=notification.is_read,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def create_notification(
    db: Session,
    user_id: uuid.UUID,
    notif_type: NotificationType,
    actor_id: Optional[uuid.UUID] = None,
    club_id: Optional[uuid.UUID] = None,
    event_id: Optional[uuid.UUID] = None,
    post_id: Optional[uuid.UUID] = None,
    comment_id: Optional[uuid.UUID] = None,
    payload: Optional[dict] = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        actor_id=actor_id,
        type=notif_type,
        club_id=club_id,
        event_id=event_id,
        post_id=post_id,
        comment_id=comment_id,
        payload=payload,
    )
    try:
        db.add(notification)
        db.commit()
        db.refresh(notification)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create notification") from exc
    return notification


def list_notifications(
    db: Session,
    user: User,
    limit: int = 50,
    before: Optional[datetime] = None,
) -> list[Notification]:
    query = (
        db.query(Notification)
        .options(selectinload(Notification.actor))
        .filter(Notification.user_id == user.uid)
        .order_by(Notification.created_at.desc())
    )
    if before:
        query = query.filter(Notification.created_at < before)

    return query.limit(limit).all()


def get_notification(db: Session, notification_id: uuid.UUID) -> Optional[Notification]:
    return (
        db.query(Notification)
        .options(selectinload(Notification.actor))
        .filter(Notification.id == notification_id)
        .first()
    )


def mark_notification_read(db: Session, notification: Notification, user: User) -> Notification:
    if notification.user_id != user.uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="notification does not belong to user")

    if notification.is_read:
        if not notification.read_at:
            notification.read_at = datetime.now(timezone.utc)
            db.add(notification)
            db.commit()
            db.refresh(notification)
        return notification

    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    try:
        db.add(notification)
        db.commit()
        db.refresh(notification)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not mark notification read") from exc

    return notification


def mark_notifications_read(
    db: Session,
    user: User,
    notification_ids: list[uuid.UUID],
) -> tuple[list[uuid.UUID], datetime]:
    if not notification_ids:
        return [], datetime.now(timezone.utc)

    notifications = (
        db.query(Notification)
        .filter(Notification.id.in_(notification_ids), Notification.user_id == user.uid)
        .all()
    )
    if not notifications:
        return [], datetime.now(timezone.utc)

    read_at = datetime.now(timezone.utc)
    for notif in notifications:
        notif.is_read = True
        notif.read_at = read_at

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not mark notifications read") from exc

    return [n.id for n in notifications], read_at
