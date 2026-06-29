"""Data catalog, browser (SQL), schema, connectors, IoT devices."""

from datetime import datetime, timedelta
import random
import re

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.core.deps import get_clickhouse
from lakehouse.mock_data import TABLE_BUILDERS, get_mock_table
from lakehouse import warehouse

router = APIRouter(prefix="/data", tags=["data"])

_RNG = random.Random(13)


@router.get("/catalog")
def list_tables():
    out = []
    for name in TABLE_BUILDERS:
        df = get_mock_table(name)
        required_cols = sum(1 for _ in df.columns)  # placeholder until we read real schema
        out.append({
            "name": name,
            "namespace": "telemetry",
            "rows_estimate": _RNG.randint(1_000, 50_000_000),
            "size_mb": round(_RNG.uniform(2.5, 12_000), 2),
            "last_updated": (datetime.now() - timedelta(minutes=_RNG.randint(1, 240))).isoformat(),
            "required_cols": required_cols,
            "optional_cols": 0,
            "columns": list(df.columns),
        })
    return {"tables": out}


@router.get("/catalog/{table_name}/schema")
def table_schema(table_name: str):
    df = get_mock_table(table_name)
    fields = []
    for i, col in enumerate(df.columns, start=1):
        py_type = str(df[col].dtype)
        if "int" in py_type:    t = "long"
        elif "float" in py_type: t = "double"
        elif "datetime" in py_type or "object" in py_type and "timestamp" in col.lower(): t = "timestamp"
        elif "bool" in py_type: t = "boolean"
        else: t = "string"
        fields.append({"position": i, "name": col, "type": t, "required": True})
    return {"table": table_name, "namespace": "telemetry", "fields": fields, "total_fields": len(fields)}


@router.get("/catalog/{table_name}/sample")
def table_sample(table_name: str, limit: int = 10):
    df = get_mock_table(table_name).head(limit)
    return {
        "table": table_name,
        "rows": df.astype(str).to_dict(orient="records"),
        "columns": list(df.columns),
    }


@router.get("/connectors")
def list_connectors():
    items = []
    for tbl in TABLE_BUILDERS:
        items.append({
            "name": f"lakehouse:{tbl}",
            "source_table": f"telemetry.{tbl}",
            "format": "Iceberg",
            "rows_pulled": _RNG.randint(1_000, 5_000_000),
            "last_pull": (datetime.now() - timedelta(minutes=_RNG.randint(1, 60))).isoformat(),
            "status": _RNG.choice(["active", "active", "active", "paused"]),
            "latency_ms": _RNG.randint(40, 2400),
        })
    return {"connectors": items}


@router.get("/devices")
def list_devices():
    devices = []
    for i in range(20):
        age = _RNG.choice([5, 15, 45, 120, 600, 3600, 86400])
        if age < 60: status = "online"
        elif age < 600: status = "stale"
        else: status = "offline"
        devices.append({
            "vehicle_id": f"MH12AB{1000 + i:04d}",
            "device_id": f"DEV-{5000 + i}",
            "last_ping": (datetime.now() - timedelta(seconds=age)).isoformat(),
            "ping_age_sec": age,
            "status": status,
            "signal_strength": _RNG.randint(-110, -55),
            "satellites": _RNG.randint(3, 12),
            "battery_voltage": round(_RNG.uniform(11.4, 14.2), 2),
        })
    return {"devices": devices, "online": sum(1 for d in devices if d["status"] == "online"),
            "stale": sum(1 for d in devices if d["status"] == "stale"),
            "offline": sum(1 for d in devices if d["status"] == "offline")}


# ------------------------------ Data Browser SQL ------------------------------

class QueryRequest(BaseModel):
    sql: str


@router.post("/browser/query")
def run_query(body: QueryRequest):
    """Safe sandbox: only SELECT against known tables (validated via mock client).
    In real mode this delegates to ClickHouseClient.query()."""
    sql = body.sql.strip()
    if not re.match(r"^select\b", sql, re.IGNORECASE):
        return {"columns": [], "rows": [], "error": "Only SELECT statements are allowed."}
    ch = get_clickhouse()
    try:
        df = ch.query(sql)
        return {
            "columns": list(df.columns),
            "rows": df.astype(str).values.tolist()[:500],
            "row_count": len(df),
        }
    except Exception as exc:
        return {"columns": [], "rows": [], "error": str(exc)}


# ------------------------------ GPS feed upload (one button) ------------------------------

@router.post("/upload-gps")
def upload_gps():
    """One-button upload into the NORMALISED warehouse (dim_vehicle / dim_node /
    fact_gps_ping).

    First run creates the schema; every later run only INSERTs pings whose
    ping_id is new (INSERT IGNORE / ON CONFLICT DO NOTHING), so re-uploading the
    same or an overlapping file just adds the new rows. Works on MySQL and
    Postgres — only WAREHOUSE_URL in .env decides which, nothing else changes.
    """
    from lakehouse import gps_store

    if not gps_store.warehouse_url():
        return {"ok": False, "error": "WAREHOUSE_URL is not configured in .env"}
    try:
        result = gps_store.load_normalized_feed()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    warehouse.invalidate_gps_cache()  # so subsequent reads see the fresh rows
    # rebuild geofences + stop events (fast, local); geocoding is on-demand
    try:
        from lakehouse import geofence
        gf = geofence.build_geofences_and_stops()
        result["geofences"] = gf.get("geofences", 0)
        result["stop_events"] = gf.get("stop_events", 0)
    except Exception as exc:
        result["geofence_error"] = str(exc)
    result["destination"] = warehouse.gps_source_label()
    return result


@router.get("/upload-gps/status")
def upload_gps_status():
    """Where the GPS feed currently lives + how many rows are in the warehouse."""
    from lakehouse import gps_store
    c = gps_store.counts()
    return {
        "warehouse_available": warehouse.is_available(),
        "dialect": gps_store.dialect(),
        "warehouse_rows": c["pings"],
        "vehicles": c["vehicles"],
        "nodes": c["nodes"],
        "schema_ready": gps_store.schema_ready(),
        "serving_from": warehouse.gps_source_label(),
    }
