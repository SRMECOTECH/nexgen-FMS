"""
Nearby-POI intelligence for stop events (OpenStreetMap Overpass API).

Nominatim reverse-geocoding only gives the street address at a coordinate
(e.g. "NH143D, Basia, Gumla, Jharkhand"). It does NOT tell you the *named place*
a driver actually used. This module fills that gap: for a stop coordinate it asks
Overpass for named amenities within a small radius (dhabas, hotels, fuel, cafés,
rest areas) and picks the one that best fits the reason for the stop — so a 6-hour
night halt off a highway resolves to "Hariyali Dhaba (dhaba, ~120 m off NH143D)".

Free, no API key. Shared public service, so callers MUST rate-limit and cache the
result (we persist it on dim_geofence and only hit Overpass from the explicit
"Enrich POI" action, never per page-load).
"""

from __future__ import annotations

import logging
import math
import os

logger = logging.getLogger(__name__)

OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
OVERPASS_DELAY_SEC = float(os.environ.get("OVERPASS_DELAY", "1.1"))  # be polite to the shared server
POI_RADIUS_M = int(os.environ.get("POI_RADIUS_M", "200"))            # how far around a stop to look for a named place


# ----------------------------------------------------------------------
# reason -> which POI categories make sense, in priority order
# ----------------------------------------------------------------------
# Friendly category names we expose (mapped from raw OSM tags below).
_REST_PREF = ["dhaba", "hotel", "motel", "rest area", "truck stop", "fuel station", "restaurant", "parking"]
_MEAL_PREF = ["dhaba", "restaurant", "eatery", "food court", "café"]
_TEA_PREF = ["café", "dhaba", "restaurant", "fuel station"]
_ANY_PREF = ["dhaba", "restaurant", "hotel", "café", "fuel station", "rest area", "eatery", "parking"]


def _pref_for_reason(reason: str | None) -> list[str]:
    r = (reason or "").lower()
    if "rest" in r or "long halt" in r or "extended" in r:
        return _REST_PREF
    if "lunch" in r or "dinner" in r or "meal" in r:
        return _MEAL_PREF
    if "tea" in r or "short" in r:
        return _TEA_PREF
    return _ANY_PREF


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _friendly_category(tags: dict) -> str | None:
    """Map raw OSM tags to a human category, or None if it's not a place a truck
    driver would deliberately stop at."""
    name = (tags.get("name") or "").lower()
    amenity = tags.get("amenity")
    tourism = tags.get("tourism")
    highway = tags.get("highway")
    shop = tags.get("shop")

    if "dhaba" in name or tags.get("cuisine") == "indian" and amenity in ("restaurant", "fast_food"):
        return "dhaba"
    if amenity == "restaurant":
        return "dhaba" if "dhaba" in name else "restaurant"
    if amenity in ("fast_food", "food_court"):
        return "eatery"
    if amenity == "cafe":
        return "café"
    if amenity == "fuel":
        return "fuel station"
    if amenity == "parking":
        return "parking"
    if amenity in ("truck_stop",):
        return "truck stop"
    if tourism in ("hotel",):
        return "hotel"
    if tourism in ("motel", "guest_house", "hostel"):
        return "motel"
    if highway in ("rest_area", "services"):
        return "rest area"
    if shop:
        return str(shop).replace("_", " ")
    return None


def nearest_poi(lat: float, lng: float, radius_m: int = POI_RADIUS_M,
                reason: str | None = None) -> dict | None:
    """Best-fitting *named* POI within radius_m of (lat, lng), or None.

    Returns {name, category, distance_m, lat, lng}. Ranking = category relevance
    for the stop reason first, then proximity. Unnamed features are ignored — we
    only surface places a human would recognise.
    """
    try:
        import requests
    except ImportError:
        return None

    r = int(radius_m)
    query = (
        "[out:json][timeout:25];"
        f"(node(around:{r},{lat},{lng})[amenity];"
        f" way(around:{r},{lat},{lng})[amenity];"
        f" node(around:{r},{lat},{lng})[tourism];"
        f" way(around:{r},{lat},{lng})[tourism];"
        f" node(around:{r},{lat},{lng})[shop];"
        f" node(around:{r},{lat},{lng})[highway=rest_area];);"
        "out center 40;"
    )
    try:
        resp = requests.post(
            OVERPASS_URL, data={"data": query},
            headers={"User-Agent": "neXgen-FMS/1.0 (fleet analytics; contact admin)"},
            timeout=30,
        )
        if not resp.ok:
            logger.warning("overpass: HTTP %s", resp.status_code)
            return None
        elements = (resp.json() or {}).get("elements", [])
    except Exception as exc:
        logger.warning("overpass: %s", exc)
        return None

    pref = _pref_for_reason(reason)
    best = None
    best_score = None
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue  # only named places
        cat = _friendly_category(tags)
        if cat is None:
            continue
        # element coordinate (node has lat/lon; way carries a 'center')
        elat = el.get("lat") or (el.get("center") or {}).get("lat")
        elng = el.get("lon") or (el.get("center") or {}).get("lon")
        if elat is None or elng is None:
            continue
        dist = _haversine_m(lat, lng, float(elat), float(elng))
        if dist > radius_m:
            continue
        # rank: preferred category index (lower = better) dominates, distance breaks ties
        rank = pref.index(cat) if cat in pref else len(pref)
        score = rank * 1000 + dist
        if best_score is None or score < best_score:
            best_score = score
            best = {"name": str(name)[:200], "category": cat,
                    "distance_m": round(dist), "lat": float(elat), "lng": float(elng)}
    return best


def label_for_stop(poi: dict | None, address: str | None, node_name: str | None,
                   state: str | None = None) -> str:
    """Human display label for a stop — NEVER raw coordinates.

    Priority: named POI (with how-far-off-the-road context) -> reverse-geocoded
    address -> nearest route waypoint -> a generic 'unmapped' fallback.
    """
    if poi and poi.get("name"):
        road = node_name or (address.split(",")[0] if address else None)
        d = poi.get("distance_m")
        bits = poi["name"]
        meta = poi.get("category") or "place"
        if d is not None and road:
            meta += f", ~{int(d)} m off {road}"
        elif d is not None:
            meta += f", ~{int(d)} m away"
        return f"{bits} ({meta})"
    if address:
        return address
    if node_name:
        return f"Near {node_name}"
    if state:
        return f"Unmapped stop · {state}"
    return "Unmapped stop"
