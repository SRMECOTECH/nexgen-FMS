/**
 * Route Intelligence — API client (plain JS, no TypeScript).
 * Wraps the FastAPI endpoints under /api/v1/route-intel/*.
 */
import axios from 'axios';

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1');

const fast = axios.create({ baseURL: BASE, timeout: 15000 });
const slow = axios.create({ baseURL: BASE, timeout: 180000 });

// --- system ----------------------------------------------------------------
export async function riStatus() {
  const { data } = await fast.get('/route-intel/status');
  return data;
}
export async function riStreamlitStatus() {
  const { data } = await fast.get('/route-intel/streamlit/status');
  return data;
}
export async function riStreamlitStart() {
  const { data } = await fast.post('/route-intel/streamlit/start');
  return data;
}

// --- uploads ---------------------------------------------------------------
export async function riUpload(file) {
  const fd = new FormData();
  fd.append('file', file);
  const { data } = await slow.post('/route-intel/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}
export async function riIngestLocal(path) {
  const { data } = await slow.post('/route-intel/ingest-local', { path });
  return data;
}
export async function riListUploads(limit = 50) {
  const { data } = await fast.get('/route-intel/uploads', { params: { limit } });
  return data;
}
export async function riGetUpload(id) {
  const { data } = await fast.get(`/route-intel/uploads/${id}`);
  return data;
}
export async function riGetUploadTrip(id) {
  const { data } = await fast.get(`/route-intel/uploads/${id}/trip`);
  return data;
}

// --- trips (one trip per upload) ------------------------------------------
export async function riGetTrip(id) {
  const { data } = await fast.get(`/route-intel/trips/${id}`);
  return data;
}
export async function riGetSegments(tripId) {
  const { data } = await fast.get(`/route-intel/trips/${tripId}/segments`);
  return data;
}
export async function riAnalyzeTrip(tripId, params = {}) {
  const { data } = await slow.post(`/route-intel/trips/${tripId}/analyze`, params);
  return data;
}
export async function riGetAnalysis(tripId) {
  const { data } = await slow.get(`/route-intel/trips/${tripId}/analysis`);
  return data;
}
export async function riGetTrack(tripId, maxPoints = 2000) {
  const { data } = await slow.get(`/route-intel/trips/${tripId}/track`, {
    params: { max_points: maxPoints },
  });
  return data;
}
export async function riRegenAi(tripId) {
  const { data } = await slow.post(`/route-intel/trips/${tripId}/regenerate-ai`);
  return data;
}

// --- segments --------------------------------------------------------------
export async function riGetSegment(segId) {
  const { data } = await fast.get(`/route-intel/segments/${segId}`);
  return data;
}
export async function riAnalyzeSegment(segId, params = {}) {
  const { data } = await slow.post(`/route-intel/segments/${segId}/analyze`, params);
  return data;
}
export async function riSegmentTrack(segId, maxPoints = 1000) {
  const { data } = await slow.get(`/route-intel/segments/${segId}/track`, {
    params: { max_points: maxPoints },
  });
  return data;
}
export async function riSegmentWeather(segId, samples = 3) {
  const { data } = await slow.get(`/route-intel/segments/${segId}/weather`, {
    params: { samples },
  });
  return data;
}

// --- enrichment ------------------------------------------------------------
export async function riTripWeather(tripId, samples = 5) {
  const { data } = await slow.get(`/route-intel/trips/${tripId}/weather`, {
    params: { samples },
  });
  return data;
}
export async function riTripWeatherImpact(tripId) {
  const { data } = await slow.get(`/route-intel/trips/${tripId}/weather-impact`);
  return data;
}
export async function riTripAddresses(tripId) {
  const { data } = await slow.get(`/route-intel/trips/${tripId}/addresses`);
  return data;
}
export async function riSegmentAddresses(tripId) {
  const { data } = await slow.get(`/route-intel/trips/${tripId}/segment-addresses`);
  return data;
}
export async function riTripByDay(tripId) {
  const { data } = await slow.get(`/route-intel/trips/${tripId}/by-day`);
  return data;
}

export async function riTripLandmarks(tripId, opts = {}) {
  const params = { samples: opts.samples ?? 5 };
  if (opts.radius_m) params.radius_m = opts.radius_m;
  if (opts.categories?.length) params.categories = opts.categories.join(',');
  const { data } = await slow.get(`/route-intel/trips/${tripId}/landmarks`, { params });
  return data;
}

// --- comparisons + insights feed ------------------------------------------
export async function riCompare(tripIds, params = {}) {
  const { data } = await slow.post('/route-intel/compare', { trip_ids: tripIds, ...params });
  return data;
}
export async function riListComparisons(limit = 30) {
  const { data } = await fast.get('/route-intel/comparisons', { params: { limit } });
  return data;
}
export async function riGetComparison(id) {
  const { data } = await fast.get(`/route-intel/comparisons/${id}`);
  return data;
}
export async function riListInsights(limit = 50, insightType, dateFrom, dateTo, dedupe = false) {
  const params = { limit };
  if (insightType) params.insight_type = insightType;
  if (dateFrom)    params.date_from = dateFrom;
  if (dateTo)      params.date_to = dateTo;
  if (dedupe)      params.dedupe = true;
  const { data } = await fast.get('/route-intel/insights', { params });
  return data;     // { insights, dedupe_available, embedding_model, raw_count?, deduped_count }
}

// --- cost config (UI-editable recommendation numbers) --------------------
export async function riGetCostConfig() {
  const { data } = await fast.get('/route-intel/cost-config');
  return data;   // { config, defaults }
}
export async function riPutCostConfig(patch) {
  const { data } = await fast.put('/route-intel/cost-config', patch);
  return data;   // { config, defaults }
}
export async function riResetCostConfig() {
  const { data } = await fast.post('/route-intel/cost-config/reset');
  return data;
}

// --- structured recommendations (headline → entries → detail) ------------
export async function riListRecommendations(limitTrips = 500) {
  const { data } = await fast.get('/route-intel/recommendations', {
    params: { limit_trips: limitTrips },
  });
  return data;   // { categories:[{category,priority,count,total_monthly_savings_inr,entries:[...]}], totals, config }
}
export async function riGetRecommendation(recId) {
  const { data } = await fast.get(`/route-intel/recommendations/${recId}`);
  return data;   // { ...entry, cost_breakdown, efficiency, config_used, trip }
}

// --- AI assistant ---------------------------------------------------------
export async function riAssistantAsk(query, ctx = {}) {
  const { data } = await slow.post('/route-intel/assistant/ask', { query, ...ctx });
  return data;
}
export async function riAssistantSuggestions() {
  const { data } = await fast.get('/route-intel/assistant/suggestions');
  return data;
}
