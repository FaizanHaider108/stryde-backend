from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid

from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models import User
from ...crud import event as event_crud
from ...crud import club as club_crud
from ...schemas.event import EventCreate, EventResponse
from ...schemas.club import InvitePayload

router = APIRouter()


@router.post("/api/v1/clubs/{club_id:uuid}/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(club_id: uuid.UUID, payload: EventCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    ev = event_crud.create_event(db, current_user, club, payload)
    return ev


@router.get("/api/v1/clubs/{club_id:uuid}/events/{event_id:uuid}", response_model=EventResponse)
def get_event(club_id: uuid.UUID, event_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    ev = event_crud.get_event(db, str(event_id))
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")

    # augment response with attendee metadata
    attendee_count = len(ev.attendees) if ev.attendees is not None else 0
    is_current_user_attending = any(str(a.uid) == str(current_user.uid) for a in (ev.attendees or []))
    resp = EventResponse.from_orm(ev)
    resp.attendee_count = attendee_count
    resp.is_current_user_attending = is_current_user_attending
    return resp


@router.post("/api/v1/clubs/{club_id:uuid}/events/{event_id:uuid}/join", response_model=EventResponse)
def join_event(club_id: uuid.UUID, event_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    ev = event_crud.get_event(db, str(event_id))
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    event_crud.join_event(db, current_user, ev)
    # return updated event info
    attendee_count = len(ev.attendees) if ev.attendees is not None else 0
    is_current_user_attending = any(str(a.uid) == str(current_user.uid) for a in (ev.attendees or []))
    resp = EventResponse.from_orm(ev)
    resp.attendee_count = attendee_count
    resp.is_current_user_attending = is_current_user_attending
    return resp


@router.post("/api/v1/clubs/{club_id:uuid}/events/{event_id:uuid}/invite")
def invite_to_event(club_id: uuid.UUID, event_id: uuid.UUID, payload: InvitePayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    ev = event_crud.get_event(db, str(event_id))
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    inv = event_crud.invite_to_event(db, current_user, ev, payload.invitee_uid)
    return {"id": str(inv.id), "status": inv.status.value}


@router.delete("/api/v1/clubs/{club_id:uuid}/events/{event_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(club_id: uuid.UUID, event_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    club = club_crud.get_club(db, str(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="club not found")
    ev = event_crud.get_event(db, str(event_id))
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    event_crud.delete_event(db, current_user, ev)