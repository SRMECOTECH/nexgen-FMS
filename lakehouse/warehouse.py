"""
Warehouse reader — read-side access to the Neon Postgres warehouse.

This is the counterpart to ingestion/sinks/postgres_sink.py (the write side).
The backend reads analytics tables (e.g. ``raw.gps_feed``) from here so that,
once the upload button has filled the cloud DB, the whole app runs off the
warehouse. Only the connection string (WAREHOUSE_URL) varies between
environments — swap it and everything else is unchanged.

If the warehouse is unreachable or the table is empty, ``read_gps_feed`` falls
back to normalising the local Excel directly, so the UI never goes blank during
development / before the first upload.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from functools import lru_cache

import pandas as pd

logger = logging.getLogger(__name__)

_TS_COLS = ("gps_ts", "server_ts", "created_ts")

# In-process cache of the (static) gps_feed snapshot. A full SELECT against
# remote Neon takes ~5s; the GPS page fires ~8 endpoints at once, so without
# this every page view would do 8 remote reads and several would time out.
# The lock makes concurrent cache-misses serialize on ONE read instead of
# stampeding the DB with 8 parallel SELECTs.
_CACHE_TTL_SEC = 600
_gps_cache: dict = {}          # keyed by vehicle ("" = all) -> {"df", "ts"}
_gps_lock = threading.Lock()


def invalidate_gps_cache() -> None:
    """Drop the cached gps_feed (call after an upload so reads see new rows)."""
    _gps_cache.clear()


def _warehouse_url() -> str | None:
    url = os.environ.get("WAREHOUSE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        return None
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    return url


@lru_cache(maxsize=1)
def _engine():
    url = _warehouse_url()
    if not url:
        return None
    try:
        from sqlalchemy import create_engine
        return create_engine(url, pool_pre_ping=True)
    except Exception as exc:  # pragma: no cover
        logger.warning("warehouse: engine init failed: %s", exc)
        return None


def _raw_schema() -> str:
    return os.environ.get("WAREHOUSE_RAW_SCHEMA", "raw")


def is_available() -> bool:
    return _engine() is not None


def table_count(table: str, schema: str | None = None) -> int:
    """Row count for a warehouse table, or -1 if it can't be read."""
    eng = _engine()
    if eng is None:
        return -1
    schema = schema or _raw_schema()
    try:
        from sqlalchemy import text
        with eng.connect() as c:
            return int(c.execute(text(f'SELECT count(*) FROM "{schema}"."{table}"')).scalar() or 0)
    except Exception:
        return -1


def read_gps_feed(force_file: bool = False, vehicle: str | None = None) -> pd.DataFrame:
    """Return the normalised gps_feed, per vehicle when given.

    Order of preference:
      1. normalised warehouse (dim_vehicle/dim_node/fact_gps_ping via gps_store)
      2. legacy flat ``raw.gps_feed`` table (Postgres only)
      3. local Excel file
    Per-vehicle results are cached in-process for _CACHE_TTL_SEC; a concurrent
    lock collapses the GPS page's ~8 simultaneous calls into one DB read.
    """
    key = vehicle or ""

    def _fresh(c):
        return c is not None and (time.time() - c["ts"]) < _CACHE_TTL_SEC

    if not force_file and _fresh(_gps_cache.get(key)):
        return _gps_cache[key]["df"]
    if force_file:
        return _read_gps_feed_uncached(force_file=True, vehicle=vehicle)

    with _gps_lock:
        if _fresh(_gps_cache.get(key)):
            return _gps_cache[key]["df"]
        df = _read_gps_feed_uncached(force_file=False, vehicle=vehicle)
        _gps_cache[key] = {"df": df, "ts": time.time()}
        return df


def warm_gps_cache() -> int:
    """Populate the gps_feed cache once (called at startup). Returns row count."""
    try:
        return len(read_gps_feed())
    except Exception as exc:  # never block startup
        logger.warning("warehouse: warm_gps_cache failed: %s", exc)
        return -1


def _read_gps_feed_uncached(force_file: bool = False, vehicle: str | None = None) -> pd.DataFrame:
    if not force_file:
        # 1) normalised store (works on MySQL + Postgres)
        try:
            from lakehouse import gps_store
            if gps_store.schema_ready():
                df = gps_store.read_feed(vehicle)
                if not df.empty:
                    logger.info("warehouse: read fact_gps_ping (%d rows, vehicle=%s)", len(df), vehicle or "ALL")
                    return df.sort_values("gps_ts").reset_index(drop=True)
        except Exception as exc:
            logger.info("warehouse: normalised store unavailable (%s)", exc)

        # 2) legacy flat table (Postgres)
        eng = _engine()
        if eng is not None:
            schema = _raw_schema()
            try:
                df = pd.read_sql(f'SELECT * FROM "{schema}"."gps_feed"', eng)
                if not df.empty:
                    for c in _TS_COLS:
                        if c in df.columns:
                            df[c] = pd.to_datetime(df[c], errors="coerce")
                    if vehicle and "vehicle_reg" in df.columns:
                        df = df[df["vehicle_reg"] == vehicle]
                    return df.sort_values("gps_ts").reset_index(drop=True)
            except Exception as exc:
                logger.info("warehouse: flat gps_feed not readable (%s) — falling back to file", exc)

    # 3) Fallback: normalise the local Excel directly.
    from lakehouse import gps_feed
    df = gps_feed.load_normalized()
    if vehicle and not df.empty:
        df = df[df["vehicle_reg"] == vehicle]
    return df


def gps_source_label() -> str:
    """Human-readable label of where gps_feed is currently being served from."""
    try:
        from lakehouse import gps_store
        if gps_store.schema_ready():
            c = gps_store.counts()
            return f"{gps_store.dialect()}: fact_gps_ping ({c['pings']:,} pings, {c['vehicles']} vehicles)"
    except Exception:
        pass
    n = table_count("gps_feed")
    if n > 0:
        return f"warehouse:{_raw_schema()}.gps_feed ({n:,} rows)"
    return "file:data/gpsfinal_*.xlsx"
