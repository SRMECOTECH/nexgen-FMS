"""
nextGen-FMS backend API entry point.

Run with (port 9001 — matches the frontend's VITE_API_URL; do NOT use 8000,
that belongs to the smart-truck backend):
    uvicorn backend.app.main:app --host 0.0.0.0 --port 9001 --reload
or simply:
    python -m backend.app.main   # reads FMS_BACKEND_PORT (9001) from .env

Data source: Excel feeds (data/*.xlsx) → local MySQL warehouse via the
lakehouse/ package. Iceberg/MinIO/ClickHouse are hard-disabled
(DISABLE_ICEBERG=true in .env) and only wired up on demand.
"""

import logging
import time
from pathlib import Path

# Load .env BEFORE importing anything that reads settings
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass  # settings module still falls back to defaults

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api import dashboard, trips, system, ml, data, operations, analytics, gps, route_intel, ai, observe, settings as settings_api
from lakehouse.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Capture every backend log line (incl. tracebacks) into the in-memory ring
# buffer that the System → Logs page reads. Must happen before routers import.
from backend.app.core import logbuffer  # noqa: E402
logbuffer.install()

settings = get_settings()

app = FastAPI(
    title="neXgen-FMS API",
    description="Fleet management platform — lakehouse-backed.",
    version="0.1.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """Return unhandled errors as JSON with the real message instead of letting
    them bubble to Starlette's outermost 500 (which ships WITHOUT CORS headers and
    makes the browser report a misleading "CORS policy" error). Handled here, the
    response still passes back through CORSMiddleware and carries Access-Control-*."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc), "path": request.url.path},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    logger.info(">>> %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("!!! %s %s UNHANDLED EXCEPTION", request.method, request.url.path)
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info("<<< %s %s %s %.0fms", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(trips.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(ml.router, prefix="/api/v1")
app.include_router(data.router, prefix="/api/v1")
app.include_router(operations.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(gps.router, prefix="/api/v1")
app.include_router(route_intel.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(observe.router, prefix="/api/v1")
app.include_router(settings_api.router, prefix="/api/v1")


@app.on_event("startup")
def _bootstrap_database():
    """Self-initialise the warehouse on a fresh clone: create the MySQL database
    named in WAREHOUSE_URL plus every missing table (idempotent). Runs in a
    background thread so an unreachable DB server never blocks startup — the
    app keeps serving from mock/Excel fallbacks until MySQL is up, and the
    Settings page can re-run this any time via POST /api/v1/settings/db/init."""
    import threading
    from lakehouse import bootstrap

    def _go():
        status = bootstrap.init_all()
        if status["ok"]:
            logger.info("startup: database bootstrap complete — warehouse ready")
        else:
            failed = {k: v.get("error") for k, v in status["steps"].items() if not v.get("ok")}
            logger.warning("startup: database bootstrap incomplete: %s", failed)

    threading.Thread(target=_go, daemon=True).start()


@app.on_event("startup")
def _warm_caches():
    """Pre-load the gps_feed snapshot in a background thread so the first GPS
    page view hits a warm cache instead of stampeding remote Neon with 8 reads."""
    import threading
    from lakehouse import warehouse

    def _go():
        n = warehouse.warm_gps_cache()
        logger.info("startup: gps_feed cache warmed (%s rows)", n)

    threading.Thread(target=_go, daemon=True).start()


@app.on_event("shutdown")
async def _close_ml_client():
    """Drain the ML proxy's HTTP keep-alive pool when uvicorn shuts down."""
    from backend.app.services import ml_client
    await ml_client.aclose()


@app.on_event("startup")
def _launch_streamlit():
    """Spawn the 'Detailed Analysis of GPS Data' Streamlit page in the
    background. Idempotent — does nothing if the port is already up."""
    import threading
    from route_intelligence import streamlit_launcher

    def _go():
        s = streamlit_launcher.ensure_started()
        logger.info("startup: streamlit launcher → %s", s)

    threading.Thread(target=_go, daemon=True).start()


def _describe_data_source() -> dict:
    """Honest description of where data actually comes from, based on the live
    .env config — not a stale label. Today: Excel feeds → local MySQL warehouse,
    with Iceberg hard-disabled. Only reports Iceberg when it is genuinely wired."""
    import os

    if settings.use_mock_data:
        return {"mode": "MOCK", "ingest": "fixtures", "warehouse": None}

    warehouse_url = os.getenv("WAREHOUSE_URL", "")
    if warehouse_url.startswith("mysql"):
        engine = "MYSQL"
    elif "postgres" in warehouse_url:
        engine = "POSTGRES"
    else:
        engine = "WAREHOUSE"

    # host:port only — never leak credentials into a health payload
    host = ""
    if "@" in warehouse_url:
        host = warehouse_url.split("@", 1)[1].split("/", 1)[0]

    ingest = os.getenv("INGEST_SOURCE", "sample").lower()
    iceberg_live = ingest == "iceberg" and not settings.disable_iceberg
    ingest_label = "ICEBERG" if iceberg_live else "EXCEL"

    return {
        "mode": f"{ingest_label}→{engine}",
        "ingest": ingest_label,
        "warehouse": engine,
        "warehouse_host": host,
        "iceberg_disabled": settings.disable_iceberg,
    }


@app.get("/health")
def health():
    src = _describe_data_source()
    return {
        "status": "ok",
        "service": "nextgen-fms-api",
        "version": "0.2.0",
        "data_source": src["mode"],
        **src,
    }


@app.get("/api/v1")
def api_root():
    return {
        "service": "nextGen-FMS API v1",
        "docs": "/docs",
        "endpoints": {
            "dashboard_summary": "/api/v1/dashboard/summary",
            "active_trips": "/api/v1/trips/active",
            "trip_detail": "/api/v1/trips/{trip_no}",
        },
    }


logger.info(
    "neXgen-FMS API ready — data_mode=%s, routes=%d",
    _describe_data_source()["mode"],
    len(app.routes),
)


if __name__ == "__main__":
    # Allows `python -m backend.app.main` and reads the port from .env.
    # Keeps the dev workflow port-config in one place (FMS_BACKEND_PORT).
    import os
    import uvicorn

    host = os.getenv("FMS_BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("FMS_BACKEND_PORT", "9001"))
    uvicorn.run(
        "backend.app.main:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=["backend", "lakehouse"],
    )
