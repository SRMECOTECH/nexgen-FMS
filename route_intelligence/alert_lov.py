"""
Parse and summarise the vendor ``s_alert_lov`` column from uploaded GPS Excels.

``s_alert_lov`` is a packed string of ``code:value`` pairs joined by ``#``, e.g.::

    1570:000#1140:12.87#1830:122#2000:k m translogistics pvt ltd

The numeric codes are vendor "list-of-values" alert/telemetry codes. There is
NO codebook in this repo, and the codes differ per device firmware, so this
module does two honest things:

  1. Parses the structure and counts how often each code fires, per device and
     per day — that is a real, dynamic "finding" (which signals are active, on
     which trucks, how loud).
  2. Looks up a human label for each code from a USER-EDITABLE map
     (``config/alert_lov_labels.json``, edited via the API). Unlabelled codes
     show as ``"code 1570"`` until you name them, so the page is useful
     immediately and gets richer as you fill in the map.

Everything is cached per (file, mtime) so re-reading many Excels on each Observe
load is cheap.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

_LABELS_PATH = Path(__file__).resolve().parent.parent / "config" / "alert_lov_labels.json"
_LOCK = threading.Lock()

# A few common-sense seeds; everything else is "code N" until the user labels it.
# Edit/extend freely via PUT /observe/alert-labels.
DEFAULT_LABELS: Dict[str, str] = {
    "1000": "Alert flag",
}

# per-file parse cache: path -> (mtime, stats)
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


# --------------------------------------------------------------------------- labels
def load_labels() -> Dict[str, str]:
    labels = dict(DEFAULT_LABELS)
    try:
        if _LABELS_PATH.exists():
            with _LABELS_PATH.open("r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                labels.update({str(k): str(v) for k, v in stored.items()})
    except Exception as exc:  # noqa: BLE001
        logger.warning("alert_lov: bad labels file (%s) — using defaults", exc)
    return labels


def save_labels(patch: Dict[str, Any]) -> Dict[str, str]:
    clean = {str(k): str(v) for k, v in (patch or {}).items() if str(v).strip()}
    with _LOCK:
        current = load_labels()
        current.update(clean)
        _LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LABELS_PATH.open("w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=2, ensure_ascii=False)
    return current


def label_for(code: str, labels: Dict[str, str] | None = None) -> str:
    labels = labels if labels is not None else load_labels()
    return labels.get(str(code)) or f"code {code}"


# --------------------------------------------------------------------------- parse
def parse_pairs(raw: str) -> Dict[str, str]:
    """``"1570:000#1140:12.87"`` -> ``{"1570": "000", "1140": "12.87"}``."""
    out: Dict[str, str] = {}
    if not raw:
        return out
    for part in str(raw).split("#"):
        if ":" in part:
            k, v = part.split(":", 1)
            k = k.strip()
            if k:
                out[k] = v.strip()
    return out


def _file_stats(path: str) -> Dict[str, Any]:
    """Parse one GPS Excel's alert columns. Cached by (path, mtime)."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {"n_rows": 0, "n_alert_rows": 0, "code_counts": {}, "code_samples": {}}
    cached = _CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]

    stats = {"n_rows": 0, "n_alert_rows": 0, "code_counts": {}, "code_samples": {}}
    try:
        df = pd.read_excel(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("alert_lov: cannot read %s (%s)", path, exc)
        return stats

    stats["n_rows"] = int(len(df))
    if "c_is_alert" in df.columns:
        stats["n_alert_rows"] = int(df["c_is_alert"].astype(str).str.upper().eq("Y").sum())
    counts: Dict[str, int] = {}
    samples: Dict[str, str] = {}
    if "s_alert_lov" in df.columns:
        for raw in df["s_alert_lov"].dropna().astype(str):
            for code, val in parse_pairs(raw).items():
                counts[code] = counts.get(code, 0) + 1
                samples.setdefault(code, val)
    stats["code_counts"] = counts
    stats["code_samples"] = samples

    _CACHE[path] = (mtime, stats)
    return stats


# --------------------------------------------------------------------------- aggregate
def build_findings(uploads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate alert findings across the given uploads.

    ``uploads`` items need: ``path`` (absolute), ``vehicle_id``, ``display_name``.
    Returns a payload with per-code findings (headline) each carrying the
    affected devices (drill-down), plus fleet totals.
    """
    labels = load_labels()
    total_rows = 0
    total_alert_rows = 0
    # code -> {count, devices: {display_name -> count}, sample}
    codes: Dict[str, Dict[str, Any]] = {}
    files_scanned = 0

    for up in uploads:
        path = up.get("path")
        if not path or not os.path.exists(path):
            continue
        st = _file_stats(path)
        if not st["n_rows"]:
            continue
        files_scanned += 1
        total_rows += st["n_rows"]
        total_alert_rows += st["n_alert_rows"]
        dev = up.get("display_name") or up.get("vehicle_id") or "unknown"
        for code, cnt in st["code_counts"].items():
            slot = codes.setdefault(code, {"count": 0, "devices": {}, "sample": st["code_samples"].get(code, "")})
            slot["count"] += cnt
            slot["devices"][dev] = slot["devices"].get(dev, 0) + cnt

    findings: List[Dict[str, Any]] = []
    for code, slot in codes.items():
        devices = [{"device": d, "count": c} for d, c in
                   sorted(slot["devices"].items(), key=lambda kv: kv[1], reverse=True)]
        findings.append({
            "code": code,
            "label": label_for(code, labels),
            "labelled": code in labels,
            "count": slot["count"],
            "n_devices": len(slot["devices"]),
            "sample_value": slot["sample"],
            "devices": devices,
        })
    findings.sort(key=lambda f: f["count"], reverse=True)

    return {
        "totals": {
            "files_scanned": files_scanned,
            "gps_rows": total_rows,
            "alert_rows": total_alert_rows,
            "alert_row_pct": round(total_alert_rows / total_rows * 100, 1) if total_rows else 0.0,
            "distinct_codes": len(findings),
        },
        "findings": findings,
    }
