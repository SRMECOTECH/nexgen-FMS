# GPS Feed — schema, KPIs, and roadmap

Profiled from `data/gpsfinal_20260603.xlsx` on 2026-06-04. Unlike the legacy
lakehouse GPS tables (see `DATA_REALITY.md`, ~40% NULL), **this device feed is
~100% populated on every analytics-relevant column** — so most of the models
that were previously BLOCKED are now buildable.

## 1. What the file is

- **3 sheets** (`01-06-2026`, `02-06-2026`, `03-06-2026`), concatenated →
  **5,185 pings**.
- **One truck**: `CG15EA3403` (entity `SAIZARENTERPRISEPVTLTD-TCIL`, device IMEI
  `867440069917706`), 2026-06-01 → 2026-06-03.
- Corridor: **Jharkhand → Odisha → Chhattisgarh** mining/industrial belt
  (KAMDARA, SIMDEGA, BIRMITRAPUR, ROURKELA, BHILAI, RAIPUR …). 639 km travelled.
- Ping cadence ~**60 s** (median), even while parked. 48% of pings moving.

## 2. Raw → canonical schema (`raw.gps_feed`)

Normalised by `lakehouse/gps_feed.py`. Natural key = `ping_id` (`device_id|gps_ts`),
so re-uploading upserts in place.

| raw column | canonical | meaning |
|---|---|---|
| `s_asset_id` | `vehicle_reg` | registration plate |
| `s_device_id` | `device_id` | IMEI |
| `s_entity_name` / `i_entity_id` | `entity_name` / `entity_id` | owning transporter |
| `dt_message` | `gps_ts` | GPS fix time |
| `dt_server` | `server_ts` | server receive time |
| `dt_created` | `created_ts` | warehouse create time |
| — | `latency_sec` | `server_ts − gps_ts` (device buffering) |
| `i_lat` / `i_long` | `latitude` / `longitude` | position |
| `i_speed` / `i_corrt_speed` | `speed_kph` / `speed_corr_kph` | reported / corrected speed |
| `i_distance` | `odometer_m` | cumulative odometer (m) |
| `i_dist` | `segment_m` | per-ping segment distance (m) |
| `i_wpnt1_*` | `from_node*` | nearest route node **behind** (no/name/lat/lng/metres/state) |
| `i_wpnt2_*` | `to_node*` | next route node **ahead** |
| `s_wpnt{1,2}_state_abbr` | `from_state` / `to_state` | JH / OR / CT |
| `s_alert_lov` | `alert_raw` + decoded → `signal_pct`(1610), `io_state`(1570), `event_codes`(1170/1370…) | encoded telemetry LOV |
| `i_msg_no` | `msg_type` | device message type |
| — | `motion_status` | derived: MOVING if corrected speed > 2 km/h |

**Decoding `s_alert_lov`** (`code:value#code:value`): `1000`=packet-valid (always Y),
`1570`=digital-IO/state word, `1610`=signal/quality %, `1170`/`1370`=sparse event
flags (panic/door/harsh-event style — seen twice, both at the Raipur facility).

## 3. KPIs we compute today (`/api/v1/gps/*`)

Distance, drive vs idle hours, **utilization %**, avg/max speed, avg daily km,
**stop count + longest stop**, over-speed %, **states crossed**, avg signal %,
event-flag count, device uptime %, ping cadence, latency, position jumps.

Example (CG15EA3403, 3 days): 639 km · 16.7 h driving / 44.7 h idle · 27%
utilization · 16 stops (longest ~16 h overnight at PASA Associates, Raipur) ·
3 states · 99.8% device uptime.

## 4. "Extraordinary" features built on this feed

| Feature | Endpoint | Notes |
|---|---|---|
| **Trip reconstruction from GPS** | `/gps/trips` | No `trip_id` in feed — split on long stops. Yields 7 clean origin→destination trips here. |
| **Stop / candidate-geofence detection** | `/gps/stops` | Runs of STOPPED pings ≥ N min → depot/customer/halt candidates with the named node + state. |
| **Route corridor & state crossings** | `/gps/corridor` | Uses the `from_node`/`to_node` waypoint pair the device already reports; logs every inter-state border crossing. |
| **Speed profile + over-speed segments** | `/gps/speed-profile` | Time series, histogram, contiguous >60 km/h segments with location. |
| **Decoded alert / signal timeline** | `/gps/alerts` | Event flags + GSM signal-drop episodes. |
| **Device health / tamper** | `/gps/device-health` | Cadence, latency, gaps, GPS jumps, (0,0) coords. |
| **Dependency-free route map** | `/gps/track` + `TrackCanvas` | Moving/stopped coloured polyline + stop markers. |

## 5. Open-source software worth adding

- **Leaflet + OpenStreetMap tiles** (or **MapLibre GL**) — real basemap for the
  track instead of the bare SVG canvas. Free, no API key with OSM tiles.
- **scikit-learn** (`DBSCAN`/`HDBSCAN`) — cluster stop locations across many
  vehicles into *named, reusable* geofences (depots, fuel pumps, customer gates).
  Currently NOT installed; the rule-based stop detector is the stopgap.
- **OSRM** or **Valhalla** (self-hosted routing/map-matching) — snap pings to
  roads, get true road distance, detect route deviation vs the planned corridor.
- **OpenTimeSeries / Prophet / `statsmodels`** — ETA & demand forecasting later.
- **DuckDB** (already a dependency) — fast local analytical queries over the
  feed without round-tripping to Postgres.

## 6. ML / DL / AI roadmap (next discussion)

Now unblocked by this feed (pivoted to **vehicle**, since `driver_id` is null):

1. **ETA / arrival prediction** — gradient-boosted (XGBoost/LightGBM) on
   distance-to-node, time-of-day, historical lane speed; later LSTM/Temporal
   Fusion Transformer once multi-vehicle history accumulates.
2. **Anomaly detection** — IsolationForest on speed/jump/latency for spoofing,
   tampering, and impossible-movement detection.
3. **Stop-purpose classification** — cluster + classify stops as
   rest / loading / fuel / detention from duration, location, time-of-day.
4. **Driving-behaviour scoring** — harsh-accel/brake proxies from speed deltas,
   over-speed exposure, night-driving share → per-vehicle safety score.
5. **LLM layer (final phase)** — natural-language fleet Q&A over these KPIs,
   automated daily trip narratives, and prescriptive suggestions
   ("truck idled 16 h at Raipur — schedule next load earlier").
