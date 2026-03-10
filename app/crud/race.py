from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from uuid import UUID

from ..models.race import Race
from ..schemas.race import ExternalRaceSync 

def get_race_by_id(db: Session, race_id: UUID) -> Race:
    """Fetch a local race, throwing an HTTP 404 if it doesn't exist."""
    try:
        race = db.query(Race).filter(Race.id == race_id).first()
        if not race:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Race not found in the local database."
            )
        return race
    except HTTPException:
        raise # Re-raise the 404 so it isn't caught by the general SQLAlchemyError block
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while fetching the race."
        )

def get_race_by_external_id(db: Session, external_id: str, provider: str) -> Race | None:
    """Internal helper: checks cache. Doesn't throw HTTP errors so it can be used safely by the sync function."""
    try:
        return db.query(Race).filter(
            Race.external_id == external_id,
            Race.external_provider == provider
        ).first()
    except SQLAlchemyError as e:
        return None

def sync_or_create_external_race(db: Session, race_data: ExternalRaceSync) -> Race:
    """Gets or creates the race, throwing HTTP 409 or 500 on failure."""
    # 1. Check if it already exists
    existing_race = get_race_by_external_id(
        db, 
        external_id=race_data.external_id, 
        provider=race_data.external_provider
    )
    
    if existing_race:
        return existing_race
        
    # 2. Prepare new local record
    new_race = Race(
        external_id=race_data.external_id,
        external_provider=race_data.external_provider,
        name=race_data.name,
        start_time=race_data.start_time,
        location_text=race_data.location_text,
        distance_km=race_data.distance_km,
        distance_label=race_data.distance_label,
        registration_url=race_data.registration_url,
        map_data=race_data.map_data
    )
    
    try:
        db.add(new_race)
        db.commit()
        db.refresh(new_race)
        return new_race
        
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail="A conflict occurred. This race might already be syncing."
        )
        
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An internal database error occurred while syncing the race."
        )