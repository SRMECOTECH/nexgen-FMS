"""Sink ABC. A sink ensures schema exists and writes a DataFrame for one table."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Sink(ABC):
    name: str = "base"

    @abstractmethod
    def ensure_schemas(self) -> None:
        """Create the target schema(s) if they don't exist."""

    @abstractmethod
    def write(
        self,
        table: str,
        df: pd.DataFrame,
        keys: list[str],
        mode: str,          # "upsert" | "full"
        source: str,
        run_id: str,
    ) -> int:
        """Write df into `table`. Returns rows written. Adds _source/_run_id/
        _ingested_at metadata. 'upsert' dedupes on `keys`; 'full' truncates first."""

    @abstractmethod
    def record_run(self, row: dict) -> None:
        """Append one audit row to meta.ingestion_runs."""

    @abstractmethod
    def write_meta(self, table: str, df: pd.DataFrame) -> None:
        """Append a DataFrame to a table in the meta schema (auto-created)."""
