import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..models import Club, ClubMember, ClubMessage, ClubMessageRead, User
from ..schemas.chat import ClubMessageOut, MessageReadOut, MessageSender


def _get_club(db: Session, club_id: uuid.UUID) -> Club:
    club = db.query(Club).filter(Club.id == club_id, Club.is_deleted == False).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")
    return club


def _ensure_member(db: Session, club: Club, user: User) -> None:
    membership = (
        db.query(ClubMember)
        .filter(ClubMember.club_id == club.id, ClubMember.user_id == user.uid)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only club members can chat")


def build_message_out(message: ClubMessage, current_user_id: Optional[uuid.UUID] = None) -> ClubMessageOut:
    reads = message.reads or []
    is_read = False
    if current_user_id:
        is_read = any(str(r.user_id) == str(current_user_id) for r in reads)

    sender = None
    if message.sender:
        sender = MessageSender(
            uid=message.sender.uid,
            full_name=message.sender.full_name,
            profile_image_s3_key=message.sender.profile_image_s3_key,
        )

    return ClubMessageOut(
        id=message.id,
        club_id=message.club_id,
        sender_id=message.sender_id,
        sender=sender,
        body=message.body,
        created_at=message.created_at,
        reads=[MessageReadOut(user_id=r.user_id, read_at=r.read_at) for r in reads],
        is_read_by_current_user=is_read,
    )


def create_message(db: Session, sender: User, club_id: uuid.UUID, body: str) -> ClubMessage:
    club = _get_club(db, club_id)
    _ensure_member(db, club, sender)

    message = ClubMessage(club_id=club.id, sender_id=sender.uid, body=body)
    now = datetime.now(timezone.utc)
    try:
        db.add(message)
        db.flush()
        db.add(ClubMessageRead(message_id=message.id, user_id=sender.uid, read_at=now))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not send message") from exc

    return (
        db.query(ClubMessage)
        .options(selectinload(ClubMessage.sender), selectinload(ClubMessage.reads))
        .filter(ClubMessage.id == message.id)
        .first()
    )


def list_messages(
    db: Session,
    club_id: uuid.UUID,
    user: User,
    limit: int = 50,
    before: Optional[datetime] = None,
) -> list[ClubMessageOut]:
    club = _get_club(db, club_id)
    _ensure_member(db, club, user)

    query = (
        db.query(ClubMessage)
        .options(selectinload(ClubMessage.sender), selectinload(ClubMessage.reads))
        .filter(ClubMessage.club_id == club.id)
    )
    if before:
        query = query.filter(ClubMessage.created_at < before)

    messages = query.order_by(ClubMessage.created_at.desc()).limit(limit).all()
    messages.reverse()
    return [build_message_out(message, user.uid) for message in messages]


def mark_messages_read(
    db: Session,
    club_id: uuid.UUID,
    user: User,
    message_ids: Optional[list[uuid.UUID]] = None,
    up_to: Optional[datetime] = None,
) -> tuple[list[uuid.UUID], datetime]:
    club = _get_club(db, club_id)
    _ensure_member(db, club, user)

    if not message_ids and not up_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message_ids or up_to is required")

    query = db.query(ClubMessage.id).filter(ClubMessage.club_id == club.id)
    if message_ids:
        query = query.filter(ClubMessage.id.in_(message_ids))
    if up_to:
        query = query.filter(ClubMessage.created_at <= up_to)

    target_ids = [row[0] for row in query.all()]
    if not target_ids:
        return [], datetime.now(timezone.utc)

    existing = (
        db.query(ClubMessageRead.message_id)
        .filter(ClubMessageRead.user_id == user.uid, ClubMessageRead.message_id.in_(target_ids))
        .all()
    )
    existing_ids = {row[0] for row in existing}
    new_ids = [mid for mid in target_ids if mid not in existing_ids]

    if not new_ids:
        return [], datetime.now(timezone.utc)

    read_at = datetime.now(timezone.utc)
    try:
        for mid in new_ids:
            db.add(ClubMessageRead(message_id=mid, user_id=user.uid, read_at=read_at))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not mark messages read") from exc

    return new_ids, read_at
