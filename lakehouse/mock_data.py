"""
Sample data that mirrors the 6 telemetry tables exposed at
http://98.70.24.178:5173/#data-catalog

Each builder returns a pandas DataFrame whose columns match the lakehouse
schema exactly, so feature-engineering code written against the mock can be
swapped to real PyIceberg / ClickHouse output with no changes.

Row counts are small on purpose — enough to exercise joins and UI rendering
without bloating memory.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import random

import pandas as pd


_RNG = random.Random(42)


def _ts(offset_min: int, base: datetime | None = None) -> datetime:
    return (base or datetime(2026, 5, 31, 6, 0, 0)) + timedelta(minutes=offset_min)


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# fact_trips  — one row per trip
# ---------------------------------------------------------------------------
def mock_fact_trips(n: int = 50) -> pd.DataFrame:
    lanes = [
        ("Mumbai", "Pune", 150),
        ("Delhi", "Jaipur", 280),
        ("Bangalore", "Chennai", 350),
        ("Hyderabad", "Vijayawada", 270),
        ("Kolkata", "Bhubaneswar", 440),
    ]
    transporters = [("VRL", 101), ("Delhivery", 102), ("BlueDart", 103), ("TCI", 104)]
    shippers = [("Tata Steel", 201), ("Reliance", 202), ("ITC", 203), ("Hindustan Unilever", 204)]

    rows = []
    for i in range(n):
        origin, dest, dist = _RNG.choice(lanes)
        transporter_name, transporter_sk = _RNG.choice(transporters)
        shipper_name, shipper_sk = _RNG.choice(shippers)
        booking = _ts(i * 30)
        start = booking + timedelta(minutes=_RNG.randint(15, 120))
        planned_eta = start + timedelta(hours=dist / 50)
        delay = _RNG.choice([-10, 0, 0, 15, 45, 90, 180])
        actual_arrival = planned_eta + timedelta(minutes=delay)
        actual_end = actual_arrival + timedelta(minutes=_RNG.randint(30, 90))
        num_legs = _RNG.choice([1, 1, 1, 2, 3])
        status = _RNG.choice(["IN_TRANSIT", "DELIVERED", "DELIVERED", "PLANNED"])

        rows.append({
            "trip_no": 100000 + i,
            "trip_uuid": _hash(f"trip-{i}"),
            "vehicle_sk": 5000 + (i % 20),
            "vehicle_id": f"MH12AB{1000 + i:04d}",
            "driver_sk": 7000 + (i % 15),
            "driver_name": f"Driver {i % 15 + 1}",
            "driver_mobile": f"+9198{_RNG.randint(10000000, 99999999)}",
            "transporter_sk": transporter_sk,
            "transporter_name": transporter_name,
            "transporter_code": transporter_name.upper()[:3],
            "shipper_sk": shipper_sk,
            "shipper_name": shipper_name,
            "consigner_sk": shipper_sk,
            "consigner_name": shipper_name,
            "origin_geofence_sk": hash(origin) % 10000,
            "origin_text": origin,
            "origin_pin_code": _RNG.randint(110000, 999999),
            "priority": _RNG.choice(["HIGH", "MEDIUM", "LOW"]),
            "tag": _RNG.choice(["", "FRAGILE", "HAZMAT", "EXPORT"]),
            "service_provider": transporter_name,
            "trip_type": _RNG.choice(["FTL", "LTL"]),
            "trip_type_desc": "Full Truck Load",
            "route_id": hash(f"{origin}-{dest}") % 100000,
            "trip_booking_ts": booking,
            "trip_start_ts": start,
            "trip_planned_eta_ts": planned_eta,
            "trip_derived_eta_ts": planned_eta + timedelta(minutes=delay // 2),
            "trip_actual_arrival_ts": actual_arrival if status == "DELIVERED" else None,
            "trip_actual_end_ts": actual_end if status == "DELIVERED" else None,
            "gate_in_ts": start - timedelta(minutes=20),
            "total_distance_km": float(dist),
            "lifecycle_status": status,
            "close_reason": "DELIVERED" if status == "DELIVERED" else None,
            "running_status": _RNG.choice(["MOVING", "STOPPED", "IDLE", "AT_CONSIGNEE"]),
            "running_status_raw": "",
            "delay_minutes": delay,
            "num_legs": num_legs,
            "num_legs_delivered": num_legs if status == "DELIVERED" else _RNG.randint(0, num_legs),
            "last_seen_in_api": datetime.now(),
            "card_id": None,
            "domain_name": "nextgen-fms",
            "multi_trip": 1 if num_legs > 1 else 0,
            "source_system": "mock",
            "source_payload_hash": _hash(f"payload-{i}"),
            "pipeline_run_id": "mock-run-001",
            "ingested_at": datetime.now(),
            "updated_at": datetime.now(),
            "schema_version": 1,
            "extra_data": None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# fact_trip_legs  — one row per leg of a trip
# ---------------------------------------------------------------------------
def mock_fact_trip_legs(trips: pd.DataFrame | None = None) -> pd.DataFrame:
    trips = trips if trips is not None else mock_fact_trips()
    consignees = ["Plant-A", "Plant-B", "Warehouse-X", "Warehouse-Y", "Retailer-Z"]
    rows = []
    for _, t in trips.iterrows():
        for seq in range(1, int(t["num_legs"]) + 1):
            leg_planned = t["trip_start_ts"] + timedelta(
                hours=(t["total_distance_km"] / 50) * (seq / t["num_legs"])
            )
            detention = _RNG.choice([0, 15, 45, 90, 240])
            rows.append({
                "trip_no": t["trip_no"],
                "leg_seq": seq,
                "shipment_id": f"SHP{t['trip_no']}-{seq}",
                "leg_uuid": _hash(f"{t['trip_no']}-{seq}"),
                "consignee_sk": hash(consignees[seq % len(consignees)]) % 10000,
                "consignee_name": consignees[seq % len(consignees)],
                "consignee_pin": _RNG.randint(110000, 999999),
                "dest_geofence_sk": hash(consignees[seq % len(consignees)]) % 10000,
                "dest_node_name": consignees[seq % len(consignees)],
                "dest_text": consignees[seq % len(consignees)],
                "final_dest": consignees[-1] if seq == t["num_legs"] else None,
                "leg_planned_eta_ts": leg_planned,
                "leg_derived_eta_ts": leg_planned + timedelta(minutes=_RNG.randint(-15, 60)),
                "leg_actual_arrival_ts": leg_planned + timedelta(minutes=_RNG.randint(-20, 120)),
                "leg_plant_in_ts": leg_planned + timedelta(minutes=_RNG.randint(0, 30)),
                "leg_pod_received_ts": leg_planned + timedelta(hours=_RNG.randint(1, 6)),
                "planned_distance_km": t["total_distance_km"] / t["num_legs"],
                "covered_distance_km": (t["total_distance_km"] / t["num_legs"]) * _RNG.uniform(0.0, 1.0),
                "pct_complete": _RNG.uniform(0.0, 1.0),
                "lrgr_no": f"LR{t['trip_no']}{seq}",
                "material_text": _RNG.choice(["Steel pipes", "FMCG goods", "Cement", "Auto parts"]),
                "invoice_numbers": f"INV{_RNG.randint(10000, 99999)}",
                "invoice_raw": None,
                "invoice_qty": float(_RNG.randint(10, 200)),
                "waybill_no": f"EWB{_RNG.randint(100000000000, 999999999999)}",
                "waybill_validity_ts": leg_planned + timedelta(days=3),
                "gate_entry_no": f"GE{_RNG.randint(1000, 9999)}",
                "trip_type_desc": t["trip_type_desc"],
                "supplier_mat_owner": t["shipper_name"],
                "event_code": None,
                "plant_detention_mins": detention,
                "plant_detention_raw": str(detention),
                "leg_status": _RNG.choice(["IN_TRANSIT", "DELIVERED"]),
                "leg_running_status": _RNG.choice(["MOVING", "AT_CONSIGNEE", "STOPPED"]),
                "leg_delay_minutes": _RNG.randint(-15, 120),
                "source_system": "mock",
                "source_payload_hash": _hash(f"leg-{t['trip_no']}-{seq}"),
                "last_seen_in_api": datetime.now(),
                "pipeline_run_id": "mock-run-001",
                "ingested_at": datetime.now(),
                "updated_at": datetime.now(),
                "schema_version": 1,
                "extra_data": None,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# gps_telemetry_events  — rich per-ping stream
# ---------------------------------------------------------------------------
def mock_gps_telemetry_events(trips: pd.DataFrame | None = None, pings_per_trip: int = 30) -> pd.DataFrame:
    trips = trips if trips is not None else mock_fact_trips(n=10)
    rows = []
    for _, t in trips.iterrows():
        lat0, lng0 = 19.0760, 72.8777   # start anywhere
        odo = float(_RNG.randint(50_000, 250_000))
        fuel_pct = 95.0
        for i in range(pings_per_trip):
            ts = t["trip_start_ts"] + timedelta(minutes=i * 10)
            lat = lat0 + i * 0.005
            lng = lng0 + i * 0.005
            speed = max(0.0, _RNG.gauss(55, 15))
            ignition = 1 if speed > 1 else _RNG.choice([0, 1])
            distance_step = (speed * 10) / 60
            odo += distance_step
            fuel_pct = max(0.0, fuel_pct - distance_step * 0.04 - _RNG.uniform(0, 0.05))
            rows.append({
                "vehicle_id": t["vehicle_id"],
                "entity_id": int(t["vehicle_sk"]),
                "entity_name": t["transporter_name"],
                "device_id": f"DEV-{t['vehicle_sk']}",
                "gps_timestamp": ts,
                "server_timestamp": ts + timedelta(seconds=_RNG.randint(1, 5)),
                "latitude": lat,
                "longitude": lng,
                "speed": float(speed),
                "heading": _RNG.randint(0, 359),
                "ignition_status": ignition,
                "odometer": odo,
                "altitude": float(_RNG.randint(0, 800)),
                "hdop": round(_RNG.uniform(0.8, 3.5), 2),
                "satellites": _RNG.randint(4, 12),
                "fuel_level_pct": round(fuel_pct, 2),
                "fuel_liters": round(fuel_pct * 4.0, 2),
                "engine_rpm": _RNG.randint(700, 2400) if ignition else 0,
                "battery_voltage": round(_RNG.uniform(12.0, 14.2), 2),
                "driver_id": str(t["driver_sk"]),
                "signal_strength": _RNG.randint(-110, -60),
                "geofence_id": None,
                "trip_id": str(t["trip_no"]),
                "motion_status": "MOVING" if speed > 5 else ("IDLE" if ignition else "STOPPED"),
                "road_speed_limit": _RNG.choice([60, 80, 100]),
                "schema_version": 1,
                "_event_id": _hash(f"{t['vehicle_id']}-{ts.isoformat()}"),
                "_ingested_at": datetime.now(),
                "_is_late": False,
                "_schema_version": 1,
                "extra_data": None,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# gps_events  — lean per-ping stream
# ---------------------------------------------------------------------------
def mock_gps_events(rich: pd.DataFrame | None = None) -> pd.DataFrame:
    rich = rich if rich is not None else mock_gps_telemetry_events()
    cols = [
        "vehicle_id", "entity_id", "entity_name", "device_id",
        "gps_timestamp", "server_timestamp", "latitude", "longitude",
        "speed", "heading", "ignition_status", "odometer",
        "_event_id", "_ingested_at", "_schema_version",
    ]
    df = rich[cols].copy()
    df["gps_timestamp"] = df["gps_timestamp"].astype(str)
    df["server_timestamp"] = df["server_timestamp"].astype(str)
    df["heading"] = df["heading"].astype(str)
    df["ignition_status"] = df["ignition_status"].astype(str)
    df["_ingested_at"] = df["_ingested_at"].astype(str)
    return df


# ---------------------------------------------------------------------------
# trip_detail  — waypoint stream
# ---------------------------------------------------------------------------
def mock_trip_detail(rich: pd.DataFrame | None = None) -> pd.DataFrame:
    rich = rich if rich is not None else mock_gps_telemetry_events()
    rows = []
    for trip_id, group in rich.groupby("trip_id"):
        for seq, (_, p) in enumerate(group.iterrows(), start=1):
            event_type = "MOVING"
            if seq == 1:
                event_type = "START"
            elif seq == len(group):
                event_type = "STOP"
            elif p["speed"] > p["road_speed_limit"]:
                event_type = "OVERSPEED"
            rows.append({
                "trip_id": trip_id,
                "sequence_no": seq,
                "gps_timestamp": p["gps_timestamp"],
                "latitude": p["latitude"],
                "longitude": p["longitude"],
                "speed": p["speed"],
                "heading": p["heading"],
                "ignition_status": p["ignition_status"],
                "odometer": p["odometer"],
                "event_type": event_type,
                "_event_id": p["_event_id"],
                "_ingested_at": p["_ingested_at"],
                "_schema_version": 1,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# trip_header  — lightweight trip view
# ---------------------------------------------------------------------------
def mock_trip_header(trips: pd.DataFrame | None = None) -> pd.DataFrame:
    trips = trips if trips is not None else mock_fact_trips()
    return pd.DataFrame([{
        "trip_id": str(t["trip_no"]),
        "vehicle_id": t["vehicle_id"],
        "driver_id": str(t["driver_sk"]),
        "start_time": t["trip_start_ts"],
        "end_time": t["trip_actual_end_ts"],
        "start_odometer": _RNG.uniform(50_000, 250_000),
        "end_odometer": _RNG.uniform(50_000, 250_000) + t["total_distance_km"],
        "start_location": t["origin_text"],
        "end_location": "Destination",
        "status": t["lifecycle_status"],
        "_event_id": _hash(f"th-{t['trip_no']}"),
        "_ingested_at": datetime.now(),
        "_schema_version": 1,
    } for _, t in trips.iterrows()])


# ---------------------------------------------------------------------------
# Lookup helper used by all three clients
# ---------------------------------------------------------------------------
TABLE_BUILDERS = {
    "fact_trips": mock_fact_trips,
    "fact_trip_legs": mock_fact_trip_legs,
    "gps_telemetry_events": mock_gps_telemetry_events,
    "gps_events": mock_gps_events,
    "trip_detail": mock_trip_detail,
    "trip_header": mock_trip_header,
}


def get_mock_table(name: str) -> pd.DataFrame:
    """Return data for a table.
    Resolution order:
      1. **Live Iceberg** (if USE_MOCK_DATA=false). Returns instantly if empty.
      2. **Sample file** under sample_data/ — faithful to the lakehouse schema,
         preserves null columns so data-quality view stays honest.
      3. **Derived sample** for trip_detail / trip_header.
      4. **Synthetic** fallback so the UI always has something to render.
    """
    # Lazy imports to avoid circular dependency
    from lakehouse import sample_loader
    from lakehouse.settings import get_settings

    # 1. Live Iceberg — only when explicitly enabled with real creds.
    _settings = get_settings()
    if not _settings.use_mock_data and not _settings.disable_iceberg:
        try:
            from lakehouse.pyiceberg_client import PyIcebergClient
            df = PyIcebergClient().read_table(name)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass  # any failure → fall through to sample / synthetic

    # 2. Sample file
    if name in {"fact_trips", "fact_trip_legs", "gps_events", "gps_telemetry_events"}:
        real = sample_loader.load(name)
        if real is not None and not real.empty:
            return real

    # 3. Derived
    if name == "trip_detail":
        derived = sample_loader.derive_trip_detail()
        if not derived.empty:
            return derived
    if name == "trip_header":
        derived = sample_loader.derive_trip_header()
        if not derived.empty:
            return derived

    # 4. Synthetic
    if name not in TABLE_BUILDERS:
        raise KeyError(f"Unknown telemetry table: {name}. Known: {list(TABLE_BUILDERS)}")
    return TABLE_BUILDERS[name]()
