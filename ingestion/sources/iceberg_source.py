"""
IcebergSource — live reads from the neXgen-Lakehouse REST catalog + MinIO.

Connection recipe is the proven one from infra/scripts/iceberg_pull_last_day.py
and lakehouse/pyiceberg_client.py: REST catalog + S3 FileIO with the S3V4
signer, ssl disabled and path-style addressing (required by MinIO).

NETWORK NOTE: the REST catalog (:8181) is not exposed publicly. From a laptop,
open an SSH tunnel first and point ICEBERG_REST_URI / ICEBERG_S3_ENDPOINT at
localhost:

    ssh -N -L 8181:localhost:8181 -L 9000:localhost:9000 user@98.70.24.178

pyiceberg + pyarrow are imported lazily so the package stays importable (and
the sample source keeps working) on machines without them installed.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from ingestion.config import IngestionConfig
from ingestion.registry import REGISTRY, TableSpec
from ingestion.sources.base import Source

logger = logging.getLogger(__name__)


class IcebergSource(Source):
    name = "iceberg_lakehouse"

    def __init__(self, cfg: IngestionConfig) -> None:
        self.cfg = cfg
        self._catalog = None  # lazy

    # ------------------------------------------------------------------
    def _get_catalog(self):
        if self._catalog is not None:
            return self._catalog
        try:
            from pyiceberg.catalog import load_catalog
        except ImportError as exc:
            raise RuntimeError(
                "pyiceberg not installed. `pip install 'pyiceberg[s3fs,pyarrow]'`."
            ) from exc

        c = self.cfg
        logger.info("IcebergSource catalog=%s s3=%s", c.iceberg_rest_uri, c.s3_endpoint)
        self._catalog = load_catalog(
            "rest_catalog",
            **{
                "type": "rest",
                "uri": c.iceberg_rest_uri,
                "s3.endpoint": c.s3_endpoint,
                "s3.access-key-id": c.s3_access_key,
                "s3.secret-access-key": c.s3_secret_key,
                "s3.region": c.s3_region,
                "s3.path-style-access": "true",
                "s3.signer": "S3V4",
                "s3.ssl-enabled": "false",
            },
        )
        return self._catalog

    # ------------------------------------------------------------------
    def list_tables(self) -> list[str]:
        cat = self._get_catalog()
        out: list[str] = []
        for ns in cat.list_namespaces():
            ns_str = ".".join(ns)
            for t in cat.list_tables(ns):
                out.append(f"{ns_str}.{t[-1]}")
        return out

    def read_table(
        self,
        logical: str,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        spec: TableSpec | None = REGISTRY.get(logical)
        fqn = spec.fqn if spec else logical
        cat = self._get_catalog()
        tbl = cat.load_table(fqn)

        row_filter = "true"
        if since is not None and spec and spec.watermark:
            from pyiceberg.expressions import GreaterThanOrEqual
            # tables store naive-UTC timestamps; pyiceberg compares via ISO literal
            cutoff = since.replace(tzinfo=None).isoformat(timespec="microseconds")
            row_filter = GreaterThanOrEqual(spec.watermark, cutoff)
            logger.info("IcebergSource %s where %s >= %s", fqn, spec.watermark, cutoff)

        scan = tbl.scan(row_filter=row_filter, limit=limit) if limit else tbl.scan(row_filter=row_filter)
        df = scan.to_arrow().to_pandas()
        logger.info("IcebergSource %s -> %d rows", fqn, len(df))
        return df
