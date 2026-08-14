from random import random
import asyncio
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

# OSRM candidate routes are evaluated concurrently in batches instead of one request at a
# time — sequential evaluation of the full candidate set was the main cause of 1+ minute
# route generation. Batches (rather than one big gather) keep a bound on concurrent load
# against the public OSRM instance and still allow an early exit once a good match is found.
# Point-to-point requests build up to ~96 candidates (see _build_detour_candidate_point_sets)
# and, when the direct route doesn't hit tolerance, can run this search twice (once raw, once
# with snapped midpoints) — at the old batch size of 8 that's ~24 sequential network round
# trips, each allowed up to OSRM_TIMEOUT's 8s read timeout, which is what drove point-to-point
# generation past a minute even though loop routes (a different, GraphHopper-only code path)
# stayed fast. Raising this cuts sequential rounds ~3x; the hard budget below bounds the rest.
CANDIDATE_BATCH_SIZE = 24

# Hard ceiling on the whole detour-candidate search in _request_osrm_distance_constrained_route
# (both the raw and snapped-midpoint passes combined). Once exceeded, remaining batches/passes
# are skipped and whichever candidate is already best gets used — same minimum-length
# correctness check as the normal path (_route_meets_target_length), just bounded latency
# instead of exhaustively working through every candidate.
OSRM_DETOUR_SEARCH_BUDGET_S = 10.0

# How many distinct route alternatives to hand back to the app when the routing engine
# has more than one valid candidate on hand (GraphHopper's alternative-route / round-trip
# seeds naturally produce several — we were previously discarding all but the single best).
NUM_ROUTE_OPTIONS = 5

OPEN_ELEVATION_URL = "https://api.open-elevation.com/api/v1/lookup"
OPEN_ELEVATION_BATCH = 100
# This public instance is well known to be slow/unreliable, and routes with several hundred
# points need multiple batches. Fetching batches one-at-a-time (previously a sequential for
# loop) meant total elevation-enrichment time was the SUM of every batch's latency — for a
# route needing 5-9 batches at up to 12s each, that alone accounted for 60+ second route
# generation. Batches now fire concurrently, and the whole step is hard-capped so a slow or
# unresponsive public API can never stall route generation — elevation is a nice-to-have,
# not worth blocking the response for.
OPEN_ELEVATION_BATCH_TIMEOUT = httpx.Timeout(connect=3.0, read=6.0, write=3.0, pool=3.0)
OPEN_ELEVATION_TOTAL_BUDGET_S = 5.0

# The public OSRM demo instance (routing.openstreetmap.de) has no uptime guarantee and is
# occasionally down outright. A flat httpx timeout doesn't reliably bound how long a dead
# TCP endpoint takes to fail in every environment — the connect phase specifically can hang
# well past the nominal timeout. Splitting it out with a short, explicit connect deadline
# makes an unreachable server fail fast and predictably instead of stalling every request
# that touches it.
OSRM_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=5.0)

# Route generation fires many concurrent requests to a handful of hosts (GraphHopper, the
# OSRM public instance, Open-Elevation, Overpass) — a single detour search alone evaluates
# candidates in batches of up to CANDIDATE_BATCH_SIZE at once. httpx.AsyncClient() is not
# free to construct: it builds a TLS context and a connection pool, and measured on real
# hosts that setup can itself take hundreds of milliseconds (worse on Windows, where the
# stdlib's default SSL context pulls from the OS certificate store). Every call site in this
# module used to open a brand-new client per request, so a batch of N concurrent requests
# paid that construction cost N times over before any network I/O even started — on top of
# losing connection pooling / TLS session reuse across requests to the same host, which
# matters even more once real network latency is added on top. A single shared, lazily
# created client removes both costs; per-call timeouts are still passed explicitly to
# `.get()`/`.post()` so each site keeps its own timeout behavior.
_shared_http_client: httpx.AsyncClient | None = None
_shared_http_client_lock = asyncio.Lock()


async def _get_shared_http_client() -> httpx.AsyncClient:
    global _shared_http_client
    if _shared_http_client is None or _shared_http_client.is_closed:
        async with _shared_http_client_lock:
            if _shared_http_client is None or _shared_http_client.is_closed:
                _shared_http_client = httpx.AsyncClient()
    return _shared_http_client


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
    that cross). Adjacent segments sharing a vertex are ignored — including the first
    and last segments of a closed loop route, which always share the closure vertex
    (first point == last point, by construction) and must not be flagged as crossing
    just because a round trip returns to its starting point.
    """
    pts = _coords_for_self_intersection_test(coords)
    n = len(pts)
    if n < 4:
        return False
    is_closed_loop = (
        abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9
    )
    for i in range(n - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        for j in range(i + 2, n - 1):
            if is_closed_loop and i == 0 and j == n - 2:
                continue
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

    # Only bail out for a genuinely degenerate (near-zero-length) segment, where the
    # perpendicular direction is undefined and dividing by segment_length_km below would
    # blow up. This function is only ever reached for real point-to-point requests — a
    # round-trip request (start == end exactly) is routed to the separate loop-generation
    # path before candidate building — so start and end are always distinct here, but they
    # can legitimately be very close (a user tapping two nearby points on a map). The
    # previous 0.05 km (50 m) cutoff silently dropped the offset entirely for any such pair,
    # collapsing every detour candidate onto the direct start-end line and making it
    # structurally impossible to stretch a route to any target distance for closely-spaced
    # pins — regardless of how large perpendicular_offset_km was supposed to be.
    if segment_length_km < 0.001:
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

    # This is the hottest OSRM call site — every candidate route, both point-to-point and
    # loop fallback, goes through it — so a short, explicit connect timeout matters most
    # here (see OSRM_TIMEOUT). The public instance both refuses connections outright under
    # load (httpx.ConnectError) and, just as often in practice, accepts the TCP handshake
    # too slowly to beat OSRM_TIMEOUT's connect deadline (httpx.ConnectTimeout — a sibling
    # exception, NOT a subclass of ConnectError, so it needs its own except arm). One quick
    # retry absorbs either without letting it escape uncaught and turn into a 500 for the
    # whole route request.
    client = await _get_shared_http_client()
    try:
        response = await client.get(url, params=params, timeout=OSRM_TIMEOUT)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        await asyncio.sleep(0.5)
        response = await client.get(url, params=params, timeout=OSRM_TIMEOUT)
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
        client = await _get_shared_http_client()
        response = await client.get(url, params=params, timeout=OSRM_TIMEOUT)
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
        client = await _get_shared_http_client()
        resp = await client.get(url, params=params, timeout=OSRM_TIMEOUT)
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
    batch_size: int = CANDIDATE_BATCH_SIZE,
) -> list[tuple[float, float] | None]:
    """
    Snap each candidate waypoint to the nearest routable edge; return None if the snap
    moved the point too far (likely wrong road / far side of a block). Callers must
    drop None entries instead of routing through raw offset coordinates.

    `batch_size` bounds how many snap requests run concurrently per wave — callers on a
    hot path (many requests per user session) should keep the conservative default;
    callers that only run as an occasional fallback can pass a larger value (e.g. the
    full point count) to trade a bigger burst for lower end-to-end latency.
    """
    if not points:
        return []

    async def snap_one(point: tuple[float, float]) -> tuple[float, float] | None:
        lat, lng = point
        s_lat, s_lng = await _snap_to_nearest_walkable_node(lat, lng, terrain_pref)
        dist_m = _haversine_distance_km(lat, lng, s_lat, s_lng) * 1000.0
        if dist_m > MIDPOINT_MAX_SNAP_DRIFT_M:
            return None
        return (s_lat, s_lng)

    out: list[tuple[float, float] | None] = []
    step = max(1, batch_size)
    for start in range(0, len(points), step):
        batch = points[start : start + step]
        out.extend(await asyncio.gather(*(snap_one(p) for p in batch)))
    return out


def _polyline_has_point_elevation(coords: list[dict]) -> bool:
    return any(c.get("elevation_m") is not None for c in coords)


async def _fetch_open_elevation_batch(
    client: httpx.AsyncClient, coords: list[dict], start: int
) -> tuple[int, list[dict]] | None:
    chunk = coords[start : start + OPEN_ELEVATION_BATCH]
    locations = [
        {"latitude": float(c["latitude"]), "longitude": float(c["longitude"])} for c in chunk
    ]
    try:
        resp = await client.post(
            OPEN_ELEVATION_URL, json={"locations": locations}, timeout=OPEN_ELEVATION_BATCH_TIMEOUT
        )
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    results = (resp.json() or {}).get("results") or []
    return start, results


async def _enrich_elevation_open_elevation(coords: list[dict]) -> list[dict]:
    """Fill elevation_m on coordinates using Open-Elevation (batch POST, run concurrently
    and hard-capped — see OPEN_ELEVATION_TOTAL_BUDGET_S)."""
    if not coords:
        return coords
    out = [dict(c) for c in coords]
    try:
        client = await _get_shared_http_client()
        batch_results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    _fetch_open_elevation_batch(client, out, start)
                    for start in range(0, len(out), OPEN_ELEVATION_BATCH)
                )
            ),
            timeout=OPEN_ELEVATION_TOTAL_BUDGET_S,
        )
    except Exception:
        return coords

    for batch in batch_results:
        if batch is None:
            continue
        start, results = batch
        for j, r in enumerate(results):
            idx = start + j
            if idx >= len(out):
                break
            ele = r.get("elevation")
            if isinstance(ele, (int, float)):
                out[idx]["elevation_m"] = float(ele)
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
    try:
        direct_route = await _request_osrm_route(payload)
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        # Every create_route call site that reaches this function either already only
        # catches HTTPException (the GraphHopper-failed and route-too-short fallbacks) or
        # catches nothing at all (the no-GraphHopper-key path) — a raw httpx exception here
        # previously escaped uncaught and surfaced to the client as an unhandled 500.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Routing service is temporarily unreachable. Please try again in a moment.",
        ) from exc
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

        def candidate_points_for(raw_candidate: list[str]) -> list[str]:
            if snap_mids and snap_map:
                points = [raw_candidate[0]]
                for pt in raw_candidate[1:-1]:
                    if pt in snap_map:
                        points.append(snap_map[pt])
                points.append(raw_candidate[-1])
                return points
            return list(raw_candidate)

        async def evaluate_one(raw_candidate: list[str]) -> dict | None:
            try:
                return await _request_osrm_route_for_points(
                    candidate_points_for(raw_candidate), terrain_pref
                )
            except (httpx.RequestError, httpx.HTTPStatusError, HTTPException):
                return None

        for start in range(0, len(raw_candidates), CANDIDATE_BATCH_SIZE):
            batch = raw_candidates[start : start + CANDIDATE_BATCH_SIZE]
            batch_results = await asyncio.gather(*(evaluate_one(c) for c in batch))

            for candidate_route in batch_results:
                if candidate_route is None:
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

            if best_route is not None and best_key[0] == 0 and best_key[1] <= tol:
                return

    async def _run_detour_search() -> None:
        await evaluate_snap_mode(False)
        if best_route is None or not _route_meets_target_length(best_route["distance_km"], target_km):
            await evaluate_snap_mode(True)

    try:
        # Hard cap on the whole search, not just a per-batch timeout: a batch that's merely
        # slow (rather than failing outright) still counts toward OSRM_TIMEOUT's read timeout,
        # so without this the two-pass loop above could still run for minutes. best_route/
        # best_key are updated incrementally as each batch completes (nonlocal), so whatever
        # was found before the deadline survives cancellation — we just stop searching for
        # something better instead of returning nothing.
        await asyncio.wait_for(_run_detour_search(), timeout=OSRM_DETOUR_SEARCH_BUDGET_S)
    except asyncio.TimeoutError:
        pass

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

    client = await _get_shared_http_client()
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
) -> list[dict]:
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

    client = await _get_shared_http_client()
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

    ranked_routes = sorted(
        clean_routes,
        key=lambda route: abs(route["distance_km"] - target_km) + (_route_backtrack_penalty(route["map_data"]) * 0.08),
    )

    if ranked_routes[0]["distance_km"] >= target_km - strict_tolerance_km:
        num_routes = getattr(payload, "num_routes", None) or NUM_ROUTE_OPTIONS
        return ranked_routes[:num_routes]

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="GRAPHOPPER_ROUTE_TOO_SHORT",
    )


# Concurrency + time budget for the GraphHopper-backed point-to-point detour search
# (_request_graphhopper_detour_route). GraphHopper is a reliably hosted, paid API — unlike
# the public OSRM demo instance (routing.openstreetmap.de) used for the OSRM candidate
# search, which has no uptime guarantee and is what actually made most short point-to-point
# requests fail or hang: GraphHopper's native alternative_route rarely stretches far past
# the direct distance between two pins, so anything more than a small detour used to fall
# straight through to OSRM. Batching here mirrors CANDIDATE_BATCH_SIZE; the budget is a
# safety net, not the expected case, since GraphHopper itself is fast and reliable.
GRAPHHOPPER_DETOUR_BATCH_SIZE = 24
GRAPHHOPPER_DETOUR_SEARCH_BUDGET_S = 12.0


async def _request_graphhopper_detour_route(
    payload: RouteCreate,
    gh_profile: str,
    direct_route_distance_km: float,
) -> dict:
    """
    GraphHopper-backed detour search for point-to-point routes: stretches a route between
    two pins out to the requested distance by routing through synthetic offset waypoints —
    the same candidate geometry _request_osrm_distance_constrained_route uses for its OSRM
    search (_build_detour_candidate_point_sets), evaluated against GraphHopper's own routing
    API instead of the flaky public OSRM demo instance.

    This is the tier that makes short point-to-point requests (e.g. "1 km between these two
    nearby pins") reliable: GraphHopper's native alternative_route (tried before this, see
    _request_graphhopper_distance_constrained_route) rarely finds an alternative that
    stretches far past the direct route, so it fails that case constantly. Previously the
    only way to stretch a route out to a target distance was OSRM — giving point-to-point
    routes the same kind of GraphHopper-only redundancy loop routes already have via
    _request_graphhopper_waypoint_loop_route, before ever depending on OSRM.
    """
    target_km = float(payload.distance_km)
    tol = _distance_tolerance_km(target_km)
    raw_candidates = _build_detour_candidate_point_sets(payload, direct_route_distance_km)

    best_route: Optional[dict] = None
    best_key: tuple = (9, 0.0, 0.0, 0.0)

    async def evaluate_one(raw_candidate: list[str]) -> dict | None:
        try:
            return await _request_graphhopper_route_for_points(raw_candidate, payload, gh_profile)
        except (httpx.RequestError, httpx.HTTPStatusError, HTTPException):
            return None

    async def _run_search() -> None:
        nonlocal best_route, best_key
        for start in range(0, len(raw_candidates), GRAPHHOPPER_DETOUR_BATCH_SIZE):
            batch = raw_candidates[start : start + GRAPHHOPPER_DETOUR_BATCH_SIZE]
            batch_results = await asyncio.gather(*(evaluate_one(c) for c in batch))

            for candidate_route in batch_results:
                if candidate_route is None:
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

            if best_route is not None and best_key[0] == 0 and best_key[1] <= tol:
                return

    try:
        await asyncio.wait_for(_run_search(), timeout=GRAPHHOPPER_DETOUR_SEARCH_BUDGET_S)
    except asyncio.TimeoutError:
        pass

    if best_route is None or not _route_meets_target_length(best_route["distance_km"], target_km):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GRAPHOPPER_DETOUR_TOO_SHORT",
        )

    return best_route


async def _request_graphhopper_loop_route(
    payload: RouteCreate,
    gh_profile: str,
    start_pt: str,
) -> list[dict]:
    """GraphHopper's native round_trip algorithm — the fast, primary path for loops.
    Fires 5 seeded requests concurrently and ranks whatever comes back by closeness to
    the target distance; OSRM is only tried if every seed fails (see generate_loop_route)."""
    url = "https://graphhopper.com/api/1/route"
    target_km = float(payload.distance_km)

    seeds = [int(random() * 1000000) for _ in range(5)]

    async def request_seed(client: httpx.AsyncClient, seed: int) -> dict | None:
        # No custom_model/ch.disable here — round_trip doesn't use a custom model, and
        # ch.disable ("flexible mode") is rejected outright on free-tier GraphHopper keys
        # ("Free packages cannot use flexible mode"), which used to make every single seed
        # fail every time, silently forcing every loop request onto the slower OSRM fallback.
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
            return None

        data = response.json()
        paths = data.get("paths") or []
        if not paths:
            return None

        # No self-intersection veto here (unlike our own synthetic offset-point candidates
        # below): GraphHopper's round_trip algorithm is a purpose-built, professionally
        # maintained routing engine, not a naive geometric heuristic. In a real street grid
        # a walking/running loop legitimately crossing its own path — e.g. using the same
        # crosswalk twice — is completely normal, not a routing defect. Rejecting on that
        # basis was discarding good, real routes and forcing every loop request onto the
        # slower fallback tiers for no reason.
        return _route_dict_from_graphhopper_path(paths[0])

    client = await _get_shared_http_client()
    candidates = await asyncio.gather(*(request_seed(client, seed) for seed in seeds))

    valid_candidates = [c for c in candidates if c is not None]
    if not valid_candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not generate a round-trip route for this location. Please try another nearby start point.",
        )

    # Best-effort: return the closest candidates even if none landed within strict
    # tolerance (matches the previous single-route fallback behavior).
    ranked_candidates = sorted(valid_candidates, key=lambda c: abs(c["distance_km"] - target_km))
    num_routes = getattr(payload, "num_routes", None) or NUM_ROUTE_OPTIONS
    return ranked_candidates[:num_routes]


async def generate_loop_route(
    payload: RouteCreate,
    gh_profile: str,
    start_pt: str,
) -> list[dict]:
    """Single entry point for loop/round-trip route generation: a start point + target
    distance in, a ranked list of routes that start and end at that same point out.
    Three tiers, each only tried if the previous one fails:

    1. GraphHopper's native round_trip algorithm — 5 seeds fired concurrently, normally
       fast (a couple of seconds). The common case; nothing past here runs if it succeeds.
    2. GraphHopper's ordinary multi-point routing, walked through offset waypoints back to
       start — doesn't need round_trip support at all, so it survives even if GraphHopper's
       round_trip algorithm specifically can't find anything for this point/distance. Tried
       before OSRM because it's the same, confirmed-reachable provider as tier 1.
    3. OSRM's candidate search — a completely different engine, tried last: it depends on
       a public demo instance with no uptime guarantee (routing.openstreetmap.de), which is
       occasionally down outright, so putting it last avoids paying for its full timeout
       chain on every request when the first two tiers — both on a provider already known
       to be reachable — are far more likely to succeed.
    """
    if not GRAPHHOPPER_API_KEY:
        return await _request_osrm_round_trip_route(payload)

    fallback_error_detail: Optional[str] = None
    try:
        return await _request_graphhopper_loop_route(payload, gh_profile, start_pt)
    except HTTPException as exc:
        fallback_error_detail = str(exc.detail)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Round-trip route generation requires a valid GraphHopper API key.",
            ) from exc
        fallback_error_detail = _extract_graphhopper_error_detail(exc)
    except httpx.RequestError as exc:
        fallback_error_detail = f"Error connecting to GraphHopper API: {str(exc)}"

    try:
        return await _request_graphhopper_waypoint_loop_route(payload, gh_profile, start_pt)
    except HTTPException as wp_exc:
        fallback_error_detail = f"{fallback_error_detail}. {wp_exc.detail}"

    try:
        return await _request_osrm_round_trip_route(payload)
    except HTTPException as osrm_exc:
        raise HTTPException(
            status_code=osrm_exc.status_code,
            detail=f"{fallback_error_detail}. OSRM fallback also failed: {osrm_exc.detail}",
        ) from osrm_exc


def _offset_origin_point(lat: float, lng: float, north_km: float, east_km: float) -> tuple[float, float]:
    offset_lat = lat + (north_km / 111.32)
    lng_scale = max(111.32 * math.cos(math.radians(lat)), 0.0001)
    offset_lng = lng + (east_km / lng_scale)
    return offset_lat, offset_lng


async def _request_graphhopper_waypoint_loop_route(
    payload: RouteCreate,
    gh_profile: str,
    start_pt: str,
) -> list[dict]:
    """Last-resort loop strategy, tried only if both GraphHopper's round_trip algorithm
    and the OSRM candidate search fail (e.g. the public OSRM demo instance being down,
    which has no uptime guarantee). Routes through offset waypoints and back to start
    using GraphHopper's ordinary multi-point routing — the same request shape as
    point-to-point routes, which already retries without custom_model/ch.disable on a
    free-tier "flexible mode" rejection (see _request_graphhopper_route_for_points), so
    it doesn't depend on round_trip support or any third-party service beyond GraphHopper
    itself, which is otherwise confirmed reachable at this point in the fallback chain.
    """
    start_lat = float(payload.start_lat)
    start_lng = float(payload.start_lng)
    target_km = float(payload.distance_km)

    orientation_vectors = [
        (1.0, 0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0, -1.0),
        (0.0, 1.0, -1.0, 0.0),
        (0.0, -1.0, 1.0, 0.0),
    ]
    scales = (0.22, 0.32, 0.45, 0.6, 0.78)

    candidate_point_sets: list[list[str]] = []
    for scale in scales:
        radius_km = max(target_km * scale, 0.15)
        for n1, e1, n2, e2 in orientation_vectors:
            p1 = _offset_origin_point(start_lat, start_lng, n1 * radius_km, e1 * radius_km)
            p2 = _offset_origin_point(start_lat, start_lng, n2 * radius_km, e2 * radius_km)
            candidate_point_sets.append([start_pt, _format_point(*p1), _format_point(*p2), start_pt])

    async def evaluate_one(points: list[str]) -> dict | None:
        try:
            return await _request_graphhopper_route_for_points(points, payload, gh_profile)
        except (httpx.RequestError, httpx.HTTPStatusError, HTTPException):
            return None

    results = await asyncio.gather(*(evaluate_one(pts) for pts in candidate_point_sets))

    ranked = sorted(
        (r for r in results if r is not None),
        key=lambda r: abs(r["distance_km"] - target_km),
    )
    if not ranked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Could not generate a round-trip close to {round(target_km, 2)} km for this point. "
                "Try a slightly larger target distance or a nearby start point."
            ),
        )

    num_routes = getattr(payload, "num_routes", None) or NUM_ROUTE_OPTIONS
    return ranked[:num_routes]


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
        client = await _get_shared_http_client()
        resp = await client.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=11.0,
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


async def _request_osrm_round_trip_route(payload: RouteCreate) -> list[dict]:
    """OSRM loop fallback — only reached when GraphHopper's round_trip algorithm fails or
    is unavailable, so every candidate is snapped and routed in a single concurrent wave
    rather than the sequential batching used for the much more frequent point-to-point
    path. Returns candidates ranked closest-to-target first."""
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

    # Snap midpoints with drift rejection (avoids OSRM legs that chord across blocks) —
    # one wave for all of them.
    snapped_mids = await _snap_detour_midpoints_for_osrm(
        all_mid_points, terrain_pref, batch_size=len(all_mid_points)
    )

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

    async def evaluate_one(candidate_points: list[str]) -> dict | None:
        try:
            return await _request_osrm_route_for_points(candidate_points, terrain_pref)
        except (httpx.RequestError, httpx.HTTPStatusError, HTTPException):
            return None

    results = await asyncio.gather(*(evaluate_one(c) for c in candidates_snapped))

    clean: list[tuple[float, dict]] = []
    intersecting: list[tuple[float, dict]] = []
    for candidate in results:
        if candidate is None:
            continue
        gap = abs(candidate["distance_km"] - target_km)
        if _polyline_self_intersects(candidate["map_data"]):
            intersecting.append((gap, candidate))
        else:
            clean.append((gap, candidate))

    within_tolerance = [pair for pair in clean if pair[0] <= tolerance_km]
    pool = within_tolerance or [pair for pair in clean if pair[0] <= max(2.0, target_km * 0.45)]

    if pool:
        pool.sort(key=lambda pair: pair[0])
        num_routes = getattr(payload, "num_routes", None) or NUM_ROUTE_OPTIONS
        return [route for _, route in pool[:num_routes]]

    if intersecting:
        intersecting.sort(key=lambda pair: pair[0])
        return [intersecting[0][1]]

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


async def _finalize_route_options(routes: list[dict]) -> list[dict]:
    """Finalize a batch of route candidates concurrently (recompute distance/elevation
    from the already-decided polyline; _finalize_route_geometry never changes lat/lng).

    Deliberately does NOT re-check self-intersection here. Every candidate source that
    needs that check already applies it at generation time (point-to-point GraphHopper/OSRM,
    and our own synthetic offset-point loop candidates) — re-checking here was pure
    redundancy for those. For GraphHopper's native round_trip results specifically, no
    source-level check is applied at all, intentionally: a real walking/running loop
    legitimately crossing its own path (e.g. the same crosswalk twice) is normal in a real
    street grid, not a routing defect, and rejecting on that basis was discarding good
    routes and forcing every loop request onto much slower fallback tiers for no reason.
    """
    return list(await asyncio.gather(*(_finalize_route_geometry(r) for r in routes)))


async def generate_point_to_point_route(
    payload: RouteCreate,
    gh_profile: str,
    start_pt: str,
    end_pt: str,
) -> list[dict]:
    """Single entry point for point-to-point route generation: a start pin, an end pin, and
    a target distance in, a ranked list of routes between them out. Three tiers, each only
    tried if the previous one can't reach the target distance — mirrors the fallback design
    in generate_loop_route:

    1. GraphHopper's native alternative_route algorithm
       (_request_graphhopper_distance_constrained_route) — up to 8 real alternatives from
       GraphHopper's own engine in a single request. Succeeds whenever the requested
       distance is reasonably close to the direct distance between the pins.
    2. GraphHopper's ordinary multi-point routing walked through synthetic offset waypoints
       between start and end (_request_graphhopper_detour_route) — the same detour-candidate
       geometry the OSRM tier below uses, evaluated against GraphHopper instead. This is the
       tier that makes short requests (e.g. "1 km between these two nearby pins") reliable:
       tier 1 rarely stretches far past the direct route, so it fails that case constantly.
       Previously the *only* way to stretch a route out to a target distance was OSRM (tier
       3) — a public demo instance with no uptime guarantee, which made it the single
       biggest source of point-to-point failures and multi-minute hangs even for short,
       easy-looking requests. Routing the same detour geometry through GraphHopper first
       gives point-to-point the same GraphHopper-only redundancy loop routes already have
       (see _request_graphhopper_waypoint_loop_route) before ever depending on OSRM.
    3. OSRM's candidate search (_request_osrm_distance_constrained_route) — tried last, only
       when GraphHopper isn't configured or every GraphHopper tier fails outright.
    """
    if not GRAPHHOPPER_API_KEY:
        return [await _request_osrm_distance_constrained_route(payload)]

    fallback_error_detail: Optional[str] = None
    try:
        return await _request_graphhopper_distance_constrained_route(payload, gh_profile, start_pt, end_pt)
    except HTTPException as exc:
        fallback_error_detail = str(exc.detail)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Route generation requires a valid GraphHopper API key.",
            ) from exc
        fallback_error_detail = _extract_graphhopper_error_detail(exc)
    except httpx.RequestError as exc:
        fallback_error_detail = f"Error connecting to GraphHopper API: {str(exc)}"

    # The detour search only needs a rough baseline distance to size its offset candidates
    # (see _build_detour_candidate_point_sets) — it tries many scales, so precision here
    # isn't critical. A failure of just this baseline lookup (network blip, self-intersect
    # on a degenerate 2-point path, etc.) shouldn't cost us the whole GraphHopper detour
    # tier; fall back to the straight-line geo distance and still attempt it.
    try:
        direct_route = await _request_graphhopper_route_for_points([start_pt, end_pt], payload, gh_profile)
        direct_route_distance_km = direct_route["distance_km"]
    except (httpx.RequestError, httpx.HTTPStatusError, HTTPException):
        direct_route_distance_km = _haversine_distance_km(
            payload.start_lat, payload.start_lng, payload.end_lat, payload.end_lng
        )

    try:
        best = await _request_graphhopper_detour_route(payload, gh_profile, direct_route_distance_km)
        return [best]
    except HTTPException as detour_exc:
        fallback_error_detail = f"{fallback_error_detail}. {detour_exc.detail}"
    except httpx.RequestError as exc:
        fallback_error_detail = f"{fallback_error_detail}. GraphHopper detour search failed: {str(exc)}"
    except httpx.HTTPStatusError as exc:
        fallback_error_detail = (
            f"{fallback_error_detail}. GraphHopper detour search failed: {_extract_graphhopper_error_detail(exc)}"
        )

    # Every GraphHopper tier failed (or GraphHopper itself errored) — OSRM is the last
    # resort, not the primary strategy, precisely because it depends on a public demo
    # instance with no uptime guarantee.
    try:
        osrm_result = await _request_osrm_distance_constrained_route(payload)
        return [osrm_result]
    except HTTPException as osrm_exc:
        raise HTTPException(
            status_code=osrm_exc.status_code,
            detail=f"{fallback_error_detail}. OSRM fallback also failed: {osrm_exc.detail}",
        ) from osrm_exc


async def create_route(payload: RouteCreate, creator: User) -> list[dict]:
    if not creator or not creator.uid:
        raise HTTPException(status_code=401, detail="User not authenticated")

    start_lat, start_lng, end_lat, end_lng = _normalize_route_coordinates(payload)
    terrain_pref = getattr(payload, "terrain", None)
    is_round_trip_request = (start_lat, start_lng) == (end_lat, end_lng)
    if is_round_trip_request:
        start_lat, start_lng = await _snap_to_nearest_walkable_node(start_lat, start_lng, terrain_pref)
        end_lat, end_lng = start_lat, start_lng
    else:
        (start_lat, start_lng), (end_lat, end_lng) = await asyncio.gather(
            _snap_to_nearest_walkable_node(start_lat, start_lng, terrain_pref),
            _snap_to_nearest_walkable_node(end_lat, end_lng, terrain_pref),
        )
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

    if is_round_trip_request:
        # Dedicated loop path — GraphHopper's round_trip algorithm first (fast, parallel
        # seeds), OSRM candidate search only as a fallback. See generate_loop_route.
        loop_results = await generate_loop_route(normalized_payload, gh_profile, start_pt)
        return await _finalize_route_options(loop_results)

    # Dedicated point-to-point path — GraphHopper's native alternative_route first, then a
    # GraphHopper-backed detour search, OSRM candidate search only as a last resort. See
    # generate_point_to_point_route.
    p2p_results = await generate_point_to_point_route(normalized_payload, gh_profile, start_pt, end_pt)
    return await _finalize_route_options(p2p_results)


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
