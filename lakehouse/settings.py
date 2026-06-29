"""
Centralized config for lakehouse clients.

All connection details come from environment variables (.env). The defaults
keep the stack in MOCK_MODE so you can run the app end-to-end with no
external dependencies. Flip USE_MOCK_DATA=false in .env to hit the real
lakehouse once you have credentials.
"""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class LakehouseSettings:
    # Global switch — when True, every client returns mock_data instead of hitting the network
    use_mock_data: bool = True

    # neXgen-Lakehouse base URL (the UI you saw at port 5173)
    lakehouse_base_url: str = "http://98.70.24.178:5173"

    # PyIceberg / REST catalog
    iceberg_catalog_uri: str = "http://98.70.24.178:8181"   # TODO confirm actual REST catalog port
    iceberg_warehouse: str = "s3://nexgen-warehouse"        # TODO confirm bucket name
    iceberg_namespace: str = "telemetry"
    iceberg_token: str = ""                                 # JWT issued by data-catalog "consumer registration"

    # S3 / MinIO (Iceberg storage layer)
    s3_endpoint: str = "http://98.70.24.178:9000"           # TODO confirm MinIO port
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"

    # ClickHouse gateway (low-latency SQL)
    clickhouse_host: str = "98.70.24.178"
    clickhouse_port: int = 8123                             # HTTP interface
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "telemetry"

    # Trino proxy (fallback for SQL via JWT)
    trino_host: str = "98.70.24.178"
    trino_port: int = 8080
    trino_token: str = ""

    # Disable all Iceberg/MinIO catalog calls — no network attempts, no logs.
    # When True, ``PyIcebergClient`` raises on use and ``get_mock_table`` skips
    # its Iceberg-fallback step. Auto-true when no S3/catalog creds are set.
    disable_iceberg: bool = True


@lru_cache(maxsize=1)
def get_settings() -> LakehouseSettings:
    """Read env vars once per process. Anything missing falls back to the
    dataclass default — most of which trigger MOCK_MODE."""
    return LakehouseSettings(
        use_mock_data=os.getenv("USE_MOCK_DATA", "true").lower() == "true",
        lakehouse_base_url=os.getenv("LAKEHOUSE_BASE_URL", "http://98.70.24.178:5173"),
        iceberg_catalog_uri=os.getenv("ICEBERG_CATALOG_URI", "http://98.70.24.178:8181"),
        iceberg_warehouse=os.getenv("ICEBERG_WAREHOUSE", "s3://nexgen-warehouse"),
        iceberg_namespace=os.getenv("ICEBERG_NAMESPACE", "telemetry"),
        iceberg_token=os.getenv("ICEBERG_TOKEN", ""),
        s3_endpoint=os.getenv("S3_ENDPOINT", "http://98.70.24.178:9000"),
        s3_access_key=os.getenv("S3_ACCESS_KEY", ""),
        s3_secret_key=os.getenv("S3_SECRET_KEY", ""),
        s3_region=os.getenv("S3_REGION", "us-east-1"),
        clickhouse_host=os.getenv("CLICKHOUSE_HOST", "98.70.24.178"),
        clickhouse_port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        clickhouse_user=os.getenv("CLICKHOUSE_USER", "default"),
        clickhouse_password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        clickhouse_database=os.getenv("CLICKHOUSE_DATABASE", "telemetry"),
        trino_host=os.getenv("TRINO_HOST", "98.70.24.178"),
        trino_port=int(os.getenv("TRINO_PORT", "8080")),
        trino_token=os.getenv("TRINO_TOKEN", ""),
        disable_iceberg=_resolve_disable_iceberg(),
    )


def _resolve_disable_iceberg() -> bool:
    """Disable Iceberg when explicitly toggled OR when no creds are present
    (the default situation — saves a doomed connection to an unreachable IP)."""
    explicit = os.getenv("DISABLE_ICEBERG")
    if explicit is not None:
        return explicit.lower() in ("1", "true", "yes", "on")
    # Auto-detect: no S3 access key + no Iceberg token => nothing to connect to.
    return not (os.getenv("S3_ACCESS_KEY") or os.getenv("ICEBERG_TOKEN"))
