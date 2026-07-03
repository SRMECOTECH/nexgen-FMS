"""
Trip-aware POI / landmark finder.

Wraps ``legacy_viz.landmark_finder.LandmarkFinder`` (Overpass API) and caches
results in MySQL ``ri_poi_cache``. Samples a few points along the trip's
polyline and merges POIs (deduped by name + lat/lng) so the UI can show
"fuel stations / restaurants / hospitals on this trip" without re-hammering
Overpass on every page load.

YAML drives defaults (radius + categories) so they're tweakable without
touching code:

    external.overpass.default_radius_m
    external.overpass.categories
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from route_intelligence import config as ricfg
from route_intelligence import db
from route_intelligence.legacy_viz.landmark_finder import LandmarkFinder

logger = logging.getLogger(__name__)

_PRECISION = 3   # ~111 m grid for the cache key


@lru_cache(maxsize=1)
def _svc() -> LandmarkFinder:
    return LandmarkFinder()


def _cache_key(lat: float, lng: float, radius_m: int, category: str) -> str:
    return f"{round(lat, _PRECISION)}|{round(lng, _PRECISION)}|{radius_m}|{category}"


def _default_categories() -> List[str]:
    raw = list(ricfg.get("external", "categories", []) or [])
    if raw:
        return raw
    # Map OSM tag values to the legacy class's category keys.
    legacy_keys = list(LandmarkFinder.POI_CATEGORIES.keys())
    return [k for k in ("fuel_stations", "rest_areas", "restaurants", "hospitals")
            if k in legacy_keys]


def _default_radius_m() -> int:
    return int(ricfg.get("external", "default_radius_m", 1500))


def pois_near(lat: float, lng: float,
              radius_m: int | None = None,
              categories: List[str] | None = None,
              use_cache: bool = True) -> List[Dict[str, Any]]:
    """POIs within ``radius_m`` of (lat, lng), filtered by category list.
    Cached per (lat-r3, lng-r3, radius, category) in ``ri_poi_cache``."""
    db.bootstrap()
    radius_m = radius_m or _default_radius_m()
    categories = categories or _default_categories()
    results: List[Dict[str, Any]] = []

    eng = db.get_engine()

    for cat in categories:
        key = _cache_key(lat, lng, radius_m, cat)
        if use_cache:
            with eng.connect() as c:
                rows = c.execute(text("""
                    SELECT name, category, poi_lat, poi_lng, distance_km
                    FROM ri_poi_cache WHERE cache_key=:k
                """), {"k": key}).mappings().all()
            if rows:
                results.extend(_row_to_poi(r) for r in rows)
                continue

        try:
            fresh = _svc().find_nearby_pois(lat, lng, radius_meters=radius_m,
                                            categories=[cat])
        except Exception as exc:
            logger.warning("landmarks: overpass failed for %s near (%s,%s): %s",
                           cat, lat, lng, exc)
            fresh = []

        # Persist (one row per POI; empty result also gets a sentinel row so
        # we don't re-query for empty radii).
        with eng.begin() as c:
            c.execute(text("DELETE FROM ri_poi_cache WHERE cache_key=:k"), {"k": key})
            for p in fresh:
                c.execute(text("""
                    INSERT INTO ri_poi_cache
                      (cache_key, lat, lng, category, name, poi_lat, poi_lng,
                       distance_km, fetched_at)
                    VALUES (:k, :la, :ln, :cat, :nm, :pla, :pln, :d, :ts)
                """), {"k": key, "la": float(lat), "ln": float(lng),
                       "cat": p.get("category"), "nm": p.get("name"),
                       "pla": float(p["lat"]), "pln": float(p["lon"]),
                       "d": float(p.get("distance_km", 0)),
                       "ts": datetime.utcnow()})
        results.extend({
            "name": p.get("name", "Unnamed"),
            "category": p.get("category"),
            "lat": float(p["lat"]),
            "lng": float(p["lon"]),
            "distance_km": round(float(p.get("distance_km", 0)), 3),
        } for p in fresh)
    return results


def _row_to_poi(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": r["name"],
        "category": r["category"],
        "lat": float(r["poi_lat"]),
        "lng": float(r["poi_lng"]),
        "distance_km": round(float(r["distance_km"] or 0), 3),
    }


def _sample_indices(n_rows: int, n_samples: int) -> List[int]:
    n_samples = max(1, min(n_samples, n_rows))
    if n_samples == 1:
        return [n_rows // 2]
    step = (n_rows - 1) / (n_samples - 1)
    return [int(round(i * step)) for i in range(n_samples)]


def landmarks_for_trip(trip_id: int,
                       n_samples: int = 5,
                       radius_m: int | None = None,
                       categories: List[str] | None = None) -> Dict[str, Any]:
    """Sample N points along the trip's polyline, fetch POIs near each, and
    return a deduped list (by name + rounded coordinates)."""
    from route_intelligence import pipeline   # local import — avoid cycle
    trip = db.get_trip(trip_id)
    if not trip:
        raise ValueError(f"trip {trip_id} not found")
    df = pipeline._load_trip_df(trip)
    if df.empty:
        return {"trip_id": trip_id, "landmarks": []}

    seen: Dict[tuple, Dict[str, Any]] = {}
    for i in _sample_indices(len(df), n_samples):
        row = df.iloc[i]
        for poi in pois_near(float(row["latitude"]), float(row["longitude"]),
                             radius_m=radius_m, categories=categories):
            key = (poi["name"], round(poi["lat"], _PRECISION), round(poi["lng"], _PRECISION))
            if key not in seen or poi["distance_km"] < seen[key]["distance_km"]:
                seen[key] = poi
    landmarks = sorted(seen.values(), key=lambda p: (p["category"] or "", p["distance_km"]))
    return {
        "trip_id": trip_id,
        "vehicle_id": trip.get("vehicle_id"),
        "from": trip.get("from_waypoint"),
        "to": trip.get("to_waypoint"),
        "n_samples": n_samples,
        "radius_m": radius_m or _default_radius_m(),
        "categories": categories or _default_categories(),
        "landmarks": landmarks,
    }
