"""
PyIceberg client — for batch reads from the neXgen-Lakehouse.

Connection pattern mirrors the working scripts/check_iceberg.py and the
infra script the lakehouse team uses internally. The S3V4 signer +
ssl-enabled=false + path-style-access combination is required to talk to
MinIO; without those flags pyiceberg can load the catalog but every data
read fails with an opaque S3 signature error.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from lakehouse.settings import LakehouseSettings, get_settings
from lakehouse.mock_data import get_mock_table

logger = logging.getLogger(__name__)

# Iceberg table name (under telemetry namespace) by our logical name
_ICEBERG_NAME = {
    "fact_trips":           "fact_trips",
    "fact_trip_legs":       "fact_trip_legs",
    "gps_telemetry_events": "gps_telemetry_events",
    "gps_events":           "gps_events",
    "trip_detail":          "trip_detail",
    "trip_header":          "trip_header",
}


class PyIcebergClient:
    def __init__(self, settings: Optional[LakehouseSettings] = None) -> None:
        self.settings = settings or get_settings()
        self._catalog = None  # lazy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def read_table(self, table: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Read an Iceberg table (optionally limited) into a DataFrame."""
        if self.settings.use_mock_data:
            logger.info("PyIcebergClient[MOCK] read_table(%s, limit=%s)", table, limit)
            df = get_mock_table(table)
            return df.head(limit) if limit else df

        catalog = self._get_catalog()
        iceberg_name = _ICEBERG_NAME.get(table, table)
        full_name = f"{self.settings.iceberg_namespace}.{iceberg_name}"
        logger.info("PyIcebergClient read_table(%s) limit=%s", full_name, limit)
        iceberg_tbl = catalog.load_table(full_name)
        scan = iceberg_tbl.scan(limit=limit) if limit else iceberg_tbl.scan()
        return scan.to_arrow().to_pandas()

    def list_tables(self) -> list[str]:
        if self.settings.use_mock_data:
            from lakehouse.mock_data import TABLE_BUILDERS
            return list(TABLE_BUILDERS.keys())
        catalog = self._get_catalog()
        return [t[-1] for t in catalog.list_tables(self.settings.iceberg_namespace)]

    def read_window(
        self,
        table: str,
        ts_column: str,
        hours: float = 24,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Read rows where ts_column >= now-hours. Uses Iceberg partition/stats
        pruning so this stays cheap even on huge tables."""
        if self.settings.use_mock_data:
            return self.read_table(table, limit=limit)

        from datetime import datetime, timedelta, timezone
        from pyiceberg.expressions import GreaterThanOrEqual

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(tzinfo=None)
        cutoff_literal = cutoff.isoformat(timespec="microseconds")

        catalog = self._get_catalog()
        iceberg_name = _ICEBERG_NAME.get(table, table)
        full_name = f"{self.settings.iceberg_namespace}.{iceberg_name}"
        tbl = catalog.load_table(full_name)
        scan = tbl.scan(row_filter=GreaterThanOrEqual(ts_column, cutoff_literal))
        df = scan.to_arrow().to_pandas()
        return df.head(limit) if limit else df

    # ------------------------------------------------------------------
    # Catalog loader — exact working pattern from check_iceberg.py
    # ------------------------------------------------------------------
    def _get_catalog(self):
        if self._catalog is not None:
            return self._catalog

        if self.settings.disable_iceberg:
            raise RuntimeError(
                "Iceberg is disabled (DISABLE_ICEBERG=true or no S3/catalog creds set). "
                "Set DISABLE_ICEBERG=false and provide S3_ACCESS_KEY + ICEBERG_TOKEN to re-enable."
            )

        try:
            from pyiceberg.catalog import load_catalog
        except ImportError as exc:
            raise RuntimeError(
                "pyiceberg not installed. Run `pip install 'pyiceberg[s3fs,pyarrow]'` "
                "or keep USE_MOCK_DATA=true in .env."
            ) from exc

        s = self.settings
        logger.debug(
            "PyIcebergClient connecting catalog=%s s3=%s region=%s",
            s.iceberg_catalog_uri, s.s3_endpoint, s.s3_region,
        )
        self._catalog = load_catalog(
            "rest_catalog",
            **{
                "type":                  "rest",
                "uri":                   s.iceberg_catalog_uri,
                "s3.endpoint":           s.s3_endpoint,
                "s3.access-key-id":      s.s3_access_key,
                "s3.secret-access-key":  s.s3_secret_key,
                "s3.region":             s.s3_region,
                "s3.path-style-access":  "true",
                "s3.signer":             "S3V4",
                "s3.ssl-enabled":        "false",
            },
        )
        return self._catalog
