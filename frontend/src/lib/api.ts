import axios from 'axios';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:9001/api/v1',
  timeout: 15000,
});

const root = axios.create({
  baseURL: (import.meta.env.VITE_API_URL ?? 'http://localhost:9001/api/v1').replace(/\/api\/v1$/, ''),
  timeout: 5000,
});

// GPS endpoints read the full feed (cold read from remote Neon can take a few
// seconds), so they get a generous timeout rather than the default 15s.
const slowApi = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:9001/api/v1',
  timeout: 90000,
});

// AI composer fans out to multiple ML models in parallel, each of which can
// cold-start the first time. The backend already caps per-model time at
// AI_MODEL_TIMEOUT (default 6s) and substitutes dummy data for slow models,
// but we still give the outer call plenty of headroom for the first request.
const aiApi = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:9001/api/v1',
  timeout: 60000,
});

// ------------------------------ Types ------------------------------

export interface HealthStatus {
  status: string;
  service: string;
  data_source: 'MOCK' | 'LAKEHOUSE';
  lakehouse_url: string;
}

export interface DashboardSummary {
  total_trips: number;
  in_transit: number;
  delivered: number;
  delayed: number;
  on_time_pct: number;
  active_vehicles: number;
  active_drivers: number;
}

export interface ActiveTrip {
  trip_no: number;
  vehicle_id: string;
  driver_name: string;
  transporter_name: string;
  shipper_name: string;
  origin_text: string;
  trip_planned_eta_ts: string;
  trip_derived_eta_ts: string;
  delay_minutes: number;
  running_status: string;
  num_legs: number;
  num_legs_delivered: number;
  total_distance_km: number;
}

export interface MonitoringJunction {
  name: string;
  status: 'live' | 'stale' | 'failed';
  event_lag_ms: number;
  proc_lag_ms: number;
  events_per_min: number;
  errors_per_min: number;
  last_seen: string;
  avg_latency_ms: number;
}

export interface PipelineJob {
  id: string;
  name: string;
  type: string;
  schedule: string;
  status: 'active' | 'running' | 'failed' | 'paused';
  last_run: string;
  next_run: string;
  duration_sec: number;
  rows_processed: number;
}

export interface CatalogTable {
  name: string;
  namespace: string;
  rows_estimate: number;
  size_mb: number;
  last_updated: string;
  required_cols: number;
  optional_cols: number;
}

export interface ConnectorStatus {
  name: string;
  source_table: string;
  format: string;
  rows_pulled: number;
  last_pull: string;
  status: 'active' | 'paused' | 'tested';
  latency_ms: number;
}

export interface IoTDeviceStatus {
  vehicle_id: string;
  device_id: string;
  last_ping: string;
  ping_age_sec: number;
  status: 'online' | 'stale' | 'offline';
  signal_strength: number;
  satellites: number;
  battery_voltage: number;
}

export interface AlertItem {
  id: string;
  timestamp: string;
  severity: 'critical' | 'warning' | 'info';
  type: string;
  vehicle_id: string;
  driver_name: string;
  message: string;
  acknowledged: boolean;
}

export interface LogEntry {
  id: number;
  ts: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  service: string;
  message: string;
  exc: string | null;
}

export interface LogsResponse {
  logs: LogEntry[];
  latest_id: number;
  counts: Record<'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL', number>;
  buffered: number;
}

// ------------------------------ Calls ------------------------------

export async function fetchHealth(): Promise<HealthStatus> {
  const { data } = await root.get<HealthStatus>('/health');
  return data;
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const { data } = await api.get<DashboardSummary>('/dashboard/summary');
  return data;
}

export async function fetchActiveTrips(limit = 50): Promise<{ count: number; trips: ActiveTrip[] }> {
  const { data } = await api.get(`/trips/active?limit=${limit}`);
  return data;
}

export async function fetchMonitoring(): Promise<{ junctions: MonitoringJunction[] }> {
  const { data } = await api.get('/system/monitoring');
  return data;
}

export async function fetchPipelines(): Promise<{ jobs: PipelineJob[] }> {
  const { data } = await api.get('/ml/pipelines');
  return data;
}

export async function fetchCatalogTables(): Promise<{ tables: CatalogTable[] }> {
  const { data } = await api.get('/data/catalog');
  return data;
}

export async function fetchConnectors(): Promise<{ connectors: ConnectorStatus[] }> {
  const { data } = await api.get('/data/connectors');
  return data;
}

export async function fetchDevices(): Promise<{ devices: IoTDeviceStatus[] }> {
  const { data } = await api.get('/data/devices');
  return data;
}

export async function fetchAlerts(): Promise<{ alerts: AlertItem[] }> {
  const { data } = await api.get('/operations/alerts');
  return data;
}

export async function fetchLogs(
  opts: { limit?: number; level?: string; search?: string } = {},
): Promise<LogsResponse> {
  const { data } = await api.get('/system/logs', { params: opts });
  return data;
}

export async function runQuery(sql: string): Promise<{ columns: string[]; rows: unknown[][]; error?: string }> {
  const { data } = await api.post('/data/browser/query', { sql });
  return data;
}

// -------- Analytics (real-data driven) ---------

export interface ColumnHealth {
  table: string;
  column: string;
  null_pct: number;
  all_zero: boolean;
  status: 'ok' | 'partial' | 'sparse' | 'zero' | 'missing';
}

export interface FeatureReadiness {
  feature: string;
  verdict: string;
  worst_status: string;
  blocking_columns: string[];
  required: string[];
}

export interface DataQuality {
  columns: ColumnHealth[];
  tables_summary: { table: string; ok: number; partial: number; sparse: number; zero: number; missing: number; total: number }[];
  feature_readiness: FeatureReadiness[];
}

export interface VehicleSummary {
  vehicle_id: string;
  entity_name: string;
  device_id: string;
  ping_count: number;
  first_seen: string;
  last_seen: string;
  avg_speed: number;
  max_speed: number;
  ignition_on_pct: number;
}

export interface VehiclePatterns {
  vehicle_id: string;
  ping_count: number;
  window: { from: string; to: string };
  hour_of_day_heatmap: { matrix: number[][]; max: number };
  activity_timeline: { date: string; pings: number; moving: number; ignition_on: number; activity_score: number }[];
  sleep_episodes: { at: string; minutes: number }[];
  meal_breaks: { at: string; minutes: number }[];
  tea_breaks: { at: string; minutes: number }[];
  drive_streaks: { start: string; end: string; minutes: number }[];
  summary: { avg_speed_when_moving: number; max_speed: number; moving_pct: number; active_days: number };
}

export async function fetchDataQuality(): Promise<DataQuality> {
  const { data } = await api.get<DataQuality>('/analytics/quality');
  return data;
}

export async function fetchAnalyticsVehicles(): Promise<{ vehicles: VehicleSummary[] }> {
  const { data } = await api.get('/analytics/vehicles');
  return data;
}

export async function fetchVehiclePatterns(vehicleId: string): Promise<VehiclePatterns> {
  const { data } = await api.get(`/analytics/vehicles/${encodeURIComponent(vehicleId)}/patterns`);
  return data;
}

export async function fetchLanes(): Promise<{ lanes: { origin: string; destination: string; trips: number; transporters: number }[] }> {
  const { data } = await api.get('/analytics/lanes');
  return data;
}

export async function fetchGpsQuality(): Promise<any> {
  const { data } = await api.get('/analytics/gps-quality');
  return data;
}

// -------- GPS feed (raw device feed -> warehouse) ---------

export interface GpsUploadStatus {
  warehouse_available: boolean;
  warehouse_rows: number;
  serving_from: string;
}

export interface GpsVehicle {
  vehicle_reg: string;
  entity_name: string;
  device_id: string;
  pings: number;
  first_seen: string;
  last_seen: string;
  distance_km: number;
  max_speed: number;
}

export interface GpsKpis {
  total_pings: number; distance_km: number; active_days: number;
  drive_hours: number; idle_hours: number; utilization_pct: number;
  avg_moving_speed: number; max_speed: number; avg_daily_km: number;
  stop_count: number; longest_stop_min: number;
  overspeed_pings: number; overspeed_pct: number; states_covered: number;
  avg_signal_pct: number; event_flag_pings: number;
}

export interface GpsTrip {
  trip: number; start: string; end: string; duration_min: number;
  distance_km: number; moving_pct: number; avg_speed: number; max_speed: number;
  from_node: string | null; to_node: string | null;
}

export interface GpsStop {
  start: string; end: string; minutes: number; lat: number; lng: number;
  near: string | null; state: string | null;
}

export interface GpsTrackPoint { t: string; lat: number; lng: number; spd: number; mv: boolean; }

export async function fetchGpsUploadStatus(): Promise<GpsUploadStatus> {
  const { data } = await slowApi.get('/data/upload-gps/status');
  return data;
}

export async function uploadGps(): Promise<{ ok: boolean; rows_written: number; status: string; error?: string; destination: string }> {
  const { data } = await slowApi.post('/data/upload-gps', {}, { timeout: 180000 });
  return data;
}

export async function fetchGpsVehicles(): Promise<{ vehicles: GpsVehicle[] }> {
  const { data } = await slowApi.get('/gps/vehicles');
  return data;
}

export async function fetchGpsKpis(vehicle?: string): Promise<{ vehicle: string; kpis: GpsKpis; error?: string }> {
  const { data } = await slowApi.get('/gps/kpis', { params: vehicle ? { vehicle } : {} });
  return data;
}

export async function fetchGpsTrips(vehicle?: string): Promise<{ trips: GpsTrip[] }> {
  const { data } = await slowApi.get('/gps/trips', { params: vehicle ? { vehicle } : {} });
  return data;
}

export async function fetchGpsStops(vehicle?: string): Promise<{ stops: GpsStop[] }> {
  const { data } = await slowApi.get('/gps/stops', { params: vehicle ? { vehicle } : {} });
  return data;
}

export async function fetchGpsTrack(vehicle?: string, bucketMin = 0): Promise<{ points: GpsTrackPoint[]; bbox: any; count: number; bucket_min: number }> {
  const params: Record<string, unknown> = {};
  if (vehicle) params.vehicle = vehicle;
  if (bucketMin > 0) params.bucket_min = bucketMin;
  const { data } = await slowApi.get('/gps/track', { params });
  return data;
}

export interface AssetLink { device_imei: string; vehicle_reg: string; first_ts: string; last_ts: string; ping_count: number; }
export async function fetchGpsAssetHistory(): Promise<{ device_vehicle: AssetLink[]; vehicle_driver: any[] }> {
  const { data } = await slowApi.get('/gps/asset-history');
  return data;
}

export interface Geofence {
  geofence_sk: number; name: string; lat: number; lng: number; radius_m: number;
  type: string; address: string | null; visits: number; total_min: number;
}
export interface Poi { name: string; category: string; distance_m: number | null; }
export interface StopEvent {
  vehicle_reg: string; arrive: string; depart: string; minutes: number;
  lat: number; lng: number; reason: string; where: string | null; type: string | null;
  poi?: Poi | null;
}
export async function fetchGpsGeofences(): Promise<{ geofences: Geofence[] }> {
  const { data } = await slowApi.get('/gps/geofences');
  return data;
}
export async function fetchGpsStopEvents(vehicle?: string): Promise<{ stops: StopEvent[] }> {
  const { data } = await slowApi.get('/gps/stop-events', { params: vehicle ? { vehicle } : {} });
  return data;
}
export async function geocodeStops(limit = 25): Promise<{ ok: boolean; geocoded_now: number; remaining: number }> {
  const { data } = await slowApi.post('/gps/geocode', {}, { params: { limit }, timeout: 180000 });
  return data;
}

// ------------------------------ Halts & Rests ------------------------------
export interface HaltCategory {
  reason: string; rule: string; purpose: string; kind: string;
  count: number; total_min: number; avg_min: number; longest_min: number; share_pct: number;
}
export interface HaltKpis {
  total_halts: number; total_hours: number; rest_hours: number;
  longest_min: number; longest_where: string | null;
  distinct_places: number; avg_min: number; categories_seen: number;
}
export interface HaltsResponse {
  vehicle: string; kpis: HaltKpis; categories: HaltCategory[]; events: StopEvent[];
}
export async function fetchGpsHalts(vehicle?: string): Promise<HaltsResponse> {
  const { data } = await slowApi.get('/gps/halts', { params: vehicle ? { vehicle } : {} });
  return data;
}
export async function buildGeofences(vehicle?: string): Promise<{ ok: boolean; geofences: number; stop_events: number; error?: string }> {
  const { data } = await slowApi.post('/gps/build-geofences', {}, { params: vehicle ? { vehicle } : {}, timeout: 180000 });
  return data;
}
export async function enrichPoi(limit = 20): Promise<{ ok: boolean; resolved_now: number; remaining: number; error?: string }> {
  const { data } = await slowApi.post('/gps/enrich-poi', {}, { params: { limit }, timeout: 180000 });
  return data;
}

// ------------------------------ Journeys ------------------------------
export interface Journey {
  trip: number; start: string; end: string; duration_min: number; distance_km: number;
  moving_pct: number; avg_speed: number; max_speed: number;
  from_node: string | null; to_node: string | null;
  from_place: string; to_place: string;
  halts: StopEvent[]; halt_count: number; halt_minutes: number;
}
export async function fetchGpsJourneys(vehicle?: string): Promise<{ vehicle: string; journeys: Journey[] }> {
  const { data } = await slowApi.get('/gps/journeys', { params: vehicle ? { vehicle } : {} });
  return data;
}
export async function fetchGpsTrackRange(
  vehicle: string, bucketMin = 15, from?: string, to?: string,
): Promise<{ points: GpsTrackPoint[]; bbox: any; count: number; bucket_min: number }> {
  const params: Record<string, unknown> = { vehicle, bucket_min: bucketMin };
  if (from) params.from = from;
  if (to) params.to = to;
  const { data } = await slowApi.get('/gps/track', { params });
  return data;
}

export interface FleetRow {
  vehicle_reg: string; device_imei: string; entity_name: string;
  pings: number; first_seen: string | null; last_seen: string | null;
  distance_km: number; max_speed: number; devices: number;
  status: 'online' | 'stale' | 'offline';
}
export async function fetchGpsFleet(): Promise<{ fleet: FleetRow[]; summary: { trucks: number; devices: number; online: number; stale: number; offline: number } }> {
  const { data } = await slowApi.get('/gps/fleet');
  return data;
}

export async function fetchGpsSpeedProfile(vehicle?: string): Promise<{ threshold_kph: number; series: { t: string; spd: number }[]; histogram: { band: string; count: number }[]; overspeed_segments: any[] }> {
  const { data } = await slowApi.get('/gps/speed-profile', { params: vehicle ? { vehicle } : {} });
  return data;
}

export async function fetchGpsCorridor(vehicle?: string): Promise<{ node_sequence: any[]; state_crossings: any[]; top_lanes: { lane: string; pings: number }[] }> {
  const { data } = await slowApi.get('/gps/corridor', { params: vehicle ? { vehicle } : {} });
  return data;
}

export async function fetchGpsAlerts(vehicle?: string): Promise<{ events: any[]; signal_drops: any[] }> {
  const { data } = await slowApi.get('/gps/alerts', { params: vehicle ? { vehicle } : {} });
  return data;
}

export async function fetchGpsDeviceHealth(vehicle?: string): Promise<{ summary: any; gaps: any[] }> {
  const { data } = await slowApi.get('/gps/device-health', { params: vehicle ? { vehicle } : {} });
  return data;
}

export interface GpsBehaviour {
  vehicle: string; score: number; error?: string;
  metrics: {
    avg_moving_speed: number; max_speed: number; night_pct: number; overspeed_pct: number;
    harsh_accel: number; harsh_brake: number; peak_hour: number; active_days: number;
  };
  by_hour: { hour: number; avg_speed: number; max_speed: number; pings: number; moving_pct: number }[];
  heatmap: { speed: number[][]; activity: number[][]; max_activity: number };
  recent_journeys: Journey[];
}
export async function fetchGpsBehaviour(vehicle?: string): Promise<GpsBehaviour> {
  const { data } = await slowApi.get('/gps/behaviour', { params: vehicle ? { vehicle } : {} });
  return data;
}

// ------------------------------ Trips (real MySQL data) ------------------------------
export interface Trip {
  trip_no: number; asset_id: string | null; device_id: string | null;
  status: string | null; status_label: string;
  org_node: string | null; dest_node: string | null; final_dest: string | null;
  booking_ts: string | null; start_ts: string | null; eta_ts: string | null;
  ata_ts: string | null; end_ts: string | null;
  consignor: string | null; consignee: string | null; transporter: string | null;
  lr_no: string | null; driver_name: string | null; driver_mobile: string | null;
  asset_type: string | null; route_id: number | null; shipment_id: string | null;
  prod_id: string | null; close_reason: string | null;
}
export interface TripLeg {
  seq: number; org_node: string | null; dest_node: string | null;
  status: string | null; stop_type: string | null; running_sts: string | null;
  total_dist: number | null; cover_dist: number | null; delay_by: number | null;
  material: string | null; eta_ts: string | null; ata_ts: string | null; last_loc: string | null;
}
export interface TripSummary {
  total: number; fleet: number; transporters: number;
  by_status: { status: string; label: string; count: number }[];
  top_consignors: { name: string; count: number }[];
  top_lanes: { lane: string; count: number }[];
  counts: { trips: number; legs: number };
}
export async function uploadTrips(): Promise<{ ok: boolean; source?: string; trips?: number; legs?: number; error?: string }> {
  const { data } = await slowApi.post('/trips/upload', {}, { timeout: 180000 });
  return data;
}
export async function fetchTripsSummary(): Promise<TripSummary> {
  const { data } = await slowApi.get('/trips/db/summary');
  return data;
}
export async function fetchTripsDb(params: { search?: string; status?: string; limit?: number; consignor?: string; consignee?: string; transporter?: string } = {}): Promise<{ count: number; trips: Trip[] }> {
  const { data } = await slowApi.get('/trips/db', { params });
  return data;
}
export type PartyDim = 'consignor' | 'consignee' | 'transporter';
export interface PartyRow { name: string; trips: number; assets: number; lanes: number; open_trips: number; last_trip: string | null; }
export async function fetchTripParties(dim: PartyDim): Promise<{ dim: string; parties: PartyRow[] }> {
  const { data } = await slowApi.get(`/trips/parties/${dim}`);
  return data;
}
export async function fetchTripDetail(tripNo: number): Promise<{ header: Trip; legs: TripLeg[]; num_legs: number; error?: string }> {
  const { data } = await slowApi.get(`/trips/db/${tripNo}`);
  return data;
}

// ============================================================================
// Route Intelligence
// ============================================================================
export interface RIUpload {
  id: number; filename: string; original_name?: string; vehicle_id: string;
  n_rows: number; first_ts: string; last_ts: string;
  total_distance_km: number; uploaded_at: string; trip_count: number;
}
export interface RITrip {
  id: number; upload_id: number; seq: number; vehicle_id: string;
  start_ts: string; end_ts: string; duration_min: number; distance_km: number;
  n_points: number; avg_speed_kmph: number; max_speed_kmph: number;
  moving_min: number; stopped_min: number;
  from_waypoint: string | null; to_waypoint: string | null;
  start_lat: number; start_lng: number; end_lat: number; end_lng: number;
  analyzed: number;
}
export interface RIInsight {
  insight_type: string; text: string; model: string; created_at: string;
}
export interface RIWaypointVisit {
  id?: number; seq: number; waypoint: string; arrive_ts: string; depart_ts: string;
  time_spent_min: number; distance_km: number; cumulative_distance_km: number;
  avg_speed_kmph: number; lat: number; lng: number; n_points: number;
}
export interface RITimeWindow {
  id?: number; window_start: string; window_end: string; window_label: string;
  total_distance_km: number; max_speed_kmph: number; avg_speed_kmph: number;
  avg_moving_speed_kmph: number; moving_time_sec: number; stopped_time_sec: number;
  waypoint_count: number; latitude: number; longitude: number; dominant_status: string;
}
export interface RIAnalysisBundle {
  trip: RITrip; run_id: number; model: string;
  route_metrics: {
    efficiency: { route_efficiency: number; actual_distance_km: number;
                  straight_line_distance_km: number; excess_distance_km: number;
                  excess_percentage: number; interpretation: string };
    speed_zones: { avg_speed_kmph: number; max_speed_kmph: number;
                   speed_std_dev: number; speed_consistency: string;
                   slow_zone_pct: number; moderate_zone_pct: number;
                   normal_zone_pct: number; high_zone_pct: number };
    traffic: { time_lost_minutes: number; distance_in_traffic_km: number;
               traffic_segments: number; avg_traffic_speed_kmph: number;
               time_saved_if_no_traffic_minutes: number };
    backtracking: { idx: number; ts: string; lat: number; lng: number; bearing_change_deg: number }[];
    backtracking_count: number;
    stop_clusters: { lat: number; lng: number; stop_count: number; first_visit: string; last_visit: string }[];
  } | null;
  cost_metrics: {
    breakdown: { total_cost_inr: number; fuel_cost_inr: number; driver_cost_inr: number;
                 idle_fuel_waste_inr: number; cost_per_km: number; efficiency_pct: number;
                 fuel_consumed_liters: number; moving_fuel_liters: number;
                 idle_fuel_liters: number; total_distance_km: number;
                 total_hours: number; moving_hours: number; stopped_hours: number };
    opportunities: { category: string; priority: string; recommendation: string;
                     potential_savings_inr: number; monthly_savings_inr: number;
                     current_waste_inr: number }[];
  } | null;
  waypoints: RIWaypointVisit[];
  time_windows: RITimeWindow[];
  ai_insights: RIInsight[];
}
export interface RIComparison {
  id: number; trip_ids: number[]; best_trip_id: number | null;
  table: any[]; created_at: string; ai_insights: RIInsight[];
}

export async function riStatus() {
  const { data } = await api.get('/route-intel/status'); return data;
}
export interface RIStreamlitStatus {
  configured_url: string; running: boolean;
  managed_pid: number | null; autostart: boolean; app_file: string;
}
export async function riStreamlitStatus(): Promise<RIStreamlitStatus> {
  const { data } = await api.get('/route-intel/streamlit/status'); return data;
}
export async function riStreamlitStart(): Promise<RIStreamlitStatus> {
  const { data } = await api.post('/route-intel/streamlit/start'); return data;
}
export async function riUpload(file: File): Promise<{ upload_id: number; trips: RITrip[] }> {
  const fd = new FormData(); fd.append('file', file);
  const { data } = await slowApi.post('/route-intel/upload', fd,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 });
  return data;
}
export async function riIngestLocal(path: string): Promise<{ upload_id: number; trips: RITrip[] }> {
  const { data } = await slowApi.post('/route-intel/ingest-local', { path }, { timeout: 120000 });
  return data;
}
export async function riListUploads(limit = 50): Promise<{ uploads: RIUpload[] }> {
  const { data } = await api.get('/route-intel/uploads', { params: { limit } }); return data;
}
export async function riGetUpload(id: number): Promise<RIUpload & { trips: RITrip[] }> {
  const { data } = await api.get(`/route-intel/uploads/${id}`); return data;
}
export async function riGetTrip(id: number): Promise<RITrip & { latest_run_id: number | null }> {
  const { data } = await api.get(`/route-intel/trips/${id}`); return data;
}
export async function riAnalyzeTrip(id: number, params: Record<string, any> = {}): Promise<RIAnalysisBundle> {
  const { data } = await slowApi.post(`/route-intel/trips/${id}/analyze`, params, { timeout: 120000 });
  return data;
}
export async function riGetAnalysis(id: number): Promise<RIAnalysisBundle> {
  const { data } = await slowApi.get(`/route-intel/trips/${id}/analysis`); return data;
}
export async function riGetTrack(id: number, maxPoints = 2000): Promise<{ points: { ts: string; lat: number; lng: number; speed: number }[] }> {
  const { data } = await slowApi.get(`/route-intel/trips/${id}/track`, { params: { max_points: maxPoints } });
  return data;
}
export async function riRegenAi(id: number) {
  const { data } = await slowApi.post(`/route-intel/trips/${id}/regenerate-ai`); return data;
}
export async function riCompare(tripIds: number[], params: Record<string, any> = {}): Promise<RIComparison> {
  const { data } = await slowApi.post('/route-intel/compare', { trip_ids: tripIds, ...params }, { timeout: 180000 });
  return data;
}
export async function riListComparisons(limit = 30) {
  const { data } = await api.get('/route-intel/comparisons', { params: { limit } }); return data;
}
export async function riGetComparison(id: number): Promise<RIComparison> {
  const { data } = await api.get(`/route-intel/comparisons/${id}`); return data;
}
export async function riListInsights(limit = 50, insight_type?: string) {
  const { data } = await api.get('/route-intel/insights', { params: { limit, insight_type } }); return data;
}

// =========================================================================
// AI Operating System — Mission Control composer (/api/v1/ai/*)
// Composes ml_client calls from the smart-truck subscription API into the
// narrative + cards the AI-OS UI consumes. See backend/app/api/ai.py.
// =========================================================================

export interface MissionControlSummary {
  generated_at: string;
  greeting: string;
  operational_risk: 'LOW' | 'MEDIUM' | 'HIGH';
  bullets: string[];
  signals: {
    drivers_scanned: number;
    drivers_at_risk: number;
    fleet_avg_driver_score: number | null;
    fatigued_drivers: number | null;
    anomaly_events_scanned: number | null;
    anomaly_events_flagged: number | null;
    upcoming_trips_forecast: number | null;
  };
  sources: Record<'driver_scorer' | 'fatigue_predictor' | 'anomaly_detector' | 'demand_forecaster', 'ok' | 'dummy' | 'unavailable'>;
}

export interface AiCard {
  id: 'fleet_stability' | 'eta_confidence' | 'risk_index' | 'ai_confidence';
  title: string;
  value_pct: number;
  confidence_pct: number;
  trend: 'up' | 'down' | 'flat';
  blurb: string;
  explain_endpoint: string;
}

export async function aiMissionControl(): Promise<MissionControlSummary> {
  const { data } = await aiApi.get('/ai/mission-control/summary'); return data;
}
export async function aiCards(): Promise<{ cards: AiCard[]; generated_at: string }> {
  const { data } = await aiApi.get('/ai/cards'); return data;
}
export async function aiExplain(cardId: AiCard['id']): Promise<any> {
  const { data } = await aiApi.get(`/ai/explain/${cardId}`); return data;
}
export async function aiLiveThinking(): Promise<{ now: string; ticks: { t: string; agent: string; msg: string }[] }> {
  const { data } = await aiApi.get('/ai/live-thinking'); return data;
}

// =========================================================================
// Observe — fleet-wide raw-signal rollup over the route-intel warehouse.
// =========================================================================

export interface ObserveKpis {
  n_vehicles: number; n_trips: number;
  total_km: number; total_hours: number;
  moving_hours: number; stopped_hours: number;
  avg_speed_kmph: number; max_speed_kmph: number;
  latest_activity_ts: string | null;
  first_activity_ts: string | null;
}

export interface ObserveVehicle {
  vehicle_id: string;
  n_uploads: number; n_trips: number; total_segments: number;
  total_km: number; total_hours: number; moving_hours: number; stopped_hours: number;
  avg_speed_kmph: number; max_speed_kmph: number;
  first_seen_ts: string | null;
  last_seen_ts: string | null;
  last_trip_end: string | null;
  n_analyzed: number;
}

export interface ObserveTrip {
  id: number; upload_id: number; vehicle_id: string;
  from_waypoint: string | null; to_waypoint: string | null;
  start_ts: string; end_ts: string;
  distance_km: number; duration_min: number;
  moving_min: number; stopped_min: number;
  n_segments: number; avg_speed_kmph: number; max_speed_kmph: number;
  analyzed: 0 | 1;
}

export interface ObserveAlert {
  alert_type: 'long_idle' | 'slow_avg' | 'long_haul' | 'unanalysed' | 'backtracks' | string;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  trip_id: number;
  vehicle_id: string;
  from_waypoint: string | null;
  to_waypoint: string | null;
  start_ts: string | null;
  note: string;
  metric: number;
}

export interface ObserveSnapshot {
  generated_at: string;
  kpis: ObserveKpis;
  vehicles: ObserveVehicle[];
  recent_trips: ObserveTrip[];
  alerts: ObserveAlert[];
}

export async function observeSnapshot(): Promise<ObserveSnapshot> {
  const { data } = await aiApi.get('/observe/snapshot'); return data;
}

// Device alerts — findings parsed from the vendor s_alert_lov column.
export interface DeviceAlertFinding {
  code: string;
  label: string;
  labelled: boolean;
  count: number;
  n_devices: number;
  sample_value: string;
  devices: { device: string; count: number }[];
}
export interface DeviceAlerts {
  generated_at: string;
  totals: { files_scanned: number; gps_rows: number; alert_rows: number; alert_row_pct: number; distinct_codes: number };
  findings: DeviceAlertFinding[];
}
export async function observeDeviceAlerts(): Promise<DeviceAlerts> {
  const { data } = await aiApi.get('/observe/device-alerts'); return data;
}
export async function observeGetAlertLabels(): Promise<{ labels: Record<string, string> }> {
  const { data } = await aiApi.get('/observe/alert-labels'); return data;
}

// =========================================================================
// Settings — every .env tunable, editable from the UI, plus DB bootstrap.
// =========================================================================

export interface ConfigKey {
  key: string; label: string; description: string;
  secret: boolean; restart: boolean; kind: 'text' | 'number' | 'bool';
  value: string;
}
export interface ConfigSection { section: string; hint: string; keys: ConfigKey[]; }
export interface AppConfig { env_file: string; env_file_exists: boolean; sections: ConfigSection[]; }

export interface DbTableStatus { name: string; rows: number | null; }
export interface DbStatus {
  configured: boolean; url_masked: string; reachable: boolean;
  dialect: string | null; database: string | null;
  tables: DbTableStatus[]; error: string | null;
}
export interface DbInitResult {
  ok: boolean; url_configured: boolean;
  steps: Record<string, { ok: boolean; error?: string }>;
}

export async function fetchAppConfig(): Promise<AppConfig> {
  const { data } = await api.get('/settings/config'); return data;
}
export async function saveAppConfig(updates: Record<string, string>): Promise<{ ok: boolean; saved: string[]; needs_restart: string[] }> {
  const { data } = await api.put('/settings/config', { updates }); return data;
}
export async function fetchDbStatus(): Promise<DbStatus> {
  const { data } = await slowApi.get('/settings/db/status'); return data;
}
export async function initDb(): Promise<DbInitResult> {
  const { data } = await slowApi.post('/settings/db/init', {}, { timeout: 120000 }); return data;
}
export async function observePutAlertLabels(patch: Record<string, string>): Promise<{ labels: Record<string, string> }> {
  const { data } = await aiApi.put('/observe/alert-labels', patch); return data;
}
