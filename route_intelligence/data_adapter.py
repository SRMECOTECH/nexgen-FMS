"""
Schema adapter — turn the vendor-flavoured ``gpsfinal_*.xlsx`` layout
into the normalized DataFrame the analyzers expect, and auto-detect
trips because the source ``i_trip_no`` column is always 0.

Vendor → normalized column map
    s_asset_id          -> vehicle_id
    dt_message          -> Date Time (parsed from "%d-%b-%y %H:%M:%S")
    i_lat, i_long       -> latitude, longitude
    i_corrt_speed       -> Speed_kmh        (fall back to i_speed)
    diff(i_distance)/1k -> Distance_km      (i_distance is a cumulative odometer in metres)
    s_wpnt1, s_wpnt2    -> Waypoint1, Waypoint2 (the corridor the vehicle is between)
    s_wpnt1_state_abbr  -> state            (handy for grouping)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from route_intelligence import config as ricfg


@dataclass
class NormalizedFrame:
    """Container for normalized data + a small summary."""
    df: pd.DataFrame
    vehicle_id: str
    n_rows: int
    n_dropped: int
    first_ts: pd.Timestamp
    last_ts: pd.Timestamp
    total_distance_km: float
    sheets: List[str] = field(default_factory=list)


@dataclass
class DetectedTrip:
    """One auto-detected trip = a moving segment bracketed by long stops."""
    seq: int
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    duration_min: float
    distance_km: float
    n_points: int
    avg_speed_kmph: float
    max_speed_kmph: float
    moving_min: float
    stopped_min: float
    from_waypoint: Optional[str]
    to_waypoint: Optional[str]
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float


# --- Excel reader ------------------------------------------------------------

def load_gps_excel(path: str) -> NormalizedFrame:
    """Read one or many sheets from a gpsfinal-style Excel into a single
    normalized DataFrame sorted by timestamp. Column names + parsing rules
    all come from ``config/route_intel.yaml`` — no code changes for a new
    vendor schema."""
    xl = pd.ExcelFile(path)
    frames = []
    for sheet in xl.sheet_names:
        try:
            frames.append(pd.read_excel(path, sheet_name=sheet))
        except Exception:
            continue
    if not frames:
        raise ValueError(f"No readable sheets in {path}")
    raw = pd.concat(frames, ignore_index=True)
    n_raw = len(raw)

    required = ricfg.excel_required()
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise ValueError(
            f"Excel missing required vendor columns: {missing}. "
            f"Got: {list(raw.columns)[:10]}…"
        )

    rename_map = ricfg.excel_column_map()
    df = raw.rename(columns=rename_map).copy()
    df["Date Time"] = pd.to_datetime(
        df["dt_message"], format=ricfg.excel_date_format(), errors="coerce"
    )
    df = df.dropna(subset=["Date Time", "latitude", "longitude"])
    df = df.sort_values("Date Time").reset_index(drop=True)
    n_dropped = n_raw - len(df)

    # Speed: try configured columns in order; fall back to 0.
    df["Speed_kmh"] = 0.0
    for col in ricfg.excel_speed_cols():
        if col in df.columns:
            df["Speed_kmh"] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            break

    # Distance: vendor odometer column → per-row diff, clipped + unit-converted.
    odo_col = ricfg.excel_odo_col()
    if odo_col in df.columns:
        odo = pd.to_numeric(df[odo_col], errors="coerce").ffill()
        units = ricfg.excel_odo_units().lower()
        divisor = 1000.0 if units == "meters" else 1.0
        clip_km = ricfg.excel_odo_clip_km()
        df["Distance_km"] = (odo.diff() / divisor).clip(lower=0, upper=clip_km).fillna(0)
    else:
        df["Distance_km"] = 0.0

    # Time diffs (used by traffic-loss and aggregation)
    df["Time_Diff_Seconds"] = (
        df["Date Time"].diff().dt.total_seconds().fillna(0).clip(lower=0)
    )
    df["Is_Moving"] = (df["Speed_kmh"] > 0).astype(int)

    # Synthetic Status string for code that expects "Moving N" / "Stopped"
    df["Status"] = np.where(
        df["Is_Moving"] == 1,
        "Moving " + df["Speed_kmh"].round(1).astype(str),
        "Stopped",
    )

    vehicle_id = str(df["vehicle_id"].iloc[0])

    return NormalizedFrame(
        df=df,
        vehicle_id=vehicle_id,
        n_rows=len(df),
        n_dropped=int(n_dropped),
        first_ts=df["Date Time"].iloc[0],
        last_ts=df["Date Time"].iloc[-1],
        total_distance_km=float(df["Distance_km"].sum()),
        sheets=list(xl.sheet_names),
    )


# --- trip auto-detection -----------------------------------------------------

def detect_trips(
    df: pd.DataFrame,
    stop_min_minutes: float | None = None,
    min_distance_km: float | None = None,
    min_duration_min: float | None = None,
) -> List[DetectedTrip]:
    """Segment the GPS stream into trips. A trip ends when the vehicle is
    stopped for ≥ ``stop_min_minutes`` (default 30 min) and resumes on the
    next moving ping. Tiny segments (under min_distance/min_duration) are
    discarded so we don't generate trips out of brief depot shuffles.

    The vendor's ``i_trip_no`` is ignored because it's always 0 in the
    Excel feed (TCIL doesn't pre-segment for us).
    """
    if df.empty:
        return []

    if stop_min_minutes is None or min_distance_km is None or min_duration_min is None:
        p = ricfg.trip_detection_params()
        stop_min_minutes = stop_min_minutes if stop_min_minutes is not None else p["stop_min_minutes"]
        min_distance_km = min_distance_km if min_distance_km is not None else p["min_distance_km"]
        min_duration_min = min_duration_min if min_duration_min is not None else p["min_duration_min"]

    # Build state runs: a run is a contiguous block with same is_moving flag.
    runs = []
    run_state = int(df["Is_Moving"].iloc[0])
    run_start = 0
    for i in range(1, len(df)):
        s = int(df["Is_Moving"].iloc[i])
        if s != run_state:
            runs.append((run_state, run_start, i - 1))
            run_state = s
            run_start = i
    runs.append((run_state, run_start, len(df) - 1))

    # Find long-stop indices: stopped runs whose duration ≥ threshold.
    trip_boundaries: List[int] = []  # row indices where a new trip starts
    for state, lo, hi in runs:
        if state == 0:
            dur = (df["Date Time"].iloc[hi] - df["Date Time"].iloc[lo]).total_seconds() / 60
            if dur >= stop_min_minutes:
                trip_boundaries.append(hi + 1)  # trip resumes after the stop

    # Convert boundaries into [start, end] index pairs.
    starts = [0] + trip_boundaries
    ends = [b - 1 for b in trip_boundaries] + [len(df) - 1]
    segments = [(s, e) for s, e in zip(starts, ends) if s <= e]

    trips: List[DetectedTrip] = []
    seq = 0
    for s_idx, e_idx in segments:
        seg = df.iloc[s_idx : e_idx + 1]
        if seg.empty:
            continue
        dist_km = float(seg["Distance_km"].sum())
        duration_min = (seg["Date Time"].iloc[-1] - seg["Date Time"].iloc[0]).total_seconds() / 60
        if dist_km < min_distance_km or duration_min < min_duration_min:
            continue
        moving = seg[seg["Is_Moving"] == 1]["Speed_kmh"]
        moving_sec = float(seg.loc[seg["Is_Moving"] == 1, "Time_Diff_Seconds"].sum())
        stopped_sec = float(seg.loc[seg["Is_Moving"] == 0, "Time_Diff_Seconds"].sum())

        from_wp = _first_nonnull(seg, "Waypoint1")
        to_wp = _last_nonnull(seg, "Waypoint2") or _last_nonnull(seg, "Waypoint1")

        seq += 1
        trips.append(
            DetectedTrip(
                seq=seq,
                start_ts=seg["Date Time"].iloc[0],
                end_ts=seg["Date Time"].iloc[-1],
                duration_min=round(duration_min, 1),
                distance_km=round(dist_km, 2),
                n_points=int(len(seg)),
                avg_speed_kmph=round(float(moving.mean()) if len(moving) else 0.0, 1),
                max_speed_kmph=round(float(seg["Speed_kmh"].max()), 1),
                moving_min=round(moving_sec / 60, 1),
                stopped_min=round(stopped_sec / 60, 1),
                from_waypoint=from_wp,
                to_waypoint=to_wp,
                start_lat=float(seg["latitude"].iloc[0]),
                start_lng=float(seg["longitude"].iloc[0]),
                end_lat=float(seg["latitude"].iloc[-1]),
                end_lng=float(seg["longitude"].iloc[-1]),
            )
        )
    return trips


def _first_nonnull(df: pd.DataFrame, col: str) -> Optional[str]:
    if col not in df.columns:
        return None
    s = df[col].dropna()
    return str(s.iloc[0]) if len(s) else None


def _last_nonnull(df: pd.DataFrame, col: str) -> Optional[str]:
    if col not in df.columns:
        return None
    s = df[col].dropna()
    return str(s.iloc[-1]) if len(s) else None


# --- time-window aggregation -------------------------------------------------

def aggregate_to_time_windows(
    df: pd.DataFrame, window: str = "30min"
) -> pd.DataFrame:
    """Reduce raw GPS into per-window summary rows. ``window`` accepts any
    pandas offset alias (15min, 30min, 1H, 2H)."""
    if df.empty:
        return pd.DataFrame()
    w = df.copy()
    w["Time_Window"] = w["Date Time"].dt.floor(window)

    agg = w.groupby("Time_Window", as_index=False).agg(
        window_start=("Date Time", "min"),
        window_end=("Date Time", "max"),
        total_distance_km=("Distance_km", "sum"),
        max_speed_kmph=("Speed_kmh", "max"),
        moving_time_sec=("Time_Diff_Seconds", lambda s: float(s[w.loc[s.index, "Is_Moving"] == 1].sum())),
        stopped_time_sec=("Time_Diff_Seconds", lambda s: float(s[w.loc[s.index, "Is_Moving"] == 0].sum())),
        waypoint_count=("Date Time", "size"),
        latitude=("latitude", "mean"),
        longitude=("longitude", "mean"),
    )

    # Average MOVING speed (excludes idle); average effective speed
    moving_speed = (
        w.assign(_s=w["Speed_kmh"].where(w["Speed_kmh"] > 0))
        .groupby("Time_Window", as_index=False)["_s"]
        .mean()
        .rename(columns={"_s": "avg_moving_speed_kmph"})
    )
    agg = agg.merge(moving_speed, on="Time_Window", how="left")
    agg["avg_moving_speed_kmph"] = agg["avg_moving_speed_kmph"].fillna(0)

    agg["total_time_hours"] = (agg["moving_time_sec"] + agg["stopped_time_sec"]) / 3600
    agg["avg_speed_kmph"] = np.where(
        agg["total_time_hours"] > 0,
        agg["total_distance_km"] / agg["total_time_hours"],
        0,
    )
    agg["dominant_status"] = np.where(
        agg["moving_time_sec"] > agg["stopped_time_sec"], "Moving", "Stopped"
    )
    agg["window_label"] = (
        agg["window_start"].dt.strftime("%H:%M") + "–" + agg["window_end"].dt.strftime("%H:%M")
    )
    return agg
