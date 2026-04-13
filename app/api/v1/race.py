import httpx
from fastapi import APIRouter, Depends, HTTPException, logger, status
from sqlalchemy.orm import Session
from datetime import datetime
from uuid import UUID
import uuid

from app.crud.race import sync_or_create_external_race, get_race_by_id
from app.lib.db import get_db
from app.schemas.race import ExternalRaceSync, SyncResponse, RaceResponse

router = APIRouter(prefix="/api/v1/races", tags=["Races"])

@router.get("/search/external")
async def search_external_races(query: str):
    url = "https://runsignup.com/rest/races"
    params = {
        "format": "json",
        "name": query,
        "events": "T"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT, 
                detail="The external race provider timed out."
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, 
                detail="External race provider is currently unavailable."
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, 
                detail="Received an invalid response from the external provider."
            )
            
    data = response.json()
    mapped_races = []
    
    for item in data.get("races", []):
        race = item.get("race", {})
        address = race.get("address", {})
        
        mapped_races.append({
            "external_id": str(race.get("race_id")),
            "external_provider": "runsignup",
            "name": race.get("name", "Unknown Race"),
            "location_text": f"{address.get('city', '')}, {address.get('country_code', '')}".strip(", "),
            "registration_url": race.get("url"),
            "start_time": datetime.utcnow().isoformat(), 
            "distance_km": 42.195,                       
            "distance_label": "Marathon"                 
        })
        
    return mapped_races


@router.post("/sync", response_model=SyncResponse)
def sync_race(race_data: ExternalRaceSync, db: Session = Depends(get_db)):
    # Any DB exceptions (409, 500) are automatically raised by the CRUD function
    local_race = sync_or_create_external_race(db=db, race_data=race_data)
    
    return SyncResponse(
        message="Race is ready in local database", 
        local_race_id=local_race.id
    )


@router.get("/{race_id:uuid}", response_model=RaceResponse)
def get_local_race(race_id: UUID, db: Session = Depends(get_db)):
    # The 404 or 500 exceptions are automatically raised by the CRUD function
    return get_race_by_id(db, race_id=race_id)