from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import uuid
from ...crud.profile import build_profile_response, update_profile
from ...crud.profile import follow_user, unfollow_user, build_profile_with_social
from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models.user import User
from ...schemas.profile import PersonalInfoOut, PersonalInfoUpdate
from ...schemas.profile import ProfileWithSocialOut
from fastapi import HTTPException
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.get("/me", response_model=PersonalInfoOut)
def get_my_profile(current_user: User = Depends(get_current_user)):
    return build_profile_response(current_user)


@router.patch("/me", response_model=PersonalInfoOut)
def update_my_profile(
    update_in: PersonalInfoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = update_profile(db, current_user, update_in)
    return build_profile_response(updated)



@router.get("/{uid:uuid}", response_model=ProfileWithSocialOut)
def get_user_profile(uid: uuid.UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return build_profile_with_social(user)


@router.post("/{uid:uuid}/follow", response_model=ProfileWithSocialOut)
def follow(uid: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        target = follow_user(db, current_user, str(uid))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return build_profile_with_social(target)


@router.post("/{uid:uuid}/unfollow", response_model=ProfileWithSocialOut)
def unfollow(uid: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        target = unfollow_user(db, current_user, str(uid))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return build_profile_with_social(target)
