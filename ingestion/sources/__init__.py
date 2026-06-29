"""Pluggable data sources. Pick one via INGEST_SOURCE / --source."""

from __future__ import annotations

from ingestion.config import IngestionConfig
from ingestion.sources.base import Source


def make_source(cfg: IngestionConfig) -> Source:
    """Factory: instantiate the configured source."""
    name = cfg.source
    if name == "sample":
        from ingestion.sources.sample_source import SampleFileSource
        return SampleFileSource()
    if name == "iceberg":
        from ingestion.sources.iceberg_source import IcebergSource
        return IcebergSource(cfg)
    if name == "gps_excel":
        from ingestion.sources.gps_excel_source import GpsExcelSource
        return GpsExcelSource()
    raise ValueError(f"Unknown INGEST_SOURCE={name!r}. Use 'sample', 'iceberg' or 'gps_excel'.")


__all__ = ["Source", "make_source"]
