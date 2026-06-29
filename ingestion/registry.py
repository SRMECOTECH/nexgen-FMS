"""
Table registry — the one place that declares *what* we ingest and *how*.

Each TableSpec maps a logical table name to:
  - its Iceberg namespace + table (for the live source),
  - its natural key (for idempotent upserts — re-runs don't duplicate),
  - its watermark column (for incremental pulls — "give me rows since T").

Natural keys / watermarks were chosen from the columns that are actually
populated in the data (see docs/DATA_REALITY.md). Where a reliable key/ts is
missing, we leave it empty and the pipeline falls back to full reload.
Add a row here to onboard a new table — no other code changes needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableSpec:
    logical: str                       # our canonical name + sink table name
    namespace: str                     # iceberg namespace (telemetry, silver, ...)
    source_table: str                  # table name within that namespace
    natural_key: tuple[str, ...] = ()  # () -> no upsert key (full reload only)
    watermark: str | None = None       # ts column for incremental, or None

    @property
    def fqn(self) -> str:
        """Fully-qualified Iceberg name, e.g. 'telemetry.gps_events'."""
        return f"{self.namespace}.{self.source_table}"


REGISTRY: dict[str, TableSpec] = {
    "fact_trips": TableSpec(
        "fact_trips", "telemetry", "fact_trips",
        natural_key=("trip_no",), watermark="ingested_at",
    ),
    "fact_trip_legs": TableSpec(
        "fact_trip_legs", "telemetry", "fact_trip_legs",
        natural_key=("trip_no", "leg_seq"), watermark=None,
    ),
    "gps_events": TableSpec(
        "gps_events", "telemetry", "gps_events",
        natural_key=("_event_id",), watermark="gps_timestamp",
    ),
    "gps_telemetry_events": TableSpec(
        "gps_telemetry_events", "telemetry", "gps_telemetry_events",
        natural_key=("vehicle_id", "gps_timestamp", "device_id"),
        watermark="gps_timestamp",
    ),
    # Raw device GPS feed (data/gpsfinal_*.xlsx), normalised by lakehouse.gps_feed.
    # Ingested via the 'gps_excel' source. ping_id = device_id|gps_ts is unique,
    # so re-running the upload upserts in place instead of duplicating.
    "gps_feed": TableSpec(
        "gps_feed", "telemetry", "gps_feed",
        natural_key=("ping_id",), watermark="gps_ts",
    ),
}

DEFAULT_TABLES: tuple[str, ...] = tuple(REGISTRY.keys())

# reverse lookup so a fully-qualified 'telemetry.gps_events' maps back to its spec
BY_FQN: dict[str, TableSpec] = {spec.fqn: spec for spec in REGISTRY.values()}


def resolve_name(name: str) -> tuple[str, str, tuple[str, ...]]:
    """Map a source-provided table name (logical OR 'namespace.table') to
    (sink_table, source_ref, natural_key).

    Known tables keep their declared natural key (→ upsert). Unknown ones
    discovered live get a SQL-safe sink name and no key (→ full reload), so
    'extract everything' works even for tables we haven't catalogued yet.
    """
    spec = REGISTRY.get(name) or BY_FQN.get(name)
    if spec:
        return spec.logical, spec.logical, spec.natural_key
    sink_table = name.replace(".", "__")  # 'silver.fact_x' -> 'silver__fact_x'
    return sink_table, name, ()


def resolve(tables: list[str] | None) -> list[TableSpec]:
    """Return TableSpecs for the requested logical names (all if None)."""
    names = tables or list(DEFAULT_TABLES)
    missing = [n for n in names if n not in REGISTRY]
    if missing:
        raise KeyError(f"Unknown table(s) {missing}. Known: {list(REGISTRY)}")
    return [REGISTRY[n] for n in names]
