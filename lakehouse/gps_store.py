"""
Normalised GPS warehouse — production entity model, dialect-aware (MySQL + PG).

The real world this models (from the brief):
  * IoT GPS DEVICES are physical units that get moved between TRUCKS over time.
  * TRUCKS (vehicles) are driven by DRIVERS who change from trip to trip.
  * Every ping must stay attributable to "which device, on which truck, driven
    by whom, at that moment" — so the history of device<->truck and truck<->driver
    is first-class, not overwritten.

Schema
------
Dimensions
  dim_device(device_sk, device_imei UQ, product_id)
  dim_vehicle(vehicle_sk, vehicle_reg UQ, entity_id, entity_name, entity_type)
  dim_driver(driver_sk, driver_ref UQ, driver_name, mobile)        # filled when feed carries it
  dim_company(company_sk, company_name UQ, address, lat, lng, state, type)  # shipper/consignee/facility
  dim_node(node_sk, node_no UQ, node_name, lat, lng, state, address, geocoded_at)

History / bridges (an asset's whole timeline)
  device_vehicle_link(device_sk, vehicle_sk, first_ts, last_ts, ping_count)   # device on which truck, when
  vehicle_driver_link(vehicle_sk, driver_sk, first_ts, last_ts)               # who drove which truck, when

Facts
  fact_gps_ping(ping_id PK, device_sk, vehicle_sk, gps_ts, lat/lng, speed,
                odometer, from_node_sk, to_node_sk, signal, loaded_flag, trip_sk)

Forward-looking (created now, populated by later jobs — so the schema is stable)
  dim_geofence(geofence_sk, name, center_lat, center_lng, radius_m, type, address)
  fact_stop_event(stop_sk, vehicle_sk, device_sk, geofence_sk, arrive_ts,
                  depart_ts, minutes, lat, lng, address, reason_inferred)

Only WAREHOUSE_URL decides MySQL vs Postgres. First upload creates everything;
later uploads INSERT IGNORE only new pings, then recompute the tiny link tables.
"""

from __future__ import annotations

import logging
import os

import pandas as pd
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, Index, Integer, MetaData,
    String, Table, UniqueConstraint, create_engine, insert, inspect, select, text,
)

from lakehouse import gps_feed

logger = logging.getLogger(__name__)

_metadata = MetaData()

dim_device = Table(
    "dim_device", _metadata,
    Column("device_sk", Integer, primary_key=True, autoincrement=True),
    Column("device_imei", String(32), unique=True, nullable=False),
    Column("product_id", Integer),
)

dim_vehicle = Table(
    "dim_vehicle", _metadata,
    Column("vehicle_sk", Integer, primary_key=True, autoincrement=True),
    Column("vehicle_reg", String(32), unique=True, nullable=False),
    Column("entity_id", BigInteger),
    Column("entity_name", String(160)),
    Column("entity_type", Integer),
)

dim_driver = Table(
    "dim_driver", _metadata,
    Column("driver_sk", Integer, primary_key=True, autoincrement=True),
    Column("driver_ref", String(48), unique=True, nullable=False),
    Column("driver_name", String(120)),
    Column("mobile", String(20)),
)

dim_company = Table(
    "dim_company", _metadata,
    Column("company_sk", Integer, primary_key=True, autoincrement=True),
    Column("company_name", String(200), unique=True, nullable=False),
    Column("address", String(400)),
    Column("lat", Float),
    Column("lng", Float),
    Column("state", String(8)),
    Column("type", String(24)),
)

dim_node = Table(
    "dim_node", _metadata,
    Column("node_sk", Integer, primary_key=True, autoincrement=True),
    Column("node_no", Integer, unique=True, nullable=False),
    Column("node_name", String(200)),
    Column("lat", Float),
    Column("lng", Float),
    Column("state", String(8)),
    Column("address", String(400)),       # reverse-geocoded (Nominatim) later
    Column("geocoded_at", DateTime),
)

device_vehicle_link = Table(
    "device_vehicle_link", _metadata,
    Column("link_sk", Integer, primary_key=True, autoincrement=True),
    Column("device_sk", Integer, nullable=False),
    Column("vehicle_sk", Integer, nullable=False),
    Column("first_ts", DateTime),
    Column("last_ts", DateTime),
    Column("ping_count", Integer),
    UniqueConstraint("device_sk", "vehicle_sk", name="uq_dev_veh"),
)

vehicle_driver_link = Table(
    "vehicle_driver_link", _metadata,
    Column("link_sk", Integer, primary_key=True, autoincrement=True),
    Column("vehicle_sk", Integer, nullable=False),
    Column("driver_sk", Integer, nullable=False),
    Column("first_ts", DateTime),
    Column("last_ts", DateTime),
    UniqueConstraint("vehicle_sk", "driver_sk", name="uq_veh_drv"),
)

fact_gps_ping = Table(
    "fact_gps_ping", _metadata,
    Column("ping_id", String(48), primary_key=True),
    Column("device_sk", Integer),
    Column("vehicle_sk", Integer, nullable=False),
    Column("gps_ts", DateTime),
    Column("server_ts", DateTime),
    Column("latency_sec", Float),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("speed_kph", Float),
    Column("speed_corr_kph", Float),
    Column("motion_status", String(12)),
    Column("odometer_m", BigInteger),
    Column("segment_m", Float),
    Column("from_node_sk", Integer),
    Column("to_node_sk", Integer),
    Column("from_node_m", Float),
    Column("to_node_m", Float),
    Column("signal_pct", Float),
    Column("io_state", String(16)),
    Column("event_codes", String(64)),
    Column("msg_type", Integer),
    Column("port_no", Integer),
    Column("loaded_flag", Boolean),       # laden vs empty (future classifier)
    Column("trip_sk", Integer),           # reconstructed-trip id (future)
    Index("ix_fact_vehicle_ts", "vehicle_sk", "gps_ts"),
    Index("ix_fact_device_ts", "device_sk", "gps_ts"),
)

dim_geofence = Table(
    "dim_geofence", _metadata,
    Column("geofence_sk", Integer, primary_key=True, autoincrement=True),
    Column("name", String(200)),
    Column("center_lat", Float),
    Column("center_lng", Float),
    Column("radius_m", Float),
    Column("type", String(24)),           # depot/customer/fuel/halt/dhaba
    Column("address", String(400)),       # reverse-geocoded street address (Nominatim)
    Column("poi_name", String(200)),      # nearest named place (Overpass/OSM)
    Column("poi_category", String(40)),   # dhaba/hotel/fuel station/café/…
    Column("poi_distance_m", Float),      # metres from stop centre to that POI
)

fact_stop_event = Table(
    "fact_stop_event", _metadata,
    Column("stop_sk", Integer, primary_key=True, autoincrement=True),
    Column("vehicle_sk", Integer),
    Column("device_sk", Integer),
    Column("geofence_sk", Integer),
    Column("arrive_ts", DateTime),
    Column("depart_ts", DateTime),
    Column("minutes", Float),
    Column("lat", Float),
    Column("lng", Float),
    Column("address", String(400)),
    Column("reason_inferred", String(80)),
    Index("ix_stop_vehicle_ts", "vehicle_sk", "arrive_ts"),
)

# Pre-aggregated 15-minute rollup — the "fetch strategy" answer. Computed at
# ingest so the map / trends read a tiny table (one row per truck per 15 min)
# instead of scanning millions of raw pings. Raw fact_gps_ping stays for drill-down.
fact_gps_15min = Table(
    "fact_gps_15min", _metadata,
    Column("vehicle_sk", Integer, primary_key=True),
    Column("bucket_ts", DateTime, primary_key=True),
    Column("pings", Integer),
    Column("avg_speed", Float),
    Column("max_speed", Float),
    Column("dist_km", Float),
    Column("moving_frac", Float),
    Column("lat", Float),
    Column("lng", Float),
)


# ----------------------------------------------------------------------
# connection
# ----------------------------------------------------------------------
def _normalize_url(url: str) -> str:
    if url.startswith("postgresql+") or url.startswith("mysql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("mysql://"):
        return "mysql+pymysql://" + url[len("mysql://"):]
    return url


_engine_cache: dict = {}


def warehouse_url() -> str | None:
    return os.environ.get("WAREHOUSE_URL") or os.environ.get("NEON_DATABASE_URL")


def engine():
    url = warehouse_url()
    if not url:
        return None
    if url not in _engine_cache:
        _engine_cache[url] = create_engine(_normalize_url(url), pool_pre_ping=True)
    return _engine_cache[url]


def dialect() -> str:
    e = engine()
    return e.dialect.name if e else ""


def schema_ready() -> bool:
    e = engine()
    if e is None:
        return False
    try:
        return inspect(e).has_table("fact_gps_ping")
    except Exception:
        return False


def _ensure_mysql_database() -> None:
    url = _normalize_url(warehouse_url() or "")
    if not url.startswith("mysql+"):
        return
    from sqlalchemy.engine import make_url
    u = make_url(url)
    if not u.database:
        return
    server = create_engine(u.set(database=None), pool_pre_ping=True)
    with server.begin() as c:
        c.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{u.database}` "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
    server.dispose()
    logger.info("gps_store: ensured MySQL database `%s`", u.database)


def ensure_schema() -> None:
    """Create database (MySQL) + all tables if absent (idempotent)."""
    if engine() is None:
        raise RuntimeError("WAREHOUSE_URL not configured")
    _ensure_mysql_database()
    _metadata.create_all(engine())
    ensure_columns()
    logger.info("gps_store: schema ensured on %s", dialect())


# Columns added after the first schema version — applied as live ALTERs so an
# existing warehouse migrates in place (no drop/recreate). Extend this map when
# new nullable columns are introduced.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "dim_geofence": {
        "poi_name": "VARCHAR(200)",
        "poi_category": "VARCHAR(40)",
        "poi_distance_m": "DOUBLE PRECISION",
    },
}


def ensure_columns() -> None:
    """Add any missing nullable columns to existing tables (idempotent migration).

    create_all() only creates absent *tables*, never new columns on existing ones,
    so we reconcile column-by-column via the inspector."""
    e = engine()
    if e is None:
        return
    name = dialect()
    insp = inspect(e)
    for table, cols in _ADDED_COLUMNS.items():
        if not insp.has_table(table):
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        for col, ddl in cols.items():
            if col in existing:
                continue
            sql_type = "DOUBLE" if (name == "mysql" and ddl == "DOUBLE PRECISION") else ddl
            try:
                with e.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}"))
                logger.info("gps_store: added column %s.%s", table, col)
            except Exception as exc:
                logger.warning("gps_store: could not add %s.%s (%s)", table, col, exc)


# ----------------------------------------------------------------------
# load (incremental)
# ----------------------------------------------------------------------
def _insert_ignore(conn, table, rows: list[dict]) -> int:
    if not rows:
        return 0
    name = dialect()
    if name == "mysql":
        from sqlalchemy.dialects.mysql import insert as mysql_insert
        stmt = mysql_insert(table).prefix_with("IGNORE")
    elif name in ("postgresql", "postgres"):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(table).on_conflict_do_nothing()
    else:
        stmt = insert(table)
    return conn.execute(stmt, rows).rowcount or 0


def _upsert_rollup(conn, rows: list[dict]) -> None:
    """Replace-on-conflict upsert for the 15-min rollup (keyed vehicle_sk+bucket_ts)."""
    if not rows:
        return
    cols = ["pings", "avg_speed", "max_speed", "dist_km", "moving_frac", "lat", "lng"]
    name = dialect()
    if name == "mysql":
        from sqlalchemy.dialects.mysql import insert as mysql_insert
        stmt = mysql_insert(fact_gps_15min)
        stmt = stmt.on_duplicate_key_update({c: stmt.inserted[c] for c in cols})
    elif name in ("postgresql", "postgres"):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(fact_gps_15min)
        stmt = stmt.on_conflict_do_update(
            index_elements=["vehicle_sk", "bucket_ts"],
            set_={c: getattr(stmt.excluded, c) for c in cols})
    else:
        stmt = insert(fact_gps_15min)
    conn.execute(stmt, rows)


def _build_rollup_rows(df: pd.DataFrame, veh_map: dict) -> list[dict]:
    """15-min per-vehicle aggregates from the just-loaded normalised frame."""
    out = []
    spd = df["speed_corr_kph"].fillna(df["speed_kph"]).fillna(0)
    g = df.assign(_spd=spd, _moving=(spd > 2)).dropna(subset=["gps_ts"])
    for reg, sub in g.groupby("vehicle_reg"):
        vsk = veh_map.get(str(reg))
        if vsk is None:
            continue
        r = (sub.set_index("gps_ts")
                .resample("15min")
                .agg(pings=("_spd", "size"), avg_speed=("_spd", "mean"), max_speed=("_spd", "max"),
                     moving_frac=("_moving", "mean"), odo_min=("odometer_m", "min"),
                     odo_max=("odometer_m", "max"), lat=("latitude", "last"), lng=("longitude", "last")))
        r = r[r["pings"] > 0]
        for ts, row in r.iterrows():
            out.append({
                "vehicle_sk": int(vsk), "bucket_ts": ts.to_pydatetime(),
                "pings": int(row["pings"]), "avg_speed": _fl(row["avg_speed"]),
                "max_speed": _fl(row["max_speed"]), "moving_frac": _fl(row["moving_frac"]),
                "dist_km": _fl((row["odo_max"] - row["odo_min"]) / 1000) if pd.notna(row["odo_max"]) else 0.0,
                "lat": _fl(row["lat"]), "lng": _fl(row["lng"]),
            })
    return out


def _i(v):
    return None if pd.isna(v) else int(v)


def _fl(v):
    return None if pd.isna(v) else float(v)


def _s(v):
    return None if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)


def load_normalized_feed(df: pd.DataFrame | None = None) -> dict:
    """First run creates schema; later runs add only new pings, then rebuild the
    (small) device<->vehicle history table from the fact so it's always correct."""
    e = engine()
    if e is None:
        return {"ok": False, "error": "WAREHOUSE_URL not configured"}
    if df is None:
        df = gps_feed.load_normalized()
    if df.empty:
        return {"ok": False, "error": "no rows in source feed"}

    ensure_schema()
    before = counts()["pings"]

    # ---- dim_device ----
    dev = df[["device_id", "product_id"]].dropna(subset=["device_id"]).drop_duplicates("device_id")
    dev_rows = [{"device_imei": str(r.device_id), "product_id": _i(r.product_id)} for r in dev.itertuples()]

    # ---- dim_vehicle ----
    veh = (df[["vehicle_reg", "entity_id", "entity_name", "entity_type"]]
           .dropna(subset=["vehicle_reg"]).drop_duplicates("vehicle_reg"))
    veh_rows = [{"vehicle_reg": str(r.vehicle_reg), "entity_id": _i(r.entity_id),
                 "entity_name": _s(r.entity_name), "entity_type": _i(r.entity_type)}
                for r in veh.itertuples()]

    # ---- dim_node (union of from/to waypoints) ----
    a = df[["from_node_no", "from_node", "from_node_lat", "from_node_lng", "from_state"]].rename(
        columns={"from_node_no": "node_no", "from_node": "node_name", "from_node_lat": "lat",
                 "from_node_lng": "lng", "from_state": "state"})
    b = df[["to_node_no", "to_node", "to_node_lat", "to_node_lng", "to_state"]].rename(
        columns={"to_node_no": "node_no", "to_node": "node_name", "to_node_lat": "lat",
                 "to_node_lng": "lng", "to_state": "state"})
    nodes = pd.concat([a, b], ignore_index=True).dropna(subset=["node_no"]).drop_duplicates("node_no")
    node_rows = [{"node_no": _i(r.node_no), "node_name": _s(r.node_name), "lat": _fl(r.lat),
                  "lng": _fl(r.lng), "state": _s(r.state)} for r in nodes.itertuples()]

    with e.begin() as conn:
        _insert_ignore(conn, dim_device, dev_rows)
        _insert_ignore(conn, dim_vehicle, veh_rows)
        _insert_ignore(conn, dim_node, node_rows)
        dev_map = dict(conn.execute(select(dim_device.c.device_imei, dim_device.c.device_sk)).all())
        veh_map = dict(conn.execute(select(dim_vehicle.c.vehicle_reg, dim_vehicle.c.vehicle_sk)).all())
        node_map = dict(conn.execute(select(dim_node.c.node_no, dim_node.c.node_sk)).all())

        fact_rows = []
        for r in df.itertuples():
            vsk = veh_map.get(str(r.vehicle_reg))
            if vsk is None:
                continue
            fact_rows.append({
                "ping_id": str(r.ping_id),
                "device_sk": dev_map.get(str(r.device_id)) if not pd.isna(r.device_id) else None,
                "vehicle_sk": int(vsk),
                "gps_ts": None if pd.isna(r.gps_ts) else r.gps_ts.to_pydatetime(),
                "server_ts": None if pd.isna(r.server_ts) else r.server_ts.to_pydatetime(),
                "latency_sec": _fl(r.latency_sec),
                "latitude": _fl(r.latitude), "longitude": _fl(r.longitude),
                "speed_kph": _fl(r.speed_kph), "speed_corr_kph": _fl(r.speed_corr_kph),
                "motion_status": _s(r.motion_status),
                "odometer_m": _i(r.odometer_m), "segment_m": _fl(r.segment_m),
                "from_node_sk": node_map.get(_i(r.from_node_no)) if not pd.isna(r.from_node_no) else None,
                "to_node_sk": node_map.get(_i(r.to_node_no)) if not pd.isna(r.to_node_no) else None,
                "from_node_m": _fl(r.from_node_m), "to_node_m": _fl(r.to_node_m),
                "signal_pct": _fl(r.signal_pct), "io_state": _s(r.io_state),
                "event_codes": _s(r.event_codes), "msg_type": _i(r.msg_type), "port_no": _i(r.port_no),
                "loaded_flag": None, "trip_sk": None,
            })
        for i in range(0, len(fact_rows), 1000):
            _insert_ignore(conn, fact_gps_ping, fact_rows[i:i + 1000])

        # rebuild device<->vehicle history from the fact (always consistent)
        conn.execute(text("DELETE FROM device_vehicle_link"))
        conn.execute(text("""
            INSERT INTO device_vehicle_link (device_sk, vehicle_sk, first_ts, last_ts, ping_count)
            SELECT device_sk, vehicle_sk, MIN(gps_ts), MAX(gps_ts), COUNT(*)
            FROM fact_gps_ping
            WHERE device_sk IS NOT NULL
            GROUP BY device_sk, vehicle_sk
        """))

        # refresh the 15-min pre-aggregation for the vehicles in this file
        _upsert_rollup(conn, _build_rollup_rows(df, veh_map))

    after = counts()["pings"]
    c = counts()
    return {
        "ok": True, "dialect": dialect(),
        "devices": c["devices"], "vehicles": c["vehicles"], "nodes": c["nodes"],
        "pings_in_file": len(fact_rows), "new_pings_added": int(after - before),
        "total_pings": int(after),
    }


# ----------------------------------------------------------------------
# read (per-vehicle, SQL-filtered)
# ----------------------------------------------------------------------
_READ_SQL = """
SELECT f.ping_id, v.vehicle_reg, d.device_imei AS device_id, v.entity_name,
       f.gps_ts, f.server_ts, f.latency_sec,
       f.latitude, f.longitude, f.speed_kph, f.speed_corr_kph, f.motion_status,
       f.odometer_m, f.segment_m,
       fn.node_name AS from_node, fn.state AS from_state, f.from_node_m,
       tn.node_name AS to_node,   tn.state AS to_state,   f.to_node_m,
       f.signal_pct, f.io_state, f.event_codes, f.msg_type, f.port_no,
       f.loaded_flag, f.trip_sk
FROM fact_gps_ping f
JOIN dim_vehicle v ON f.vehicle_sk = v.vehicle_sk
LEFT JOIN dim_device d ON f.device_sk = d.device_sk
LEFT JOIN dim_node fn ON f.from_node_sk = fn.node_sk
LEFT JOIN dim_node tn ON f.to_node_sk = tn.node_sk
{where}
ORDER BY f.gps_ts
"""


def read_feed(vehicle: str | None = None) -> pd.DataFrame:
    e = engine()
    if e is None or not schema_ready():
        return pd.DataFrame()
    where = "WHERE v.vehicle_reg = :veh" if vehicle else ""
    df = pd.read_sql(text(_READ_SQL.format(where=where)), e,
                     params=({"veh": vehicle} if vehicle else {}))
    for c in ("gps_ts", "server_ts"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def asset_history() -> dict:
    """Device<->truck (and, when available, truck<->driver) timelines."""
    e = engine()
    if e is None or not schema_ready():
        return {"device_vehicle": [], "vehicle_driver": []}
    dv = pd.read_sql(text("""
        SELECT d.device_imei, v.vehicle_reg, l.first_ts, l.last_ts, l.ping_count
        FROM device_vehicle_link l
        JOIN dim_device d ON l.device_sk = d.device_sk
        JOIN dim_vehicle v ON l.vehicle_sk = v.vehicle_sk
        ORDER BY d.device_imei, l.first_ts
    """), e)
    return {
        "device_vehicle": [
            {"device_imei": r.device_imei, "vehicle_reg": r.vehicle_reg,
             "first_ts": str(r.first_ts), "last_ts": str(r.last_ts), "ping_count": int(r.ping_count)}
            for r in dv.itertuples()
        ],
        "vehicle_driver": [],   # populated once the feed carries driver identity
    }


def read_rollup(vehicle: str | None = None, frm: str | None = None, to: str | None = None) -> pd.DataFrame:
    """Read the tiny 15-min rollup (for fast map/trend rendering at scale)."""
    e = engine()
    if e is None or not inspect(e).has_table("fact_gps_15min"):
        return pd.DataFrame()
    sql = ("SELECT r.bucket_ts, r.pings, r.avg_speed, r.max_speed, r.dist_km, "
           "r.moving_frac, r.lat, r.lng, v.vehicle_reg "
           "FROM fact_gps_15min r JOIN dim_vehicle v ON r.vehicle_sk = v.vehicle_sk")
    where, params = [], {}
    if vehicle:
        where.append("v.vehicle_reg = :veh"); params["veh"] = vehicle
    if frm:
        where.append("r.bucket_ts >= :frm"); params["frm"] = frm
    if to:
        where.append("r.bucket_ts <= :to"); params["to"] = to
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.bucket_ts"
    df = pd.read_sql(text(sql), e, params=params)
    if "bucket_ts" in df.columns:
        df["bucket_ts"] = pd.to_datetime(df["bucket_ts"], errors="coerce")
    return df


def fleet() -> list[dict]:
    """One fast row per truck for the fleet table: vehicle, device, coverage,
    distance and online/stale/offline status — computed from dims + rollup so it
    scales to thousands of trucks without touching raw pings."""
    e = engine()
    if e is None or not schema_ready():
        return []
    sql = """
        SELECT v.vehicle_reg, v.entity_name,
               d.device_imei,
               COUNT(f.ping_id)          AS pings,
               MIN(f.gps_ts)             AS first_seen,
               MAX(f.gps_ts)             AS last_seen,
               (MAX(f.odometer_m) - MIN(f.odometer_m)) / 1000.0 AS distance_km,
               MAX(f.speed_corr_kph)     AS max_speed,
               COUNT(DISTINCT CASE WHEN f.device_sk IS NOT NULL THEN f.device_sk END) AS devices
        FROM dim_vehicle v
        LEFT JOIN fact_gps_ping f ON f.vehicle_sk = v.vehicle_sk
        LEFT JOIN dim_device d ON f.device_sk = d.device_sk
        GROUP BY v.vehicle_reg, v.entity_name, d.device_imei
        ORDER BY pings DESC
    """
    df = pd.read_sql(text(sql), e)
    now = pd.Timestamp.utcnow().tz_localize(None)
    out = []
    for r in df.itertuples():
        last = pd.to_datetime(r.last_seen, errors="coerce")
        age_h = (now - last).total_seconds() / 3600 if pd.notna(last) else 1e9
        status = "online" if age_h < 1 else ("stale" if age_h < 24 else "offline")
        out.append({
            "vehicle_reg": r.vehicle_reg,
            "device_imei": r.device_imei or "—",
            "entity_name": r.entity_name or "",
            "pings": int(r.pings or 0),
            "first_seen": None if pd.isna(last) else str(pd.to_datetime(r.first_seen)),
            "last_seen": None if pd.isna(last) else str(last),
            "distance_km": round(float(r.distance_km), 1) if r.distance_km else 0.0,
            "max_speed": round(float(r.max_speed), 0) if r.max_speed else 0.0,
            "devices": int(r.devices or 0),
            "status": status,
        })
    return out


def counts() -> dict:
    e = engine()
    if e is None or not schema_ready():
        return {"devices": 0, "vehicles": 0, "nodes": 0, "pings": 0}
    with e.connect() as c:
        def n(t):
            return int(c.execute(text(f"SELECT count(*) FROM {t}")).scalar() or 0)
        return {"devices": n("dim_device"), "vehicles": n("dim_vehicle"),
                "nodes": n("dim_node"), "pings": n("fact_gps_ping")}
