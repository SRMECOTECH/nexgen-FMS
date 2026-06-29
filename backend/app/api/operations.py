"""Operational endpoints — alerts, geofences."""

from datetime import datetime, timedelta
import random

from fastapi import APIRouter

router = APIRouter(prefix="/operations", tags=["operations"])

_RNG = random.Random(17)


@router.get("/alerts")
def list_alerts():
    types = [
        ("speeding",        "warning",  "Exceeded road speed by 23 km/h"),
        ("idling",          "info",     "Idled 38 mins at non-authorized location"),
        ("route_deviation", "warning",  "Drifted 4.2 km from canonical lane path"),
        ("detention",       "critical", "Detained 4h 12m at consignee Plant-B"),
        ("fuel_pilferage",  "critical", "Unexplained fuel drop 23L without movement"),
        ("late_delivery",   "warning",  "ETA slipped by 95 min"),
        ("device_offline",  "critical", "No GPS ping for 47 minutes"),
        ("harsh_braking",   "warning",  "5 harsh-brake events in last 30 min"),
    ]
    items = []
    for i in range(24):
        type_, sev, msg = _RNG.choice(types)
        items.append({
            "id": f"alert-{20000 + i}",
            "timestamp": (datetime.now() - timedelta(minutes=_RNG.randint(1, 720))).isoformat(),
            "severity": sev,
            "type": type_,
            "vehicle_id": f"MH12AB{1000 + _RNG.randint(0, 19):04d}",
            "driver_name": f"Driver {_RNG.randint(1, 15)}",
            "message": msg,
            "acknowledged": _RNG.random() < 0.3,
        })
    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return {
        "alerts": items,
        "summary": {
            "critical": sum(1 for x in items if x["severity"] == "critical"),
            "warning":  sum(1 for x in items if x["severity"] == "warning"),
            "info":     sum(1 for x in items if x["severity"] == "info"),
            "unacked":  sum(1 for x in items if not x["acknowledged"]),
        },
    }


@router.get("/geofences")
def list_geofences():
    zones = [
        ("Mumbai Depot",      "depot",     19.0760, 72.8777, 500),
        ("Pune Plant",        "customer",  18.5204, 73.8567, 800),
        ("Bangalore Hub",     "depot",     12.9716, 77.5946, 1200),
        ("Chennai Port",      "customer",  13.0827, 80.2707, 1500),
        ("HPCL Fuel Hub",     "fuel",      19.0330, 73.0297, 300),
        ("Restricted Zone A", "restricted",19.2183, 72.9781, 2000),
    ]
    items = []
    for i, (name, kind, lat, lng, radius) in enumerate(zones):
        items.append({
            "id": f"gf-{100 + i}",
            "name": name,
            "kind": kind,
            "lat": lat,
            "lng": lng,
            "radius_m": radius,
            "active_vehicles": _RNG.randint(0, 12),
            "entries_today": _RNG.randint(0, 45),
            "exits_today": _RNG.randint(0, 45),
        })
    return {"geofences": items}
