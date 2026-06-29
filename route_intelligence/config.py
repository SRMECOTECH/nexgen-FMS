"""
Centralised config loader. Reads ``config/route_intel.yaml`` once, exposes
typed accessors so other modules don't need to know the file format.

Override individual values from env vars when convenient (no need to edit YAML
for a one-off port change). Convention: ``RI_<section>_<key>=value`` —
e.g. ``RI_STREAMLIT_PORT=8888`` overrides ``streamlit.port``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML is required — pip install pyyaml") from exc


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "route_intel.yaml"


def _env_override(section: str, key: str) -> Optional[str]:
    var = f"RI_{section.upper()}_{key.upper()}"
    return os.environ.get(var)


def _coerce(default: Any, raw: str) -> Any:
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


@lru_cache(maxsize=1)
def _load_raw() -> Dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get(section: str, key: str, default: Any = None) -> Any:
    """Look up ``section.key`` with env-var override and YAML fallback."""
    cfg = _load_raw()
    sec = cfg.get(section, {}) or {}
    val = sec.get(key, default)
    over = _env_override(section, key)
    if over is None:
        return val
    return _coerce(val if val is not None else default, over)


def section(name: str) -> Dict[str, Any]:
    return dict(_load_raw().get(name, {}) or {})


def path(key: str) -> Path:
    """Resolve a path from the ``paths:`` section relative to project root."""
    rel = get("paths", key, "")
    p = Path(rel)
    return p if p.is_absolute() else (_PROJECT_ROOT / p)


def project_root() -> Path:
    return _PROJECT_ROOT


def config_file() -> Path:
    return _CONFIG_PATH


# ---- convenience getters used widely ---------------------------------------
def streamlit_url() -> str:
    host = get("streamlit", "host", "127.0.0.1")
    port = int(get("streamlit", "port", 8501))
    return f"http://{host}:{port}"


def streamlit_port() -> int:
    return int(get("streamlit", "port", 8501))


def streamlit_app_file() -> Path:
    rel = get("streamlit", "app_file", "streamlit_app/app.py")
    p = Path(rel)
    return p if p.is_absolute() else (_PROJECT_ROOT / p)


def excel_required() -> List[str]:
    return list(get("excel", "required_columns", []) or [])


def excel_column_map() -> Dict[str, str]:
    return dict(get("excel", "column_map", {}) or {})


def excel_speed_cols() -> List[str]:
    return list(get("excel", "speed_columns", ["i_corrt_speed", "i_speed"]) or [])


def excel_odo_col() -> str:
    return get("excel", "odometer_column", "i_distance")


def excel_odo_units() -> str:
    return get("excel", "odometer_units", "meters")


def excel_odo_clip_km() -> float:
    return float(get("excel", "odometer_per_row_clip_max_km", 10))


def excel_date_format() -> str:
    return get("excel", "date_format", "%d-%b-%y %H:%M:%S")


def trip_detection_params() -> Dict[str, float]:
    s = section("trip_detection")
    return {
        "stop_min_minutes": float(s.get("stop_min_minutes", 30)),
        "min_distance_km": float(s.get("min_trip_distance_km", 1.0)),
        "min_duration_min": float(s.get("min_trip_duration_min", 5.0)),
    }


def cost_defaults() -> Dict[str, float]:
    s = section("cost")
    return {
        "fuel_price_per_liter": float(s.get("fuel_price_per_liter", 100.0)),
        "fuel_efficiency_kmpl": float(s.get("fuel_efficiency_kmpl", 4.0)),
        "driver_wage_per_hour": float(s.get("driver_wage_per_hour", 150.0)),
        "idle_fuel_consumption_lph": float(s.get("idle_fuel_consumption_lph", 1.5)),
    }


def aggregation_choices() -> List[str]:
    return list(get("aggregation", "choices", ["15min", "30min", "1H", "2H"]))


def default_window() -> str:
    return get("aggregation", "default_window", "30min")
