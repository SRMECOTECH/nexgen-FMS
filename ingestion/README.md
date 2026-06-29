# ingestion/ — source → warehouse pipeline

Pulls fleet data from a **source** and lands it in a **sink** (warehouse).
Both sides are swappable behind ABCs, so changing the upstream system or the
destination database is a config change, not a rewrite.

```
Source (sources/)            Pipeline (pipeline.py)      Sink (sinks/)
-----------------            ----------------------      -------------
IcebergSource   (live)  ─┐                            ┌─ PostgresSink (Neon)  ← now
SampleFileSource (xlsx) ─┼─►  per-table read → write  ┤
RestApiSource  (future) ─┘    + incremental watermark └─ MySQLSink   (future)
                              + idempotent upsert
                              + run audit + profiling
```

## Quickstart

```powershell
Set-Location "C:\Users\Sanjoy Chattopadhyay\PycharmProjects\nextGen-FMS"
.\.venv\Scripts\Activate.ps1

# Offline, today — land the sample data into Neon (proves the whole path)
python -m ingestion --source sample --mode full

# What does a source expose?
python -m ingestion --source sample --list
```

## Going live (neXgen-Lakehouse over SSH tunnel)

The Iceberg REST catalog (`:8181`) is **not** reachable from a laptop — it's
only published on the server's network. Bridge it with a tunnel, then the same
pipeline pulls live:

```powershell
# Terminal 1 — keep this open (uses your SSH creds; nothing is stored)
ssh -N -L 8181:localhost:8181 -L 9000:localhost:9000 user@98.70.24.178

# Terminal 2 — .env already points ICEBERG_REST_URI/S3 at localhost
python -m ingestion --source iceberg --list                     # what's actually there?
python -m ingestion --source iceberg --tables gps_events --limit 1000   # smoke test first
python -m ingestion --source iceberg --all                      # EXTRACT EVERYTHING
```

### Extract everything (`--all`)

`--all` discovers every namespace/table the catalog exposes (incl. uncatalogued
ones like `silver.*`), and full-loads each into `raw.*` — catalogued tables
keep their natural key, unknown ones land as `raw.<namespace>__<table>`.

⚠️ **Volume / Neon free tier (~0.5 GB):** the GPS tables can be millions of
rows/day. Do a bounded run first to gauge size, then go full:

```powershell
python -m ingestion --source iceberg --all --since-hours 24      # last day of everything
python -m ingestion --source iceberg --tables gps_events --since-hours 6   # one table, 6h
```

`--since-hours N` does an incremental pull on tables that declare a watermark
column (see `registry.py`); upserts on the natural key make re-runs safe.

## Configuration (.env)

| var | meaning |
|---|---|
| `WAREHOUSE_URL` | SQLAlchemy URL of the sink. `postgresql+psycopg://…` now; `mysql+pymysql://…` later. |
| `WAREHOUSE_RAW_SCHEMA` | landing schema (default `raw`). |
| `INGEST_SOURCE` | `sample` or `iceberg`. |
| `ICEBERG_REST_URI` / `ICEBERG_S3_*` | live source knobs (localhost when tunnelled). |

## What lands where (in the sink)

- `raw.<table>` — one table per source table, columns auto-typed from the data,
  plus `_source`, `_run_id`, `_ingested_at` metadata.
- `meta.ingestion_runs` — one audit row per (table, run): rows written, status, error, timing.
- `meta.data_quality` — per-column null-rate / cardinality / `verdict`
  (DEAD / SPARSE / CONSTANT / USABLE). This is the discovery loop: query it to
  see which columns carry ML signal.

## Onboarding a new table

Add one `TableSpec` to `registry.py` (namespace, source table, natural key,
watermark). No other code changes.

## Adding a new sink (e.g. MySQL)

Subclass `sinks/base.Sink` mirroring `PostgresSink`; swap `ON CONFLICT … DO
UPDATE` for MySQL's `ON DUPLICATE KEY UPDATE`. Register its URL scheme in
`sinks/__init__.make_sink`. Pipeline code is untouched.
```
