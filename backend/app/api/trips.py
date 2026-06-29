"""
Example route — proves the lakehouse client wiring end-to-end.

Returns a paginated list of active trips, joined with the latest leg detail.
In MOCK mode (default), responses are realistic sample rows. When the real
lakehouse is wired in .env, the same SQL will run against ClickHouse.
"""

from fastapi import APIRouter, Depends, Query

from backend.app.core.deps import get_clickhouse
from lakehouse import ClickHouseClient

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("/active")
def list_active_trips(limit: int = Query(200, ge=1, le=1000)):
    """Trips currently in transit (status O/T) — real MySQL fact_trip data,
    same source as /trips/db so the dashboard and Trips page agree."""
    from lakehouse import trip_store
    rows = trip_store.active_trips(limit=limit)
    return {"count": len(rows), "trips": rows}


# ----------------------------------------------------------------------
# Real trip master data (MySQL) — ingested from data/trpdtaopn_*.xlsx
# ----------------------------------------------------------------------
@router.post("/upload")
def upload_trips():
    """One-button ingest of the trip workbook (data/trpdtaopn_*.xlsx) into MySQL
    (fact_trip + fact_trip_leg). Full snapshot refresh — safe to re-run."""
    from lakehouse import trip_store, gps_store
    if not gps_store.warehouse_url():
        return {"ok": False, "error": "WAREHOUSE_URL is not configured in .env"}
    try:
        return trip_store.load_trips()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/db/status")
def trips_db_status():
    from lakehouse import trip_store
    return trip_store.counts()


@router.get("/db/summary")
def trips_db_summary():
    from lakehouse import trip_store
    return {**trip_store.summary(), **{"counts": trip_store.counts()}}


@router.get("/parties/{dim}")
def trips_parties(dim: str):
    """Trips grouped by consignor | consignee | transporter."""
    from lakehouse import trip_store
    if dim not in ("consignor", "consignee", "transporter"):
        return {"error": "dim must be consignor | consignee | transporter", "parties": []}
    return {"dim": dim, "parties": trip_store.party_summary(dim)}


@router.get("/db")
def trips_db_list(search: str | None = Query(None), status: str | None = Query(None),
                  consignor: str | None = Query(None), consignee: str | None = Query(None),
                  transporter: str | None = Query(None), limit: int = Query(500, ge=1, le=2000)):
    from lakehouse import trip_store
    rows = trip_store.list_trips(search=search, status=status, limit=limit,
                                 consignor=consignor, consignee=consignee, transporter=transporter)
    return {"count": len(rows), "trips": rows}


@router.get("/db/{trip_no}")
def trips_db_detail(trip_no: int):
    from lakehouse import trip_store
    return trip_store.trip_detail(trip_no)


@router.get("/{trip_no}")
def get_trip_detail(trip_no: int, ch: ClickHouseClient = Depends(get_clickhouse)):
    """Full trip header + all legs."""
    header = ch.query(f"SELECT * FROM telemetry.fact_trips WHERE trip_no = {trip_no} LIMIT 1")
    legs = ch.query(f"SELECT * FROM telemetry.fact_trip_legs WHERE trip_no = {trip_no} ORDER BY leg_seq")

    if header.empty:
        return {"error": f"Trip {trip_no} not found"}

    return {
        "header": header.iloc[0].to_dict(),
        "legs": legs.to_dict(orient="records"),
        "num_legs": len(legs),
    }
