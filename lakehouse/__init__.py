"""
nextGen-FMS lakehouse access layer.

Three clients, one for each workload:

    pyiceberg_client  -> ML training pipelines (batch reads, full table scans)
    clickhouse_client -> FastAPI serving (low-latency SQL for live dashboards)
    duckdb_client     -> Ad-hoc analytics / notebooks (in-process)

All three currently return mock data. Replace the TODO blocks with real
connection logic once credentials for the neXgen-Lakehouse are available.
"""

from lakehouse.settings import LakehouseSettings, get_settings
from lakehouse.pyiceberg_client import PyIcebergClient
from lakehouse.clickhouse_client import ClickHouseClient
from lakehouse.duckdb_client import DuckDBClient

__all__ = [
    "LakehouseSettings",
    "get_settings",
    "PyIcebergClient",
    "ClickHouseClient",
    "DuckDBClient",
]
