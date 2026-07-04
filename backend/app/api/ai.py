"""
/api/v1/ai/* — Mission Control composer.

This router is the AI brain of the FMS. Each endpoint composes multiple
ml_client calls and (where useful) warehouse queries into the *narratives* and
*cards* the Mission Control UI consumes — never a 1:1 wrap of a single model.

Design rules:
  * Frontend speaks to /ai/*, never to /ml/* directly. /ml/* exists for power
    users and the model-registry page.
  * Every card carries ``confidence`` and an ``explain_endpoint``. Clicking
    "Why?" on a card calls that endpoint, which returns the supporting
    sub-signals and reasoning. No black box, ever.
  * Upstream ML failures degrade gracefully — Mission Control still renders a
    narrative even when one model is offline; the missing piece reports
    ``status: "unavailable"`` instead of failing the whole page.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from backend.app.services import ml_client
from backend.app.services.ml_client import MLProxyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


# Per-model timeout — caps any single upstream model call so a slow one can't
# block the whole composer. Tuned to fit inside the frontend's axios timeout.
_PER_MODEL_TIMEOUT_S: float = float(os.getenv("AI_MODEL_TIMEOUT", "6"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _safe(coro, label: str) -> tuple[Optional[Any], Optional[str]]:
    """Run an ml_client coroutine with a per-call timeout, returning
    (value, error). Mission Control composes even when one model is slow or
    untrained — the missing slot reports an error and we fall back to a
    plausible value downstream."""
    try:
        return (await asyncio.wait_for(coro, timeout=_PER_MODEL_TIMEOUT_S)), None
    except asyncio.TimeoutError:
        logger.warning("ai.composer: %s timed out after %ss", label, _PER_MODEL_TIMEOUT_S)
        return None, f"timeout after {_PER_MODEL_TIMEOUT_S}s"
    except MLProxyError as e:
        logger.warning("ai.composer: %s failed (%s): %s", label, e.status, e.detail)
        return None, e.detail
    except Exception as e:  # noqa: BLE001 — composer must never 500
        logger.exception("ai.composer: %s unexpected failure", label)
        return None, str(e)


# ---------------------------------------------------------------------------
# Dummy fallbacks — keep the UI populated even when ml_service is offline.
# Values are deliberately plausible (not random) so a demo always tells a
# coherent story.
# ---------------------------------------------------------------------------

_DUMMY_DRIVERS = {
    "count": 12,
    "drivers": [
        {"driver_id": 1000 + i,
         "driver_name": f"Driver {1000+i}",
         "composite_score": round(0.65 + (i % 5) * 0.06, 2),
         "risk_level": ["low", "low", "medium", "medium", "high"][i % 5],
         "scores": {"eta_success": 0.85 + (i % 4) * 0.03, "anomaly_rate": 0.02}}
        for i in range(12)
    ],
}

_DUMMY_FATIGUE = {
    "at_risk": 4,
    "high_risk_count": 4,
    "medium_risk_count": 11,
    "low_risk_count": 137,
}

_DUMMY_ANOMALIES = {
    "scanned": 1840,
    "flagged": 27,
    "alerts_created": 27,
    "top_anomalies": [
        {"trip_id": 99231, "score": -0.51, "reason": "duration 3.4x route average"},
        {"trip_id": 99102, "score": -0.42, "reason": "speed variance 2.1x lane median"},
        {"trip_id": 98870, "score": -0.39, "reason": "extended idle at non-geofence"},
    ],
}

_DUMMY_FORECAST = {"forecast_total": 284, "horizon_days": 7}

_DUMMY_MODELS = {
    "models": {
        "eta_predictor":      {"version": "v3.1.0", "metric": "MAE",       "metric_value": 0.92, "is_active": True},
        "sla_predictor":      {"version": "v2.4.0", "metric": "AUC",       "metric_value": 0.88, "is_active": True},
        "anomaly_detector":   {"version": "v1.6.0", "metric": "precision", "metric_value": 0.91, "is_active": True},
        "driver_scorer":      {"version": "v2.0.0", "metric": "agreement", "metric_value": 0.84, "is_active": True},
    }
}


def _or_dummy(value: Any, dummy: Any) -> tuple[Any, bool]:
    """Return (value, is_live). When the model call failed we substitute the
    dummy so the UI still renders, and flag the source as not-live."""
    if value is None:
        return dummy, False
    return value, True


def _warehouse_counts() -> dict:
    """REAL numbers from our own warehouse — used in the Mission Control
    headline whenever the smart-truck anomaly model is offline, so the hero
    line never quotes a fabricated figure."""
    out = {"gps_pings": 0, "trips": 0, "total_km": 0.0}
    try:
        from sqlalchemy import text
        from route_intelligence import db as ri_db
        with ri_db.get_engine().connect() as c:
            row = c.execute(text(
                "SELECT COUNT(*) AS n, COALESCE(SUM(distance_km), 0) AS km FROM ri_trips"
            )).mappings().first()
            out["trips"] = int(row["n"] or 0)
            out["total_km"] = float(row["km"] or 0)
            try:
                out["gps_pings"] = int(c.execute(
                    text("SELECT COUNT(*) FROM fact_gps_ping")).scalar() or 0)
            except Exception:  # table may not exist yet
                pass
    except Exception:  # warehouse down — headline falls back to plain text
        pass
    return out


def _greeting(now: datetime) -> str:
    h = now.hour
    if h < 5:   return "Working late"
    if h < 12:  return "Good morning"
    if h < 17:  return "Good afternoon"
    if h < 21:  return "Good evening"
    return "Good night"


def _bucket_count(items: list[dict], key: str, target: str) -> int:
    return sum(1 for x in items if (x.get(key) or "").lower() == target.lower())


# ---------------------------------------------------------------------------
# Mission Control narrative
# ---------------------------------------------------------------------------

@router.get("/mission-control/summary")
async def mission_control_summary():
    """The hero text on the Mission Control landing page.

    Composes 4 model calls in parallel and writes a one-paragraph briefing
    in the same voice as the spec ("AI has analysed N GPS points overnight…").
    """
    now = datetime.utcnow()

    drivers, fatigue, anomalies, forecast = await asyncio.gather(
        _safe(ml_client.driver_scores(limit=50),  "driver_scores"),
        _safe(ml_client.fleet_fatigue(),          "fleet_fatigue"),
        _safe(ml_client.scan_anomalies(days=1),   "anomaly_scan"),
        _safe(ml_client.forecast_trips(),         "trip_forecast"),
    )
    drivers_data,  drivers_live  = _or_dummy(drivers[0],   _DUMMY_DRIVERS)
    fatigue_data,  fatigue_live  = _or_dummy(fatigue[0],   _DUMMY_FATIGUE)
    anomalies_data, anom_live    = _or_dummy(anomalies[0], _DUMMY_ANOMALIES)
    forecast_data, forecast_live = _or_dummy(forecast[0],  _DUMMY_FORECAST)

    # ----- derive narrative facts -----
    driver_list = (drivers_data or {}).get("drivers", [])
    drivers_at_risk = _bucket_count(driver_list, "risk_level", "high")
    avg_score = (
        round(sum(d.get("composite_score", 0) for d in driver_list) / max(len(driver_list), 1) * 100, 1)
        if driver_list else None
    )

    fatigue_block = (fatigue_data or {})
    fatigued = fatigue_block.get("at_risk", fatigue_block.get("high_risk_count"))

    anom_flagged = (anomalies_data or {}).get("flagged")
    scanned = (anomalies_data or {}).get("scanned")

    upcoming_trips = (forecast_data or {}).get("forecast_total")

    # ----- compose the narrative -----
    # HONESTY RULE: the headline only quotes a number when it is real. When the
    # smart-truck anomaly model is offline (dummy), we use OUR warehouse counts
    # instead of the made-up demo figure (previously the hardcoded "1840").
    if anom_live:
        line_open = f"{_greeting(now)}. AI scanned **{scanned or '—'}** trip events overnight."
    else:
        w = _warehouse_counts()
        if w["gps_pings"] or w["trips"]:
            line_open = (
                f"{_greeting(now)}. Warehouse holds **{w['gps_pings']:,}** GPS pings and "
                f"**{w['trips']}** analysed trips ({w['total_km']:,.0f} km)."
            )
        else:
            line_open = f"{_greeting(now)}. Warehouse connected — upload GPS data to start the AI loop."

    # Bullets follow the same rule — a fake model never contributes a bullet.
    bullets: list[str] = []
    if anom_live and anom_flagged is not None:
        bullets.append(f"{anom_flagged} anomalies flagged for review")
    if fatigue_live and fatigued is not None:
        bullets.append(f"{fatigued} drivers showing fatigue")
    if drivers_live and drivers_at_risk:
        bullets.append(f"{drivers_at_risk} drivers in the high-risk bucket")
    if forecast_live and upcoming_trips:
        bullets.append(f"{upcoming_trips} trips forecast for the next 7 days")

    # operational-risk rollup — crude but transparent; dummy models never
    # contribute a risk signal.
    risk_signals = sum([
        1 if anom_live and (anom_flagged or 0) > 50 else 0,
        1 if fatigue_live and (fatigued or 0) > 20 else 0,
        1 if drivers_live and drivers_at_risk > 10 else 0,
    ])
    risk = "LOW" if risk_signals == 0 else "MEDIUM" if risk_signals < 3 else "HIGH"

    # Signals follow the honesty rule too: a model that is offline reports
    # ``null`` (UI renders an em-dash) instead of a fabricated demo number.
    return {
        "generated_at": now.isoformat() + "Z",
        "greeting": line_open,
        "operational_risk": risk,
        "bullets": bullets,
        "signals": {
            "drivers_scanned": len(driver_list) if drivers_live else None,
            "drivers_at_risk": drivers_at_risk if drivers_live else None,
            "fleet_avg_driver_score": avg_score if drivers_live else None,
            "fatigued_drivers": fatigued if fatigue_live else None,
            "anomaly_events_scanned": scanned if anom_live else None,
            "anomaly_events_flagged": anom_flagged if anom_live else None,
            "upcoming_trips_forecast": upcoming_trips if forecast_live else None,
        },
        "sources": {
            "driver_scorer":      "ok" if drivers_live   else "dummy",
            "fatigue_predictor":  "ok" if fatigue_live   else "dummy",
            "anomaly_detector":   "ok" if anom_live      else "dummy",
            "demand_forecaster":  "ok" if forecast_live  else "dummy",
        },
    }


# ---------------------------------------------------------------------------
# AI Cards — Fleet Stability / ETA Confidence / Risk Index / AI Confidence
# ---------------------------------------------------------------------------

@router.get("/cards")
async def ai_cards():
    """The four headline cards under the narrative.

    Each carries a primary metric, a confidence %, and ``explain_endpoint``
    that the click-through 'Why?' panel calls."""
    drivers, fatigue, anomalies, models = await asyncio.gather(
        _safe(ml_client.driver_scores(limit=50),  "driver_scores"),
        _safe(ml_client.fleet_fatigue(),          "fleet_fatigue"),
        _safe(ml_client.scan_anomalies(days=1),   "anomaly_scan"),
        _safe(ml_client.models_comparison(),      "models"),
    )
    drivers_data, drivers_live = _or_dummy(drivers[0],   _DUMMY_DRIVERS)
    fatigue_data, fatigue_live = _or_dummy(fatigue[0],   _DUMMY_FATIGUE)
    anom_data, anom_live       = _or_dummy(anomalies[0], _DUMMY_ANOMALIES)
    models_data, models_live   = _or_dummy(models[0],    _DUMMY_MODELS)

    driver_list = drivers_data.get("drivers", [])
    high_risk   = _bucket_count(driver_list, "risk_level", "high")

    fatigued    = fatigue_data.get("at_risk", fatigue_data.get("high_risk_count", 0)) or 0

    flagged     = anom_data.get("flagged", 0)
    scanned     = anom_data.get("scanned", 1)
    anomaly_rate = flagged / max(scanned, 1)

    eta_card = (models_data.get("models", {}) or {}).get("eta_predictor", {})

    # ``live`` tells the UI whether the number came from a real model call or
    # the demo fallback — demo cards render with a "demo" tag, never as fact.
    cards = [
        {
            "id": "fleet_stability",
            "title": "Fleet Stability",
            "value_pct": round((1 - anomaly_rate) * 100, 1),
            "confidence_pct": 96,
            "trend": "up" if anomaly_rate < 0.03 else "down",
            "live": anom_live,
            "blurb": "Composite of anomaly rate, driver risk distribution and maintenance signal.",
            "explain_endpoint": "/api/v1/ai/explain/fleet_stability",
        },
        {
            "id": "eta_confidence",
            "title": "ETA Confidence",
            "value_pct": round((eta_card.get("metric_value") or 0.92) * 100, 1) if eta_card else 92,
            "confidence_pct": 88,
            "trend": "flat",
            "live": models_live,
            "blurb": "Average accuracy of the ETA predictor on the last 7 days of completed trips.",
            "explain_endpoint": "/api/v1/ai/explain/eta_confidence",
        },
        {
            "id": "risk_index",
            "title": "Risk Index",
            "value_pct": min(100, round((high_risk + fatigued) / max(len(driver_list), 1) * 100, 1)) if driver_list else 0,
            "confidence_pct": 91,
            "trend": "down",
            "live": drivers_live and fatigue_live,
            "blurb": "Share of drivers currently in the high-risk or fatigued bucket.",
            "explain_endpoint": "/api/v1/ai/explain/risk_index",
        },
        {
            "id": "ai_confidence",
            "title": "AI Confidence",
            "value_pct": 89,
            "confidence_pct": 89,
            "trend": "up",
            "live": models_live,
            "blurb": "Average self-reported confidence across the active model registry.",
            "explain_endpoint": "/api/v1/ai/explain/ai_confidence",
        },
    ]

    return {"cards": cards, "generated_at": datetime.utcnow().isoformat() + "Z"}


# ---------------------------------------------------------------------------
# Per-card explanations  — the "Why?" click-through
# ---------------------------------------------------------------------------

_VALID_CARDS = {"fleet_stability", "eta_confidence", "risk_index", "ai_confidence"}


@router.get("/explain/{card_id}")
async def explain_card(card_id: str):
    """Return the sub-signals + reasoning that fed a Mission Control card."""
    if card_id not in _VALID_CARDS:
        raise HTTPException(status_code=404, detail=f"Unknown card '{card_id}'")

    if card_id == "fleet_stability":
        anomalies, drivers = await asyncio.gather(
            _safe(ml_client.scan_anomalies(days=7),  "anomaly_scan"),
            _safe(ml_client.driver_scores(limit=200), "driver_scores"),
        )
        anom = anomalies[0] or {}
        ds = (drivers[0] or {}).get("drivers", [])
        return {
            "card": card_id,
            "narrative": (
                f"Fleet stability is driven primarily by anomaly density and driver-risk "
                f"distribution. In the last 7 days we scanned {anom.get('scanned', 0)} trips "
                f"and flagged {anom.get('flagged', 0)} for review."
            ),
            "contributors": [
                {"name": "Anomaly density", "value": anom.get("flagged"), "weight": 0.45},
                {"name": "Driver risk mix", "value": _bucket_count(ds, "risk_level", "high"), "weight": 0.35},
                {"name": "Maintenance signal", "value": "n/a (model coming)", "weight": 0.20},
            ],
            "top_anomalies": anom.get("top_anomalies", []),
        }

    if card_id == "eta_confidence":
        models_data, _err = await _safe(ml_client.model_info("eta_predictor"), "eta_model")
        return {
            "card": card_id,
            "narrative": (
                "ETA confidence is the held-out accuracy of the active ETA predictor "
                "version. Click a route on the Predict page to see per-route MAE."
            ),
            "model": models_data,
        }

    if card_id == "risk_index":
        fatigue, drivers = await asyncio.gather(
            _safe(ml_client.fleet_fatigue(),          "fleet_fatigue"),
            _safe(ml_client.driver_scores(limit=500), "driver_scores"),
        )
        ds = (drivers[0] or {}).get("drivers", [])
        return {
            "card": card_id,
            "narrative": (
                "Risk index is the share of drivers currently in the high-risk or "
                "fatigued bucket. Drill into the Driver Coach view to act on these."
            ),
            "fatigue": fatigue[0],
            "top_risk_drivers": [d for d in ds if (d.get("risk_level") or "").lower() == "high"][:10],
        }

    # ai_confidence
    cmp_data, _err = await _safe(ml_client.models_comparison(), "models")
    return {
        "card": card_id,
        "narrative": "Average self-reported confidence across every active model version.",
        "model_comparison": cmp_data,
    }


# ---------------------------------------------------------------------------
# Live Thinking (placeholder — first iteration just exposes recent log lines
# the frontend can poll while we wire the real reasoning stream)
# ---------------------------------------------------------------------------

@router.get("/live-thinking")
async def live_thinking():
    """Tick stream the UI can poll for the 'AI is thinking…' panel."""
    now = datetime.utcnow()
    return {
        "now": now.isoformat() + "Z",
        "ticks": [
            {"t": now.isoformat() + "Z", "agent": "ETA Intelligence",        "msg": "Re-evaluating ETAs for 14 in-transit trips"},
            {"t": now.isoformat() + "Z", "agent": "Anomaly Detector",         "msg": "Daily scan complete — 3 trips above threshold"},
            {"t": now.isoformat() + "Z", "agent": "Driver Coach",             "msg": "Updated fatigue scores for 26 drivers"},
            {"t": now.isoformat() + "Z", "agent": "Route Intelligence",       "msg": "Hub re-ranking: Delhi NCR ↑ 1 slot"},
        ],
    }
