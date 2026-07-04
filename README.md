# neXgen-FMS — Fleet Intelligence

Fleet Management Platform — successor to `smart-truck`. Ingests **trip master data**
and **raw GPS device feeds** into a local **MySQL warehouse**, then serves a
React dashboard with live KPIs, charts, maps and ML-ready analytics.

> Targeting feature parity + ML differentiators against [FleetX](https://fleetx.io).

---

## Architecture (one line)

```
Excel feeds ─▶ lakehouse/ (pandas + SQLAlchemy) ─▶ MySQL warehouse ─▶ backend/ FastAPI ─▶ frontend/ React (dark + cyan theme)
            (trpdtaopn_*.xlsx, gpsfinal_*.xlsx)        (fact_trip,                /api/v1/*           Recharts + Leaflet
                                                        fact_gps_ping, …)
```

- **Warehouse** = local **MySQL 8** (`WAREHOUSE_URL` in `.env`). Neon Postgres is kept
  commented as a dialect-aware fallback. The DB auto-creates on first upload.
- **Data source toggle** lives in `.env` (`USE_MOCK_DATA`, `WAREHOUSE_URL`). The header
  pill shows the live mode — **`LAKEHOUSE`** (real warehouse) or **`MOCK`** (sample rows).

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/GPS_FEED.md](docs/GPS_FEED.md)
and [docs/DATA_REALITY.md](docs/DATA_REALITY.md) for the deep dives, and
[docs/UI_GUIDE.md](docs/UI_GUIDE.md) for the **design system + full button reference**.

---

## Quickstart

### Fresh clone / fork — standalone setup (any machine)

The app is **self-initialising**: give it a MySQL server and it creates the
database + every table on first startup.

```bash
# 0. Prerequisites: Python 3.11+, Node 18+, MySQL 8 running locally (or any reachable MySQL/Postgres)

# 1. Clone your fork
git clone https://github.com/<you>/nexgen-FMS.git && cd nexgen-FMS

# 2. Create the config file (the ONLY file you must touch)
cp .env.example .env
#    → edit ONE line: WAREHOUSE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/nextgen_fms
#      (the nextgen_fms database does NOT need to exist — it is auto-created)

# 3. Backend
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python -m backend.app.main                        # ← auto-creates DB + all tables on startup

# 4. Frontend (second terminal)
cd frontend && npm install && npm run dev         # http://localhost:6173
```

Everything else is optional (smart-truck ML API, OSRM, Streamlit deep-dive —
the app falls back gracefully when they're absent) and **every setting can be
viewed/edited from the UI**: **System → Settings** shows the DB status, an
"Initialize database" button, and every `.env` tunable with save-back to file.

**Troubleshooting is built in**: **System → Logs** streams the real backend
logs into the browser — startup, DB bootstrap, every API request, and full
error tracebacks — with level filters and text search. If anything fails,
the reason is on that page.

**Real AI insights (optional)**: Route Intelligence insights default to
built-in templates (no key needed). To get genuinely dynamic AI insights,
grab a free key at [aistudio.google.com](https://aistudio.google.com) →
open **Settings → AI Insights**, paste `GEMINI_API_KEY`, set the engine to
`gemini`, Save — then click **Regenerate AI** on any trip. Powered by Google
Gemini via LangChain; falls back to templates automatically if the key is
missing or the free-tier quota runs out.

### First-time setup (project-local venv)

```powershell
Set-Location "C:\Users\Sanjoy Chattopadhyay\PycharmProjects\nextGen-FMS"
.\scripts\setup-venv.ps1            # creates .venv, installs deps (.env is the single config file)
```

### Day-to-day (two terminals)

```powershell
# Terminal 1 — backend  (http://localhost:9001)
# Port is read from .env (FMS_BACKEND_PORT). Sits alongside smart-truck on 8000.
Set-Location "C:\Users\Sanjoy Chattopadhyay\PycharmProjects\nextGen-FMS"
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload --port $env:FMS_BACKEND_PORT `
    --reload-dir backend --reload-dir lakehouse
# or simply:  python -m backend.app.main   (reads FMS_BACKEND_PORT itself)

# Terminal 2 — frontend  (http://localhost:6173)
# Port is read from .env (FMS_FRONTEND_PORT). Sits alongside smart-truck on 5173.
Set-Location "C:\Users\Sanjoy Chattopadhyay\PycharmProjects\nextGen-FMS\frontend"
npm run dev
```

### ML subscription API (smart-truck)

The backend proxies every model call to **smart-truck**'s ML subscription API
(see `../smart-truck/docs/API_REFERENCE.md`). Make sure it is running on the
default `localhost:8001` before the AI pages render, and that `ML_API_KEY` in
`.env` is a valid subscription key.

```powershell
# Terminal 3 — smart-truck ml_service  (http://localhost:8001)
Set-Location "C:\Users\Sanjoy Chattopadhyay\PycharmProjects\smart-truck"
uvicorn ml_service.app.main:app --reload --port 8001
```

> **PowerShell tip:** your username has a space, so paths must be quoted.
> `cd C:\Users\Sanjoy Chattopadhyay\...` fails; `Set-Location "C:\Users\Sanjoy Chattopadhyay\..."` works.

### Load data

The warehouse starts empty. Use the in-app upload buttons (below) to ingest the
Excel feeds in `data/`:

1. **Trips** page → **Upload to Warehouse** → loads `data/trpdtaopn_*.xlsx`.
2. **GPS Feed** page → **Upload to Warehouse** → loads `data/gpsfinal_*.xlsx`.

---

## What each button does

The two buttons you'll use most are **Refresh** and **Upload to Warehouse** — and they
are *not* the same thing:

- **Refresh** = re-read what's *already in the warehouse* (fast, read-only). Use it after
  an upload, or to pull the latest after someone else loaded data.
- **Upload to Warehouse** = re-ingest the *Excel source files* into MySQL (the heavy step).
  The user-facing label "cloud DB" is the same MySQL warehouse.

| Page | Button / control | What it does | API call |
|------|------------------|--------------|----------|
| **Header** (all pages) | 🔄 Refresh | Re-pings backend health; updates the **System Healthy · LAKEHOUSE/MOCK** pill and data-source label. Auto-runs every 30 s. | `GET /health` |
| **Header** | 🔔 Bell · Search ⌘K | Placeholders (notifications / global search) — wired in a later phase. | — |
| **Sidebar footer** | `v0.1.0 · <SOURCE>` dot | Live status: green = warehouse reachable; shows **MOCK vs LAKEHOUSE** + host, straight from `/health`. | `GET /health` |
| **Dashboard** | Refresh | Reloads KPIs, charts and the active-trips table. | `GET /dashboard/summary`, `GET /trips/active?limit=200` |
| **Trips** | Refresh | Reloads KPIs, charts and the trip book **from MySQL** (does *not* re-read Excel). | `GET /trips/db/summary`, `GET /trips/db` |
| **Trips** | **Upload to Warehouse** | Reads `data/trpdtaopn_*.xlsx` (sheets `Trip_Data` + `Trip_Data_Dtl`) and **full-snapshot refreshes** `fact_trip` + `fact_trip_leg` (DELETE + INSERT, idempotent). Then auto-refreshes. | `POST /trips/upload` |
| **Trips** | Status chips · Search | Server-side filter / debounced search of the trip book. | `GET /trips/db?status=…&search=…` |
| **Trips** | Row click | Opens the trip detail modal (header + per-leg breakdown). | `GET /trips/db/{trip_no}` |
| **GPS Feed** | Refresh | Reloads warehouse status + the fleet table. | `GET /data/upload-gps/status`, `GET /gps/fleet` |
| **GPS Feed** | **Upload to Warehouse** | Reads `data/gpsfinal_*.xlsx`, normalises the device schema and **incrementally** upserts new pings into `fact_gps_ping` (`INSERT IGNORE` on `ping_id`). First upload also builds geofences + stop events. | `POST /data/upload-gps` |
| **GPS Feed** | Row click | Opens the per-truck detail (route map, journeys, speed, device health). | navigates to `/gps/{vehicle_reg}` |
| **Halts & Rests / Geofences** | Build geofences | DBSCAN-clusters stop coordinates into geofences + stop events. | `POST /gps/build-geofences` |
| **Halts & Rests / Geofences** | Geocode | Reverse-geocodes stop coordinates (Nominatim, rate-limited 1/s). | `POST /gps/geocode?limit=N` |
| **Halts & Rests / Geofences** | Enrich POI | Looks up nearby points of interest (Overpass). | `POST /gps/enrich-poi?limit=N` |
| **Any table** | ‹ 1 2 3 › · *N / page* | Client-side pagination of the loaded result set. | — (no network) |

---

## UI redesign (this iteration)

- **Typography** — **Space Grotesk** (headings + metrics, via `.metric`/`.font-display`)
  + **Inter** (body), loaded in `index.html`. Previously `Inter` was requested in CSS but
  never loaded, so the app fell back to the plain OS font.
- **Visuals-first layout** — every flagship page now leads with **KPIs → charts → table**.
- **Native charts** — built with **Recharts** (donut, ranked bars, gauge, area-trend),
  themed to the cyan palette. *We deliberately did not embed Streamlit:* it's a separate
  Python server that can only be iframed, won't match the theme, and can't share state with
  React. Native charts give the same diagrams with none of that overhead.
- **Pagination everywhere** — `usePagination` hook + drop-in `<Pagination>` component.
- **Reusable kit** — `components/ui/KpiCard`, `components/charts/{ChartCard,DonutChart,BarChart,AreaTrend,Gauge}`.

Full details + how to roll the pattern onto the remaining pages: [docs/UI_GUIDE.md](docs/UI_GUIDE.md).

---

## Project layout

```
backend/      FastAPI app (backend/app/main.py, api/ routers)
lakehouse/    warehouse clients + ingestion (trip_store, gps_store, geofence, poi, …)
frontend/     React + Vite + Tailwind v4 UI
  src/pages/        one file per route
  src/components/   layout/, ui/, charts/
  src/hooks/        usePagination
  src/lib/api.ts    typed axios client (every endpoint lives here)
data/         Excel feeds (trpdtaopn_*.xlsx, gpsfinal_*.xlsx)
docs/         architecture, GPS feed, data reality, UI guide
.env          the single config file (warehouse URL, thresholds, geocoding)
```

## Status

Warehouse-backed (local MySQL). Trip + GPS ingestion and analytics are live;
ML/DL/LLM differentiators are the next phase. Flip `USE_MOCK_DATA=true` in `.env`
to demo against sample rows without a database.
