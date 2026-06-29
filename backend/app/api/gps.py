"""
GPS intelligence API — everything we can squeeze out of the raw device feed
(``raw.gps_feed``), served from the warehouse when full, the Excel otherwise.

Every endpoint here works on data that is 100% present in the feed (position,
speed, odometer, route nodes, signal, timestamps), so nothing is blocked the
way the legacy fuel/RPM/driver models were.

Endpoints (prefix /api/v1/gps):
    GET /status         where the data is served from + coverage
    GET /vehicles       vehicles seen in the feed
    GET /kpis           headline KPIs (distance, drive/idle time, speed, stops…)
    GET /track          decimated lat/lng track for the map (+ moving flag)
    GET /trips          reconstructed movement sessions (trip-from-GPS)
    GET /stops          stop episodes = candidate geofences (depot/customer/halt)
    GET /speed-profile  speed over time + over-speed segments + histogram
    GET /alerts         decoded alert/event timeline (signal drops, event flags)
    GET /corridor       route-node sequence + state border crossings
    GET /device-health  ping cadence, latency, gaps, position jumps
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Query

from lakehouse import warehouse

router = APIRouter(prefix="/gps", tags=["gps"])

# ---- speed band (no road_speed_limit in feed; use a fleet policy threshold) ----
# All tunables come from .env (the single source of config) with safe fallbacks.
OVERSPEED_KPH = float(os.environ.get("OVERSPEED_KPH", "60"))   # ping speed above this = over-speed
MOVING_KPH = float(os.environ.get("MOVING_KPH", "2"))         # ping speed above this = moving (vs stopped)
STOP_MIN_MINUTES = float(os.environ.get("STOP_MIN_MINUTES", "12"))  # min dwell to count as a stop
POI_RADIUS_M = int(os.environ.get("POI_RADIUS_M", "200"))           # search radius for nearby named places


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _load(vehicle: str | None = None) -> pd.DataFrame:
    # push the vehicle filter into SQL so N-truck reads stay fast
    df = warehouse.read_gps_feed(vehicle=vehicle)
    if df.empty:
        return df
    df = df.copy()
    df["gps_ts"] = pd.to_datetime(df["gps_ts"], errors="coerce")
    df = df.dropna(subset=["gps_ts"]).sort_values("gps_ts")
    if vehicle and "vehicle_reg" in df.columns:
        df = df[df["vehicle_reg"] == vehicle]
    # unify the speed column we trust
    df["speed"] = df["speed_corr_kph"].fillna(df["speed_kph"]).fillna(0).astype(float)
    df["moving"] = df["speed"] > MOVING_KPH
    df["gap_sec"] = df["gps_ts"].diff().dt.total_seconds().fillna(0)
    return df.reset_index(drop=True)


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _clean(v):
    """Make a value JSON-safe (no NaN/inf, no numpy scalars/timestamps)."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
    if isinstance(v, (pd.Timestamp,)):
        return None if pd.isna(v) else v.isoformat()
    if v is pd.NaT or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


def _f(v, nd=2):
    try:
        f = float(v)
        return 0.0 if (np.isnan(f) or np.isinf(f)) else round(f, nd)
    except Exception:
        return 0.0


def _empty(msg="no gps data — upload the feed first"):
    return {"error": msg, "vehicles": [], "kpis": {}, "rows": []}


# ----------------------------------------------------------------------
# status / vehicles
# ----------------------------------------------------------------------
@router.get("/status")
def status():
    df = _load()
    if df.empty:
        return {"source": warehouse.gps_source_label(), "loaded": False,
                "warehouse_available": warehouse.is_available()}
    return {
        "source": warehouse.gps_source_label(),
        "warehouse_available": warehouse.is_available(),
        "loaded": True,
        "rows": int(len(df)),
        "vehicles": int(df["vehicle_reg"].nunique()),
        "devices": int(df["device_id"].nunique()),
        "from": _clean(df["gps_ts"].min()),
        "to": _clean(df["gps_ts"].max()),
    }


@router.get("/fleet")
def fleet():
    """Fleet table source: one row per truck (vehicle + IoT device + coverage +
    online/stale/offline). Fast aggregate — scales to thousands of trucks."""
    from lakehouse import gps_store
    rows = gps_store.fleet()
    return {
        "fleet": rows,
        "summary": {
            "trucks": len({r["vehicle_reg"] for r in rows}),
            "devices": len({r["device_imei"] for r in rows if r["device_imei"] != "—"}),
            "online": sum(1 for r in rows if r["status"] == "online"),
            "stale": sum(1 for r in rows if r["status"] == "stale"),
            "offline": sum(1 for r in rows if r["status"] == "offline"),
        },
    }


@router.get("/vehicles")
def vehicles():
    df = _load()
    if df.empty:
        return {"vehicles": []}
    out = []
    for vid, g in df.groupby("vehicle_reg"):
        out.append({
            "vehicle_reg": vid,
            "entity_name": g["entity_name"].dropna().iloc[0] if g["entity_name"].notna().any() else "",
            "device_id": g["device_id"].dropna().iloc[0] if g["device_id"].notna().any() else "",
            "pings": int(len(g)),
            "first_seen": _clean(g["gps_ts"].min()),
            "last_seen": _clean(g["gps_ts"].max()),
            "distance_km": _f((g["odometer_m"].max() - g["odometer_m"].min()) / 1000),
            "max_speed": _f(g["speed"].max(), 0),
        })
    return {"vehicles": out}


# ----------------------------------------------------------------------
# KPIs
# ----------------------------------------------------------------------
@router.get("/kpis")
def kpis(vehicle: str | None = Query(None)):
    df = _load(vehicle)
    if df.empty:
        return _empty()

    # time accounting: attribute each ping's preceding gap to moving/idle,
    # ignoring outsized gaps (device offline) above 15 min.
    g = df.copy()
    g["gap_min"] = g["gap_sec"].clip(upper=900) / 60.0
    drive_min = g.loc[g["moving"], "gap_min"].sum()
    idle_min = g.loc[~g["moving"], "gap_min"].sum()

    dist_km = (g["odometer_m"].max() - g["odometer_m"].min()) / 1000 if g["odometer_m"].notna().any() else 0
    span_h = max((g["gps_ts"].max() - g["gps_ts"].min()).total_seconds() / 3600, 1e-9)
    stops = _detect_stops(g)
    over = g[g["speed"] > OVERSPEED_KPH]

    return {
        "vehicle": vehicle or "ALL",
        "kpis": {
            "total_pings": int(len(g)),
            "distance_km": _f(dist_km),
            "active_days": int(g["gps_ts"].dt.date.nunique()),
            "drive_hours": _f(drive_min / 60),
            "idle_hours": _f(idle_min / 60),
            "utilization_pct": _f(100 * drive_min / max(drive_min + idle_min, 1e-9)),
            "avg_moving_speed": _f(g.loc[g["moving"], "speed"].mean()),
            "max_speed": _f(g["speed"].max(), 0),
            "avg_daily_km": _f(dist_km / max(g["gps_ts"].dt.date.nunique(), 1)),
            "stop_count": len(stops),
            "longest_stop_min": _f(max((s["minutes"] for s in stops), default=0), 0),
            "overspeed_pings": int(len(over)),
            "overspeed_pct": _f(100 * len(over) / max(len(g), 1)),
            "states_covered": int(pd.concat([g["from_state"], g["to_state"]]).dropna().nunique()),
            "avg_signal_pct": _f(g["signal_pct"].mean(), 0),
            "event_flag_pings": int(g["event_codes"].notna().sum()),
        },
    }


# ----------------------------------------------------------------------
# map track (decimated)
# ----------------------------------------------------------------------
@router.get("/track")
def track(vehicle: str | None = Query(None), max_points: int = 2000,
          bucket_min: float = 0, frm: str | None = Query(None, alias="from"),
          to: str | None = Query(None)):
    """Map track, downsampled on demand so we never ship millions of points.

    bucket_min > 0  -> merge each N-minute window into one representative point
                       (last fix in the window) carrying that window's distance
                       and avg/max speed. Set bucket_min=10..15 for huge feeds.
    from / to        -> ISO datetimes to page through a time range.

    For bucket_min == 15 we serve the PRE-AGGREGATED fact_gps_15min rollup
    (computed at ingest) — no raw-ping scan, so it stays instant at any scale.
    """
    # Fast path: pre-aggregated 15-min rollup, no raw scan.
    if bucket_min == 15:
        from lakehouse import gps_store
        r = gps_store.read_rollup(vehicle, frm, to)
        if not r.empty:
            r = r.dropna(subset=["lat", "lng"])
            pts = [
                {"t": _clean(row.bucket_ts), "lat": _f(row.lat, 6), "lng": _f(row.lng, 6),
                 "spd": _f(row.avg_speed, 0), "max_spd": _f(row.max_speed, 0),
                 "km": _f(row.dist_km), "mv": bool(row.moving_frac > 0.4)}
                for row in r.itertuples()
            ]
            return {"points": pts, "count": len(pts), "bucket_min": 15, "source": "rollup",
                    "bbox": {"min_lat": _f(r["lat"].min(), 6), "max_lat": _f(r["lat"].max(), 6),
                             "min_lng": _f(r["lng"].min(), 6), "max_lng": _f(r["lng"].max(), 6)}}

    df = _load(vehicle)
    if df.empty:
        return {"points": [], "bbox": None, "count": 0}
    g = df.dropna(subset=["latitude", "longitude"])
    g = g[(g["latitude"].between(-90, 90)) & (g["longitude"].between(-180, 180))]
    g = g[(g["latitude"] != 0) | (g["longitude"] != 0)]
    if frm:
        g = g[g["gps_ts"] >= pd.Timestamp(frm)]
    if to:
        g = g[g["gps_ts"] <= pd.Timestamp(to)]
    if g.empty:
        return {"points": [], "bbox": None, "count": 0}

    if bucket_min and bucket_min > 0:
        gg = g.set_index("gps_ts")
        bucket = f"{int(bucket_min)}min"
        agg = gg.resample(bucket).agg(
            lat=("latitude", "last"), lng=("longitude", "last"),
            avg_spd=("speed", "mean"), max_spd=("speed", "max"),
            moving=("moving", "mean"), odo_min=("odometer_m", "min"), odo_max=("odometer_m", "max"),
        ).dropna(subset=["lat", "lng"])
        pts = [
            {"t": _clean(idx), "lat": _f(r.lat, 6), "lng": _f(r.lng, 6),
             "spd": _f(r.avg_spd, 0), "max_spd": _f(r.max_spd, 0),
             "km": _f((r.odo_max - r.odo_min) / 1000), "mv": bool(r.moving > 0.4)}
            for idx, r in agg.iterrows()
        ]
    else:
        if len(g) > max_points:
            step = int(np.ceil(len(g) / max_points))
            g = g.iloc[::step]
        pts = [
            {"t": _clean(r.gps_ts), "lat": _f(r.latitude, 6), "lng": _f(r.longitude, 6),
             "spd": _f(r.speed, 0), "mv": bool(r.moving)}
            for r in g.itertuples()
        ]
    return {
        "points": pts,
        "bbox": {
            "min_lat": _f(g["latitude"].min(), 6), "max_lat": _f(g["latitude"].max(), 6),
            "min_lng": _f(g["longitude"].min(), 6), "max_lng": _f(g["longitude"].max(), 6),
        },
        "count": len(pts),
        "bucket_min": bucket_min,
    }


@router.post("/build-geofences")
def build_geofences(vehicle: str | None = Query(None), min_minutes: float = STOP_MIN_MINUTES):
    """Detect stops, cluster them into reusable geofences (DBSCAN), and infer the
    reason for each stop (rest/lunch/dinner/tea/loading/halt). Fast + local."""
    from lakehouse import geofence
    return geofence.build_geofences_and_stops(min_minutes=min_minutes, vehicle=vehicle)


@router.post("/geocode")
def geocode(limit: int = 20):
    """Reverse-geocode geofences without an address yet (Nominatim, rate-limited,
    cached in the DB). Returns how many were resolved + how many remain."""
    from lakehouse import geofence
    return geofence.geocode_pending(limit=limit)


@router.post("/enrich-poi")
def enrich_poi(limit: int = 20, radius_m: int = POI_RADIUS_M):
    """Resolve the nearest *named* place (dhaba/hotel/fuel/café) for stop geofences
    via OpenStreetMap Overpass — turns a bare address into the actual venue a driver
    used. Rate-limited + cached on dim_geofence; safe to re-run."""
    from lakehouse import geofence
    return geofence.enrich_poi(limit=limit, radius_m=radius_m)


@router.get("/geofences")
def geofences():
    """All discovered geofences with visit counts, dwell totals, type and address."""
    from lakehouse import geofence
    return {"geofences": geofence.list_geofences()}


@router.get("/stop-events")
def stop_events(vehicle: str | None = Query(None)):
    """Enriched stop log: when/where/how long + inferred reason + address."""
    from lakehouse import geofence
    return {"stops": geofence.list_stop_events(vehicle)}


# ----------------------------------------------------------------------
# halts & rests — the stop taxonomy, served as its own analytics section
# ----------------------------------------------------------------------
# Keep this in sync with lakehouse/geofence._infer_reason(). Each entry
# documents HOW the reason is inferred and WHAT it means, so the UI can
# explain every category by its name and workings.
HALT_TAXONOMY: list[dict] = [
    {"reason": "Night rest",        "rule": "≥ 6 h, arriving 20:00–05:59",
     "purpose": "Overnight driver rest / mandatory sleep", "kind": "rest_stop"},
    {"reason": "Long halt",         "rule": "≥ 6 h, daytime arrival",
     "purpose": "Extended daytime standstill (yard wait / breakdown)", "kind": "facility"},
    {"reason": "Extended halt",     "rule": "> 1 h 40 m",
     "purpose": "Long stop — loading, queue or layover", "kind": "facility"},
    {"reason": "Lunch break",       "rule": "25–100 min, 11:00–15:00",
     "purpose": "Midday meal stop", "kind": "eatery"},
    {"reason": "Dinner break",      "rule": "25–100 min, 19:00–23:00",
     "purpose": "Evening meal stop", "kind": "eatery"},
    {"reason": "Tea / short break", "rule": "8–25 min",
     "purpose": "Quick tea / restroom break", "kind": "halt"},
    {"reason": "Halt",              "rule": "any other qualifying stop",
     "purpose": "Unclassified short standstill", "kind": "halt"},
]
_HALT_ORDER = {t["reason"]: i for i, t in enumerate(HALT_TAXONOMY)}


@router.get("/halts")
def halts(vehicle: str | None = Query(None)):
    """Halts & rests as a first-class section: every stop event from the
    warehouse, plus a by-category breakdown and headline KPIs. Each category
    carries the rule it was inferred from so the UI explains itself."""
    from lakehouse import geofence
    events = geofence.list_stop_events(vehicle)

    # per-category aggregation, seeded so every taxonomy row is always present
    cats: dict[str, dict] = {
        t["reason"]: {**t, "count": 0, "total_min": 0.0, "longest_min": 0.0}
        for t in HALT_TAXONOMY
    }
    total_min = 0.0
    longest = None
    places: set[str] = set()
    for ev in events:
        r = ev.get("reason") or "Halt"
        c = cats.setdefault(r, {"reason": r, "rule": "—", "purpose": "—",
                                "kind": "halt", "count": 0, "total_min": 0.0, "longest_min": 0.0})
        m = float(ev.get("minutes") or 0)
        c["count"] += 1
        c["total_min"] += m
        c["longest_min"] = max(c["longest_min"], m)
        total_min += m
        if ev.get("where"):
            places.add(str(ev["where"]))
        if longest is None or m > float(longest.get("minutes") or 0):
            longest = ev

    categories = []
    for r, c in cats.items():
        cnt = c["count"]
        categories.append({
            "reason": r, "rule": c["rule"], "purpose": c["purpose"], "kind": c["kind"],
            "count": cnt,
            "total_min": round(c["total_min"], 0),
            "avg_min": round(c["total_min"] / cnt, 0) if cnt else 0,
            "longest_min": round(c["longest_min"], 0),
            "share_pct": round(100 * c["total_min"] / total_min, 1) if total_min else 0.0,
        })
    categories.sort(key=lambda x: (_HALT_ORDER.get(x["reason"], 99)))

    rest_min = sum(c["total_min"] for c in categories if c["kind"] == "rest_stop")
    return {
        "vehicle": vehicle or "ALL",
        "kpis": {
            "total_halts": len(events),
            "total_hours": round(total_min / 60, 1),
            "rest_hours": round(rest_min / 60, 1),
            "longest_min": round(float(longest["minutes"]), 0) if longest else 0,
            "longest_where": (longest.get("where") if longest else None),
            "distinct_places": len(places),
            "avg_min": round(total_min / len(events), 0) if events else 0,
            "categories_seen": sum(1 for c in categories if c["count"] > 0),
        },
        "categories": categories,
        "events": events,
    }


@router.get("/asset-history")
def asset_history():
    """Full timeline of which IoT device rode on which truck (and, when the feed
    carries it, which driver drove which truck) — so moving a device between
    trucks, or a driver between trucks, stays auditable."""
    from lakehouse import gps_store
    return gps_store.asset_history()


# ----------------------------------------------------------------------
# stop detection (candidate geofences) — runs of STOPPED pings
# ----------------------------------------------------------------------
def _detect_stops(df: pd.DataFrame, min_minutes: float = 10) -> list[dict]:
    g = df.dropna(subset=["latitude", "longitude"]).copy()
    if g.empty:
        return []
    # group consecutive stopped pings
    g["blk"] = (g["moving"] != g["moving"].shift()).cumsum()
    stops = []
    for _, blk in g[~g["moving"]].groupby("blk"):
        mins = (blk["gps_ts"].max() - blk["gps_ts"].min()).total_seconds() / 60
        if mins < min_minutes:
            continue
        stops.append({
            "start": _clean(blk["gps_ts"].min()),
            "end": _clean(blk["gps_ts"].max()),
            "minutes": _f(mins, 0),
            "lat": _f(blk["latitude"].median(), 6),
            "lng": _f(blk["longitude"].median(), 6),
            "near": (blk["from_node"].mode().iloc[0] if blk["from_node"].notna().any() else None),
            "state": (blk["from_state"].mode().iloc[0] if blk["from_state"].notna().any() else None),
        })
    return sorted(stops, key=lambda s: s["minutes"], reverse=True)


@router.get("/stops")
def stops(vehicle: str | None = Query(None), min_minutes: float = 10):
    df = _load(vehicle)
    if df.empty:
        return {"stops": []}
    return {"stops": _detect_stops(df, min_minutes)}


# ----------------------------------------------------------------------
# trip reconstruction — split on long stops (>30 min)
# ----------------------------------------------------------------------
@router.get("/trips")
def trips(vehicle: str | None = Query(None), split_minutes: float = 30):
    """Reconstruct trips from GPS alone (no trip_id in the feed).

    The device keeps pinging while parked, so trips can't be split on ping gaps.
    Instead we split on *long stops*: a STOPPED run lasting > split_minutes ends
    the current trip. Everything between two long stops that contains real
    movement is one reconstructed trip.
    """
    df = _load(vehicle)
    if df.empty:
        return {"trips": []}
    g = df.copy()

    # run-length blocks of constant motion state
    g["blk"] = (g["moving"] != g["moving"].shift()).cumsum()
    blk_dur = g.groupby("blk").apply(
        lambda b: (b["gps_ts"].max() - b["gps_ts"].min()).total_seconds() / 60,
        include_groups=False,
    )
    # a separator = a stopped block longer than split_minutes
    stopped_blocks = g.groupby("blk")["moving"].first()
    is_sep = (~stopped_blocks) & (blk_dur > split_minutes)
    sep_ids = set(is_sep[is_sep].index)

    # assign a trip id that increments after each separator block
    trip_id, ids = 0, []
    prev_sep = False
    for b in g["blk"]:
        if b in sep_ids:
            if not prev_sep:
                trip_id += 1
            prev_sep = True
        else:
            prev_sep = False
        ids.append(trip_id if b not in sep_ids else -1)
    g["trip_id"] = ids

    out = []
    n = 0
    for tid, seg in g[g["trip_id"] >= 0].groupby("trip_id"):
        if seg["moving"].sum() < 3:
            continue
        dist = (seg["odometer_m"].max() - seg["odometer_m"].min()) / 1000
        dur = (seg["gps_ts"].max() - seg["gps_ts"].min()).total_seconds() / 60
        if dur <= 0 or dist < 0.5:
            continue
        n += 1
        out.append({
            "trip": n,
            "start": _clean(seg["gps_ts"].min()),
            "end": _clean(seg["gps_ts"].max()),
            "duration_min": _f(dur, 0),
            "distance_km": _f(dist),
            "moving_pct": _f(100 * seg["moving"].mean()),
            "avg_speed": _f(seg.loc[seg["moving"], "speed"].mean()),
            "max_speed": _f(seg["speed"].max(), 0),
            "from_node": (seg["from_node"].dropna().iloc[0] if seg["from_node"].notna().any() else None),
            "to_node": (seg["to_node"].dropna().iloc[-1] if seg["to_node"].notna().any() else None),
        })
    return {"trips": out}


# ----------------------------------------------------------------------
# journeys — reconstructed trips enriched with their halts (POI-aware)
# ----------------------------------------------------------------------
@router.get("/journeys")
def journeys(vehicle: str | None = Query(None), split_minutes: float = 30):
    """A vehicle's journeys (reconstructed trips) with resolved place names and the
    halts that fall within each one — the master list the Halts page drills into.
    Place fields are waypoint/POI names, never raw coordinates."""
    trip_list = trips(vehicle, split_minutes).get("trips", [])
    from lakehouse import geofence
    stops = geofence.list_stop_events(vehicle)
    parsed = [(pd.to_datetime(s.get("arrive"), errors="coerce"), s) for s in stops]

    out = []
    for t in trip_list:
        start = pd.to_datetime(t.get("start"), errors="coerce")
        end = pd.to_datetime(t.get("end"), errors="coerce")
        halts = [s for (ts, s) in parsed
                 if pd.notna(ts) and pd.notna(start) and pd.notna(end) and start <= ts <= end]
        halts.sort(key=lambda s: s.get("arrive") or "")
        out.append({
            **t,
            "from_place": t.get("from_node") or "—",
            "to_place": t.get("to_node") or "—",
            "halts": halts,
            "halt_count": len(halts),
            "halt_minutes": round(sum(float(h.get("minutes") or 0) for h in halts), 0),
        })
    return {"vehicle": vehicle or "ALL", "journeys": out}


# ----------------------------------------------------------------------
# driving behaviour — how this truck is driven (by time of day)
# ----------------------------------------------------------------------
@router.get("/behaviour")
def behaviour(vehicle: str | None = Query(None)):
    """Driving-style analytics for one truck: speed by hour-of-day, a day×hour
    heatmap, night-driving / over-speed / harsh-event rates, a 0–100 style score,
    and the last few journeys — everything from the raw GPS feed."""
    df = _load(vehicle)
    if df.empty:
        return {"error": "no gps data", "vehicle": vehicle or "ALL"}
    g = df.copy()
    g["hour"] = g["gps_ts"].dt.hour
    g["dow"] = g["gps_ts"].dt.dayofweek      # 0 = Monday
    moving = g[g["moving"]]

    # speed by hour-of-day
    by_hour = []
    for h in range(24):
        sub = g[g["hour"] == h]
        mv = sub[sub["moving"]]
        by_hour.append({
            "hour": h,
            "avg_speed": _f(mv["speed"].mean(), 1) if len(mv) else 0.0,
            "max_speed": _f(sub["speed"].max(), 0) if len(sub) else 0.0,
            "pings": int(len(sub)),
            "moving_pct": _f(100 * len(mv) / len(sub), 0) if len(sub) else 0.0,
        })

    # heatmap: avg moving speed + activity (ping count) per [dow][hour]
    spd_sum = [[0.0] * 24 for _ in range(7)]
    cnt = [[0] * 24 for _ in range(7)]
    for r in g.itertuples():
        spd_sum[r.dow][r.hour] += r.speed if r.moving else 0.0
        cnt[r.dow][r.hour] += 1
    speed_matrix = [[round(spd_sum[d][h] / cnt[d][h], 1) if cnt[d][h] else 0.0 for h in range(24)] for d in range(7)]
    activity_matrix = [[cnt[d][h] for h in range(24)] for d in range(7)]
    max_activity = max((max(row) for row in activity_matrix), default=0)

    # style metrics
    g["dspd"] = g["speed"].diff()
    harsh_accel = int((g["dspd"] > 25).sum())
    harsh_brake = int((g["dspd"] < -25).sum())
    night = g[(g["hour"] >= 22) | (g["hour"] <= 4)]
    night_moving = int(night["moving"].sum())
    night_pct = _f(100 * night_moving / max(int(moving["moving"].count()), 1), 0)
    overspeed_pct = _f(100 * (g["speed"] > OVERSPEED_KPH).sum() / max(len(g), 1), 1)
    harsh_per_100 = _f(100 * (harsh_accel + harsh_brake) / max(len(g), 1), 1)
    score = max(0.0, min(100.0, 100 - overspeed_pct * 1.5 - harsh_per_100 * 4 - float(night_pct) * 0.2))

    # busiest driving window
    hour_move = [(h, by_hour[h]["moving_pct"]) for h in range(24)]
    peak_hour = max(hour_move, key=lambda x: x[1])[0] if hour_move else 0

    recent = trips(vehicle).get("trips", [])
    recent = list(reversed(recent))[:6]

    return {
        "vehicle": vehicle or "ALL",
        "score": round(score),
        "metrics": {
            "avg_moving_speed": _f(moving["speed"].mean(), 1) if len(moving) else 0.0,
            "max_speed": _f(g["speed"].max(), 0),
            "night_pct": night_pct,
            "overspeed_pct": overspeed_pct,
            "harsh_accel": harsh_accel,
            "harsh_brake": harsh_brake,
            "peak_hour": peak_hour,
            "active_days": int(g["gps_ts"].dt.date.nunique()),
        },
        "by_hour": by_hour,
        "heatmap": {"speed": speed_matrix, "activity": activity_matrix, "max_activity": max_activity},
        "recent_journeys": recent,
    }


# ----------------------------------------------------------------------
# speed profile
# ----------------------------------------------------------------------
@router.get("/speed-profile")
def speed_profile(vehicle: str | None = Query(None), max_points: int = 1500):
    df = _load(vehicle)
    if df.empty:
        return {"series": [], "histogram": [], "overspeed_segments": []}
    g = df.copy()
    series_src = g
    if len(g) > max_points:
        step = int(np.ceil(len(g) / max_points))
        series_src = g.iloc[::step]
    series = [{"t": _clean(r.gps_ts), "spd": _f(r.speed, 0)} for r in series_src.itertuples()]

    bins = list(range(0, 90, 10))
    hist = pd.cut(g["speed"], bins=bins + [999], right=False).value_counts().sort_index()
    histogram = [{"band": f"{int(iv.left)}-{int(iv.right) if iv.right < 999 else '+'}",
                  "count": int(c)} for iv, c in hist.items()]

    # contiguous over-speed segments
    g["ovr"] = g["speed"] > OVERSPEED_KPH
    g["blk"] = (g["ovr"] != g["ovr"].shift()).cumsum()
    segs = []
    for _, blk in g[g["ovr"]].groupby("blk"):
        segs.append({
            "start": _clean(blk["gps_ts"].min()),
            "end": _clean(blk["gps_ts"].max()),
            "peak_kph": _f(blk["speed"].max(), 0),
            "minutes": _f((blk["gps_ts"].max() - blk["gps_ts"].min()).total_seconds() / 60, 1),
            "near": (blk["from_node"].mode().iloc[0] if blk["from_node"].notna().any() else None),
        })
    return {
        "threshold_kph": OVERSPEED_KPH,
        "series": series,
        "histogram": histogram,
        "overspeed_segments": sorted(segs, key=lambda s: s["peak_kph"], reverse=True)[:25],
    }


# ----------------------------------------------------------------------
# alerts / events timeline (decoded LOV)
# ----------------------------------------------------------------------
@router.get("/alerts")
def alerts(vehicle: str | None = Query(None)):
    df = _load(vehicle)
    if df.empty:
        return {"events": [], "signal_drops": []}
    g = df.copy()
    events = [
        {"t": _clean(r.gps_ts), "codes": r.event_codes, "lat": _f(r.latitude, 6),
         "lng": _f(r.longitude, 6), "near": r.from_node, "speed": _f(r.speed, 0)}
        for r in g[g["event_codes"].notna()].itertuples()
    ]
    # signal drops: signal_pct <= 40
    drops = g[g["signal_pct"].notna() & (g["signal_pct"] <= 40)].copy()
    drops["blk"] = (drops["gps_ts"].diff().dt.total_seconds().fillna(0) > 300).cumsum()
    drop_out = []
    for _, blk in drops.groupby("blk"):
        drop_out.append({
            "start": _clean(blk["gps_ts"].min()),
            "end": _clean(blk["gps_ts"].max()),
            "min_signal": _f(blk["signal_pct"].min(), 0),
            "pings": int(len(blk)),
            "near": (blk["from_node"].mode().iloc[0] if blk["from_node"].notna().any() else None),
        })
    return {"events": events, "signal_drops": drop_out[:50]}


# ----------------------------------------------------------------------
# route corridor — node sequence + state crossings
# ----------------------------------------------------------------------
@router.get("/corridor")
def corridor(vehicle: str | None = Query(None)):
    df = _load(vehicle)
    if df.empty:
        return {"node_sequence": [], "state_crossings": [], "top_lanes": []}
    g = df.copy()

    # ordered node-pair sequence (collapse consecutive duplicates)
    g["lane"] = g["from_node"].astype(str) + " → " + g["to_node"].astype(str)
    seq = g["lane"][g["lane"] != g["lane"].shift()]
    node_seq = [{"at": _clean(g.loc[i, "gps_ts"]), "lane": seq.loc[i]} for i in seq.index][:200]

    # state crossings: when the active 'from_state' changes
    st = g.dropna(subset=["from_state"]).copy()
    st["chg"] = st["from_state"] != st["from_state"].shift()
    crossings = [
        {"at": _clean(r.gps_ts), "to_state": r.from_state, "near": r.from_node,
         "lat": _f(r.latitude, 6), "lng": _f(r.longitude, 6)}
        for r in st[st["chg"]].itertuples()
    ]

    lanes = (g["lane"].value_counts().head(15)
             .rename_axis("lane").reset_index(name="pings"))
    top_lanes = [{"lane": r["lane"], "pings": int(r["pings"])} for _, r in lanes.iterrows()]
    return {"node_sequence": node_seq, "state_crossings": crossings, "top_lanes": top_lanes}


# ----------------------------------------------------------------------
# device health — cadence, latency, gaps, position jumps
# ----------------------------------------------------------------------
@router.get("/device-health")
def device_health(vehicle: str | None = Query(None)):
    df = _load(vehicle)
    if df.empty:
        return {"summary": {}, "gaps": []}
    g = df.copy()
    g["lat_p"] = g["latitude"].shift()
    g["lng_p"] = g["longitude"].shift()
    mask = g["lat_p"].notna()
    g.loc[mask, "jump_km"] = _haversine_km(g.loc[mask, "lat_p"], g.loc[mask, "lng_p"],
                                           g.loc[mask, "latitude"], g.loc[mask, "longitude"])
    gaps = g[g["gap_sec"] > 300]
    gap_rows = [
        {"at": _clean(r.gps_ts), "gap_min": _f(r.gap_sec / 60, 1), "near": r.from_node}
        for r in gaps.itertuples()
    ]
    return {
        "summary": {
            "median_ping_sec": _f(g["gap_sec"][g["gap_sec"] > 0].median(), 0),
            "p95_ping_sec": _f(g["gap_sec"][g["gap_sec"] > 0].quantile(0.95), 0),
            "max_gap_min": _f(g["gap_sec"].max() / 60, 1),
            "avg_latency_sec": _f(g["latency_sec"].mean() if "latency_sec" in g else 0, 1),
            "max_latency_sec": _f(g["latency_sec"].max() if "latency_sec" in g else 0, 0),
            "max_jump_km": _f(g.get("jump_km", pd.Series([0])).max(), 2),
            "zero_coord_pings": int(((g["latitude"] == 0) & (g["longitude"] == 0)).sum()),
            "uptime_pct": _f(100 * (g["gap_sec"] <= 120).mean()),
        },
        "gaps": sorted(gap_rows, key=lambda x: x["gap_min"], reverse=True)[:30],
    }
