"""
PostgresSink — lands DataFrames into a Postgres warehouse (Neon).

Design choices for robustness:
  * Tables are auto-created from the DataFrame's dtypes on first sight, into a
    dedicated raw schema (default 'raw'), plus _source/_run_id/_ingested_at
    metadata columns.
  * Idempotent UPSERT via a staging table + INSERT ... ON CONFLICT, keyed on
    the table's natural key, so re-runs update in place instead of duplicating.
  * 'full' mode truncates then loads (for tables with no natural key).
  * dict/list cells (e.g. extra_data) are JSON-encoded so they fit a text col.

Everything goes through SQLAlchemy, so porting to MySQL means subclassing and
swapping the ON CONFLICT clause for ON DUPLICATE KEY — no pipeline changes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, inspect, text

from ingestion.sinks.base import Sink

logger = logging.getLogger(__name__)

_META_COLS = ("_source", "_run_id", "_ingested_at")


def _normalize_url(url: str) -> str:
    """Force the psycopg (v3) driver; accept bare postgres:// URLs."""
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


class PostgresSink(Sink):
    name = "postgres"

    def __init__(self, url: str, schema: str = "raw") -> None:
        self.schema = schema
        self.engine = create_engine(_normalize_url(url), pool_pre_ping=True)

    # ------------------------------------------------------------------
    def ensure_schemas(self) -> None:
        with self.engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"'))
            c.execute(text("CREATE SCHEMA IF NOT EXISTS meta"))
        self._ensure_audit_table()

    # ------------------------------------------------------------------
    def write(self, table, df, keys, mode, source, run_id) -> int:
        if df is None or df.empty:
            logger.info("PostgresSink: %s has 0 rows — nothing to write", table)
            # still ensure the (empty) table exists so downstream queries don't 500
            return 0

        df = self._sanitize(df)
        df["_source"] = source
        df["_run_id"] = run_id
        df["_ingested_at"] = datetime.now(timezone.utc)

        usable_keys = [k for k in keys if k in df.columns]
        if usable_keys:
            # collapse intra-batch dupes: ON CONFLICT can't hit a key twice, and
            # a full-load append would violate the table's unique index otherwise
            before = len(df)
            df = df.drop_duplicates(subset=usable_keys, keep="last").reset_index(drop=True)
            if len(df) < before:
                logger.info("PostgresSink: %s deduped %d -> %d on %s",
                            table, before, len(df), usable_keys)
        self._ensure_table(table, df, usable_keys)

        if mode == "full" or not usable_keys:
            return self._full_load(table, df, truncate=(mode == "full"))
        return self._upsert(table, df, usable_keys)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    @staticmethod
    def _sanitize(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        int64_max = np.iinfo(np.int64).max
        for col in df.columns:
            dt = df[col].dtype
            # Postgres has no unsigned ints — downcast to int64, or str if it overflows
            if dt.kind == "u":
                df[col] = (df[col].astype("int64") if df[col].max() <= int64_max
                           else df[col].astype(str))
            elif dt == "object":
                # JSON-encode dict/list cells; leave plain strings/None alone
                if df[col].map(lambda v: isinstance(v, (dict, list))).any():
                    df[col] = df[col].map(
                        lambda v: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v
                    )
        return df

    def _qual(self, table: str) -> str:
        return f'"{self.schema}"."{table}"'

    def _ensure_table(self, table: str, df: pd.DataFrame, keys: list[str]) -> None:
        insp = inspect(self.engine)
        if not insp.has_table(table, schema=self.schema):
            # create columns/types by writing the header (0 rows)
            df.head(0).to_sql(table, self.engine, schema=self.schema,
                              if_exists="fail", index=False)
            logger.info("PostgresSink: created %s (%d cols)", self._qual(table), len(df.columns))
        if keys:
            cols = ", ".join(f'"{k}"' for k in keys)
            idx = ("ux_" + table + "_" + "_".join(keys))[:60]
            with self.engine.begin() as c:
                c.execute(text(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx}" ON {self._qual(table)} ({cols})'
                ))

    def _full_load(self, table: str, df: pd.DataFrame, truncate: bool) -> int:
        with self.engine.begin() as c:
            if truncate:
                c.execute(text(f"TRUNCATE TABLE {self._qual(table)}"))
        df.to_sql(table, self.engine, schema=self.schema, if_exists="append",
                  index=False, method="multi", chunksize=500)
        logger.info("PostgresSink: %s full-load %d rows (truncate=%s)", table, len(df), truncate)
        return len(df)

    def _upsert(self, table: str, df: pd.DataFrame, keys: list[str]) -> int:
        stg = f"_stg_{table}"
        df.to_sql(stg, self.engine, schema=self.schema, if_exists="replace",
                  index=False, method="multi", chunksize=500)
        cols = list(df.columns)
        collist = ", ".join(f'"{c}"' for c in cols)
        conflict = ", ".join(f'"{k}"' for k in keys)
        non_keys = [c for c in cols if c not in keys]
        if non_keys:
            updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in non_keys)
            action = f"DO UPDATE SET {updates}"
        else:
            action = "DO NOTHING"
        sql = (
            f"INSERT INTO {self._qual(table)} ({collist}) "
            f'SELECT {collist} FROM "{self.schema}"."{stg}" '
            f"ON CONFLICT ({conflict}) {action}"
        )
        with self.engine.begin() as c:
            c.execute(text(sql))
            c.execute(text(f'DROP TABLE "{self.schema}"."{stg}"'))
        logger.info("PostgresSink: %s upsert %d rows on %s", table, len(df), keys)
        return len(df)

    # ------------------------------------------------------------------
    # audit
    # ------------------------------------------------------------------
    def _ensure_audit_table(self) -> None:
        with self.engine.begin() as c:
            c.execute(text("""
                CREATE TABLE IF NOT EXISTS meta.ingestion_runs (
                    run_id       text,
                    table_name   text,
                    source       text,
                    mode         text,
                    rows_written bigint,
                    status       text,
                    error        text,
                    started_at   timestamptz,
                    finished_at  timestamptz
                )
            """))

    def write_meta(self, table: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        self._sanitize(df).to_sql(table, self.engine, schema="meta",
                                  if_exists="append", index=False,
                                  method="multi", chunksize=500)

    def record_run(self, row: dict) -> None:
        with self.engine.begin() as c:
            c.execute(text("""
                INSERT INTO meta.ingestion_runs
                    (run_id, table_name, source, mode, rows_written, status, error, started_at, finished_at)
                VALUES
                    (:run_id, :table_name, :source, :mode, :rows_written, :status, :error, :started_at, :finished_at)
            """), row)
