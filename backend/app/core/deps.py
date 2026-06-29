"""
FastAPI dependency providers.

Replaces smart-truck's pymysql get_db with lakehouse clients. Each request
gets a thin wrapper around one of the three connectors — the client is
process-singleton, so this is cheap.
"""

from functools import lru_cache

from lakehouse import ClickHouseClient, DuckDBClient, PyIcebergClient


@lru_cache(maxsize=1)
def _clickhouse() -> ClickHouseClient:
    return ClickHouseClient()


@lru_cache(maxsize=1)
def _pyiceberg() -> PyIcebergClient:
    return PyIcebergClient()


@lru_cache(maxsize=1)
def _duckdb() -> DuckDBClient:
    return DuckDBClient()


def get_clickhouse() -> ClickHouseClient:
    """Inject ClickHouse for live dashboard / KPI endpoints."""
    return _clickhouse()


def get_pyiceberg() -> PyIcebergClient:
    """Inject PyIceberg for routes that need full-table scans (rare in API)."""
    return _pyiceberg()


def get_duckdb() -> DuckDBClient:
    """Inject DuckDB for ad-hoc / cross-table joins."""
    return _duckdb()
