"""
Trip warehouse — stores the real trip master data (data/trpdtaopn_*.xlsx) into
MySQL alongside the GPS facts.

The source has two sheets:
  * Trip_Data      -> one row per trip   (origin/dest, consignor/consignee,
                      driver, status, booking/start/ETA/ATA dates …)   -> fact_trip
  * Trip_Data_Dtl  -> one row per leg    (sub-trip sequence, distances, stop type,
                      leg status, last-known location …)               -> fact_trip_leg

We keep a curated, cleanly-named subset (the raw export has 48 + 75 cryptic
s_/i_/dt_/c_ columns). Loading is a full snapshot REFRESH (delete + insert) so the
tables always mirror the latest file — idempotent, safe to re-run.

Only WAREHOUSE_URL (in .env) decides MySQL vs Postgres — same as gps_store.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import (
    BigInteger, Column, DateTime, Float, Integer, MetaData, String, Table, insert,
)

from lakehouse import gps_store

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _ROOT / "data"
_TS_FMT = "%d-%b-%y %H:%M:%S"          # e.g. '02-JUN-26 17:24:28'

_metadata = MetaData()

fact_trip = Table(
    "fact_trip", _metadata,
    Column("trip_no", BigInteger, primary_key=True, autoincrement=False),
    Column("asset_id", String(32)),          # vehicle reg
    Column("device_id", String(32)),
    Column("trip_type", String(8)),
    Column("status", String(8)),             # O = open / in-transit, etc.
    Column("org_node", String(120)),
    Column("dest_node", String(120)),
    Column("final_dest", String(120)),
    Column("booking_ts", DateTime),
    Column("start_ts", DateTime),
    Column("eta_ts", DateTime),
    Column("ata_ts", DateTime),
    Column("end_ts", DateTime),
    Column("consignor", String(200)),
    Column("consignee", String(200)),
    Column("transporter", String(200)),
    Column("lr_no", String(64)),
    Column("driver_name", String(120)),
    Column("driver_mobile", String(20)),
    Column("asset_type", String(40)),
    Column("route_id", Integer),
    Column("shipment_id", String(64)),
    Column("prod_id", String(32)),
    Column("close_reason", String(120)),
)

fact_trip_leg = Table(
    "fact_trip_leg", _metadata,
    Column("trip_no", BigInteger, primary_key=True, autoincrement=False),
    Column("seq", Integer, primary_key=True, autoincrement=False),
    Column("org_node", String(120)),
    Column("dest_node", String(120)),
    Column("status", String(8)),
    Column("stop_type", String(24)),
    Column("running_sts", String(40)),
    Column("total_dist", Float),
    Column("cover_dist", Float),
    Column("delay_by", Integer),
    Column("material", String(200)),
    Column("eta_ts", DateTime),
    Column("ata_ts", DateTime),
    Column("org_lat", Float),
    Column("org_lng", Float),
    Column("dest_lat", Float),
    Column("dest_lng", Float),
    Column("last_loc", String(200)),
)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _dt(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, format=_TS_FMT, errors="coerce")
    if out.isna().any():
        out = out.fillna(pd.to_datetime(s, errors="coerce"))
    return out


def _i(v):
    return None if pd.isna(v) else int(v)


def _fl(v):
    try:
        return None if pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return None


def _s(v):
    return None if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v).strip()


def _ts(v):
    return None if pd.isna(v) else v.to_pydatetime()


def find_trip_excel() -> Path | None:
    """Newest trip workbook under data/ (trpdtaopn_*.xlsx preferred)."""
    if not _DATA_DIR.exists():
        return None
    for pattern in ("trpdtaopn_*.xlsx", "Trip_data*.xlsx", "*trip*dta*.xlsx"):
        c = sorted(_DATA_DIR.glob(pattern))
        if c:
            return c[-1]
    return None


def ensure_schema() -> None:
    if gps_store.engine() is None:
        raise RuntimeError("WAREHOUSE_URL not configured")
    gps_store._ensure_mysql_database()
    _metadata.create_all(gps_store.engine())


# ----------------------------------------------------------------------
# load (full snapshot refresh)
# ----------------------------------------------------------------------
def load_trips(path: Path | None = None) -> dict:
    e = gps_store.engine()
    if e is None:
        return {"ok": False, "error": "WAREHOUSE_URL not configured"}
    path = path or find_trip_excel()
    if path is None or not path.exists():
        return {"ok": False, "error": "no trip workbook found under data/"}

    xls = pd.ExcelFile(path)
    hdr = pd.read_excel(xls, sheet_name="Trip_Data")
    dtl = pd.read_excel(xls, sheet_name="Trip_Data_Dtl") if "Trip_Data_Dtl" in xls.sheet_names else pd.DataFrame()

    for col in ("dt_booking", "dt_trip_start", "dt_trip_eta", "dt_trip_ata", "dt_trip_end"):
        if col in hdr:
            hdr[col] = _dt(hdr[col])

    trip_rows = [{
        "trip_no": _i(r.get("i_trip_no")), "asset_id": _s(r.get("s_asset_id")),
        "device_id": _s(r.get("s_device_id")), "trip_type": _s(r.get("c_trip_type")),
        "status": _s(r.get("c_trip_status")),
        "org_node": _s(r.get("s_org_node_name")), "dest_node": _s(r.get("s_dest_node_name")),
        "final_dest": _s(r.get("s_final_dest")),
        "booking_ts": _ts(r.get("dt_booking")), "start_ts": _ts(r.get("dt_trip_start")),
        "eta_ts": _ts(r.get("dt_trip_eta")), "ata_ts": _ts(r.get("dt_trip_ata")),
        "end_ts": _ts(r.get("dt_trip_end")),
        "consignor": _s(r.get("s_cnr_name")), "consignee": _s(r.get("s_cne_name")),
        "transporter": _s(r.get("s_trans_name")), "lr_no": _s(r.get("s_lr_no")),
        "driver_name": _s(r.get("s_driver_name")), "driver_mobile": _s(r.get("s_driver_mobile_no")),
        "asset_type": _s(r.get("s_asset_type")), "route_id": _i(r.get("i_route_id")),
        "shipment_id": _s(r.get("s_shipment_id")), "prod_id": _s(r.get("s_prod_id")),
        "close_reason": _s(r.get("s_close_reason")),
    } for _, r in hdr.iterrows() if not pd.isna(r.get("i_trip_no"))]

    if not dtl.empty:
        for col in ("dt_sub_trip_eta", "dt_sub_trip_ata"):
            if col in dtl:
                dtl[col] = _dt(dtl[col])
    leg_rows = [{
        "trip_no": _i(r.get("i_trip_no")), "seq": _i(r.get("i_sub_trip_seq")) or 1,
        "org_node": _s(r.get("s_org_node_name")), "dest_node": _s(r.get("s_dest_node_name")),
        "status": _s(r.get("c_sub_trip_status")), "stop_type": _s(r.get("s_stop_type")),
        "running_sts": _s(r.get("s_running_sts")),
        "total_dist": _fl(r.get("s_total_dist")), "cover_dist": _fl(r.get("s_cover_dist")),
        "delay_by": _i(r.get("i_delay_by")), "material": _s(r.get("s_material_desc")),
        "eta_ts": _ts(r.get("dt_sub_trip_eta")), "ata_ts": _ts(r.get("dt_sub_trip_ata")),
        "org_lat": _fl(r.get("i_org_lat")), "org_lng": _fl(r.get("i_org_lon")),
        "dest_lat": _fl(r.get("i_dest_lat")), "dest_lng": _fl(r.get("i_dest_lon")),
        "last_loc": _s(r.get("s_sub_trip_last_loc")),
    } for _, r in dtl.iterrows() if not pd.isna(r.get("i_trip_no"))] if not dtl.empty else []

    ensure_schema()
    from sqlalchemy import text
    with e.begin() as conn:
        conn.execute(text("DELETE FROM fact_trip_leg"))
        conn.execute(text("DELETE FROM fact_trip"))
        for i in range(0, len(trip_rows), 500):
            conn.execute(insert(fact_trip), trip_rows[i:i + 500])
        for i in range(0, len(leg_rows), 500):
            conn.execute(insert(fact_trip_leg), leg_rows[i:i + 500])

    return {"ok": True, "source": path.name, "trips": len(trip_rows), "legs": len(leg_rows)}


# ----------------------------------------------------------------------
# reads
# ----------------------------------------------------------------------
def _ready() -> bool:
    from sqlalchemy import inspect
    e = gps_store.engine()
    if e is None:
        return False
    try:
        return inspect(e).has_table("fact_trip")
    except Exception:
        return False


def counts() -> dict:
    from sqlalchemy import text
    if not _ready():
        return {"trips": 0, "legs": 0}
    e = gps_store.engine()
    with e.connect() as c:
        return {"trips": int(c.execute(text("SELECT COUNT(*) FROM fact_trip")).scalar() or 0),
                "legs": int(c.execute(text("SELECT COUNT(*) FROM fact_trip_leg")).scalar() or 0)}


_STATUS_LABEL = {"O": "Open", "C": "Closed", "D": "Delivered", "X": "Cancelled", "T": "In transit"}


def _trip_dict(r) -> dict:
    return {
        "trip_no": int(r.trip_no), "asset_id": r.asset_id, "device_id": r.device_id,
        "status": r.status, "status_label": _STATUS_LABEL.get((r.status or "").strip(), r.status or "—"),
        "org_node": r.org_node, "dest_node": r.dest_node, "final_dest": r.final_dest,
        "booking_ts": _str(r.booking_ts), "start_ts": _str(r.start_ts),
        "eta_ts": _str(r.eta_ts), "ata_ts": _str(r.ata_ts), "end_ts": _str(r.end_ts),
        "consignor": r.consignor, "consignee": r.consignee, "transporter": r.transporter,
        "lr_no": r.lr_no, "driver_name": r.driver_name, "driver_mobile": r.driver_mobile,
        "asset_type": r.asset_type, "route_id": _i(r.route_id), "shipment_id": r.shipment_id,
        "prod_id": r.prod_id, "close_reason": r.close_reason,
    }


def _str(v):
    return None if v is None or pd.isna(v) else str(v)


_PARTY_COL = {"consignor": "consignor", "consignee": "consignee", "transporter": "transporter"}


def list_trips(search: str | None = None, status: str | None = None, limit: int = 500,
               consignor: str | None = None, consignee: str | None = None,
               transporter: str | None = None) -> list[dict]:
    from sqlalchemy import text
    if not _ready():
        return []
    e = gps_store.engine()
    where, params = [], {}
    if status:
        where.append("status = :st"); params["st"] = status
    for key, val in (("consignor", consignor), ("consignee", consignee), ("transporter", transporter)):
        if val:
            where.append(f"{key} = :{key}"); params[key] = val
    if search:
        where.append("(asset_id LIKE :q OR consignor LIKE :q OR consignee LIKE :q OR "
                     "org_node LIKE :q OR dest_node LIKE :q OR CAST(trip_no AS CHAR) LIKE :q OR driver_name LIKE :q)")
        params["q"] = f"%{search}%"
    sql = "SELECT * FROM fact_trip"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY start_ts DESC LIMIT :lim"
    params["lim"] = int(limit)
    df = pd.read_sql(text(sql), e, params=params)
    return [_trip_dict(r) for r in df.itertuples()]


def party_summary(dim: str) -> list[dict]:
    """Aggregate trips by consignor / consignee / transporter — one row per party
    with trip count, fleet size, lanes covered, open count and last trip date."""
    from sqlalchemy import text
    col = _PARTY_COL.get(dim)
    if not col or not _ready():
        return []
    e = gps_store.engine()
    open_expr = "SUM(CASE WHEN status IN ('O','T') THEN 1 ELSE 0 END)"
    sql = (f"SELECT {col} AS name, COUNT(*) AS trips, COUNT(DISTINCT asset_id) AS assets, "
           f"COUNT(DISTINCT CONCAT(COALESCE(org_node,''),'>',COALESCE(dest_node,''))) AS lanes, "
           f"{open_expr} AS open_trips, MAX(start_ts) AS last_trip "
           f"FROM fact_trip WHERE {col} IS NOT NULL AND {col} <> '' "
           f"GROUP BY {col} ORDER BY trips DESC")
    df = pd.read_sql(text(sql), e)
    return [{
        "name": r.name, "trips": int(r.trips), "assets": int(r.assets),
        "lanes": int(r.lanes), "open_trips": int(r.open_trips or 0),
        "last_trip": _str(r.last_trip),
    } for r in df.itertuples()]


def trip_detail(trip_no: int) -> dict:
    from sqlalchemy import text
    if not _ready():
        return {"error": "trips not loaded"}
    e = gps_store.engine()
    h = pd.read_sql(text("SELECT * FROM fact_trip WHERE trip_no = :n"), e, params={"n": trip_no})
    if h.empty:
        return {"error": f"trip {trip_no} not found"}
    legs = pd.read_sql(text("SELECT * FROM fact_trip_leg WHERE trip_no = :n ORDER BY seq"), e, params={"n": trip_no})
    leg_rows = [{
        "seq": int(r.seq), "org_node": r.org_node, "dest_node": r.dest_node,
        "status": r.status, "stop_type": r.stop_type, "running_sts": r.running_sts,
        "total_dist": _fl(r.total_dist), "cover_dist": _fl(r.cover_dist), "delay_by": _i(r.delay_by),
        "material": r.material, "eta_ts": _str(r.eta_ts), "ata_ts": _str(r.ata_ts),
        "last_loc": r.last_loc,
    } for r in legs.itertuples()]
    return {"header": _trip_dict(h.iloc[0]), "legs": leg_rows, "num_legs": len(leg_rows)}


def _delay_minutes(eta: pd.Series, ata: pd.Series) -> pd.Series:
    """Minutes late = (actual arrival, or 'now' for still-running trips) − planned ETA.
    NaN where there is no ETA to measure against."""
    now = pd.Timestamp.now()
    eta = pd.to_datetime(eta, errors="coerce")
    ata = pd.to_datetime(ata, errors="coerce")
    arrival = ata.fillna(now)
    return (arrival - eta).dt.total_seconds() / 60.0


def dashboard_summary() -> dict:
    """Fleet-wide KPI cards for the landing page — computed from the REAL trip
    master data in MySQL (fact_trip), so it always matches the Trips page."""
    from sqlalchemy import text
    zeros = {"total_trips": 0, "in_transit": 0, "delivered": 0, "delayed": 0,
             "on_time_pct": 0.0, "active_vehicles": 0, "active_drivers": 0}
    if not _ready():
        return zeros
    e = gps_store.engine()
    df = pd.read_sql(text("SELECT status, asset_id, driver_name, eta_ts, ata_ts FROM fact_trip"), e)
    total = len(df)
    if total == 0:
        return zeros
    st = df["status"].fillna("").astype(str).str.strip().str.upper()
    delay = _delay_minutes(df["eta_ts"], df["ata_ts"])
    has_eta = pd.to_datetime(df["eta_ts"], errors="coerce").notna()
    measured = int(has_eta.sum())
    on_time = int(((delay <= 30) & has_eta).sum())
    active_mask = st.isin(["O", "T"])
    return {
        "total_trips": int(total),
        "in_transit": int(active_mask.sum()),
        "delivered": int(st.isin(["D", "C"]).sum()),
        "delayed": int((delay > 30).sum()),
        "on_time_pct": round(on_time / measured * 100, 1) if measured else 0.0,
        "active_vehicles": int(df.loc[active_mask, "asset_id"].dropna().nunique()),
        "active_drivers": int(df.loc[active_mask, "driver_name"].dropna().nunique()),
    }


def active_trips(limit: int = 200) -> list[dict]:
    """In-transit trips (status O/T) shaped for the dashboard 'Active Trips' table,
    straight from MySQL fact_trip. Empty list until the trip workbook is uploaded."""
    from sqlalchemy import text
    if not _ready():
        return []
    e = gps_store.engine()
    df = pd.read_sql(
        text("SELECT trip_no, asset_id, driver_name, transporter, consignor, "
             "org_node, dest_node, status, eta_ts, ata_ts, start_ts "
             "FROM fact_trip WHERE status IN ('O','T') ORDER BY start_ts DESC LIMIT :lim"),
        e, params={"lim": int(limit)})
    if df.empty:
        return []
    delay = _delay_minutes(df["eta_ts"], df["ata_ts"]).fillna(0)
    out = []
    for i, r in enumerate(df.itertuples()):
        out.append({
            "trip_no": int(r.trip_no),
            "vehicle_id": r.asset_id or "—",
            "driver_name": r.driver_name or "—",
            "transporter_name": r.transporter or "—",
            "shipper_name": r.consignor or "—",
            "origin_text": f"{r.org_node or '—'} → {r.dest_node or '—'}",
            "trip_planned_eta_ts": _str(r.eta_ts),
            "trip_derived_eta_ts": _str(r.ata_ts),
            # not-yet-due trips (ETA in the future) show as on-time, not a big negative
            "delay_minutes": max(0, int(round(delay.iloc[i]))),
            "running_status": _STATUS_LABEL.get((r.status or "").strip(), r.status or "—"),
            "num_legs": 0, "num_legs_delivered": 0, "total_distance_km": 0.0,
        })
    return out


def summary() -> dict:
    from sqlalchemy import text
    if not _ready():
        return {"total": 0, "by_status": [], "top_consignors": [], "top_lanes": [], "fleet": 0, "transporters": 0}
    e = gps_store.engine()
    with e.connect() as c:
        total = int(c.execute(text("SELECT COUNT(*) FROM fact_trip")).scalar() or 0)
        fleet = int(c.execute(text("SELECT COUNT(DISTINCT asset_id) FROM fact_trip")).scalar() or 0)
        transporters = int(c.execute(text("SELECT COUNT(DISTINCT transporter) FROM fact_trip")).scalar() or 0)
        by_status = [{"status": s or "—", "label": _STATUS_LABEL.get((s or "").strip(), s or "—"), "count": int(n)}
                     for s, n in c.execute(text("SELECT status, COUNT(*) FROM fact_trip GROUP BY status ORDER BY 2 DESC")).all()]
        cons = [{"name": n or "—", "count": int(k)} for n, k in c.execute(
            text("SELECT consignor, COUNT(*) FROM fact_trip GROUP BY consignor ORDER BY 2 DESC LIMIT 6")).all()]
        lanes = [{"lane": f"{o} → {d}", "count": int(k)} for o, d, k in c.execute(
            text("SELECT org_node, dest_node, COUNT(*) FROM fact_trip GROUP BY org_node, dest_node ORDER BY 3 DESC LIMIT 6")).all()]
    return {"total": total, "fleet": fleet, "transporters": transporters,
            "by_status": by_status, "top_consignors": cons, "top_lanes": lanes}
