"""
Analytics that work on the REAL sample data we have.

Centred on what the data actually contains:
  * GPS pings (lat/lng, speed, heading, ignition, odometer) - 100% present
  * Trip commercial header (vehicle, transporter, shipper, origin) - 100% present
  * Lane metadata (origin_text, destination)

Avoiding columns that are mostly NULL in the sample
(fuel, RPM, battery, detention, PoD, road_speed_limit, geofence_id).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter

from lakehouse.mock_data import get_mock_table

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _safe_float(v) -> float:
    """Convert pandas/numpy floats to JSON-safe values (no NaN/inf)."""
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return 0.0
        return round(f, 2)
    except Exception:
        return 0.0


# ----------------------------------------------------------------------
# Data quality assessment — what's null, what's not, what's blocked
# ----------------------------------------------------------------------

# Map of "promised features" to required columns. Each feature is graded by
# the worst column it depends on.
FEATURE_DEPENDENCIES = {
    "Dynamic ETA prediction":      ["trip_actual_end_ts", "total_distance_km", "trip_start_ts"],
    "Delay-risk classifier":       ["delay_minutes", "trip_actual_arrival_ts", "trip_planned_eta_ts"],
    "Driver risk score":           ["driver_id", "driver_sk", "speed", "ignition_status"],
    "Telemetry anomaly":           ["latitude", "longitude", "speed", "gps_timestamp"],
    "Fuel pilferage":              ["fuel_level_pct", "fuel_liters", "odometer"],
    "Detention prediction":        ["plant_detention_mins", "leg_actual_arrival_ts"],
    "Geofence dwell anomaly":      ["geofence_id", "motion_status", "ignition_status"],
    "Predictive maintenance":      ["battery_voltage", "engine_rpm", "fuel_liters"],
    "Route deviation":             ["latitude", "longitude", "trip_id"],
    "Lane discovery":              ["origin_text", "dest_text"],
    "Vehicle behavioural rhythm":  ["vehicle_id", "gps_timestamp", "speed", "ignition_status"],
    "Lane volume / popularity":    ["vehicle_id", "origin_text", "trip_start_ts"],
    "PoD / payment cycle":         ["leg_pod_received_ts"],
    "Speeding detection":          ["road_speed_limit", "speed"],
}

TABLES_WITH_COLS = {
    "fact_trips":           ["fact_trips"],
    "fact_trip_legs":       ["fact_trip_legs"],
    "gps_telemetry_events": ["gps_telemetry_events"],
    "gps_events":           ["gps_events"],
}


def _column_health(table: str, df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    n = len(df) or 1
    for col in df.columns:
        nulls = int(df[col].isna().sum())
        # treat all-zero numeric columns as a softer "no signal" issue
        all_zero = False
        try:
            all_zero = pd.api.types.is_numeric_dtype(df[col]) and df[col].fillna(0).abs().sum() == 0
        except Exception:
            pass
        pct = nulls / n * 100
        if pct >= 100:    status = "missing"
        elif pct >= 50:   status = "sparse"
        elif pct > 0:     status = "partial"
        elif all_zero:    status = "zero"
        else:             status = "ok"
        out.append({
            "table": table,
            "column": col,
            "null_pct": round(pct, 1),
            "all_zero": all_zero,
            "status": status,
        })
    return out


@router.get("/quality")
def data_quality():
    rows: list[dict[str, Any]] = []
    for tbl in ["fact_trips", "fact_trip_legs", "gps_events", "gps_telemetry_events"]:
        try:
            df = get_mock_table(tbl)
            rows.extend(_column_health(tbl, df))
        except Exception as exc:
            rows.append({"table": tbl, "column": "(error)", "null_pct": 100, "status": "missing",
                         "error": str(exc)})

    # Roll-up per table
    by_table = defaultdict(lambda: {"ok": 0, "partial": 0, "sparse": 0, "zero": 0, "missing": 0, "total": 0})
    for r in rows:
        by_table[r["table"]]["total"] += 1
        by_table[r["table"]][r["status"]] += 1

    # Feature-readiness
    available_cols = {(r["table"], r["column"]): r for r in rows}
    feature_status = []
    for feat, cols in FEATURE_DEPENDENCIES.items():
        worst = "ok"
        missing = []
        for c in cols:
            # find this column in any table it lives in
            candidates = [r for (_, cc), r in available_cols.items() if cc == c]
            if not candidates:
                worst = "missing"
                missing.append(c)
                continue
            for cand in candidates:
                rank = {"ok": 0, "partial": 1, "zero": 2, "sparse": 3, "missing": 4}
                if rank[cand["status"]] > rank[worst]:
                    worst = cand["status"]
            if all(cand["status"] in ("missing", "sparse") for cand in candidates):
                missing.append(c)
        verdict = {
            "ok":      "READY",
            "partial": "MOSTLY READY",
            "zero":    "DEGRADED (zeros)",
            "sparse":  "BLOCKED — sparse",
            "missing": "BLOCKED — missing column",
        }[worst]
        feature_status.append({
            "feature": feat,
            "verdict": verdict,
            "worst_status": worst,
            "blocking_columns": missing,
            "required": cols,
        })

    return {
        "columns": rows,
        "tables_summary": [{"table": k, **v} for k, v in by_table.items()],
        "feature_readiness": feature_status,
    }


# ----------------------------------------------------------------------
# Behavioural patterns — per-vehicle rhythm derived from GPS
# ----------------------------------------------------------------------

def _vehicle_gps(vehicle_id: str | None = None) -> pd.DataFrame:
    # Try lean stream first — it's what the lakehouse actually publishes today.
    # Fall back to the richer stream when lean is empty.
    df = get_mock_table("gps_events")
    if df.empty:
        df = get_mock_table("gps_telemetry_events")
    if df.empty:
        return df
    df = df.copy()
    df["gps_timestamp"] = pd.to_datetime(df["gps_timestamp"], errors="coerce")
    df = df.dropna(subset=["gps_timestamp"])
    if vehicle_id:
        df = df[df["vehicle_id"] == vehicle_id]
    df = df.sort_values("gps_timestamp")
    return df


@router.get("/vehicles")
def list_vehicles():
    """Vehicles observed in GPS + their basic stats."""
    df = _vehicle_gps()
    if df.empty:
        return {"vehicles": []}
    grp = df.groupby("vehicle_id")
    out = []
    for vid, g in grp:
        out.append({
            "vehicle_id": str(vid),
            "entity_name": str(g["entity_name"].iloc[0]) if "entity_name" in g and pd.notna(g["entity_name"].iloc[0]) else "",
            "device_id":   str(g["device_id"].iloc[0])   if "device_id" in g and pd.notna(g["device_id"].iloc[0]) else "",
            "ping_count": int(len(g)),
            "first_seen": g["gps_timestamp"].min().isoformat(),
            "last_seen":  g["gps_timestamp"].max().isoformat(),
            "avg_speed":  round(float(g["speed"].mean()), 1) if "speed" in g else 0.0,
            "max_speed":  round(float(g["speed"].max()), 1)  if "speed" in g else 0.0,
            "ignition_on_pct": round(float(g["ignition_status"].astype(float).mean()) * 100, 1)
                              if "ignition_status" in g else 0.0,
        })
    return {"vehicles": out}


@router.get("/vehicles/{vehicle_id}/patterns")
def vehicle_patterns(vehicle_id: str):
    """Behavioural pattern bundle for a single vehicle (works as a driver proxy
    because driver_id is null in the sample). Returns:
      * hour_of_day_heatmap  — movement intensity by day-of-week × hour-of-day
      * activity_timeline    — daily ignition/movement/stop ratios
      * sleep_episodes       — long gaps with ignition off (>6h)
      * meal_breaks          — recurring stops 30-90 min
      * tea_breaks           — recurring stops 10-30 min
      * drive_streaks        — longest continuous moving windows
      * calendar_heatmap     — per-day activity score
    """
    df = _vehicle_gps(vehicle_id)
    if df.empty:
        return {"vehicle_id": vehicle_id, "error": "no data"}

    df["hour"] = df["gps_timestamp"].dt.hour
    df["dow"]  = df["gps_timestamp"].dt.dayofweek   # 0 = Mon
    df["date"] = df["gps_timestamp"].dt.date
    df["moving"] = (df["speed"].astype(float) > 5).astype(int)

    # 7×24 heatmap
    pivot = (df.assign(weight=df["moving"])
               .groupby(["dow", "hour"])["weight"].sum()
               .unstack(fill_value=0))
    pivot = pivot.reindex(index=range(7), columns=range(24), fill_value=0)
    heatmap = pivot.values.tolist()
    max_val = int(pivot.values.max() or 1)

    # Activity timeline per day
    timeline = (df.groupby("date")
                  .agg(pings=("speed", "size"),
                       moving=("moving", "sum"),
                       ign_on=("ignition_status", lambda s: int((s.astype(float) > 0).sum())))
                  .reset_index())
    timeline["activity_score"] = (timeline["moving"] / timeline["pings"]).round(2)
    timeline_rows = [
        {"date": str(r["date"]), "pings": int(r["pings"]), "moving": int(r["moving"]),
         "ignition_on": int(r["ign_on"]), "activity_score": float(r["activity_score"])}
        for _, r in timeline.iterrows()
    ]

    # Sleep / meal / tea via gap analysis
    df_gaps = df[["gps_timestamp", "ignition_status", "speed"]].copy()
    df_gaps["gap_min"] = df_gaps["gps_timestamp"].diff().dt.total_seconds().div(60).fillna(0)
    df_gaps["is_off"]  = df_gaps["ignition_status"].astype(float) == 0
    df_gaps["is_idle"] = (df_gaps["speed"].astype(float) < 5)

    def classify_gap(row):
        if row["gap_min"] >= 6 * 60:                          return "sleep"
        if 30 <= row["gap_min"] <= 90 and row["is_idle"]:     return "meal_break"
        if 10 <= row["gap_min"] < 30  and row["is_idle"]:     return "tea_break"
        return None

    df_gaps["episode"] = df_gaps.apply(classify_gap, axis=1)
    eps = df_gaps[df_gaps["episode"].notna()][["gps_timestamp", "gap_min", "episode"]]
    sleep_eps = [{"at": r["gps_timestamp"].isoformat(), "minutes": int(r["gap_min"])}
                 for _, r in eps[eps["episode"] == "sleep"].iterrows()]
    meal_eps  = [{"at": r["gps_timestamp"].isoformat(), "minutes": int(r["gap_min"])}
                 for _, r in eps[eps["episode"] == "meal_break"].iterrows()]
    tea_eps   = [{"at": r["gps_timestamp"].isoformat(), "minutes": int(r["gap_min"])}
                 for _, r in eps[eps["episode"] == "tea_break"].iterrows()]

    # Drive streaks — longest continuous moving stretch per day
    streaks = []
    cur_start = None
    for _, r in df.iterrows():
        if r["moving"]:
            if cur_start is None:
                cur_start = r["gps_timestamp"]
            cur_end = r["gps_timestamp"]
        else:
            if cur_start is not None:
                streaks.append((cur_start, cur_end, (cur_end - cur_start).total_seconds() / 60))
                cur_start = None
    if cur_start is not None:
        streaks.append((cur_start, cur_end, (cur_end - cur_start).total_seconds() / 60))
    streaks_out = sorted(
        [{"start": s.isoformat(), "end": e.isoformat(), "minutes": int(m)} for s, e, m in streaks],
        key=lambda x: x["minutes"], reverse=True,
    )[:10]

    return {
        "vehicle_id": vehicle_id,
        "ping_count": int(len(df)),
        "window":     {"from": df["gps_timestamp"].min().isoformat(),
                       "to":   df["gps_timestamp"].max().isoformat()},
        "hour_of_day_heatmap": {"matrix": heatmap, "max": max_val},
        "activity_timeline":  timeline_rows,
        "sleep_episodes":     sleep_eps,
        "meal_breaks":        meal_eps,
        "tea_breaks":         tea_eps,
        "drive_streaks":      streaks_out,
        "summary": {
            "avg_speed_when_moving": _safe_float(df[df["moving"] == 1]["speed"].mean()),
            "max_speed":             _safe_float(df["speed"].max()),
            "moving_pct":            _safe_float(df["moving"].mean() * 100),
            "active_days":           int(df["date"].nunique()),
        },
    }


# ----------------------------------------------------------------------
# Lane volume — per origin × destination
# ----------------------------------------------------------------------

@router.get("/lanes")
def lane_volume():
    trips = get_mock_table("fact_trips")
    legs  = get_mock_table("fact_trip_legs")
    if trips.empty:
        return {"lanes": []}
    merged = trips[["trip_no", "origin_text", "transporter_name", "trip_start_ts"]] \
             .merge(legs[["trip_no", "dest_text"]], on="trip_no", how="left")
    merged["dest_text"] = merged["dest_text"].fillna("(unknown)")
    grp = (merged.groupby(["origin_text", "dest_text"])
                 .agg(trip_count=("trip_no", "nunique"),
                      transporters=("transporter_name", "nunique"))
                 .reset_index()
                 .sort_values("trip_count", ascending=False))
    return {"lanes": [
        {"origin": r["origin_text"], "destination": r["dest_text"],
         "trips": int(r["trip_count"]), "transporters": int(r["transporters"])}
        for _, r in grp.iterrows()
    ]}


# ----------------------------------------------------------------------
# GPS quality — latency, position jumps, stale devices
# ----------------------------------------------------------------------

@router.get("/gps-quality")
def gps_quality():
    df = _vehicle_gps()
    if df.empty:
        return {"summary": {}, "samples": []}
    df["gps_timestamp"]    = pd.to_datetime(df["gps_timestamp"], errors="coerce")
    df["server_timestamp"] = pd.to_datetime(df["server_timestamp"], errors="coerce")
    df["latency_sec"] = (df["server_timestamp"] - df["gps_timestamp"]).dt.total_seconds()
    df["latency_sec"] = df["latency_sec"].clip(lower=0)

    # Position jumps within same vehicle
    df = df.sort_values(["vehicle_id", "gps_timestamp"])
    df["lat_prev"] = df.groupby("vehicle_id")["latitude"].shift()
    df["lng_prev"] = df.groupby("vehicle_id")["longitude"].shift()
    df["ts_prev"]  = df.groupby("vehicle_id")["gps_timestamp"].shift()
    df["gap_sec"]  = (df["gps_timestamp"] - df["ts_prev"]).dt.total_seconds()
    # crude haversine
    def hav(la1, lo1, la2, lo2):
        la1r, la2r = np.radians(la1), np.radians(la2)
        d_la = la2r - la1r
        d_lo = np.radians(lo2 - lo1)
        a = np.sin(d_la / 2) ** 2 + np.cos(la1r) * np.cos(la2r) * np.sin(d_lo / 2) ** 2
        return 2 * 6371 * np.arcsin(np.sqrt(a))
    mask = df["lat_prev"].notna()
    df.loc[mask, "jump_km"] = hav(df.loc[mask, "lat_prev"], df.loc[mask, "lng_prev"],
                                  df.loc[mask, "latitude"], df.loc[mask, "longitude"])

    return {
        "summary": {
            "ping_count":           int(len(df)),
            "avg_latency_sec":      round(float(df["latency_sec"].mean() or 0), 2),
            "p95_latency_sec":      round(float(df["latency_sec"].quantile(0.95) or 0), 2),
            "max_jump_km":          round(float(df["jump_km"].max() or 0), 2),
            "avg_gap_sec":          round(float(df["gap_sec"].mean() or 0), 2),
            "unique_vehicles":      int(df["vehicle_id"].nunique()),
            "unique_devices":       int(df["device_id"].nunique()),
        },
        "samples": df[["vehicle_id", "gps_timestamp", "latency_sec", "jump_km", "gap_sec"]]
                     .head(50)
                     .astype(str)
                     .to_dict(orient="records"),
    }
