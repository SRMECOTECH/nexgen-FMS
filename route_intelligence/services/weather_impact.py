"""
Weather-impact correlator.

For every 30-min time window of a trip, pull the hourly historical weather at
the window's centre coordinate AND timestamp (cached via
``services.weather.historical_at``), classify it (clear / rain / heavy-rain /
storm / fog), and decide whether a slow window is *likely* explained by
adverse weather.

Used to answer the dispatcher's real question: "the truck slowed down here —
was it weather, traffic, or driver?". Weather is the cheapest correlation to
make (we already have all the data on disk), so it's the first signal we add.

Returned shape (consumed by ``/trips/{id}/weather-impact``):

  {
    "trip_id": 17,
    "verdict": "weather_was_a_factor",      # plain English bucket
    "summary": {
        "windows_total":            64,
        "windows_slow":             18,
        "windows_adverse_weather":  12,
        "windows_slow_and_adverse": 9,      # high-confidence weather-caused
        "minutes_lost_to_weather":  142,
        "median_speed_kmph":        34.6,
        "slow_threshold_kmph":      20.8,
    },
    "windows": [
        {
          "window_label":   "13:30–13:59",
          "window_start":   "2026-06-01T13:30:00",
          "lat": 22.41, "lng": 84.07,
          "avg_speed_kmph": 11.3,
          "is_slow":        true,
          "weather":        {"rain_mm": 5.4, "weather_code": 63, "wind_kmh": 18,
                              "description": "Heavy rain", "temperature_c": 27},
          "weather_bucket": "heavy_rain",
          "weather_caused": true,            # slow AND adverse
          "note":           "Heavy rain (5.4 mm/h) — speed dropped to 11 km/h."
        },
        ...
    ],
  }
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from route_intelligence import db
from route_intelligence.services import weather as weather_svc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables — exposed as kwargs so the API can override if needed.
# ---------------------------------------------------------------------------
DEFAULT_SLOW_RATIO       = 0.60   # window is "slow" if avg_speed < 0.6 * median
DEFAULT_ABSOLUTE_SLOW_KPH = 25.0  # but also always slow if absolute < 25 km/h
RAIN_LIGHT_MM   = 0.5             # >= this -> "rain"
RAIN_HEAVY_MM   = 4.0             # >= this -> "heavy_rain"
WIND_STORM_KMH  = 50.0            # >= this -> "storm"


# WMO weather codes — see https://open-meteo.com/en/docs
# Buckets: clear (0-3), fog (45,48), drizzle (51-57), rain (61-67),
#          snow (71-77), showers (80-82), thunderstorm (95-99)
def _bucket_from_code(code: Optional[int]) -> str:
    if code is None:
        return "clear"
    if code in (45, 48):                 return "fog"
    if 51 <= code <= 57:                 return "rain"        # drizzle counted as rain
    if 61 <= code <= 67:                 return "rain"
    if 71 <= code <= 77:                 return "snow"
    if 80 <= code <= 82:                 return "rain"        # rain showers
    if 95 <= code <= 99:                 return "storm"
    return "clear"


def classify_weather(w: Dict[str, Any]) -> str:
    """Combine WMO code + measurable mm/h + wind to pick a single bucket.

    The mm/h check upgrades "rain" → "heavy_rain" so the UI can light it red,
    and wind upgrades anything to "storm" if it's gusty enough to actually
    matter for a 16-wheeler."""
    if not w or "error" in w:
        return "unknown"

    rain_mm   = float(w.get("rain_mm") or 0)
    wind_kmh  = float(w.get("wind_speed_kmh") or 0)
    code      = w.get("weather_code")

    bucket = _bucket_from_code(code)

    # Upgrade by intensity
    if bucket == "rain" and rain_mm >= RAIN_HEAVY_MM:
        bucket = "heavy_rain"
    if wind_kmh >= WIND_STORM_KMH and bucket in ("clear", "rain"):
        bucket = "storm"

    # Fallback: if WMO code missing but rain present, still flag it.
    if bucket == "clear" and rain_mm >= RAIN_LIGHT_MM:
        bucket = "heavy_rain" if rain_mm >= RAIN_HEAVY_MM else "rain"

    return bucket


_ADVERSE = {"rain", "heavy_rain", "storm", "snow", "fog"}


def _note(bucket: str, w: Dict[str, Any], avg_kph: float) -> str:
    rain_mm = float(w.get("rain_mm") or 0)
    wind    = float(w.get("wind_speed_kmh") or 0)
    if bucket == "heavy_rain":
        return f"Heavy rain ({rain_mm:.1f} mm/h) — speed dropped to {avg_kph:.0f} km/h."
    if bucket == "rain":
        return f"Rain ({rain_mm:.1f} mm/h) — speed at {avg_kph:.0f} km/h."
    if bucket == "storm":
        return f"Storm conditions (wind {wind:.0f} km/h) — speed at {avg_kph:.0f} km/h."
    if bucket == "fog":
        return f"Low-visibility fog conditions — speed at {avg_kph:.0f} km/h."
    if bucket == "snow":
        return f"Snowfall along route — speed at {avg_kph:.0f} km/h."
    return f"Clear weather — slowdown unlikely to be weather-driven."


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def weather_impact_for_trip(trip_id: int,
                             slow_ratio: float = DEFAULT_SLOW_RATIO,
                             slow_abs_kph: float = DEFAULT_ABSOLUTE_SLOW_KPH) -> Dict[str, Any]:
    """Run the correlation for the latest analysis run of ``trip_id``."""
    trip = db.get_trip(trip_id)
    if not trip:
        raise ValueError(f"trip {trip_id} not found")

    # Pick the latest WHOLE-TRIP run (helper skips segment-scoped runs, which
    # only cover one leg and would otherwise show as ~17 windows for a
    # multi-day trip).
    trip_run = db.get_latest_done_run_for_trip(trip_id)
    if not trip_run:
        raise ValueError(f"trip {trip_id} has no completed trip-level analysis run — analyse it first")
    run_id = trip_run["id"]

    with db.get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT window_label, window_start, window_end,
                   avg_speed_kmph, latitude, longitude,
                   moving_time_sec, stopped_time_sec
            FROM ri_time_windows
            WHERE run_id=:r AND latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY window_start
        """), {"r": run_id}).mappings().all()

    if not rows:
        return _empty_payload(trip_id)

    # ---- compute the slow threshold from this trip's own speed distribution
    speeds = [float(r["avg_speed_kmph"]) for r in rows if r["avg_speed_kmph"] is not None]
    median_kph = statistics.median(speeds) if speeds else 0.0
    slow_threshold = min(slow_abs_kph, max(5.0, median_kph * slow_ratio))

    out_windows: List[Dict[str, Any]] = []
    minutes_lost = 0.0
    slow_n = adverse_n = both_n = 0

    for r in rows:
        avg = float(r["avg_speed_kmph"] or 0)
        ts: datetime = r["window_start"]
        lat = float(r["latitude"]); lng = float(r["longitude"])

        # Cached on disk by (lat, lng, day) — second pass on the same trip is free.
        try:
            w = weather_svc.historical_at(lat, lng, ts)
        except Exception as exc:
            logger.warning("weather_impact: lookup failed at %s: %s", ts, exc)
            w = {"error": str(exc)}

        bucket = classify_weather(w)
        is_slow = avg < slow_threshold
        is_adverse = bucket in _ADVERSE
        weather_caused = is_slow and is_adverse

        if is_slow: slow_n += 1
        if is_adverse: adverse_n += 1
        if weather_caused:
            both_n += 1
            # minutes "lost" = window length (in min) of the adverse-slow overlap
            seconds = float(r["moving_time_sec"] or 0) + float(r["stopped_time_sec"] or 0)
            minutes_lost += seconds / 60.0

        out_windows.append({
            "window_label":   r["window_label"],
            "window_start":   ts.isoformat() if ts else None,
            "lat":            lat,
            "lng":            lng,
            "avg_speed_kmph": round(avg, 1),
            "is_slow":        is_slow,
            "weather":        _trim_weather(w),
            "weather_bucket": bucket,
            "weather_caused": weather_caused,
            "note":           _note(bucket, w, avg),
        })

    summary = {
        "windows_total":            len(out_windows),
        "windows_slow":             slow_n,
        "windows_adverse_weather":  adverse_n,
        "windows_slow_and_adverse": both_n,
        "minutes_lost_to_weather":  round(minutes_lost, 1),
        "median_speed_kmph":        round(median_kph, 1),
        "slow_threshold_kmph":      round(slow_threshold, 1),
    }

    return {
        "trip_id": trip_id,
        "from":    trip.get("from_waypoint"),
        "to":      trip.get("to_waypoint"),
        "verdict": _verdict(summary),
        "summary": summary,
        "windows": out_windows,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trim_weather(w: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the few weather fields the UI actually needs."""
    if not w or "error" in w:
        return {"error": (w or {}).get("error", "no data")}
    return {
        "temperature_c":       w.get("temperature_c"),
        "rain_mm":             w.get("rain_mm"),
        "wind_kmh":            w.get("wind_speed_kmh"),
        "cloud_cover_pct":     w.get("cloud_cover_pct"),
        "weather_code":        w.get("weather_code"),
        "description":         w.get("weather_description"),
    }


def _verdict(s: Dict[str, int]) -> str:
    """One-bucket verdict the UI uses to colour the card."""
    if s["windows_total"] == 0:
        return "no_data"
    pct_caused = (s["windows_slow_and_adverse"] / s["windows_total"]) * 100
    if pct_caused >= 15:
        return "weather_was_a_factor"
    if s["windows_adverse_weather"] > 0:
        return "weather_present_but_minor"
    return "weather_was_clear"


def _empty_payload(trip_id: int) -> Dict[str, Any]:
    return {
        "trip_id": trip_id,
        "verdict": "no_data",
        "summary": {
            "windows_total": 0, "windows_slow": 0,
            "windows_adverse_weather": 0, "windows_slow_and_adverse": 0,
            "minutes_lost_to_weather": 0.0, "median_speed_kmph": 0,
            "slow_threshold_kmph": 0,
        },
        "windows": [],
    }
