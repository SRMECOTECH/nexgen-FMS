"""Pluggable warehouse sinks. PostgresSink today; MySQLSink is a drop-in later."""

from __future__ import annotations

from ingestion.config import IngestionConfig
from ingestion.sinks.base import Sink


def make_sink(cfg: IngestionConfig) -> Sink:
    """Factory: choose sink by URL scheme so 'swap the DB' is config-only."""
    if not cfg.has_warehouse_url:
        raise RuntimeError("WAREHOUSE_URL is not set — nowhere to write. See .env.")
    url = cfg.warehouse_url
    if url.startswith(("postgresql", "postgres")):
        from ingestion.sinks.postgres_sink import PostgresSink
        return PostgresSink(url, schema=cfg.raw_schema)
    if url.startswith("mysql"):
        raise NotImplementedError(
            "MySQLSink not implemented yet — the abstraction is ready, add "
            "ingestion/sinks/mysql_sink.py mirroring PostgresSink (ON DUPLICATE KEY)."
        )
    raise ValueError(f"Unsupported WAREHOUSE_URL scheme: {url.split('://')[0]}")


__all__ = ["Sink", "make_sink"]
