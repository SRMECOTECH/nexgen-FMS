"""
Reusable enrichment services lifted out of legacy_viz so they can be called
from anywhere — FastAPI routes, the Streamlit deep-dive page, MCP tools,
batch jobs, etc. Each service is trip-aware: you hand it a trip_id (or a
segment_id) and it does the right thing.

  weather   — historical weather along a trip's route at the trip's own dates
  geocoding — reverse-geocode trip start/end + segment endpoints (Nominatim)
  landmarks — fuel / restaurant / hotel / parking POIs near the polyline

All three cache to MySQL so re-runs are free.
"""
