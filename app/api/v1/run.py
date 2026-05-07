from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid

from ...crud import run as run_crud
from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models import User
from ...schemas.run import RunCreate, RunResponse

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.get("/me", response_model=list[RunResponse], include_in_schema=False)
@router.get("/me/", response_model=list[RunResponse])
def list_my_runs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return run_crud.get_user_runs(db, current_user.uid)


@router.get("/user/{uid:uuid}", response_model=list[RunResponse])
def list_user_runs(uid: uuid.UUID, db: Session = Depends(get_db)):
    return run_crud.get_user_runs(db, uid)


@router.get("/{run_id:uuid}", response_model=RunResponse)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    run = run_crud.get_visible_run(db, run_id, current_user.uid)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found or access denied")
    return run


@router.post("/", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def create_run(payload: RunCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return run_crud.create_run(db, current_user, payload)
