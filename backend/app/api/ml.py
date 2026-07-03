"""
/api/v1/ml/* — thin proxy router over the smart-truck ML subscription API.

Every route forwards to ``backend.app.services.ml_client`` which holds the
``X-API-Key`` and base URL. The frontend should always go through this router
(never call ml_service directly) so the subscription key never leaves the
server and tier errors come back as normal FMS errors.

For the request/response shapes see ``../smart-truck/docs/API_REFERENCE.md``.
The legacy ``/ml/pipelines`` mock — used by the older ML Pipelines UI page —
is kept under ``/ml/pipelines`` for backward compatibility until that page is
migrated to the new Live Thinking view.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.services import ml_client
from backend.app.services.ml_client import MLAuthError, MLNotReadyError, MLProxyError, MLUpstreamError

router = APIRouter(prefix="/ml", tags=["ml"])


# ---------------------------------------------------------------------------
# Error translation — proxy errors → FastAPI HTTPException
# ---------------------------------------------------------------------------

def _raise(exc: MLProxyError) -> None:
    """Map an ml_client error to the closest HTTP status for FMS consumers."""
    if isinstance(exc, MLAuthError):
        # Don't echo upstream 401 to the browser — that would confuse the FMS
        # session. Surface as 502 (bad gateway) so the UI shows "ML key issue".
        raise HTTPException(status_code=502, detail=f"ML subscription auth failed: {exc.detail}")
    if isinstance(exc, MLNotReadyError):
        raise HTTPException(status_code=404, detail=exc.detail)
    if isinstance(exc, MLUpstreamError):
        raise HTTPException(status_code=502, detail=f"ML service unreachable: {exc.detail}")
    raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class ETAReq(BaseModel):
    origin: str
    destination: str
    driver_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    trip_km: Optional[float] = None
    trip_start: Optional[str] = Field(None, description="ISO datetime; defaults to now upstream")


class SLAReq(ETAReq):
    """Same shape as ETAReq."""


class RouteOptimizeReq(BaseModel):
    origin: str
    destination: str
    trip_km: Optional[float] = None
    hour: Optional[int] = Field(None, ge=0, le=23)
    day_of_week: Optional[int] = Field(None, ge=0, le=6)


class DriverRecReq(BaseModel):
    origin: str
    destination: str
    top_n: int = Field(10, ge=1, le=100)


# ---------------------------------------------------------------------------
# Proxy routes  —  same shape & semantics as API_REFERENCE.md §3-§22
# ---------------------------------------------------------------------------

@router.get("/health")
async def ml_health():
    try:
        return await ml_client.health()
    except MLProxyError as e:
        _raise(e)


@router.get("/landing")
async def ml_landing():
    try:
        return await ml_client.landing()
    except MLProxyError as e:
        _raise(e)


@router.post("/predict/eta")
async def predict_eta(req: ETAReq):
    try:
        return await ml_client.predict_eta(**req.model_dump(exclude_none=True))
    except MLProxyError as e:
        _raise(e)


@router.post("/predict/sla")
async def predict_sla(req: SLAReq):
    try:
        return await ml_client.predict_sla(**req.model_dump(exclude_none=True))
    except MLProxyError as e:
        _raise(e)


@router.post("/scan/anomalies")
async def scan_anomalies(days: int = Query(7, ge=1, le=90)):
    try:
        return await ml_client.scan_anomalies(days=days)
    except MLProxyError as e:
        _raise(e)


@router.get("/drivers/scores")
async def driver_scores(limit: int = Query(100, ge=1, le=1000)):
    try:
        return await ml_client.driver_scores(limit=limit)
    except MLProxyError as e:
        _raise(e)


@router.get("/drivers/{driver_id}/score")
async def driver_score(driver_id: int):
    try:
        return await ml_client.driver_score(driver_id)
    except MLProxyError as e:
        _raise(e)


@router.get("/drivers/fatigue")
async def fleet_fatigue():
    try:
        return await ml_client.fleet_fatigue()
    except MLProxyError as e:
        _raise(e)


@router.get("/drivers/{driver_id}/fatigue")
async def driver_fatigue(driver_id: int):
    try:
        return await ml_client.driver_fatigue(driver_id)
    except MLProxyError as e:
        _raise(e)


@router.get("/forecast/demand")
async def forecast_demand(route: Optional[str] = None):
    try:
        return await ml_client.forecast_demand(route=route)
    except MLProxyError as e:
        _raise(e)


@router.get("/forecast/trips")
async def forecast_trips(route: Optional[str] = None):
    try:
        return await ml_client.forecast_trips(route=route)
    except MLProxyError as e:
        _raise(e)


@router.post("/optimize/route")
async def optimize_route(req: RouteOptimizeReq):
    try:
        return await ml_client.optimize_route(**req.model_dump(exclude_none=True))
    except MLProxyError as e:
        _raise(e)


@router.get("/optimize/hubs")
async def optimize_hubs():
    try:
        return await ml_client.optimize_hubs()
    except MLProxyError as e:
        _raise(e)


@router.post("/recommend/drivers")
async def recommend_drivers(req: DriverRecReq):
    try:
        return await ml_client.recommend_drivers(**req.model_dump())
    except MLProxyError as e:
        _raise(e)


@router.get("/clients")
async def clients():
    try:
        return await ml_client.clients()
    except MLProxyError as e:
        _raise(e)


@router.get("/clients/forecast")
async def clients_forecast(client: Optional[str] = None):
    try:
        return await ml_client.clients_forecast(client=client)
    except MLProxyError as e:
        _raise(e)


@router.get("/clients/{client_name}/profile")
async def client_profile(client_name: str):
    try:
        return await ml_client.client_profile(client_name)
    except MLProxyError as e:
        _raise(e)


@router.get("/models")
async def models():
    try:
        return await ml_client.models()
    except MLProxyError as e:
        _raise(e)


@router.get("/models/comparison")
async def models_comparison():
    try:
        return await ml_client.models_comparison()
    except MLProxyError as e:
        _raise(e)


@router.get("/models/{model_name}")
async def model_info(model_name: str):
    try:
        return await ml_client.model_info(model_name)
    except MLProxyError as e:
        _raise(e)


@router.post("/train/{model_name}")
async def train_model(model_name: str, sync: bool = False):
    try:
        return await ml_client.train(model_name, sync=sync)
    except MLProxyError as e:
        _raise(e)


@router.post("/train-all")
async def train_all():
    try:
        return await ml_client.train_all()
    except MLProxyError as e:
        _raise(e)


@router.post("/train-tier/{tier}")
async def train_tier(tier: str):
    try:
        return await ml_client.train_tier(tier)
    except MLProxyError as e:
        _raise(e)


@router.get("/training/readiness")
async def training_readiness():
    try:
        return await ml_client.training_readiness()
    except MLProxyError as e:
        _raise(e)


@router.post("/cache/clear")
async def cache_clear(model_name: Optional[str] = None):
    try:
        return await ml_client.cache_clear(model_name=model_name)
    except MLProxyError as e:
        _raise(e)


# ---------------------------------------------------------------------------
# LEGACY  — kept for the old ML Pipelines page until it is replaced by the
#           new Live Thinking / AI Agents view. Returns synthetic cron rows.
# ---------------------------------------------------------------------------

_RNG = random.Random(11)


@router.get("/pipelines")
def list_pipelines():
    jobs = [
        ("Daily driver scoring",        "driver_score",   "0 2 * * *",  "active"),
        ("Weekly ETA retrain",          "eta_predictor",  "0 1 * * 0",  "active"),
        ("Weekly SLA retrain",          "sla_classifier", "0 2 * * 0",  "active"),
        ("Hourly anomaly scan",         "anomaly_scan",   "0 * * * *",  "running"),
        ("Monthly fuel anomaly retrain","fuel_anomaly",   "0 3 1 * *",  "active"),
        ("15-min alert dispatch",       "alert_dispatch", "*/15 * * * *","active"),
        ("Daily detention model",       "detention",      "0 4 * * *",  "paused"),
        ("Weekly maintenance proxy",    "maintenance",    "0 5 * * 0",  "failed"),
    ]
    out = []
    for i, (name, type_, sched, status) in enumerate(jobs):
        last = datetime.now() - timedelta(hours=_RNG.randint(1, 24))
        out.append({
            "id": f"job-{100 + i}",
            "name": name,
            "type": type_,
            "schedule": sched,
            "status": status,
            "last_run": last.isoformat(),
            "next_run": (last + timedelta(hours=24)).isoformat(),
            "duration_sec": _RNG.randint(8, 600),
            "rows_processed": _RNG.randint(1_000, 500_000),
        })
    return {"jobs": out}
