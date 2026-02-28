from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid
from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models import User
from ...crud import club as club_crud
from ...schemas.club import (
    ClubCreate,
    ClubOut,
    ClubMemberOut,
    InvitePayload,
    InvitationOut,
)

router = APIRouter(prefix="/api/v1/clubs", tags=["clubs"])


@router.post("/", response_model=ClubOut, status_code=status.HTTP_201_CREATED)
def create_club(payload: ClubCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.create_club(db, current_user, payload.name, payload.description, payload.image_url)
    return club


@router.get("/", response_model=list[ClubOut])
def list_clubs(db: Session = Depends(get_db)):
    return club_crud.list_clubs(db)


@router.get("/{club_id:uuid}", response_model=ClubOut)
def get_club(club_id: uuid.UUID, db: Session = Depends(get_db)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    return club

@router.get("/invitations", response_model=list[InvitationOut])
def my_invitations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List invitations addressed to the current user."""
    return club_crud.list_user_invitations(db, current_user)

@router.post("/{club_id:uuid}/invite", response_model=InvitationOut)
def invite(club_id: uuid.UUID, payload: InvitePayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    inv = club_crud.invite_member(db, current_user, club, payload.invitee_uid)
    return inv

@router.post("/invitations/{inv_id:uuid}/accept", response_model=ClubMemberOut)
def accept_invitation(inv_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    inv = club_crud.get_invitation(db, str(inv_id))
    if not inv:
        raise HTTPException(status_code=404, detail="invitation not found")
    member = club_crud.accept_invitation(db, inv, current_user)
    return {"user": member.user, "role": member.role.value if hasattr(member.role, 'value') else member.role, "joined_at": member.joined_at}


@router.post("/invitations/{inv_id:uuid}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_invitation(inv_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    inv = club_crud.get_invitation(db, str(inv_id))
    if not inv:
        raise HTTPException(status_code=404, detail="invitation not found")
    club_crud.decline_invitation(db, inv, current_user)


@router.get("/{club_id:uuid}/members", response_model=list[ClubMemberOut])
def list_members(club_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    # require membership to view
    membership = [m for m in club.members if str(m.user_id) == str(current_user.uid)]
    if not membership:
        raise HTTPException(status_code=403, detail="only members can view members")
    return club.members


@router.post("/{club_id:uuid}/join", response_model=ClubMemberOut)
def join_club(club_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    member = club_crud.join_club(db, current_user, club)
    return {"user": member.user, "role": member.role.value if hasattr(member.role, 'value') else member.role, "joined_at": member.joined_at}


@router.post("/{club_id:uuid}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_club(club_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    club_crud.leave_club(db, current_user, club)


@router.delete("/{club_id:uuid}/members/{member_uid}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(club_id: uuid.UUID, member_uid: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    club_crud.remove_member(db, current_user, club, member_uid)


@router.delete("/{club_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_club(club_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    club_crud.delete_club(db, current_user, club)
