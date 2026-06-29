"""
Orchestrator — wires adapter → trip detection → analyzers → DB → AI insights.

Two public entry points:

    ingest_excel(path) -> Dict
        Hashes the file, runs the schema adapter, auto-detects trips, and
        persists everything to ``ri_uploads`` + ``ri_trips``. Returns the
        upload id and the trip list. Safe to call twice on the same file
        (sha256 deduplication).

    analyze_trip(trip_id, params) -> Dict
        Loads the raw GPS slice for that trip, runs every analyzer, writes
        the per-purpose result tables, calls the AI layer for each insight
        type, and returns the full bundle the UI consumes.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from route_intelligence import db
from route_intelligence import ai_insights as ai
from route_intelligence.analyzers import (
    BusinessAnalyzer,
    CostParams,
    RouteAnalyzer,
    WaypointAnalyzer,
)
from route_intelligence.data_adapter import (
    aggregate_to_time_windows,
    detect_trips,
    load_gps_excel,
)

logger = logging.getLogger(__name__)


# Where uploaded files land. We keep the originals so re-analysis is possible.
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "ri_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# ingest_excel
# ============================================================================
def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest_excel(stored_path: Path, original_name: str) -> Dict[str, Any]:
    """Read + normalize + auto-detect, persist headers + trips, return summary."""
    sha = _sha256_of(stored_path)
    size = stored_path.stat().st_size

    nf = load_gps_excel(str(stored_path))
    trips = detect_trips(nf.df)

    upload_id = db.insert_upload(
        filename=stored_path.name,
        original_name=original_name,
        sha256=sha,
        vehicle_id=nf.vehicle_id,
        n_rows=nf.n_rows,
        n_dropped=nf.n_dropped,
        first_ts=nf.first_ts.to_pydatetime(),
        last_ts=nf.last_ts.to_pydatetime(),
        total_distance_km=nf.total_distance_km,
        sheets=nf.sheets,
        size_bytes=size,
    )

    # Only insert trips on the first ingest of this sha; on duplicate uploads
    # the rows already exist and we just return them.
    existing = db.list_trips_for_upload(upload_id)
    if not existing:
        db.insert_trips(upload_id, nf.vehicle_id, trips)
        existing = db.list_trips_for_upload(upload_id)

    return {
        "upload_id": upload_id,
        "vehicle_id": nf.vehicle_id,
        "n_rows": nf.n_rows,
        "n_dropped": nf.n_dropped,
        "first_ts": str(nf.first_ts),
        "last_ts": str(nf.last_ts),
        "total_distance_km": round(nf.total_distance_km, 2),
        "sheets": nf.sheets,
        "trips": existing,
    }


# ============================================================================
# analyze_trip
# ============================================================================
DEFAULT_PARAMS = {
    "fuel_price_per_liter": 100.0,
    "fuel_efficiency_kmpl": 4.0,
    "driver_wage_per_hour": 150.0,
    "idle_fuel_consumption_lph": 1.5,
    "window": "30min",
    "traffic_slow_threshold_kmph": 15,
}


def _params_with_defaults(params: Dict[str, Any] | None) -> Dict[str, Any]:
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update({k: v for k, v in params.items() if v is not None})
    return p


def _load_trip_slice(trip: Dict[str, Any]) -> pd.DataFrame:
    """Re-read the source Excel and slice to this trip's timestamps. We don't
    cache the raw frame to keep memory small; loads are <1s for typical files."""
    upload = db.get_upload(trip["upload_id"])
    if not upload:
        raise ValueError(f"upload {trip['upload_id']} not found")
    path = UPLOAD_DIR / upload["filename"]
    if not path.exists():
        raise FileNotFoundError(f"source file missing: {path}")
    nf = load_gps_excel(str(path))
    df = nf.df
    df = df[(df["Date Time"] >= pd.Timestamp(trip["start_ts"]))
            & (df["Date Time"] <= pd.Timestamp(trip["end_ts"]))].reset_index(drop=True)
    return df


def analyze_trip(trip_id: int, params: Dict[str, Any] | None = None,
                regenerate_ai: bool = False) -> Dict[str, Any]:
    """Run the full pipeline for a trip. Idempotent on (trip_id, params_hash) —
    returns cached results if nothing changed (except AI when ``regenerate_ai``)."""
    trip = db.get_trip(trip_id)
    if not trip:
        raise ValueError(f"trip {trip_id} not found")
    p = _params_with_defaults(params)
    run_id = db.get_or_create_run(trip_id, p)
    run = db.get_run(run_id)
    if run and run["status"] == "done" and not regenerate_ai:
        # Cached: just return what's in DB.
        return _read_bundle(trip_id, run_id)

    try:
        seg = _load_trip_slice(trip)
        if seg.empty:
            raise ValueError("no GPS rows in trip range")

        # Time-window aggregation
        df_agg = aggregate_to_time_windows(seg, p["window"])

        # Business / route / waypoint
        ba = BusinessAnalyzer(CostParams(
            fuel_price_per_liter=p["fuel_price_per_liter"],
            fuel_efficiency_kmpl=p["fuel_efficiency_kmpl"],
            driver_wage_per_hour=p["driver_wage_per_hour"],
            idle_fuel_consumption_lph=p["idle_fuel_consumption_lph"],
        ))
        costs = ba.calculate_journey_costs(df_agg)
        opps = ba.cost_savings_opportunities(df_agg)
        eff = RouteAnalyzer.route_efficiency(seg)
        zones = RouteAnalyzer.speed_zones(seg)
        traffic = RouteAnalyzer.traffic_loss(seg, p["traffic_slow_threshold_kmph"])
        bt = RouteAnalyzer.backtracking_events(seg, sample_step=max(1, len(seg) // 500))
        clusters = RouteAnalyzer.stop_clusters(seg)
        waypoints = WaypointAnalyzer.consolidate(seg)

        # Persist everything
        db.upsert_route_metrics(run_id, efficiency=eff, speed_zones=zones,
                                traffic=traffic, backtracking=bt, stop_clusters=clusters)
        db.upsert_cost_metrics(run_id, costs, opps)
        db.replace_waypoints(run_id, waypoints)
        db.replace_time_windows(run_id, df_agg)

        # AI insights (deterministic context → LLM/rule paragraphs)
        _generate_all_ai(run_id, trip, costs, opps, eff, zones, traffic, bt)

        db.mark_run_done(run_id)
        db.mark_trip_analyzed(trip_id)
        return _read_bundle(trip_id, run_id)
    except Exception as exc:
        logger.exception("analyze_trip failed for trip=%s run=%s", trip_id, run_id)
        db.mark_run_failed(run_id, str(exc))
        raise


def _generate_all_ai(run_id, trip, costs, opps, eff, zones, traffic, bt):
    insights = [
        ai.trip_summary(trip, costs, eff, traffic, zones),
        ai.cost_advice(costs, opps),
        ai.route_quality(eff, bt, zones),
        ai.traffic_callout(traffic),
        ai.recommendations_list(opps),
    ]
    for ins in insights:
        db.insert_ai_insight(
            run_id=run_id,
            insight_type=ins["insight_type"],
            text_body=ins["text"],
            model=ins["model"],
        )


def _read_bundle(trip_id: int, run_id: int) -> Dict[str, Any]:
    trip = db.get_trip(trip_id)
    bundle = db.fetch_full_analysis(run_id)
    bundle["trip"] = trip
    bundle["run_id"] = run_id
    bundle["params_hash"] = db.get_run(run_id)["params_hash"]
    bundle["model"] = ai.backend_name()
    return bundle


# ============================================================================
# Comparison
# ============================================================================
def compare_trips(trip_ids: List[int], params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Analyze (or read cached results) for each trip, then build a ranked table."""
    if not trip_ids:
        raise ValueError("need at least 2 trip_ids")
    p = _params_with_defaults(params)

    rows = []
    per_trip = []
    for tid in trip_ids:
        # ensure each trip has been analyzed
        bundle = analyze_trip(tid, p)
        per_trip.append(bundle)
        trip = bundle["trip"]
        label = f"#{trip['seq']} {trip.get('from_waypoint','?')} → {trip.get('to_waypoint','?')}"
        c = bundle["cost_metrics"]["breakdown"] if bundle.get("cost_metrics") else {}
        rows.append({
            "trip_id": tid,
            "Route": label,
            "Distance (km)": c.get("total_distance_km", 0),
            "Duration (hrs)": c.get("total_hours", 0),
            "Moving Time (hrs)": c.get("moving_hours", 0),
            "Idle Time (hrs)": c.get("stopped_hours", 0),
            "Avg Speed (km/h)": round(c.get("total_distance_km", 0) / c.get("total_hours", 1), 1)
                if c.get("total_hours") else 0,
            "Moving Speed (km/h)": round(c.get("total_distance_km", 0) / c.get("moving_hours", 1), 1)
                if c.get("moving_hours") else 0,
            "Total Cost (₹)": c.get("total_cost_inr", 0),
            "Fuel Cost (₹)": c.get("fuel_cost_inr", 0),
            "Idle Waste (₹)": c.get("idle_fuel_waste_inr", 0),
            "Cost/km (₹)": c.get("cost_per_km", 0),
            "Efficiency (%)": c.get("efficiency_pct", 0),
        })

    # Ranks + weighted score
    import pandas as pd
    df = pd.DataFrame(rows)
    df["Cost Rank"] = df["Total Cost (₹)"].rank()
    df["Time Rank"] = df["Duration (hrs)"].rank()
    df["Efficiency Rank"] = df["Efficiency (%)"].rank(ascending=False)
    df["Overall Score"] = (
        (1 / df["Cost Rank"]) * 0.4
        + (1 / df["Time Rank"]) * 0.3
        + (1 / df["Efficiency Rank"]) * 0.3
    ).round(3)
    table = df.to_dict(orient="records")
    best_row = max(table, key=lambda r: r["Overall Score"])
    best_trip_id = int(best_row["trip_id"])

    cmp_id = db.insert_comparison(trip_ids, table, best_trip_id)

    # AI verdict
    verdict = ai.comparison_verdict(table)
    db.insert_ai_insight(comparison_id=cmp_id,
                         insight_type=verdict["insight_type"],
                         text_body=verdict["text"],
                         model=verdict["model"])

    return db.get_comparison(cmp_id)


# ============================================================================
# Track decimation for the map
# ============================================================================
def get_trip_track(trip_id: int, max_points: int = 2000) -> List[Dict]:
    trip = db.get_trip(trip_id)
    if not trip:
        raise ValueError(f"trip {trip_id} not found")
    seg = _load_trip_slice(trip)
    if seg.empty:
        return []
    step = max(1, len(seg) // max_points)
    sub = seg.iloc[::step]
    return [
        {
            "ts": str(r["Date Time"]),
            "lat": float(r["latitude"]),
            "lng": float(r["longitude"]),
            "speed": float(r["Speed_kmh"]),
        }
        for _, r in sub.iterrows()
    ]
