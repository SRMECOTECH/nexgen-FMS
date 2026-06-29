"""
Dashboard KPI endpoints — power the cards on the landing page.

These read the SAME real trip master data (MySQL `fact_trip`, loaded from
data/trpdtaopn_*.xlsx) that the Trips page uses, so the headline numbers always
agree. (The old implementation queried a mock ClickHouse table and reported ~20
trips while the Trips page showed the real 284 — that mismatch is fixed here.)
"""

from fastapi import APIRouter

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_summary():
    """Fleet-wide KPIs shown as cards across the top of the dashboard."""
    from lakehouse import trip_store
    return trip_store.dashboard_summary()
