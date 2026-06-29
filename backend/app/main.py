"""
nextGen-FMS backend API entry point.

Run with:
    uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

Data source: neXgen-Lakehouse (Iceberg) via the lakehouse/ package.
Currently in MOCK mode — flip USE_MOCK_DATA=false in .env once credentials
are available.
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

from backend.app.api import dashboard, trips, system, ml, data, operations, analytics, gps, route_intel
from lakehouse.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

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


@app.get("/health")
def health():
    if settings.use_mock_data:
        src = "MOCK"
    elif not settings.clickhouse_password:
        src = "LAKEHOUSE"   # via PyIceberg fallback
    else:
        src = "LAKEHOUSE"
    return {
        "status": "ok",
        "service": "nextgen-fms-api",
        "data_source": src,
        "lakehouse_url": settings.lakehouse_base_url,
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


data_mode = "MOCK" if settings.use_mock_data else (
    "ICEBERG_FALLBACK" if not settings.clickhouse_password else "LIVE_CH"
)
logger.info("neXgen-FMS API ready — data_mode=%s, routes=%d", data_mode, len(app.routes))
