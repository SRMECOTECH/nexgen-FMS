"""
Pipeline orchestrator: source -> sink, per table, with audit + profiling.

Resilient by table: one table failing doesn't abort the rest; each outcome is
written to meta.ingestion_runs. Two entry points:

  run(tables=...)  - ingest specific catalogued tables (default: the registry).
  run_all(...)     - DISCOVER every table the source exposes and extract them
                     all (catalogued or not). This is "pull everything".
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ingestion.config import IngestionConfig, load_config
from ingestion.profile import profile_df
from ingestion.registry import resolve, resolve_name
from ingestion.sinks import make_sink
from ingestion.sources import make_source

logger = logging.getLogger(__name__)


@dataclass
class TableResult:
    table: str
    rows: int
    status: str
    error: str | None = None


# (sink_table, source_ref, natural_key)
Target = tuple[str, str, tuple[str, ...]]


def _execute(targets: list[Target], mode: str, limit, since, cfg) -> list[TableResult]:
    source = make_source(cfg)
    sink = make_sink(cfg)
    sink.ensure_schemas()
    run_id = uuid.uuid4().hex[:12]

    logger.info("=== ingestion run %s | source=%s sink=%s mode=%s targets=%d ===",
                run_id, source.name, sink.name, mode, len(targets))

    results: list[TableResult] = []
    for sink_table, source_ref, keys in targets:
        started = datetime.now(timezone.utc)
        try:
            df = source.read_table(source_ref, since=since, limit=limit)
            rows = sink.write(sink_table, df, list(keys), mode, source.name, run_id)
            if df is not None and not df.empty:
                sink.write_meta("data_quality", profile_df(sink_table, df, run_id))
            res = TableResult(sink_table, rows, "ok")
        except Exception as exc:  # keep going; record the failure
            logger.exception("table %s FAILED", sink_table)
            res = TableResult(sink_table, 0, "error", str(exc)[:500])
        results.append(res)
        sink.record_run({
            "run_id": run_id, "table_name": sink_table, "source": source.name,
            "mode": mode, "rows_written": res.rows, "status": res.status,
            "error": res.error, "started_at": started,
            "finished_at": datetime.now(timezone.utc),
        })

    ok = sum(1 for r in results if r.status == "ok")
    total = sum(r.rows for r in results)
    logger.info("=== run %s done: %d/%d tables ok, %d rows ===",
                run_id, ok, len(results), total)
    return results


def _since(since_hours: float | None) -> datetime | None:
    return (datetime.now(timezone.utc) - timedelta(hours=since_hours)) if since_hours else None


def run(tables=None, mode="upsert", limit=None, since_hours=None, cfg=None) -> list[TableResult]:
    """Ingest catalogued tables (default: the whole registry)."""
    cfg = cfg or load_config()
    targets = [(s.logical, s.logical, s.natural_key) for s in resolve(tables)]
    return _execute(targets, mode, limit, _since(since_hours), cfg)


def run_all(mode="full", limit=None, since_hours=None, cfg=None) -> list[TableResult]:
    """Discover EVERY table the source exposes and extract them all.

    Catalogued tables keep their natural key (upsert-capable); unknown ones are
    landed under a SQL-safe name (e.g. silver.fact_x -> raw.silver__fact_x) with
    a full reload. Default mode is 'full' so this is a clean whole-warehouse copy.
    """
    cfg = cfg or load_config()
    source = make_source(cfg)
    names = source.list_tables()
    logger.info("run_all: source exposes %d tables: %s", len(names), names)
    targets = [resolve_name(n) for n in names]
    return _execute(targets, mode, limit, _since(since_hours), cfg)
