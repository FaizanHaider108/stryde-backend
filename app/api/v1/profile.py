from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...crud.profile import build_profile_response, update_profile
from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models.user import User
from ...schemas.profile import PersonalInfoOut, PersonalInfoUpdate

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
