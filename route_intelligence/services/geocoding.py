"""
Trip-aware reverse-geocoding.

Wraps ``legacy_viz.geocoder.ReverseGeocoder`` (Nominatim) and swaps its JSON
file cache for the MySQL ``ri_geocode_cache`` table so addresses are shared
across runs, services, and processes. Respects Nominatim's 1 req/s policy via
the legacy service's own rate-limiter.

Public entry points:
    address_at(lat, lng)              one coordinate → address dict
    addresses_for_trip(trip_id)       start + end address of a trip
    addresses_for_segments(trip_id)   start + end of every segment in a trip
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from route_intelligence import db
from route_intelligence.legacy_viz.geocoder import ReverseGeocoder

logger = logging.getLogger(__name__)

_PRECISION = 3  # ~111 m grid for the cache key


@lru_cache(maxsize=1)
def _svc() -> ReverseGeocoder:
    # We don't care about its JSON cache — we have MySQL.
    return ReverseGeocoder()


def _key(lat: float, lng: float) -> str:
    return f"{round(lat, _PRECISION)}|{round(lng, _PRECISION)}"


def address_at(lat: float, lng: float, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """Reverse-geocode one (lat, lng) → dict with formatted_address, city,
    state, country, etc. Cached in ``ri_geocode_cache``."""
    db.bootstrap()
    key = _key(lat, lng)

    if use_cache:
        with db.get_engine().connect() as c:
            row = c.execute(text("""
                SELECT address, raw_json FROM ri_geocode_cache WHERE cache_key=:k
            """), {"k": key}).first()
            if row:
                try:
                    return json.loads(row[1]) if row[1] else {"formatted_address": row[0]}
                except Exception:
                    pass

    try:
        addr = _svc().get_address(float(lat), float(lng))
    except Exception as exc:
        logger.warning("geocoding failed for (%s, %s): %s", lat, lng, exc)
        return None
    if not addr:
        return None

    with db.get_engine().begin() as c:
        c.execute(text("""
            INSERT INTO ri_geocode_cache
              (cache_key, lat, lng, address, raw_json, fetched_at)
            VALUES (:k, :la, :ln, :a, :r, :ts)
            ON DUPLICATE KEY UPDATE address=:a, raw_json=:r, fetched_at=:ts
        """), {"k": key, "la": float(lat), "ln": float(lng),
               "a": addr.get("formatted_address", "")[:1000],
               "r": json.dumps(addr, default=str),
               "ts": datetime.utcnow()})
    return addr


def addresses_for_trip(trip_id: int) -> Dict[str, Any]:
    """Resolve start and end addresses of a trip header."""
    t = db.get_trip(trip_id)
    if not t:
        raise ValueError(f"trip {trip_id} not found")
    return {
        "trip_id": trip_id,
        "start": address_at(t["start_lat"], t["start_lng"]),
        "end": address_at(t["end_lat"], t["end_lng"]),
    }


def addresses_for_segments(trip_id: int) -> Dict[str, Any]:
    """Resolve start + end addresses for EVERY segment of a trip. Calls are
    rate-limited by the underlying Nominatim wrapper (1 req/sec) so this
    blocks for N seconds on a cold cache."""
    segs = db.list_segments_for_trip(trip_id)
    if not segs:
        raise ValueError(f"no segments for trip {trip_id}")
    out: List[Dict[str, Any]] = []
    for s in segs:
        out.append({
            "segment_id": s["id"],
            "seq": s["seq"],
            "from_waypoint": s["from_waypoint"],
            "to_waypoint": s["to_waypoint"],
            "start_address": address_at(s["start_lat"], s["start_lng"]),
            "end_address": address_at(s["end_lat"], s["end_lng"]),
        })
    return {"trip_id": trip_id, "segments": out}
