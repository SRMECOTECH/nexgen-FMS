"""
DuckDB client — for ad-hoc analysis from scripts and notebooks.

Reads Iceberg tables directly via DuckDB's iceberg extension. In mock mode
it simply registers the mock DataFrames as views so the same query syntax
works.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from lakehouse.settings import LakehouseSettings, get_settings
from lakehouse.mock_data import TABLE_BUILDERS, get_mock_table

logger = logging.getLogger(__name__)


class DuckDBClient:
    def __init__(self, settings: Optional[LakehouseSettings] = None) -> None:
        self.settings = settings or get_settings()
        self._con = None

    def query(self, sql: str) -> pd.DataFrame:
        con = self._get_connection()
        logger.info("DuckDB SQL: %s", sql[:120])
        return con.execute(sql).fetchdf()

    def _get_connection(self):
        if self._con is not None:
            return self._con

        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError(
                "duckdb not installed. Run `pip install duckdb` or keep "
                "USE_MOCK_DATA=true in .env."
            ) from exc

        self._con = duckdb.connect(":memory:")

        if self.settings.use_mock_data:
            for name in TABLE_BUILDERS:
                self._con.register(name, get_mock_table(name))
            logger.info("DuckDB[MOCK] registered %d mock tables", len(TABLE_BUILDERS))
            return self._con

        # TODO: enable iceberg + s3 extensions and point at the real catalog.
        #       See https://duckdb.org/docs/extensions/iceberg
        self._con.execute("INSTALL iceberg; LOAD iceberg;")
        self._con.execute("INSTALL httpfs; LOAD httpfs;")
        self._con.execute(f"SET s3_endpoint='{self.settings.s3_endpoint}';")
        self._con.execute(f"SET s3_access_key_id='{self.settings.s3_access_key}';")
        self._con.execute(f"SET s3_secret_access_key='{self.settings.s3_secret_key}';")
        return self._con
