"""
Trip-aware weather enrichment.

Wraps ``legacy_viz.weather_service.WeatherService`` so we don't reimplement
Open-Meteo. Adds three things the legacy service didn't have:

1. **Trip-date awareness** — fetches HISTORICAL weather at the trip's actual
   start/end timestamps (not "now"). Works for completed trips uploaded weeks
   later.
2. **MySQL cache** — one row per (lat_round3, lng_round3, day) in
   ``ri_weather_cache``; re-runs of the same trip cost zero network calls.
3. **Polyline sampling** — picks evenly-spaced points along the trip's path
   so a long-haul covers source / midway / destination weather instead of
   just the endpoints.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from route_intelligence import config as ricfg
from route_intelligence import db
from route_intelligence.legacy_viz.weather_service import WeatherService

logger = logging.getLogger(__name__)

_PRECISION = 3   # ~111 m grid for the cache key
_MAX_AGE_DAYS = 30


# ----------------------------------------------------------------------------
# Cache table bootstrap (separate from the main DB bootstrap so this service
# is independently usable without forcing the route-intel schema)
# ----------------------------------------------------------------------------
_DDL = """
CREATE TABLE IF NOT EXISTS ri_weather_cache (
    cache_key VARCHAR(48) PRIMARY KEY,
    lat DOUBLE NOT NULL,
    lng DOUBLE NOT NULL,
    date_str CHAR(10) NOT NULL,
    payload_json MEDIUMTEXT,
    fetched_at DATETIME NOT NULL,
    INDEX idx_wc_day (date_str)
)
"""

_BOOTSTRAPPED = False


def _bootstrap_cache() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    with db.get_engine().begin() as c:
        c.execute(text(_DDL))
    _BOOTSTRAPPED = True


def _cache_key(lat: float, lng: float, date_str: str) -> str:
    return f"{round(lat, _PRECISION)}|{round(lng, _PRECISION)}|{date_str}"


# ----------------------------------------------------------------------------
# Backing service (singleton — sets up the requests Session once)
# ----------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _svc() -> WeatherService:
    return WeatherService()


# ----------------------------------------------------------------------------
# Low-level: one (lat, lng, date) → weather dict, cached in MySQL
# ----------------------------------------------------------------------------
def historical_at(lat: float, lng: float, when: datetime,
                  use_cache: bool = True) -> Dict[str, Any]:
    """Return historical weather for a single coordinate on the day of ``when``.
    Cached in MySQL by 3-decimal lat/lng + ISO date."""
    _bootstrap_cache()
    date_str = when.strftime("%Y-%m-%d")
    key = _cache_key(lat, lng, date_str)

    if use_cache:
        with db.get_engine().connect() as c:
            row = c.execute(text("SELECT payload_json FROM ri_weather_cache WHERE cache_key=:k"),
                            {"k": key}).first()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except Exception:
                    pass  # bad cache entry, refetch

    try:
        data = _svc().get_historical_weather(lat, lng, when)
    except Exception as exc:
        logger.warning("weather: legacy service failed (%s, %s, %s): %s", lat, lng, date_str, exc)
        return {"error": str(exc), "lat": lat, "lng": lng, "date": date_str}

    payload = data if isinstance(data, dict) else {"raw": data}
    with db.get_engine().begin() as c:
        c.execute(text("""
            INSERT INTO ri_weather_cache
              (cache_key, lat, lng, date_str, payload_json, fetched_at)
            VALUES (:k, :la, :ln, :d, :p, :ts)
            ON DUPLICATE KEY UPDATE payload_json=:p, fetched_at=:ts
        """), {"k": key, "la": float(lat), "ln": float(lng), "d": date_str,
               "p": json.dumps(payload, default=str), "ts": datetime.utcnow()})
    return payload


# ----------------------------------------------------------------------------
# Trip-aware sampling
# ----------------------------------------------------------------------------
@dataclass
class WeatherSample:
    lat: float
    lng: float
    ts: str        # the GPS ping timestamp at this sample
    fraction: float   # 0.0 = start, 1.0 = end (for the UI to label)
    weather: Dict[str, Any]


def _sample_indices(n_rows: int, n_samples: int) -> List[int]:
    n_samples = max(1, min(n_samples, n_rows))
    if n_samples == 1:
        return [n_rows // 2]
    step = (n_rows - 1) / (n_samples - 1)
    return [int(round(i * step)) for i in range(n_samples)]


def weather_along(df: pd.DataFrame, n_samples: int = 5) -> List[WeatherSample]:
    """Sample N evenly-spaced points along a GPS DataFrame and fetch historical
    weather at each point's *own* timestamp. Returns one ``WeatherSample`` per
    sample point (start, end, and N-2 in between)."""
    if df.empty:
        return []
    out: List[WeatherSample] = []
    n_rows = len(df)
    idxs = _sample_indices(n_rows, n_samples)
    for i in idxs:
        row = df.iloc[i]
        ts = pd.Timestamp(row["Date Time"]).to_pydatetime()
        w = historical_at(float(row["latitude"]), float(row["longitude"]), ts)
        out.append(WeatherSample(
            lat=float(row["latitude"]),
            lng=float(row["longitude"]),
            ts=str(row["Date Time"]),
            fraction=round(i / max(1, n_rows - 1), 3),
            weather=w,
        ))
    return out


def weather_for_trip(trip_id: int, n_samples: int = 5) -> Dict[str, Any]:
    """High-level entry point for the FastAPI route. Loads the trip's GPS,
    samples N points, returns the bundle the UI renders."""
    from route_intelligence import pipeline   # local import — avoid cycle
    trip = db.get_trip(trip_id)
    if not trip:
        raise ValueError(f"trip {trip_id} not found")
    df = pipeline._load_trip_df(trip)
    samples = weather_along(df, n_samples=n_samples)
    return {
        "trip_id": trip_id,
        "vehicle_id": trip.get("vehicle_id"),
        "from": trip.get("from_waypoint"),
        "to": trip.get("to_waypoint"),
        "start_ts": str(trip.get("start_ts")),
        "end_ts": str(trip.get("end_ts")),
        "samples": [_to_dict(s) for s in samples],
    }


def weather_for_segment(segment_id: int, n_samples: int = 3) -> Dict[str, Any]:
    from route_intelligence import pipeline
    seg = db.get_segment(segment_id)
    if not seg:
        raise ValueError(f"segment {segment_id} not found")
    trip = db.get_trip(seg["trip_id"])
    df = pipeline._load_segment_df(trip, seg)
    samples = weather_along(df, n_samples=n_samples)
    return {
        "segment_id": segment_id,
        "trip_id": seg["trip_id"],
        "from": seg.get("from_waypoint"),
        "to": seg.get("to_waypoint"),
        "start_ts": str(seg.get("start_ts")),
        "end_ts": str(seg.get("end_ts")),
        "samples": [_to_dict(s) for s in samples],
    }


def _to_dict(s: WeatherSample) -> Dict[str, Any]:
    return {
        "lat": s.lat, "lng": s.lng,
        "ts": s.ts, "fraction": s.fraction,
        "weather": s.weather,
    }
