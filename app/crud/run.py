from typing import Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import PlanWorkout, Post, Race, Route, Run, User
from ..schemas.run import RunCreate


def _parse_run_id(run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(run_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run id") from exc


def get_run(db: Session, run_id: str) -> Optional[Run]:
    run_uuid = _parse_run_id(run_id)
    return db.query(Run).filter(Run.id == run_uuid).first()


def get_user_runs(db: Session, user_id: uuid.UUID) -> list[Run]:
    return (
        db.query(Run)
        .filter(Run.user_id == user_id)
        .order_by(Run.start_time.desc())
        .all()
    )


def get_visible_run(db: Session, run_id: uuid.UUID, current_user_id: Optional[uuid.UUID] = None) -> Optional[Run]:
    query = db.query(Run).filter(Run.id == run_id)
    is_shared = exists().where(Post.run_id == Run.id)

    if current_user_id:
        return query.filter((Run.user_id == current_user_id) | is_shared).first()

    return query.filter(is_shared).first()


def _ensure_route_exists(db: Session, route_id: uuid.UUID) -> None:
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="route not found")


def _ensure_race_exists(db: Session, race_id: uuid.UUID) -> None:
    race = db.query(Race).filter(Race.id == race_id).first()
    if not race:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="race not found")


def _ensure_plan_workout_exists(db: Session, plan_workout_id: uuid.UUID) -> None:
    plan_workout = db.query(PlanWorkout).filter(PlanWorkout.id == plan_workout_id).first()
    if not plan_workout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan workout not found")


def create_run(db: Session, user: User, payload: RunCreate) -> Run:
    if payload.route_id:
        _ensure_route_exists(db, payload.route_id)
    if payload.race_id:
        _ensure_race_exists(db, payload.race_id)
    if payload.plan_workout_id:
        _ensure_plan_workout_exists(db, payload.plan_workout_id)

    average_pace = payload.average_pace
    if average_pace is None and payload.distance_km > 0:
        average_pace = payload.duration_seconds / payload.distance_km

    run = Run(
        user_id=user.uid,
        route_id=payload.route_id,
        race_id=payload.race_id,
        plan_workout_id=payload.plan_workout_id,
        distance_km=payload.distance_km,
        duration_seconds=payload.duration_seconds,
        average_pace=average_pace,
        start_lat=payload.start_lat,
        start_lng=payload.start_lng,
        end_lat=payload.end_lat,
        end_lng=payload.end_lng,
        map_data=payload.map_data,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )

    try:
        db.add(run)
        db.commit()
        db.refresh(run)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create run") from exc

    return run
