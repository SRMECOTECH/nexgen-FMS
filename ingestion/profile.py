"""
Lightweight data-quality profiler.

For every column of an ingested table, record null-rate, distinct count and
dtype. Persisted to meta.data_quality so "what can we actually extract from
this data?" is a live query that refreshes on each run — the programmatic
companion to docs/DATA_REALITY.md. This is the heart of the discovery/R&D
loop: columns at 100% null are dead features; columns with healthy fill +
cardinality are where the ML value is.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def profile_df(table: str, df: pd.DataFrame, run_id: str) -> pd.DataFrame:
    n = len(df)
    now = datetime.now(timezone.utc)
    rows = []
    for col in df.columns:
        null_pct = round(float(df[col].isna().mean()) * 100, 2) if n else 100.0
        try:
            distinct = int(df[col].nunique(dropna=True))
        except TypeError:  # unhashable cells (dicts/lists)
            distinct = int(df[col].astype(str).nunique(dropna=True))
        rows.append({
            "run_id": run_id,
            "table_name": table,
            "column_name": col,
            "dtype": str(df[col].dtype),
            "row_count": n,
            "null_pct": null_pct,
            "distinct_count": distinct,
            "verdict": _verdict(null_pct, distinct),
            "profiled_at": now,
        })
    return pd.DataFrame(rows)


def _verdict(null_pct: float, distinct: int) -> str:
    if null_pct >= 100.0:
        return "DEAD"          # 100% null — unusable
    if null_pct >= 90.0:
        return "SPARSE"        # mostly null
    if distinct <= 1:
        return "CONSTANT"      # no signal (e.g. delay_minutes always 1)
    return "USABLE"
