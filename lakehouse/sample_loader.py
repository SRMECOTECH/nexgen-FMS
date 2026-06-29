"""
Loader for the real sample Excel files under sample_data/.

When MOCK mode is active and these files exist, every lakehouse client returns
the REAL sampled rows instead of synthetic ones. This gives us a faithful
preview of the lakehouse contents — including the columns that are mostly
null in production — so the UI can surface data-quality gaps honestly.

Files mapped:
    sample_data/fact_trips.xlsx           -> telemetry.fact_trips
    sample_data/fact_trips_legs.xlsx      -> telemetry.fact_trip_legs
    sample_data/gps_events.xlsx           -> telemetry.gps_events
    sample_data/gps_telemtry_events.xlsx  -> telemetry.gps_telemetry_events
                                             (typo in source filename is intentional)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Project root = parent of the lakehouse/ package
_SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"

_FILE_MAP = {
    "fact_trips":            "fact_trips.xlsx",
    "fact_trip_legs":        "fact_trips_legs.xlsx",
    "gps_events":            "gps_events.xlsx",
    "gps_telemetry_events":  "gps_telemtry_events.xlsx",
    # No sample for trip_detail / trip_header — derive at request time.
}


@lru_cache(maxsize=16)
def _read(table: str) -> pd.DataFrame | None:
    fname = _FILE_MAP.get(table)
    if not fname:
        return None
    path = _SAMPLE_DIR / fname
    if not path.exists():
        return None
    logger.info("sample_loader: reading %s", path)
    df = pd.read_excel(path)
    # Normalise timestamps where possible
    for col in df.columns:
        if "_ts" in col or col.endswith("_at") or col.endswith("_timestamp"):
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def has_sample(table: str) -> bool:
    return _read(table) is not None


def load(table: str) -> pd.DataFrame | None:
    """Return the real sample DataFrame for a table, or None if no file."""
    df = _read(table)
    return df.copy() if df is not None else None


def derive_trip_detail() -> pd.DataFrame:
    """trip_detail isn't sampled — derive a stand-in from gps_telemetry_events
    grouped by vehicle_id so the UI has something to show."""
    g = _read("gps_telemetry_events")
    if g is None or g.empty:
        return pd.DataFrame()
    out = g.assign(
        trip_id=g["vehicle_id"],
        sequence_no=g.groupby("vehicle_id").cumcount() + 1,
        event_type="MOVING",
    )[[
        "trip_id", "sequence_no", "gps_timestamp", "latitude", "longitude",
        "speed", "heading", "ignition_status", "odometer", "event_type",
        "_event_id", "_ingested_at", "_schema_version",
    ]]
    return out


def derive_trip_header() -> pd.DataFrame:
    """Cheap trip_header derived from fact_trips."""
    f = _read("fact_trips")
    if f is None or f.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "trip_id":       f["trip_no"].astype(str),
        "vehicle_id":    f["vehicle_id"],
        "driver_id":     f["driver_sk"].astype(str),
        "start_time":    f["trip_start_ts"],
        "end_time":      f.get("trip_actual_end_ts"),
        "start_odometer":  0.0,
        "end_odometer":    0.0,
        "start_location":  f["origin_text"],
        "end_location":    "—",
        "status":          f["lifecycle_status"],
        "_event_id":       f["trip_uuid"],
        "_ingested_at":    f["ingested_at"],
        "_schema_version": 1,
    })
