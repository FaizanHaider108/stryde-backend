from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid

from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models import User
from ...crud import route as route_crud
from ...schemas.route import RouteCreate, RouteResponse

router = APIRouter(prefix="/api/v1/routes", tags=["routes"])

@router.get("/me", response_model=list[RouteResponse])
def get_my_routes(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all routes created by the logged-in user."""
    return route_crud.get_user_routes(db, current_user.uid)

@router.get("/{route_id}", response_model=RouteResponse)
def get_single_route(route_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get a specific route, respecting privacy/event sharing rules."""
    route = route_crud.get_visible_route(db, route_id, current_user.uid)
    if not route:
        # We return 404 even if it exists but is private to protect privacy
        raise HTTPException(status_code=404, detail="Route not found or access denied")
    return route

@router.post("/", response_model=RouteResponse, status_code=status.HTTP_201_CREATED)
def create_route(payload: RouteCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    route = route_crud.create_route(db, current_user, payload)
    return route


@router.delete("/{route_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(route_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    route = route_crud.get_route(db, str(route_id))
    if not route:
        raise HTTPException(status_code=404, detail="route not found")
    route_crud.delete_route(db, current_user, route)
