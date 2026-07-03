"""
Thin client to the OSRM app's distance API (the NexGen Route Intelligence
service that fronts an OSRM engine).

nextGen-FMS never talks to the raw OSRM engine directly — it calls the OSRM
app, which owns the engine URL, map-matching windows, and gap-bridging. We only
need one thing here: turn a list of ``(lat, lon)`` coordinates into an actual
ROAD distance, to replace the haversine straight-line used in route-efficiency.

Configuration (all optional):
    OSRM_API_URL        base URL of the OSRM app (default http://localhost:8000)
    OSRM_API_TIMEOUT    per-call timeout in seconds (default 15)

Everything degrades gracefully: if the OSRM app (or its engine) is unreachable,
every function returns ``None`` and the caller falls back to the straight line.
Nothing here ever raises into the analysis pipeline.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Sequence, Tuple

import httpx

logger = logging.getLogger(__name__)

_Coord = Tuple[float, float]  # (lat, lon)


def base_url() -> str:
    return os.getenv("OSRM_API_URL", "http://localhost:8000").rstrip("/")


def _timeout() -> float:
    try:
        return float(os.getenv("OSRM_API_TIMEOUT", "15"))
    except ValueError:
        return 15.0


def is_configured() -> bool:
    """OSRM is 'wired' whenever a URL is set — reachability is checked per-call."""
    return bool(base_url())


def road_distance_km(coords: Sequence[_Coord]) -> Optional[dict]:
    """Optimal ROAD distance through the ordered ``(lat, lon)`` points.

    Returns ``{"road_distance_km", "duration_min", "source"}`` on success, or
    ``None`` if fewer than 2 points, OSRM is unreachable, or it can't route.
    """
    pts: List[List[float]] = [[float(a), float(b)] for a, b in coords]
    if len(pts) < 2:
        return None
    try:
        with httpx.Client(timeout=_timeout()) as c:
            r = c.post(f"{base_url()}/api/route-distance", json={"coordinates": pts})
        if r.status_code != 200:
            logger.warning("osrm_gateway: /api/route-distance -> HTTP %s", r.status_code)
            return None
        data = r.json()
        if not data.get("ok"):
            return None
        return {
            "road_distance_km": data.get("road_distance_km"),
            "duration_min": data.get("duration_min"),
            "source": data.get("source", "osrm"),
        }
    except Exception as exc:  # noqa: BLE001 — offline/timeouts are expected, fall back
        logger.info("osrm_gateway: OSRM unavailable (%s) — caller will use straight-line", exc)
        return None
