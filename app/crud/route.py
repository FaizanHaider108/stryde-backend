from random import random

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
import uuid
import os
from sqlalchemy import exists

import httpx
from fastapi import HTTPException, status

from ..models import Route, Event, User
from ..schemas.route import RouteCreate, RouteSave
from ..models.route import EnvironmentEnum, TerrainEnum, ElevationProfileEnum

GRAPHHOPPER_API_KEY = os.getenv("GRAPHHOPPER_API_KEY")

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

async def create_route(payload: RouteCreate, creator: User) -> dict:
    if not creator or not creator.uid:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    start_pt = f"{payload.start_lat},{payload.start_lng}"
    end_pt = f"{payload.end_lat},{payload.end_lng}"

    # --- 1. PREFERENCE MAPPING (The Friday Shortcut) ---
    # We safely extract the string values in case Pydantic passes them as raw strings
    terrain_pref = getattr(payload, 'terrain', None)
    elevation_pref = getattr(payload, 'elevation_profile', None)
    
    # Default to standard pedestrian
    gh_profile = "foot" 

    # Swap the engine profile based on user preferences
    if terrain_pref == "unpaved" or terrain_pref == TerrainEnum.unpaved:
        gh_profile = "hike" 
    elif elevation_pref == "flat" or elevation_pref == ElevationProfileEnum.flat:
        # Wheelchair profile is the most aggressive way to force perfectly flat, paved routes
        gh_profile = "foot" 

    # --- 2. ROUTING LOGIC ---
    if start_pt == end_pt:
        point = start_pt
        algorithm = "round_trip"
    else:
        point = [start_pt, end_pt]
        algorithm = "alternative_route"

    seed = int(random() * 1000000)  # Random seed for variability in round trips
    
    url = "https://graphhopper.com/api/1/route"
    
    params = {
        "point": point,
        "profile": gh_profile,      # Dynamically injected profile!
        "algorithm": algorithm,
        "points_encoded": "true",
        "key": GRAPHHOPPER_API_KEY,
        # Elevation data returns Z-coordinates. Set to true if your frontend needs it.
        "elevation": "false"        
    }

    # Safely attach algorithm-specific parameters to prevent API crashes
    if algorithm == "round_trip":
        target_distance_meters = int(float(payload.distance_km) * 1000)
        params["round_trip.distance"] = target_distance_meters
        params["round_trip.seed"] = seed
    else:
        params["alternative_route.max_paths"] = 2 

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if not data.get("paths"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"Could not generate a route for this location: {str(exc)}"
                )
            
            best_route = data["paths"][0]

            # Return exactly what the endpoint needs
            return {
                "map_data": best_route["points"],
                "distance_km": round(best_route["distance"] / 1000, 2),
                "duration_seconds": int(best_route["time"] / 1000)
            }

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Error connecting to GraphHopper API: {str(exc)}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code, 
            detail=f"GraphHopper API error: {str(exc)}"
        ) from exc
    
def save_route(db: Session, creator: User, payload: RouteSave) -> Route:
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
