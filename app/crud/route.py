from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
import uuid
from sqlalchemy import exists

from fastapi import HTTPException, status

from ..models import Route, Event, User
from ..schemas.route import RouteCreate
from ..models.route import EnvironmentEnum, TerrainEnum, ElevationProfileEnum


def _parse_route_id(route_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(route_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid route id") from exc

def get_user_routes(db: Session, user_id: uuid.UUID):
    """Fetch all routes created by a specific user."""
    return db.query(Route).filter(Route.creator_id == user_id).all()

def get_visible_route(db: Session, route_id: uuid.UUID, current_user_id: Optional[uuid.UUID] = None):
    """
    Fetch a route only if:
    1. The user is the creator OR
    2. The route is attached to at least one event (public)
    """
    query = db.query(Route).filter(Route.id == route_id)
    
    # Check if a non-deleted event exists for this route
    route_is_in_event = exists().where(Event.route_id == Route.id, Event.is_deleted == False)
    
    if current_user_id:
        # Creator OR Attached to Event
        return query.filter(
            (Route.creator_id == current_user_id) | route_is_in_event
        ).first()
    
    # Not logged in? Only show if attached to an event
    return query.filter(route_is_in_event).first()

def get_route(db: Session, route_id: str) -> Optional[Route]:
    route_uuid = _parse_route_id(route_id)
    return db.query(Route).filter(Route.id == route_uuid).first()


def _find_existing_route(db: Session, creator_id: uuid.UUID, payload: RouteCreate) -> Optional[Route]:
    return (
        db.query(Route)
        .filter(
            Route.creator_id == creator_id,
            Route.map_data == payload.map_data,
            Route.distance_km == payload.distance_km,
            Route.start_lat == payload.start_lat,
            Route.start_lng == payload.start_lng,
            Route.end_lat == payload.end_lat,
            Route.end_lng == payload.end_lng,
        )
        .first()
    )


def create_route(db: Session, creator: User, payload: RouteCreate) -> Route:
    existing = _find_existing_route(db, creator.uid, payload)
    if existing:
        return existing

    route = Route(
        creator_id=creator.uid,
        name=payload.name,
        distance_km=payload.distance_km,
        elevation_gain_m=payload.elevation_gain_m,
        start_lat=payload.start_lat,
        start_lng=payload.start_lng,
        start_address=payload.start_address,
        end_lat=payload.end_lat,
        end_lng=payload.end_lng,
        end_address=payload.end_address,
        map_data=payload.map_data,
        avoid_pollution=payload.avoid_pollution or False,
        environment=EnvironmentEnum(payload.environment.value if hasattr (payload.environment, 'value') else payload.environment) if payload.environment else None,
        terrain=TerrainEnum(payload.terrain.value if hasattr (payload.terrain, 'value') else payload.terrain) if payload.terrain else None,
        elevation_profile=ElevationProfileEnum(payload.elevation_profile.value if hasattr (payload.elevation_profile, 'value') else payload.elevation_profile) if payload.elevation_profile else None,
    )
    try:
        db.add(route)
        db.commit()
        db.refresh(route)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create route") from exc
    return route


def delete_route(db: Session, requester: User, route: Route) -> None:
    if route.creator_id != requester.uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only creator can delete route")

    event = db.query(Event).filter(Event.route_id == route.id, Event.is_deleted == False).first()
    if event:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Route is attached to an event")

    try:
        db.delete(route)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not delete route") from exc
