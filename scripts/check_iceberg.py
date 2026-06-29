#!/usr/bin/env python
"""
Pull the last day of data from an Iceberg table whose Parquet files live on MinIO.

Connects to the same REST catalog (datalake-iceberg-rest) and MinIO that the
ingestion service uses, mirroring the connection convention in
ingestion_service/sinks/iceberg_sink.py.

Run from the HOST (not inside a container). Defaults point at the eTrans
server's published ports:
  - iceberg-rest -> http://98.70.24.178:8181
  - minio        -> http://98.70.24.178:9000

Every connection knob is overridable via env var or CLI flag. Env var names
match configs/ingestion.env so you can `source` that file if you prefer.

Examples:
  # Default table (telemetry.gps_events), last 24h, print summary
  python infra/scripts/iceberg_pull_last_day.py

  # A different table + timestamp column, write the slice to Parquet
  python infra/scripts/iceberg_pull_last_day.py \
      --table silver.fact_vehicle_alert --ts-column alert_ts \
      --out alerts_last_day.parquet

  # Point at the VM instead of localhost
  python infra/scripts/iceberg_pull_last_day.py \
      --rest-uri http://10.3.3.131:8181 --s3-endpoint http://10.3.3.131:9000
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

from pyiceberg.catalog import load_catalog
from pyiceberg.expressions import GreaterThanOrEqual


def _env(*names, default=None):
    """First non-empty value among the given env var names."""
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


def _bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def build_catalog(args):
    """Load the REST catalog with S3 (MinIO) file IO configured.

    The S3 settings tell pyiceberg how to reach MinIO directly for reading
    the Parquet data files; without them it would try to honor the catalog's
    own in-network endpoint (http://minio:9000), which the host can't resolve.
    """
    return load_catalog(
        "rest_catalog",
        **{
            "type": "rest",
            "uri": args.rest_uri,
            "s3.endpoint": args.s3_endpoint,
            "s3.access-key-id": args.s3_access_key,
            "s3.secret-access-key": args.s3_secret_key,
            "s3.region": args.s3_region,
            "s3.path-style-access": "true" if args.s3_path_style else "false",
            "s3.signer": "S3V4",
            "s3.ssl-enabled": "true" if args.s3_secure else "false",
        },
    )


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Pull the last day of data from an Iceberg table on MinIO."
    )
    p.add_argument(
        "--table",
        default=_env("ICEBERG_TABLE", default="telemetry.gps_events"),
        help="Fully-qualified Iceberg table (namespace.table). Default: telemetry.gps_events",
    )
    p.add_argument(
        "--ts-column",
        default=_env("ICEBERG_TS_COLUMN", default="gps_timestamp"),
        help="Timestamp column to window on. Default: gps_timestamp",
    )
    p.add_argument(
        "--hours",
        type=float,
        default=float(_env("ICEBERG_WINDOW_HOURS", default="24")),
        help="Look-back window in hours. Default: 24",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Optional path to write the result (.parquet or .csv). "
        "If omitted, prints a summary + a few sample rows.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Sample rows to print when --out is not given. Default: 10",
    )

    # Connection knobs (host-mapped ports by default).
    p.add_argument(
        "--rest-uri",
        default=_env("ICEBERG_REST_URI", default="http://98.70.24.178:8181"),
    )
    p.add_argument(
        "--s3-endpoint",
        default=_env(
            "ICEBERG_S3_ENDPOINT", "MINIO_ENDPOINT", default="http://98.70.24.178:9000"
        ),
    )
    p.add_argument(
        "--s3-access-key",
        default=_env("ICEBERG_S3_ACCESS_KEY", "MINIO_ACCESS_KEY", default="admin"),
    )
    p.add_argument(
        "--s3-secret-key",
        default=_env(
            "ICEBERG_S3_SECRET_KEY", "MINIO_SECRET_KEY", default="password123"
        ),
    )
    p.add_argument(
        "--s3-region",
        default=_env("ICEBERG_S3_REGION", "MINIO_REGION", default="us-east-1"),
    )
    p.add_argument(
        "--s3-path-style",
        dest="s3_path_style",
        action="store_true",
        default=_bool(
            _env("ICEBERG_S3_PATH_STYLE_ACCESS", "MINIO_PATH_STYLE_ACCESS"),
            default=True,
        ),
        help="Use path-style S3 addressing (required by MinIO). Default: on.",
    )
    p.add_argument(
        "--s3-secure",
        dest="s3_secure",
        action="store_true",
        default=_bool(_env("ICEBERG_S3_SECURE", "MINIO_SECURE"), default=False),
        help="Use TLS for the S3 endpoint. Default: off.",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # The table partitions/stores gps_timestamp as naive UTC (see iceberg_sink),
    # so build a naive-UTC lower bound to match the column's wall-clock values.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    cutoff_naive = cutoff.replace(tzinfo=None)
    # pyiceberg compares timestamps via ISO-8601 string literals.
    cutoff_literal = cutoff_naive.isoformat(timespec="microseconds")

    print(f"[iceberg] catalog : {args.rest_uri}")
    print(f"[iceberg] s3      : {args.s3_endpoint}")
    print(f"[iceberg] table   : {args.table}")
    print(f"[iceberg] window  : {args.ts_column} >= {cutoff_literal} (UTC, last {args.hours}h)")

    catalog = build_catalog(args)
    table = catalog.load_table(args.table)

    row_filter = GreaterThanOrEqual(args.ts_column, cutoff_literal)
    # to_arrow() reads only the Parquet files/row-groups whose stats overlap the
    # window (partition + column-stats pruning), so we don't scan the whole table.
    scan = table.scan(row_filter=row_filter)
    arrow_table = scan.to_arrow()

    print(f"[iceberg] rows    : {arrow_table.num_rows}")

    if args.out:
        out = args.out
        if out.lower().endswith(".csv"):
            import pyarrow.csv as pacsv

            pacsv.write_csv(arrow_table, out)
        else:
            import pyarrow.parquet as pq

            pq.write_table(arrow_table, out)
        print(f"[iceberg] wrote   : {out}")
    else:
        if arrow_table.num_rows == 0:
            print("[iceberg] (no rows in window)")
        else:
            head = arrow_table.slice(0, max(0, args.limit)).to_pylist()
            print(f"[iceberg] sample  : first {len(head)} row(s)")
            for i, row in enumerate(head, 1):
                print(f"  {i:>3}. {row}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
