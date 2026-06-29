This will be long but it's your foundation document. Save it. I'll go table-by-table first, then model-by-model with exact joins and feature recipes.

---

# PART A — Schema deep dive (every column, what it does)

## A.1 `telemetry.fact_trips` — one row per trip

The **trip header**. Use this when you want "give me everything about trip X" or "list all trips that...".

| # | Column | Type | What it actually means |
|---|---|---|---|
| 1 | `trip_no` | long | Business trip number — what humans use to refer to the trip. **Primary join key**. |
| 2 | `trip_uuid` | string | Globally unique ID. Use it when integrating with external systems. |
| 3 | `vehicle_sk` | long | Warehouse internal ID of the vehicle. Use to join to a vehicles dimension. |
| 4 | `vehicle_id` | string | Real-world vehicle registration / plate (e.g., "MH12AB1234"). |
| 5 | `driver_sk` | long | Internal ID of the driver. |
| 6 | `driver_name` | string | Driver's name (denormalized for convenience). |
| 7 | `driver_mobile` | string | Driver's phone — useful for SMS/WhatsApp alerts. |
| 8 | `transporter_sk` | long | Internal ID of the transporter (the trucking company). |
| 9 | `transporter_name` | string | Transporter name. |
| 10 | `transporter_code` | string | Short code, e.g., "VRL", "DELHIVERY". |
| 11 | `shipper_sk` | long | Internal ID of the shipper (customer paying for freight). |
| 12 | `shipper_name` | string | Shipper name. |
| 13 | `consigner_sk` | long | Internal ID of the consigner (origin party — usually = shipper). |
| 14 | `consigner_name` | string | Consigner name. |
| 15 | `origin_geofence_sk` | long | Geofence ID of the pickup location. |
| 16 | `origin_text` | string | Free-text pickup address. |
| 17 | `origin_pin_code` | int | PIN code of origin. |
| 18 | `priority` | string | HIGH / MEDIUM / LOW etc. — set by the dispatcher. |
| 19 | `tag` | string | Free-text labels ("HAZMAT", "FRAGILE", "EXPORT"). |
| 20 | `service_provider` | string | Often same as transporter. |
| 21 | `trip_type` | string | Code like "FTL", "LTL". |
| 22 | `trip_type_desc` | string | Human label of trip type. |
| 23 | `route_id` | long | If trip follows a pre-defined route, its ID. |
| 24 | `trip_booking_ts` | timestamp | When the trip was *booked* in the system. |
| 25 | `trip_start_ts` | timestamp | When the truck actually started moving. |
| 26 | `trip_planned_eta_ts` | timestamp | What was promised at booking. |
| 27 | `trip_derived_eta_ts` | timestamp | Latest re-estimated ETA (this is what your ML will improve). |
| 28 | `trip_actual_arrival_ts` | timestamp | When the truck reached final destination. |
| 29 | `trip_actual_end_ts` | timestamp | When the trip was officially closed (PoD received etc.). |
| 30 | `gate_in_ts` | timestamp | Gate entry at first stop. |
| 31 | `total_distance_km` | double | Total planned distance. |
| 32 | `lifecycle_status` | string | PLANNED / IN_TRANSIT / DELIVERED / CANCELLED / CLOSED. |
| 33 | `close_reason` | string | Why it closed (DELIVERED, RETURNED, BREAKDOWN…). |
| 34 | `running_status` | string | Current operational state (MOVING, STOPPED, IDLE…). |
| 35 | `running_status_raw` | string | Vendor-specific original code (kept for debugging). |
| 36 | `delay_minutes` | int | `actual_arrival − planned_eta` in minutes. **The target for delay models**. |
| 37 | `num_legs` | int | How many legs this trip has. |
| 38 | `num_legs_delivered` | int | How many legs have completed delivery. |
| 39 | `last_seen_in_api` | timestamp | Last time source system confirmed this trip exists. |
| 40 | `card_id`, 41 `domain_name`, 42 `multi_trip` | misc | Source-system fields; mostly ignorable. |
| 43-49 | `source_system`, `source_payload_hash`, `pipeline_run_id`, `ingested_at`, `updated_at`, `schema_version`, `extra_data` | **pipeline metadata** | Use only for data-quality debugging. |

---

## A.2 `telemetry.fact_trip_legs` — one row per leg

The **leg detail**. A trip with 3 stops produces 3 rows here, joined to `fact_trips` by `trip_no`.

| # | Column | Meaning |
|---|---|---|
| 1 | `trip_no` | **FK to `fact_trips.trip_no`**. |
| 2 | `leg_seq` | Sequence within the trip (1, 2, 3…). |
| 3 | `shipment_id` | Reference number of the goods on this leg. |
| 4 | `leg_uuid` | Unique ID for this specific leg. |
| 5-7 | `consignee_sk`, `consignee_name`, `consignee_pin` | Who's receiving and where. |
| 8 | `dest_geofence_sk` | Geofence of the drop location. |
| 9-11 | `dest_node_name`, `dest_text`, `final_dest` | Destination labels. |
| 12 | `leg_planned_eta_ts` | Promised arrival for this leg. |
| 13 | `leg_derived_eta_ts` | Re-estimated arrival. |
| 14 | `leg_actual_arrival_ts` | When it actually arrived. |
| 15 | `leg_plant_in_ts` | Reached the loading/unloading bay. |
| 16 | `leg_pod_received_ts` | Proof-of-delivery received. |
| 17 | `planned_distance_km` | Distance to this leg's destination. |
| 18 | `covered_distance_km` | Distance covered so far. |
| 19 | `pct_complete` | covered / planned. |
| 20 | `lrgr_no` | Lorry receipt number. |
| 21 | `material_text` | Free-text description of goods. |
| 22-24 | `invoice_numbers`, `invoice_raw`, `invoice_qty` | Commercial paperwork. |
| 25-26 | `waybill_no`, `waybill_validity_ts` | E-way bill info. |
| 27 | `gate_entry_no` | Gate pass at consignee. |
| 28 | `trip_type_desc` | Trip type at leg level. |
| 29 | `supplier_mat_owner` | Who owns the material being moved. |
| 30 | `event_code` | Internal status code. |
| 31 | `plant_detention_mins` | **Minutes truck was stuck at this stop** — gold for detention analytics. |
| 32 | `plant_detention_raw` | Raw vendor value. |
| 33 | `leg_status` | Per-leg lifecycle. |
| 34 | `leg_running_status` | Per-leg operational status. |
| 35 | `leg_delay_minutes` | Delay at this leg. |
| 36-43 | pipeline metadata | Same as before. |

---

## A.3 `telemetry.gps_telemetry_events` — one row per ping (rich)

The **detailed GPS stream**. This is your largest table — millions of rows per day. Joined to trips via `trip_id` and/or `vehicle_id` + time-window.

| # | Column | Meaning |
|---|---|---|
| 1 | `vehicle_id` | Plate — join key to `fact_trips.vehicle_id`. |
| 2-3 | `entity_id`, `entity_name` | Internal device-owner. |
| 4 | `device_id` | Physical IoT device ID (a vehicle can change devices). |
| 5 | `gps_timestamp` | When the device recorded position. |
| 6 | `server_timestamp` | When the server received it. |
| 7-8 | `latitude`, `longitude` | Coordinates. |
| 9 | `speed` | km/h or m/s. |
| 10 | `heading` | 0-359° from north. |
| 11 | `ignition_status` | 0/1 — engine off/on. |
| 12 | `odometer` | Cumulative km. |
| 13 | `altitude` | Meters above sea level. |
| 14 | `hdop` | GPS accuracy (<2 great, >10 bad). |
| 15 | `satellites` | How many sats locked. |
| 16 | `fuel_level_pct` | Tank %. |
| 17 | `fuel_liters` | Liters in tank. |
| 18 | `engine_rpm` | Engine revs. |
| 19 | `battery_voltage` | Volts. |
| 20 | `driver_id` | Who was driving at this ping. |
| 21 | `signal_strength` | Cellular signal. |
| 22 | `geofence_id` | Which geofence the vehicle was inside (if any). |
| 23 | `trip_id` | Which trip this ping belongs to (if assigned). |
| 24 | `motion_status` | MOVING/STOPPED/IDLE. |
| 25 | `road_speed_limit` | Legal limit for current road. |
| 27-32 | metadata (`_event_id`, `_ingested_at`, `_is_late`, etc.) | Pipeline housekeeping. |

---

## A.4 `telemetry.gps_events` — one row per ping (lean)

A downsampled / lighter version of the same stream. No fuel, no RPM, no battery, no satellites. Use when you only need position + speed and want cheaper queries.

Key columns: `vehicle_id`, `gps_timestamp`, `lat/lng`, `speed`, `heading`, `ignition_status`, `odometer`. Same metadata columns.

**Rule of thumb:** start with `gps_telemetry_events` for ML feature building; use `gps_events` for live-map serving where you only need where the truck is.

---

## A.5 `telemetry.trip_detail` — one row per waypoint per trip

A trip-scoped GPS stream. Already joined to a `trip_id` at ingestion time.

| Column | Meaning |
|---|---|
| `trip_id` | FK to trip. |
| `sequence_no` | Order of this waypoint within the trip. |
| `gps_timestamp` | When. |
| `latitude`, `longitude` | Where. |
| `speed`, `heading`, `ignition_status`, `odometer` | Basic kinematics. |
| `event_type` | START / STOP / IGNITION_ON / IGNITION_OFF / GEOFENCE_IN / OVERSPEED / etc. |

This table is the easiest one for trip-replay and lane-discovery — you don't have to re-link GPS to trips yourself.

---

## A.6 `telemetry.trip_header` — one row per trip (lightweight)

A slimmer trip summary table. Likely auto-derived from raw events without the full commercial enrichment that `fact_trips` has.

Columns: `trip_id`, `vehicle_id`, `driver_id`, `start_time`, `end_time`, `start_odometer`, `end_odometer`, `start_location`, `end_location`, `status`.

**When to use:** quick distance/duration questions and joining GPS streams to a trip when you don't need shipper/consignee enrichment.

---

## A.7 Mental map of joins

```
fact_trips  ─── trip_no ───►  fact_trip_legs
     │
     │ vehicle_id + (between trip_start_ts and trip_actual_end_ts)
     ▼
gps_telemetry_events  ───  gps_events  (same key, fewer cols)

trip_header ── trip_id ──► trip_detail  (waypoint stream)

fact_trips.trip_no  ←──  (sometimes equal to)  trip_header.trip_id
```

The two "trip" pairs (`fact_trips`/`fact_trip_legs` vs `trip_header`/`trip_detail`) likely come from different source systems — one is the **commercial / TMS** view, the other is the **device-derived** view. You will probably link them by `vehicle_id + time window` until you confirm a direct key exists.

---

# PART B — Model-by-model build plan

For each model: **purpose → tables → joins → features → model → target → evaluation → output**.

---

## B.1 — Dynamic ETA prediction (Tier 1)

**Purpose:** At any moment during an in-progress trip, predict the remaining time to destination.

**Tables used:**
- `fact_trips` (trip metadata, planned ETA, total distance)
- `fact_trip_legs` (current leg, planned distance per leg)
- `gps_telemetry_events` (current speed, position, fuel, idle time)
- `trip_detail` (waypoint history for the current trip)

**Joins:**
```
fact_trips f
  JOIN fact_trip_legs l           ON f.trip_no = l.trip_no
  JOIN gps_telemetry_events g     ON g.vehicle_id = f.vehicle_id
                                  AND g.gps_timestamp BETWEEN f.trip_start_ts AND COALESCE(f.trip_actual_end_ts, NOW())
```

**Feature recipe (compute as of "prediction time" T):**

| Feature | Source | Notes |
|---|---|---|
| `lane_id` | `origin_geofence_sk` + `dest_geofence_sk` | Bucketize origin-dest pair. |
| `historical_lane_median_minutes` | `fact_trips` aggregate | Median duration of completed trips on same lane (last 90d). |
| `historical_lane_p90_minutes` | same | P90 to capture tail. |
| `vehicle_avg_speed_30d` | `gps_telemetry_events` | Mean speed (when moving) per vehicle. |
| `driver_avg_delay_minutes_30d` | `fact_trips.delay_minutes` | Driver's historic delay tendency. |
| `transporter_on_time_rate_30d` | `fact_trips` | Transporter OT%. |
| `hour_of_day_start`, `day_of_week`, `is_weekend`, `is_holiday` | `trip_start_ts` | Time encoding. |
| `pct_complete` | `fact_trip_legs.pct_complete` | Where in the trip we are. |
| `remaining_distance_km` | `total_distance_km − covered_distance_km` | Direct distance left. |
| `current_speed_kmh` | last 5 min of `gps_telemetry_events` | Average. |
| `idle_minutes_last_hour` | `gps_telemetry_events` where ignition=1 & speed=0 | Recent stuckness. |
| `elapsed_minutes` | `T − trip_start_ts` | Time used so far. |
| `legs_remaining` | `num_legs − num_legs_delivered` | Multi-stop trips. |
| `weather_at_current_location` (later) | external API | Add in v2. |

**Model:** XGBoost regressor (`xgboost.XGBRegressor`, `objective='reg:squarederror'` or `reg:absoluteerror`).

**Target:** `remaining_minutes = trip_actual_end_ts − T`, where T is a *sampled* prediction time inside the trip. Sample 5-10 random T's per historical trip during training so the model learns to predict at any progress %.

**Evaluation:**
- MAE (minutes), MAPE (% error), separately at `pct_complete = 0, 25, 50, 75`.
- Compare to a simple baseline: `remaining_distance / current_speed`. You must beat this.

**Output:** Refresh `trip_derived_eta_ts` on `fact_trips` every N minutes for active trips.

---

## B.2 — Delay-risk classifier (Tier 1)

**Purpose:** *Before* the trip starts, predict whether it will be > X minutes late so dispatch can act (assign better driver, change vehicle, warn customer).

**Tables used:** `fact_trips`, `fact_trip_legs` (for past trips to build history), nothing live.

**Joins:** Just `fact_trips` self-aggregated to compute history features per driver/vehicle/transporter/lane.

**Features (all computed *as of trip_booking_ts* — no future leakage):**

| Feature | Source |
|---|---|
| `driver_trips_completed_30d` | `fact_trips` count where driver_sk = X, trip_actual_end_ts < booking_ts |
| `driver_late_rate_30d` | mean(delay_minutes > 30) |
| `driver_avg_delay_30d` | mean(delay_minutes) |
| `vehicle_breakdowns_90d` | count(close_reason = 'BREAKDOWN') |
| `vehicle_age_days` | needs a vehicles dim (later) |
| `transporter_otif_30d` | (% legs on time at transporter level) |
| `lane_median_delay` | aggregate per origin-dest pair |
| `lane_p90_delay` | same |
| `lane_trip_count` | popularity |
| `hour_of_day_start`, `day_of_week`, `is_monsoon_month` | time |
| `priority` | from `fact_trips` |
| `trip_type` | from `fact_trips` |
| `num_legs` | multi-stop is harder |
| `total_distance_km` | longer = more variance |

**Model choices to try, in order:**
1. **Logistic regression** — baseline + interpretability.
2. **XGBoost classifier** — usually wins.
3. **LightGBM** — try if XGB is slow.

**Target:** `delay_minutes > 60` (binary). Also build a **regression** version predicting expected delay minutes.

**Evaluation:** ROC-AUC, precision@top-10% (dispatch can only act on so many alerts).

**Output:** A risk score 0-1 stored at trip-booking time. UI shows green / yellow / red.

---

## B.3 — Driver risk score (Tier 1)

**Purpose:** A weekly 0-100 safety score per driver.

**Tables used:** `gps_telemetry_events` (primary), `fact_trips` (to attribute pings to a driver).

**Joins:**
```
gps_telemetry_events g
  JOIN fact_trips f ON g.vehicle_id = f.vehicle_id
                   AND g.gps_timestamp BETWEEN f.trip_start_ts AND f.trip_actual_end_ts
```
(Use `driver_sk` from `fact_trips` since `g.driver_id` is often missing.)

**Per-driver weekly features:**

| Feature | Recipe |
|---|---|
| `overspeed_rate` | count(speed > road_speed_limit) / total_pings |
| `harsh_brake_count` | count(speed[t-1] − speed[t] > threshold within 5s window) |
| `harsh_accel_count` | symmetric on positive side |
| `idle_pct` | count(ignition=1 AND speed=0) / count(ignition=1) |
| `night_drive_pct` | pings between 22:00-05:00 / total |
| `continuous_drive_max_hours` | max continuous moving streak |
| `avg_speed_when_moving` | mean(speed where speed > 5) |
| `speed_volatility` | std(speed) per trip averaged |

**Model approach (do both):**
1. **Rule-based composite score (start here):**
   ```
   score = 100
         − w1 * overspeed_rate_normalized
         − w2 * harsh_brake_per_100km
         − w3 * night_drive_pct
         − w4 * continuous_drive_violation_count
   ```
   Tune weights with domain knowledge.

2. **IsolationForest** on the same features → outputs anomaly score per driver. Combine with rule-based for "this driver scores 35 *and* looks unusual."

**Evaluation:** No labels exist for "good/bad driver." Validate by correlating score with actual incidents: accidents, breakdowns, customer complaints (when available). Until then, sanity-check by ranking — top 10 worst should look bad to a fleet manager.

**Output:** Weekly score per driver + breakdown of the contributing factors (so coaching is actionable).

---

## B.4 — Anomaly detection on telemetry (Tier 1)

**Purpose:** Catch "weird" pings/sequences — sensor failure, stuck GPS, theft, off-route stops.

**Tables used:** `gps_telemetry_events`.

**Per-ping or per-rolling-window features:**

| Feature | Recipe |
|---|---|
| `speed_jump` | abs(speed[t] − speed[t-1]) |
| `position_jump_km` | haversine(lat[t], lat[t-1]) — if huge with tiny time delta → GPS error |
| `time_gap_seconds` | gps_timestamp[t] − gps_timestamp[t-1] |
| `ignition_off_with_motion` | ignition=0 AND speed > 5 |
| `motion_without_trip` | trip_id IS NULL AND speed > 5 |
| `hdop` | already a quality signal |
| `satellites` | low = suspicious |
| `signal_strength` | low = stale risk |

**Models to try:**
1. **IsolationForest** (`sklearn.ensemble.IsolationForest`) — your default for tabular outlier detection.
2. **Autoencoder** (Keras, small MLP) — once you have enough data and want to capture multi-feature correlations.
3. **Rule-based filters layered on top** — `position_jump_km > 50 AND time_gap < 60s → impossible_jump`.

**Evaluation:** Manual review of top 100 flagged events. Iterate.

**Output:** An `anomaly_events` table with `event_id, vehicle_id, gps_timestamp, anomaly_type, anomaly_score`.

---

## B.5 — Fuel-theft / pilferage detection (Tier 2)

**Purpose:** Flag suspicious sudden drops in fuel level.

**Tables used:** `gps_telemetry_events` (need `fuel_level_pct`, `fuel_liters`, `odometer`, `ignition_status`).

**Approach (rules first, then ML):**

1. **Build per-ping fuel-delta features:**
   - `fuel_delta_liters = fuel_liters[t-1] − fuel_liters[t]`
   - `odo_delta_km = odometer[t] − odometer[t-1]`
   - `time_delta_min`
   - `expected_consumption_liters = odo_delta_km / expected_mileage_kmpl` (compute per-vehicle baseline mileage first)
   - `unexplained_drop = fuel_delta_liters − expected_consumption_liters`

2. **Rule layer (catches obvious cases):**
   - `fuel_delta_liters > 20 AND ignition_status = 0` → very likely siphoning (truck parked, fuel drops 20L)
   - `unexplained_drop > 15 within 10 minutes`
   - `fuel_delta_liters < 0 AND magnitude > 30L` → could be a refill (need to distinguish; refills usually happen at fuel stations — cross-check with geofences)

3. **ML layer (catches subtle cases):**
   - **IsolationForest** on per-vehicle fuel-consumption profile (liters/km, liters/hour while idle, etc.). Per-vehicle baselining matters because a 16-wheeler ≠ a pickup.
   - Or **change-point detection** (e.g., `ruptures` library) on the fuel_liters time series.

**Evaluation:** Confirmed pilferage cases reported by the fleet manager → use as positive labels.

**Output:** Suspected events with location pinned on map and 30-minute video window of telemetry before/after. This is what makes operations trust the alert.

---

## B.6 — Detention prediction (Tier 2)

**Purpose:** At leg start, predict how long the truck will be stuck at the consignee/plant.

**Tables used:** `fact_trip_legs` (history of `plant_detention_mins` per consignee).

**Features (at leg start):**

| Feature | Source |
|---|---|
| `consignee_avg_detention_30d` | mean over `fact_trip_legs` |
| `consignee_p90_detention_30d` | tail behaviour |
| `consignee_detention_by_hour_of_day` | some plants are slow in evenings |
| `consignee_detention_by_day_of_week` | Mondays are worse |
| `material_type` (`material_text` hash/category) | bulky goods = longer unload |
| `arrival_hour` | most predictive single feature usually |
| `is_arrival_near_shift_change` | flag |
| `trip_type` |  |
| `transporter_relationship_with_consignee_trips_count` | familiarity helps |

**Model:** XGBoost regressor → expected detention minutes. Also a classifier for "will detention > 4 hours."

**Evaluation:** MAE on minutes. Calibration plot.

**Output:** Shown to dispatcher when planning leg: "Expect 3h 20m detention at consignee X." Drives slot-booking strategy with the customer.

---

## B.7 — Geofence dwell-time anomaly (Tier 2)

**Purpose:** Flag when a vehicle is parked at a place it shouldn't be, for longer than expected.

**Tables used:** `gps_telemetry_events` + a geofences dimension (build one if you don't have it).

**Approach:**
1. Aggregate consecutive pings where `motion_status='STOPPED'` and `ignition=0` → dwell episodes (`vehicle_id, start_ts, end_ts, lat, lng, duration_min, geofence_id`).
2. Classify each dwell location:
   - Inside an authorized geofence (depot, customer, fuel pump) → normal
   - Outside any authorized geofence → suspicious if duration > threshold
3. Per-vehicle/per-route baselines for what "normal" dwell duration is on a given lane.
4. **IsolationForest** on dwell-episode features (`duration_min`, `hour_of_day`, `distance_from_planned_route`, `is_within_authorized_geofence`).

**Output:** Dwell anomalies with map location, duration, and "nearest known geofence" for context.

---

## B.8 — Predictive maintenance proxy (Tier 2)

**Purpose:** Rank vehicles most likely to break down next, without true OBD-II.

**Tables used:** `gps_telemetry_events` (battery_voltage, engine_rpm, fuel_liters, odometer, speed), `fact_trips` (close_reason = 'BREAKDOWN' = ground truth).

**Per-vehicle weekly features:**

| Feature | Recipe |
|---|---|
| `battery_voltage_min`, `_mean`, `_trend_30d` | downward trend = dying battery |
| `idle_rpm_mean`, `_std` | unstable idle = engine issue |
| `rpm_vs_speed_correlation` | abnormal ratio = clutch/gear issue |
| `fuel_economy_kmpl` | trip distance / trip fuel used |
| `fuel_economy_trend_30d` | falling = engine degrading |
| `temperature_proxy_signals` (none here) | gap |
| `breakdowns_last_180d` | recurrence |

**Model:** XGBoost classifier predicting `breakdown_in_next_14d`. Train on historical (vehicle, week) windows.

**Evaluation:** Precision@10 — of the top 10 flagged vehicles, how many actually broke down in the next 14 days.

**Output:** Weekly "vehicles to inspect" list for the maintenance team.

---

## B.9 — Route deviation detection (Tier 2)

**Purpose:** Detect when a truck strays from the expected lane path.

**Tables used:** `trip_detail` (waypoints), historical `trip_detail` for the same lane.

**Approach:**
1. For each lane (`origin_geofence_sk` → `dest_geofence_sk`), build the **canonical path**: cluster all historical waypoints from completed trips on that lane, get a representative polyline. Tools: shapely + DBSCAN or h3 hex-binning.
2. For an active trip, at each new waypoint compute `min_distance_from_canonical_path_km`.
3. Flag if `distance > 3 km` sustained for `> 5 minutes` (not just a one-off bad GPS fix).
4. **Sequence model option (later):** train an LSTM autoencoder on canonical waypoint sequences, score new sequences by reconstruction error.

**Output:** Deviation alerts with map snippet showing canonical vs. actual.

---

## B.10 — Trip clustering / lane discovery (Tier 3)

**Purpose:** Discover natural lanes from data instead of relying on manual configuration.

**Tables used:** `fact_trips` (`origin_geofence_sk` or `origin_text` → `dest` for legs).

**Approach:**
1. Build `(origin_lat, origin_lng, dest_lat, dest_lng)` tuples.
2. **DBSCAN** (or HDBSCAN) on 4D coordinates with `eps` ≈ 5 km equivalent.
3. Each cluster = a lane. Label by most common origin-text + dest-text.
4. Surface high-volume undiscovered lanes to the ops team.

**Output:** New `discovered_lanes` table.

---

## B.11 — LSTM / Temporal-Fusion ETA (Tier 3)

**Only after B.1 plateaus.**

**Tables used:** Same as B.1, but feed the **full waypoint sequence** of the in-progress trip, not just aggregates.

**Models to try:**
- **LSTM** (encoder of waypoints + decoder predicting remaining-minutes).
- **Temporal Fusion Transformer** (`pytorch-forecasting`).
- **N-BEATS** for univariate time-to-arrival.

These add ~10-25% accuracy on long-tail trips. Skip until your XGB MAE stops improving.

---

## B.12 — CV on dashcam / e-PoD (Tier 3)

**Skip for now.** You don't have image data. Note as a roadmap item once you ship a driver mobile app that captures PoD photos. Then YOLOv8/ResNet for sign-quality verification, damage detection, etc.

---

# How to sequence the build

**Month 1:** Schemas understood (you just did this), data connectors wired (PyIceberg + ClickHouse), B.1 (Dynamic ETA) shipped end-to-end as the template — model + endpoint + UI.

**Month 2:** B.2 (Delay risk), B.3 (Driver score), B.4 (Anomaly detection). All three reuse the data pipelines from B.1.

**Month 3:** B.5 (Fuel pilferage), B.6 (Detention) — your differentiators. These are what make a customer call you instead of FleetX.

**Month 4+:** B.7-B.9 as you build the geofence and route catalog. B.10-B.12 only when the base product is stable.

---

When you're ready, pick one of these models — I'd start with **B.1 (Dynamic ETA)** — and I'll write the actual data-extraction queries (PyIceberg + ClickHouse SQL), the feature-engineering script, and the training pipeline against your new lakehouse.