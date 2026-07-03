"""
One-call database bootstrap — makes a fresh clone self-initialising.

``init_all()`` is invoked on backend startup (see backend/app/main.py) and can
be re-run any time from the Settings page (POST /api/v1/settings/db/init).
It is idempotent:

  1. Creates the MySQL database named in WAREHOUSE_URL if it doesn't exist
     (on Postgres the database must already exist — Neon creates it for you).
  2. Creates every warehouse table that is missing:
       - gps_store   → dim_device/dim_vehicle/…/fact_gps_ping/fact_stop_event
       - trip_store  → fact_trip / fact_trip_leg
       - route_intelligence.db → all ri_* result tables
  3. Applies in-place column migrations (gps_store.ensure_columns).

Nothing here raises on an unreachable server — callers get a status dict and
the app keeps serving (mock/Excel fallbacks stay usable) until MySQL is up.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _step(status: Dict[str, Any], name: str, fn) -> None:
    try:
        fn()
        status["steps"][name] = {"ok": True}
    except Exception as exc:  # noqa: BLE001 — report, never crash startup
        status["ok"] = False
        status["steps"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        logger.warning("bootstrap: step %s failed: %s", name, exc)


def init_all() -> Dict[str, Any]:
    """Create database + every table (idempotent). Returns a status report."""
    import os

    status: Dict[str, Any] = {"ok": True, "steps": {}, "url_configured": bool(os.environ.get("WAREHOUSE_URL"))}
    if not status["url_configured"]:
        status["ok"] = False
        status["steps"]["config"] = {"ok": False, "error": "WAREHOUSE_URL is not set in .env"}
        return status

    from lakehouse import gps_store, trip_store

    _step(status, "create_database", gps_store._ensure_mysql_database)
    _step(status, "gps_tables", gps_store.ensure_schema)
    _step(status, "trip_tables", trip_store.ensure_schema)

    def _ri():
        from route_intelligence import db as ri_db
        ri_db.bootstrap(force=True)

    _step(status, "route_intel_tables", _ri)

    if status["ok"]:
        logger.info("bootstrap: warehouse ready (database + all tables ensured)")
    return status


def db_status() -> Dict[str, Any]:
    """Live snapshot of the warehouse: reachable? which tables exist? row counts."""
    import os

    from sqlalchemy import inspect, text
    from sqlalchemy.engine import make_url

    from lakehouse import gps_store

    url = os.environ.get("WAREHOUSE_URL", "")
    out: Dict[str, Any] = {
        "configured": bool(url),
        "url_masked": _mask_url(url),
        "reachable": False,
        "dialect": None,
        "database": None,
        "tables": [],
        "error": None,
    }
    if not url:
        out["error"] = "WAREHOUSE_URL is not set"
        return out

    try:
        out["database"] = make_url(gps_store._normalize_url(url)).database
    except Exception:
        pass

    eng = gps_store.engine()
    if eng is None:
        out["error"] = "engine could not be created"
        return out
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        out["reachable"] = True
        out["dialect"] = eng.dialect.name
        insp = inspect(eng)
        for t in sorted(insp.get_table_names()):
            try:
                with eng.connect() as c:
                    n = c.execute(text(f"SELECT COUNT(*) FROM `{t}`" if eng.dialect.name == "mysql"
                                       else f'SELECT COUNT(*) FROM "{t}"')).scalar()
            except Exception:
                n = None
            out["tables"].append({"name": t, "rows": int(n) if n is not None else None})
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _mask_url(url: str) -> str:
    """mysql+pymysql://root:****@127.0.0.1:3306/nextgen_fms — never leak passwords."""
    if not url:
        return ""
    try:
        from sqlalchemy.engine import make_url
        u = make_url(url)
        if u.password:
            u = u.set(password="****")
        return str(u)
    except Exception:
        return url.split("@")[-1] if "@" in url else url
