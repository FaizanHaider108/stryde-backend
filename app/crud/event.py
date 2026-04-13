from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
import uuid

from fastapi import HTTPException, status

from ..lib.notifications import notify_user
from ..models import Event, EventInvitation, Club, ClubMember, ClubRole, User, InvitationStatus, NotificationType, Route
from ..schemas.event import EventCreate


def create_event(db: Session, creator: User, club: Club, payload: EventCreate) -> Event:
    """Create a new event. Only club owner can create events."""
    # reject operations on deleted clubs
    if getattr(club, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    owner_membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == creator.uid).first()
    if not owner_membership or owner_membership.role != ClubRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only club owner can create events")

    if not payload.route_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="route_id is required")

    route = db.query(Route).filter(Route.id == payload.route_id).first()
    if not route:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="route not found")
    if route.creator_id != creator.uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Route does not belong to user")
    
    event = Event(
        club_id=club.id,
        creator_id=creator.uid,
        route_id=payload.route_id,
        name=payload.name,
        description=payload.description,
        start_time=payload.start_time,
        pace_intensity=payload.pace_intensity,
    )
    try:
        db.add(event)
        db.commit()
        db.refresh(event)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create event") from exc
    return event


def get_event(db: Session, event_id: str) -> Optional[Event]:
    try:
        ev_uuid = uuid.UUID(event_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event id")
    return db.query(Event).filter(Event.id == ev_uuid, Event.is_deleted == False).first()


def get_event_invitation(db: Session, inv_id: str) -> Optional[EventInvitation]:
    try:
        inv_uuid = uuid.UUID(inv_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invitation id")
    return db.query(EventInvitation).filter(EventInvitation.id == inv_uuid).first()


def list_pending_event_invitations(db: Session, user: User):
    return (
        db.query(EventInvitation)
        .join(Event, Event.id == EventInvitation.event_id)
        .join(Club, Club.id == Event.club_id)
        .filter(
            EventInvitation.invitee_id == user.uid,
            EventInvitation.status == InvitationStatus.pending,
            Event.is_deleted == False,
            Club.is_deleted == False,
        )
        .order_by(EventInvitation.created_at.desc())
        .all()
    )


def list_events_for_club(db: Session, club: Club):
    if getattr(club, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")
    return db.query(Event).filter(Event.club_id == club.id, Event.is_deleted == False).order_by(Event.start_time).all()


def join_event(db: Session, user: User, event: Event) -> None:
    # ensure event and club are active
    if getattr(event, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    club = db.query(Club).filter(Club.id == event.club_id, Club.is_deleted == False).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == user.uid).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only club members can join events")

    # Prevent duplicate attendance
    if user in event.attendees:
        return

    try:
        event.attendees.append(user)
        db.add(event)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not join event")


def invite_to_event(db: Session, inviter: User, event: Event, invitee_uid: str) -> EventInvitation:
    # only club owner may invite to events
    club = db.query(Club).filter(Club.id == event.club_id, Club.is_deleted == False).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")
    if getattr(event, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    inviter_membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == inviter.uid).first()
    if not inviter_membership or inviter_membership.role != ClubRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only club owner can invite members to events")

    try:
        invitee_uuid = uuid.UUID(invitee_uid)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invitee id")

    # only club members can be invited
    invitee_membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == invitee_uuid).first()
    if not invitee_membership:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitee must be a club member")

    already_attending = any(str(a.uid) == str(invitee_uuid) for a in (event.attendees or []))
    if already_attending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already attending this event")

    # ensure no pending invitation exists
    existing = db.query(EventInvitation).filter(
        EventInvitation.event_id == event.id,
        EventInvitation.invitee_id == invitee_uuid,
        EventInvitation.status == InvitationStatus.pending,
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An invitation is already pending for this user")

    invitation = EventInvitation(event_id=event.id, inviter_id=inviter.uid, invitee_id=invitee_uuid)
    try:
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create event invitation")

    notify_user(
        db,
        user_id=invitee_uuid,
        notif_type=NotificationType.event_invitation,
        actor_id=inviter.uid,
        club_id=club.id,
        event_id=event.id,
        payload={"invitation_id": str(invitation.id)},
    )
    return invitation


def accept_event_invitation(db: Session, invitation: EventInvitation, user: User) -> Event:
    if invitation.invitee_id != user.uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invitation does not belong to user")
    if invitation.status != InvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is not pending")

    event = db.query(Event).filter(Event.id == invitation.event_id, Event.is_deleted == False).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    club = db.query(Club).filter(Club.id == event.club_id, Club.is_deleted == False).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == user.uid).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only club members can join events")

    if user not in (event.attendees or []):
        event.attendees.append(user)

    invitation.status = InvitationStatus.accepted
    try:
        db.add(invitation)
        db.add(event)
        db.commit()
        db.refresh(event)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not accept event invitation")
    return event


def decline_event_invitation(db: Session, invitation: EventInvitation, user: User) -> None:
    if invitation.invitee_id != user.uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invitation does not belong to user")
    if invitation.status != InvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is not pending")

    event = db.query(Event).filter(Event.id == invitation.event_id, Event.is_deleted == False).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    club = db.query(Club).filter(Club.id == event.club_id, Club.is_deleted == False).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    invitation.status = InvitationStatus.declined
    try:
        db.add(invitation)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not decline event invitation")


def leave_event(db: Session, user: User, event: Event) -> None:
    if getattr(event, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    club = db.query(Club).filter(Club.id == event.club_id, Club.is_deleted == False).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    if user not in (event.attendees or []):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not attending this event")

    try:
        event.attendees.remove(user)
        db.add(event)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not leave event")


def delete_event(db: Session, owner: User, event: Event) -> None:
    # only owner can delete
    club = db.query(Club).filter(Club.id == event.club_id).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")
    owner_membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == owner.uid).first()
    if not owner_membership or owner_membership.role != ClubRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can delete event")
    if getattr(event, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    try:
        event.is_deleted = True
        db.add(event)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not delete event")
