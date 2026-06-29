"""
MySQL result-store for route intelligence.

Tables (all prefixed ``ri_``):
    ri_uploads          one row per uploaded Excel
    ri_trips            one row per auto-detected trip in an upload
    ri_analysis_runs    one row per ``analyze`` invocation on a trip
    ri_route_metrics    efficiency / backtracking / traffic / speed-zone JSON
    ri_cost_metrics     cost-model output JSON
    ri_waypoints        consolidated waypoint visits
    ri_time_windows     per-window aggregates (30-min default)
    ri_comparisons      one row per /compare call (list of trip_ids + ranks)
    ri_ai_insights      LLM-generated paragraphs keyed by run/comparison
    ri_geocode_cache    Nominatim reverse-geocode cache
    ri_poi_cache        Overpass POI cache

JSON columns are TEXT (4-byte UTF-8) — MySQL ≥5.7 supports a real JSON
type but keeping TEXT avoids dialect-specific surprises and we always
parse with Python's json module anyway.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# --- engine ------------------------------------------------------------------
def _warehouse_url() -> str:
    url = os.environ.get("WAREHOUSE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        raise RuntimeError("WAREHOUSE_URL is not set — set it in .env")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(_warehouse_url(), pool_pre_ping=True, future=True)


def is_mysql() -> bool:
    return "mysql" in _warehouse_url().lower()


# --- DDL ---------------------------------------------------------------------
# We write MySQL-flavoured DDL but the schema is generic enough that the same
# strings work on Postgres if the user flips WAREHOUSE_URL.
_AI_KEY = "BIGINT" if True else "BIGSERIAL"  # placeholder if we ever templatize

_DDL_MYSQL: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS ri_uploads (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        filename VARCHAR(255) NOT NULL,
        original_name VARCHAR(255),
        sha256 CHAR(64) UNIQUE,
        vehicle_id VARCHAR(64),
        n_rows INT,
        n_dropped INT,
        first_ts DATETIME,
        last_ts DATETIME,
        total_distance_km DOUBLE,
        sheets_json TEXT,
        uploaded_at DATETIME NOT NULL,
        size_bytes BIGINT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_trips (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        upload_id BIGINT NOT NULL,
        seq INT NOT NULL,
        vehicle_id VARCHAR(64),
        start_ts DATETIME NOT NULL,
        end_ts DATETIME NOT NULL,
        duration_min DOUBLE,
        distance_km DOUBLE,
        n_points INT,
        avg_speed_kmph DOUBLE,
        max_speed_kmph DOUBLE,
        moving_min DOUBLE,
        stopped_min DOUBLE,
        from_waypoint VARCHAR(255),
        to_waypoint VARCHAR(255),
        start_lat DOUBLE, start_lng DOUBLE,
        end_lat DOUBLE,   end_lng DOUBLE,
        analyzed TINYINT(1) DEFAULT 0,
        INDEX idx_ri_trips_upload (upload_id),
        UNIQUE KEY uq_ri_trips_upload_seq (upload_id, seq)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_analysis_runs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        trip_id BIGINT NOT NULL,
        params_hash CHAR(40) NOT NULL,
        params_json TEXT NOT NULL,
        status VARCHAR(16) NOT NULL,
        started_at DATETIME NOT NULL,
        finished_at DATETIME,
        error_text TEXT,
        UNIQUE KEY uq_ri_runs_trip_hash (trip_id, params_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_route_metrics (
        run_id BIGINT PRIMARY KEY,
        efficiency_json TEXT,
        speed_zones_json TEXT,
        traffic_json TEXT,
        backtracking_count INT,
        backtracking_json TEXT,
        stop_clusters_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_cost_metrics (
        run_id BIGINT PRIMARY KEY,
        total_cost_inr DOUBLE,
        fuel_cost_inr DOUBLE,
        driver_cost_inr DOUBLE,
        idle_fuel_waste_inr DOUBLE,
        cost_per_km DOUBLE,
        efficiency_pct DOUBLE,
        breakdown_json TEXT,
        opportunities_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_waypoints (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        run_id BIGINT NOT NULL,
        seq INT NOT NULL,
        waypoint VARCHAR(255),
        arrive_ts DATETIME,
        depart_ts DATETIME,
        time_spent_min DOUBLE,
        distance_km DOUBLE,
        cumulative_distance_km DOUBLE,
        avg_speed_kmph DOUBLE,
        lat DOUBLE, lng DOUBLE,
        n_points INT,
        INDEX idx_ri_wp_run (run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_time_windows (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        run_id BIGINT NOT NULL,
        window_start DATETIME,
        window_end DATETIME,
        window_label VARCHAR(16),
        total_distance_km DOUBLE,
        max_speed_kmph DOUBLE,
        avg_speed_kmph DOUBLE,
        avg_moving_speed_kmph DOUBLE,
        moving_time_sec DOUBLE,
        stopped_time_sec DOUBLE,
        waypoint_count INT,
        latitude DOUBLE, longitude DOUBLE,
        dominant_status VARCHAR(16),
        INDEX idx_ri_tw_run (run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_comparisons (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        trip_ids_json TEXT NOT NULL,
        table_json TEXT NOT NULL,
        best_trip_id BIGINT,
        created_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_ai_insights (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        run_id BIGINT NULL,
        comparison_id BIGINT NULL,
        insight_type VARCHAR(48) NOT NULL,
        text MEDIUMTEXT NOT NULL,
        model VARCHAR(96),
        prompt_tokens INT,
        completion_tokens INT,
        created_at DATETIME NOT NULL,
        INDEX idx_ri_ai_run (run_id),
        INDEX idx_ri_ai_cmp (comparison_id),
        INDEX idx_ri_ai_type (insight_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_geocode_cache (
        cache_key VARCHAR(32) PRIMARY KEY,
        lat DOUBLE NOT NULL,
        lng DOUBLE NOT NULL,
        address TEXT,
        raw_json MEDIUMTEXT,
        fetched_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ri_poi_cache (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        cache_key VARCHAR(64) NOT NULL,
        lat DOUBLE NOT NULL,
        lng DOUBLE NOT NULL,
        category VARCHAR(48),
        name VARCHAR(255),
        poi_lat DOUBLE, poi_lng DOUBLE,
        distance_km DOUBLE,
        fetched_at DATETIME NOT NULL,
        INDEX idx_poi_key (cache_key)
    )
    """,
]


_BOOTSTRAPPED = False


def bootstrap(force: bool = False) -> None:
    """Idempotent — runs the DDL once per process."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED and not force:
        return
    eng = get_engine()
    with eng.begin() as c:
        for stmt in _DDL_MYSQL:
            c.execute(text(stmt))
    _BOOTSTRAPPED = True
    logger.info("route_intel: DB tables bootstrapped (mysql=%s)", is_mysql())


# --- helpers -----------------------------------------------------------------
def params_hash(params: Dict[str, Any]) -> str:
    raw = json.dumps(params, sort_keys=True, default=str).encode()
    return hashlib.sha1(raw).hexdigest()


def now() -> datetime:
    return datetime.utcnow()


def js(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def jl(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


# --- DAO: uploads ------------------------------------------------------------
def insert_upload(*, filename: str, original_name: str, sha256: str,
                  vehicle_id: str, n_rows: int, n_dropped: int,
                  first_ts: datetime, last_ts: datetime,
                  total_distance_km: float, sheets: List[str],
                  size_bytes: int) -> int:
    bootstrap()
    with get_engine().begin() as c:
        existing = c.execute(text("SELECT id FROM ri_uploads WHERE sha256=:h"),
                             {"h": sha256}).scalar()
        if existing:
            return int(existing)
        r = c.execute(text("""
            INSERT INTO ri_uploads
              (filename, original_name, sha256, vehicle_id, n_rows, n_dropped,
               first_ts, last_ts, total_distance_km, sheets_json, uploaded_at, size_bytes)
            VALUES
              (:filename, :original_name, :sha256, :vehicle_id, :n_rows, :n_dropped,
               :first_ts, :last_ts, :total_distance_km, :sheets_json, :uploaded_at, :size_bytes)
        """), {
            "filename": filename, "original_name": original_name, "sha256": sha256,
            "vehicle_id": vehicle_id, "n_rows": n_rows, "n_dropped": n_dropped,
            "first_ts": first_ts, "last_ts": last_ts,
            "total_distance_km": total_distance_km, "sheets_json": js(sheets),
            "uploaded_at": now(), "size_bytes": size_bytes,
        })
        return int(r.lastrowid)


def list_uploads(limit: int = 50) -> List[Dict]:
    bootstrap()
    with get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT u.id, u.filename, u.original_name, u.vehicle_id, u.n_rows,
                   u.first_ts, u.last_ts, u.total_distance_km, u.uploaded_at,
                   (SELECT COUNT(*) FROM ri_trips t WHERE t.upload_id=u.id) AS trip_count
            FROM ri_uploads u
            ORDER BY u.uploaded_at DESC
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
    return [dict(r) for r in rows]


def get_upload(upload_id: int) -> Optional[Dict]:
    with get_engine().connect() as c:
        r = c.execute(text("SELECT * FROM ri_uploads WHERE id=:id"),
                      {"id": upload_id}).mappings().first()
        return dict(r) if r else None


# --- DAO: trips --------------------------------------------------------------
def insert_trips(upload_id: int, vehicle_id: str, trips: Iterable[Any]) -> List[int]:
    bootstrap()
    ids: List[int] = []
    with get_engine().begin() as c:
        for t in trips:
            r = c.execute(text("""
                INSERT INTO ri_trips
                  (upload_id, seq, vehicle_id, start_ts, end_ts, duration_min,
                   distance_km, n_points, avg_speed_kmph, max_speed_kmph,
                   moving_min, stopped_min, from_waypoint, to_waypoint,
                   start_lat, start_lng, end_lat, end_lng)
                VALUES
                  (:upload_id, :seq, :vehicle_id, :start_ts, :end_ts, :duration_min,
                   :distance_km, :n_points, :avg_speed_kmph, :max_speed_kmph,
                   :moving_min, :stopped_min, :from_waypoint, :to_waypoint,
                   :start_lat, :start_lng, :end_lat, :end_lng)
            """), {
                "upload_id": upload_id, "seq": t.seq, "vehicle_id": vehicle_id,
                "start_ts": t.start_ts, "end_ts": t.end_ts,
                "duration_min": t.duration_min, "distance_km": t.distance_km,
                "n_points": t.n_points, "avg_speed_kmph": t.avg_speed_kmph,
                "max_speed_kmph": t.max_speed_kmph,
                "moving_min": t.moving_min, "stopped_min": t.stopped_min,
                "from_waypoint": t.from_waypoint, "to_waypoint": t.to_waypoint,
                "start_lat": t.start_lat, "start_lng": t.start_lng,
                "end_lat": t.end_lat, "end_lng": t.end_lng,
            })
            ids.append(int(r.lastrowid))
    return ids


def list_trips_for_upload(upload_id: int) -> List[Dict]:
    bootstrap()
    with get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT * FROM ri_trips WHERE upload_id=:u ORDER BY seq
        """), {"u": upload_id}).mappings().all()
    return [dict(r) for r in rows]


def get_trip(trip_id: int) -> Optional[Dict]:
    with get_engine().connect() as c:
        r = c.execute(text("SELECT * FROM ri_trips WHERE id=:id"),
                      {"id": trip_id}).mappings().first()
        return dict(r) if r else None


def mark_trip_analyzed(trip_id: int) -> None:
    with get_engine().begin() as c:
        c.execute(text("UPDATE ri_trips SET analyzed=1 WHERE id=:id"), {"id": trip_id})


# --- DAO: analysis runs ------------------------------------------------------
def get_or_create_run(trip_id: int, params: Dict[str, Any]) -> int:
    """Returns existing run_id if (trip, params_hash) already analyzed,
    otherwise creates a fresh pending row and returns its id."""
    bootstrap()
    h = params_hash(params)
    with get_engine().begin() as c:
        existing = c.execute(text("""
            SELECT id FROM ri_analysis_runs WHERE trip_id=:t AND params_hash=:h
        """), {"t": trip_id, "h": h}).scalar()
        if existing:
            return int(existing)
        r = c.execute(text("""
            INSERT INTO ri_analysis_runs
              (trip_id, params_hash, params_json, status, started_at)
            VALUES (:t, :h, :p, 'running', :now)
        """), {"t": trip_id, "h": h, "p": js(params), "now": now()})
        return int(r.lastrowid)


def mark_run_done(run_id: int) -> None:
    with get_engine().begin() as c:
        c.execute(text("""
            UPDATE ri_analysis_runs SET status='done', finished_at=:now WHERE id=:id
        """), {"id": run_id, "now": now()})


def mark_run_failed(run_id: int, err: str) -> None:
    with get_engine().begin() as c:
        c.execute(text("""
            UPDATE ri_analysis_runs SET status='failed', finished_at=:now, error_text=:e WHERE id=:id
        """), {"id": run_id, "now": now(), "e": err[:8000]})


def get_run(run_id: int) -> Optional[Dict]:
    with get_engine().connect() as c:
        r = c.execute(text("SELECT * FROM ri_analysis_runs WHERE id=:id"),
                      {"id": run_id}).mappings().first()
        return dict(r) if r else None


def get_latest_done_run_for_trip(trip_id: int) -> Optional[Dict]:
    with get_engine().connect() as c:
        r = c.execute(text("""
            SELECT * FROM ri_analysis_runs
            WHERE trip_id=:t AND status='done'
            ORDER BY finished_at DESC LIMIT 1
        """), {"t": trip_id}).mappings().first()
        return dict(r) if r else None


# --- DAO: per-run result tables ---------------------------------------------
def upsert_route_metrics(run_id: int, *, efficiency: Dict, speed_zones: Dict,
                        traffic: Dict, backtracking: List[Dict],
                        stop_clusters: List[Dict]) -> None:
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM ri_route_metrics WHERE run_id=:r"), {"r": run_id})
        c.execute(text("""
            INSERT INTO ri_route_metrics
              (run_id, efficiency_json, speed_zones_json, traffic_json,
               backtracking_count, backtracking_json, stop_clusters_json)
            VALUES (:r, :e, :z, :t, :bc, :b, :s)
        """), {
            "r": run_id, "e": js(efficiency), "z": js(speed_zones), "t": js(traffic),
            "bc": len(backtracking), "b": js(backtracking), "s": js(stop_clusters),
        })


def upsert_cost_metrics(run_id: int, breakdown: Dict, opportunities: List[Dict]) -> None:
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM ri_cost_metrics WHERE run_id=:r"), {"r": run_id})
        c.execute(text("""
            INSERT INTO ri_cost_metrics
              (run_id, total_cost_inr, fuel_cost_inr, driver_cost_inr,
               idle_fuel_waste_inr, cost_per_km, efficiency_pct,
               breakdown_json, opportunities_json)
            VALUES (:r, :tc, :fc, :dc, :iw, :cpk, :ep, :b, :o)
        """), {
            "r": run_id,
            "tc": breakdown.get("total_cost_inr"),
            "fc": breakdown.get("fuel_cost_inr"),
            "dc": breakdown.get("driver_cost_inr"),
            "iw": breakdown.get("idle_fuel_waste_inr"),
            "cpk": breakdown.get("cost_per_km"),
            "ep": breakdown.get("efficiency_pct"),
            "b": js(breakdown), "o": js(opportunities),
        })


def replace_waypoints(run_id: int, waypoints: List[Dict]) -> None:
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM ri_waypoints WHERE run_id=:r"), {"r": run_id})
        for w in waypoints:
            c.execute(text("""
                INSERT INTO ri_waypoints
                  (run_id, seq, waypoint, arrive_ts, depart_ts, time_spent_min,
                   distance_km, cumulative_distance_km, avg_speed_kmph,
                   lat, lng, n_points)
                VALUES
                  (:r, :seq, :wp, :a, :d, :tm, :km, :ck, :sp, :lat, :lng, :np)
            """), {
                "r": run_id, **{
                    "seq": w["seq"], "wp": w["waypoint"],
                    "a": w["arrive_ts"], "d": w["depart_ts"],
                    "tm": w["time_spent_min"], "km": w["distance_km"],
                    "ck": w["cumulative_distance_km"], "sp": w["avg_speed_kmph"],
                    "lat": w["lat"], "lng": w["lng"], "np": w["n_points"],
                }
            })


def replace_time_windows(run_id: int, df_windows) -> None:
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM ri_time_windows WHERE run_id=:r"), {"r": run_id})
        for _, w in df_windows.iterrows():
            c.execute(text("""
                INSERT INTO ri_time_windows
                  (run_id, window_start, window_end, window_label,
                   total_distance_km, max_speed_kmph, avg_speed_kmph,
                   avg_moving_speed_kmph, moving_time_sec, stopped_time_sec,
                   waypoint_count, latitude, longitude, dominant_status)
                VALUES
                  (:r, :ws, :we, :wl, :td, :ms, :as_, :ams, :mt, :st,
                   :wc, :la, :lo, :ds)
            """), {
                "r": run_id,
                "ws": w["window_start"].to_pydatetime(),
                "we": w["window_end"].to_pydatetime(),
                "wl": w["window_label"],
                "td": float(w["total_distance_km"]),
                "ms": float(w["max_speed_kmph"]),
                "as_": float(w["avg_speed_kmph"]),
                "ams": float(w["avg_moving_speed_kmph"]),
                "mt": float(w["moving_time_sec"]),
                "st": float(w["stopped_time_sec"]),
                "wc": int(w["waypoint_count"]),
                "la": float(w["latitude"]),
                "lo": float(w["longitude"]),
                "ds": w["dominant_status"],
            })


# --- DAO: bundle read --------------------------------------------------------
def fetch_full_analysis(run_id: int) -> Dict:
    with get_engine().connect() as c:
        rm = c.execute(text("SELECT * FROM ri_route_metrics WHERE run_id=:r"),
                       {"r": run_id}).mappings().first()
        cm = c.execute(text("SELECT * FROM ri_cost_metrics WHERE run_id=:r"),
                       {"r": run_id}).mappings().first()
        wp = c.execute(text("SELECT * FROM ri_waypoints WHERE run_id=:r ORDER BY seq"),
                       {"r": run_id}).mappings().all()
        tw = c.execute(text("SELECT * FROM ri_time_windows WHERE run_id=:r ORDER BY window_start"),
                       {"r": run_id}).mappings().all()
        ai = c.execute(text("""
            SELECT insight_type, text, model, created_at FROM ri_ai_insights
            WHERE run_id=:r ORDER BY created_at
        """), {"r": run_id}).mappings().all()
    return {
        "route_metrics": {
            "efficiency": jl(rm["efficiency_json"]) if rm else None,
            "speed_zones": jl(rm["speed_zones_json"]) if rm else None,
            "traffic": jl(rm["traffic_json"]) if rm else None,
            "backtracking_count": rm["backtracking_count"] if rm else 0,
            "backtracking": jl(rm["backtracking_json"]) if rm else [],
            "stop_clusters": jl(rm["stop_clusters_json"]) if rm else [],
        } if rm else None,
        "cost_metrics": {
            "breakdown": jl(cm["breakdown_json"]) if cm else None,
            "opportunities": jl(cm["opportunities_json"]) if cm else [],
        } if cm else None,
        "waypoints": [dict(w) for w in wp],
        "time_windows": [dict(w) for w in tw],
        "ai_insights": [dict(a) for a in ai],
    }


# --- DAO: AI insights --------------------------------------------------------
def insert_ai_insight(*, run_id: Optional[int] = None,
                      comparison_id: Optional[int] = None,
                      insight_type: str, text_body: str, model: str,
                      prompt_tokens: Optional[int] = None,
                      completion_tokens: Optional[int] = None) -> int:
    bootstrap()
    with get_engine().begin() as c:
        if run_id is not None:
            c.execute(text("""
                DELETE FROM ri_ai_insights
                WHERE run_id=:r AND insight_type=:t
            """), {"r": run_id, "t": insight_type})
        if comparison_id is not None:
            c.execute(text("""
                DELETE FROM ri_ai_insights
                WHERE comparison_id=:cmp AND insight_type=:t
            """), {"cmp": comparison_id, "t": insight_type})
        r = c.execute(text("""
            INSERT INTO ri_ai_insights
              (run_id, comparison_id, insight_type, text, model,
               prompt_tokens, completion_tokens, created_at)
            VALUES (:r, :cmp, :t, :body, :m, :pt, :ct, :now)
        """), {"r": run_id, "cmp": comparison_id, "t": insight_type,
               "body": text_body, "m": model, "pt": prompt_tokens,
               "ct": completion_tokens, "now": now()})
        return int(r.lastrowid)


def fetch_insights_for_run(run_id: int) -> List[Dict]:
    with get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT insight_type, text, model, created_at FROM ri_ai_insights
            WHERE run_id=:r ORDER BY created_at
        """), {"r": run_id}).mappings().all()
    return [dict(r) for r in rows]


# --- DAO: comparisons --------------------------------------------------------
def insert_comparison(trip_ids: List[int], table_rows: List[Dict],
                      best_trip_id: Optional[int]) -> int:
    bootstrap()
    with get_engine().begin() as c:
        r = c.execute(text("""
            INSERT INTO ri_comparisons (trip_ids_json, table_json, best_trip_id, created_at)
            VALUES (:t, :tab, :b, :now)
        """), {"t": js(trip_ids), "tab": js(table_rows),
               "b": best_trip_id, "now": now()})
        return int(r.lastrowid)


def get_comparison(cmp_id: int) -> Optional[Dict]:
    with get_engine().connect() as c:
        r = c.execute(text("SELECT * FROM ri_comparisons WHERE id=:id"),
                      {"id": cmp_id}).mappings().first()
        if not r:
            return None
        d = dict(r)
        d["trip_ids"] = jl(d.pop("trip_ids_json")) or []
        d["table"] = jl(d.pop("table_json")) or []
        ai = c.execute(text("""
            SELECT insight_type, text, model, created_at FROM ri_ai_insights
            WHERE comparison_id=:cmp ORDER BY created_at
        """), {"cmp": cmp_id}).mappings().all()
        d["ai_insights"] = [dict(x) for x in ai]
        return d


def list_comparisons(limit: int = 30) -> List[Dict]:
    with get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT id, trip_ids_json, best_trip_id, created_at
            FROM ri_comparisons ORDER BY created_at DESC LIMIT :lim
        """), {"lim": limit}).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["trip_ids"] = jl(d.pop("trip_ids_json")) or []
        out.append(d)
    return out
