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
    detect_segments,
    detect_trips,         # deprecated alias of detect_segments
    summarize_trip,
    aggregate_to_time_windows,
    NormalizedFrame,
    DetectedSegment,
    DetectedTrip,         # deprecated alias of DetectedSegment
    TripSummary,
)
from route_intelligence.analyzers import (
    BusinessAnalyzer,
    RouteAnalyzer,
    WaypointAnalyzer,
)

__all__ = [
    "load_gps_excel",
    "detect_segments",
    "detect_trips",
    "summarize_trip",
    "aggregate_to_time_windows",
    "NormalizedFrame",
    "DetectedSegment",
    "DetectedTrip",
    "TripSummary",
    "BusinessAnalyzer",
    "RouteAnalyzer",
    "WaypointAnalyzer",
]
