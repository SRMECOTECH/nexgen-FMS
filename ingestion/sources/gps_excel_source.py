"""
GpsExcelSource — reads the raw device GPS Excel (data/gpsfinal_*.xlsx) and
exposes it as the single logical table ``gps_feed``.

It delegates the actual file read + 40-column normalisation to
``lakehouse.gps_feed`` so the transform is shared with the read-time analytics.
This is the source you select for the "one-button upload all GPS data" flow:

    python -m ingestion --source gps_excel --tables gps_feed
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from ingestion.sources.base import Source
from lakehouse import gps_feed

logger = logging.getLogger(__name__)


class GpsExcelSource(Source):
    name = "gps_excel"

    def list_tables(self) -> list[str]:
        return ["gps_feed"]

    def read_table(
        self,
        logical: str,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        if logical != "gps_feed":
            logger.warning("GpsExcelSource: unknown table %r — empty frame", logical)
            return pd.DataFrame()

        df = gps_feed.load_normalized()
        if df.empty:
            return df

        if since is not None and "gps_ts" in df.columns:
            df = df[df["gps_ts"] >= pd.Timestamp(since)]
        if limit:
            df = df.head(limit)

        logger.info("GpsExcelSource: gps_feed -> %d rows", len(df))
        return df.reset_index(drop=True)
