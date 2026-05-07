from random import random
import json
import math

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
import uuid
import os
from sqlalchemy import exists

import httpx
from fastapi import HTTPException, status

from ..models import Post, Route, Event, User
from ..schemas.route import RouteCreate, RouteSave
from ..models.route import EnvironmentEnum, TerrainEnum, ElevationProfileEnum

GRAPHHOPPER_API_KEY = os.getenv("GRAPHHOPPER_API_KEY")
OSRM_BASE_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/foot"
OSRM_NEAREST_URL = "https://routing.openstreetmap.de/routed-foot/nearest/v1/foot"


def _build_graphhopper_custom_model(payload: RouteCreate) -> dict:
    terrain_pref = getattr(payload, 'terrain', None)
    prefers_unpaved = terrain_pref == "unpaved" or terrain_pref == TerrainEnum.unpaved

    # Strong bonuses for pedestrian/local roads; heavy penalties for arterials/highways.
    # distance_influence=30 (down from 70) makes GH willing to take longer paths through
    # side streets rather than cutting straight across on major roads.
    priority_rules = [
        {"if": "road_class == FOOTWAY",      "multiply_by": 2.3},
        {"if": "road_class == PATH",          "multiply_by": 2.1},
        {"if": "road_class == CYCLEWAY",      "multiply_by": 1.9},
        {"if": "road_class == PEDESTRIAN",    "multiply_by": 1.9},
        {"if": "road_class == LIVING_STREET", "multiply_by": 1.75},
        {"if": "road_class == RESIDENTIAL",   "multiply_by": 1.55},
        {"if": "road_class == UNCLASSIFIED",  "multiply_by": 1.35},
        {"if": "road_class == SERVICE",       "multiply_by": 1.2},
        {"if": "road_class == TRACK",         "multiply_by": 1.15 if prefers_unpaved else 0.8},
        {"if": "road_class == TERTIARY",      "multiply_by": 0.85},
        {"if": "road_class == SECONDARY",     "multiply_by": 0.65},
        {"if": "road_class == PRIMARY",       "multiply_by": 0.35},
        {"if": "road_class == TRUNK",         "multiply_by": 0.15},
        {"if": "road_class == MOTORWAY",      "multiply_by": 0.01},
    ]

    if prefers_unpaved:
        priority_rules.extend([
            {"if": "surface == UNPAVED", "multiply_by": 1.2},
            {"if": "surface == GRAVEL",  "multiply_by": 1.15},
        ])
    else:
        priority_rules.extend([
            {"if": "surface == ASPHALT", "multiply_by": 1.05},
            {"if": "surface == PAVED",   "multiply_by": 1.05},
        ])

    return {
        "priority": priority_rules,
        "distance_influence": 25,
    }


def _decode_polyline(encoded: str, precision: int = 5) -> list[dict]:
    """Decode a Google-style encoded polyline string to lat/lng coordinates."""
    factor = 10 ** precision
    points = []
    index = 0
    lat = 0
    lng = 0

    while index < len(encoded):
        result = _decode_value(encoded, index, factor)
        lat += result['value']
        index = result['index']

        result = _decode_value(encoded, index, factor)
        lng += result['value']
        index = result['index']

        points.append({'latitude': lat / factor, 'longitude': lng / factor})

    return points


def _decode_value(encoded: str, index: int, factor: int) -> dict:
    """Helper to decode a single value from encoded polyline."""
    value = 0
    shift = 0
    while index < len(encoded):
        code = ord(encoded[index]) - 63
        index += 1
        value |= (code & 0x1f) << shift
        shift += 5
        if not (code & 0x20):
            break

    value = ~(value >> 1) if (value & 1) else (value >> 1)
    return {'value': value, 'index': index}


def _haversine_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _distance_tolerance_km(target_km: float) -> float:
    """
    Strict tolerance for user-requested distance in location-to-location routing.
    Keep generated route close to the requested distance; otherwise fail clearly.
    """
    return max(0.25, target_km * 0.05)


def _route_backtrack_penalty(coords: list[dict]) -> float:
    """
    Higher penalty means more likely route has sharp reversals / backtracking.
    """
    if len(coords) < 4:
        return 0.0

    def bearing(a: dict, b: dict) -> float:
        lat1 = math.radians(a["latitude"])
        lat2 = math.radians(b["latitude"])
        dlon = math.radians(b["longitude"] - a["longitude"])
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        return (math.degrees(math.atan2(y, x)) + 360) % 360

    reversals = 0
    duplicate_hits = 0
    rounded_seen: set[tuple[float, float]] = set()

    for i in range(1, len(coords)):
        rounded = (round(coords[i]["latitude"], 5), round(coords[i]["longitude"], 5))
        if rounded in rounded_seen:
            duplicate_hits += 1
        rounded_seen.add(rounded)

    for i in range(1, len(coords) - 1):
        b1 = bearing(coords[i - 1], coords[i])
        b2 = bearing(coords[i], coords[i + 1])
        turn = abs(((b2 - b1 + 540) % 360) - 180)
        if turn > 155:
            reversals += 1

    return reversals + duplicate_hits * 0.6


def _normalize_route_coordinates(payload: RouteCreate) -> tuple[float, float, float, float]:
    original = (payload.start_lat, payload.start_lng, payload.end_lat, payload.end_lng)
    candidates = [original]

    if abs(payload.start_lng) <= 90 and abs(payload.start_lat) <= 180:
        candidates.append((payload.start_lng, payload.start_lat, payload.end_lat, payload.end_lng))
    if abs(payload.end_lng) <= 90 and abs(payload.end_lat) <= 180:
        candidates.append((payload.start_lat, payload.start_lng, payload.end_lng, payload.end_lat))
    if abs(payload.start_lng) <= 90 and abs(payload.start_lat) <= 180 and abs(payload.end_lng) <= 90 and abs(payload.end_lat) <= 180:
        candidates.append((payload.start_lng, payload.start_lat, payload.end_lng, payload.end_lat))

    def geo_distance(candidate: tuple[float, float, float, float]) -> float:
        return _haversine_distance_km(candidate[0], candidate[1], candidate[2], candidate[3])

    original_geo_km = geo_distance(original)
    best_candidate = min(candidates, key=geo_distance)
    best_geo_km = geo_distance(best_candidate)
    target_km = float(payload.distance_km)

    if (
        best_candidate != original
        and original_geo_km > max(target_km * 5, 30)
        and best_geo_km < original_geo_km * 0.2
        and best_geo_km <= max(target_km * 3, 20)
    ):
        return best_candidate

    return original


def _extract_graphhopper_error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        payload = exc.response.json()
        if isinstance(payload, dict):
            if isinstance(payload.get("message"), str) and payload["message"].strip():
                return payload["message"].strip()
            hints = payload.get("hints")
            if isinstance(hints, list) and hints:
                first = hints[0]
                if isinstance(first, dict):
                    message = first.get("message")
                    if isinstance(message, str) and message.strip():
                        return message.strip()
    except Exception:
        pass

    return f"GraphHopper request failed with HTTP {exc.response.status_code}"


def _is_graphhopper_flexible_mode_rejection(exc: httpx.HTTPStatusError) -> bool:
    return exc.response.status_code == 400 and "flexible mode" in _extract_graphhopper_error_detail(exc).lower()


def _format_point(lat: float, lng: float) -> str:
    return f"{lat},{lng}"


def _offset_point_along_segment(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    position: float,
    perpendicular_offset_km: float,
    side: int,
) -> str:
    base_lat = start_lat + (end_lat - start_lat) * position
    base_lng = start_lng + (end_lng - start_lng) * position

    mean_lat_rad = math.radians((start_lat + end_lat) / 2)
    dx_km = (end_lng - start_lng) * 111.32 * math.cos(mean_lat_rad)
    dy_km = (end_lat - start_lat) * 111.32
    segment_length_km = math.hypot(dx_km, dy_km)

    if segment_length_km < 0.05:
        return _format_point(base_lat, base_lng)

    perp_x = (-dy_km / segment_length_km) * perpendicular_offset_km * side
    perp_y = (dx_km / segment_length_km) * perpendicular_offset_km * side

    offset_lat = base_lat + (perp_y / 111.32)
    lng_scale = max(111.32 * math.cos(mean_lat_rad), 0.0001)
    offset_lng = base_lng + (perp_x / lng_scale)
    return _format_point(offset_lat, offset_lng)


def _build_detour_candidate_point_sets(
    payload: RouteCreate,
    direct_route_distance_km: float,
) -> list[list[str]]:
    start_lat = payload.start_lat
    start_lng = payload.start_lng
    end_lat = payload.end_lat
    end_lng = payload.end_lng
    direct_geo_km = max(_haversine_distance_km(start_lat, start_lng, end_lat, end_lng), 0.1)
    target_km = float(payload.distance_km)
    extra_distance_km = max(target_km - direct_route_distance_km, 0.25)
    detour_target_total_km = direct_geo_km + extra_distance_km
    offset_base_km = max(
        math.sqrt(max((detour_target_total_km / 2) ** 2 - (direct_geo_km / 2) ** 2, 0.0)),
        0.2,
    )

    candidates: list[list[str]] = []
    start_pt = _format_point(start_lat, start_lng)
    end_pt = _format_point(end_lat, end_lng)

    for side in (-1, 1):
        for scale in (0.4, 0.6, 0.85, 1.1, 1.35, 1.7, 2.1, 2.6, 3.2):
            offset_km = offset_base_km * scale
            midpoint = _offset_point_along_segment(
                start_lat,
                start_lng,
                end_lat,
                end_lng,
                0.5,
                offset_km,
                side,
            )
            candidates.append([start_pt, midpoint, end_pt])

            first_detour = _offset_point_along_segment(
                start_lat,
                start_lng,
                end_lat,
                end_lng,
                0.32,
                offset_km * 0.9,
                side,
            )
            second_detour = _offset_point_along_segment(
                start_lat,
                start_lng,
                end_lat,
                end_lng,
                0.68,
                offset_km * 0.9,
                side,
            )
            candidates.append([start_pt, first_detour, second_detour, end_pt])

            opposite_second_detour = _offset_point_along_segment(
                start_lat,
                start_lng,
                end_lat,
                end_lng,
                0.7,
                offset_km * 0.8,
                -side,
            )
            candidates.append([start_pt, first_detour, opposite_second_detour, end_pt])

    return candidates


async def _request_osrm_route_for_points(points: list[str]) -> dict:
    osrm_coordinates = []
    for point in points:
        lat_str, lng_str = point.split(",")
        osrm_coordinates.append(f"{lng_str},{lat_str}")

    url = f"{OSRM_BASE_URL}/" + ";".join(osrm_coordinates)
    params = {
        "overview": "full",
        "geometries": "geojson",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    routes = data.get("routes") or []
    if not routes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not generate a route for this location. Please check your start and end points.",
        )

    best_route = routes[0]
    coordinates = best_route.get("geometry", {}).get("coordinates", [])
    decoded_coords = [
        {"latitude": lat, "longitude": lng}
        for lng, lat in coordinates
    ]

    return {
        "map_data": decoded_coords,
        "distance_km": round(best_route["distance"] / 1000, 2),
        "duration_seconds": int(best_route["duration"]),
        "elevation_gain_m": None,
    }


async def _request_osrm_nearest(lat: float, lng: float) -> tuple[float, float] | None:
    url = f"{OSRM_NEAREST_URL}/{lng},{lat}"
    params = {"number": 1}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None

    waypoints = data.get("waypoints") or []
    if not waypoints:
        return None

    location = waypoints[0].get("location")
    if not (isinstance(location, list) and len(location) >= 2):
        return None

    snapped_lng, snapped_lat = location[0], location[1]
    if not (isinstance(snapped_lat, (int, float)) and isinstance(snapped_lng, (int, float))):
        return None

    snap_dist_km = _haversine_distance_km(lat, lng, float(snapped_lat), float(snapped_lng))
    if snap_dist_km > 0.2:
        return None

    return float(snapped_lat), float(snapped_lng)


async def _request_osrm_route(payload: RouteCreate) -> dict:
    return await _request_osrm_route_for_points([
        _format_point(payload.start_lat, payload.start_lng),
        _format_point(payload.end_lat, payload.end_lng),
    ])


async def _request_osrm_distance_constrained_route(payload: RouteCreate) -> dict:
    direct_route = await _request_osrm_route(payload)
    target_km = float(payload.distance_km)
    tolerance_km = _distance_tolerance_km(target_km)

    if direct_route["distance_km"] > target_km + tolerance_km:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The selected start and end points already require {direct_route['distance_km']} km, "
                f"which is longer than the requested {round(target_km, 2)} km."
            ),
        )

    if abs(direct_route["distance_km"] - target_km) <= tolerance_km:
        return direct_route

    best_route = direct_route
    best_gap = abs(direct_route["distance_km"] - target_km)

    # Collect all unique intermediate waypoints from every candidate set, then
    # snap them all to local roads in one Overpass call.  This steers the router
    # onto residential streets / footpaths rather than the nearest arterial.
    raw_candidates = _build_detour_candidate_point_sets(payload, direct_route["distance_km"])
    unique_mids: dict[str, tuple[float, float]] = {}
    for cand in raw_candidates:
        for pt in cand[1:-1]:
            if pt not in unique_mids:
                lat_s, lng_s = pt.split(",")
                unique_mids[pt] = (float(lat_s), float(lng_s))

    if unique_mids:
        snapped_coords = await _snap_waypoints_to_routable_roads(list(unique_mids.values()))
        snap_map = {
            orig: _format_point(*sc)
            for orig, sc in zip(unique_mids.keys(), snapped_coords)
        }
    else:
        snap_map = {}

    for raw_candidate in raw_candidates:
        candidate_points = (
            [raw_candidate[0]]
            + [snap_map.get(pt, pt) for pt in raw_candidate[1:-1]]
            + [raw_candidate[-1]]
        )
        try:
            candidate_route = await _request_osrm_route_for_points(candidate_points)
        except (httpx.RequestError, httpx.HTTPStatusError):
            continue

        candidate_gap = abs(candidate_route["distance_km"] - target_km)
        if candidate_gap < best_gap:
            best_route = candidate_route
            best_gap = candidate_gap

        if candidate_gap <= tolerance_km:
            return candidate_route

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Could not find a route between the selected points within ±{round(tolerance_km, 2)} km "
            f"of {round(target_km, 2)} km. Best available was {best_route['distance_km']} km."
        ),
    )


async def _request_graphhopper_route_for_points(
    points: list[str],
    payload: RouteCreate,
    gh_profile: str,
) -> dict:
    url = "https://graphhopper.com/api/1/route"

    base_params: dict[str, object] = {
        "point": points,
        "profile": gh_profile,
        "points_encoded": "true",
        "key": GRAPHHOPPER_API_KEY,
        "elevation": "false",
    }

    params_with_custom_model = {
        **base_params,
        "ch.disable": "true",
        "custom_model": json.dumps(_build_graphhopper_custom_model(payload)),
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params_with_custom_model)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if not _is_graphhopper_flexible_mode_rejection(exc):
                raise
            response = await client.get(url, params=base_params)
            response.raise_for_status()
            data = response.json()

    if not data.get("paths"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not generate a route for this location. Please check your start and end points.",
        )

    best_route = data["paths"][0]
    encoded_polyline = best_route["points"]
    decoded_coords = _decode_polyline(encoded_polyline)

    elevation_gain_m = best_route.get("ascend")
    if elevation_gain_m is not None:
        elevation_gain_m = round(float(elevation_gain_m), 1)

    return {
        "map_data": decoded_coords,
        "distance_km": round(best_route["distance"] / 1000, 2),
        "duration_seconds": int(best_route["time"] / 1000),
        "elevation_gain_m": elevation_gain_m,
    }


async def _request_graphhopper_distance_constrained_route(
    payload: RouteCreate,
    gh_profile: str,
    start_pt: str,
    end_pt: str,
) -> dict:
    url = "https://graphhopper.com/api/1/route"
    target_km = float(payload.distance_km)
    strict_tolerance_km = _distance_tolerance_km(target_km)

    base_params: dict[str, object] = {
        "point": [start_pt, end_pt],
        "profile": gh_profile,
        "points_encoded": "true",
        "key": GRAPHHOPPER_API_KEY,
        "elevation": "false",
        "algorithm": "alternative_route",
        "alternative_route.max_paths": 4,
        "alternative_route.max_weight_factor": 1.8,
        "alternative_route.max_share_factor": 0.65,
    }

    params_with_custom_model = {
        **base_params,
        "ch.disable": "true",
        "custom_model": json.dumps(_build_graphhopper_custom_model(payload)),
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params_with_custom_model)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if not _is_graphhopper_flexible_mode_rejection(exc):
                raise
            response = await client.get(url, params=base_params)
            response.raise_for_status()
            data = response.json()

    paths = data.get("paths") or []
    if not paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not generate a route for this location. Please check your start and end points.",
        )

    converted_routes: list[dict] = []
    for path in paths:
        encoded_polyline = path.get("points")
        if not encoded_polyline:
            continue
        decoded_coords = _decode_polyline(encoded_polyline)
        elevation_gain_m = path.get("ascend")
        if elevation_gain_m is not None:
            elevation_gain_m = round(float(elevation_gain_m), 1)
        converted_routes.append(
            {
                "map_data": decoded_coords,
                "distance_km": round(path["distance"] / 1000, 2),
                "duration_seconds": int(path["time"] / 1000),
                "elevation_gain_m": elevation_gain_m,
            }
        )

    if not converted_routes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generated route data was invalid for this location.",
        )

    best_route = min(
        converted_routes,
        key=lambda route: abs(route["distance_km"] - target_km) + (_route_backtrack_penalty(route["map_data"]) * 0.08),
    )
    best_gap = abs(best_route["distance_km"] - target_km)
    backtrack_penalty = _route_backtrack_penalty(best_route["map_data"])

    if best_gap <= strict_tolerance_km and backtrack_penalty <= 8:
        return best_route

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Could not find a clean route between the selected points within ±{round(strict_tolerance_km, 2)} km "
            f"of {round(target_km, 2)} km. Best graph route was {best_route['distance_km']} km."
        ),
    )


async def _request_graphhopper_route(
    payload: RouteCreate,
    gh_profile: str,
    start_pt: str,
    end_pt: str,
) -> dict:
    is_round_trip = start_pt == end_pt

    if not is_round_trip:
        return await _request_graphhopper_distance_constrained_route(payload, gh_profile, start_pt, end_pt)

    url = "https://graphhopper.com/api/1/route"
    target_km = float(payload.distance_km)
    strict_tolerance_km = max(0.35, target_km * 0.08)

    seeds = [int(random() * 1000000) for _ in range(5)]
    best_route: Optional[dict] = None
    best_gap = float("inf")

    async with httpx.AsyncClient() as client:
        for seed in seeds:
            request_params: dict[str, object] = {
                "point": start_pt,
                "profile": gh_profile,
                "algorithm": "round_trip",
                "points_encoded": "true",
                "key": GRAPHHOPPER_API_KEY,
                "elevation": "false",
                "round_trip.distance": int(target_km * 1000),
                "round_trip.seed": seed,
            }

            try:
                response = await client.get(url, params=request_params)
                response.raise_for_status()
            except (httpx.RequestError, httpx.HTTPStatusError):
                continue

            data = response.json()
            paths = data.get("paths") or []
            if not paths:
                continue

            path = paths[0]
            encoded_polyline = path.get("points")
            if not encoded_polyline:
                continue

            decoded_coords = _decode_polyline(encoded_polyline)
            elevation_gain_m = path.get("ascend")
            if elevation_gain_m is not None:
                elevation_gain_m = round(float(elevation_gain_m), 1)

            candidate = {
                "map_data": decoded_coords,
                "distance_km": round(path["distance"] / 1000, 2),
                "duration_seconds": int(path["time"] / 1000),
                "elevation_gain_m": elevation_gain_m,
            }
            gap = abs(candidate["distance_km"] - target_km)
            if gap < best_gap:
                best_gap = gap
                best_route = candidate
            if gap <= strict_tolerance_km:
                return candidate

    if best_route is not None:
        return best_route

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Could not generate a round-trip route for this location. Please try another nearby start point.",
    )


def _offset_origin_point(lat: float, lng: float, north_km: float, east_km: float) -> tuple[float, float]:
    offset_lat = lat + (north_km / 111.32)
    lng_scale = max(111.32 * math.cos(math.radians(lat)), 0.0001)
    offset_lng = lng + (east_km / lng_scale)
    return offset_lat, offset_lng


async def _snap_waypoints_via_overpass(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """
    Snap a batch of (lat, lng) waypoints to the nearest local road using a single
    Overpass API bounding-box query. Queries for footways, paths, living streets,
    residential, service, unclassified and tertiary roads — everything that makes
    up a residential neighbourhood. Falls back to the original coordinates if
    Overpass is unavailable, times out, or returns nothing within 600 m.

    One Overpass call for all points keeps latency low even when there are many
    detour candidates.
    """
    if not points:
        return points

    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    # Bounding box with a small padding
    min_lat = min(lats) - 0.012
    max_lat = max(lats) + 0.012
    min_lng = min(lngs) - 0.012
    max_lng = max(lngs) + 0.012

    query = (
        "[out:json][timeout:9];"
        'way["highway"~"^(footway|path|living_street|residential|service|unclassified|tertiary)$"]'
        f"({min_lat},{min_lng},{max_lat},{max_lng});"
        "out center 500;"
    )

    try:
        async with httpx.AsyncClient(timeout=11.0) as client:
            resp = await client.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
            )
            resp.raise_for_status()

        elements = [e for e in resp.json().get("elements", []) if "center" in e]
        if not elements:
            return points

        result: list[tuple[float, float]] = []
        for lat, lng in points:
            best = min(
                elements,
                key=lambda e: _haversine_distance_km(
                    lat, lng, e["center"]["lat"], e["center"]["lon"]
                ),
            )
            dist_km = _haversine_distance_km(
                lat, lng, best["center"]["lat"], best["center"]["lon"]
            )
            # Only snap if the nearest local road is within 150 m;
            # otherwise keep the original geometric waypoint.
            if dist_km < 0.15:
                result.append((best["center"]["lat"], best["center"]["lon"]))
            else:
                result.append((lat, lng))
        return result

    except Exception:
        # Overpass unavailable or timed out — continue with un-snapped waypoints
        return points


async def _snap_waypoints_to_routable_roads(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """
    Snap candidate waypoints in two stages:
    1) Overpass snap to neighborhood/local roads (street-level preference)
    2) OSRM nearest snap to ensure each point is routable on the foot network
    """
    if not points:
        return points

    overpass_snapped = await _snap_waypoints_via_overpass(points)
    result: list[tuple[float, float]] = []
    for lat, lng in overpass_snapped:
        nearest = await _request_osrm_nearest(lat, lng)
        if nearest is not None:
            result.append(nearest)
        else:
            result.append((lat, lng))
    return result


async def _request_osrm_round_trip_route(payload: RouteCreate) -> dict:
    start_lat = float(payload.start_lat)
    start_lng = float(payload.start_lng)
    start_pt = _format_point(start_lat, start_lng)
    target_km = float(payload.distance_km)
    tolerance_km = max(0.6, target_km * 0.18)

    orientation_vectors = [
        (1.0, 0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0, -1.0),
        (0.0, 1.0, -1.0, 0.0),
        (0.0, -1.0, 1.0, 0.0),
    ]
    scales = (0.18, 0.24, 0.32, 0.42, 0.55, 0.72, 0.92)

    # Pre-generate all intermediate waypoints so they can be batch-snapped
    # to local roads in a single Overpass query before any routing calls.
    all_raw_candidates: list[list[str]] = []
    all_mid_points: list[tuple[float, float]] = []
    for scale in scales:
        radius_km = max(target_km * scale, 0.25)
        for n1, e1, n2, e2 in orientation_vectors:
            p1 = _offset_origin_point(start_lat, start_lng, n1 * radius_km, e1 * radius_km)
            p2 = _offset_origin_point(start_lat, start_lng, n2 * radius_km, e2 * radius_km)
            all_raw_candidates.append([start_pt, _format_point(*p1), _format_point(*p2), start_pt])
            all_mid_points.extend([p1, p2])

    # One Overpass call snaps all waypoints to the nearest local road
    snapped_mids = await _snap_waypoints_to_routable_roads(all_mid_points)
    snap_it = iter(snapped_mids)

    candidates_snapped: list[list[str]] = []
    for _ in all_raw_candidates:
        s1 = next(snap_it)
        s2 = next(snap_it)
        candidates_snapped.append([start_pt, _format_point(*s1), _format_point(*s2), start_pt])

    best_route: Optional[dict] = None
    best_gap = float("inf")

    for candidate_points in candidates_snapped:
        try:
            candidate = await _request_osrm_route_for_points(candidate_points)
        except (httpx.RequestError, httpx.HTTPStatusError, HTTPException):
            continue

        gap = abs(candidate["distance_km"] - target_km)
        if gap < best_gap:
            best_gap = gap
            best_route = candidate

        if gap <= tolerance_km:
            return candidate

    if best_route and best_gap <= max(1.2, target_km * 0.32):
        return best_route

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Could not generate a round-trip close to {round(target_km, 2)} km for this point. "
            "Try a slightly larger target distance or a nearby start point."
        ),
    )


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

    route_is_in_event = exists().where(Event.route_id == Route.id, Event.is_deleted.is_(False))

    if current_user_id:
        return query.filter(
            (Route.creator_id == current_user_id) | route_is_in_event
        ).first()

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

    start_lat, start_lng, end_lat, end_lng = _normalize_route_coordinates(payload)
    normalized_payload = payload.model_copy(
        update={
            "start_lat": start_lat,
            "start_lng": start_lng,
            "end_lat": end_lat,
            "end_lng": end_lng,
        }
    )
    start_pt = f"{start_lat},{start_lng}"
    end_pt = f"{end_lat},{end_lng}"

    terrain_pref = getattr(payload, 'terrain', None)
    elevation_pref = getattr(payload, 'elevation_profile', None)
    gh_profile = "foot"

    if terrain_pref == "unpaved" or terrain_pref == TerrainEnum.unpaved:
        gh_profile = "hike"
    elif elevation_pref == "flat" or elevation_pref == ElevationProfileEnum.flat:
        gh_profile = "foot"

    if GRAPHHOPPER_API_KEY:
        fallback_error_detail: Optional[str] = None
        try:
            return await _request_graphhopper_route(normalized_payload, gh_profile, start_pt, end_pt)
        except httpx.RequestError as exc:
            fallback_error_detail = f"Error connecting to GraphHopper API: {str(exc)}"
            if start_pt == end_pt:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=fallback_error_detail,
                ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Round-trip route generation requires a valid GraphHopper API key.",
                ) from exc
            fallback_error_detail = _extract_graphhopper_error_detail(exc)
        except HTTPException as exc:
            fallback_error_detail = str(exc.detail)

        # GraphHopper can fail in dense/local-road areas; fallback to OSRM keeps
        # route generation available for street-level routing.
        try:
            if start_pt != end_pt:
                return await _request_osrm_distance_constrained_route(normalized_payload)
            return await _request_osrm_round_trip_route(normalized_payload)
        except HTTPException as osrm_exc:
            if fallback_error_detail:
                raise HTTPException(
                    status_code=osrm_exc.status_code,
                    detail=f"{fallback_error_detail}. OSRM fallback also failed: {osrm_exc.detail}",
                ) from osrm_exc
            raise

    if start_pt != end_pt:
        return await _request_osrm_distance_constrained_route(normalized_payload)

    return await _request_osrm_round_trip_route(normalized_payload)


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
        environment=EnvironmentEnum(payload.environment.value if hasattr(payload.environment, 'value') else payload.environment) if payload.environment else None,
        terrain=TerrainEnum(payload.terrain.value if hasattr(payload.terrain, 'value') else payload.terrain) if payload.terrain else None,
        elevation_profile=ElevationProfileEnum(payload.elevation_profile.value if hasattr(payload.elevation_profile, 'value') else payload.elevation_profile) if payload.elevation_profile else None,
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

    event = db.query(Event).filter(Event.route_id == route.id, Event.is_deleted.is_(False)).first()
    if event:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Route is attached to an event")

    try:
        # Decouple shared posts from this saved route before deletion so feed
        # posts remain visible with their route snapshot data.
        db.query(Post).filter(Post.route_id == route.id).update(
            {Post.route_id: None},
            synchronize_session=False,
        )
        db.delete(route)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not delete route") from exc
