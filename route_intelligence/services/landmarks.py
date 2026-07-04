"""
Trip-aware POI / landmark finder — fast Overpass client.

The old implementation issued one Overpass request PER (sample-point ×
category) — 5 points × 4 categories = 20 sequential requests, each with a
1-second courtesy sleep and a 25 s server-side timeout. Worst case was
minutes of "Querying Overpass…" with nothing to show.

This version:
  * ONE request per trip — Overpass's ``around`` filter accepts a whole
    polyline (``around:R,lat1,lng1,lat2,lng2,…``), so we send the sampled
    route once with every category tag union'd into a single query.
  * Hard client timeouts (5 s connect / 15 s read) and automatic fallback
    across three public mirrors.
  * Results cached per (trip, radius, categories) in ``ri_poi_cache`` with a
    30-day TTL, including a sentinel row for empty results so an empty
    corridor doesn't re-query on every open.
  * Never raises for network trouble — returns ``{"landmarks": [], "error":
    "…"}`` so the UI can render a retry affordance instead of hanging.

YAML (``config/route_intel.yaml``) drives defaults:

    external.overpass.default_radius_m
    external.overpass.timeout_s          (server-side [timeout:N], default 10)
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy import text

from route_intelligence import config as ricfg
from route_intelligence import db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category registry — OSM tag → UI label/icon. Mirrors the legacy
# LandmarkFinder.POI_CATEGORIES keys so old callers keep working.
# ---------------------------------------------------------------------------
POI_CATEGORIES: Dict[str, Dict[str, str]] = {
    "fuel_stations": {"key": "amenity", "value": "fuel",       "icon": "⛽", "label": "Fuel Station"},
    "restaurants":   {"key": "amenity", "value": "restaurant", "icon": "🍽️", "label": "Restaurant"},
    "hotels":        {"key": "tourism", "value": "hotel",      "icon": "🏨", "label": "Hotel"},
    "parking":       {"key": "amenity", "value": "parking",    "icon": "🅿️", "label": "Parking"},
    "rest_areas":    {"key": "highway", "value": "rest_area",  "icon": "🛑", "label": "Rest Area"},
    "hospitals":     {"key": "amenity", "value": "hospital",   "icon": "🏥", "label": "Hospital"},
    "police":        {"key": "amenity", "value": "police",     "icon": "👮", "label": "Police Station"},
    "workshops":     {"key": "shop",    "value": "car_repair", "icon": "🔧", "label": "Workshop"},
}

# POIs of these categories are useful even without an OSM name; everything
# else unnamed ("Unnamed" dhaba #37) is noise and gets dropped.
_KEEP_UNNAMED = {"fuel_stations", "hospitals", "rest_areas", "parking"}

_DEFAULT_CATEGORIES = ["fuel_stations", "rest_areas", "restaurants", "hospitals"]

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

_HTTP_TIMEOUT: Tuple[int, int] = (5, 15)   # (connect, read) seconds per mirror
_CACHE_TTL = timedelta(days=30)
_MAX_RESULTS = 250
_EMPTY_SENTINEL = "__empty__"

_UA = {"User-Agent": "nextGen-FMS/0.2 (route-intelligence; contact: ops@nextgen-fms.local)"}


def _overpass_cfg() -> Dict[str, Any]:
    return dict((ricfg.section("external") or {}).get("overpass") or {})


def _default_radius_m() -> int:
    try:
        return int(_overpass_cfg().get("default_radius_m", 1500))
    except (TypeError, ValueError):
        return 1500


def _server_timeout_s() -> int:
    try:
        return max(5, min(int(_overpass_cfg().get("timeout_s", 10)), 25))
    except (TypeError, ValueError):
        return 10


def _normalize_categories(categories: Optional[List[str]]) -> List[str]:
    cats = [c for c in (categories or _DEFAULT_CATEGORIES) if c in POI_CATEGORIES]
    return cats or _DEFAULT_CATEGORIES


# ---------------------------------------------------------------------------
# Overpass query — one HTTP request for the whole trip.
#
# NOTE we deliberately query small discs around each sampled point rather than
# a single polyline corridor: `around` with a 300 km linestring makes Overpass
# scan a giant band and it times out SILENTLY (HTTP 200 + "remark": "runtime
# error: Query timed out…" + zero elements). N tiny discs in one union are
# cheap and mirror the "POIs near the route" semantics we want.
# ---------------------------------------------------------------------------
def _build_query(points: List[Tuple[float, float]], radius_m: int,
                 categories: List[str]) -> str:
    # group category values by OSM tag key → one regex match per (key, point)
    by_key: Dict[str, List[str]] = {}
    for cat in categories:
        spec = POI_CATEGORIES[cat]
        by_key.setdefault(spec["key"], []).append(spec["value"])

    parts: List[str] = []
    for lat, lng in points:
        at = f"(around:{radius_m},{lat:.5f},{lng:.5f});"
        for key, values in by_key.items():
            selector = (f'["{key}"="{values[0]}"]' if len(values) == 1
                        else f'["{key}"~"^({"|".join(values)})$"]')
            parts.append(f"node{selector}{at}")
            parts.append(f"way{selector}{at}")
    return (
        f"[out:json][timeout:{_server_timeout_s()}];"
        f"({''.join(parts)});out center {_MAX_RESULTS};"
    )


def _ask_mirror(url: str, query: str) -> Tuple[str, Optional[List[dict]], Optional[str]]:
    host = url.split("/")[2]
    try:
        resp = requests.post(url, data={"data": query},
                             headers=_UA, timeout=_HTTP_TIMEOUT)
        if resp.status_code != 200:
            return host, None, f"{host}: HTTP {resp.status_code}"
        payload = resp.json()
        # Overpass reports mid-query timeouts as HTTP 200 + a "remark" and an
        # empty element list — that is a FAILURE, not an empty result, and
        # must never be cached as "no POIs here".
        remark = (payload.get("remark") or "")
        if "error" in remark.lower():
            return host, None, f"{host}: {remark.strip()}"
        return host, (payload.get("elements") or []), None
    except requests.exceptions.Timeout:
        return host, None, f"{host}: timed out"
    except Exception as exc:  # noqa: BLE001 — mirror down, DNS, bad JSON…
        return host, None, f"{host}: {type(exc).__name__}"


def _fetch_overpass(query: str) -> Tuple[Optional[List[dict]], Optional[str]]:
    """Race all mirrors in parallel. First NON-EMPTY success wins; an empty
    success is only trusted once no other mirror produced data (guards against
    stale or partially-synced mirrors answering fast with nothing). Public
    mirrors are individually flaky (504s, 20 s stalls), so a sequential
    fallback chain used to cost 30 s+ — the race bounds wall time to one
    mirror's timeout (~15 s worst case, typically 2-6 s)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    errors: List[str] = []
    empty_success = False
    with ThreadPoolExecutor(max_workers=len(OVERPASS_MIRRORS)) as pool:
        futures = [pool.submit(_ask_mirror, url, query) for url in OVERPASS_MIRRORS]
        for fut in as_completed(futures):
            host, elements, err = fut.result()
            if elements:
                logger.info("landmarks: answered by %s (%d elements)", host, len(elements))
                return elements, None
            if elements is not None:      # genuine 200 with zero elements
                empty_success = True
                continue
            errors.append(err)
            logger.warning("landmarks: overpass mirror failed — %s", err)
    if empty_success:
        return [], None
    return None, "; ".join(errors) or "no mirrors configured"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _elements_to_pois(elements: List[dict], route_points: List[Tuple[float, float]],
                      categories: List[str]) -> List[Dict[str, Any]]:
    """Map raw Overpass elements → POI dicts with the nearest-route distance."""
    tag_to_cat = {(POI_CATEGORIES[c]["key"], POI_CATEGORIES[c]["value"]): c
                  for c in categories}
    seen: Dict[tuple, Dict[str, Any]] = {}
    for el in elements:
        tags = el.get("tags") or {}
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        cat_key = next((c for (k, v), c in tag_to_cat.items() if tags.get(k) == v), None)
        if cat_key is None:
            continue
        name = (tags.get("name") or "").strip()
        if not name and cat_key not in _KEEP_UNNAMED:
            continue
        name = name or POI_CATEGORIES[cat_key]["label"]
        dist = min(_haversine_km(float(lat), float(lng), plat, plng)
                   for plat, plng in route_points)
        dedupe = (name.lower(), round(float(lat), 3), round(float(lng), 3))
        poi = {
            "name": name,
            "category": POI_CATEGORIES[cat_key]["label"],
            "category_key": cat_key,
            "icon": POI_CATEGORIES[cat_key]["icon"],
            "lat": float(lat),
            "lng": float(lng),
            "distance_km": round(dist, 3),
        }
        if dedupe not in seen or poi["distance_km"] < seen[dedupe]["distance_km"]:
            seen[dedupe] = poi
    return sorted(seen.values(), key=lambda p: p["distance_km"])


# ---------------------------------------------------------------------------
# ri_poi_cache — one bundle of rows per (trip, radius, categories) key
# ---------------------------------------------------------------------------
def _trip_cache_key(trip_id: int, radius_m: int, categories: List[str]) -> str:
    digest = hashlib.md5(
        json.dumps([radius_m, sorted(categories)]).encode()).hexdigest()[:16]
    return f"trip:{trip_id}:{digest}"


def _cache_read(key: str) -> Optional[List[Dict[str, Any]]]:
    """Return cached POIs (possibly []) when fresh, else None."""
    cutoff = datetime.utcnow() - _CACHE_TTL
    with db.get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT name, category, poi_lat, poi_lng, distance_km, fetched_at
            FROM ri_poi_cache WHERE cache_key = :k
        """), {"k": key}).mappings().all()
    if not rows:
        return None
    if any(r["fetched_at"] and r["fetched_at"] < cutoff for r in rows):
        return None  # stale — refetch
    icon_by_label = {v["label"]: v["icon"] for v in POI_CATEGORIES.values()}
    key_by_label = {v["label"]: k for k, v in POI_CATEGORIES.items()}
    out = []
    for r in rows:
        if r["category"] == _EMPTY_SENTINEL:
            continue
        out.append({
            "name": r["name"],
            "category": r["category"],
            "category_key": key_by_label.get(r["category"], ""),
            "icon": icon_by_label.get(r["category"], "📍"),
            "lat": float(r["poi_lat"]),
            "lng": float(r["poi_lng"]),
            "distance_km": round(float(r["distance_km"] or 0), 3),
        })
    return sorted(out, key=lambda p: p["distance_km"])


def _cache_write(key: str, anchor: Tuple[float, float],
                 pois: List[Dict[str, Any]]) -> None:
    now = datetime.utcnow()
    with db.get_engine().begin() as c:
        c.execute(text("DELETE FROM ri_poi_cache WHERE cache_key = :k"), {"k": key})
        if not pois:  # sentinel so empty corridors don't re-query for 30 days
            c.execute(text("""
                INSERT INTO ri_poi_cache
                    (cache_key, lat, lng, category, name, poi_lat, poi_lng,
                     distance_km, fetched_at)
                VALUES (:k, :la, :ln, :cat, NULL, 0, 0, 0, :ts)
            """), {"k": key, "la": anchor[0], "ln": anchor[1],
                   "cat": _EMPTY_SENTINEL, "ts": now})
            return
        for p in pois:
            c.execute(text("""
                INSERT INTO ri_poi_cache
                    (cache_key, lat, lng, category, name, poi_lat, poi_lng,
                     distance_km, fetched_at)
                VALUES (:k, :la, :ln, :cat, :nm, :pla, :pln, :d, :ts)
            """), {"k": key, "la": anchor[0], "ln": anchor[1],
                   "cat": p["category"], "nm": p["name"][:255],
                   "pla": p["lat"], "pln": p["lng"],
                   "d": p["distance_km"], "ts": now})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def pois_near(lat: float, lng: float,
              radius_m: int | None = None,
              categories: List[str] | None = None,
              use_cache: bool = True) -> List[Dict[str, Any]]:  # noqa: ARG001
    """POIs around a single point — one Overpass request for ALL categories."""
    radius_m = radius_m or _default_radius_m()
    cats = _normalize_categories(categories)
    elements, err = _fetch_overpass(_build_query([(lat, lng)], radius_m, cats))
    if elements is None:
        logger.warning("landmarks: pois_near(%s,%s) failed: %s", lat, lng, err)
        return []
    return _elements_to_pois(elements, [(lat, lng)], cats)


def _sample_indices(n_rows: int, n_samples: int) -> List[int]:
    n_samples = max(1, min(n_samples, n_rows))
    if n_samples == 1:
        return [n_rows // 2]
    step = (n_rows - 1) / (n_samples - 1)
    return [int(round(i * step)) for i in range(n_samples)]


def landmarks_for_trip(trip_id: int,
                       n_samples: int = 8,
                       radius_m: int | None = None,
                       categories: List[str] | None = None,
                       force_refresh: bool = False) -> Dict[str, Any]:
    """POIs within ``radius_m`` of the trip's polyline. Single Overpass call,
    MySQL-cached for 30 days. Network failure is reported in ``error`` —
    never raised — so the UI can offer a retry."""
    from route_intelligence import pipeline   # local import — avoid cycle
    db.bootstrap()
    trip = db.get_trip(trip_id)
    if not trip:
        raise ValueError(f"trip {trip_id} not found")

    radius_m = radius_m or _default_radius_m()
    cats = _normalize_categories(categories)

    base = {
        "trip_id": trip_id,
        "vehicle_id": trip.get("vehicle_id"),
        "from": trip.get("from_waypoint"),
        "to": trip.get("to_waypoint"),
        "radius_m": radius_m,
        "categories": cats,
    }

    key = _trip_cache_key(trip_id, radius_m, cats)
    if not force_refresh:
        cached = _cache_read(key)
        if cached is not None:
            return {**base, "landmarks": cached, "source": "cache", "error": None}

    df = pipeline._load_trip_df(trip)
    if df.empty:
        return {**base, "landmarks": [], "source": "none", "error": None}

    points = [(float(df.iloc[i]["latitude"]), float(df.iloc[i]["longitude"]))
              for i in _sample_indices(len(df), max(2, min(n_samples, 12)))]

    elements, err = _fetch_overpass(_build_query(points, radius_m, cats))
    if elements is None:
        # Serve a stale cache over nothing, if one exists.
        stale = _cache_read_stale(key)
        if stale:
            return {**base, "landmarks": stale, "source": "stale-cache", "error": err}
        return {**base, "landmarks": [], "source": "overpass", "error": err}

    pois = _elements_to_pois(elements, points, cats)
    try:
        _cache_write(key, points[0], pois)
    except Exception:  # cache is best-effort — never fail the response
        logger.exception("landmarks: cache write failed for %s", key)
    return {**base, "landmarks": pois, "source": "overpass", "error": None}


def _cache_read_stale(key: str) -> List[Dict[str, Any]]:
    """Best-effort read ignoring TTL — used when every mirror is down."""
    with db.get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT name, category, poi_lat, poi_lng, distance_km
            FROM ri_poi_cache
            WHERE cache_key = :k AND category <> :s
        """), {"k": key, "s": _EMPTY_SENTINEL}).mappings().all()
    icon_by_label = {v["label"]: v["icon"] for v in POI_CATEGORIES.values()}
    return sorted(({
        "name": r["name"],
        "category": r["category"],
        "category_key": "",
        "icon": icon_by_label.get(r["category"], "📍"),
        "lat": float(r["poi_lat"]),
        "lng": float(r["poi_lng"]),
        "distance_km": round(float(r["distance_km"] or 0), 3),
    } for r in rows), key=lambda p: p["distance_km"])
