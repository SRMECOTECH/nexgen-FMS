"""
Route Intelligence package for nextGen-FMS.

Excel upload → schema adapter → trip auto-detection → analyzers
(business cost, route efficiency, waypoints, speed zones, traffic) →
MySQL result store → AI insights (local LLM) → REST API → UI.

All math is pure functions on pandas DataFrames; figures are built in
the React frontend with Recharts.
"""

from route_intelligence.data_adapter import (
    load_gps_excel,
    detect_trips,
    aggregate_to_time_windows,
    NormalizedFrame,
    DetectedTrip,
)
from route_intelligence.analyzers import (
    BusinessAnalyzer,
    RouteAnalyzer,
    WaypointAnalyzer,
)

__all__ = [
    "load_gps_excel",
    "detect_trips",
    "aggregate_to_time_windows",
    "NormalizedFrame",
    "DetectedTrip",
    "BusinessAnalyzer",
    "RouteAnalyzer",
    "WaypointAnalyzer",
]
