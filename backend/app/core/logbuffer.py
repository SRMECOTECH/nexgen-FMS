"""
In-memory ring buffer of REAL backend logs — powers the System → Logs page.

A ``logging.Handler`` attached to the root logger keeps the most recent
records (default 3000) in a thread-safe deque, including full exception
tracebacks. The UI polls GET /api/v1/system/logs to render them, so any
startup / DB / ingestion failure is visible in the browser without ever
opening a terminal.

Nothing is written to disk and the buffer is bounded, so memory stays flat.
"""

from __future__ import annotations

import logging
import threading
import traceback
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

_MAX_RECORDS = 3000

_lock = threading.Lock()
_buffer: deque = deque(maxlen=_MAX_RECORDS)
_counter = 0  # monotonic id so the UI can poll incrementally


class BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        global _counter
        try:
            exc = None
            if record.exc_info and record.exc_info[0] is not None:
                exc = "".join(traceback.format_exception(*record.exc_info))
            entry = {
                "ts": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "service": record.name,
                "message": record.getMessage(),
                "exc": exc,
            }
            with _lock:
                _counter += 1
                entry["id"] = _counter
                _buffer.append(entry)
        except Exception:  # noqa: BLE001 — a broken log record must never crash the app
            pass


def install(level: int = logging.INFO) -> None:
    """Attach the buffer handler to the root logger (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(h, BufferHandler) for h in root.handlers):
        return
    h = BufferHandler(level=level)
    root.addHandler(h)


_LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "WARN": 30, "ERROR": 40, "CRITICAL": 50}


def get_logs(limit: int = 200, level: Optional[str] = None,
             search: Optional[str] = None, after_id: int = 0) -> Dict[str, Any]:
    """Newest-first slice of the buffer with optional min-level / text filters."""
    min_lvl = _LEVEL_ORDER.get((level or "").upper(), 0)
    q = (search or "").lower()
    with _lock:
        rows: List[Dict[str, Any]] = list(_buffer)
        latest_id = _counter
    out = []
    counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
    for r in rows:
        lvl = r["level"] if r["level"] in counts else "INFO"
        counts[lvl] += 1
        if r["id"] <= after_id:
            continue
        if min_lvl and _LEVEL_ORDER.get(r["level"], 20) < min_lvl:
            continue
        if q and q not in f"{r['service']} {r['message']} {r['exc'] or ''}".lower():
            continue
        out.append(r)
    out = out[-limit:]
    out.reverse()  # newest first
    return {"logs": out, "latest_id": latest_id, "counts": counts, "buffered": len(rows)}
