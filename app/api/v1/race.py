import httpx
from fastapi import APIRouter, Depends, HTTPException, logger, status
from sqlalchemy.orm import Session
from datetime import datetime
from uuid import UUID
import uuid
import re

from app.crud.race import sync_or_create_external_race, get_race_by_id
from app.lib.db import get_db
from app.schemas.race import ExternalRaceSync, SyncResponse, RaceResponse

router = APIRouter(prefix="/api/v1/races", tags=["Races"])


def _parse_distance_from_event_label(label: str) -> tuple[float | None, str | None]:
    text = (label or "").lower()
    if not text:
        return None, None

    if "marathon" in text and "half" not in text:
        return 42.195, "Marathon"
    if "half" in text and "marathon" in text:
        return 21.097, "Half Marathon"
    if "10k" in text:
        return 10.0, "10K"
    if "5k" in text:
        return 5.0, "5K"

    miles_match = re.search(r"(\d+(?:\.\d+)?)\s*(mi|mile|miles)\b", text)
    if miles_match:
        miles = float(miles_match.group(1))
        km = round(miles * 1.60934, 3)
        return km, f"{miles:g} mi"

    km_match = re.search(r"(\d+(?:\.\d+)?)\s*(km|kilometer|kilometre|kilometers|kilometres)\b", text)
    if km_match:
        km = float(km_match.group(1))
        return km, f"{km:g} km"

    return None, None

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
        event_candidates = race.get("events") or []
        best_distance_km = None
        best_distance_label = None

        for event in event_candidates:
            event_name = str(event.get("name") or "")
            distance_km, distance_label = _parse_distance_from_event_label(event_name)
            if distance_km is not None:
                if best_distance_km is None or distance_km < best_distance_km:
                    best_distance_km = distance_km
                    best_distance_label = distance_label

        if best_distance_km is None:
            fallback_distance_km, fallback_distance_label = _parse_distance_from_event_label(str(race.get("name") or ""))
            best_distance_km = fallback_distance_km if fallback_distance_km is not None else 5.0
            best_distance_label = fallback_distance_label or f"{best_distance_km:g} km"
        
        mapped_races.append({
            "external_id": str(race.get("race_id")),
            "external_provider": "runsignup",
            "name": race.get("name", "Unknown Race"),
            "location_text": f"{address.get('city', '')}, {address.get('country_code', '')}".strip(", "),
            "registration_url": race.get("url"),
            "start_time": datetime.utcnow().isoformat(), 
            "distance_km": best_distance_km,
            "distance_label": best_distance_label,
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