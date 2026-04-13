from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
import uuid

from fastapi import HTTPException, status

from ..lib.notifications import notify_user
from ..models import Club, ClubMember, ClubRole, ClubInvitation, InvitationStatus, NotificationType, User


def create_club(db: Session, owner: User, name: str, description: Optional[str] = None, image_url: Optional[str] = None) -> Club:
    """Create a new club and attach the owner as a member with role `owner`.

    Raises HTTPException(status_code=400) on DB errors.
    """
    club = Club(name=name, description=description, image_url=image_url)
    try:
        db.add(club)
        db.flush()
        owner_membership = ClubMember(club_id=club.id, user_id=owner.uid, role=ClubRole.owner)
        db.add(owner_membership)
        db.commit()
        db.refresh(club)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create club") from exc
    return club


def get_club(db: Session, club_id: str) -> Optional[Club]:
    try:
        club_uuid = uuid.UUID(club_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid club id")
    return db.query(Club).filter(Club.id == club_uuid, Club.is_deleted == False).first()


def list_clubs(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Club).filter(Club.is_deleted == False).offset(skip).limit(limit).all()


def invite_member(db: Session, inviter: User, club: Club, invitee_uid: str) -> ClubInvitation:
    """Create a pending invitation for a user to join a club.

    Permission: only club owner can invite. Returns existing pending invitation if present.
    """
    # Reject operations on deleted clubs
    if getattr(club, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    inviter_membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == inviter.uid).first()
    if not inviter_membership or inviter_membership.role != ClubRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only club owner can invite members")

    try:
        invitee_uuid = uuid.UUID(invitee_uid)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invitee id")

    # prevent inviting yourself
    if invitee_uuid == inviter.uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot invite yourself")

    # do not invite existing members
    existing_membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == invitee_uuid).first()
    if existing_membership:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a club member")

    existing = db.query(ClubInvitation).filter(
        ClubInvitation.club_id == club.id,
        ClubInvitation.invitee_id == invitee_uuid,
        ClubInvitation.status == InvitationStatus.pending,
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An invitation is already pending for this user")

    invitation = ClubInvitation(club_id=club.id, inviter_id=inviter.uid, invitee_id=invitee_uuid)
    try:
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create invitation") from exc

    notify_user(
        db,
        user_id=invitee_uuid,
        notif_type=NotificationType.club_invitation,
        actor_id=inviter.uid,
        club_id=club.id,
        payload={"invitation_id": str(invitation.id)},
    )
    return invitation


def get_invitation(db: Session, inv_id: str) -> Optional[ClubInvitation]:
    try:
        inv_uuid = uuid.UUID(inv_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invitation id")
    return db.query(ClubInvitation).filter(ClubInvitation.id == inv_uuid).first()


def list_user_invitations(db: Session, user: User):
    """Return invitations where the user is the invitee."""
    return (
        db.query(ClubInvitation)
        .join(Club, Club.id == ClubInvitation.club_id)
        .filter(ClubInvitation.invitee_id == user.uid, ClubInvitation.status == InvitationStatus.pending, Club.is_deleted == False)
        .order_by(ClubInvitation.created_at.desc())
        .all()
    )


def accept_invitation(db: Session, invitation: ClubInvitation, user: User) -> ClubMember:
    """Accept a pending invitation and create a membership.

    Raises HTTPException for permission/invalid-state errors.
    """
    if invitation.invitee_id != user.uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invitation does not belong to user")
    if invitation.status != InvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is not pending")

    # ensure club still active
    club = db.query(Club).filter(Club.id == invitation.club_id, Club.is_deleted == False).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    existing_membership = db.query(ClubMember).filter(ClubMember.club_id == invitation.club_id, ClubMember.user_id == user.uid).first()
    if existing_membership:
        invitation.status = InvitationStatus.accepted
        db.commit()
        return existing_membership

    member = ClubMember(club_id=invitation.club_id, user_id=user.uid, role=ClubRole.member)
    try:
        db.add(member)
        invitation.status = InvitationStatus.accepted
        db.commit()
        db.refresh(member)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not accept invitation") from exc
    return member


def decline_invitation(db: Session, invitation: ClubInvitation, user: User) -> None:
    if invitation.invitee_id != user.uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invitation does not belong to user")
    if invitation.status != InvitationStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is not pending")
    # ensure club still active
    club = db.query(Club).filter(Club.id == invitation.club_id, Club.is_deleted == False).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    invitation.status = InvitationStatus.declined
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not decline invitation")


def join_club(db: Session, user: User, club: Club) -> ClubMember:
    # reject operations on deleted clubs
    if getattr(club, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    existing = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == user.uid).first()
    if existing:
        return existing
    member = ClubMember(club_id=club.id, user_id=user.uid, role=ClubRole.member)
    try:
        db.add(member)
        db.commit()
        db.refresh(member)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not join club") from exc
    return member


def leave_club(db: Session, user: User, club: Club) -> None:
    # reject operations on deleted clubs
    if getattr(club, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == user.uid).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    if membership.role == ClubRole.owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner cannot leave the club")
    try:
        db.delete(membership)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not leave club")


def remove_member(db: Session, owner: User, club: Club, member_uid: str) -> None:
    # reject operations on deleted clubs
    if getattr(club, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")

    owner_membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == owner.uid).first()
    if not owner_membership or owner_membership.role != ClubRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can remove members")
    try:
        member_uuid = uuid.UUID(member_uid)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid member id")
    if owner.uid == member_uuid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner cannot remove themself")
    membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == member_uuid).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    try:
        db.delete(membership)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not remove member")


def delete_club(db: Session, owner: User, club: Club) -> None:
    owner_membership = db.query(ClubMember).filter(ClubMember.club_id == club.id, ClubMember.user_id == owner.uid).first()
    if not owner_membership or owner_membership.role != ClubRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can delete club")
    if getattr(club, "is_deleted", False):
        # already deleted
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="club not found")
    try:
        club.is_deleted = True
        db.add(club)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not delete club")
