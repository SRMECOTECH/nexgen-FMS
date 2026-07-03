"""
HTTP client that proxies nextGen-FMS to the smart-truck ML subscription API.

The smart-truck ml_service (default ``http://localhost:8001``) exposes every
trained model behind a subscription key (see
``../smart-truck/docs/API_REFERENCE.md``). This module is the **single point of
contact** with that service for the whole FMS backend — no other module should
build URLs or read ``ML_API_KEY`` directly.

Design rules:
  * One method per endpoint in API_REFERENCE.md (numbered to match).
  * Async (``httpx.AsyncClient``) so it composes inside FastAPI handlers.
  * Errors map to ``MLProxyError`` subclasses, never to opaque 500s.
  * No business logic. Aggregation lives in ``backend/app/api/ai.py``.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MLProxyError(RuntimeError):
    """Base class for any failure talking to the ML subscription API."""

    def __init__(self, status: int, detail: str, path: str) -> None:
        super().__init__(f"[{status}] {path}: {detail}")
        self.status = status
        self.detail = detail
        self.path = path


class MLAuthError(MLProxyError):
    """401 or 403 — bad key or tier doesn't include this endpoint."""


class MLNotReadyError(MLProxyError):
    """404 — model not trained yet, or resource not found."""


class MLUpstreamError(MLProxyError):
    """5xx or transport error — ml_service down / unreachable."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MLConfig:
    base_url: str
    api_key: str
    timeout: float

    @classmethod
    def from_env(cls) -> "MLConfig":
        return cls(
            base_url=os.getenv("ML_SERVICE_URL", "http://localhost:8001").rstrip("/"),
            api_key=os.getenv("ML_API_KEY", ""),
            timeout=float(os.getenv("ML_PROXY_TIMEOUT", "20")),
        )


# ---------------------------------------------------------------------------
# Low-level transport
# ---------------------------------------------------------------------------

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    """Lazily build a process-wide AsyncClient. Reused across requests so we
    benefit from HTTP/1.1 keep-alive when calling ml_service repeatedly."""
    global _client
    if _client is None:
        cfg = MLConfig.from_env()
        _client = httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            headers={"X-API-Key": cfg.api_key} if cfg.api_key else {},
        )
        logger.info("ml_client: bound to %s (key=%s)", cfg.base_url, "set" if cfg.api_key else "MISSING")
    return _client


async def aclose() -> None:
    """Call on app shutdown to drain the connection pool."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


@asynccontextmanager
async def _handled(path: str) -> AsyncIterator[None]:
    """Translate httpx errors into our typed errors so handlers can map them
    to FastAPI HTTPException without leaking ML_API_KEY in tracebacks."""
    try:
        yield
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        if status in (401, 403):
            raise MLAuthError(status, detail, path) from None
        if status == 404:
            raise MLNotReadyError(status, detail, path) from None
        raise MLUpstreamError(status, detail, path) from None
    except (httpx.TransportError, httpx.TimeoutException) as e:
        raise MLUpstreamError(0, f"transport error: {e!r}", path) from None


async def _get(path: str, params: Optional[dict[str, Any]] = None) -> Any:
    async with _handled(path):
        r = await _get_client().get(path, params=params)
        r.raise_for_status()
        return r.json()


async def _post(path: str, json: Optional[dict[str, Any]] = None, params: Optional[dict[str, Any]] = None) -> Any:
    async with _handled(path):
        r = await _get_client().post(path, json=json, params=params)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Public API — one method per endpoint in API_REFERENCE.md
# (numbered to match the table in §Endpoint index)
# ---------------------------------------------------------------------------

# 1-2 — public
async def health() -> dict:
    return await _get("/health")


async def landing() -> dict:
    return await _get("/ml")


# 3 — ETA predictor  (basic)
async def predict_eta(*, origin: str, destination: str, driver_id: Optional[int] = None,
                      vehicle_id: Optional[int] = None, trip_km: Optional[float] = None,
                      trip_start: Optional[str] = None) -> dict:
    body = {"origin": origin, "destination": destination}
    if driver_id is not None: body["driver_id"] = driver_id
    if vehicle_id is not None: body["vehicle_id"] = vehicle_id
    if trip_km is not None: body["trip_km"] = trip_km
    if trip_start is not None: body["trip_start"] = trip_start
    return await _post("/ml/predict/eta", json=body)


# 4 — SLA predictor  (pro)
async def predict_sla(*, origin: str, destination: str, driver_id: Optional[int] = None,
                      vehicle_id: Optional[int] = None, trip_km: Optional[float] = None,
                      trip_start: Optional[str] = None) -> dict:
    body = {"origin": origin, "destination": destination}
    if driver_id is not None: body["driver_id"] = driver_id
    if vehicle_id is not None: body["vehicle_id"] = vehicle_id
    if trip_km is not None: body["trip_km"] = trip_km
    if trip_start is not None: body["trip_start"] = trip_start
    return await _post("/ml/predict/sla", json=body)


# 5 — Anomaly batch scan  (pro)
async def scan_anomalies(*, days: int = 7) -> dict:
    return await _post("/ml/scan/anomalies", params={"days": days})


# 6-7 — Driver scorer  (basic)
async def driver_scores(*, limit: int = 100) -> dict:
    return await _get("/ml/drivers/scores", params={"limit": limit})


async def driver_score(driver_id: int) -> dict:
    return await _get(f"/ml/drivers/{driver_id}/score")


# 8-9 — Fatigue predictor  (pro)
async def fleet_fatigue() -> dict:
    return await _get("/ml/drivers/fatigue")


async def driver_fatigue(driver_id: int) -> dict:
    return await _get(f"/ml/drivers/{driver_id}/fatigue")


# 10-11 — Demand / trip forecast  (basic)
async def forecast_demand(*, route: Optional[str] = None) -> dict:
    return await _get("/ml/forecast/demand", params={"route": route} if route else None)


async def forecast_trips(*, route: Optional[str] = None) -> dict:
    return await _get("/ml/forecast/trips", params={"route": route} if route else None)


# 12-13 — Route optimizer  (pro)
async def optimize_route(*, origin: str, destination: str, trip_km: Optional[float] = None,
                         hour: Optional[int] = None, day_of_week: Optional[int] = None) -> dict:
    body: dict[str, Any] = {"origin": origin, "destination": destination}
    if trip_km is not None: body["trip_km"] = trip_km
    if hour is not None: body["hour"] = hour
    if day_of_week is not None: body["day_of_week"] = day_of_week
    return await _post("/ml/optimize/route", json=body)


async def optimize_hubs() -> dict:
    return await _get("/ml/optimize/hubs")


# 14 — Driver recommender  (pro)
async def recommend_drivers(*, origin: str, destination: str, top_n: int = 10) -> dict:
    return await _post(
        "/ml/recommend/drivers",
        json={"origin": origin, "destination": destination, "top_n": top_n},
    )


# 15-17 — Client demand forecaster  (enterprise)
async def clients() -> dict:
    return await _get("/ml/clients")


async def clients_forecast(*, client: Optional[str] = None) -> dict:
    return await _get("/ml/clients/forecast", params={"client": client} if client else None)


async def client_profile(client_name: str) -> dict:
    return await _get(f"/ml/clients/{client_name}/profile")


# 18-20 — Registry  (basic)
async def models() -> dict:
    return await _get("/ml/models")


async def models_comparison() -> dict:
    return await _get("/ml/models/comparison")


async def model_info(model_name: str) -> dict:
    return await _get(f"/ml/models/{model_name}")


# 21-26 — Training / admin  (enterprise)
async def train(model_name: str, *, sync: bool = False) -> dict:
    return await _post(f"/ml/train/{model_name}/sync" if sync else f"/ml/train/{model_name}")


async def train_all() -> dict:
    return await _post("/ml/train-all")


async def train_tier(tier: str) -> dict:
    return await _post(f"/ml/train-tier/{tier}")


async def training_readiness() -> dict:
    return await _get("/ml/training/readiness")


async def cache_clear(*, model_name: Optional[str] = None) -> dict:
    return await _post("/ml/cache/clear", params={"model_name": model_name} if model_name else None)
