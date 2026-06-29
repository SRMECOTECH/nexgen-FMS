"""
Canonical normaliser for the raw device GPS feed (data/gpsfinal_*.xlsx).

This is the ONE place that understands the raw 40-column device schema and turns
it into a clean, analytics-ready table called ``gps_feed``. Both the ingestion
pipeline (file -> Neon) and the read-time analytics use this module, so the
transform is defined exactly once.

Raw schema (per ping, Hungarian-ish device naming):
    s_asset_id        vehicle registration plate (e.g. CG15EA3403)
    s_device_id       device IMEI
    i_entity_id       owning entity id
    s_entity_name     owning entity / transporter name
    i_entity_type     entity type code
    s_prod_id         device product / protocol id
    dt_message        GPS fix timestamp  (the ping time)   '01-JUN-26 00:00:23'
    dt_server         server receive timestamp
    dt_created        warehouse create timestamp (micros)
    i_lat / i_long    position
    i_speed           reported speed (km/h)
    i_corrt_speed     corrected speed (km/h)
    i_distance        cumulative odometer (metres)
    i_dist            per-ping segment distance (metres)
    i_wpnt1_*         nearest route node BEHIND  (no, name, lat, long, metres, state)
    i_wpnt2_*         next route node AHEAD       (no, name, lat, long, metres, state)
    s_alert_lov       encoded telemetry/alert LOV  '1000:Y#1570:10000#1610:100'
    i_msg_no          device message type code
    i_port_no         listener port
    c_is_*            Y/N flags (active / alert / processed / deleted / fixedtrip)

Decoded ``s_alert_lov`` keys observed:
    1000 -> packet valid flag (always Y)
    1570 -> digital IO / state word (e.g. 10000 vs 00000)
    1610 -> signal/quality percentage (5..100)
    1170, 1370 -> sparse event flags (panic / harsh-event style)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Project root = parent of the lakehouse/ package
_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _ROOT / "data"

# Device timestamp format: '01-JUN-26 00:00:23' (created col carries micros).
_TS_FMT = "%d-%b-%y %H:%M:%S"


def find_gps_excel() -> Path | None:
    """Return the newest gps*.xlsx under data/ (e.g. gpsfinal_20260603.xlsx)."""
    if not _DATA_DIR.exists():
        return None
    candidates = sorted(_DATA_DIR.glob("gps*.xlsx"))
    return candidates[-1] if candidates else None


def _parse_ts(series: pd.Series) -> pd.Series:
    # Try the device format first; fall back to pandas inference for the
    # micro-second 'dt_created' values that carry a fractional part.
    out = pd.to_datetime(series, format=_TS_FMT, errors="coerce")
    if out.isna().any():
        fallback = pd.to_datetime(series, errors="coerce")
        out = out.fillna(fallback)
    return out


def _decode_alert_lov(value: object) -> dict:
    """'1000:Y#1570:10000#1610:100' -> {'1000':'Y','1570':'10000','1610':'100'}."""
    if not isinstance(value, str) or not value:
        return {}
    pairs = {}
    for tok in value.split("#"):
        if ":" in tok:
            k, _, v = tok.partition(":")
            pairs[k.strip()] = v.strip()
    return pairs


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Map the raw device frame to the canonical ``gps_feed`` schema.

    Idempotent and column-tolerant: missing raw columns degrade to NULL rather
    than raising, so a slightly different export still ingests.
    """
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]

    def col(name, default=np.nan):
        return df[name] if name in df.columns else pd.Series(default, index=df.index)

    gps_ts = _parse_ts(col("dt_message"))
    server_ts = _parse_ts(col("dt_server"))
    created_ts = _parse_ts(col("dt_created"))

    out = pd.DataFrame({
        # identity
        "vehicle_reg":   col("s_asset_id").astype("string"),
        "device_id":     col("s_device_id").astype("string"),
        "entity_id":     pd.to_numeric(col("i_entity_id"), errors="coerce"),
        "entity_name":   col("s_entity_name").astype("string"),
        "entity_type":   pd.to_numeric(col("i_entity_type"), errors="coerce"),
        "product_id":    pd.to_numeric(col("s_prod_id"), errors="coerce"),
        "trip_no_raw":   pd.to_numeric(col("i_trip_no"), errors="coerce"),
        # time
        "gps_ts":        gps_ts,
        "server_ts":     server_ts,
        "created_ts":    created_ts,
        "latency_sec":   (server_ts - gps_ts).dt.total_seconds().clip(lower=0),
        # position & motion
        "latitude":      pd.to_numeric(col("i_lat"), errors="coerce"),
        "longitude":     pd.to_numeric(col("i_long"), errors="coerce"),
        "speed_kph":     pd.to_numeric(col("i_speed"), errors="coerce"),
        "speed_corr_kph": pd.to_numeric(col("i_corrt_speed"), errors="coerce"),
        "odometer_m":    pd.to_numeric(col("i_distance"), errors="coerce"),
        "segment_m":     pd.to_numeric(col("i_dist"), errors="coerce"),
        # route corridor — node behind / node ahead
        "from_node_no":   pd.to_numeric(col("i_wpnt1_node_no"), errors="coerce"),
        "from_node":      col("s_wpnt1").astype("string"),
        "from_node_lat":  pd.to_numeric(col("i_wpnt1_lat"), errors="coerce"),
        "from_node_lng":  pd.to_numeric(col("i_wpnt1_long"), errors="coerce"),
        "from_node_m":    pd.to_numeric(col("i_wpnt1_mt"), errors="coerce"),
        "from_state":     col("s_wpnt1_state_abbr").astype("string"),
        "to_node_no":     pd.to_numeric(col("i_wpnt2_node_no"), errors="coerce"),
        "to_node":        col("s_wpnt2").astype("string"),
        "to_node_lat":    pd.to_numeric(col("i_wpnt2_lat"), errors="coerce"),
        "to_node_lng":    pd.to_numeric(col("i_wpnt2_long"), errors="coerce"),
        "to_node_m":      pd.to_numeric(col("i_wpnt2_mt"), errors="coerce"),
        "to_state":       col("s_wpnt2_state_abbr").astype("string"),
        # device / message
        "msg_type":      pd.to_numeric(col("i_msg_no"), errors="coerce"),
        "port_no":       pd.to_numeric(col("i_port_no"), errors="coerce"),
        "alert_raw":     col("s_alert_lov").astype("string"),
        "is_alert":      col("c_is_alert").astype("string"),
        "is_active":     col("c_is_active").astype("string"),
        "is_processed":  col("c_is_processed").astype("string"),
    })

    # Decode the alert LOV into useful columns
    decoded = col("s_alert_lov").map(_decode_alert_lov)
    out["signal_pct"] = pd.to_numeric(decoded.map(lambda d: d.get("1610")), errors="coerce")
    out["io_state"]   = decoded.map(lambda d: d.get("1570")).astype("string")
    # any key whose value is 'Y' other than the always-on 1000 packet flag
    out["event_codes"] = decoded.map(
        lambda d: ",".join(sorted(k for k, v in d.items() if v == "Y" and k != "1000")) or None
    ).astype("string")

    # Derived motion state (no ignition column in this feed; use corrected speed)
    spd = out["speed_corr_kph"].fillna(out["speed_kph"]).fillna(0)
    out["motion_status"] = np.where(spd > 2, "MOVING", "STOPPED")

    # Stable surrogate ping id (device + ping time) — natural key for upserts
    out["ping_id"] = (
        out["device_id"].fillna("?") + "|" +
        out["gps_ts"].dt.strftime("%Y%m%d%H%M%S").fillna("?")
    )

    out = out.dropna(subset=["gps_ts"]).sort_values("gps_ts").reset_index(drop=True)
    return out


def load_normalized(path: str | Path | None = None) -> pd.DataFrame:
    """Read every sheet of the GPS Excel, concat, and normalise to gps_feed."""
    p = Path(path) if path else find_gps_excel()
    if p is None or not p.exists():
        logger.warning("gps_feed: no GPS Excel found under %s", _DATA_DIR)
        return pd.DataFrame()
    xl = pd.ExcelFile(p)
    frames = [xl.parse(s) for s in xl.sheet_names]
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    logger.info("gps_feed: read %s (%d sheets, %d raw rows)", p.name, len(xl.sheet_names), len(raw))
    return normalize(raw)
