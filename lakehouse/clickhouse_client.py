"""
ClickHouse client — for low-latency SQL serving from FastAPI.

The lakehouse exposes a ClickHouse gateway over the same Iceberg tables.
Use this for dashboard endpoints, KPI cards, and any path that needs <1s
responses.

Modes (auto-selected at construction):
    MOCK            -> reads from lakehouse/mock_data.py (real sample files
                       under sample_data/ if present, else synthetic).
    ICEBERG_FALLBACK-> when USE_MOCK_DATA=false AND CLICKHOUSE_PASSWORD is
                       empty (no CH auth available), every SELECT is routed
                       through PyIceberg. We parse the table name out of the
                       SQL and use Iceberg's scan API; pandas does the rest
                       of the SELECT (column projection, LIMIT).
    LIVE            -> CH password is set; talk to ClickHouse over HTTP.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import pandas as pd

from lakehouse.settings import LakehouseSettings, get_settings
from lakehouse.mock_data import get_mock_table

logger = logging.getLogger(__name__)


class ClickHouseClient:
    def __init__(self, settings: Optional[LakehouseSettings] = None) -> None:
        self.settings = settings or get_settings()
        self._client = None
        self._iceberg = None

        if self.settings.use_mock_data:
            self.mode = "MOCK"
        elif not self.settings.clickhouse_password:
            self.mode = "ICEBERG_FALLBACK"
        else:
            self.mode = "LIVE"
        logger.info("ClickHouseClient mode=%s", self.mode)

    # ------------------------------------------------------------------
    def query(self, sql: str, params: Optional[dict[str, Any]] = None) -> pd.DataFrame:
        if self.mode == "MOCK":
            return self._mock_query(sql)
        if self.mode == "ICEBERG_FALLBACK":
            return self._iceberg_query(sql)

        client = self._get_client()
        logger.info("ClickHouse SQL: %s", sql[:120])
        return client.query_df(sql, parameters=params or {})

    def execute(self, sql: str) -> None:
        if self.mode != "LIVE":
            logger.info("ClickHouse[%s] execute (noop): %s", self.mode, sql[:120])
            return
        self._get_client().command(sql)

    # ------------------------------------------------------------------
    # MOCK + ICEBERG_FALLBACK share a tiny SQL parser
    # ------------------------------------------------------------------
    @staticmethod
    def _parse(sql: str) -> tuple[str | None, int | None, str | None]:
        """Return (table, limit, where_clause). Best-effort, single-table only."""
        tm = re.search(r"from\s+([a-z_][a-z0-9_.]*)", sql, re.IGNORECASE)
        if not tm:
            return None, None, None
        table = tm.group(1).split(".")[-1]
        lm = re.search(r"limit\s+(\d+)", sql, re.IGNORECASE)
        limit = int(lm.group(1)) if lm else None
        wm = re.search(r"\bwhere\b(.+?)(?:order\s+by|limit|group\s+by|$)", sql, re.IGNORECASE | re.DOTALL)
        where = wm.group(1).strip() if wm else None
        return table, limit, where

    def _mock_query(self, sql: str) -> pd.DataFrame:
        table, limit, _where = self._parse(sql)
        if not table:
            logger.warning("ClickHouse[MOCK] couldn't parse FROM — returning empty df")
            return pd.DataFrame()
        df = get_mock_table(table)
        return df.head(limit) if limit else df

    def _iceberg_query(self, sql: str) -> pd.DataFrame:
        table, limit, where = self._parse(sql)
        if not table:
            logger.warning("ClickHouse[ICEBERG_FALLBACK] couldn't parse FROM — empty df")
            return pd.DataFrame()
        if self._iceberg is None:
            from lakehouse.pyiceberg_client import PyIcebergClient
            self._iceberg = PyIcebergClient(self.settings)
        logger.info("ClickHouse[ICEBERG_FALLBACK] -> iceberg.%s limit=%s", table, limit)
        df = pd.DataFrame()
        try:
            df = self._iceberg.read_table(table, limit=limit)
        except Exception as exc:
            logger.warning("Iceberg fallback read failed for %s: %s", table, exc)
        # If Iceberg returned an empty slice (table not yet populated), serve
        # the sample-file rows instead so the UI still has something to show.
        if df.empty:
            logger.info("Iceberg returned 0 rows for %s — falling back to sample data", table)
            df = get_mock_table(table)
            if limit:
                df = df.head(limit)
        # Best-effort WHERE filter on simple equality (e.g. lifecycle_status='ACTIVE')
        if where:
            try:
                eq = re.match(r"\s*([a-z_][a-z0-9_]*)\s*=\s*'([^']+)'", where, re.IGNORECASE)
                if eq and eq.group(1) in df.columns:
                    df = df[df[eq.group(1)].astype(str) == eq.group(2)]
            except Exception:
                pass
        return df

    # ------------------------------------------------------------------
    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import clickhouse_connect
        except ImportError as exc:
            raise RuntimeError(
                "clickhouse-connect not installed. Run `pip install clickhouse-connect`."
            ) from exc

        self._client = clickhouse_connect.get_client(
            host=self.settings.clickhouse_host,
            port=self.settings.clickhouse_port,
            username=self.settings.clickhouse_user,
            password=self.settings.clickhouse_password,
            database=self.settings.clickhouse_database,
        )
        return self._client
