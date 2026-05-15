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

# Detour / multi-leg OSRM: reject midpoint snaps that jump too far (wrong side of block → chords).
MIDPOINT_MAX_SNAP_DRIFT_M = 150.0

OPEN_ELEVATION_URL = "https://api.open-elevation.com/api/v1/lookup"
OPEN_ELEVATION_BATCH = 100


def _osrm_route_base(terrain_pref: object | None) -> str:
    """OSRM public instance: bike routing is closer to trail networks when terrain is unpaved."""
    if terrain_pref == "unpaved" or terrain_pref == TerrainEnum.unpaved:
        return "https://routing.openstreetmap.de/routed-bike/route/v1/bike"
    return "https://routing.openstreetmap.de/routed-foot/route/v1/foot"


def _osrm_nearest_base(terrain_pref: object | None) -> str:
    if terrain_pref == "unpaved" or terrain_pref == TerrainEnum.unpaved:
        return "https://routing.openstreetmap.de/routed-bike/nearest/v1/bike"
    return "https://routing.openstreetmap.de/routed-foot/nearest/v1/foot"


def _build_graphhopper_custom_model(payload: RouteCreate) -> dict:
    terrain_pref = getattr(payload, "terrain", None)
    elevation_pref = getattr(payload, "elevation_profile", None)
    prefers_unpaved = terrain_pref == "unpaved" or terrain_pref == TerrainEnum.unpaved
    wants_flat = elevation_pref == "flat" or elevation_pref == ElevationProfileEnum.flat

    # Tuned for street-level running: continuous pavements and paths; avoid busy arterials.
    priority_rules: list[dict[str, str]] = [
        {"if": "road_class == FOOTWAY", "multiply_by": "1.5"},
        {"if": "road_class == PATH", "multiply_by": "1.3"},
        {"if": "road_class == CYCLEWAY", "multiply_by": "1.2"},
        {"if": "road_class == RESIDENTIAL", "multiply_by": "1.1"},
        {"if": "road_class == LIVING_STREET", "multiply_by": "1.1"},
        {"if": "road_class == PEDESTRIAN", "multiply_by": "1.15"},
        {"if": "road_class == UNCLASSIFIED", "multiply_by": "1.0"},
        {"if": "road_class == SERVICE", "multiply_by": "0.95"},
        {"if": "road_class == TERTIARY", "multiply_by": "0.85"},
        {"if": "road_class == SECONDARY", "multiply_by": "0.7"},
        {"if": "road_class == PRIMARY", "multiply_by": "0.5"},
        {"if": "road_class == TRUNK", "multiply_by": "0.3"},
        {"if": "road_class == MOTORWAY", "multiply_by": "0.05"},
    ]

    if prefers_unpaved:
        priority_rules.append({"if": "road_class == TRACK", "multiply_by": "1.4"})
    else:
        priority_rules.append({"if": "road_class == TRACK", "multiply_by": "0.75"})

    if wants_flat:
        priority_rules.append({"if": "average_slope > 5", "multiply_by": "0.6"})

    if prefers_unpaved:
        priority_rules.extend(
            [
                {"if": "surface == UNPAVED", "multiply_by": "1.2"},
                {"if": "surface == GRAVEL", "multiply_by": "1.15"},
            ]
        )
    else:
        priority_rules.extend(
            [
                {"if": "surface == ASPHALT", "multiply_by": "1.05"},
                {"if": "surface == PAVED", "multiply_by": "1.05"},
            ]
        )

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


def _graphhopper_points_to_coords(gh_points: object) -> list[dict]:
    """Decode GraphHopper `points`: encoded string or GeoJSON with optional elevation (m)."""
    if isinstance(gh_points, str):
        return _decode_polyline(gh_points)
    if not isinstance(gh_points, dict):
        return []
    coordinates = gh_points.get("coordinates") or []
    out: list[dict] = []
    for c in coordinates:
        if not isinstance(c, (list, tuple)) or len(c) < 2:
            continue
        lng, lat = float(c[0]), float(c[1])
        item: dict = {"latitude": lat, "longitude": lng}
        if len(c) >= 3 and c[2] is not None:
            try:
                item["elevation_m"] = float(c[2])
            except (TypeError, ValueError):
                pass
        out.append(item)
    return out


def _surface_types_from_gh_path(path: dict) -> list[str] | None:
    details = path.get("details") or {}
    surface = details.get("surface")
    if not isinstance(surface, list):
        return None
    ordered: list[str] = []
    for interval in surface:
        if isinstance(interval, (list, tuple)) and len(interval) >= 3:
            label = interval[2]
            if isinstance(label, str) and label and label not in ordered:
                ordered.append(label)
    return ordered or None


def _compute_elevation_stats(coords: list[dict]) -> tuple[float | None, float | None]:
    gain = 0.0
    loss = 0.0
    used_any = False
    for i in range(1, len(coords)):
        e0 = coords[i - 1].get("elevation_m")
        e1 = coords[i].get("elevation_m")
        if e0 is None or e1 is None:
            continue
        used_any = True
        delta = float(e1) - float(e0)
        if delta > 0:
            gain += delta
        else:
            loss += abs(delta)
    if not used_any:
        return None, None
    return round(gain, 1), round(loss, 1)


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
    How close the generated path length must be to the user's requested distance (km).
    Tight enough that a 5 km request cannot silently return ~1.6 km.
    """
    return max(0.2, target_km * 0.04)


def _distance_max_overshoot_km(target_km: float) -> float:
    """Soft cap — prefer routes under this excess length when choosing among candidates."""
    return max(2.0, target_km * 0.6)


def _polyline_length_km(coords: list[dict]) -> float:
    """Ground distance along a polyline (haversine per segment), in km."""
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(coords)):
        a = coords[i - 1]
        b = coords[i]
        total += _haversine_distance_km(
            float(a["latitude"]),
            float(a["longitude"]),
            float(b["latitude"]),
            float(b["longitude"]),
        )
    return total


def _coords_for_self_intersection_test(coords: list[dict], max_segments: int = 900) -> list[tuple[float, float]]:
    """Down-sample long polylines so intersection tests stay fast on mobile CPUs."""
    if len(coords) < 2:
        return []
    if len(coords) <= max_segments + 1:
        return [(float(c["latitude"]), float(c["longitude"])) for c in coords]
    n = len(coords)
    out: list[tuple[float, float]] = []
    for k in range(max_segments + 1):
        idx = min(int(round(k * (n - 1) / max_segments)), n - 1)
        c = coords[idx]
        out.append((float(c["latitude"]), float(c["longitude"])))
    return out


def _segment_intersects_open(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    cx: float,
    cy: float,
    dx: float,
    dy: float,
) -> bool:
    """True if closed segments AB and CD intersect (including proper colinear overlap)."""

    def orient(px: float, py: float, qx: float, qy: float, rx: float, ry: float) -> float:
        return (qy - py) * (rx - qx) - (qx - px) * (ry - qy)

    def on_segment(px: float, py: float, qx: float, qy: float, rx: float, ry: float, eps: float = 1e-10) -> bool:
        return (
            min(px, rx) - eps <= qx <= max(px, rx) + eps
            and min(py, ry) - eps <= qy <= max(py, ry) + eps
        )

    o1 = orient(ax, ay, bx, by, cx, cy)
    o2 = orient(ax, ay, bx, by, dx, dy)
    o3 = orient(cx, cy, dx, dy, ax, ay)
    o4 = orient(cx, cy, dx, dy, bx, by)

    if o1 == 0 and on_segment(ax, ay, cx, cy, bx, by):
        return True
    if o2 == 0 and on_segment(ax, ay, dx, dy, bx, by):
        return True
    if o3 == 0 and on_segment(cx, cy, ax, ay, dx, dy):
        return True
    if o4 == 0 and on_segment(cx, cy, bx, by, dx, dy):
        return True

    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def _polyline_self_intersects(coords: list[dict]) -> bool:
    """
    Detect self-intersection / bow-ties on the route polyline (non-adjacent segments
    that cross). Adjacent segments sharing a vertex are ignored.
    """
    pts = _coords_for_self_intersection_test(coords)
    n = len(pts)
    if n < 4:
        return False
    for i in range(n - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        for j in range(i + 2, n - 1):
            cx, cy = pts[j]
            dx, dy = pts[j + 1]
            if _segment_intersects_open(ax, ay, bx, by, cx, cy, dx, dy):
                return True
    return False


async def _finalize_route_geometry(route: dict) -> dict:
    """
    Recompute distance and elevation stats from the router polyline.

    Snapped start/end pins are already on the network; we do not replace the first/last
    vertices with raw user pins (that used to draw straight segments through buildings).

    OSRM polylines have no elevation — enrich via Open-Elevation when no point has elevation_m.
    """
    coords = list(route.get("map_data") or [])
    if len(coords) >= 2 and not _polyline_has_point_elevation(coords):
        coords = await _enrich_elevation_open_elevation(coords)

    new_len = _polyline_length_km(coords) if len(coords) >= 2 else 0.0
    new_route = {**route, "map_data": coords, "distance_km": round(new_len, 2)}

    gain_poly, loss_poly = _compute_elevation_stats(coords)
    if gain_poly is not None:
        new_route["elevation_gain_m"] = gain_poly
        new_route["elevation_loss_m"] = loss_poly
    elif new_route.get("elevation_loss_m") is None:
        new_route["elevation_loss_m"] = None

    return new_route


def _route_meets_target_length(distance_km: float, target_km: float) -> bool:
    """User-requested distance is a minimum target (within tolerance). Longer routes are OK."""
    return distance_km >= target_km - _distance_tolerance_km(target_km)


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
    """
    Only correct individual coordinate pairs where lat and lng are clearly
    reversed (|lat| > 90 but |lng| <= 90). Never rearrange or swap the
    start/end points with each other — the user chose them explicitly.
    """
    start_lat = float(payload.start_lat)
    start_lng = float(payload.start_lng)
    end_lat = float(payload.end_lat)
    end_lng = float(payload.end_lng)

    if abs(start_lat) > 90 and abs(start_lng) <= 90:
        start_lat, start_lng = start_lng, start_lat
    if abs(end_lat) > 90 and abs(end_lng) <= 90:
        end_lat, end_lng = end_lng, end_lat

    return start_lat, start_lng, end_lat, end_lng


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
        for scale in (0.4, 0.55, 0.7, 0.85, 1.05, 1.25, 1.5, 1.8, 2.2, 2.7, 3.3, 4.0, 5.0, 6.5, 8.5, 11.0):
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


async def _request_osrm_route_for_points(points: list[str], terrain_pref: object | None = None) -> dict:
    osrm_coordinates = []
    for point in points:
        lat_str, lng_str = point.split(",")
        osrm_coordinates.append(f"{lng_str},{lat_str}")

    base = _osrm_route_base(terrain_pref)
    url = f"{base}/" + ";".join(osrm_coordinates)
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
        "elevation_loss_m": None,
        "surface_types": None,
    }


async def _request_osrm_nearest(
    lat: float,
    lng: float,
    terrain_pref: object | None = None,
    max_snap_km: float | None = 0.2,
) -> tuple[float, float] | None:
    base = _osrm_nearest_base(terrain_pref)
    url = f"{base}/{lng},{lat}"
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
    if max_snap_km is not None and snap_dist_km > max_snap_km:
        return None

    return float(snapped_lat), float(snapped_lng)


async def _snap_to_nearest_walkable_node(
    lat: float,
    lng: float,
    terrain_pref: object | None = None,
) -> tuple[float, float]:
    """Snap a pin to the closest routable edge (no max-distance rejection; returns original on failure)."""
    base = _osrm_nearest_base(terrain_pref)
    url = f"{base}/{lng},{lat}"
    params = {"number": 1}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return lat, lng

    waypoints = data.get("waypoints") or []
    if not waypoints:
        return lat, lng
    loc = waypoints[0].get("location")
    if not (isinstance(loc, list) and len(loc) >= 2):
        return lat, lng
    snapped_lng, snapped_lat = loc[0], loc[1]
    if not (isinstance(snapped_lat, (int, float)) and isinstance(snapped_lng, (int, float))):
        return lat, lng
    return float(snapped_lat), float(snapped_lng)


async def _snap_detour_midpoints_for_osrm(
    points: list[tuple[float, float]],
    terrain_pref: object | None,
) -> list[tuple[float, float] | None]:
    """
    Snap each candidate waypoint to the nearest routable edge; return None if the snap
    moved the point too far (likely wrong road / far side of a block). Callers must
    drop None entries instead of routing through raw offset coordinates.
    """
    out: list[tuple[float, float] | None] = []
    for lat, lng in points:
        s_lat, s_lng = await _snap_to_nearest_walkable_node(lat, lng, terrain_pref)
        dist_m = _haversine_distance_km(lat, lng, s_lat, s_lng) * 1000.0
        if dist_m > MIDPOINT_MAX_SNAP_DRIFT_M:
            out.append(None)
        else:
            out.append((s_lat, s_lng))
    return out


def _polyline_has_point_elevation(coords: list[dict]) -> bool:
    return any(c.get("elevation_m") is not None for c in coords)


async def _enrich_elevation_open_elevation(coords: list[dict]) -> list[dict]:
    """Fill elevation_m on coordinates using Open-Elevation (batch POST)."""
    if not coords:
        return coords
    out = [dict(c) for c in coords]
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            for start in range(0, len(out), OPEN_ELEVATION_BATCH):
                chunk = out[start : start + OPEN_ELEVATION_BATCH]
                locations = [
                    {"latitude": float(c["latitude"]), "longitude": float(c["longitude"])}
                    for c in chunk
                ]
                resp = await client.post(OPEN_ELEVATION_URL, json={"locations": locations})
                if resp.status_code != 200:
                    continue
                results = (resp.json() or {}).get("results") or []
                for j, r in enumerate(results):
                    idx = start + j
                    if idx >= len(out):
                        break
                    ele = r.get("elevation")
                    if isinstance(ele, (int, float)):
                        out[idx]["elevation_m"] = float(ele)
    except Exception:
        return coords
    return out


async def _request_osrm_route(payload: RouteCreate) -> dict:
    terrain_pref = getattr(payload, "terrain", None)
    return await _request_osrm_route_for_points(
        [
            _format_point(payload.start_lat, payload.start_lng),
            _format_point(payload.end_lat, payload.end_lng),
        ],
        terrain_pref,
    )


async def _request_osrm_distance_constrained_route(payload: RouteCreate) -> dict:
    terrain_pref = getattr(payload, "terrain", None)
    direct_route = await _request_osrm_route(payload)
    target_km = float(payload.distance_km)
    tol = _distance_tolerance_km(target_km)

    if _route_meets_target_length(direct_route["distance_km"], target_km) and not _polyline_self_intersects(
        direct_route["map_data"]
    ):
        return direct_route

    raw_candidates = _build_detour_candidate_point_sets(payload, direct_route["distance_km"])

    best_route: Optional[dict] = None
    best_key: tuple = (9, 0.0, 0.0, 0.0)
    if not _polyline_self_intersects(direct_route["map_data"]):
        best_route = direct_route
        d0 = direct_route["distance_km"]
        if _route_meets_target_length(d0, target_km):
            gap0 = abs(d0 - target_km)
            cap0 = target_km + _distance_max_overshoot_km(target_km)
            over0 = max(0.0, d0 - cap0)
            best_key = (0, gap0, over0, _route_backtrack_penalty(direct_route["map_data"]) * 0.02)
        else:
            best_key = (1, -d0, 0.0, 0.0)

    async def evaluate_snap_mode(snap_mids: bool) -> None:
        nonlocal best_route, best_key
        snap_map: dict[str, str] = {}
        if snap_mids:
            unique_mids: dict[str, tuple[float, float]] = {}
            for cand in raw_candidates:
                for pt in cand[1:-1]:
                    if pt not in unique_mids:
                        lat_s, lng_s = pt.split(",")
                        unique_mids[pt] = (float(lat_s), float(lng_s))
            if unique_mids:
                snapped_coords = await _snap_detour_midpoints_for_osrm(list(unique_mids.values()), terrain_pref)
                snap_map = {}
                for orig, sc in zip(unique_mids.keys(), snapped_coords):
                    if sc is not None:
                        snap_map[orig] = _format_point(*sc)

        for raw_candidate in raw_candidates:
            if snap_mids and snap_map:
                candidate_points = [raw_candidate[0]]
                for pt in raw_candidate[1:-1]:
                    if pt in snap_map:
                        candidate_points.append(snap_map[pt])
                candidate_points.append(raw_candidate[-1])
            else:
                candidate_points = list(raw_candidate)

            try:
                candidate_route = await _request_osrm_route_for_points(candidate_points, terrain_pref)
            except (httpx.RequestError, httpx.HTTPStatusError, HTTPException):
                continue

            if _polyline_self_intersects(candidate_route["map_data"]):
                continue

            d = candidate_route["distance_km"]
            meets = _route_meets_target_length(d, target_km)
            gap = abs(d - target_km) if meets else 0.0
            if meets:
                cap = target_km + _distance_max_overshoot_km(target_km)
                over = max(0.0, d - cap)
                key = (0, gap, over, _route_backtrack_penalty(candidate_route["map_data"]) * 0.02)
            else:
                key = (1, -d, 0.0, 0.0)

            if best_route is None or key < best_key:
                best_route = candidate_route
                best_key = key

            if meets and gap <= tol:
                return

    await evaluate_snap_mode(False)
    if best_route is None or not _route_meets_target_length(best_route["distance_km"], target_km):
        await evaluate_snap_mode(True)

    if best_route is None or not _route_meets_target_length(best_route["distance_km"], target_km):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Could not build a foot route of at least {target_km - tol:.2f} km "
                f"(target {target_km:.2f} km) between these pins. "
                "Try moving start/end slightly apart, increasing the target distance, or choosing different pins."
            ),
        )

    if _polyline_self_intersects(best_route["map_data"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Could not build a route without the path crossing itself for these pins. "
                "Try adjusting the start or end point slightly."
            ),
        )

    return best_route


def _graphhopper_common_route_params(gh_profile: str) -> dict[str, object]:
    return {
        "profile": gh_profile,
        "points_encoded": "false",
        "elevation": "true",
        "instructions": "false",
        "details": ["surface"],
        "key": GRAPHHOPPER_API_KEY,
    }


def _route_dict_from_graphhopper_path(path: dict) -> dict | None:
    gh_points = path.get("points")
    if gh_points is None:
        return None
    decoded_coords = _graphhopper_points_to_coords(gh_points)
    if not decoded_coords:
        return None
    elevation_gain_m = path.get("ascend")
    if elevation_gain_m is not None:
        elevation_gain_m = round(float(elevation_gain_m), 1)
    return {
        "map_data": decoded_coords,
        "distance_km": round(path["distance"] / 1000, 2),
        "duration_seconds": int(path["time"] / 1000),
        "elevation_gain_m": elevation_gain_m,
        "elevation_loss_m": None,
        "surface_types": _surface_types_from_gh_path(path),
    }


async def _request_graphhopper_route_for_points(
    points: list[str],
    payload: RouteCreate,
    gh_profile: str,
) -> dict:
    url = "https://graphhopper.com/api/1/route"

    base_params: dict[str, object] = {
        "point": points,
        **_graphhopper_common_route_params(gh_profile),
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

    path0 = data["paths"][0]
    route_dict = _route_dict_from_graphhopper_path(path0)
    if route_dict is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not generate a route for this location. Please check your start and end points.",
        )

    if _polyline_self_intersects(route_dict["map_data"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GRAPHOPPER_SELF_INTERSECT",
        )

    return route_dict


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
        **_graphhopper_common_route_params(gh_profile),
        "algorithm": "alternative_route",
        "alternative_route.max_paths": 8,
        "alternative_route.max_weight_factor": 4.0,
        "alternative_route.max_share_factor": 0.55,
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
        route_dict = _route_dict_from_graphhopper_path(path)
        if route_dict is None:
            continue
        converted_routes.append(route_dict)

    if not converted_routes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generated route data was invalid for this location.",
        )

    clean_routes = [r for r in converted_routes if not _polyline_self_intersects(r["map_data"])]
    if not clean_routes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Every suggested path crossed itself for this location. "
                "Try slightly different start or end pins, or a different target distance."
            ),
        )

    best_route = min(
        clean_routes,
        key=lambda route: abs(route["distance_km"] - target_km) + (_route_backtrack_penalty(route["map_data"]) * 0.08),
    )

    if best_route["distance_km"] >= target_km - strict_tolerance_km:
        return best_route

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="GRAPHOPPER_ROUTE_TOO_SHORT",
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
                **_graphhopper_common_route_params(gh_profile),
                "algorithm": "round_trip",
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
            candidate = _route_dict_from_graphhopper_path(path)
            if candidate is None:
                continue

            decoded_coords = candidate["map_data"]
            if _polyline_self_intersects(decoded_coords):
                continue

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


async def _snap_waypoints_to_routable_roads(
    points: list[tuple[float, float]],
    terrain_pref: object | None = None,
) -> list[tuple[float, float]]:
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
        nearest = await _request_osrm_nearest(lat, lng, terrain_pref)
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
    terrain_pref = getattr(payload, "terrain", None)

    orientation_vectors = [
        (1.0, 0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0, -1.0),
        (0.0, 1.0, -1.0, 0.0),
        (0.0, -1.0, 1.0, 0.0),
    ]
    scales = (0.18, 0.24, 0.32, 0.42, 0.55, 0.72, 0.92)

    all_raw_candidates: list[list[str]] = []
    all_mid_points: list[tuple[float, float]] = []
    for scale in scales:
        radius_km = max(target_km * scale, 0.25)
        for n1, e1, n2, e2 in orientation_vectors:
            p1 = _offset_origin_point(start_lat, start_lng, n1 * radius_km, e1 * radius_km)
            p2 = _offset_origin_point(start_lat, start_lng, n2 * radius_km, e2 * radius_km)
            all_raw_candidates.append([start_pt, _format_point(*p1), _format_point(*p2), start_pt])
            all_mid_points.extend([p1, p2])

    # Snap midpoints with drift rejection (avoids OSRM legs that chord across blocks).
    snapped_mids = await _snap_detour_midpoints_for_osrm(all_mid_points, terrain_pref)

    candidates_snapped: list[list[str]] = []
    mid_idx = 0
    for _ in all_raw_candidates:
        s1 = snapped_mids[mid_idx]
        s2 = snapped_mids[mid_idx + 1]
        mid_idx += 2
        if s1 is None or s2 is None:
            continue
        candidates_snapped.append([start_pt, _format_point(*s1), _format_point(*s2), start_pt])

    if not candidates_snapped:
        candidates_snapped = [list(c) for c in all_raw_candidates]

    best_route: Optional[dict] = None
    best_gap = float("inf")

    for candidate_points in candidates_snapped:
        try:
            candidate = await _request_osrm_route_for_points(candidate_points, terrain_pref)
        except (httpx.RequestError, httpx.HTTPStatusError, HTTPException):
            continue

        if _polyline_self_intersects(candidate["map_data"]):
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
    terrain_pref = getattr(payload, "terrain", None)
    start_lat, start_lng = await _snap_to_nearest_walkable_node(start_lat, start_lng, terrain_pref)
    end_lat, end_lng = await _snap_to_nearest_walkable_node(end_lat, end_lng, terrain_pref)
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

    elevation_pref = getattr(payload, "elevation_profile", None)
    gh_profile = "foot"

    if terrain_pref == "unpaved" or terrain_pref == TerrainEnum.unpaved:
        gh_profile = "hike"
    elif elevation_pref == "flat" or elevation_pref == ElevationProfileEnum.flat:
        gh_profile = "foot"

    if GRAPHHOPPER_API_KEY:
        fallback_error_detail: Optional[str] = None
        try:
            gh_result = await _request_graphhopper_route(normalized_payload, gh_profile, start_pt, end_pt)
            finalized = await _finalize_route_geometry(gh_result)
            if _polyline_self_intersects(finalized["map_data"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="GRAPHOPPER_SELF_INTERSECT",
                )
            return finalized
        except HTTPException as exc:
            if str(exc.detail) == "GRAPHOPPER_ROUTE_TOO_SHORT":
                try:
                    if start_pt != end_pt:
                        osrm_result = await _request_osrm_distance_constrained_route(normalized_payload)
                    else:
                        osrm_result = await _request_osrm_round_trip_route(normalized_payload)
                    return await _finalize_route_geometry(osrm_result)
                except HTTPException as osrm_exc:
                    raise HTTPException(
                        status_code=osrm_exc.status_code,
                        detail=(
                            f"Could not build a route close to your requested "
                            f"{float(payload.distance_km):.1f} km. {osrm_exc.detail}"
                        ),
                    ) from osrm_exc
            fallback_error_detail = str(exc.detail)
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

        # GraphHopper can fail in dense/local-road areas; fallback to OSRM keeps
        # route generation available for street-level routing.
        try:
            if start_pt != end_pt:
                osrm_result = await _request_osrm_distance_constrained_route(normalized_payload)
            else:
                osrm_result = await _request_osrm_round_trip_route(normalized_payload)
            return await _finalize_route_geometry(osrm_result)
        except HTTPException as osrm_exc:
            if fallback_error_detail:
                raise HTTPException(
                    status_code=osrm_exc.status_code,
                    detail=f"{fallback_error_detail}. OSRM fallback also failed: {osrm_exc.detail}",
                ) from osrm_exc
            raise

    if start_pt != end_pt:
        osrm_only = await _request_osrm_distance_constrained_route(normalized_payload)
        return await _finalize_route_geometry(osrm_only)

    rt_only = await _request_osrm_round_trip_route(normalized_payload)
    return await _finalize_route_geometry(rt_only)


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

    # Events reference routes with ON DELETE RESTRICT. Removing the route requires
    # deleting those event rows first (cascades invitations / attendee links).
    # Saved-route deletion should succeed even if the route was used for a club run.
    db.query(Event).filter(Event.route_id == route.id).delete(synchronize_session=False)

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
