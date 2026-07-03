"""
Detailed Analysis of GPS Data — Streamlit deep-dive page.

Adapted from the original Route Intelligence Analyzer. Key differences:
  * imports live under ``route_intelligence.legacy_viz.*`` inside nextGen-FMS
  * upload parser uses ``route_intelligence.data_adapter.load_gps_excel`` so
    the vendor schema (``s_asset_id, dt_message, i_lat, i_long, i_corrt_speed,
    i_distance, s_wpnt1, s_wpnt2``) just works. Legacy files with
    ``Asset Number / Date Time / Latitude / Longitude / Distance / Status``
    still load via the original code path as a fallback.
  * cost / window / column / threshold defaults all come from
    ``config/route_intel.yaml``.
"""

# Make project root importable when this file is launched by `streamlit run`
import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go

# Route intelligence — legacy_viz (Plotly/folium heavy) + the new adapter
from route_intelligence.legacy_viz.geocoder import ReverseGeocoder
from route_intelligence.legacy_viz.landmark_finder import LandmarkFinder
from route_intelligence.legacy_viz.route_analyzer import RouteAnalyzer
from route_intelligence.legacy_viz.journey_planner import JourneyPlannerAgent
from route_intelligence.legacy_viz.business_analyzer import BusinessAnalyzer
from route_intelligence.legacy_viz.comparison_visualizer import ComparisonVisualizer
from route_intelligence.legacy_viz.enhanced_comparison import EnhancedComparison
from route_intelligence.legacy_viz.waypoint_analyser import WaypointAnalyzer
from route_intelligence.legacy_viz.weather_service import WeatherService

from route_intelligence import config as ricfg
from route_intelligence.data_adapter import load_gps_excel

# Page config
st.set_page_config(
    page_title="Detailed Analysis of GPS Data",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .speed-info-box {
        background-color: #e3f2fd;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #2196f3;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize services
@st.cache_resource
def init_services():
    """Initialize all route intelligence services"""
    return {
        'geocoder': ReverseGeocoder(),
        'landmark_finder': LandmarkFinder(),
        'route_analyzer': RouteAnalyzer(),
        'journey_planner': JourneyPlannerAgent(),
        'business_analyzer': BusinessAnalyzer(),
        'comparison_visualizer': ComparisonVisualizer(),
        'enhanced_comparison': EnhancedComparison(),
        'waypoint_analyzer': WaypointAnalyzer(),
        'weather_service': WeatherService()
    }

services = init_services()

def extract_speed(status_text):
    """Extract speed from status text"""
    if pd.isna(status_text):
        return 0
    status_str = str(status_text)
    if 'Moving' in status_str:
        try:
            parts = status_str.split()
            for part in parts:
                cleaned = part.replace('.', '', 1)
                if cleaned.isdigit():
                    return float(part)
        except Exception:
            pass
    return 0

def aggregate_to_time_windows(df, time_window='30min'):
    """Aggregate raw GPS data into time windows"""
    df["Time_Window"] = df["Date Time"].dt.floor(time_window)
    df["Time_Diff_Seconds"] = df["Date Time"].diff().dt.total_seconds().fillna(0)
    df["Is_Moving"] = (df["Speed_kmh"] > 0).astype(int)

    aggregated = df.groupby("Time_Window").agg(
        window_start=("Date Time", "min"),
        window_end=("Date Time", "max"),
        total_distance_km=("Distance_km", "sum"),
        max_speed_kmph=("Speed_kmh", "max"),
        moving_time_sec=("Time_Diff_Seconds", lambda x: x[df.loc[x.index, "Is_Moving"] == 1].sum()),
        stopped_time_sec=("Time_Diff_Seconds", lambda x: x[df.loc[x.index, "Is_Moving"] == 0].sum()),
        avg_moving_speed_kmph=("Speed_kmh", lambda x: x[x > 0].mean()),
        waypoint_count=("Date Time", "count"),
        latitude=("latitude", "mean"),
        longitude=("longitude", "mean")
    ).reset_index()

    aggregated["avg_moving_speed_kmph"] = aggregated["avg_moving_speed_kmph"].fillna(0)
    aggregated["max_speed_kmph"] = aggregated["max_speed_kmph"].fillna(0)

    total_time_hours = (aggregated['moving_time_sec'] + aggregated['stopped_time_sec']) / 3600
    aggregated['avg_speed_kmph'] = np.where(
        total_time_hours > 0,
        aggregated['total_distance_km'] / total_time_hours,
        0
    )

    aggregated["dominant_status"] = np.where(
        aggregated["moving_time_sec"] > aggregated["stopped_time_sec"],
        "Moving", "Stopped"
    )

    aggregated["window_label"] = (
        aggregated["window_start"].dt.strftime("%H:%M") + "–" +
        aggregated["window_end"].dt.strftime("%H:%M")
    )

    return aggregated

# Header
st.markdown('<p class="main-header">🗺️ Detailed Analysis of GPS Data</p>', unsafe_allow_html=True)
st.markdown(
    "**Complete fleet analytics for the nextGen-FMS route-intel pipeline — "
    "business intelligence, enhanced comparison, AI insights, waypoint analysis. "
    "Reads vendor `gpsfinal_*.xlsx` natively.**"
)

# ---- defaults from config/route_intel.yaml ----
_COST = ricfg.cost_defaults()
_AGG_DEFAULT = ricfg.default_window()
_AGG_CHOICES = ricfg.aggregation_choices()
_SAMPLE_FILE = ricfg.path("sample_file")

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/route.png", width=80)
    st.title("⚙️ Settings")

    st.subheader("📁 Data Upload")
    uploaded_files = st.file_uploader(
        "Upload Excel with GPS Data",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        help=(
            "ONE Excel = ONE trip. Long stops within the file are SEGMENTS of "
            "that trip, not separate trips. Upload multiple files to compare "
            "different trips side-by-side.\n\n"
            "Vendor schema: s_asset_id, dt_message, i_lat, i_long, i_corrt_speed, "
            "i_distance, s_wpnt1, s_wpnt2.  Legacy schema (Asset Number, Date Time, "
            "Latitude, Longitude, Distance, Status) also supported."
        )
    )
    use_sample = st.checkbox(
        f"…or use sample file ({_SAMPLE_FILE.name})",
        value=False,
        help=f"Loads {_SAMPLE_FILE} from disk — bypasses the upload dialog.",
    )

    st.subheader("💰 Cost Parameters")
    _cs = ricfg.section("cost")
    fuel_price = st.number_input("Diesel Price (₹/L)",
        value=_COST["fuel_price_per_liter"],
        min_value=float(_cs.get("fuel_price_min", 50.0)),
        max_value=float(_cs.get("fuel_price_max", 200.0)),
        step=float(_cs.get("fuel_price_step", 5.0)))
    fuel_efficiency = st.number_input("Fuel Efficiency (km/L)",
        value=_COST["fuel_efficiency_kmpl"],
        min_value=float(_cs.get("fuel_efficiency_min", 2.0)),
        max_value=float(_cs.get("fuel_efficiency_max", 8.0)),
        step=float(_cs.get("fuel_efficiency_step", 0.5)))
    driver_wage = st.number_input("Driver Wage (₹/hr)",
        value=_COST["driver_wage_per_hour"],
        min_value=float(_cs.get("driver_wage_min", 50.0)),
        max_value=float(_cs.get("driver_wage_max", 500.0)),
        step=float(_cs.get("driver_wage_step", 10.0)))

    services['business_analyzer'].fuel_price = fuel_price
    services['business_analyzer'].fuel_efficiency = fuel_efficiency
    services['business_analyzer'].driver_wage = driver_wage

    combine_routes = False
    if uploaded_files:
        st.success(f"📂 {len(uploaded_files)} file(s) uploaded")
        if len(uploaded_files) > 1:
            combine_routes = st.checkbox("Combine all routes into one", value=False)
    elif use_sample:
        st.info(f"📂 using sample: {_SAMPLE_FILE.name}")

    st.subheader("⏱️ Time Aggregation")
    time_window = st.selectbox(
        "Time Window for Aggregation",
        _AGG_CHOICES,
        index=max(0, _AGG_CHOICES.index(_AGG_DEFAULT)) if _AGG_DEFAULT in _AGG_CHOICES else 1,
        help="Aggregate GPS waypoints into time windows"
    )

    st.subheader("🎛️ Analysis Options")
    weather_enabled = st.checkbox("🌤️ Show Weather Info", value=True, help="Display current weather at source/destination locations")
    geocode_enabled = st.checkbox("🌍 Enable Geocoding", value=False)
    poi_enabled = st.checkbox("🏢 Find Landmarks/POIs", value=False)
    ai_enabled = st.checkbox("🤖 AI Journey Planner", value=False)

    if geocode_enabled:
        geocode_sample_rate = st.slider("Geocoding sample rate", 1, 20, 5)

    if poi_enabled:
        poi_radius = st.slider("POI search radius (m)", 500, 5000, 1500, step=500)
        poi_categories = st.multiselect(
            "POI Categories",
            ['fuel_stations', 'restaurants', 'hotels', 'rest_areas', 'parking', 'hospitals'],
            default=['fuel_stations', 'rest_areas']
        )

    st.markdown("---")
    st.caption("Built with ❤️ using Streamlit")

# Main content — accept either upload(s) OR the configured sample file
if (uploaded_files is None or len(uploaded_files) == 0) and not use_sample:
    st.info("👆 **Upload one or more Excel files with GPS data to begin analysis**")

    with st.expander("📊 Understanding Speed Metrics", expanded=True):
        st.markdown("""
        ### How This App Calculates Speed
        
        This app aggregates GPS waypoints into **time windows** (default: 30 minutes):
        
        1. **Effective Speed** (what you see as "Average Speed"):
           - Formula: `Total Distance / Total Time (including stops)`
           - Includes all stopped periods
        
        2. **Moving Speed** (shown separately):
           - Formula: `Average of actual speeds when vehicle is moving`
           - Excludes stopped periods
        
        **Why use time windows?**
        - Reduces data noise from GPS fluctuations
        - Provides cleaner patterns and trends
        - Matches how drivers actually experience journeys
        """)

    st.stop()

def _parse_one_excel(name: str, source) -> pd.DataFrame | None:
    """Return a normalized DataFrame from either the new vendor schema
    (s_asset_id, dt_message, i_lat, i_long, i_corrt_speed, i_distance, …)
    or the legacy schema (Asset Number, Date Time, Latitude, Longitude,
    Distance, Status). ``source`` is a file path or an UploadedFile."""
    # --- attempt vendor-schema adapter first ---
    try:
        # write UploadedFile to a temp path the adapter can re-open
        if hasattr(source, "read"):
            import tempfile, os as _os
            suf = "." + name.split(".")[-1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suf) as tmp:
                tmp.write(source.getbuffer() if hasattr(source, "getbuffer") else source.read())
                tmp_path = tmp.name
            try:
                nf = load_gps_excel(tmp_path)
            finally:
                try: _os.unlink(tmp_path)
                except Exception: pass
        else:
            nf = load_gps_excel(str(source))
        df = nf.df.copy()
        df["source_file"] = name
        return df
    except ValueError as exc_vendor:
        # not a vendor file — try legacy parser
        pass

    # --- legacy schema fallback (Asset Number / Date Time / ...) ---
    ext = name.split(".")[-1].lower()
    engine = "xlrd" if ext == "xls" else "openpyxl"
    if hasattr(source, "read"):
        if hasattr(source, "seek"):
            source.seek(0)
        df = pd.read_excel(source, engine=engine)
    else:
        df = pd.read_excel(source, engine=engine)
    required = ["Asset Number", "Date Time", "Latitude", "Longitude", "Distance", "Status"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"❌ File '{name}' isn't a vendor file and is also missing legacy columns: {missing}")
        return None
    df["Date Time"] = pd.to_datetime(df["Date Time"], format="%d-%b-%y %H:%M:%S", errors="coerce")
    df = df.rename(columns={"Latitude": "latitude", "Longitude": "longitude"})
    df = df.dropna(subset=["Date Time", "latitude", "longitude"]).sort_values("Date Time").reset_index(drop=True)
    df["Speed_kmh"] = df["Status"].apply(extract_speed)
    df["Distance_km"] = df["Distance"].astype(str).str.replace(" km", "", regex=False).astype(float)
    df["Time_Diff_Seconds"] = df["Date Time"].diff().dt.total_seconds().fillna(0).clip(lower=0)
    df["Is_Moving"] = (df["Speed_kmh"] > 0).astype(int)
    df["vehicle_id"] = df["Asset Number"].iloc[0]
    df["source_file"] = name
    return df


# Process uploaded file(s) — or the sample file when no upload was given
try:
    with st.spinner("📊 Processing GPS data with time-window aggregation..."):
        all_dataframes = []
        all_aggregated = []
        file_info = []

        # Build the work-list: real uploads, OR the sample file from config
        if uploaded_files and len(uploaded_files) > 0:
            work_items = [(uf.name, uf) for uf in uploaded_files]
        else:
            work_items = [(_SAMPLE_FILE.name, _SAMPLE_FILE)]

        # Normalise ``uploaded_files`` so the (large) block of legacy code below
        # that branches on ``len(uploaded_files)`` keeps working in sample-mode.
        if not uploaded_files:
            uploaded_files = ["__sample__"]  # placeholder of length 1

        for fname, src in work_items:
            df = _parse_one_excel(fname, src)
            if df is None:
                continue

            aggregated_df = aggregate_to_time_windows(df, time_window)
            aggregated_df['vehicle_id'] = df['vehicle_id'].iloc[0]
            aggregated_df['source_file'] = fname

            all_dataframes.append(df)
            all_aggregated.append(aggregated_df)

            file_info.append({
                'filename': fname,
                'vehicle_id': df['vehicle_id'].iloc[0],
                'waypoints': len(df),
                'aggregated_windows': len(aggregated_df),
                'start_time': df['Date Time'].min(),
                'end_time': df['Date Time'].max(),
                'distance_km': df['Distance_km'].sum(),
            })

        if not all_dataframes:
            st.error("❌ No valid data found in uploaded files")
            st.stop()

        if len(uploaded_files) > 1 and combine_routes:
            df_agg = pd.concat(all_aggregated, ignore_index=True).sort_values('window_start')
            df_raw = pd.concat(all_dataframes, ignore_index=True).sort_values('Date Time')
        else:
            df_agg = all_aggregated[0]
            df_raw = all_dataframes[0]

        st.session_state.aggregated_data = df_agg
        st.session_state.raw_data = df_raw
        st.session_state.all_aggregated = all_aggregated
        st.session_state.all_dataframes = all_dataframes
        st.session_state.file_info = file_info

        # Waypoint preprocessing
        waypoint_analyzer = services['waypoint_analyzer']

        # Preprocess individual trips
        all_waypoint_processed = []
        for df in all_dataframes:
            wp_processed = waypoint_analyzer.preprocess_waypoint_data(df)
            all_waypoint_processed.append(wp_processed)

        # Cumulative preprocessing for multiple trips
        if len(all_dataframes) > 1:
            combined_waypoint_df = waypoint_analyzer.cumulative_preprocessing_multiple_trips(all_dataframes)
            st.session_state.combined_waypoint_data = combined_waypoint_df

        st.session_state.waypoint_processed = all_waypoint_processed

    if len(uploaded_files) > 1:
        with st.expander("📋 Uploaded Files Summary", expanded=True):
            summary_df = pd.DataFrame(file_info)
            st.dataframe(summary_df, use_container_width=True)

    st.success(f"✅ Loaded {len(df_raw)} waypoints → Aggregated into {len(df_agg)} time windows ({time_window})")
    st.info(f"📅 Time range: {df_raw['Date Time'].min()} to {df_raw['Date Time'].max()}")

    # Weather Information Section
    if weather_enabled:
        weather_service = services['weather_service']

        def get_weather_emoji(weather_code):
            """Get emoji based on weather code"""
            emoji_map = {
                0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
                45: "🌫️", 48: "🌫️",
                51: "🌧️", 53: "🌧️", 55: "🌧️",
                61: "🌧️", 63: "🌧️", 65: "🌧️",
                71: "🌨️", 73: "🌨️", 75: "🌨️",
                80: "🌦️", 81: "🌦️", 82: "🌦️",
                95: "⛈️", 96: "⛈️", 99: "⛈️"
            }
            return emoji_map.get(weather_code, "🌡️")

        def display_weather_card(weather_data, location_type, file_num=None):
            """Display a weather card for a location"""
            if 'error' in weather_data:
                st.warning(f"Could not fetch weather: {weather_data['error']}")
                return

            emoji = get_weather_emoji(weather_data.get('weather_code', 0))
            title = f"{emoji} {location_type}"
            if file_num is not None:
                title = f"File {file_num}: {title}"

            st.markdown(f"**{title}**")

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                temp = weather_data.get('temperature_c', 'N/A')
                feels_like = weather_data.get('apparent_temperature_c', 'N/A')
                st.metric("🌡️ Temperature", f"{temp}°C", delta=f"Feels {feels_like}°C")
            with col_b:
                humidity = weather_data.get('humidity_pct', 'N/A')
                st.metric("💧 Humidity", f"{humidity}%")
            with col_c:
                wind = weather_data.get('wind_speed_kmh', 'N/A')
                st.metric("💨 Wind", f"{wind} km/h")

            weather_desc = weather_data.get('weather_description', 'Unknown')
            cloud_cover = weather_data.get('cloud_cover_pct', 'N/A')
            st.caption(f"**{weather_desc}** | Cloud Cover: {cloud_cover}% | Timezone: {weather_data.get('timezone', 'N/A')}")

        with st.expander("🌤️ Current Weather at Route Locations", expanded=True):
            if len(uploaded_files) == 1:
                # Single file - show source and destination weather
                first_row = all_dataframes[0].iloc[0]
                last_row = all_dataframes[0].iloc[-1]

                source_lat, source_lon = first_row['latitude'], first_row['longitude']
                dest_lat, dest_lon = last_row['latitude'], last_row['longitude']

                col_src, col_dst = st.columns(2)

                with col_src:
                    with st.spinner("Fetching source weather..."):
                        source_weather = weather_service.get_current_weather(source_lat, source_lon)
                    display_weather_card(source_weather, f"Source ({source_lat:.4f}, {source_lon:.4f})")

                with col_dst:
                    with st.spinner("Fetching destination weather..."):
                        dest_weather = weather_service.get_current_weather(dest_lat, dest_lon)
                    display_weather_card(dest_weather, f"Destination ({dest_lat:.4f}, {dest_lon:.4f})")
            else:
                # Multiple files - show weather for each file's source and destination
                st.markdown("### Weather at Source & Destination for Each Route")

                for idx, df in enumerate(all_dataframes, 1):
                    first_row = df.iloc[0]
                    last_row = df.iloc[-1]

                    source_lat, source_lon = first_row['latitude'], first_row['longitude']
                    dest_lat, dest_lon = last_row['latitude'], last_row['longitude']

                    vehicle_id = df['vehicle_id'].iloc[0] if 'vehicle_id' in df.columns else f"Route {idx}"

                    st.markdown(f"---")
                    st.markdown(f"#### 📁 File {idx}: {file_info[idx-1]['filename']} ({vehicle_id})")

                    col_src, col_dst = st.columns(2)

                    with col_src:
                        with st.spinner(f"Fetching source weather for file {idx}..."):
                            source_weather = weather_service.get_current_weather(source_lat, source_lon)
                        display_weather_card(source_weather, f"Source ({source_lat:.4f}, {source_lon:.4f})")

                    with col_dst:
                        with st.spinner(f"Fetching destination weather for file {idx}..."):
                            dest_weather = weather_service.get_current_weather(dest_lat, dest_lon)
                        display_weather_card(dest_weather, f"Destination ({dest_lat:.4f}, {dest_lon:.4f})")

    # Business Intelligence Metrics
    business_analyzer = services['business_analyzer']
    costs = business_analyzer.calculate_journey_costs(df_agg)

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        total_distance = df_agg['total_distance_km'].sum()
        st.metric("Total Distance", f"{total_distance:.2f} km")

    with col2:
        avg_speed_effective = df_agg['avg_speed_kmph'].mean()
        st.metric("Avg Speed (Effective)", f"{avg_speed_effective:.1f} km/h",
                  help="Total distance / total time (includes stops)")

    with col3:
        duration = (df_agg['moving_time_sec'].sum() + df_agg['stopped_time_sec'].sum()) / 3600
        st.metric("Duration", f"{duration:.1f} hours")

    with col4:
        st.metric("💰 Total Cost", f"₹{costs['total_cost_inr']:,.0f}",
                  help=f"Fuel: ₹{costs['fuel_cost_inr']:,.0f} + Driver: ₹{costs['driver_cost_inr']:,.0f}")

    with col5:
        st.metric("⚠️ Idle Waste", f"₹{costs['idle_fuel_waste_inr']:,.0f}",
                  delta=f"-{costs['idle_fuel_liters']:.1f}L wasted",
                  delta_color="inverse")

    # Speed breakdown info
    with st.expander("📊 Speed Metrics Breakdown", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("### Effective Speed")
            st.write(f"**{avg_speed_effective:.1f} km/h**")
            st.caption("Total distance ÷ total time")
            st.caption("Includes all stopped periods")

        with col2:
            st.markdown("### Moving Speed")
            avg_speed_moving = df_agg['avg_moving_speed_kmph'].mean()
            st.write(f"**{avg_speed_moving:.1f} km/h**")
            st.caption("Avg of speeds when moving")
            st.caption("Excludes stopped periods")

        with col3:
            moving_time_hours = df_agg['moving_time_sec'].sum() / 3600
            stopped_time_hours = df_agg['stopped_time_sec'].sum() / 3600

            st.markdown("### Time Breakdown")
            st.write(f"Moving: {moving_time_hours:.1f}h ({moving_time_hours / duration * 100:.0f}%)")
            st.write(f"Stopped: {stopped_time_hours:.1f}h ({stopped_time_hours / duration * 100:.0f}%)")

    # Tabs for analysis
    if len(uploaded_files) > 1 and not combine_routes:
        # MULTI-ROUTE MODE WITH ENHANCED COMPARISON
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
            "💼 Business Dashboard",
            "📊 Enhanced Comparison",
            "🗺️ Interactive Map",
            "🏢 Landmarks & POIs",
            "📍 Geocoding",
            "🤖 AI Insights",
            "📈 Advanced Charts",
            "📍 Waypoint Analysis"
        ])
    else:
        # SINGLE ROUTE MODE
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "💼 Business Dashboard",
            "📊 Route Comparison",
            "🗺️ Interactive Map",
            "🏢 Landmarks & POIs",
            "📍 Geocoding",
            "🤖 AI Insights",
            "📍 Waypoint Analysis"
        ])

    with tab1:
        st.subheader("💼 Business Intelligence Dashboard")

        with st.expander("📋 Executive Summary", expanded=True):
            summary = business_analyzer.generate_executive_summary(df_agg,
                                                                   file_info[0]['filename'] if len(
                                                                       file_info) == 1 else "Combined Routes")
            st.markdown(summary)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 💰 Cost Breakdown")
            cost_fig = go.Figure(data=[go.Pie(
                labels=['Fuel (Moving)', 'Fuel (Idle)', 'Driver Wages'],
                values=[
                    costs['moving_fuel_liters'] * fuel_price,
                    costs['idle_fuel_liters'] * fuel_price,
                    costs['driver_cost_inr']
                ],
                marker=dict(colors=['#2ecc71', '#e74c3c', '#3498db']),
                hole=0.4
            )])
            cost_fig.update_layout(height=400, title="Cost Distribution")
            st.plotly_chart(cost_fig, use_container_width=True, key="plotly_chart_1")

        with col2:
            st.markdown("### 📊 Cost Metrics")
            metric_col1, metric_col2 = st.columns(2)
            with metric_col1:
                st.metric("Cost per km", f"₹{costs['cost_per_km']:.2f}")
                st.metric("Fuel Consumed", f"{costs['fuel_consumed_liters']:.1f}L")
            with metric_col2:
                st.metric("Moving Fuel", f"{costs['moving_fuel_liters']:.1f}L", delta="Productive")
                st.metric("Idle Fuel", f"{costs['idle_fuel_liters']:.1f}L", delta="Wasted", delta_color="inverse")

        st.markdown("### 🎯 Cost Savings Opportunities")
        opportunities = business_analyzer.identify_cost_savings_opportunities(df_agg)

        if opportunities:
            for opp in opportunities:
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.subheader(opp["category"])
                        st.write("**Recommendation:**", opp["recommendation"])
                        st.write("💰 **Potential Savings per trip:** ₹{:,.0f}".format(opp["potential_savings_inr"]))
                        st.write("📅 **Monthly Savings:** ₹{:,.0f}".format(opp["monthly_savings_inr"]))
                    with col2:
                        if opp["priority"] == "HIGH":
                            st.error("HIGH PRIORITY")
                        elif opp["priority"] == "MEDIUM":
                            st.warning("MEDIUM PRIORITY")
                        else:
                            st.success("LOW PRIORITY")
                    st.divider()
        else:
            st.info("No major cost optimization opportunities identified. Route is already efficient!")

    with tab2:
        if len(uploaded_files) > 1 and not combine_routes:
            # ENHANCED COMPARISON MODE
            st.subheader("📊 Enhanced Multi-Route Comparison")

            enhanced_comp = services['enhanced_comparison']
            routes_for_comparison = [(info['filename'], agg) for info, agg in zip(file_info, all_aggregated)]
            raw_routes_for_comparison = [(info['filename'], raw) for info, raw in zip(file_info, all_dataframes)]

            # Multi-route overlay map
            st.markdown("### 🗺️ All Routes Overlay Map")
            multi_route_map = enhanced_comp.create_multi_route_map(routes_for_comparison)
            st_folium(multi_route_map, width=1200, height=700)

            # Route legend
            st.markdown("#### 📍 Route Summary")
            cols = st.columns(min(len(routes_for_comparison), 3))
            for idx, (route_name, df_agg_route) in enumerate(routes_for_comparison):
                with cols[idx % 3]:
                    total_dist = df_agg_route['total_distance_km'].sum()
                    duration_route = (df_agg_route['moving_time_sec'].sum() + df_agg_route['stopped_time_sec'].sum()) / 3600
                    st.metric(route_name, f"{total_dist:.1f} km", f"{duration_route:.1f} hrs")

            st.markdown("---")

            # Comprehensive data table
            st.markdown("### 📋 Detailed Comparison Table")
            comparison_table = enhanced_comp.create_detailed_comparison_table(
                routes_for_comparison,
                raw_routes_for_comparison
            )
            st.dataframe(
                comparison_table.style.highlight_min(
                    subset=['Duration (hrs)', 'Stopped Time (hrs)'],
                    color='lightgreen'
                ).highlight_max(
                    subset=['Efficiency (%)', 'Avg Speed (km/h)'],
                    color='lightgreen'
                ),
                use_container_width=True
            )

            # Download
            csv = comparison_table.to_csv(index=False)
            st.download_button("📥 Download Comparison (CSV)", csv, "enhanced_route_comparison.csv", "text/csv")

            st.markdown("---")

            # Comprehensive heatmap
            st.markdown("### 🔥 Comprehensive Heatmap: Distance, Speed & Stops")
            heatmap = enhanced_comp.create_comprehensive_heatmap(routes_for_comparison)
            st.plotly_chart(heatmap, use_container_width=True, key="plotly_chart_2")

            st.markdown("---")

            # Waypoint distribution
            st.markdown("### 📍 Waypoint Distribution Analysis")
            waypoint_chart = enhanced_comp.create_waypoint_distribution_chart(routes_for_comparison)
            st.plotly_chart(waypoint_chart, use_container_width=True, key="plotly_chart_3")

        else:
            st.subheader("📊 Multi-Route Comparison")

            if len(uploaded_files) < 2:
                st.info("💡 Upload multiple Excel files to compare different routes")
                st.markdown("""
                ### How to Compare Routes:
                1. Upload 2 or more Excel files
                2. Each file represents a different route or journey
                3. See side-by-side comparisons of:
                   - Total costs
                   - Time efficiency
                   - Speed patterns
                   - Cost per kilometer
                """)
            else:
                routes_for_comparison = [(info['filename'], df) for info, df in zip(file_info, all_aggregated)]
                comparison_df = business_analyzer.compare_routes(routes_for_comparison)

                st.markdown("## 🏆 Route Recommendations")

                if comparison_df is not None and len(comparison_df) > 0:
                    best = comparison_df.sort_values("Efficiency (%)", ascending=False).iloc[0]
                    cheapest = comparison_df.sort_values("Total Cost (₹)").iloc[0]
                    fastest = comparison_df.sort_values("Duration (hrs)").iloc[0]

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.success("🏆 Overall Best")
                        st.write("**Route:**", best["Route"])
                        st.write("Efficiency:", best["Efficiency (%)"], "%")
                        st.write("Cost:", "₹{:,.0f}".format(best["Total Cost (₹)"]))

                    with col2:
                        st.info("💰 Cheapest Route")
                        st.write("**Route:**", cheapest["Route"])
                        st.write("Cost:", "₹{:,.0f}".format(cheapest["Total Cost (₹)"]))
                        st.write("Saves vs worst:", "₹{:,.0f}".format(
                            comparison_df["Total Cost (₹)"].max() - cheapest["Total Cost (₹)"]
                        ))

                    with col3:
                        st.warning("⚡ Fastest Route")
                        st.write("**Route:**", fastest["Route"])
                        st.write("Duration:", fastest["Duration (hrs)"], "hrs")
                        st.write("Saves time:", "{:.1f} hrs".format(
                            comparison_df["Duration (hrs)"].max() - fastest["Duration (hrs)"]
                        ))

                comp_viz = services['comparison_visualizer']

                st.markdown("### 📊 Detailed Comparisons")

                viz_tab1, viz_tab2, viz_tab3, viz_tab4 = st.tabs([
                    "💰 Cost Analysis",
                    "📈 Performance Radar",
                    "⏱️ Time vs Distance",
                    "🏆 Rankings"
                ])

                with viz_tab1:
                    cost_chart = comp_viz.create_cost_comparison_chart(comparison_df)
                    st.plotly_chart(cost_chart, use_container_width=True, key="plotly_chart_4")

                with viz_tab2:
                    radar_chart = comp_viz.create_efficiency_comparison_radar(comparison_df)
                    st.plotly_chart(radar_chart, use_container_width=True, key="plotly_chart_5")

                with viz_tab3:
                    scatter_chart = comp_viz.create_time_distance_comparison(comparison_df)
                    st.plotly_chart(scatter_chart, use_container_width=True, key="plotly_chart_6")

                with viz_tab4:
                    ranking_table = comp_viz.create_ranking_table(comparison_df)
                    st.plotly_chart(ranking_table, use_container_width=True, key="plotly_chart_7")

                st.markdown("### 🚛 Speed Profiles Comparison")
                speed_profile = comp_viz.create_speed_profile_comparison(routes_for_comparison)
                st.plotly_chart(speed_profile, use_container_width=True, key="plotly_chart_8")

                st.markdown("### 📋 Detailed Metrics Table")
                st.dataframe(comparison_df, use_container_width=True)

    with tab3:
        st.subheader("🗺️ Interactive Route Map")

        center_lat = df_raw['latitude'].mean()
        center_lon = df_raw['longitude'].mean()

        m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles='OpenStreetMap')

        coordinates = df_raw[['latitude', 'longitude']].values.tolist()
        folium.PolyLine(coordinates, color='blue', weight=3, opacity=0.7).add_to(m)

        folium.Marker(
            [df_raw.iloc[0]['latitude'], df_raw.iloc[0]['longitude']],
            popup=f"Start: {df_raw.iloc[0]['Date Time']}",
            icon=folium.Icon(color='green', icon='play')
        ).add_to(m)

        folium.Marker(
            [df_raw.iloc[-1]['latitude'], df_raw.iloc[-1]['longitude']],
            popup=f"End: {df_raw.iloc[-1]['Date Time']}",
            icon=folium.Icon(color='red', icon='stop')
        ).add_to(m)

        st_folium(m, width=None, height=500)

        st.subheader("Speed Comparison: Effective vs Moving")

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df_agg['window_start'],
            y=df_agg['avg_speed_kmph'],
            name='Effective Speed (with stops)',
            line=dict(color='#ff7f0e', width=2)
        ))

        fig.add_trace(go.Scatter(
            x=df_agg['window_start'],
            y=df_agg['avg_moving_speed_kmph'],
            name='Moving Speed (excludes stops)',
            line=dict(color='#2ca02c', width=2, dash='dash')
        ))

        fig.update_layout(
            title=f'Speed Over Time ({time_window} windows)',
            xaxis_title='Time',
            yaxis_title='Speed (km/h)',
            hovermode='x unified'
        )

        st.plotly_chart(fig, use_container_width=True, key="plotly_chart_9")

    with tab4:
        st.subheader("🏢 Landmarks & Points of Interest")

        if not poi_enabled:
            st.info("Enable POI search in the sidebar")
        else:
            if st.button("🔍 Find Landmarks Along Route", type="primary"):
                finder = services['landmark_finder']

                sample_interval = max(1, len(df_agg) // 10)
                sampled = df_agg.iloc[::sample_interval]

                all_pois = []
                progress_bar = st.progress(0)

                for idx, (i, row) in enumerate(sampled.iterrows()):
                    pois = finder.find_nearby_pois(row['latitude'], row['longitude'], poi_radius, poi_categories)

                    for poi in pois[:3]:
                        all_pois.append({
                            'Window Time': row['window_label'],
                            'POI Name': poi['name'],
                            'Category': poi['category'],
                            'Distance (km)': poi['distance_km']
                        })

                    progress_bar.progress((idx + 1) / len(sampled))

                if all_pois:
                    st.session_state.poi_data = pd.DataFrame(all_pois)
                    st.success(f"✅ Found {len(all_pois)} POIs along the route")

            if 'poi_data' in st.session_state:
                st.dataframe(st.session_state.poi_data, use_container_width=True)

    with tab5:
        st.subheader("📍 Reverse Geocoding")

        if not geocode_enabled:
            st.info("Enable geocoding in the sidebar to use this feature")
        else:
            if st.button("🚀 Start Geocoding", type="primary"):
                geocoder = services['geocoder']

                indices = range(0, len(df_agg), geocode_sample_rate)
                geocoded_data = []

                progress_bar = st.progress(0)
                status_text = st.empty()

                for i, idx in enumerate(indices):
                    row = df_agg.iloc[idx]
                    status_text.text(f"Geocoding window {i + 1}/{len(indices)}...")

                    address = geocoder.get_address(row['latitude'], row['longitude'])

                    if address:
                        geocoded_data.append({
                            'Time Window': row['window_label'],
                            'Start Time': row['window_start'],
                            'Latitude': row['latitude'],
                            'Longitude': row['longitude'],
                            'Address': address['formatted_address'],
                            'City': address.get('city', 'N/A'),
                            'State': address.get('state', 'N/A')
                        })

                    progress_bar.progress((i + 1) / len(indices))

                st.session_state.geocoded_data = pd.DataFrame(geocoded_data)
                status_text.text("✅ Geocoding complete!")

            if 'geocoded_data' in st.session_state:
                st.dataframe(st.session_state.geocoded_data, use_container_width=True)

    with tab6:
        st.subheader("🤖 AI-Powered Journey Insights")

        planner = services['journey_planner']

        if not planner.enabled:
            st.error("❌ OpenAI API key not configured. Set OPENAI_API_KEY in your .env file")
            st.info("💡 Get your API key from https://platform.openai.com/api-keys")
        else:
            if st.button("🚀 Generate AI Analysis & Recommendations", type="primary"):
                with st.spinner("AI analyzing your journey data..."):
                    moving_time_h = df_agg['moving_time_sec'].sum() / 3600
                    stopped_time_h = df_agg['stopped_time_sec'].sum() / 3600

                    historical_data = {
                        'avg_time_hours': duration,
                        'avg_effective_speed_kmph': avg_speed_effective,
                        'avg_moving_speed_kmph': df_agg['avg_moving_speed_kmph'].mean(),
                        'total_distance_km': total_distance,
                        'moving_time_hours': moving_time_h,
                        'stopped_time_hours': stopped_time_h,
                        'efficiency_pct': (moving_time_h / duration * 100) if duration > 0 else 0
                    }

                    start_loc = "Starting Point"
                    end_loc = "Destination"

                    if 'geocoded_data' in st.session_state:
                        geo_df = st.session_state.geocoded_data
                        if len(geo_df) > 0:
                            start_loc = geo_df.iloc[0]['City'] or geo_df.iloc[0]['State'] or start_loc
                            end_loc = geo_df.iloc[-1]['City'] or geo_df.iloc[-1]['State'] or end_loc

                    plan = planner.plan_journey(
                        start_location=start_loc,
                        end_location=end_loc,
                        distance_km=total_distance,
                        historical_data=historical_data,
                        weather_forecast=None,  # Weather removed
                        cost_data=costs
                    )

                    st.session_state.ai_plan = plan

            if 'ai_plan' in st.session_state:
                st.markdown("### 🎯 AI-Generated Recommendations")
                st.markdown(st.session_state.ai_plan)

                st.markdown("### 📊 Data-Driven Insights")

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("#### ⚡ Quick Wins")
                    opportunities = business_analyzer.identify_cost_savings_opportunities(df_agg)
                    for opp in opportunities[:2]:
                        st.success(f"**{opp['category']}**: {opp['recommendation']}")

                with col2:
                    moving_time_h = df_agg['moving_time_sec'].sum() / 3600
                    st.markdown("#### 📈 Performance Metrics")
                    st.info(f"**Efficiency Score**: {(moving_time_h / duration * 100):.0f}%")
                    st.info(f"**Cost Efficiency**: ₹{costs['cost_per_km']:.2f}/km")


    with tab7:
        st.subheader("📍 Enhanced Waypoint Analysis with Diagrammatic Visualizations")

        waypoint_analyzer = services['waypoint_analyzer']

        # Check if waypoint data is available
        if 'waypoint_processed' not in st.session_state:
            with st.spinner("⏳ Processing waypoint data with cumulative metrics..."):
                wp_processed = waypoint_analyzer.preprocess_waypoint_data(df_raw)
                st.session_state.waypoint_processed = [wp_processed]

        wp_df = st.session_state.waypoint_processed[0]

        # Summary
        st.markdown("### 📊 Waypoint Journey Summary")
        summary_text = waypoint_analyzer.generate_waypoint_summary(wp_df, file_info[0]['filename'] if file_info else "Trip")
        st.markdown(summary_text)

        # Key metrics in cards
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric("Total Waypoints", f"{len(wp_df):,}")

        with col2:
            if 'cumulative_time_hours' in wp_df.columns:
                total_time = wp_df['cumulative_time_hours'].max()
            else:
                total_time = (wp_df['Date Time'].max() - wp_df['Date Time'].min()).total_seconds() / 3600
            st.metric("Journey Duration", f"{total_time:.2f} hrs")

        with col3:
            if 'cumulative_distance_km' in wp_df.columns:
                total_dist = wp_df['cumulative_distance_km'].max()
            else:
                total_dist = wp_df['Distance_km'].sum()
            st.metric("Total Distance", f"{total_dist:.2f} km")

        with col4:
            waypoints_per_hour = len(wp_df) / max(1, total_time)
            st.metric("Waypoints/Hour", f"{waypoints_per_hour:.1f}")

        with col5:
            if 'Speed_kmh' in wp_df.columns:
                avg_speed = wp_df['Speed_kmh'].mean()
                st.metric("Avg Speed", f"{avg_speed:.1f} km/h")

        st.markdown("---")
        
        # CONSOLIDATED WAYPOINT DIAGRAM (NEW)
        if 'Waypoint1' in wp_df.columns or 'Waypoint 1' in wp_df.columns:
            st.markdown("### 🎯 Consolidated Waypoint Transitions")
            st.info("📍 This shows UNIQUE waypoint locations (duplicates merged) with time spent and distance between each location")
            
            # Consolidate waypoints
            wp_consolidated = waypoint_analyzer.consolidate_waypoints(wp_df)
            
            # Display consolidated summary
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Unique Waypoint Locations", len(wp_consolidated))
            with col2:
                total_stops = len(wp_consolidated[wp_consolidated['Status'] == 'Stopped'])
                st.metric("Stop Locations", total_stops)
            with col3:
                avg_time_per_stop = wp_consolidated['Time_Spent_Minutes'].mean()
                st.metric("Avg Time/Location", f"{avg_time_per_stop:.1f} min")
            
            # Show consolidated diagram
            consolidated_fig = waypoint_analyzer.create_consolidated_waypoint_diagram(wp_consolidated)
            st.plotly_chart(consolidated_fig, use_container_width=True, key="plotly_chart_14")
            
            # Show consolidated data table
            with st.expander("📋 View Consolidated Waypoint Data Table", expanded=False):
                display_df = wp_consolidated[[
                    'Waypoint_Name', 'Arrival_Time', 'Departure_Time', 'Time_Spent_Minutes',
                    'Distance_To_Next', 'Cumulative_Distance', 'Avg_Speed', 'Status', 'Visit_Number'
                ]].copy()
                display_df['Arrival_Time'] = display_df['Arrival_Time'].dt.strftime('%H:%M:%S')
                display_df['Departure_Time'] = display_df['Departure_Time'].dt.strftime('%H:%M:%S')
                st.dataframe(display_df, use_container_width=True, height=400)
                
                # Download consolidated data
                csv_consolidated = wp_consolidated.to_csv(index=False)
                st.download_button(
                    "📥 Download Consolidated Waypoint Data",
                    csv_consolidated,
                    f"consolidated_waypoints_{file_info[0]['filename'] if file_info else 'trip'}.csv",
                    "text/csv"
                )
            
            st.markdown("---")

        # MAIN DIAGRAMMATIC VISUALIZATION
        st.markdown("### 🗺️ Complete Waypoint Journey Diagram (All GPS Points)")
        st.info("📍 This diagram shows the complete journey with waypoints, distances between them, time intervals, and speed profile")
        
        # Sample rate control for large datasets
        sample_rate = 1
        if len(wp_df) > 500:
            sample_rate = st.slider(
                "Sample Rate (show every Nth waypoint for performance)",
                min_value=1,
                max_value=min(50, len(wp_df) // 10),
                value=max(1, len(wp_df) // 500),
                help="For large datasets, sampling improves visualization performance"
            )
        
        journey_diagram = waypoint_analyzer.create_waypoint_journey_diagram(wp_df, sample_rate=sample_rate)
        st.plotly_chart(journey_diagram, use_container_width=True, key="plotly_chart_15")

        st.markdown("---")

        # WAYPOINT NETWORK DIAGRAM
        st.markdown("### 🔗 Waypoint Network & Connection Diagram")
        st.info("📊 Interactive network showing how waypoints connect over time and distance")
        
        max_network_points = st.slider(
            "Number of waypoints to display in network",
            min_value=20,
            max_value=min(200, len(wp_df)),
            value=min(50, len(wp_df)),
            help="Adjust for optimal visualization clarity"
        )
        
        network_diagram = waypoint_analyzer.create_waypoint_connection_diagram(wp_df, max_points=max_network_points)
        st.plotly_chart(network_diagram, use_container_width=True, key="plotly_chart_16")

        st.markdown("---")

        # SEGMENT ANALYSIS
        st.markdown("### 📊 Journey Segment Analysis")
        st.info("🔍 Analysis of journey broken into segments (gaps > 30 minutes between waypoints)")
        
        segment_chart = waypoint_analyzer.create_waypoint_segment_analysis(wp_df)
        st.plotly_chart(segment_chart, use_container_width=True, key="plotly_chart_17")

        st.markdown("---")

        # DISTANCE-TIME CORRELATION
        st.markdown("### 📈 Distance vs Time Correlation Analysis")
        correlation_chart = waypoint_analyzer.create_distance_time_correlation(wp_df)
        st.plotly_chart(correlation_chart, use_container_width=True, key="plotly_chart_18")

        st.markdown("---")

        # Waypoint1 Analysis if column exists
        if 'Waypoint1' in wp_df.columns:
            st.markdown("### 🏷️ Waypoint1 Named Location Analysis")

            wp1_analysis = waypoint_analyzer.analyze_waypoint1_column(wp_df)

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Unique Waypoint1 Values", wp1_analysis['unique_waypoint1_values'])

            with col2:
                st.metric("Total Waypoints", wp1_analysis['total_waypoints'])

            with col3:
                if wp1_analysis['waypoints_with_stops'] > 0:
                    st.metric("Waypoints with Stops", wp1_analysis['waypoints_with_stops'])

            col1, col2 = st.columns(2)

            with col1:
                # Top waypoints table
                st.markdown("#### Top 10 Waypoint1 Locations")
                top_10 = pd.DataFrame(list(wp1_analysis['top_10_waypoints'].items()),
                                     columns=['Waypoint1', 'Count'])
                st.dataframe(top_10, use_container_width=True, height=350)

            with col2:
                # Frequency chart
                freq_chart = waypoint_analyzer.create_waypoint1_frequency_chart(wp_df, top_n=15)
                if freq_chart:
                    st.plotly_chart(freq_chart, use_container_width=True, key="plotly_chart_19")

            # Transitions analysis
            if wp1_analysis['top_transitions']:
                st.markdown("#### 🔄 Top Waypoint1 Transitions (Route Patterns)")
                st.caption("Most common routes taken between named waypoints")
                transitions_df = pd.DataFrame(list(wp1_analysis['top_transitions'].items()),
                                             columns=['Transition', 'Count'])
                st.dataframe(transitions_df, use_container_width=True, height=300)

            st.markdown("---")

        # Additional Visualizations
        st.markdown("### 📊 Additional Waypoint Visualizations")

        viz_tab1, viz_tab2, viz_tab3 = st.tabs([
            "📅 Waypoint Timeline",
            "⏰ Hourly Density Heatmap",
            "🚀 Speed Distribution"
        ])

        with viz_tab1:
            st.markdown("#### Cumulative waypoint accumulation over time")
            timeline_fig = waypoint_analyzer.create_waypoint_timeline_chart(wp_df)
            st.plotly_chart(timeline_fig, use_container_width=True, key="plotly_chart_20")

        with viz_tab2:
            st.markdown("#### Waypoint density by hour and day")
            heatmap_fig = waypoint_analyzer.create_hourly_waypoint_heatmap(wp_df)
            st.plotly_chart(heatmap_fig, use_container_width=True, key="plotly_chart_21")

        with viz_tab3:
            st.markdown("#### Distribution of speeds at all waypoints")
            speed_dist_fig = waypoint_analyzer.create_waypoint_speed_distribution(wp_df)
            if speed_dist_fig:
                st.plotly_chart(speed_dist_fig, use_container_width=True, key="plotly_chart_22")
            else:
                st.info("Speed data not available")

        st.markdown("---")

        # Pattern analysis
        st.markdown("### 🔍 Waypoint Pattern Analysis")

        patterns = waypoint_analyzer.analyze_waypoint_patterns(wp_df)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("#### ⏰ Temporal Patterns")
            st.write(f"**Peak Hour**: {patterns['temporal']['peak_hour']}:00")
            st.write(f"**Quietest Hour**: {patterns['temporal']['quiet_hour']}:00")
            
            # Show hourly distribution
            hourly_df = pd.DataFrame(list(patterns['temporal']['waypoints_by_hour'].items()),
                                    columns=['Hour', 'Waypoints']).sort_values('Hour')
            st.bar_chart(hourly_df.set_index('Hour'))

        with col2:
            if patterns['speed_patterns']:
                st.markdown("#### 🚗 Movement Patterns")
                st.write(f"**Avg Speed**: {patterns['speed_patterns']['avg_speed_at_waypoints']:.1f} km/h")
                st.write(f"**Max Speed**: {patterns['speed_patterns']['max_speed']:.1f} km/h")
                st.write(f"**Min Speed**: {patterns['speed_patterns']['min_speed']:.1f} km/h")
                st.write(f"**Moving Waypoints**: {patterns['speed_patterns']['waypoints_moving']:,}")
                st.write(f"**Stopped Waypoints**: {patterns['speed_patterns']['waypoints_stopped']:,}")

        with col3:
            if patterns['distance_patterns']:
                st.markdown("#### 📏 Distance Patterns")
                st.write(f"**Total Distance**: {patterns['distance_patterns']['total_distance']:.2f} km")
                st.write(f"**Avg Between Waypoints**: {patterns['distance_patterns']['avg_distance_between_waypoints']:.3f} km")
                st.write(f"**Max Segment**: {patterns['distance_patterns']['max_distance_segment']:.3f} km")

        st.markdown("---")
        
        # Download waypoint data
        st.markdown("### 💾 Download Waypoint Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Download complete processed waypoint data
            csv_data = wp_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Complete Waypoint Data (CSV)",
                data=csv_data,
                file_name=f"waypoint_analysis_{file_info[0]['filename'] if file_info else 'trip'}.csv",
                mime="text/csv"
            )
        
        with col2:
            # Download summary statistics
            summary_stats = pd.DataFrame({
                'Metric': ['Total Waypoints', 'Total Distance (km)', 'Total Time (hrs)', 
                          'Avg Speed (km/h)', 'Waypoints/Hour'],
                'Value': [len(wp_df), total_dist, total_time, 
                         wp_df['Speed_kmh'].mean() if 'Speed_kmh' in wp_df.columns else 0,
                         waypoints_per_hour]
            })
            st.download_button(
                label="📊 Download Summary Statistics (CSV)",
                data=summary_stats.to_csv(index=False),
                file_name=f"waypoint_summary_{file_info[0]['filename'] if file_info else 'trip'}.csv",
                mime="text/csv"
            )


    # Additional tabs for multi-route mode
    if len(uploaded_files) > 1 and not combine_routes:
        with tab7:
            st.subheader("📈 Advanced Comparison Charts")
            enhanced_comp = services['enhanced_comparison']
            routes_for_charts = [(info['filename'], agg) for info, agg in zip(file_info, all_aggregated)]
            
            st.markdown("### 📏 Total Distance Comparison")
            distance_chart = enhanced_comp.create_distance_comparison_chart(routes_for_charts)
            st.plotly_chart(distance_chart, use_container_width=True, key="plotly_chart_23")
            
            st.markdown("### ⏱️ Time Breakdown: Moving vs Stopped")
            duration_chart = enhanced_comp.create_stacked_duration_chart(routes_for_charts)
            st.plotly_chart(duration_chart, use_container_width=True, key="plotly_chart_24")
            
            st.markdown("### 📊 Speed Distribution Analysis")
            speed_dist_chart = enhanced_comp.create_speed_distribution_boxplot(routes_for_charts)
            st.plotly_chart(speed_dist_chart, use_container_width=True, key="plotly_chart_25")

        with tab8:
            st.subheader("📍 Multi-Trip Waypoint Analysis")

            waypoint_analyzer = services['waypoint_analyzer']

            # Get combined waypoint data
            if 'combined_waypoint_data' in st.session_state:
                combined_wp_df = st.session_state.combined_waypoint_data
            else:
                combined_wp_df = waypoint_analyzer.cumulative_preprocessing_multiple_trips(all_dataframes)
                st.session_state.combined_waypoint_data = combined_wp_df

            # Trip comparison
            st.markdown("### 📊 Waypoint Comparison Across Trips")

            comparison_df = waypoint_analyzer.compare_waypoints_across_trips(combined_wp_df)
            st.dataframe(comparison_df, use_container_width=True)

            # Download comparison
            csv = comparison_df.to_csv(index=False)
            st.download_button("📥 Download Waypoint Comparison", csv,
                              "waypoint_comparison.csv", "text/csv")

            st.markdown("---")

            # Comparison visualizations
            st.markdown("### 📈 Waypoint Comparison Charts")

            comparison_chart = waypoint_analyzer.create_waypoint_comparison_chart(comparison_df)
            st.plotly_chart(comparison_chart, use_container_width=True, key="plotly_chart_26")

            st.markdown("---")

            # Individual trip analysis
            st.markdown("### 🔍 Individual Trip Waypoint Details")

            trip_selector = st.selectbox(
                "Select Trip to Analyze",
                options=combined_wp_df['trip_name'].unique() if 'trip_name' in combined_wp_df.columns
                        else combined_wp_df['trip_id'].unique()
            )

            if 'trip_name' in combined_wp_df.columns:
                selected_trip_df = combined_wp_df[combined_wp_df['trip_name'] == trip_selector]
            else:
                selected_trip_df = combined_wp_df[combined_wp_df['trip_id'] == trip_selector]

            # Summary for selected trip
            trip_summary = waypoint_analyzer.generate_waypoint_summary(selected_trip_df, str(trip_selector))
            st.markdown(trip_summary)

            # Waypoint1 analysis for selected trip
            if 'Waypoint1' in selected_trip_df.columns:
                st.markdown("#### 🏷️ Waypoint1 Analysis for Selected Trip")

                wp1_analysis = waypoint_analyzer.analyze_waypoint1_column(selected_trip_df)

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Unique Waypoint1 Values", wp1_analysis['unique_waypoint1_values'])

                with col2:
                    st.metric("Total Waypoints", wp1_analysis['total_waypoints'])

                with col3:
                    if wp1_analysis['top_10_waypoints']:
                        most_common = list(wp1_analysis['top_10_waypoints'].keys())[0]
                        st.metric("Most Common", most_common)

                # Frequency chart for selected trip
                freq_chart = waypoint_analyzer.create_waypoint1_frequency_chart(selected_trip_df)
                if freq_chart:
                    st.plotly_chart(freq_chart, use_container_width=True, key="plotly_chart_27")

            # Visualizations for selected trip
            st.markdown("#### 📊 Visualizations for Selected Trip")

            viz_col1, viz_col2 = st.columns(2)

            with viz_col1:
                timeline_fig = waypoint_analyzer.create_waypoint_timeline_chart(selected_trip_df)
                st.plotly_chart(timeline_fig, use_container_width=True, key="plotly_chart_28")

            with viz_col2:
                speed_dist_fig = waypoint_analyzer.create_waypoint_speed_distribution(selected_trip_df)
                if speed_dist_fig:
                    st.plotly_chart(speed_dist_fig, use_container_width=True, key="plotly_chart_29")

            # Hourly heatmap
            heatmap_fig = waypoint_analyzer.create_hourly_waypoint_heatmap(selected_trip_df)
            st.plotly_chart(heatmap_fig, use_container_width=True, key="plotly_chart_30")

except Exception as e:
    st.error(f"❌ Error processing file: {str(e)}")
    st.exception(e)