"""
Pure-math analyzers for route intelligence. No Streamlit, no Plotly, no I/O —
just functions on DataFrames that return JSON-serialisable dicts/lists.

Three layers:
    BusinessAnalyzer  — cost model (fuel + driver, idle waste, savings opps)
    RouteAnalyzer     — efficiency, backtracking, speed zones, traffic loss
    WaypointAnalyzer  — consolidate the corridor labels into a journey
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import radians, sin, cos, sqrt, atan2, degrees
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from route_intelligence import cost_config
from route_intelligence import osrm_gateway


# ============================================================================
# Business: cost model
# ============================================================================
@dataclass
class CostParams:
    # Defaults pull from the live, UI-editable config so a BusinessAnalyzer()
    # built without explicit params still uses the configured numbers.
    fuel_price_per_liter: float = None  # type: ignore[assignment]
    fuel_efficiency_kmpl: float = None  # type: ignore[assignment]
    driver_wage_per_hour: float = None  # type: ignore[assignment]
    idle_fuel_consumption_lph: float = None  # type: ignore[assignment]

    def __post_init__(self):
        cfg = cost_config.load()
        if self.fuel_price_per_liter is None:
            self.fuel_price_per_liter = cfg["fuel_price_per_liter"]
        if self.fuel_efficiency_kmpl is None:
            self.fuel_efficiency_kmpl = cfg["fuel_efficiency_kmpl"]
        if self.driver_wage_per_hour is None:
            self.driver_wage_per_hour = cfg["driver_wage_per_hour"]
        if self.idle_fuel_consumption_lph is None:
            self.idle_fuel_consumption_lph = cfg["idle_fuel_consumption_lph"]


class BusinessAnalyzer:
    def __init__(self, params: CostParams | None = None):
        self.p = params or CostParams()

    def calculate_journey_costs(self, df_agg: pd.DataFrame) -> Dict:
        total_distance = float(df_agg["total_distance_km"].sum())
        moving_hours = float(df_agg["moving_time_sec"].sum()) / 3600
        stopped_hours = float(df_agg["stopped_time_sec"].sum()) / 3600
        total_hours = moving_hours + stopped_hours

        moving_fuel = total_distance / self.p.fuel_efficiency_kmpl if self.p.fuel_efficiency_kmpl else 0
        idle_fuel = stopped_hours * self.p.idle_fuel_consumption_lph
        total_fuel = moving_fuel + idle_fuel
        fuel_cost = total_fuel * self.p.fuel_price_per_liter
        driver_cost = total_hours * self.p.driver_wage_per_hour
        total_cost = fuel_cost + driver_cost

        return {
            "total_distance_km": round(total_distance, 2),
            "moving_hours": round(moving_hours, 2),
            "stopped_hours": round(stopped_hours, 2),
            "total_hours": round(total_hours, 2),
            "fuel_consumed_liters": round(total_fuel, 2),
            "moving_fuel_liters": round(moving_fuel, 2),
            "idle_fuel_liters": round(idle_fuel, 2),
            "fuel_cost_inr": round(fuel_cost, 2),
            "driver_cost_inr": round(driver_cost, 2),
            "total_cost_inr": round(total_cost, 2),
            "idle_fuel_waste_inr": round(idle_fuel * self.p.fuel_price_per_liter, 2),
            "cost_per_km": round(total_cost / total_distance, 2) if total_distance > 0 else 0,
            "efficiency_pct": round(moving_hours / total_hours * 100, 1) if total_hours > 0 else 0,
        }

    def cost_savings_opportunities(self, df_agg: pd.DataFrame) -> List[Dict]:
        # Live, UI-editable thresholds & multipliers (see route_intelligence/cost_config.py).
        cfg = cost_config.load()
        month = cfg["trips_per_month"]

        opps: List[Dict] = []
        stopped_hours = float(df_agg["stopped_time_sec"].sum()) / 3600
        moving_hours = float(df_agg["moving_time_sec"].sum()) / 3600

        if stopped_hours > cfg["idle_hours_trigger"]:
            idle_waste = stopped_hours * self.p.idle_fuel_consumption_lph * self.p.fuel_price_per_liter
            pct = cfg["idle_savings_pct"]
            potential = idle_waste * pct
            opps.append({
                "category": "Idle Time Reduction",
                "priority": "HIGH",
                "current_waste_inr": round(idle_waste, 2),
                "potential_savings_inr": round(potential, 2),
                "monthly_savings_inr": round(potential * month, 2),
                "recommendation": f"Reduce idle time by {pct * 100:.0f}% (save ₹{potential:.0f}/trip).",
                # trigger evidence — powers the detailed report
                "metrics": {"stopped_hours": round(stopped_hours, 2),
                            "trigger": f"idle > {cfg['idle_hours_trigger']}h"},
            })

        speed_target = cfg["speed_target_kmph"]
        if len(df_agg) and float(df_agg["avg_moving_speed_kmph"].mean()) < speed_target:
            avg_speed = float(df_agg["avg_moving_speed_kmph"].mean())
            time_saved = moving_hours * cfg["route_opt_time_saved_pct"]
            savings = time_saved * self.p.driver_wage_per_hour
            opps.append({
                "category": "Route Optimization",
                "priority": "MEDIUM",
                "current_waste_inr": 0,
                "potential_savings_inr": round(savings, 2),
                "monthly_savings_inr": round(savings * month, 2),
                "recommendation": f"Reroute or coach driver to lift average moving speed to ~{speed_target:.0f} km/h.",
                "metrics": {"avg_moving_speed_kmph": round(avg_speed, 1),
                            "trigger": f"avg speed < {speed_target:.0f} km/h"},
            })

        h_start, h_end = cfg["peak_hour_start"], cfg["peak_hour_end"]
        peak = df_agg[(df_agg["window_start"].dt.hour >= h_start) & (df_agg["window_start"].dt.hour <= h_end)]
        peak_share = (len(peak) / len(df_agg)) if len(df_agg) else 0.0
        if len(df_agg) and peak_share > cfg["peak_share_trigger"]:
            opps.append({
                "category": "Peak Hour Avoidance",
                "priority": "MEDIUM",
                "current_waste_inr": 0,
                "potential_savings_inr": cfg["peak_per_trip_savings_inr"],
                "monthly_savings_inr": cfg["peak_monthly_savings_inr"],
                "recommendation": f"Start trips before {h_start} AM to dodge peak-hour congestion.",
                "metrics": {"peak_window_share_pct": round(peak_share * 100, 1),
                            "trigger": f">{cfg['peak_share_trigger'] * 100:.0f}% of windows in {h_start}-{h_end}h"},
            })

        return opps

    def compare(self, routes: List[Tuple[str, pd.DataFrame]]) -> pd.DataFrame:
        """``routes`` = list of (label, df_agg) tuples → ranked comparison DF."""
        rows = []
        for label, df_agg in routes:
            costs = self.calculate_journey_costs(df_agg)
            total_distance = float(df_agg["total_distance_km"].sum())
            moving_hours = float(df_agg["moving_time_sec"].sum()) / 3600
            stopped_hours = float(df_agg["stopped_time_sec"].sum()) / 3600
            total_hours = moving_hours + stopped_hours
            rows.append({
                "Route": label,
                "Distance (km)": round(total_distance, 2),
                "Duration (hrs)": round(total_hours, 2),
                "Moving Time (hrs)": round(moving_hours, 2),
                "Idle Time (hrs)": round(stopped_hours, 2),
                "Avg Speed (km/h)": round(float(df_agg["avg_speed_kmph"].mean()), 1),
                "Moving Speed (km/h)": round(float(df_agg["avg_moving_speed_kmph"].mean()), 1),
                "Total Cost (₹)": costs["total_cost_inr"],
                "Fuel Cost (₹)": costs["fuel_cost_inr"],
                "Idle Waste (₹)": costs["idle_fuel_waste_inr"],
                "Cost/km (₹)": costs["cost_per_km"],
                "Efficiency (%)": costs["efficiency_pct"],
            })
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["Cost Rank"] = df["Total Cost (₹)"].rank()
        df["Time Rank"] = df["Duration (hrs)"].rank()
        df["Efficiency Rank"] = df["Efficiency (%)"].rank(ascending=False)
        # Weighted score (higher = better)
        df["Overall Score"] = (
            (1 / df["Cost Rank"]) * 0.4
            + (1 / df["Time Rank"]) * 0.3
            + (1 / df["Efficiency Rank"]) * 0.3
        ).round(3)
        return df


# ============================================================================
# Route: efficiency, speed zones, traffic, backtracking
# ============================================================================
class RouteAnalyzer:
    @staticmethod
    def route_efficiency(df: pd.DataFrame) -> Dict:
        if df.empty or "latitude" not in df or "longitude" not in df:
            return {"error": "GPS coordinates missing"}
        s_lat, s_lon = float(df.iloc[0]["latitude"]), float(df.iloc[0]["longitude"])
        e_lat, e_lon = float(df.iloc[-1]["latitude"]), float(df.iloc[-1]["longitude"])
        straight = _haversine(s_lat, s_lon, e_lat, e_lon)
        actual = float(df["Distance_km"].sum()) if "Distance_km" in df else 0.0

        # Baseline for "excess" is the OPTIMAL ROAD distance from OSRM when the
        # engine is reachable (a real, drivable lower bound), and only falls back
        # to the haversine straight line when OSRM is unavailable. Comparing the
        # driven distance to the road optimum is far more meaningful than
        # comparing it to a straight line that no truck could ever drive.
        osrm = osrm_gateway.road_distance_km([(s_lat, s_lon), (e_lat, e_lon)])
        if osrm and osrm.get("road_distance_km"):
            baseline = float(osrm["road_distance_km"])
            baseline_source = "osrm_road"
        else:
            baseline = straight
            baseline_source = "straight_line"

        eff = baseline / actual if actual > 0 else 0.0
        return {
            "straight_line_distance_km": round(straight, 2),
            "osrm_road_distance_km": round(float(osrm["road_distance_km"]), 2) if osrm and osrm.get("road_distance_km") else None,
            "baseline_distance_km": round(baseline, 2),
            "baseline_source": baseline_source,
            "actual_distance_km": round(actual, 2),
            "route_efficiency": round(eff, 3),
            "excess_distance_km": round(actual - baseline, 2),
            "excess_percentage": round((1 - eff) * 100, 1) if eff else 0.0,
            "interpretation": _interpret_efficiency(eff),
        }

    @staticmethod
    def speed_zones(df: pd.DataFrame) -> Dict:
        if "Speed_kmh" not in df:
            return {"error": "Speed data missing"}
        speeds = df.loc[df["Speed_kmh"] > 0, "Speed_kmh"]
        if speeds.empty:
            return {"error": "No movement"}
        total = len(speeds)
        slow = (speeds < 20).sum()
        moderate = ((speeds >= 20) & (speeds < 60)).sum()
        normal = ((speeds >= 60) & (speeds < 80)).sum()
        high = (speeds >= 80).sum()
        std = float(speeds.std())
        return {
            "avg_speed_kmph": round(float(speeds.mean()), 1),
            "max_speed_kmph": round(float(speeds.max()), 1),
            "min_speed_kmph": round(float(speeds.min()), 1),
            "speed_std_dev": round(std, 1),
            "slow_zone_pct": round(slow / total * 100, 1),
            "moderate_zone_pct": round(moderate / total * 100, 1),
            "normal_zone_pct": round(normal / total * 100, 1),
            "high_zone_pct": round(high / total * 100, 1),
            "speed_consistency": "High" if std < 15 else "Moderate" if std < 25 else "Low",
        }

    @staticmethod
    def traffic_loss(df: pd.DataFrame, slow_threshold_kmph: int = 15) -> Dict:
        if "Speed_kmh" not in df or "Time_Diff_Seconds" not in df:
            return {"error": "Speed/time columns missing"}
        mask = (df["Speed_kmh"] > 0) & (df["Speed_kmh"] < slow_threshold_kmph)
        seg = df[mask]
        if seg.empty:
            return {
                "time_lost_minutes": 0.0,
                "distance_in_traffic_km": 0.0,
                "traffic_segments": 0,
                "avg_traffic_speed_kmph": 0.0,
                "time_saved_if_no_traffic_minutes": 0.0,
            }
        time_lost_sec = float(seg["Time_Diff_Seconds"].sum())
        dist_traffic = float(seg["Distance_km"].sum()) if "Distance_km" in seg else 0.0
        normal_hours = dist_traffic / 50  # baseline 50 km/h
        actual_hours = time_lost_sec / 3600
        saved_min = max(0.0, actual_hours - normal_hours) * 60
        return {
            "time_lost_minutes": round(time_lost_sec / 60, 1),
            "distance_in_traffic_km": round(dist_traffic, 2),
            "traffic_segments": int(len(seg)),
            "avg_traffic_speed_kmph": round(float(seg["Speed_kmh"].mean()), 1),
            "time_saved_if_no_traffic_minutes": round(saved_min, 1),
        }

    @staticmethod
    def backtracking_events(df: pd.DataFrame, sample_step: int = 1) -> List[Dict]:
        """Return positions (idx, lat, lng, ts, bearing_change_deg) where the
        course reverses by >135°. Sample every Nth point for very dense feeds."""
        if len(df) < 3:
            return []
        out: List[Dict] = []
        # Downsample using indices
        idx = list(range(0, len(df), sample_step))
        for k in range(1, len(idx) - 1):
            i0, i1, i2 = idx[k - 1], idx[k], idx[k + 1]
            r0 = df.iloc[i0]; r1 = df.iloc[i1]; r2 = df.iloc[i2]
            b1 = _bearing(r0["latitude"], r0["longitude"], r1["latitude"], r1["longitude"])
            b2 = _bearing(r1["latitude"], r1["longitude"], r2["latitude"], r2["longitude"])
            diff = abs(((b2 - b1 + 180) % 360) - 180)  # smallest signed diff
            if diff > 135:
                out.append({
                    "idx": int(i1),
                    "ts": str(r1["Date Time"]),
                    "lat": float(r1["latitude"]),
                    "lng": float(r1["longitude"]),
                    "bearing_change_deg": round(diff, 1),
                })
        return out

    @staticmethod
    def stop_clusters(df: pd.DataFrame, min_stops: int = 3) -> List[Dict]:
        if "Is_Moving" not in df:
            return []
        stops = df[df["Is_Moving"] == 0].copy()
        if len(stops) < min_stops:
            return []
        stops["lat_r"] = stops["latitude"].round(2)
        stops["lon_r"] = stops["longitude"].round(2)
        grp = (
            stops.groupby(["lat_r", "lon_r"])
            .agg(stop_count=("Date Time", "size"),
                 first=("Date Time", "min"),
                 last=("Date Time", "max"),
                 lat=("latitude", "mean"),
                 lng=("longitude", "mean"))
            .reset_index()
        )
        grp = grp[grp["stop_count"] >= min_stops]
        return [
            {
                "lat": float(r["lat"]),
                "lng": float(r["lng"]),
                "stop_count": int(r["stop_count"]),
                "first_visit": str(r["first"]),
                "last_visit": str(r["last"]),
            }
            for _, r in grp.iterrows()
        ]


# ============================================================================
# Waypoint: consolidate corridor labels into a journey
# ============================================================================
class WaypointAnalyzer:
    @staticmethod
    def consolidate(df: pd.DataFrame) -> List[Dict]:
        """Collapse consecutive rows that share Waypoint1 into one visit row.
        Produces a journey table the UI can render as the waypoint timeline."""
        if "Waypoint1" not in df.columns or df["Waypoint1"].isna().all():
            return []
        d = df.copy()
        d["wp"] = d["Waypoint1"].fillna("UNKNOWN").astype(str)
        d["group_id"] = (d["wp"] != d["wp"].shift()).cumsum()

        out = []
        cum_km = 0.0
        for gid, seg in d.groupby("group_id", sort=False):
            wp = str(seg["wp"].iloc[0])
            if wp == "UNKNOWN":
                continue
            arrive = seg["Date Time"].iloc[0]
            depart = seg["Date Time"].iloc[-1]
            dist = float(seg["Distance_km"].sum()) if "Distance_km" in seg else 0.0
            cum_km += dist
            time_min = (depart - arrive).total_seconds() / 60
            moving = seg[seg["Is_Moving"] == 1]["Speed_kmh"] if "Is_Moving" in seg else pd.Series(dtype=float)
            out.append({
                "seq": len(out) + 1,
                "waypoint": wp,
                "arrive_ts": str(arrive),
                "depart_ts": str(depart),
                "time_spent_min": round(time_min, 1),
                "distance_km": round(dist, 2),
                "cumulative_distance_km": round(cum_km, 2),
                "avg_speed_kmph": round(float(moving.mean()) if len(moving) else 0.0, 1),
                "lat": float(seg["latitude"].mean()),
                "lng": float(seg["longitude"].mean()),
                "n_points": int(len(seg)),
            })
        return out

    @staticmethod
    def by_day(df: pd.DataFrame) -> List[Dict]:
        """Per-day breakdown of a trip's GPS frame. Each output row covers a
        single calendar day and reports distance, moving/stopped time, ping
        count, max speed, and waypoints touched on that day. Multi-day trips
        produce N rows; single-day trips produce 1."""
        if df.empty or "Date Time" not in df.columns:
            return []
        d = df.copy()
        d["date"] = pd.to_datetime(d["Date Time"]).dt.date
        out: List[Dict] = []
        for day, sub in d.groupby("date", sort=True):
            moving_sec = float(sub.loc[sub["Is_Moving"] == 1, "Time_Diff_Seconds"].sum()) \
                if "Is_Moving" in sub and "Time_Diff_Seconds" in sub else 0.0
            stopped_sec = float(sub.loc[sub["Is_Moving"] == 0, "Time_Diff_Seconds"].sum()) \
                if "Is_Moving" in sub and "Time_Diff_Seconds" in sub else 0.0
            dist_km = float(sub["Distance_km"].sum()) if "Distance_km" in sub else 0.0
            moving_speeds = sub.loc[sub["Is_Moving"] == 1, "Speed_kmh"] \
                if "Is_Moving" in sub and "Speed_kmh" in sub else pd.Series(dtype=float)
            waypoints = (
                sorted(set(sub["Waypoint1"].dropna().astype(str).tolist()))
                if "Waypoint1" in sub else []
            )
            out.append({
                "date": day.isoformat(),
                "day_of_week": pd.Timestamp(day).day_name(),
                "n_pings": int(len(sub)),
                "distance_km": round(dist_km, 2),
                "moving_min": round(moving_sec / 60, 1),
                "stopped_min": round(stopped_sec / 60, 1),
                "duration_min": round((moving_sec + stopped_sec) / 60, 1),
                "avg_moving_kmph": round(float(moving_speeds.mean()) if len(moving_speeds) else 0.0, 1),
                "max_speed_kmph": round(float(sub["Speed_kmh"].max()) if "Speed_kmh" in sub else 0.0, 1),
                "first_ts": str(sub["Date Time"].min()),
                "last_ts":  str(sub["Date Time"].max()),
                "waypoints_touched": waypoints[:12],   # keep it reasonable
                "n_waypoints": len(waypoints),
            })
        return out

    @staticmethod
    def segments_between(df: pd.DataFrame) -> List[Dict]:
        """Distances and durations between consecutive consolidated waypoints."""
        wp = WaypointAnalyzer.consolidate(df)
        if len(wp) < 2:
            return []
        out = []
        for a, b in zip(wp[:-1], wp[1:]):
            d = _haversine(a["lat"], a["lng"], b["lat"], b["lng"])
            t = (pd.to_datetime(b["arrive_ts"]) - pd.to_datetime(a["depart_ts"])).total_seconds() / 60
            speed = d / (t / 60) if t > 0 else 0
            out.append({
                "from": a["waypoint"],
                "to": b["waypoint"],
                "distance_km": round(d, 2),
                "duration_min": round(t, 1),
                "avg_speed_kmph": round(speed, 1),
            })
        return out


# ============================================================================
# helpers
# ============================================================================
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (degrees(atan2(x, y)) + 360) % 360


def _interpret_efficiency(eff: float) -> str:
    if eff >= 0.9:
        return "Excellent — very direct route"
    if eff >= 0.75:
        return "Good — minor detours"
    if eff >= 0.6:
        return "Fair — some indirect routing"
    return "Poor — significant detours or backtracking"
