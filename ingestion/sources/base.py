"""Source ABC. A source knows how to list tables and read one into a DataFrame."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd


class Source(ABC):
    #: short identifier stored in the sink's _source column
    name: str = "base"

    @abstractmethod
    def list_tables(self) -> list[str]:
        """Logical table names this source can provide."""

    @abstractmethod
    def read_table(
        self,
        logical: str,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Read one logical table.

        Args:
            logical: registry name (e.g. 'gps_events').
            since:   if set and the table has a watermark column, return only
                     rows at/after this instant (incremental pull).
            limit:   cap rows (sampling / smoke tests).
        """
