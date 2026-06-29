"""
CLI for the ingestion pipeline.

Examples (run from project root with the venv active):

    # land everything from the configured source (INGEST_SOURCE in .env)
    python -m ingestion

    # explicitly use the offline sample source, full reload
    python -m ingestion --source sample --mode full

    # live lakehouse (open the SSH tunnel first), only GPS, last 24h
    python -m ingestion --source iceberg --tables gps_events --since-hours 24

    # just show what the source exposes
    python -m ingestion --list
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys

from ingestion.config import load_config
from ingestion.registry import DEFAULT_TABLES


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m ingestion",
                                description="Pull source data into the warehouse sink.")
    p.add_argument("--source", choices=["sample", "iceberg", "gps_excel"],
                   help="Override INGEST_SOURCE for this run.")
    p.add_argument("--tables", nargs="*", default=None,
                   help=f"Logical tables (default: registry). Known: {', '.join(DEFAULT_TABLES)}")
    p.add_argument("--all", action="store_true",
                   help="DISCOVER and extract EVERY table the source exposes "
                        "(incl. uncatalogued, e.g. silver.*). Defaults to --mode full.")
    p.add_argument("--mode", choices=["upsert", "full"], default="upsert",
                   help="upsert (dedupe on natural key) or full (truncate+load).")
    p.add_argument("--limit", type=int, default=None, help="Cap rows per table.")
    p.add_argument("--since-hours", type=float, default=None,
                   help="Incremental: only rows newer than now-N hours (needs watermark).")
    p.add_argument("--list", action="store_true", help="List source tables and exit.")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    cfg = load_config()
    if args.source:
        cfg = dataclasses.replace(cfg, source=args.source)

    if args.list:
        from ingestion.sources import make_source
        src = make_source(cfg)
        print(f"source = {src.name}")
        for t in src.list_tables():
            print("  ", t)
        return 0

    if args.all:
        from ingestion.pipeline import run_all
        # --all is a whole-warehouse snapshot: default to full reload
        mode = args.mode if "--mode" in (argv or sys.argv[1:]) else "full"
        results = run_all(mode=mode, limit=args.limit, since_hours=args.since_hours, cfg=cfg)
    else:
        from ingestion.pipeline import run
        results = run(tables=args.tables, mode=args.mode, limit=args.limit,
                      since_hours=args.since_hours, cfg=cfg)

    print("\n  table                     rows   status")
    print("  " + "-" * 44)
    for r in results:
        line = f"  {r.table:<24} {r.rows:>6}   {r.status}"
        if r.error:
            line += f"  ({r.error[:60]})"
        print(line)
    failed = [r for r in results if r.status != "ok"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
