"""
Single source of truth for the route-intelligence cost model + recommendation
thresholds — the numbers shown in the "Critical action items" cards.

Everything here used to be hardcoded in ``analyzers.py`` (fuel price, km/l,
driver wage) and buried as magic numbers inside ``cost_savings_opportunities``
(the >2h idle trigger, the <40 km/h speed trigger, the flat ₹15k peak-hour
figure, the ×30 monthly multiplier). They are now read from a JSON file so the
UI can edit them live via ``GET/PUT /api/v1/route-intel/cost-config`` — no code
change, no restart, applied on the next analysis run.

The JSON file is created on first read with the defaults below. Any key missing
from the file falls back to its default, so partial files are safe.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# config/route_intel_costs.json at the repo root (…/nextGen-FMS/config/…)
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "route_intel_costs.json"
_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Defaults — match the historical hardcoded values so behaviour is unchanged
# until someone edits them.
# ---------------------------------------------------------------------------
DEFAULTS: Dict[str, Any] = {
    # --- cost model (was CostParams in analyzers.py) ---
    "fuel_price_per_liter": 100.0,      # ₹/L
    "fuel_efficiency_kmpl": 4.0,        # km/L
    "driver_wage_per_hour": 150.0,      # ₹/h
    "idle_fuel_consumption_lph": 1.5,   # L/h burned while idling
    "maintenance_per_km": 0.0,          # ₹/km maintenance (tyres, service, wear)
    "toll_per_trip": 0.0,               # ₹/trip toll estimate

    # --- monthly projection ---
    "trips_per_month": 30,              # the "×30" that turns per-trip → per-month

    # --- Idle Time Reduction (HIGH) trigger + math ---
    "idle_hours_trigger": 2.0,          # fire the card when stopped_hours exceeds this
    "idle_savings_pct": 0.30,           # assumed % of idle waste that is recoverable

    # --- Route Optimization (MEDIUM) trigger + math ---
    "speed_target_kmph": 40.0,          # fire when avg moving speed is below this
    "route_opt_time_saved_pct": 0.15,   # assumed % of moving time saved by rerouting

    # --- Peak Hour Avoidance (MEDIUM) trigger + math ---
    "peak_hour_start": 8,               # peak window start hour (inclusive)
    "peak_hour_end": 10,                # peak window end hour (inclusive)
    "peak_share_trigger": 0.30,         # fire when >this share of windows are in peak
    "peak_per_trip_savings_inr": 500.0, # assumed ₹/trip saved by shifting off-peak
    "peak_monthly_savings_inr": 15000.0,
}

_NUMERIC_KEYS = set(DEFAULTS.keys())


def load() -> Dict[str, Any]:
    """Return the live config (defaults merged with the on-disk overrides)."""
    cfg = dict(DEFAULTS)
    try:
        if _CONFIG_PATH.exists():
            with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                cfg.update({k: v for k, v in stored.items() if k in _NUMERIC_KEYS})
    except Exception as exc:  # noqa: BLE001 — never let a bad file break analysis
        logger.warning("cost_config: could not read %s (%s) — using defaults", _CONFIG_PATH, exc)
    return cfg


def save(partial: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ``partial`` into the stored config, write it, and return the result.

    Only known numeric keys are accepted; unknown keys are ignored and non-
    numeric values raise ``ValueError`` so the UI gets a clear 400.
    """
    clean: Dict[str, Any] = {}
    for k, v in (partial or {}).items():
        if k not in _NUMERIC_KEYS:
            continue
        try:
            clean[k] = float(v) if not isinstance(v, bool) else v
        except (TypeError, ValueError):
            raise ValueError(f"'{k}' must be a number, got {v!r}")
    # a couple of keys are logically ints
    for int_key in ("peak_hour_start", "peak_hour_end", "trips_per_month"):
        if int_key in clean:
            clean[int_key] = int(clean[int_key])

    with _LOCK:
        current = load()
        current.update(clean)
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _CONFIG_PATH.open("w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=2)
    logger.info("cost_config: saved %d override(s) → %s", len(clean), _CONFIG_PATH)
    return current


def reset() -> Dict[str, Any]:
    """Delete overrides and fall back to DEFAULTS."""
    with _LOCK:
        if _CONFIG_PATH.exists():
            _CONFIG_PATH.unlink()
    return dict(DEFAULTS)
