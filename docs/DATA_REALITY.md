# Data Reality — What's actually in the lakehouse

Profiled from `sample_data/*.xlsx` on 2026-05-31. **The lakehouse schema
promises ~170 columns; about 40% of them are 100% NULL in the sample.**
This document maps every promised feature/model from `docs/ARCHITECTURE.md`
to its current viability and proposes new ideas that fit what we *do* have.

A live, machine-driven version of this matrix is exposed at
**`/api/v1/analytics/quality`** and rendered in the UI under
**Data → Data Quality**.

---

## 1. What's present (high signal)

| Table | Columns reliably populated |
|---|---|
| `fact_trips` | `trip_no`, `trip_uuid`, `vehicle_sk`, `vehicle_id`, `transporter_sk`, `transporter_name`, `shipper_sk`, `shipper_name`, `origin_text`, `priority`, `service_provider`, `trip_type`, `trip_booking_ts`, `trip_start_ts`, `trip_planned_eta_ts`, `lifecycle_status`, `running_status`, `num_legs`, `num_legs_delivered`, `multi_trip`, `enrichment_status`, `last_seen_in_api`, `ingested_at`, `updated_at`, `source_system`, `entity_id` |
| `fact_trip_legs` | `trip_no`, `leg_seq`, `shipment_id`, `leg_uuid`, `consignee_sk`, `consignee_name`, `dest_node_name`, `dest_text`, `final_dest`, `leg_planned_eta_ts`, `planned_distance_km`, `covered_distance_km`, `leg_status` |
| `gps_telemetry_events`, `gps_events` | `vehicle_id`, `entity_id`, `entity_name`, `device_id`, `gps_timestamp`, `server_timestamp`, `latitude`, `longitude`, `speed`, `heading`, `ignition_status`, `odometer`, `_event_id`, `_ingested_at` |

## 2. What's missing or unusable

| Column | Status | Impact |
|---|---|---|
| `driver_sk` | always `0` | All driver-level analytics blocked |
| `driver_name` | 50% null | Same |
| `driver_id` (GPS) | 100% null | Cannot link GPS pings to a person |
| `driver_mobile` | 100% null | No SMS/WhatsApp alerts |
| `trip_actual_arrival_ts`, `trip_actual_end_ts`, `gate_in_ts` | 100% null | No supervised labels for ETA / SLA |
| `total_distance_km` | always `0` | No baseline for distance-based features |
| `delay_minutes` | always `1` | Pre-computed but meaningless |
| `close_reason` | 100% null | Cannot identify breakdowns |
| `fuel_level_pct`, `fuel_liters` | 90-100% null | Fuel pilferage model dies |
| `engine_rpm`, `battery_voltage` | 90% null | Predictive maintenance proxy dies |
| `road_speed_limit` | 100% null | Cannot do speeding detection without map enrichment |
| `geofence_id`, `motion_status` | 100% null | Dwell anomaly model dies; motion must be derived |
| `plant_detention_mins`, `leg_pod_received_ts`, `leg_actual_arrival_ts` | 100% null | Detention prediction + PoD/payment-cycle dies |
| `trip_id` on GPS | 100% null | Must join GPS to trips by `vehicle_id + time window` |
| `consigner_sk/name`, `origin_geofence_sk`, `tag` | 100% null | Lose some commercial enrichment |
| `route_id`, `card_id`, `domain_name` | 100% null | Ignorable |

---

## 3. Foundation models — verdict per item

| # | Model | Verdict | Why |
|---|---|---|---|
| B.1  | Dynamic ETA prediction       | 🔴 BLOCKED       | No `trip_actual_end_ts` (target), `total_distance_km = 0` |
| B.2  | Delay-risk classifier        | 🔴 BLOCKED       | `delay_minutes` is constant 1; no actual arrival ts |
| B.3  | Driver risk score            | 🔴 BLOCKED       | No driver linkage anywhere; must pivot to **vehicle** rhythm |
| B.4  | Telemetry anomaly            | 🟡 DEGRADED      | Speed sometimes 0; works for position-jump detection only |
| B.5  | Fuel-theft / pilferage       | 🔴 BLOCKED       | `fuel_level_pct` 90-100% null |
| B.6  | Detention prediction         | 🔴 BLOCKED       | `plant_detention_mins` 100% null |
| B.7  | Geofence dwell anomaly       | 🔴 BLOCKED       | `geofence_id`, `motion_status` 100% null |
| B.8  | Predictive maintenance proxy | 🔴 BLOCKED       | `battery_voltage`, `engine_rpm` 90% null |
| B.9  | Route deviation              | 🟡 PARTIAL       | Have `lat`/`lng` over time; lack `trip_id` linkage on GPS so canonical-path attribution needs vehicle+time join |
| B.10 | Lane discovery               | 🟢 READY         | `origin_text` + `dest_text` present |
| B.11 | LSTM / TFT ETA               | 🔴 BLOCKED       | Same target gap as B.1 |
| B.12 | CV / dashcam                 | ⚪ NOT APPLICABLE | No image data |

**Of 12 promised models, only 2 are buildable today (B.4 partial, B.10 ready).**

---

## 4. New models that *do* fit the data

Pivot the product toward what GPS + commercial header gives us. All of these
are exposed live at `/api/v1/analytics/*` and rendered in the UI.

### 4.1 Vehicle Behavioural Rhythm  🟢 READY
- **Inputs:** `gps_telemetry_events` (or `gps_events`): `vehicle_id`, `gps_timestamp`, `speed`, `ignition_status`, `odometer`.
- **What it does (per vehicle, last N days):**
  - **7×24 movement heatmap** — day-of-week × hour-of-day intensity. Reveals "this truck is a night runner", "this truck always rests on Sundays".
  - **Sleep episodes** — long stretches (>6h) with ignition off → driver rest. Useful for HOS compliance.
  - **Meal break detection** — recurring 30-90 min idle stops. Mid-day cluster = lunch; late-evening cluster = dinner.
  - **Tea break detection** — 10-30 min idle stops every 2-3 h. Indian-trucking habit; useful coach-on-routine signal.
  - **Drive streaks** — longest continuous moving stretches → fatigue risk proxy.
  - **Activity calendar** — GitHub-style per-day intensity dot grid → which days the truck is dormant.
- **UI:** Intelligence → **Behavioural Patterns** (new page).
- **API:** `GET /api/v1/analytics/vehicles`, `GET /api/v1/analytics/vehicles/{id}/patterns`.

### 4.2 Lane Volume / Discovery  🟢 READY
- **Inputs:** `fact_trips.origin_text` + `fact_trip_legs.dest_text`.
- **What it does:** lists most-used lanes by trip count, distinct transporters, distinct shippers.
- **UI:** Intelligence → **Lane Volume**.
- **API:** `GET /api/v1/analytics/lanes`.

### 4.3 GPS Data Quality Monitor  🟢 READY
- **Inputs:** any GPS table.
- **What it does:** computes ping latency (server_ts − gps_ts), position jumps (haversine between consecutive pings of the same vehicle), gap distribution → tells you which devices are misbehaving.
- **API:** `GET /api/v1/analytics/gps-quality`.

### 4.4 Vehicle Utilization  🟢 READY
- **Inputs:** GPS pings.
- **What it does:** per vehicle per day → % time moving / idle (ignition on, speed 0) / off (ignition off).
- **Product angle:** turn into a "asset productivity" report a fleet manager pays for.

### 4.5 Shipper / Transporter Mix  🟢 READY
- **Inputs:** `fact_trips`.
- **What it does:** scorecard per shipper/transporter on trip volume, priority mix, trip type mix.

### 4.6 Data-Driven Geofence Discovery  🟡 PARTIAL
- **Trick:** because `geofence_id` is null, DERIVE geofences by clustering long-stop locations.
- **Method:** DBSCAN on `(latitude, longitude)` of pings where `motion_status` would be STOPPED — i.e., `speed = 0` for >30 min. Each cluster → candidate geofence (depot, customer, fuel pump).
- **Why it matters:** once you have geofences, every downstream model (dwell anomaly, detention) unblocks.

### 4.7 Device Health / Tamper Detection  🟢 READY
- **Inputs:** GPS pings, especially `server_timestamp - gps_timestamp`, missing pings, `_is_late`.
- **What it does:** flag devices going silent, devices with high ingestion lag, devices with bogus `(0,0)` coords.

### 4.8 Trip-from-GPS Reconstruction  🟡 PARTIAL
- **Trick:** because `trip_id` is null on GPS, INFER trip segments per vehicle by detecting gaps where ignition off > 30 min and treating each "moving session" as a derived trip. Cross-check inferred trip count vs `fact_trips` rows to detect ingestion lag.

---

## 5. Re-prioritised sequence (revised from ARCHITECTURE.md)

**Phase 1 (this week) — build on what's present**
1. ✅ Sample loader + Data Quality view (done)
2. ✅ Behavioural Patterns page (done)
3. ✅ Lane Volume page (done)
4. GPS Quality dashboard polish
5. Derived geofence discovery (DBSCAN on stops)

**Phase 2 — unblock-the-data work**
6. Talk to data team: get `driver_sk` populated, `trip_actual_end_ts` populated, `fuel_level_pct` populated
7. Add `geofence_id` enrichment in the lakehouse OR run our DBSCAN derivation as a backfill job

**Phase 3 — original model roadmap** (once Phase 2 lands)
8. B.1 Dynamic ETA, B.2 Delay risk, B.3 Driver risk, B.5 Fuel pilferage

---

## 6. Conversation we need to have with the lakehouse team

> "These columns are promised in the catalog schema but 100% NULL in the
> sample we have. Are they: (a) not being ingested yet, (b) ingested but in
> a different namespace, (c) enrichment-pending? For each, please tell us
> when they're expected to flow."

Top of the list:
- `driver_*` fields on `fact_trips` (zero / null)
- `trip_actual_arrival_ts`, `trip_actual_end_ts`, `gate_in_ts`
- `delay_minutes` (looks constant, not a derived signal)
- `total_distance_km` (always 0)
- `fuel_level_pct`, `fuel_liters`, `engine_rpm`, `battery_voltage` on GPS
- `road_speed_limit`, `geofence_id`, `motion_status` on GPS
- `plant_detention_mins`, `leg_pod_received_ts`, `leg_actual_*_ts` on legs
