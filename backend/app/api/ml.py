"""ML pipelines, model registry, predictions."""

from datetime import datetime, timedelta
import random

from fastapi import APIRouter

router = APIRouter(prefix="/ml", tags=["ml"])

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


@router.get("/models")
def list_models():
    models = [
        ("eta_predictor",   "XGBoost",         "regression",     "v3", 0.847),
        ("sla_classifier",  "XGBoost",         "classification", "v2", 0.913),
        ("driver_scorer",   "Composite + IF",  "scoring",        "v5", 0.0),
        ("anomaly_detector","IsolationForest", "anomaly",        "v2", 0.0),
        ("fuel_anomaly",    "IsolationForest", "anomaly",        "v1", 0.0),
        ("detention",       "XGBoost",         "regression",     "v1", 0.732),
        ("route_deviation", "Rule + LSTM",     "deviation",      "v0", 0.0),
    ]
    out = []
    for name, algo, kind, version, metric in models:
        out.append({
            "name": name,
            "algorithm": algo,
            "kind": kind,
            "version": version,
            "trained_at": (datetime.now() - timedelta(days=_RNG.randint(1, 30))).isoformat(),
            "primary_metric": metric,
            "metric_label": "R²" if kind == "regression" else ("ROC-AUC" if kind == "classification" else "n/a"),
            "is_active": True,
            "size_kb": _RNG.randint(120, 4800),
        })
    return {"models": out}
