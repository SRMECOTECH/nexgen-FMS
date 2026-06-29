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
    upload["trips"] = db.list_trips_for_upload(upload_id)
    return upload


@router.get("/uploads/{upload_id}/trips")
def list_trips(upload_id: int) -> Dict[str, Any]:
    if not db.get_upload(upload_id):
        raise HTTPException(404, "upload not found")
    return {"trips": db.list_trips_for_upload(upload_id)}


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
    return t


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
def list_insights(limit: int = 50, insight_type: Optional[str] = None) -> Dict[str, Any]:
    """Latest AI paragraphs across the fleet — feeds the 'Insights' page."""
    from sqlalchemy import text
    where = []
    params: Dict[str, Any] = {"lim": limit}
    if insight_type:
        where.append("ai.insight_type = :t")
        params["t"] = insight_type
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with db.get_engine().connect() as c:
        rows = c.execute(text(f"""
            SELECT ai.id, ai.run_id, ai.comparison_id, ai.insight_type,
                   ai.text, ai.model, ai.created_at,
                   t.id AS trip_id, t.seq AS trip_seq,
                   t.from_waypoint, t.to_waypoint, t.vehicle_id
            FROM ri_ai_insights ai
            LEFT JOIN ri_analysis_runs r ON r.id = ai.run_id
            LEFT JOIN ri_trips t ON t.id = r.trip_id
            {where_sql}
            ORDER BY ai.created_at DESC
            LIMIT :lim
        """), params).mappings().all()
    return {"insights": [dict(r) for r in rows]}
