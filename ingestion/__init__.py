"""
nextGen-FMS ingestion package.

A small, pluggable ETL layer that pulls fleet data from a *source* and lands
it in a *sink* (warehouse). Both sides are swappable behind ABCs so that
changing the upstream system or the destination DB is a config change, not a
rewrite:

    Source (sources/)            Pipeline (pipeline.py)      Sink (sinks/)
    -----------------            ----------------------      -------------
    IcebergSource   (live)  ─┐                            ┌─ PostgresSink (Neon)  ← now
    SampleFileSource (xlsx) ─┼─►  per-table read → write  ┤
    RestApiSource  (future) ─┘    + incremental watermark └─ MySQLSink   (future)
                                  + idempotent upsert
                                  + run audit + profiling

Entry point:  python -m ingestion --help
"""

from ingestion.config import IngestionConfig, load_config

__all__ = ["IngestionConfig", "load_config"]
