"""
Centralised, env-driven config for the ingestion pipeline.

Loads .env once (same file the backend uses) and exposes a frozen dataclass.
Source/sink selection and every connection knob is overridable via env var so
nothing secret lives in code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass  # rely on real env vars


def _env(*names: str, default: str | None = None) -> str | None:
    """First non-empty value among the given env var names (mirrors the
    convention in infra/scripts/iceberg_pull_last_day.py)."""
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


@dataclass(frozen=True)
class IngestionConfig:
    # --- sink (warehouse) ---
    warehouse_url: str
    raw_schema: str

    # --- source selection ---
    source: str            # "sample" | "iceberg"

    # --- live Iceberg source knobs ---
    iceberg_rest_uri: str
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str

    @property
    def has_warehouse_url(self) -> bool:
        return bool(self.warehouse_url)


@lru_cache(maxsize=1)
def load_config() -> IngestionConfig:
    _load_dotenv()
    return IngestionConfig(
        warehouse_url=_env("WAREHOUSE_URL", "NEON_DATABASE_URL", default="") or "",
        raw_schema=_env("WAREHOUSE_RAW_SCHEMA", default="raw"),
        source=(_env("INGEST_SOURCE", default="sample") or "sample").lower(),
        # env names match both our .env and the user's pull script
        iceberg_rest_uri=_env("ICEBERG_REST_URI", "ICEBERG_CATALOG_URI",
                              default="http://localhost:8181"),
        s3_endpoint=_env("ICEBERG_S3_ENDPOINT", "S3_ENDPOINT", "MINIO_ENDPOINT",
                         default="http://localhost:9000"),
        s3_access_key=_env("ICEBERG_S3_ACCESS_KEY", "S3_ACCESS_KEY", "MINIO_ACCESS_KEY",
                           default="admin"),
        s3_secret_key=_env("ICEBERG_S3_SECRET_KEY", "S3_SECRET_KEY", "MINIO_SECRET_KEY",
                           default="password123"),
        s3_region=_env("ICEBERG_S3_REGION", "S3_REGION", "MINIO_REGION",
                       default="us-east-1"),
    )
