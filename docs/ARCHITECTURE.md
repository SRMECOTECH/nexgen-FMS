# nextGen-FMS Architecture

## Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                       neXgen-Lakehouse                          │
│   Iceberg tables under namespace `telemetry.*` (6 tables)       │
│      fact_trips, fact_trip_legs, gps_telemetry_events,          │
│      gps_events, trip_detail, trip_header                       │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ PyIcebergClient│  │ ClickHouseClient │  │  DuckDBClient    │
│  (batch ML)    │  │  (API serving)   │  │  (ad-hoc / nb)   │
└────────────────┘  └──────────────────┘  └──────────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  ml_service/   │  │   backend/       │  │   scripts/, nb/  │
│  training      │  │   FastAPI :8000  │  │                  │
│  serving :8001 │  │                  │  │                  │
└────────────────┘  └─────────┬────────┘  └──────────────────┘
                              ▼
                    ┌──────────────────┐
                    │   frontend/      │
                    │   React :5173    │
                    │   Dark + Amber   │
                    └──────────────────┘
```

## Folder layout

```
nextGen-FMS/
├─ lakehouse/                # 3 client wrappers + mock data
│  ├─ pyiceberg_client.py    # batch reads for ML training
│  ├─ clickhouse_client.py   # low-latency SQL for FastAPI
│  ├─ duckdb_client.py       # in-process for ad-hoc work
│  ├─ mock_data.py           # realistic sample rows matching real schema
│  └─ settings.py            # central env-var config
│
├─ backend/                  # FastAPI service (port 8000)
│  ├─ requirements.txt
│  └─ app/
│     ├─ main.py             # entry point — uvicorn target
│     ├─ core/deps.py        # dependency providers (get_clickhouse, etc.)
│     └─ api/                # route modules
│        ├─ dashboard.py
│        └─ trips.py
│
├─ ml_service/               # ML training + model serving (port 8001)
│  └─ app/
│     ├─ training/           # train_pipeline.py — needs rewire to lakehouse
│     ├─ features/           # feature_engineering.py — needs rewire
│     └─ serving/            # model_server.py — needs rewire
│
├─ frontend/                 # React + Vite + Tailwind (port 5173)
│  └─ src/
│     ├─ components/
│     │  ├─ layout/ (Sidebar, Header)
│     │  └─ ui/     (Spinner, KpiCard)
│     ├─ pages/    (Dashboard, Trips, Vehicles, Drivers, MLHub)
│     ├─ lib/api.ts          # axios client
│     ├─ index.css           # dark + amber theme tokens (CSS vars)
│     └─ _legacy/            # smart-truck pages kept for salvage
│
├─ ml_models/                # .joblib model artifacts (gitignored)
├─ docs/                     # this file + future ADRs
├─ scripts/                  # one-off jobs (sync, backfill, etc.)
├─ .env                      # single source of truth for ALL config (gitignored)
└─ .gitignore
```

## How a request flows (Dashboard summary)

1. Browser → `GET http://localhost:5173/`
2. React `Dashboard.tsx` calls `fetchDashboardSummary()` from `lib/api.ts`
3. Axios → `GET http://localhost:8000/api/v1/dashboard/summary`
4. FastAPI route `dashboard.get_summary` resolves `Depends(get_clickhouse)`
5. `ClickHouseClient.query("SELECT * FROM telemetry.fact_trips LIMIT 1000")`
6. In MOCK mode → `lakehouse/mock_data.py::mock_fact_trips()` returns a DataFrame
   In real mode → SQL runs against ClickHouse gateway over Iceberg
7. Route computes counts and returns JSON
8. React renders KPI cards

## Switching from MOCK to real lakehouse

1. Get JWT + S3 creds from neXgen-Lakehouse UI ("Consumers" tab)
2. Fill `.env`:
   ```
   USE_MOCK_DATA=false
   ICEBERG_TOKEN=...
   S3_ACCESS_KEY=...
   S3_SECRET_KEY=...
   CLICKHOUSE_PASSWORD=...
   ```
3. `pip install pyiceberg[s3fs] clickhouse-connect duckdb`
   (uncomment the lines in `backend/requirements.txt`)
4. Restart uvicorn. Health endpoint should now show `data_source: LAKEHOUSE`.

## Where each ML model from the planning doc lives

| Tier | Model                  | File(s) to add                                       |
| ---- | ---------------------- | ---------------------------------------------------- |
| 1    | Dynamic ETA            | `ml_service/app/training/eta_trainer.py`             |
| 1    | Delay-risk classifier  | `ml_service/app/training/delay_risk_trainer.py`      |
| 1    | Driver risk score      | `ml_service/app/training/driver_score.py`            |
| 1    | Telemetry anomaly      | `ml_service/app/training/telemetry_anomaly.py`       |
| 2    | Fuel pilferage         | `ml_service/app/training/fuel_anomaly.py`            |
| 2    | Detention predictor    | `ml_service/app/training/detention.py`               |
| 2    | Route deviation        | `ml_service/app/training/route_deviation.py`         |
| 2    | Predictive maintenance | `ml_service/app/training/maintenance_proxy.py`       |
| 3    | Lane discovery (DBSCAN)| `scripts/discover_lanes.py`                          |

Each trainer reads via `PyIcebergClient`, writes a `.joblib` to `ml_models/`,
and is exposed through `ml_service/app/serving/model_server.py`.

## What's NOT here yet (next session)

- Live map (Leaflet/Mapbox) on Dashboard
- `/api/v1/vehicles` and `/api/v1/drivers` routes
- ML service rewire — the copied `training/`, `features/`, `serving/` modules
  still expect a pymysql connection. They need to be switched to PyIcebergClient.
- Auth (per project preference: none for now)
