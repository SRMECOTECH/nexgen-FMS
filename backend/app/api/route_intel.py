"""
Route Intelligence API — Excel upload, trip detection, per-trip deep analysis,
multi-trip comparison, and AI-written insights.

All endpoints under ``/api/v1/route-intel``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from route_intelligence import db, pipeline, streamlit_launcher
from route_intelligence import ai_insights as ai
from route_intelligence import config as ricfg
from route_intelligence import cost_config
from route_intelligence import osrm_gateway
from route_intelligence.services import weather as weather_svc
from route_intelligence.services import weather_impact as weather_impact_svc
from route_intelligence.services import geocoding as geocode_svc
from route_intelligence.services import landmarks as landmarks_svc
from route_intelligence.services import assistant as assistant_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/route-intel", tags=["route-intelligence"])

UPLOAD_DIR = pipeline.UPLOAD_DIR


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    fuel_price_per_liter: Optional[float] = None
    fuel_efficiency_kmpl: Optional[float] = None
    driver_wage_per_hour: Optional[float] = None
    idle_fuel_consumption_lph: Optional[float] = None
    window: Optional[str] = None
    traffic_slow_threshold_kmph: Optional[int] = None
    regenerate_ai: bool = False


class CompareRequest(BaseModel):
    trip_ids: List[int]
    fuel_price_per_liter: Optional[float] = None
    fuel_efficiency_kmpl: Optional[float] = None
    driver_wage_per_hour: Optional[float] = None
    idle_fuel_consumption_lph: Optional[float] = None


# ---------------------------------------------------------------------------
# system
# ---------------------------------------------------------------------------
@router.get("/status")
def status() -> Dict[str, Any]:
    """Health + backend info for the UI to display."""
    db.bootstrap()
    return {
        "ok": True,
        "ai_backend": ai.backend_name(),
        "models_dir": str(ai.MODELS_DIR),
        "upload_dir": str(UPLOAD_DIR),
        "tables_ready": True,
        "streamlit": streamlit_launcher.status(),
        "config_file": str(ricfg.config_file()),
    }


@router.get("/streamlit/status")
def streamlit_status() -> Dict[str, Any]:
    """Is the 'Detailed Analysis of GPS Data' Streamlit page reachable?"""
    return streamlit_launcher.status()


@router.post("/streamlit/start")
def streamlit_start() -> Dict[str, Any]:
    """Idempotent launch — the FastAPI startup hook already calls this, so this
    is mostly useful for manual recovery from the UI."""
    return streamlit_launcher.ensure_started()


# ---------------------------------------------------------------------------
# uploads
# ---------------------------------------------------------------------------
@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Accept an Excel file, store it, run adapter + trip detection, return
    upload id + detected trips. Idempotent: same sha256 returns existing row."""
    if not file.filename:
        raise HTTPException(400, "filename missing")
    safe_name = Path(file.filename).name
    target = UPLOAD_DIR / safe_name
    with open(target, "wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        return pipeline.ingest_excel(target, safe_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class IngestPathRequest(BaseModel):
    path: str
    original_name: Optional[str] = None


@router.post("/ingest-local")
def ingest_local(req: IngestPathRequest) -> Dict[str, Any]:
    """Ingest a file already on disk (e.g. ``data/gpsfinal_20260603.xlsx``).
    Used by the 'Load sample' button to skip the multipart upload."""
    src = Path(req.path)
    if not src.is_absolute():
        # treat as relative to project root
        src = Path(__file__).resolve().parents[3] / req.path
    if not src.exists():
        raise HTTPException(404, f"file not found: {src}")
    name = req.original_name or src.name
    target = UPLOAD_DIR / name
    if not target.exists() or src.resolve() != target.resolve():
        shutil.copy(src, target)
    return pipeline.ingest_excel(target, name)


@router.get("/uploads")
def list_uploads(limit: int = 50) -> Dict[str, Any]:
    return {"uploads": db.list_uploads(limit=limit)}


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: int) -> Dict[str, Any]:
    upload = db.get_upload(upload_id)
    if not upload:
        raise HTTPException(404, "upload not found")
    trip = db.get_trip_for_upload(upload_id)
    upload["trip"] = trip
    upload["segments"] = db.list_segments_for_trip(trip["id"]) if trip else []
    return upload


@router.get("/uploads/{upload_id}/trip")
def get_upload_trip(upload_id: int) -> Dict[str, Any]:
    """One Excel = one trip. Returns the trip + its segments."""
    if not db.get_upload(upload_id):
        raise HTTPException(404, "upload not found")
    trip = db.get_trip_for_upload(upload_id)
    if not trip:
        raise HTTPException(404, "no trip rows for this upload yet")
    trip["segments"] = db.list_segments_for_trip(trip["id"])
    return trip


# ---------------------------------------------------------------------------
# trips
# ---------------------------------------------------------------------------
@router.get("/trips/{trip_id}")
def get_trip(trip_id: int) -> Dict[str, Any]:
    t = db.get_trip(trip_id)
    if not t:
        raise HTTPException(404, "trip not found")
    latest = db.get_latest_done_run_for_trip(trip_id)
    t["latest_run_id"] = latest["id"] if latest else None
    t["segments"] = db.list_segments_for_trip(trip_id)
    return t


@router.get("/trips/{trip_id}/segments")
def list_segments(trip_id: int) -> Dict[str, Any]:
    if not db.get_trip(trip_id):
        raise HTTPException(404, "trip not found")
    return {"segments": db.list_segments_for_trip(trip_id)}


@router.get("/segments/{segment_id}")
def get_segment(segment_id: int) -> Dict[str, Any]:
    s = db.get_segment(segment_id)
    if not s:
        raise HTTPException(404, "segment not found")
    return s


@router.post("/segments/{segment_id}/analyze")
def analyze_segment(segment_id: int, req: Optional[AnalyzeRequest] = None) -> Dict[str, Any]:
    """Run the analyzer suite scoped to one segment of a trip."""
    if not db.get_segment(segment_id):
        raise HTTPException(404, "segment not found")
    params = req.dict(exclude_none=True) if req else {}
    params.pop("regenerate_ai", None)
    try:
        return pipeline.analyze_segment(segment_id, params)
    except FileNotFoundError as exc:
        raise HTTPException(410, f"source file gone — re-upload needed: {exc}")
    except Exception as exc:
        logger.exception("analyze_segment failed for segment=%s", segment_id)
        raise HTTPException(500, f"analyze failed: {exc}")


@router.get("/segments/{segment_id}/track")
def get_segment_track(segment_id: int, max_points: int = 1000) -> Dict[str, Any]:
    if not db.get_segment(segment_id):
        raise HTTPException(404, "segment not found")
    return {"points": pipeline.get_segment_track(segment_id, max_points=max_points)}


@router.get("/trips/{trip_id}/by-day")
def trip_by_day(trip_id: int) -> Dict[str, Any]:
    """Per-day breakdown for a multi-day trip — distance, moving/stopped time,
    pings, max speed, waypoints touched per calendar day."""
    trip = db.get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "trip not found")
    try:
        from route_intelligence.analyzers import WaypointAnalyzer
        df = pipeline._load_trip_df(trip)
        days = WaypointAnalyzer.by_day(df)
        return {
            "trip_id": trip_id,
            "vehicle_id": trip.get("vehicle_id"),
            "from": trip.get("from_waypoint"),
            "to": trip.get("to_waypoint"),
            "n_days": len(days),
            "days": days,
        }
    except FileNotFoundError as exc:
        raise HTTPException(410, f"source file missing — re-upload needed: {exc}")
    except Exception as exc:
        logger.exception("trip_by_day failed for trip=%s", trip_id)
        raise HTTPException(500, f"by-day breakdown failed: {exc}")


# ---------------------------------------------------------------------------
# Enrichment — weather (historical Open-Meteo at the trip's own dates)
# ---------------------------------------------------------------------------
@router.get("/trips/{trip_id}/weather")
def trip_weather(trip_id: int, samples: int = 5) -> Dict[str, Any]:
    """Historical weather sampled along the trip's polyline AT the trip's own
    timestamps. ``samples`` controls how many points along the route to fetch."""
    if not db.get_trip(trip_id):
        raise HTTPException(404, "trip not found")
    try:
        return weather_svc.weather_for_trip(trip_id, n_samples=max(1, min(samples, 12)))
    except Exception as exc:
        logger.exception("weather_for_trip failed for trip=%s", trip_id)
        raise HTTPException(500, f"weather lookup failed: {exc}")


@router.get("/trips/{trip_id}/weather-impact")
def trip_weather_impact(trip_id: int) -> Dict[str, Any]:
    """For every 30-min time-window of the trip, pull the hourly historical
    weather at that window's coordinate AND timestamp, then decide whether
    each slow window can be *blamed* on weather (rain / heavy-rain / storm /
    fog / snow).

    Returns a verdict the UI uses to colour the card (``weather_was_a_factor``
    vs ``weather_was_clear``), summary counts, and a per-window timeline."""
    if not db.get_trip(trip_id):
        raise HTTPException(404, "trip not found")
    try:
        return weather_impact_svc.weather_impact_for_trip(trip_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.exception("weather_impact failed for trip=%s", trip_id)
        raise HTTPException(500, f"weather-impact analysis failed: {exc}")


@router.get("/segments/{segment_id}/weather")
def segment_weather(segment_id: int, samples: int = 3) -> Dict[str, Any]:
    if not db.get_segment(segment_id):
        raise HTTPException(404, "segment not found")
    try:
        return weather_svc.weather_for_segment(segment_id, n_samples=max(1, min(samples, 8)))
    except Exception as exc:
        logger.exception("weather_for_segment failed for segment=%s", segment_id)
        raise HTTPException(500, f"weather lookup failed: {exc}")


# ---------------------------------------------------------------------------
# Enrichment — reverse geocoding (Nominatim, rate-limited, MySQL-cached)
# ---------------------------------------------------------------------------
class GeocodeRequest(BaseModel):
    lat: float
    lng: float


@router.post("/geocode/reverse")
def geocode_reverse(req: GeocodeRequest) -> Dict[str, Any]:
    addr = geocode_svc.address_at(req.lat, req.lng)
    if not addr:
        raise HTTPException(404, "no address found")
    return addr


@router.get("/trips/{trip_id}/addresses")
def trip_addresses(trip_id: int) -> Dict[str, Any]:
    if not db.get_trip(trip_id):
        raise HTTPException(404, "trip not found")
    try:
        return geocode_svc.addresses_for_trip(trip_id)
    except Exception as exc:
        logger.exception("addresses_for_trip failed for trip=%s", trip_id)
        raise HTTPException(500, f"geocoding failed: {exc}")


@router.get("/trips/{trip_id}/segment-addresses")
def trip_segment_addresses(trip_id: int) -> Dict[str, Any]:
    if not db.get_trip(trip_id):
        raise HTTPException(404, "trip not found")
    try:
        return geocode_svc.addresses_for_segments(trip_id)
    except Exception as exc:
        logger.exception("addresses_for_segments failed for trip=%s", trip_id)
        raise HTTPException(500, f"geocoding failed: {exc}")


# ---------------------------------------------------------------------------
# Enrichment — landmarks / POIs (Overpass, MySQL-cached)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# AI Assistant — conversational layer over the analyzed data
# ---------------------------------------------------------------------------
class AssistantAskRequest(BaseModel):
    query: str
    trip_id: Optional[int] = None        # context hints — if the user is
    segment_id: Optional[int] = None     # already on a trip/segment page


@router.post("/assistant/ask")
def assistant_ask(req: AssistantAskRequest) -> Dict[str, Any]:
    if not req.query or not req.query.strip():
        raise HTTPException(400, "query is required")
    ctx = {}
    if req.trip_id is not None:    ctx["trip_id"] = req.trip_id
    if req.segment_id is not None: ctx["segment_id"] = req.segment_id
    try:
        return assistant_svc.ask(req.query.strip(), ctx)
    except Exception as exc:
        logger.exception("assistant.ask failed for query=%r", req.query)
        raise HTTPException(500, f"assistant failed: {exc}")


@router.get("/assistant/suggestions")
def assistant_suggestions() -> Dict[str, Any]:
    """Default suggestion chips for the UI to render."""
    return {"suggestions": assistant_svc.suggestions()}


@router.get("/trips/{trip_id}/landmarks")
def trip_landmarks(trip_id: int,
                   samples: int = 5,
                   radius_m: Optional[int] = None,
                   categories: Optional[str] = None) -> Dict[str, Any]:
    """POIs near the trip's polyline. ``categories`` is a comma-separated list
    of category keys (fuel_stations, restaurants, hotels, parking, rest_areas,
    hospitals, police, workshops). Defaults come from config/route_intel.yaml."""
    if not db.get_trip(trip_id):
        raise HTTPException(404, "trip not found")
    cats = [c.strip() for c in categories.split(",")] if categories else None
    try:
        return landmarks_svc.landmarks_for_trip(
            trip_id, n_samples=max(1, min(samples, 12)),
            radius_m=radius_m, categories=cats,
        )
    except Exception as exc:
        logger.exception("landmarks failed for trip=%s", trip_id)
        raise HTTPException(500, f"landmarks lookup failed: {exc}")


@router.post("/trips/{trip_id}/analyze")
def analyze_trip(trip_id: int, req: Optional[AnalyzeRequest] = None) -> Dict[str, Any]:
    """Run the full analysis pipeline. Idempotent for unchanged params; pass
    ``regenerate_ai=true`` to re-roll the natural-language insights only."""
    params = req.dict(exclude_none=True) if req else {}
    regen = params.pop("regenerate_ai", False)
    if not db.get_trip(trip_id):
        raise HTTPException(404, "trip not found")
    try:
        bundle = pipeline.analyze_trip(trip_id, params, regenerate_ai=regen)
        return bundle
    except FileNotFoundError as exc:
        raise HTTPException(410, f"source file gone — re-upload needed: {exc}")
    except Exception as exc:
        logger.exception("analyze failed for trip=%s", trip_id)
        raise HTTPException(500, f"analyze failed: {exc}")


@router.get("/trips/{trip_id}/analysis")
def get_analysis(trip_id: int) -> Dict[str, Any]:
    """Return the most recent successful analysis bundle for a trip, or 404."""
    if not db.get_trip(trip_id):
        raise HTTPException(404, "trip not found")
    run = db.get_latest_done_run_for_trip(trip_id)
    if not run:
        raise HTTPException(404, "no successful analysis yet — call POST /analyze")
    bundle = db.fetch_full_analysis(run["id"])
    bundle["trip"] = db.get_trip(trip_id)
    bundle["run_id"] = run["id"]
    bundle["params_hash"] = run["params_hash"]
    bundle["model"] = ai.backend_name()
    return bundle


@router.get("/trips/{trip_id}/track")
def get_track(trip_id: int, max_points: int = 2000) -> Dict[str, Any]:
    if not db.get_trip(trip_id):
        raise HTTPException(404, "trip not found")
    return {"points": pipeline.get_trip_track(trip_id, max_points=max_points)}


@router.post("/trips/{trip_id}/regenerate-ai")
def regenerate_ai(trip_id: int) -> Dict[str, Any]:
    run = db.get_latest_done_run_for_trip(trip_id)
    if not run:
        raise HTTPException(400, "run analyze first")
    # Re-roll insights using cached metric tables
    bundle = db.fetch_full_analysis(run["id"])
    trip = db.get_trip(trip_id)
    costs = bundle["cost_metrics"]["breakdown"]
    opps = bundle["cost_metrics"]["opportunities"] or []
    eff = bundle["route_metrics"]["efficiency"]
    zones = bundle["route_metrics"]["speed_zones"]
    traffic = bundle["route_metrics"]["traffic"]
    bt = bundle["route_metrics"]["backtracking"] or []
    for ins in [
        ai.trip_summary(trip, costs, eff, traffic, zones),
        ai.cost_advice(costs, opps),
        ai.route_quality(eff, bt, zones),
        ai.traffic_callout(traffic),
        ai.recommendations_list(opps),
    ]:
        db.insert_ai_insight(run_id=run["id"], insight_type=ins["insight_type"],
                             text_body=ins["text"], model=ins["model"])
    return {"ok": True, "run_id": run["id"], "model": ai.backend_name()}


# ---------------------------------------------------------------------------
# comparisons
# ---------------------------------------------------------------------------
@router.post("/compare")
def compare(req: CompareRequest) -> Dict[str, Any]:
    if len(req.trip_ids) < 2:
        raise HTTPException(400, "need at least 2 trip_ids")
    if len(req.trip_ids) > 6:
        raise HTTPException(400, "compare at most 6 trips at a time")
    params = req.dict(exclude={"trip_ids"}, exclude_none=True)
    try:
        return pipeline.compare_trips(req.trip_ids, params)
    except Exception as exc:
        logger.exception("compare failed for trips=%s", req.trip_ids)
        raise HTTPException(500, f"compare failed: {exc}")


@router.get("/comparisons")
def list_comparisons(limit: int = 30) -> Dict[str, Any]:
    return {"comparisons": db.list_comparisons(limit=limit)}


@router.get("/comparisons/{cmp_id}")
def get_comparison(cmp_id: int) -> Dict[str, Any]:
    cmp = db.get_comparison(cmp_id)
    if not cmp:
        raise HTTPException(404, "comparison not found")
    return cmp


# ---------------------------------------------------------------------------
# fleet-wide insights feed (cheap: queries cached AI rows)
# ---------------------------------------------------------------------------
@router.get("/insights")
def list_insights(limit: int = 50, insight_type: Optional[str] = None,
                  date_from: Optional[str] = None, date_to: Optional[str] = None,
                  dedupe: bool = False) -> Dict[str, Any]:
    """Latest AI paragraphs across the fleet — feeds the 'Insights' page.
    Optional ISO ``date_from`` / ``date_to`` (yyyy-mm-dd) scope the feed by
    insight creation timestamp.

    ``dedupe=true`` — collapses near-duplicate insights per (trip, insight_type)
    using the local sentence-transformer (``models/embeddings/...``). When the
    embedding model isn't installed yet, this flag is a no-op and we return
    all rows + ``dedupe_available: false`` so the UI can surface that."""
    from sqlalchemy import text
    where = []
    params: Dict[str, Any] = {"lim": limit}
    if insight_type:
        where.append("ai.insight_type = :t")
        params["t"] = insight_type
    if date_from:
        where.append("ai.created_at >= :df")
        params["df"] = date_from
    if date_to:
        where.append("ai.created_at < DATE_ADD(:dt, INTERVAL 1 DAY)")
        params["dt"] = date_to
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    # We also pull the segment row when the run was segment-scoped, so the UI
    # can show the *actual* scope (e.g. "PITHORA → BHILAI") instead of always
    # showing the parent trip name. params_json LIKE '%"segment_id": N%' is
    # how analyze_segment marks segment runs.
    with db.get_engine().connect() as c:
        rows = c.execute(text(f"""
            SELECT ai.id, ai.run_id, ai.comparison_id, ai.insight_type,
                   ai.text, ai.model, ai.created_at,
                   t.id AS trip_id,
                   t.from_waypoint, t.to_waypoint, t.vehicle_id,
                   t.n_segments, t.distance_km,
                   r.params_json,
                   s.id           AS segment_id,
                   s.seq          AS segment_seq,
                   s.from_waypoint AS segment_from,
                   s.to_waypoint   AS segment_to,
                   s.distance_km   AS segment_distance_km
            FROM ri_ai_insights ai
            LEFT JOIN ri_analysis_runs r ON r.id = ai.run_id
            LEFT JOIN ri_trips t ON t.id = r.trip_id
            LEFT JOIN ri_segments s
                   ON s.trip_id = t.id
                  AND r.params_json LIKE CONCAT('%"segment_id": ', s.id, '%')
            {where_sql}
            ORDER BY ai.created_at DESC
            LIMIT :lim
        """), params).mappings().all()

    insights = [dict(r) for r in rows]
    # Add a derived ``scope`` field — "trip" or "segment" — so the UI doesn't
    # have to re-parse params_json on every row.
    for r in insights:
        r["scope"] = "segment" if r.get("segment_id") else "trip"
        # Don't ship the raw params back to the browser.
        r.pop("params_json", None)

    # Lazy import so the route works even when the embeddings extra isn't installed.
    from route_intelligence.services import embeddings as emb
    dedupe_available = emb.is_available()

    payload: Dict[str, Any] = {
        "insights":            insights,
        "dedupe_available":    dedupe_available,
        "embedding_model":     emb.model_name(),
    }

    if not (dedupe and dedupe_available and insights):
        payload["deduped_count"] = len(insights)
        return payload

    # Group by (trip_id, insight_type) — only collapse near-duplicates inside
    # the same bucket, never across types or trips.
    buckets: Dict[tuple, List[int]] = {}
    for i, r in enumerate(insights):
        buckets.setdefault((r.get("trip_id"), r.get("insight_type")), []).append(i)

    keep_idx: set = set()
    for _, idxs in buckets.items():
        if len(idxs) == 1:
            keep_idx.add(idxs[0]); continue
        texts = [insights[i].get("text") or "" for i in idxs]
        cluster_ids = emb.cluster_by_similarity(texts, threshold=0.92)
        # Keep the newest row per cluster (insights are already ORDER BY created_at DESC,
        # so the first occurrence of each cluster id is the newest).
        seen: set = set()
        for local_i, cid in enumerate(cluster_ids):
            if cid in seen: continue
            seen.add(cid)
            keep_idx.add(idxs[local_i])

    deduped = [r for i, r in enumerate(insights) if i in keep_idx]
    payload["insights"]      = deduped
    payload["raw_count"]     = len(insights)
    payload["deduped_count"] = len(deduped)
    return payload


# ---------------------------------------------------------------------------
# cost model config (UI-editable) — the numbers behind the recommendation cards
# ---------------------------------------------------------------------------
class CostConfigUpdate(BaseModel):
    # all optional — send only the fields you want to change
    fuel_price_per_liter: Optional[float] = None
    fuel_efficiency_kmpl: Optional[float] = None
    driver_wage_per_hour: Optional[float] = None
    idle_fuel_consumption_lph: Optional[float] = None
    trips_per_month: Optional[int] = None
    idle_hours_trigger: Optional[float] = None
    idle_savings_pct: Optional[float] = None
    speed_target_kmph: Optional[float] = None
    route_opt_time_saved_pct: Optional[float] = None
    peak_hour_start: Optional[int] = None
    peak_hour_end: Optional[int] = None
    peak_share_trigger: Optional[float] = None
    peak_per_trip_savings_inr: Optional[float] = None
    peak_monthly_savings_inr: Optional[float] = None


@router.get("/cost-config")
def get_cost_config() -> Dict[str, Any]:
    """Live cost-model + threshold values used to generate recommendations.
    ``defaults`` lets the UI show a 'reset to default' affordance per field."""
    return {"config": cost_config.load(), "defaults": cost_config.DEFAULTS}


@router.put("/cost-config")
def put_cost_config(update: CostConfigUpdate) -> Dict[str, Any]:
    """Persist edited values. Applies to the NEXT analysis run — call
    POST /trips/{id}/analyze (or regenerate) to recompute existing trips."""
    try:
        cfg = cost_config.save(update.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"config": cfg, "defaults": cost_config.DEFAULTS}


@router.post("/cost-config/reset")
def reset_cost_config() -> Dict[str, Any]:
    return {"config": cost_config.reset(), "defaults": cost_config.DEFAULTS}


# ---------------------------------------------------------------------------
# structured fleet recommendations — headline (category) → entries → detail
# ---------------------------------------------------------------------------
def _rec_id(trip_id: Any, category: str) -> str:
    import hashlib
    return hashlib.md5(f"{trip_id}|{category}".encode()).hexdigest()[:12]


def _fleet_recommendation_entries(limit_trips: int = 500) -> List[Dict[str, Any]]:
    """Flatten every trip's structured opportunities into per-(trip, category)
    entries carrying route context — the building block for both the grouped
    feed and the detail lookup."""
    entries: List[Dict[str, Any]] = []
    for row in db.fleet_cost_opportunities(limit_trips=limit_trips):
        for opp in row["opportunities"]:
            entries.append({
                "id":                  _rec_id(row["trip_id"], opp["category"]),
                "trip_id":             row["trip_id"],
                "run_id":              row["run_id"],
                "vehicle_id":          row["vehicle_id"],
                "from_waypoint":       row["from_waypoint"],
                "to_waypoint":         row["to_waypoint"],
                "distance_km":         row["distance_km"],
                "category":            opp["category"],
                "priority":            opp.get("priority", "MEDIUM"),
                "recommendation":      opp.get("recommendation", ""),
                "monthly_savings_inr": opp.get("monthly_savings_inr", 0),
                "potential_savings_inr": opp.get("potential_savings_inr", 0),
                "current_waste_inr":   opp.get("current_waste_inr", 0),
                "metrics":             opp.get("metrics", {}),
            })
    return entries


_PRIORITY_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


@router.get("/recommendations")
def list_recommendations(limit_trips: int = 500) -> Dict[str, Any]:
    """Fleet-wide savings recommendations, grouped by category (the headline).
    Each headline carries its entries (one per route/trip); the UI drills
    headline → entries → GET /recommendations/{id} for the full report."""
    entries = _fleet_recommendation_entries(limit_trips)

    groups: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        g = groups.setdefault(e["category"], {
            "category": e["category"], "priority": e["priority"],
            "count": 0, "total_monthly_savings_inr": 0.0, "entries": [],
        })
        g["count"] += 1
        g["total_monthly_savings_inr"] += e["monthly_savings_inr"] or 0
        # a category's headline priority = its most severe entry
        if _PRIORITY_RANK.get(e["priority"], 0) > _PRIORITY_RANK.get(g["priority"], 0):
            g["priority"] = e["priority"]
        g["entries"].append(e)

    categories = list(groups.values())
    for g in categories:
        g["total_monthly_savings_inr"] = round(g["total_monthly_savings_inr"], 2)
        g["entries"].sort(key=lambda e: e["monthly_savings_inr"] or 0, reverse=True)
    categories.sort(key=lambda g: (_PRIORITY_RANK.get(g["priority"], 0),
                                   g["total_monthly_savings_inr"]), reverse=True)

    return {
        "categories": categories,
        "totals": {
            "count": len(entries),
            "monthly_savings_inr": round(sum(e["monthly_savings_inr"] or 0 for e in entries), 2),
            "high": sum(1 for e in entries if e["priority"] == "HIGH"),
            "medium": sum(1 for e in entries if e["priority"] == "MEDIUM"),
            "trips": len({e["trip_id"] for e in entries}),
        },
        "config": cost_config.load(),
    }


@router.get("/recommendations/{rec_id}")
def get_recommendation(rec_id: str) -> Dict[str, Any]:
    """Full descriptive report for one recommendation card: the action, the
    trigger evidence, the complete journey cost breakdown, and the route
    efficiency (straight-line vs OSRM road distance when available)."""
    entry = next((e for e in _fleet_recommendation_entries() if e["id"] == rec_id), None)
    if not entry:
        raise HTTPException(404, "recommendation not found (re-analyse may have changed it)")

    # pull the run's full metrics for the descriptive breakdown
    full = db.fetch_full_analysis(entry["run_id"])
    cost_breakdown = (full.get("cost_metrics") or {}).get("breakdown") or {}
    efficiency = (full.get("route_metrics") or {}).get("efficiency") or {}

    return {
        **entry,
        "cost_breakdown": cost_breakdown,
        "efficiency": efficiency,
        "config_used": cost_config.load(),
        "trip": db.get_trip(entry["trip_id"]),
    }
