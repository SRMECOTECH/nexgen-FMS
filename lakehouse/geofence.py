"""
Geofence discovery + stop-event enrichment + reverse geocoding.

Pipeline (all free / open-source):
  1. Detect STOP episodes per truck   — consecutive low-speed pings >= N minutes.
  2. Cluster stop locations           — DBSCAN (haversine) groups repeat visits to
                                         the same place into ONE reusable geofence.
  3. Infer why it stopped             — duration + time-of-day -> rest / lunch /
                                         dinner / tea / loading / halt.
  4. Reverse geocode geofences        — Nominatim (OpenStreetMap), cached in the DB
                                         so we hit the API once per place, not per ping.

Writes dim_geofence + fact_stop_event. Rebuilt idempotently on each call (both
tables are tiny relative to the raw fact).

Nominatim usage policy: <=1 request/second, descriptive User-Agent, cache results.
For 500-1000 trucks you can self-host Nominatim/Photon and point NOMINATIM_URL at it.
"""

from __future__ import annotations

import logging
import os
import time

import numpy as np
import pandas as pd
from sqlalchemy import text

from lakehouse import gps_store, poi

logger = logging.getLogger(__name__)

# Bias the Overpass POI search by what kind of place this geofence usually is.
_TYPE_REASON_HINT = {
    "rest_stop": "Night rest",
    "eatery": "Lunch break",
    "facility": "Long halt",
    "halt": "Tea / short break",
}

NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
GEOCODE_DELAY_SEC = float(os.environ.get("NOMINATIM_DELAY", "1.1"))  # respect 1 req/s
# Stop-detection tunables — all sourced from .env (single source of config).
STOP_MIN_MINUTES = float(os.environ.get("STOP_MIN_MINUTES", "12"))   # a STOP must last at least this long
STOP_CLUSTER_EPS_M = float(os.environ.get("STOP_CLUSTER_EPS_M", "250"))  # DBSCAN radius merging repeat visits
_EARTH_M = 6_371_000.0


# ----------------------------------------------------------------------
# stop detection
# ----------------------------------------------------------------------
_FACT_SQL = """
SELECT f.vehicle_sk, f.device_sk, v.vehicle_reg, f.gps_ts,
       f.latitude, f.longitude,
       COALESCE(f.speed_corr_kph, f.speed_kph, 0) AS speed,
       fn.node_name AS near_node
FROM fact_gps_ping f
JOIN dim_vehicle v ON f.vehicle_sk = v.vehicle_sk
LEFT JOIN dim_node fn ON f.from_node_sk = fn.node_sk
{where}
ORDER BY f.vehicle_sk, f.gps_ts
"""


def _detect_stops(min_minutes: float, vehicle: str | None) -> pd.DataFrame:
    e = gps_store.engine()
    if e is None or not gps_store.schema_ready():
        return pd.DataFrame()
    where = "WHERE v.vehicle_reg = :veh" if vehicle else ""
    df = pd.read_sql(text(_FACT_SQL.format(where=where)), e,
                     params=({"veh": vehicle} if vehicle else {}))
    if df.empty:
        return df
    df["gps_ts"] = pd.to_datetime(df["gps_ts"], errors="coerce")
    df = df.dropna(subset=["gps_ts", "latitude", "longitude"])
    df["moving"] = df["speed"].astype(float) > 2

    stops = []
    for vsk, g in df.groupby("vehicle_sk"):
        g = g.sort_values("gps_ts")
        g["blk"] = (g["moving"] != g["moving"].shift()).cumsum()
        for _, blk in g[~g["moving"]].groupby("blk"):
            mins = (blk["gps_ts"].max() - blk["gps_ts"].min()).total_seconds() / 60
            if mins < min_minutes:
                continue
            stops.append({
                "vehicle_sk": int(vsk),
                "device_sk": int(blk["device_sk"].mode().iloc[0]) if blk["device_sk"].notna().any() else None,
                "vehicle_reg": blk["vehicle_reg"].iloc[0],
                "arrive_ts": blk["gps_ts"].min(),
                "depart_ts": blk["gps_ts"].max(),
                "minutes": round(mins, 1),
                "lat": float(blk["latitude"].median()),
                "lng": float(blk["longitude"].median()),
                "near_node": blk["near_node"].mode().iloc[0] if blk["near_node"].notna().any() else None,
            })
    return pd.DataFrame(stops)


# ----------------------------------------------------------------------
# clustering + reason inference
# ----------------------------------------------------------------------
def _cluster(stops: pd.DataFrame, eps_m: float = 250.0) -> np.ndarray:
    """DBSCAN over stop coords (haversine). min_samples=1 -> every stop joins a
    cluster or forms its own geofence (no noise)."""
    if stops.empty:
        return np.array([])
    coords = np.radians(stops[["lat", "lng"]].to_numpy())
    try:
        from sklearn.cluster import DBSCAN
        labels = DBSCAN(eps=eps_m / _EARTH_M, min_samples=1, metric="haversine").fit_predict(coords)
        return labels
    except Exception as exc:  # sklearn missing -> degrade: each stop its own geofence
        logger.warning("geofence: DBSCAN unavailable (%s) — one geofence per stop", exc)
        return np.arange(len(stops))


def _infer_reason(minutes: float, hour: int) -> str:
    if minutes >= 360:
        return "Night rest" if (hour >= 20 or hour <= 5) else "Long halt"
    if 25 <= minutes <= 100 and 11 <= hour <= 15:
        return "Lunch break"
    if 25 <= minutes <= 100 and 19 <= hour <= 23:
        return "Dinner break"
    if 8 <= minutes < 25:
        return "Tea / short break"
    if minutes > 100:
        return "Extended halt"
    return "Halt"


def _geofence_type(reasons: list[str]) -> str:
    s = set(reasons)
    if {"Night rest"} & s:
        return "rest_stop"
    if {"Lunch break", "Dinner break"} & s:
        return "eatery"
    if {"Long halt", "Extended halt"} & s:
        return "facility"
    return "halt"


# ----------------------------------------------------------------------
# build
# ----------------------------------------------------------------------
def build_geofences_and_stops(min_minutes: float = STOP_MIN_MINUTES, eps_m: float = STOP_CLUSTER_EPS_M,
                              vehicle: str | None = None) -> dict:
    """Detect stops, cluster into geofences, infer reasons, persist both tables.

    Rebuilds the whole dim_geofence + fact_stop_event each call (tiny tables).
    Preserves any addresses already reverse-geocoded by matching geofence centre.
    """
    e = gps_store.engine()
    if e is None or not gps_store.schema_ready():
        return {"ok": False, "error": "warehouse/schema not ready"}

    stops = _detect_stops(min_minutes, vehicle)
    if stops.empty:
        return {"ok": True, "geofences": 0, "stop_events": 0, "note": "no stops detected"}

    stops = stops.reset_index(drop=True)
    stops["cluster"] = _cluster(stops, eps_m)
    stops["hour"] = stops["arrive_ts"].dt.hour
    stops["reason"] = [_infer_reason(m, h) for m, h in zip(stops["minutes"], stops["hour"])]

    # keep previously-geocoded addresses (match by rounded centre)
    prior = pd.read_sql(text("SELECT center_lat, center_lng, address FROM dim_geofence WHERE address IS NOT NULL"), e) \
        if _has(e, "dim_geofence") else pd.DataFrame()
    addr_lookup = {}
    for r in prior.itertuples():
        addr_lookup[(round(r.center_lat, 4), round(r.center_lng, 4))] = r.address

    # one geofence per cluster
    geofences, gf_index = [], {}
    for cid, grp in stops.groupby("cluster"):
        clat, clng = float(grp["lat"].mean()), float(grp["lng"].mean())
        radius = float(np.sqrt(((grp["lat"] - clat) ** 2 + (grp["lng"] - clng) ** 2).max()) * 111_000) or 80.0
        name = grp["near_node"].mode().iloc[0] if grp["near_node"].notna().any() else f"Stop @ {clat:.3f},{clng:.3f}"
        gf = {
            "name": str(name)[:200],
            "center_lat": clat, "center_lng": clng,
            "radius_m": round(max(radius, 60.0), 1),
            "type": _geofence_type(list(grp["reason"])),
            "address": addr_lookup.get((round(clat, 4), round(clng, 4))),
        }
        gf_index[cid] = len(geofences)
        geofences.append(gf)

    with e.begin() as conn:
        conn.execute(text("DELETE FROM fact_stop_event"))
        conn.execute(text("DELETE FROM dim_geofence"))
        # insert geofences, capture surrogate keys by re-selecting
        for gf in geofences:
            conn.execute(text("""
                INSERT INTO dim_geofence (name, center_lat, center_lng, radius_m, type, address)
                VALUES (:name, :center_lat, :center_lng, :radius_m, :type, :address)
            """), gf)
        gmap = {}
        for row in conn.execute(text("SELECT geofence_sk, center_lat, center_lng FROM dim_geofence")).all():
            gmap[(round(row[1], 5), round(row[2], 5))] = row[0]

        events = []
        for r in stops.itertuples():
            gf = geofences[gf_index[r.cluster]]
            gsk = gmap.get((round(gf["center_lat"], 5), round(gf["center_lng"], 5)))
            events.append({
                "vehicle_sk": r.vehicle_sk, "device_sk": r.device_sk, "geofence_sk": gsk,
                "arrive_ts": r.arrive_ts.to_pydatetime(), "depart_ts": r.depart_ts.to_pydatetime(),
                "minutes": float(r.minutes), "lat": r.lat, "lng": r.lng,
                "address": gf["address"], "reason_inferred": r.reason,
            })
        for i in range(0, len(events), 500):
            conn.execute(text("""
                INSERT INTO fact_stop_event
                  (vehicle_sk, device_sk, geofence_sk, arrive_ts, depart_ts, minutes, lat, lng, address, reason_inferred)
                VALUES
                  (:vehicle_sk, :device_sk, :geofence_sk, :arrive_ts, :depart_ts, :minutes, :lat, :lng, :address, :reason_inferred)
            """), events[i:i + 500])

    return {"ok": True, "geofences": len(geofences), "stop_events": len(stops),
            "geocoded": int(sum(1 for g in geofences if g["address"]))}


def _has(engine, table) -> bool:
    from sqlalchemy import inspect
    try:
        return inspect(engine).has_table(table)
    except Exception:
        return False


# ----------------------------------------------------------------------
# reverse geocoding (Nominatim) — cached in dim_geofence.address
# ----------------------------------------------------------------------
def _reverse(lat: float, lng: float) -> str | None:
    import requests
    try:
        r = requests.get(
            f"{NOMINATIM_URL}/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "zoom": 16, "addressdetails": 0},
            headers={"User-Agent": "neXgen-FMS/1.0 (fleet analytics; contact admin)"},
            timeout=10,
        )
        if r.ok:
            return (r.json() or {}).get("display_name")
    except Exception as exc:
        logger.warning("geocode: %s", exc)
    return None


def geocode_pending(limit: int = 20) -> dict:
    """Reverse-geocode geofences that don't have an address yet (rate-limited),
    then propagate the address onto their stop events."""
    e = gps_store.engine()
    if e is None or not gps_store.schema_ready():
        return {"ok": False, "error": "schema not ready"}
    pending = pd.read_sql(text(
        "SELECT geofence_sk, center_lat, center_lng FROM dim_geofence "
        "WHERE address IS NULL LIMIT :lim"), e, params={"lim": int(limit)})
    done = 0
    for r in pending.itertuples():
        addr = _reverse(r.center_lat, r.center_lng)
        if addr:
            with e.begin() as conn:
                conn.execute(text("UPDATE dim_geofence SET address=:a WHERE geofence_sk=:s"),
                             {"a": addr[:400], "s": r.geofence_sk})
                conn.execute(text("UPDATE fact_stop_event SET address=:a WHERE geofence_sk=:s"),
                             {"a": addr[:400], "s": r.geofence_sk})
            done += 1
        time.sleep(GEOCODE_DELAY_SEC)
    remaining = int(pd.read_sql(text("SELECT count(*) c FROM dim_geofence WHERE address IS NULL"), e)["c"].iloc[0])
    return {"ok": True, "geocoded_now": done, "remaining": remaining}


# ----------------------------------------------------------------------
# POI enrichment (Overpass / OSM) — cached on dim_geofence.poi_*
# ----------------------------------------------------------------------
def enrich_poi(limit: int = 20, radius_m: int = poi.POI_RADIUS_M) -> dict:
    """Resolve the nearest named place (dhaba/hotel/fuel/…) for geofences that
    don't have one yet, then propagate it onto their stop events' reads. Hits the
    shared Overpass server once per geofence, rate-limited and cached."""
    e = gps_store.engine()
    if e is None or not gps_store.schema_ready():
        return {"ok": False, "error": "schema not ready"}
    gps_store.ensure_columns()
    pending = pd.read_sql(text(
        "SELECT geofence_sk, center_lat, center_lng, type FROM dim_geofence "
        "WHERE poi_name IS NULL LIMIT :lim"), e, params={"lim": int(limit)})
    done = 0
    for r in pending.itertuples():
        hint = _TYPE_REASON_HINT.get(r.type)
        p = poi.nearest_poi(float(r.center_lat), float(r.center_lng), radius_m=radius_m, reason=hint)
        if p:
            with e.begin() as conn:
                conn.execute(text(
                    "UPDATE dim_geofence SET poi_name=:n, poi_category=:c, poi_distance_m=:d "
                    "WHERE geofence_sk=:s"),
                    {"n": p["name"], "c": p["category"], "d": p["distance_m"], "s": r.geofence_sk})
            done += 1
        time.sleep(poi.OVERPASS_DELAY_SEC)
    remaining = int(pd.read_sql(text(
        "SELECT count(*) c FROM dim_geofence WHERE poi_name IS NULL"), e)["c"].iloc[0])
    return {"ok": True, "resolved_now": done, "remaining": remaining}


def _poi_obj(name, category, distance) -> dict | None:
    if not name or (isinstance(name, float) and pd.isna(name)):
        return None
    return {"name": name, "category": category,
            "distance_m": None if pd.isna(distance) else round(float(distance))}


# ----------------------------------------------------------------------
# reads
# ----------------------------------------------------------------------
def list_geofences() -> list[dict]:
    e = gps_store.engine()
    if e is None or not _has(e, "dim_geofence"):
        return []
    df = pd.read_sql(text("""
        SELECT g.geofence_sk, g.name, g.center_lat, g.center_lng, g.radius_m, g.type, g.address,
               g.poi_name, g.poi_category, g.poi_distance_m,
               COUNT(s.stop_sk) AS visits, COALESCE(SUM(s.minutes),0) AS total_min
        FROM dim_geofence g
        LEFT JOIN fact_stop_event s ON s.geofence_sk = g.geofence_sk
        GROUP BY g.geofence_sk, g.name, g.center_lat, g.center_lng, g.radius_m, g.type, g.address,
                 g.poi_name, g.poi_category, g.poi_distance_m
        ORDER BY visits DESC, total_min DESC
    """), e)
    out = []
    for r in df.itertuples():
        p = _poi_obj(r.poi_name, r.poi_category, r.poi_distance_m)
        out.append({
            "geofence_sk": int(r.geofence_sk), "name": r.name,
            "lat": round(float(r.center_lat), 6), "lng": round(float(r.center_lng), 6),
            "radius_m": float(r.radius_m), "type": r.type, "address": r.address,
            "poi": p, "label": poi.label_for_stop(p, r.address, r.name),
            "visits": int(r.visits), "total_min": round(float(r.total_min), 0),
        })
    return out


def list_stop_events(vehicle: str | None = None) -> list[dict]:
    e = gps_store.engine()
    if e is None or not _has(e, "fact_stop_event"):
        return []
    where = "WHERE v.vehicle_reg = :veh" if vehicle else ""
    df = pd.read_sql(text(f"""
        SELECT v.vehicle_reg, s.arrive_ts, s.depart_ts, s.minutes, s.lat, s.lng,
               s.reason_inferred, s.address, g.name AS node_name, g.type,
               g.poi_name, g.poi_category, g.poi_distance_m
        FROM fact_stop_event s
        JOIN dim_vehicle v ON s.vehicle_sk = v.vehicle_sk
        LEFT JOIN dim_geofence g ON s.geofence_sk = g.geofence_sk
        {where}
        ORDER BY s.minutes DESC
    """), e, params=({"veh": vehicle} if vehicle else {}))
    out = []
    for r in df.itertuples():
        p = _poi_obj(r.poi_name, r.poi_category, r.poi_distance_m)
        out.append({
            "vehicle_reg": r.vehicle_reg,
            "arrive": str(r.arrive_ts), "depart": str(r.depart_ts),
            "minutes": round(float(r.minutes), 0),
            "lat": round(float(r.lat), 6), "lng": round(float(r.lng), 6),
            "reason": r.reason_inferred, "type": r.type,
            "poi": p,
            "where": poi.label_for_stop(p, r.address, r.node_name),
        })
    return out
