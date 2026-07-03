"""
/api/v1/observe/* — fleet-wide raw-signal rollup.

Reads the route-intel warehouse (the same tables the trip pages render from)
and turns it into a single "what does my fleet look like right now" payload
the Observe page consumes. Three buckets:

  * KPIs              — totals across every uploaded trip
  * Vehicle roster    — one row per known vehicle with last-seen status
  * Alerts            — derived directly from trip + segment metrics:
                          long idle, slow average speed, very long hauls,
                          excessive backtracking events
  * Recent activity   — latest N trips, chronological

No mock data — everything comes from ri_uploads / ri_trips / ri_segments /
ri_route_metrics. When you upload more Excels this page automatically updates.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter
from sqlalchemy import text

from route_intelligence import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/observe", tags=["observe"])


@router.get("/snapshot")
def snapshot() -> Dict[str, Any]:
    """Single payload powering the Observe page. ~one round-trip to MySQL."""
    with db.get_engine().connect() as c:
        # --- KPIs -----------------------------------------------------------
        kpi_row = c.execute(text("""
            SELECT
                COUNT(DISTINCT vehicle_id) AS n_vehicles,
                COUNT(*)                   AS n_trips,
                COALESCE(SUM(distance_km), 0)         AS total_km,
                COALESCE(SUM(duration_min) / 60, 0)   AS total_hours,
                COALESCE(SUM(moving_min)  / 60, 0)    AS moving_hours,
                COALESCE(SUM(stopped_min) / 60, 0)    AS stopped_hours,
                COALESCE(AVG(avg_speed_kmph), 0)      AS avg_speed_kmph,
                COALESCE(MAX(max_speed_kmph), 0)      AS max_speed_kmph,
                MAX(end_ts)                AS latest_activity_ts,
                MIN(start_ts)              AS first_activity_ts
            FROM ri_trips
        """)).mappings().first() or {}

        # --- Vehicle roster ------------------------------------------------
        vehicles = c.execute(text("""
            SELECT
                COALESCE(u.vehicle_id, t.vehicle_id) AS vehicle_id,
                COUNT(DISTINCT u.id)  AS n_uploads,
                COUNT(DISTINCT t.id)  AS n_trips,
                COALESCE(SUM(t.distance_km), 0)    AS total_km,
                COALESCE(SUM(t.duration_min) / 60, 0) AS total_hours,
                COALESCE(SUM(t.moving_min)  / 60, 0)  AS moving_hours,
                COALESCE(SUM(t.stopped_min) / 60, 0)  AS stopped_hours,
                COALESCE(AVG(t.avg_speed_kmph), 0) AS avg_speed_kmph,
                COALESCE(MAX(t.max_speed_kmph), 0) AS max_speed_kmph,
                COALESCE(SUM(t.n_segments), 0)     AS total_segments,
                MAX(t.end_ts)         AS last_trip_end,
                MAX(u.last_ts)        AS last_seen_ts,
                MIN(u.first_ts)       AS first_seen_ts,
                SUM(CASE WHEN t.analyzed = 1 THEN 1 ELSE 0 END) AS n_analyzed
            FROM ri_uploads u
            LEFT JOIN ri_trips t ON t.upload_id = u.id
            WHERE COALESCE(u.vehicle_id, t.vehicle_id) IS NOT NULL
            GROUP BY COALESCE(u.vehicle_id, t.vehicle_id)
            ORDER BY MAX(u.last_ts) DESC, MAX(t.end_ts) DESC
        """)).mappings().all()

        # --- Recent activity (last 25 trips) -------------------------------
        recent_trips = c.execute(text("""
            SELECT id, upload_id, vehicle_id, from_waypoint, to_waypoint,
                   start_ts, end_ts, distance_km, duration_min, moving_min,
                   stopped_min, n_segments, avg_speed_kmph, max_speed_kmph,
                   analyzed
            FROM ri_trips
            ORDER BY start_ts DESC
            LIMIT 25
        """)).mappings().all()

        # --- Alerts (derived from trip-level metrics) -----------------------
        # Each branch produces (type, severity, note, metric) so the UI can
        # sort + colour-code without any per-row logic.
        alerts = c.execute(text("""
            SELECT * FROM (
                SELECT 'long_idle' AS alert_type, 'HIGH' AS severity,
                       t.id AS trip_id, t.vehicle_id,
                       t.from_waypoint, t.to_waypoint, t.start_ts,
                       CONCAT(ROUND(t.stopped_min / 60, 1), ' h stopped') AS note,
                       t.stopped_min AS metric
                FROM ri_trips t
                WHERE t.stopped_min > 240

                UNION ALL
                SELECT 'slow_avg', 'MEDIUM',
                       t.id, t.vehicle_id, t.from_waypoint, t.to_waypoint, t.start_ts,
                       CONCAT(ROUND(t.avg_speed_kmph, 1), ' km/h average'),
                       100 - t.avg_speed_kmph
                FROM ri_trips t
                WHERE t.avg_speed_kmph < 20 AND t.avg_speed_kmph > 0

                UNION ALL
                SELECT 'long_haul', 'LOW',
                       t.id, t.vehicle_id, t.from_waypoint, t.to_waypoint, t.start_ts,
                       CONCAT(ROUND(t.distance_km), ' km · ', ROUND(t.duration_min / 60, 1), ' h'),
                       t.distance_km
                FROM ri_trips t
                WHERE t.distance_km > 500

                UNION ALL
                SELECT 'unanalysed', 'LOW',
                       t.id, t.vehicle_id, t.from_waypoint, t.to_waypoint, t.start_ts,
                       'No AI analysis yet — click to analyse',
                       1
                FROM ri_trips t
                WHERE COALESCE(t.analyzed, 0) = 0
            ) a
            ORDER BY FIELD(a.severity, 'HIGH', 'MEDIUM', 'LOW'),
                     a.metric DESC
            LIMIT 50
        """)).mappings().all()

        # --- Backtracking alerts (from route_metrics) ----------------------
        bt = c.execute(text("""
            SELECT ar.trip_id, t.vehicle_id, t.from_waypoint, t.to_waypoint, t.start_ts,
                   r.backtracking_json
            FROM ri_route_metrics r
            JOIN ri_analysis_runs ar ON ar.id = r.run_id
            JOIN ri_trips t ON t.id = ar.trip_id
            WHERE r.backtracking_json IS NOT NULL
              AND ar.params_json NOT LIKE '%"scope": "segment"%'
        """)).mappings().all()

    # --- Post-process alerts (parse JSON, append backtracking) -------------
    alerts_out: List[Dict[str, Any]] = [dict(a) for a in alerts]
    import json
    for r in bt:
        try:
            arr = json.loads(r["backtracking_json"]) if r["backtracking_json"] else []
        except Exception:
            arr = []
        if len(arr) >= 5:
            alerts_out.append({
                "alert_type": "backtracks",
                "severity":   "MEDIUM" if len(arr) >= 10 else "LOW",
                "trip_id":    r["trip_id"],
                "vehicle_id": r["vehicle_id"],
                "from_waypoint": r["from_waypoint"],
                "to_waypoint":   r["to_waypoint"],
                "start_ts":   r["start_ts"],
                "note":       f"{len(arr)} backtracking events on this trip",
                "metric":     len(arr),
            })
    # Keep at most 50 alerts, severity-first.
    rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    alerts_out.sort(key=lambda a: (-rank.get(a.get("severity"), 0), -(a.get("metric") or 0)))
    alerts_out = alerts_out[:50]

    return {
        "generated_at":  datetime.utcnow().isoformat() + "Z",
        "kpis":          _serialize(kpi_row),
        "vehicles":      [_serialize(v) for v in vehicles],
        "recent_trips":  [_serialize(t) for t in recent_trips],
        "alerts":        [_serialize(a) for a in alerts_out],
    }


@router.get("/device-alerts")
def device_alerts(limit_files: int = 200) -> Dict[str, Any]:
    """Findings from the vendor ``s_alert_lov`` column across every uploaded GPS
    Excel — the "what are the devices actually reporting?" view. Grouped by
    alert code (headline) → affected devices (drill-down). Updates automatically
    as new files are uploaded; codes are named via the editable label map so
    the findings get more meaningful over time.
    """
    from route_intelligence import alert_lov, pipeline
    uploads = db.list_uploads(limit=limit_files)
    enriched = []
    for u in uploads:
        enriched.append({
            "upload_id":    u["id"],
            "vehicle_id":   u.get("vehicle_id"),
            "display_name": u.get("display_name"),
            "path":         str(pipeline.UPLOAD_DIR / u["filename"]),
        })
    payload = alert_lov.build_findings(enriched)
    payload["generated_at"] = datetime.utcnow().isoformat() + "Z"
    return payload


@router.get("/alert-labels")
def get_alert_labels() -> Dict[str, Any]:
    """The editable ``s_alert_lov`` code → human label map."""
    from route_intelligence import alert_lov
    return {"labels": alert_lov.load_labels()}


@router.put("/alert-labels")
def put_alert_labels(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ``{code: label}`` pairs into the map so findings show real names."""
    from route_intelligence import alert_lov
    return {"labels": alert_lov.save_labels(patch or {})}


def _serialize(row) -> Dict[str, Any]:
    """datetime → ISO string so json.dumps in FastAPI doesn't choke."""
    out = dict(row) if row is not None else {}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out
