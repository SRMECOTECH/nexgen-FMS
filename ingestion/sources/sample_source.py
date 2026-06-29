"""
SampleFileSource — reads the real sampled rows under sample_data/*.xlsx.

Lets the whole pipeline run end-to-end offline (no creds, no tunnel) against
schema-faithful data, so the sink/upsert/profiling logic is validated before
we flip to the live lakehouse. Reuses lakehouse.sample_loader so there's one
source of truth for the file mapping.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from ingestion.registry import REGISTRY
from ingestion.sources.base import Source
from lakehouse import sample_loader

logger = logging.getLogger(__name__)


class SampleFileSource(Source):
    name = "sample_xlsx"

    def list_tables(self) -> list[str]:
        return [t for t in REGISTRY if sample_loader.has_sample(t)]

    def read_table(
        self,
        logical: str,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        df = sample_loader.load(logical)
        if df is None:
            logger.warning("SampleFileSource: no sample file for %r — empty frame", logical)
            return pd.DataFrame()

        # Honour incremental window if the watermark column exists & is parseable.
        spec = REGISTRY.get(logical)
        if since is not None and spec and spec.watermark and spec.watermark in df.columns:
            ts = pd.to_datetime(df[spec.watermark], errors="coerce")
            df = df[ts >= pd.Timestamp(since)]

        if limit:
            df = df.head(limit)
        logger.info("SampleFileSource: %s -> %d rows", logical, len(df))
        return df.reset_index(drop=True)
