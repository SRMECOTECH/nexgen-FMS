"""System health, monitoring, logs, recovery."""

from datetime import datetime, timedelta
import random

from fastapi import APIRouter, Query

router = APIRouter(prefix="/system", tags=["system"])

_RNG = random.Random(7)


@router.get("/monitoring")
def get_monitoring():
    """Pipeline junctions — mirror of lakehouse Monitoring view but scoped to OUR ML/data flows."""
    junctions = [
        {"name": "Lakehouse Fetcher",   "lane": "ingest",  "status": "live"},
        {"name": "Feature Builder",     "lane": "transform", "status": "live"},
        {"name": "ETA Predictor",       "lane": "ml",      "status": "live"},
        {"name": "SLA Classifier",      "lane": "ml",      "status": "live"},
        {"name": "Driver Scorer",       "lane": "ml",      "status": "stale"},
        {"name": "Anomaly Detector",    "lane": "ml",      "status": "live"},
        {"name": "Alert Generator",     "lane": "alerts",  "status": "live"},
        {"name": "Notification Pusher", "lane": "alerts",  "status": "stale"},
    ]
    out = []
    for j in junctions:
        out.append({
            **j,
            "event_lag_ms": _RNG.randint(0, 50) if j["status"] == "live" else _RNG.randint(2000, 20000),
            "proc_lag_ms": _RNG.randint(0, 30),
            "events_per_min": _RNG.randint(20, 300) if j["status"] == "live" else 0,
            "errors_per_min": 0 if j["status"] == "live" else _RNG.randint(1, 8),
            "last_seen": (datetime.now() - timedelta(seconds=_RNG.randint(1, 240))).isoformat(),
            "avg_latency_ms": round(_RNG.uniform(5, 950), 2),
        })
    return {"junctions": out}


@router.get("/logs")
def get_logs(
    limit: int = Query(200, ge=1, le=1000),
    level: str | None = Query(None, description="Minimum level: DEBUG|INFO|WARNING|ERROR"),
    search: str | None = Query(None, description="Substring match on service/message/traceback"),
    after_id: int = Query(0, ge=0, description="Only records newer than this id (incremental poll)"),
):
    """REAL backend logs from the in-memory ring buffer (see core/logbuffer.py).
    Every line the backend logs — startup, DB bootstrap, per-request traces,
    unhandled exceptions with full tracebacks — is visible here and on the
    System → Logs page in the UI."""
    from backend.app.core import logbuffer

    return logbuffer.get_logs(limit=limit, level=level, search=search, after_id=after_id)


@router.get("/recovery")
def get_recovery():
    """Dead-letter queue for failed ML predictions and lakehouse fetches."""
    items = []
    for i in range(8):
        items.append({
            "id": f"dlq-{1000 + i}",
            "type": _RNG.choice(["ml_prediction", "lakehouse_fetch", "alert_dispatch"]),
            "failed_at": (datetime.now() - timedelta(minutes=_RNG.randint(2, 240))).isoformat(),
            "retry_count": _RNG.randint(0, 3),
            "error": _RNG.choice([
                "ConnectionTimeout",
                "ModelNotFound: driver_scorer v4",
                "ClickHouseError: read timeout",
                "ValidationError: missing trip_no",
            ]),
            "payload_size_bytes": _RNG.randint(120, 4096),
        })
    return {"items": items, "total": len(items)}
