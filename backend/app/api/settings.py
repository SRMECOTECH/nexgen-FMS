"""
Settings API — makes the app self-configuring from the UI.

Every tunable the app reads from .env is declared in ``CONFIG_REGISTRY`` below
with a label, description and grouping. The frontend Settings page renders the
registry, lets the user edit values, and saves them back:

  GET  /api/v1/settings/config      → registry + current values
  PUT  /api/v1/settings/config      → write updates to .env + live os.environ
  GET  /api/v1/settings/db/status   → is the warehouse reachable? which tables?
  POST /api/v1/settings/db/init     → create database + all tables (idempotent)

Saving updates BOTH the .env file (so a restart keeps the value) and
``os.environ`` (so most values apply immediately — anything env-read per
request). Keys flagged ``restart: true`` (ports, Vite vars) only take full
effect after a backend/frontend restart, and the UI says so.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)

# repo root: backend/app/api/settings.py → parents[3]
ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


# ---------------------------------------------------------------------------
# Registry — one entry per .env key the app reads. ``secret`` values render as
# password fields in the UI; ``restart`` marks keys that need a process restart.
# ---------------------------------------------------------------------------
def _k(key: str, label: str, desc: str, *, secret: bool = False,
       restart: bool = False, kind: str = "text",
       choices: List[str] | None = None) -> Dict[str, Any]:
    return {"key": key, "label": label, "description": desc,
            "secret": secret, "restart": restart, "kind": kind,
            "choices": choices}


CONFIG_REGISTRY: List[Dict[str, Any]] = [
    {
        "section": "Core — data source & warehouse",
        "hint": "Where data comes from and which database stores it.",
        "keys": [
            _k("WAREHOUSE_URL", "Warehouse database URL",
               "SQLAlchemy URL of the MySQL (or Postgres) warehouse. On MySQL the "
               "database is auto-created on init — only the server must exist. "
               "Example: mysql+pymysql://root:root@127.0.0.1:3306/nextgen_fms",
               secret=True),
            _k("USE_MOCK_DATA", "Use mock data",
               "true = serve in-memory demo fixtures (no DB needed); false = real data.",
               kind="bool"),
            _k("INGEST_SOURCE", "Ingestion source",
               "sample = Excel feeds in sample_data/ and data/ (works offline); "
               "iceberg = live lakehouse (needs the Iceberg block configured)."),
            _k("WAREHOUSE_RAW_SCHEMA", "Raw landing schema",
               "Logical schema name for raw landing tables."),
            _k("DISABLE_ICEBERG", "Disable Iceberg",
               "true = never attempt Iceberg/MinIO network calls.", kind="bool"),
        ],
    },
    {
        "section": "Ports & URLs",
        "hint": "Where each service listens. Changing these needs a restart.",
        "keys": [
            _k("FMS_BACKEND_HOST", "Backend host", "Bind address of the FastAPI backend.", restart=True),
            _k("FMS_BACKEND_PORT", "Backend port", "Port of the FastAPI backend (default 9001).", restart=True, kind="number"),
            _k("FMS_FRONTEND_PORT", "Frontend port", "Port of the Vite dev server (default 6173).", restart=True, kind="number"),
            _k("VITE_API_URL", "Frontend → backend URL",
               "Base URL the React app calls. Must point at the backend's /api/v1.", restart=True),
            _k("VITE_ML_API_URL", "Frontend → ML API URL",
               "Direct link to the smart-truck ML API (Swagger / raw-model buttons only).", restart=True),
        ],
    },
    {
        "section": "AI Insights (Route Intelligence)",
        "hint": "Real, dynamic insights from a free-tier cloud LLM. Leave provider on "
                "'rule-based' to use the built-in templates (no key needed).",
        "keys": [
            _k("INSIGHTS_PROVIDER", "Insights engine",
               "gemini = real AI via Google Gemini (needs a key below); "
               "rule-based = built-in templates, always works, no key.",
               choices=["rule-based", "gemini"]),
            _k("GEMINI_API_KEY", "Gemini API key",
               "Free key from https://aistudio.google.com → 'Get API key'. "
               "Stored only in your .env (never committed to git).", secret=True),
            _k("GEMINI_MODEL", "Gemini model",
               "Which Gemini model to call. gemini-2.0-flash is fast + free; "
               "gemini-2.5-flash is also free-tier.",
               choices=["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]),
            _k("INSIGHTS_TEMPERATURE", "Creativity (temperature)",
               "0.0 = strict/factual, 1.0 = more varied wording. 0.4 is a good default.",
               kind="number"),
        ],
    },
    {
        "section": "ML subscription API (smart-truck)",
        "hint": "Optional — AI pages fall back to demo data when unreachable.",
        "keys": [
            _k("ML_SERVICE_URL", "ML service URL", "smart-truck ML subscription API the backend proxies to."),
            _k("ML_API_KEY", "ML API key", "X-API-Key sent on every proxied model call.", secret=True),
            _k("SMART_TRUCK_DB_URL", "smart-truck DB URL (read-only)",
               "Only used to suggest ETA city names from its route_summary table.", secret=True),
            _k("ML_PROXY_TIMEOUT", "Proxy timeout (s)", "Per-call timeout when proxying a model call.", kind="number"),
            _k("AI_MODEL_TIMEOUT", "AI model timeout (s)",
               "Per-model cap inside /ai/*; slower models get demo data so the UI always renders.", kind="number"),
        ],
    },
    {
        "section": "OSRM road distances",
        "hint": "Optional — falls back to straight-line distance when unreachable.",
        "keys": [
            _k("OSRM_API_URL", "OSRM API URL", "Road-distance service for route efficiency."),
            _k("OSRM_API_TIMEOUT", "OSRM timeout (s)", "Per-call timeout for OSRM requests.", kind="number"),
        ],
    },
    {
        "section": "Analytics tunables",
        "hint": "Speed bands and stop detection.",
        "keys": [
            _k("MOVING_KPH", "Moving threshold (km/h)",
               "A ping faster than this counts as MOVING; at/below = stopped.", kind="number"),
            _k("OVERSPEED_KPH", "Overspeed threshold (km/h)",
               "A ping faster than this is flagged OVER-SPEED (fleet policy).", kind="number"),
            _k("STOP_MIN_MINUTES", "Minimum stop (min)",
               "A standstill must last at least this long to be recorded as a stop.", kind="number"),
            _k("STOP_CLUSTER_EPS_M", "Stop cluster radius (m)",
               "DBSCAN radius that merges repeat visits into one geofence.", kind="number"),
        ],
    },
    {
        "section": "Location enrichment",
        "hint": "Reverse-geocoding (Nominatim) and nearby-place lookup (Overpass).",
        "keys": [
            _k("NOMINATIM_URL", "Nominatim URL", "Reverse-geocoding service (coordinate → address)."),
            _k("NOMINATIM_DELAY", "Nominatim delay (s)", "Seconds between calls — respect 1 req/s.", kind="number"),
            _k("OVERPASS_URL", "Overpass URL", "Nearby named place (dhaba/hotel/fuel) lookup."),
            _k("OVERPASS_DELAY", "Overpass delay (s)", "Seconds between calls (shared public server).", kind="number"),
            _k("POI_RADIUS_M", "POI search radius (m)", "How far around a stop to search for a named place.", kind="number"),
        ],
    },
]

_ALL_KEYS = {k["key"] for s in CONFIG_REGISTRY for k in s["keys"]}


# ---------------------------------------------------------------------------
# .env read / write — preserves comments and layout; updates lines in place.
# ---------------------------------------------------------------------------
_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def _read_env_file() -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m:
            # strip trailing inline comments like "1.1   # seconds between calls"
            raw = m.group(2)
            val = raw.split("#", 1)[0].strip() if "#" in raw else raw.strip()
            values[m.group(1)] = val
    return values


def _write_env_updates(updates: Dict[str, str]) -> None:
    """Replace KEY=... lines in place; append missing keys at the end."""
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    elif ENV_EXAMPLE.exists():
        lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    pending = dict(updates)
    out: List[str] = []
    for line in lines:
        m = _LINE_RE.match(line) if not line.lstrip().startswith("#") else None
        if m and m.group(1) in pending:
            out.append(f"{m.group(1)}={pending.pop(m.group(1))}")
        else:
            out.append(line)
    if pending:
        out.append("")
        out.append("# --- added from the Settings page ---")
        out.extend(f"{k}={v}" for k, v in pending.items())
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def _current_value(key: str, file_values: Dict[str, str]) -> str:
    return os.environ.get(key, file_values.get(key, ""))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
class ConfigUpdate(BaseModel):
    updates: Dict[str, str]


@router.get("/config")
def get_config():
    file_values = _read_env_file()
    sections = []
    for sec in CONFIG_REGISTRY:
        sections.append({
            "section": sec["section"],
            "hint": sec["hint"],
            "keys": [{**k, "value": _current_value(k["key"], file_values)} for k in sec["keys"]],
        })
    return {"env_file": str(ENV_FILE), "env_file_exists": ENV_FILE.exists(), "sections": sections}


@router.put("/config")
def put_config(body: ConfigUpdate):
    unknown = set(body.updates) - _ALL_KEYS
    if unknown:
        raise HTTPException(400, f"Unknown config keys: {sorted(unknown)}")

    _write_env_updates(body.updates)
    for k, v in body.updates.items():
        os.environ[k] = v

    # Invalidate caches so env-derived config is re-read immediately.
    try:
        from lakehouse.settings import get_settings
        get_settings.cache_clear()
    except Exception:  # noqa: BLE001
        pass
    # Re-select the AI-insights backend so a freshly-saved Gemini key/model/
    # provider takes effect on the next "Regenerate AI" without a restart.
    try:
        from route_intelligence import ai_insights
        ai_insights.reset_backend()
    except Exception:  # noqa: BLE001
        pass

    restart_keys = [k["key"] for s in CONFIG_REGISTRY for k in s["keys"] if k["restart"]]
    needs_restart = sorted(set(body.updates) & set(restart_keys))
    logger.info("settings: updated %s (restart needed for %s)", sorted(body.updates), needs_restart)
    return {"ok": True, "saved": sorted(body.updates), "needs_restart": needs_restart}


@router.get("/db/status")
def get_db_status():
    from lakehouse import bootstrap
    return bootstrap.db_status()


@router.post("/db/init")
def post_db_init():
    from lakehouse import bootstrap
    return bootstrap.init_all()
