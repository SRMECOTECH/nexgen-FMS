import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft, Route as RouteIcon, Clock, Gauge, Navigation, Timer,
  Coins, Fuel, UserSquare, AlertTriangle, MapPin, Sparkles,
  Activity, RefreshCw, Loader2, TrendingDown, Wand2, Layers,
  CloudSun, Building2, Map as MapIcon, RotateCcw, Wind, Zap,
  Truck, ArrowRight, Calendar, CalendarDays, ListTree, ChevronRight,
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip, Legend, ComposedChart, Bar, Cell, ReferenceLine, Area,
  BarChart, PieChart, Pie, Treemap,
} from 'recharts';
import PageHeader from '../components/ui/PageHeader';
import KpiCard from '../components/ui/KpiCard';
import LeafletMap from '../components/ui/LeafletMap';
import FeatureCatalog from '../components/ui/FeatureCatalog';
import ChartCard from '../components/charts/ChartCard';
import AreaTrend from '../components/charts/AreaTrend';
import DonutChart from '../components/charts/DonutChart';
import { ChartTooltip, AXIS, GRID } from '../components/charts/theme';
import {
  riGetTrip, riGetAnalysis, riAnalyzeTrip, riGetTrack, riRegenAi,
  riTripWeather, riTripWeatherImpact, riTripAddresses, riTripLandmarks, riTripByDay,
  riGetCostConfig, riPutCostConfig, riResetCostConfig, riPredictEta, riEtaLocations,
} from '../lib/routeIntel';

// ============================================================================
// RouteIntelligenceTrip — feature-catalog edition.
//
// Old layout was a single endless scroll of charts. The new layout is:
//   1. Hero      — back, title, AI summary, KPI strip, "See segment-wise
//                  detailed report" CTA.
//   2. Catalog   — every chart / map / table / advice block as a clickable
//                  feature card with a short cool description.
//                  Click → slide-in drawer renders the full detail panel.
//
// Nothing is removed from the page; it's just reorganised so the user can scan
// the available views first and dive into the ones they care about.
// ============================================================================

export default function RouteIntelligenceTrip() {
  const { tripId = '' } = useParams();
  const nav = useNavigate();
  const id = Number(tripId);

  const [trip, setTrip] = useState(null);
  const [bundle, setBundle] = useState(null);
  const [track, setTrack] = useState([]);
  const [weather, setWeather] = useState(null);
  const [weatherImpact, setWeatherImpact] = useState(null);
  const [addresses, setAddresses] = useState(null);
  // { status: 'idle' | 'loading' | 'done' | 'error', data, error }
  const [landmarks, setLandmarks] = useState({ status: 'idle', data: null, error: null });
  const [byDay, setByDay] = useState(null);
  const [loadingByDay, setLoadingByDay] = useState(true);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [regen, setRegen] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const t = await riGetTrip(id); setTrip(t);
      let b;
      try { b = await riGetAnalysis(id); }
      catch { setAnalyzing(true); b = await riAnalyzeTrip(id); }
      setBundle(b);
      riGetTrack(id, 2000).then(r => setTrack(r.points)).catch(() => {});
      setLoadingByDay(true);
      riTripByDay(id)
        .then(setByDay)
        .catch(() => setByDay({ days: [], n_days: 0 }))
        .finally(() => setLoadingByDay(false));
    } catch (e) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'failed');
    } finally { setLoading(false); setAnalyzing(false); }
  };
  useEffect(() => { load(); }, [id]);

  const reanalyze = async () => {
    setAnalyzing(true); setError(null);
    try { setBundle(await riAnalyzeTrip(id)); }
    catch (e) { setError(e?.response?.data?.detail ?? e?.message); }
    finally { setAnalyzing(false); }
  };

  const regenAi = async () => {
    setRegen(true);
    try {
      const res = await riRegenAi(id);
      if (res && res.ok === false && res.detail) setError(res.detail);
      setBundle(await riGetAnalysis(id));
    }
    finally { setRegen(false); }
  };

  // Landmarks are fetched lazily when the card opens; `force` bypasses the
  // 30-day server cache (used by the Retry button after a network failure).
  const loadLandmarks = (force = false) => {
    if (!force && (landmarks.status === 'loading' || landmarks.status === 'done')) return;
    setLandmarks({ status: 'loading', data: null, error: null });
    riTripLandmarks(id, { samples: 8, radius_m: 1500, refresh: force })
      .then(d => setLandmarks({ status: 'done', data: d, error: d?.error ?? null }))
      .catch(e => setLandmarks({
        status: 'error', data: null,
        error: e?.response?.data?.detail ?? e?.message ?? 'lookup failed',
      }));
  };

  // ---- derived series ----
  const speedSeries = useMemo(() => {
    if (!bundle?.time_windows?.length) return [];
    return bundle.time_windows.map(w => ({
      label: w.window_label,
      Effective: Math.round(w.avg_speed_kmph),
      Moving: Math.round(w.avg_moving_speed_kmph),
      Max: Math.round(w.max_speed_kmph),
    }));
  }, [bundle]);

  const distSeries = useMemo(() => {
    if (!bundle?.time_windows?.length) return [];
    return bundle.time_windows.map(w => ({ label: w.window_label, value: Number(w.total_distance_km.toFixed(2)) }));
  }, [bundle]);

  const costData = useMemo(() => {
    const c = bundle?.cost_metrics?.breakdown;
    if (!c) return [];
    const movingFuelInr = (c.moving_fuel_liters || 0) * (c.fuel_cost_inr / Math.max(0.01, c.fuel_consumed_liters));
    return [
      { name: 'Fuel (moving)', value: Math.round(movingFuelInr), color: '#00C2FF' },
      { name: 'Fuel (idle)',   value: Math.round(c.idle_fuel_waste_inr || 0), color: '#FF4D6D' },
      { name: 'Driver wages',  value: Math.round(c.driver_cost_inr || 0), color: '#00E676' },
    ].filter(d => d.value > 0);
  }, [bundle]);

  const zoneData = useMemo(() => {
    const z = bundle?.route_metrics?.speed_zones;
    if (!z) return [];
    return [
      { name: 'Slow (<20)',       value: z.slow_zone_pct,      color: '#FF4D6D' },
      { name: 'Moderate (20-60)', value: z.moderate_zone_pct,  color: '#FFC107' },
      { name: 'Normal (60-80)',   value: z.normal_zone_pct,    color: '#00C2FF' },
      { name: 'High (≥80)',       value: z.high_zone_pct,      color: '#00E676' },
    ].filter(d => d.value > 0);
  }, [bundle]);

  if (loading || analyzing) {
    return (
      <div className="space-y-4">
        <PageHeader title="Route Intelligence" subtitle={analyzing ? 'Running analysis…' : 'Loading…'} />
        <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-3)' }}>
          <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} />
          {analyzing ? 'Computing cost · efficiency · traffic · waypoints · AI…' : 'Loading…'}
        </div>
      </div>
    );
  }
  if (!trip || !bundle) {
    return (
      <div className="space-y-4">
        <button onClick={() => nav(-1)} className="btn-soft text-xs">
          <ArrowLeft className="w-3.5 h-3.5" /> Back
        </button>
        <div className="card text-sm" style={{ color: 'var(--danger)' }}>
          {error ?? 'Could not load this trip.'}
        </div>
      </div>
    );
  }

  const c = bundle.cost_metrics?.breakdown;
  const eff = bundle.route_metrics?.efficiency;
  const zones = bundle.route_metrics?.speed_zones;
  const wp = bundle.waypoints || [];
  // For the Waypoint-sequence chart, trim the trailing "parked at destination"
  // visits: once the truck arrives it keeps logging the same spot (0 km, 0 km/h),
  // which drew a long, misleading flat tail. Cut everything after the last
  // waypoint that actually moved so the chart shows the real journey.
  const wpLastMove = wp.reduce(
    (acc, w, i) => ((w.distance_km || 0) > 0 || (w.avg_speed_kmph || 0) > 0 ? i : acc), 0);
  const wpPlot = wp.slice(0, wpLastMove + 1);
  const wpParkedTail = wp.length - wpPlot.length;
  const opps = bundle.cost_metrics?.opportunities || [];
  const bt = bundle.route_metrics?.backtracking || [];
  const clusters = bundle.route_metrics?.stop_clusters || [];
  const tw = bundle.time_windows || [];
  const segments = trip.segments || [];
  const tripSummary    = bundle.ai_insights.find(x => x.insight_type === 'trip_summary');
  const costAdvice     = bundle.ai_insights.find(x => x.insight_type === 'cost_advice');
  const routeQual      = bundle.ai_insights.find(x => x.insight_type === 'route_quality');
  const recsList       = bundle.ai_insights.find(x => x.insight_type === 'recommendations_list');

  const allMapStops = [
    ...wp.map(w => ({ lat: w.lat, lng: w.lng, minutes: Math.round(w.time_spent_min),
                      near: `${w.waypoint} · ${w.distance_km}km` })),
    ...clusters.map(s => ({ lat: s.lat, lng: s.lng, minutes: s.stop_count,
                            near: `cluster · ${s.stop_count} stops` })),
  ];

  // -----------------------------------------------------------------------
  // Feature catalog config — each entry is a card. Heavy charts/tables live
  // inside the `detail` function so they only render when the drawer opens.
  // -----------------------------------------------------------------------
  const features = [
    {
      id: 'executive_summary',
      icon: Building2,
      title: 'Executive Summary',
      description: 'One-page manager report — headline KPIs and a facts-only observation. No charts, no AI.',
      preview: <PreviewKV k="For" v="managers"
                 sub={`${trip.n_segments ?? 0} segments · ${(trip.n_points ?? 0).toLocaleString()} pts`} />,
      detail: <ExecutiveSummary trip={trip} c={c} zones={zones} eff={eff}
                 stops={clusters.length} processing={bundle.processing_seconds} />,
    },
    {
      id: 'speed_analytics',
      icon: Gauge,
      title: 'Speed Analytics',
      description: 'Speed over time, distribution histogram, speed-zone donut and statistics — how the truck actually drove.',
      preview: <PreviewKV k="Avg / Max" v={`${zones?.avg_speed_kmph ?? 0} / ${zones?.max_speed_kmph ?? 0}`} sub="km/h" />,
      detail: <SpeedAnalyticsPanel windows={tw} zones={zones} />,
    },
    {
      id: 'stop_idle',
      icon: Timer,
      title: 'Stop & Idle Analytics',
      description: 'Every halt cluster: durations, longest/shortest/average, idle share and idle-fuel estimate, with a full stops table.',
      preview: <PreviewKV k="Stops" v={String(clusters.length)} sub={`${(c?.stopped_hours ?? 0).toFixed(1)}h idle`} />,
      detail: <StopIdlePanel stops={clusters} c={c} />,
    },
    {
      id: 'time_analytics',
      icon: CalendarDays,
      title: 'Time Analytics',
      description: 'When the trip happened — distance by hour-of-day, a moving/stopped timeline, and the moving-vs-idle breakdown.',
      preview: <PreviewKV k="Windows" v={String(tw.length)} sub="30-min" />,
      detail: <TimeAnalyticsPanel windows={tw} />,
    },
    {
      id: 'gps_quality',
      icon: Navigation,
      title: 'GPS Quality',
      description: 'Telemetry health — total records, sampling interval, coverage and per-window density.',
      preview: <PreviewKV k="Points" v={(trip.n_points ?? 0).toLocaleString()} sub="records" />,
      detail: <GpsQualityPanel trip={trip} windows={tw} />,
    },
    {
      id: 'route_geometry',
      icon: Navigation,
      title: 'Route Analytics & Geometry',
      description: 'Straight vs actual distance, detour %, backtracking, and route shape — total turns, sharp turns and heading over the trip.',
      preview: <PreviewKV k="Detour" v={`${eff?.excess_percentage ?? 0}%`} sub={`${bt.length} backtracks`} />,
      detail: <RouteGeometryPanel eff={eff} bt={bt} track={track} />,
    },
    {
      id: 'cost_analytics',
      icon: Coins,
      title: 'Cost Analytics',
      description: 'Where the money went — treemap and waterfall of driver, fuel and idle cost, plus cost per km and per hour.',
      preview: <PreviewKV k="Total" v={`₹${Math.round(c?.total_cost_inr ?? 0).toLocaleString()}`} sub={`₹${(c?.cost_per_km ?? 0).toFixed(1)}/km`} />,
      detail: <CostAnalyticsPanel c={c} />,
    },
    {
      id: 'route_map',
      icon: MapIcon,
      title: 'Route on the map',
      description: 'See the actual driven path with halt clusters and waypoint markers pinned on top.',
      preview: <PreviewKV k="GPS points" v={track.length.toLocaleString()} />,
      detail: (
        <ChartCard title="Route" icon={MapIcon}
          subtitle={`${track.length.toLocaleString()} points · waypoints + halt clusters as markers`}>
          <LeafletMap points={track} stops={allMapStops} height={520} />
        </ChartCard>
      ),
    },
    {
      id: 'cost_breakdown',
      icon: Coins,
      title: 'Cost breakdown',
      description: 'Where every rupee on this trip went — fuel moving, fuel wasted at idle, driver wages.',
      preview: <PreviewKV k="Total" v={`₹${Math.round(c?.total_cost_inr ?? 0).toLocaleString()}`}
                          sub={`₹${(c?.cost_per_km ?? 0).toFixed(1)}/km`} />,
      detail: (
        <ChartCard title="Cost breakdown" icon={Coins}
          subtitle={`₹${(c?.cost_per_km ?? 0).toFixed(1)} per km`}>
          <DonutChart data={costData}
            centerValue={`₹${Math.round(c?.total_cost_inr ?? 0).toLocaleString()}`}
            centerLabel="trip cost" unit=" ₹" height={260} />
          <div className="mt-4 grid grid-cols-3 gap-3">
            <Stat icon={Fuel} label="fuel" value={`${(c?.fuel_consumed_liters ?? 0).toFixed(1)} L`} />
            <Stat icon={UserSquare} label="driver" value={`₹${Math.round(c?.driver_cost_inr ?? 0).toLocaleString()}`} />
            <Stat icon={TrendingDown} label="idle" value={`${(c?.idle_fuel_liters ?? 0).toFixed(1)} L`} />
          </div>
        </ChartCard>
      ),
    },
    {
      id: 'day_by_day',
      icon: CalendarDays,
      title: 'Day-by-day timeline',
      description: 'How the trip unfolded each calendar day — distance, moving vs idle minutes, waypoints touched.',
      preview: byDay?.n_days != null
        ? <PreviewKV k="Days" v={String(byDay.n_days)} />
        : <PreviewKV k="Days" v="…" />,
      detail: <DayByDayPanel byDay={byDay} loading={loadingByDay} />,
    },
    {
      id: 'segments',
      icon: Layers,
      title: 'Segments of this trip',
      description: 'Each leg of the trip as its own tile — click any segment for a full per-segment report.',
      preview: <PreviewKV k="Segments" v={String(segments.length)} />,
      detail: <SegmentsPanel segments={segments} />,
    },
    {
      id: 'weather',
      icon: CloudSun,
      title: 'Weather along the route',
      description: 'Historical weather sampled at key points of the route — pulled from open-meteo at trip dates.',
      preview: <PreviewKV k="Source" v="open-meteo" sub="on-demand" />,
      onOpen: () => { if (!weather) riTripWeather(id, 5).then(setWeather).catch(e => setError(e?.message)); },
      detail: <WeatherPanel weather={weather} />,
    },
    {
      id: 'weather_impact',
      icon: Zap,
      title: 'Weather impact on speed',
      description: 'Cross-references every 30-min window of the trip with rain / storm / fog at that exact spot — tells you whether the slowdowns were caused by weather.',
      preview: weatherImpact
        ? <PreviewKV
            k={({weather_was_a_factor: 'Verdict', weather_present_but_minor: 'Verdict',
                 weather_was_clear: 'Verdict', no_data: 'Verdict'}[weatherImpact.verdict])}
            v={({weather_was_a_factor: 'Weather slowed truck',
                 weather_present_but_minor: 'Weather present',
                 weather_was_clear: 'Weather was clear',
                 no_data: '—'}[weatherImpact.verdict])}
            sub={`${weatherImpact.summary.minutes_lost_to_weather ?? 0} min lost`}
          />
        : <PreviewKV k="Status" v="ready" sub="on-demand" />,
      status: weatherImpact?.verdict === 'weather_was_a_factor' ? 'demo' : 'live',
      onOpen: () => { if (!weatherImpact) riTripWeatherImpact(id).then(setWeatherImpact).catch(e => setError(e?.message)); },
      detail: <WeatherImpactPanel impact={weatherImpact} />,
    },
    {
      id: 'addresses',
      icon: MapPin,
      title: 'Pickup & drop addresses',
      description: 'Reverse-geocoded start and end addresses for human-readable trip endpoints.',
      preview: <PreviewKV k="Source" v="Nominatim" sub="cached" />,
      onOpen: () => { if (!addresses) riTripAddresses(id).then(setAddresses).catch(e => setError(e?.message)); },
      detail: <AddressPanel addresses={addresses} />,
    },
    {
      id: 'eta_compare',
      icon: Timer,
      title: 'Predicted vs Actual ETA',
      description: 'Runs the smart-truck ETA model for this route and compares its predicted duration against how long the trip actually took. Edit the origin/destination to re-send clean city names.',
      preview: <PreviewKV k="Model" v="smart-truck ETA" sub="editable route" />,
      status: 'live',
      detail: <EtaComparePanel trip={trip} />,
    },
    {
      id: 'landmarks',
      icon: Building2,
      title: 'Landmarks & POIs near route',
      description: 'Fuel pumps, dhabas, hospitals and rest stops within 1.5 km of the route — one OpenStreetMap query, cached for 30 days.',
      preview: <PreviewKV k="Radius" v="1.5 km" sub="OpenStreetMap" />,
      onOpen: () => loadLandmarks(),
      detail: <LandmarksPanel landmarks={landmarks} onRetry={() => loadLandmarks(true)} />,
    },
    {
      id: 'speed_time',
      icon: Gauge,
      title: 'Speed over time',
      description: 'Three traces side-by-side: effective speed, moving-only speed, and window max — by 30-min window.',
      preview: <PreviewKV k="Avg" v={`${zones?.avg_speed_kmph ?? 0} km/h`} sub={`max ${zones?.max_speed_kmph ?? 0}`} />,
      detail: (
        <ChartCard title="Speed over time" icon={Gauge} subtitle="effective · moving · window max">
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={speedSeries} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip content={(p) => <ChartTooltip {...p} unit=" km/h" />} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
              <Line type="monotone" dataKey="Effective" stroke="#00C2FF" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="Moving"    stroke="#00E676" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="Max"       stroke="#FFC107" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      ),
    },
    {
      id: 'speed_zones',
      icon: Activity,
      title: 'Speed zones',
      description: 'Share of distance spent in slow (<20), moderate (20-60), normal (60-80) and high (≥80) km/h bands.',
      preview: <PreviewKV k="Consistency" v={zones?.speed_consistency ?? '—'} />,
      detail: (
        <ChartCard title="Speed zones" icon={Activity}
          subtitle={`consistency: ${zones?.speed_consistency ?? '—'}`}>
          <DonutChart data={zoneData} unit="%"
            centerValue={`${zones?.avg_speed_kmph ?? 0}`}
            centerLabel="km/h avg" height={300} />
        </ChartCard>
      ),
    },
    {
      id: 'distance_per_window',
      icon: RouteIcon,
      title: 'Distance per window',
      description: 'Kilometres covered in each 30-minute window — peaks tell you where the truck was making real progress.',
      preview: <PreviewKV k="Windows" v={String(distSeries.length)} />,
      detail: (
        <ChartCard title="Distance per window" icon={RouteIcon} subtitle="km covered each window">
          <AreaTrend data={distSeries} xKey="label" yKey="value" unit=" km" height={300} color="#00C2FF" />
        </ChartCard>
      ),
    },
    {
      id: 'route_quality',
      icon: Wand2,
      title: 'Route quality',
      description: 'Detour ratio vs the straight-line, backtracking events, and an AI reading of how clean the route was.',
      preview: <PreviewKV k="Efficiency" v={`${Math.round((eff?.route_efficiency ?? 0) * 100)}%`}
                          sub={`${bt.length} backtracks`} />,
      detail: (
        <ChartCard title="Route quality" subtitle={eff?.interpretation ?? '—'} icon={Wand2}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <Stat label="straight"   value={`${eff?.straight_line_distance_km ?? 0} km`} icon={Navigation} />
            <Stat label="actual"     value={`${eff?.actual_distance_km ?? 0} km`}        icon={RouteIcon} />
            <Stat label="excess"     value={`${eff?.excess_distance_km ?? 0} km`}        icon={TrendingDown} />
            <Stat label="backtracks" value={String(bt.length)}                            icon={RotateCcw} />
          </div>
          {routeQual && (
            <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-2)' }}>{routeQual.text}</p>
          )}
        </ChartCard>
      ),
    },
    {
      id: 'waypoints',
      icon: MapPin,
      title: 'Waypoint sequence',
      description: 'Cumulative kilometres and per-segment distance plotted against waypoint order — the trip\'s spine.',
      preview: <PreviewKV k="Visits" v={String(wp.length)} sub="consolidated" />,
      detail: (
        <ChartCard title="Waypoint sequence" icon={MapPin}
          subtitle={`${wpPlot.length} moving visits · cumulative distance (left) vs per-visit km & speed (right)`
            + (wpParkedTail > 0 ? ` · ${wpParkedTail} parked visits at destination trimmed` : '')}>
          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart
              data={wpPlot.map(w => ({
                seq: w.seq, cum: w.cumulative_distance_km,
                seg: w.distance_km, speed: w.avg_speed_kmph,
              }))}
              margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
              <defs>
                <linearGradient id="cumFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"  stopColor="#00C2FF" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#00C2FF" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="seq" {...AXIS}
                interval={Math.max(0, Math.floor(wpPlot.length / 10))}
                minTickGap={16} tickLine={false} />
              <YAxis yAxisId="cum" {...AXIS} width={44}
                label={{ value: 'cum km', angle: -90, position: 'insideLeft', fontSize: 10, fill: 'var(--fg-3)' }} />
              <YAxis yAxisId="small" orientation="right" {...AXIS} width={40} />
              <Tooltip content={(p) => <ChartTooltip {...p} />} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
              {/* Cumulative distance = the trip's spine, drawn as a smooth filled area. */}
              <Area yAxisId="cum" type="monotone" dataKey="cum" name="cum km"
                stroke="#00C2FF" strokeWidth={2.5} fill="url(#cumFill)" dot={false} activeDot={{ r: 4 }} />
              {/* Per-visit distance + speed on their own small-scale right axis. */}
              <Line yAxisId="small" type="monotone" dataKey="speed" name="avg kph"
                stroke="#FFC107" strokeWidth={1.5} dot={false} />
              <Line yAxisId="small" type="monotone" dataKey="seg" name="seg km"
                stroke="#00E676" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
      ),
    },
    {
      id: 'cost_advice',
      icon: Sparkles,
      title: 'Cost advice (AI)',
      description: 'A natural-language reading of the cost breakdown with the biggest single lever called out.',
      preview: <PreviewKV k="Source" v={bundle.model ?? '—'} />,
      detail: (
        <ChartCard title="Cost advice" icon={Sparkles} subtitle="natural-language reading">
          {costAdvice
            ? <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-2)' }}>{costAdvice.text}</p>
            : <p className="text-xs" style={{ color: 'var(--fg-3)' }}>No advice generated for this trip.</p>}
        </ChartCard>
      ),
    },
    {
      id: 'recommendations',
      icon: Wand2,
      title: 'Recommendations',
      description: 'Prioritised actions with estimated monthly savings — what the dispatcher should do about this trip.',
      preview: <PreviewKV k="Opportunities" v={String(opps.length)}
                          sub={opps.length ? `top: ${opps[0].priority}` : 'none'} />,
      detail: <RecommendationsPanel opps={opps} recsList={recsList} />,
    },
  ];

  return (
    <div className="space-y-6">
      <button onClick={() => nav(`/route-intel/uploads/${trip.upload_id}`)} className="btn-soft text-xs">
        <ArrowLeft className="w-3.5 h-3.5" /> Upload
      </button>

      {/* ===== Hero ====================================================== */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <PageHeader
          title={`${trip.from_waypoint ?? '—'} → ${trip.to_waypoint ?? '—'}`}
          subtitle={`${trip.vehicle_id} · ${trip.n_segments} segments · ${new Date(trip.start_ts).toLocaleString()}`}
        />
        <div className="flex items-center gap-2">
          <button onClick={regenAi} disabled={regen} className="btn-soft text-xs">
            {regen ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
            Regenerate AI
          </button>
          <button onClick={reanalyze} className="btn-primary text-xs flex items-center gap-1">
            <RefreshCw className="w-3 h-3" /> Re-run
          </button>
        </div>
      </div>

      {tripSummary ? (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="card ai-glow" style={{ borderColor: 'var(--accent)' }}>
          <div className="absolute -top-10 -right-10 w-32 h-32 rounded-full blur-2xl pointer-events-none"
            style={{ background: 'var(--accent)', opacity: 0.16 }} />
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg shrink-0" style={{ background: 'var(--accent)' }}>
              <Sparkles className="w-4 h-4" color="#000" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-[0.15em] mb-1" style={{ color: 'var(--accent)' }}>
                AI Summary · {tripSummary.model ?? bundle.model}
              </div>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-1)' }}>{tripSummary.text}</p>
            </div>
          </div>
        </motion.div>
      ) : (
        <div className="card flex items-center justify-between gap-3">
          <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
            No AI summary for this trip yet — click <b>Regenerate AI</b> to have
            the LLM write one (needs the Gemini key on the Settings page).
          </div>
          <button onClick={regenAi} disabled={regen} className="btn-soft text-xs shrink-0">
            {regen ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
            Generate
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KpiCard icon={RouteIcon} label="Distance" value={`${c?.total_distance_km ?? 0}`} trend="km" index={0} />
        <KpiCard icon={Clock} label="Duration" value={`${(c?.total_hours ?? 0).toFixed(1)}`} trend="hours" index={1} />
        <KpiCard icon={Gauge} label="Avg / Max" value={`${zones?.avg_speed_kmph ?? 0} / ${zones?.max_speed_kmph ?? 0}`} trend="km/h" index={2} />
        <KpiCard icon={Activity} label="Efficiency" value={`${Math.round((eff?.route_efficiency ?? 0) * 100)}%`}
          trend={`${eff?.excess_percentage ?? 0}% excess`}
          tone={eff && eff.route_efficiency >= 0.85 ? 'success' : 'warning'} index={3} />
        <KpiCard icon={Coins} label="Total cost" value={`₹${Math.round(c?.total_cost_inr ?? 0).toLocaleString()}`}
          trend={`₹${(c?.cost_per_km ?? 0).toFixed(1)}/km`} index={4} />
        <KpiCard icon={AlertTriangle} label="Idle waste" value={`₹${Math.round(c?.idle_fuel_waste_inr ?? 0).toLocaleString()}`}
          trend={`${(c?.stopped_hours ?? 0).toFixed(1)}h stopped`} tone="warning" index={5} />
      </div>

      {/* "See segment-wise detailed report" CTA — sits right under the KPIs */}
      <Link
        to={segments.length ? `/route-intel/segments/${segments[0].id}` : '#'}
        className="inline-flex items-center justify-between gap-3 w-full md:w-auto px-4 py-3 rounded-xl border transition-all hover:shadow-lg"
        style={{
          background: 'linear-gradient(90deg, var(--accent-soft), transparent)',
          borderColor: 'var(--accent)',
          color: 'var(--accent)',
        }}
      >
        <span className="flex items-center gap-2 text-sm font-semibold">
          <ListTree className="w-4 h-4" />
          See segment-wise detailed report
        </span>
        <span className="text-[11px] mono px-2 py-0.5 rounded" style={{ background: 'var(--bg-2)' }}>
          {segments.length} segment{segments.length === 1 ? '' : 's'}
        </span>
        <ChevronRight className="w-4 h-4" />
      </Link>

      {/* ===== Feature Catalog ============================================ */}
      <section>
        <div className="flex items-center gap-2 mb-3" style={{ color: 'var(--fg-3)' }}>
          <Sparkles className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">Trip features · click any card to drill in</span>
        </div>
        <FeatureCatalog features={features} />
      </section>

      {error && <div className="card text-xs" style={{ color: 'var(--danger)' }}>{error}</div>}
    </div>
  );
}

// ===========================================================================
// Drawer-content panels
// ===========================================================================

function DayByDayPanel({ byDay, loading }) {
  if (loading) {
    return (
      <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3 h-3 animate-spin" /> Computing day-by-day…
      </div>
    );
  }
  if (!byDay?.days?.length) {
    return <div className="text-xs" style={{ color: 'var(--fg-3)' }}>No daily data available.</div>;
  }
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {byDay.days.map((d) => {
          const maxKm = Math.max(...byDay.days.map(x => x.distance_km || 0), 1);
          const pct = Math.round(((d.distance_km || 0) / maxKm) * 100);
          return (
            <motion.div key={d.date}
              initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
              className="p-3 rounded-lg" style={{ background: 'var(--bg-2)' }}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: 'var(--accent)' }}>
                  <Calendar className="w-3 h-3" /> {d.date}
                </div>
                <span className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>{d.day_of_week}</span>
              </div>
              <div className="text-2xl font-bold mono" style={{ color: 'var(--fg-1)' }}>
                {d.distance_km}<span className="text-xs ml-1" style={{ color: 'var(--fg-3)' }}>km</span>
              </div>
              <div className="mt-1.5 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-3)' }}>
                <div className="h-full transition-all" style={{ width: `${pct}%`, background: 'var(--accent)' }} />
              </div>
              <div className="grid grid-cols-3 gap-1.5 mt-2 text-[10px]">
                <div>
                  <div style={{ color: 'var(--fg-3)' }}>moving</div>
                  <div className="mono font-semibold" style={{ color: 'var(--success)' }}>{Math.round(d.moving_min)} min</div>
                </div>
                <div>
                  <div style={{ color: 'var(--fg-3)' }}>idle</div>
                  <div className="mono font-semibold" style={{ color: 'var(--warning)' }}>{Math.round(d.stopped_min)} min</div>
                </div>
                <div>
                  <div style={{ color: 'var(--fg-3)' }}>max kph</div>
                  <div className="mono font-semibold" style={{ color: 'var(--fg-1)' }}>{d.max_speed_kmph}</div>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: 'var(--fg-3)' }} className="text-left">
              <th className="pb-2 pr-3">Date</th>
              <th className="pb-2 pr-3">Day</th>
              <th className="pb-2 pr-3 text-right">Dist (km)</th>
              <th className="pb-2 pr-3 text-right">Moving (min)</th>
              <th className="pb-2 pr-3 text-right">Idle (min)</th>
              <th className="pb-2 pr-3 text-right">Avg moving</th>
              <th className="pb-2 pr-3 text-right">Max kph</th>
              <th className="pb-2 pr-3 text-right">Pings</th>
              <th className="pb-2 pr-3 text-right">WPs</th>
            </tr>
          </thead>
          <tbody>
            {byDay.days.map(d => (
              <tr key={d.date} className="border-t" style={{ borderColor: 'var(--border)' }}>
                <td className="py-1.5 pr-3 font-semibold" style={{ color: 'var(--fg-1)' }}>{d.date}</td>
                <td className="py-1.5 pr-3" style={{ color: 'var(--fg-2)' }}>{d.day_of_week}</td>
                <td className="py-1.5 pr-3 text-right mono">{d.distance_km}</td>
                <td className="py-1.5 pr-3 text-right mono">{Math.round(d.moving_min)}</td>
                <td className="py-1.5 pr-3 text-right mono">{Math.round(d.stopped_min)}</td>
                <td className="py-1.5 pr-3 text-right mono">{d.avg_moving_kmph}</td>
                <td className="py-1.5 pr-3 text-right mono">{d.max_speed_kmph}</td>
                <td className="py-1.5 pr-3 text-right mono">{d.n_pings.toLocaleString()}</td>
                <td className="py-1.5 pr-3 text-right mono">{d.n_waypoints}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SegmentsPanel({ segments }) {
  if (!segments?.length) {
    return <div className="text-xs" style={{ color: 'var(--fg-3)' }}>No segments on this trip.</div>;
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {segments.map((s) => (
        <Link key={s.id} to={`/route-intel/segments/${s.id}`} className="card card-hover p-3 block">
          <div className="flex items-center justify-between mb-2">
            <span className="chip chip-completed">#{s.seq}</span>
            <span className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>
              {new Date(s.start_ts).toLocaleDateString()}
            </span>
          </div>
          <div className="text-xs font-semibold mb-1" style={{ color: 'var(--fg-1)' }}>
            {s.from_waypoint} → {s.to_waypoint}
          </div>
          <div className="grid grid-cols-3 gap-1.5 mt-2">
            <Stat label="dist" value={`${s.distance_km}km`} />
            <Stat label="dur"  value={`${(s.duration_min / 60).toFixed(1)}h`} />
            <Stat label="avg"  value={`${s.avg_speed_kmph}kph`} />
          </div>
          <div className="mt-2 text-[10px] font-semibold flex items-center gap-0.5" style={{ color: 'var(--accent)' }}>
            Open segment <ArrowRight className="w-2.5 h-2.5" />
          </div>
        </Link>
      ))}
    </div>
  );
}

function WeatherPanel({ weather }) {
  if (!weather) {
    return (
      <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3 h-3 animate-spin" /> Fetching from open-meteo…
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {weather.samples.map((s, i) => (
        <div key={i} className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'var(--bg-2)' }}>
          <div>
            <div className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>
              @{Math.round(s.fraction * 100)}% · {new Date(s.ts).toLocaleDateString()}
            </div>
            <div className="text-sm font-semibold" style={{ color: 'var(--fg-1)' }}>
              {s.weather?.weather_description ?? '—'}
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold mono" style={{ color: 'var(--accent)' }}>
              {s.weather?.temperature_c ?? '—'}°
            </div>
            <div className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>
              {s.weather?.wind_speed_kmh ?? '—'} km/h
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function WeatherImpactPanel({ impact }) {
  if (!impact) {
    return (
      <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3 h-3 animate-spin" /> Correlating each window with weather…
      </div>
    );
  }
  const { summary, windows, verdict } = impact;

  const verdictMap = {
    weather_was_a_factor:      { label: 'Weather likely caused several slowdowns', color: 'var(--danger)',  Icon: AlertTriangle },
    weather_present_but_minor: { label: 'Some weather present, mostly clear',       color: 'var(--warning)', Icon: CloudSun },
    weather_was_clear:         { label: 'Weather was clear — slowdowns are not weather-driven', color: 'var(--success)', Icon: Activity },
    no_data:                   { label: 'No weather data for this trip',            color: 'var(--fg-3)',    Icon: AlertTriangle },
  };
  const v = verdictMap[verdict] ?? verdictMap.no_data;

  const bucketColor = (b) => ({
    clear:      'var(--success)',
    rain:       'var(--accent)',
    heavy_rain: 'var(--danger)',
    storm:      'var(--danger)',
    fog:        'var(--warning)',
    snow:       'var(--accent-2)',
  }[b] ?? 'var(--fg-3)');

  // Show the cause-confirmed windows first, then the rest.
  const sorted = [...windows].sort((a, b) =>
    (b.weather_caused ? 1 : 0) - (a.weather_caused ? 1 : 0)
  );

  // Chart data — chronological, so the speed line reads left→right in time.
  const chartData = [...windows]
    .sort((a, b) => new Date(a.window_start) - new Date(b.window_start))
    .map((w) => ({
      label: (w.window_start
        ? new Date(w.window_start).toLocaleDateString(undefined, { day: '2-digit', month: 'short' }) + ' '
        : '') + (w.window_label || ''),
      speed: Number(w.avg_speed_kmph ?? 0),
      rain:  Number(w.weather?.rain_mm ?? 0),
      bucket: w.weather_bucket,
      caused: !!w.weather_caused,
      temp: w.weather?.temperature_c,
      wind: w.weather?.wind_kmh,
    }));
  const barColor = (d) =>
    d.caused ? 'var(--danger)' : d.bucket === 'clear' ? 'var(--success)' : bucketColor(d.bucket);
  const tickInterval = Math.max(0, Math.floor(chartData.length / 8));

  return (
    <div className="space-y-4">
      {/* Verdict banner */}
      <div
        className="rounded-2xl p-4 flex items-start gap-3"
        style={{ background: 'var(--bg-2)', border: `1px solid ${v.color}` }}
      >
        <v.Icon className="w-5 h-5 mt-0.5 shrink-0" style={{ color: v.color }} />
        <div className="flex-1">
          <div className="text-[10px] uppercase tracking-[0.15em]" style={{ color: v.color }}>
            Verdict
          </div>
          <div className="text-sm font-semibold" style={{ color: 'var(--fg-1)' }}>
            {v.label}
          </div>
          {summary.minutes_lost_to_weather > 0 && (
            <div className="text-[11px] mt-1" style={{ color: 'var(--fg-3)' }}>
              ~{summary.minutes_lost_to_weather} min of slow driving overlap with adverse weather.
            </div>
          )}
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Windows scanned"    value={String(summary.windows_total)} />
        <Stat label="Slow windows"        value={String(summary.windows_slow)} />
        <Stat label="Adverse weather"     value={String(summary.windows_adverse_weather)} />
        <Stat label="Weather-caused"      value={String(summary.windows_slow_and_adverse)} />
        <Stat label="Median speed"        value={`${summary.median_speed_kmph} km/h`} />
        <Stat label="Slow threshold"      value={`${summary.slow_threshold_kmph} km/h`} />
        <Stat label="Minutes lost"        value={`${summary.minutes_lost_to_weather}`} />
        <Stat label="Confidence"          value={summary.windows_slow_and_adverse >= 3 ? 'High' : summary.windows_slow_and_adverse > 0 ? 'Medium' : 'Low'} />
      </div>

      {/* ===== Speed vs weather chart ===== */}
      <div className="rounded-2xl p-4" style={{ background: 'var(--bg-2)', border: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--fg-3)' }}>
            Speed vs weather · over the trip
          </div>
          <div className="flex items-center gap-3 text-[10px]" style={{ color: 'var(--fg-3)' }}>
            <LegendDot color="var(--success)" label="clear" />
            <LegendDot color="var(--accent)"  label="rain" />
            <LegendDot color="var(--danger)"  label="weather-caused" />
            <LegendDot color="var(--accent-2)" label="rain mm" line />
          </div>
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={chartData} margin={{ top: 12, right: 4, bottom: 0, left: -18 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="label" interval={tickInterval} tickLine={false}
              tick={{ fontSize: 9, fill: 'var(--fg-3)' }} axisLine={{ stroke: 'var(--border)' }} />
            <YAxis yAxisId="spd" tick={{ fontSize: 10, fill: 'var(--fg-3)' }} tickLine={false}
              axisLine={false} width={42}
              label={{ value: 'km/h', angle: -90, position: 'insideLeft', fontSize: 10, fill: 'var(--fg-3)' }} />
            <YAxis yAxisId="rain" orientation="right" tick={{ fontSize: 10, fill: 'var(--accent-2)' }}
              tickLine={false} axisLine={false} width={34} />
            <Tooltip content={<WeatherChartTip />} cursor={{ fill: 'var(--bg-3)', opacity: 0.4 }} />
            <ReferenceLine yAxisId="spd" y={summary.slow_threshold_kmph} stroke="var(--warning)"
              strokeDasharray="4 4"
              label={{ value: `slow < ${summary.slow_threshold_kmph}`, fontSize: 10, fill: 'var(--warning)', position: 'insideTopRight' }} />
            <Bar yAxisId="spd" dataKey="speed" radius={[2, 2, 0, 0]} maxBarSize={16}>
              {chartData.map((d, i) => <Cell key={i} fill={barColor(d)} />)}
            </Bar>
            <Line yAxisId="rain" type="monotone" dataKey="rain" stroke="var(--accent-2)"
              strokeWidth={1.6} dot={false} name="rain mm" />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="text-[10px] mt-1" style={{ color: 'var(--fg-3)' }}>
          Red bars = slow <b>and</b> adverse weather at that spot. Blue line = rainfall (right axis).
        </div>
      </div>

      {/* Per-window timeline */}
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>
          Per-window correlation · weather-caused moments first
        </div>
        <div className="space-y-1.5 max-h-[60vh] overflow-y-auto pr-1">
          {sorted.length === 0 && (
            <div className="text-xs" style={{ color: 'var(--fg-3)' }}>No windows to analyse.</div>
          )}
          {sorted.map((w, i) => {
            const dt = w.window_start ? new Date(w.window_start) : null;
            const dateLbl = dt
              ? dt.toLocaleDateString(undefined, { day: '2-digit', month: 'short' })
              : '';
            return (
            <div
              key={i}
              className="flex items-start gap-3 p-2.5 rounded-lg text-xs"
              style={{
                background: 'var(--bg-2)',
                borderLeft: `3px solid ${w.weather_caused ? 'var(--danger)' : bucketColor(w.weather_bucket)}`,
              }}
            >
              <div className="mono w-28 shrink-0" style={{ color: 'var(--fg-3)' }}>
                <span className="block text-[10px]" style={{ color: 'var(--accent)' }}>{dateLbl}</span>
                {w.window_label}
              </div>
              <div
                className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded shrink-0"
                style={{ background: 'var(--bg-3)', color: bucketColor(w.weather_bucket) }}
              >
                {w.weather_bucket.replace('_', ' ')}
              </div>
              <div className="flex-1 min-w-0">
                <div style={{ color: 'var(--fg-1)' }}>{w.note}</div>
                <div className="text-[10px] mono mt-0.5" style={{ color: 'var(--fg-3)' }}>
                  {w.avg_speed_kmph} km/h · {(w.weather?.temperature_c ?? '—')}°C ·
                  rain {(w.weather?.rain_mm ?? 0).toFixed(1)} mm · wind {(w.weather?.wind_kmh ?? 0).toFixed(0)} km/h
                </div>
              </div>
              {w.weather_caused && (
                <span
                  className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded shrink-0"
                  style={{ background: 'var(--danger)', color: '#000' }}
                >
                  caused
                </span>
              )}
            </div>
            );
          })}
        </div>
      </div>

      <div className="text-[10px] mono pt-2 border-t" style={{ color: 'var(--fg-4)', borderColor: 'var(--border)' }}>
        Source: open-meteo hourly archive · cached per (lat 3dp, lng 3dp, day) in ri_weather_cache.
        Classification: WMO weather code + rain mm/h + wind km/h. "Caused" = slow window AND adverse bucket.
      </div>
    </div>
  );
}

// Small colour key for the weather chart.
function LegendDot({ color, label, line }) {
  return (
    <span className="flex items-center gap-1">
      <span
        style={{
          background: line ? 'transparent' : color,
          borderTop: line ? `2px solid ${color}` : 'none',
          width: line ? 12 : 8, height: line ? 0 : 8, borderRadius: line ? 0 : 9999,
          display: 'inline-block',
        }}
      />
      {label}
    </span>
  );
}

// Rich tooltip for the speed-vs-weather chart.
function WeatherChartTip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg px-3 py-2 text-[11px]"
      style={{ background: 'var(--bg-1)', border: '1px solid var(--border)', color: 'var(--fg-1)' }}>
      <div className="font-semibold mb-0.5">{d.label}</div>
      <div className="mono" style={{ color: d.caused ? 'var(--danger)' : 'var(--fg-2)' }}>
        {d.speed} km/h {d.caused ? '· weather-caused' : ''}
      </div>
      <div className="mono" style={{ color: 'var(--fg-3)' }}>
        {d.bucket?.replace('_', ' ')} · rain {d.rain.toFixed(1)} mm
        {d.temp != null ? ` · ${d.temp}°C` : ''}{d.wind != null ? ` · wind ${Math.round(d.wind)} km/h` : ''}
      </div>
    </div>
  );
}

// §1 Executive Summary — one-page manager report. KPI cards + facts only.
function ExecutiveSummary({ trip, c, zones, eff, stops, processing }) {
  const num = (v, d = 0) => (v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d }));
  const hoursLabel = (h) => {
    if (h == null) return '—';
    const m = Math.round(h * 60);
    return `${Math.floor(m / 60)}h ${m % 60}m`;
  };

  const distance  = c?.total_distance_km ?? trip.distance_km ?? 0;
  const durationH = c?.total_hours ?? (trip.duration_min ? trip.duration_min / 60 : 0);
  const avgSpeed  = zones?.avg_speed_kmph ?? trip.avg_speed_kmph ?? 0;
  const maxSpeed  = zones?.max_speed_kmph ?? trip.max_speed_kmph ?? 0;
  const movingH   = c?.moving_hours ?? (trip.moving_min ? trip.moving_min / 60 : 0);
  const idleH     = c?.stopped_hours ?? (trip.stopped_min ? trip.stopped_min / 60 : 0);
  const gpsPts    = trip.n_points ?? 0;
  const segments  = trip.n_segments ?? 0;
  const cost      = c?.total_cost_inr ?? 0;
  const costPerKm = c?.cost_per_km ?? 0;
  const efficiency = c?.efficiency_pct ?? Math.round((eff?.route_efficiency ?? 0) * 100);

  const idlePct = (movingH + idleH) > 0 ? Math.round((idleH / (movingH + idleH)) * 100) : 0;
  const belowHighway = avgSpeed > 0 && avgSpeed < 60;
  const avgGapSec = gpsPts > 0 && trip.duration_min ? Math.round((trip.duration_min * 60) / gpsPts) : null;
  const quality = avgGapSec == null ? 'unknown' : avgGapSec <= 90 ? 'excellent' : avgGapSec <= 240 ? 'good' : 'fair';

  const kpis = [
    { icon: RouteIcon,  label: 'Distance',        value: `${num(distance, 1)} km` },
    { icon: Clock,      label: 'Duration',        value: hoursLabel(durationH) },
    { icon: Gauge,      label: 'Average Speed',   value: `${num(avgSpeed, 1)} km/h` },
    { icon: Zap,        label: 'Maximum Speed',   value: `${num(maxSpeed, 0)} km/h` },
    { icon: Truck,      label: 'Moving Time',     value: hoursLabel(movingH) },
    { icon: Timer,      label: 'Idle Time',       value: hoursLabel(idleH) },
    { icon: MapPin,     label: 'Stops',           value: num(stops, 0) },
    { icon: Navigation, label: 'GPS Points',      value: num(gpsPts, 0) },
    { icon: Layers,     label: 'Segments',        value: num(segments, 0) },
    { icon: Coins,      label: 'Cost',            value: `₹${num(cost, 0)}` },
    { icon: Activity,   label: 'Efficiency',      value: `${num(efficiency, 0)}%` },
    { icon: RefreshCw,  label: 'Processing Time', value: processing != null ? `${processing}s` : '—' },
  ];

  const facts = [
    `Trip covered ${num(distance, 1)} km${trip.from_waypoint ? ` from ${trip.from_waypoint} to ${trip.to_waypoint}` : ''}.`,
    `Average speed (${num(avgSpeed, 1)} km/h) remained ${belowHighway ? 'below' : 'at or above'} the highway average (~60 km/h).`,
    `Idle time represented ${idlePct}% of trip duration.`,
    `${segments} operational segment${segments === 1 ? '' : 's'} detected.`,
    `GPS quality remained ${quality}${avgGapSec != null ? ` (~${avgGapSec}s between records)` : ''}.`,
    `${num(gpsPts, 0)} telemetry records processed${processing != null ? ` in ${processing}s` : ''}.`,
    `Estimated cost ₹${num(cost, 0)} (₹${num(costPerKm, 1)}/km).`,
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-xl p-3 border"
            style={{ background: 'var(--bg-2)', borderColor: 'var(--border)' }}>
            <div className="flex items-center gap-2 mb-2">
              <div className="p-1.5 rounded-md" style={{ background: 'var(--bg-3)' }}>
                <k.icon className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
              </div>
              <div className="text-[10px] uppercase tracking-[0.12em]" style={{ color: 'var(--fg-3)' }}>{k.label}</div>
            </div>
            <div className="text-xl font-bold mono" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
              {k.value}
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-2xl p-4" style={{ background: 'var(--bg-2)', border: '1px solid var(--border)' }}>
        <div className="flex items-center gap-2 mb-3">
          <Building2 className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          <div className="text-sm font-semibold" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
            Executive Observation
          </div>
          <span className="text-[10px] mono px-1.5 py-0.5 rounded"
            style={{ background: 'var(--bg-3)', color: 'var(--fg-3)' }}>facts only · no AI</span>
        </div>
        <ul className="space-y-1.5">
          {facts.map((f, i) => (
            <li key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--fg-2)' }}>
              <span style={{ color: 'var(--accent)' }}>•</span><span>{f}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// ---- shared helpers for the analytics panels -------------------------------
const _r1 = (v) => Math.round((Number(v) || 0) * 10) / 10;
const _mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
const _median = (a) => {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y); const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const TIP = { contentStyle: { background: 'var(--bg-1)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 11 },
              labelStyle: { color: 'var(--fg-2)' }, itemStyle: { color: 'var(--fg-1)' } };
function EmptyNote({ text }) {
  return <div className="text-xs" style={{ color: 'var(--fg-3)' }}>{text}</div>;
}
function MiniStat({ label, value, tone }) {
  return (
    <div className="rounded-lg p-2.5 border" style={{ background: 'var(--bg-2)', borderColor: 'var(--border)' }}>
      <div className="text-[10px] uppercase tracking-[0.1em]" style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="text-lg font-bold mono" style={{ color: tone || 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}

// §3 Speed Analytics
function SpeedAnalyticsPanel({ windows, zones }) {
  if (!windows?.length) return <EmptyNote text="No time-window data — re-run analysis." />;
  const series = windows.map((w, i) => ({
    t: w.window_label || String(i), avg: _r1(w.avg_speed_kmph),
    moving: _r1(w.avg_moving_speed_kmph), max: _r1(w.max_speed_kmph),
  }));
  const bands = [[0, 20], [20, 40], [40, 60], [60, 80], [80, 999]];
  const hist = bands.map(([lo, hi]) => ({
    band: hi === 999 ? `${lo}+` : `${lo}-${hi}`,
    count: windows.filter(w => (w.avg_speed_kmph || 0) >= lo && (w.avg_speed_kmph || 0) < hi).length,
  }));
  const zoneData = [
    { name: 'Slow', value: _r1(zones?.slow_zone_pct), fill: 'var(--danger)' },
    { name: 'Moderate', value: _r1(zones?.moderate_zone_pct), fill: 'var(--warning)' },
    { name: 'Normal', value: _r1(zones?.normal_zone_pct), fill: 'var(--success)' },
    { name: 'Fast', value: _r1(zones?.high_zone_pct), fill: 'var(--accent)' },
  ].filter(z => z.value > 0);
  const avgs = windows.map(w => w.avg_speed_kmph || 0);
  return (
    <div className="space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Speed over time</div>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={series} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid {...GRID} vertical={false} />
            <XAxis dataKey="t" {...AXIS} interval={Math.max(0, Math.floor(series.length / 8))} minTickGap={16} tickLine={false} />
            <YAxis {...AXIS} />
            <Tooltip {...TIP} />
            <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
            <Line type="monotone" dataKey="max" name="max" stroke="var(--fg-4)" strokeWidth={1} dot={false} />
            <Line type="monotone" dataKey="moving" name="moving avg" stroke="var(--accent)" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="avg" name="avg" stroke="#FFC107" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Speed distribution</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={hist} margin={{ top: 6, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="band" {...AXIS} tickLine={false} />
              <YAxis {...AXIS} allowDecimals={false} />
              <Tooltip {...TIP} />
              <Bar dataKey="count" name="windows" radius={[3, 3, 0, 0]} fill="var(--accent)" maxBarSize={40} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Speed zones</div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={zoneData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={72} paddingAngle={2}>
                {zoneData.map((z, i) => <Cell key={i} fill={z.fill} />)}
              </Pie>
              <Tooltip {...TIP} formatter={(v, n) => [`${v}%`, n]} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
        <MiniStat label="Mean" value={`${_r1(_mean(avgs))}`} />
        <MiniStat label="Median" value={`${_r1(_median(avgs))}`} />
        <MiniStat label="Max" value={`${_r1(Math.max(...avgs))}`} />
        <MiniStat label="Min" value={`${_r1(Math.min(...avgs))}`} />
        <MiniStat label="Std dev" value={`${_r1(zones?.speed_std_dev)}`} />
        <MiniStat label="Consistency" value={`${_r1(zones?.speed_consistency)}`} />
      </div>
    </div>
  );
}

// §4 Stop & Idle Analytics
function StopIdlePanel({ stops, c }) {
  const durs = (stops || []).map(s => ({
    ...s,
    mins: Math.max(0, (new Date(s.last_visit) - new Date(s.first_visit)) / 60000),
  }));
  const vals = durs.map(d => d.mins);
  const total = durs.length;
  const longest = total ? Math.max(...vals) : 0;
  const shortest = total ? Math.min(...vals) : 0;
  const idlePct = c && c.total_hours > 0 ? Math.round((c.stopped_hours / c.total_hours) * 100) : 0;
  const bands = [[0, 5], [5, 15], [15, 30], [30, 60], [60, 120], [120, 1e9]];
  const hist = bands.map(([lo, hi]) => ({
    band: hi === 1e9 ? `${lo}m+` : `${lo}-${hi}m`,
    count: durs.filter(d => d.mins >= lo && d.mins < hi).length,
  }));
  const table = [...durs].sort((a, b) => b.mins - a.mins).slice(0, 20);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
        <MiniStat label="Total stops" value={String(total)} />
        <MiniStat label="Longest" value={`${_r1(longest)}m`} tone="var(--danger)" />
        <MiniStat label="Shortest" value={`${_r1(shortest)}m`} />
        <MiniStat label="Average" value={`${_r1(_mean(vals))}m`} />
        <MiniStat label="Idle %" value={`${idlePct}%`} tone="var(--warning)" />
        <MiniStat label="Idle fuel" value={`${_r1(c?.idle_fuel_liters)} L`} tone="var(--warning)" />
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Stop duration distribution</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={hist} margin={{ top: 6, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid {...GRID} vertical={false} />
            <XAxis dataKey="band" {...AXIS} tickLine={false} />
            <YAxis {...AXIS} allowDecimals={false} />
            <Tooltip {...TIP} />
            <Bar dataKey="count" name="stops" radius={[3, 3, 0, 0]} fill="var(--warning)" maxBarSize={44} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Stops (longest first)</div>
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <table className="w-full text-xs">
            <thead style={{ background: 'var(--bg-2)' }}>
              <tr className="text-left" style={{ color: 'var(--fg-3)' }}>
                <th className="px-3 py-2">Start</th><th className="px-3 py-2">End</th>
                <th className="px-3 py-2 text-right">Duration</th><th className="px-3 py-2 text-right">Visits</th>
                <th className="px-3 py-2">Coordinates</th>
              </tr>
            </thead>
            <tbody>
              {table.map((s, i) => (
                <tr key={i} style={{ borderTop: '1px solid var(--border-soft)' }}>
                  <td className="px-3 py-1.5 mono" style={{ color: 'var(--fg-2)' }}>{new Date(s.first_visit).toLocaleString()}</td>
                  <td className="px-3 py-1.5 mono" style={{ color: 'var(--fg-2)' }}>{new Date(s.last_visit).toLocaleString()}</td>
                  <td className="px-3 py-1.5 mono text-right" style={{ color: 'var(--fg-1)' }}>{_r1(s.mins)}m</td>
                  <td className="px-3 py-1.5 mono text-right" style={{ color: 'var(--fg-3)' }}>{s.stop_count}</td>
                  <td className="px-3 py-1.5 mono" style={{ color: 'var(--fg-3)' }}>{_r1(s.lat * 1000) / 1000}, {_r1(s.lng * 1000) / 1000}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// §6 Time Analytics
function TimeAnalyticsPanel({ windows }) {
  if (!windows?.length) return <EmptyNote text="No time-window data — re-run analysis." />;
  const byHour = {};
  windows.forEach(w => { const h = new Date(w.window_start).getHours(); byHour[h] = (byHour[h] || 0) + (w.total_distance_km || 0); });
  const hourly = Array.from({ length: 24 }, (_, h) => ({ hour: String(h).padStart(2, '0'), km: _r1(byHour[h] || 0) }));
  const moving = windows.reduce((a, w) => a + (w.moving_time_sec || 0), 0);
  const stopped = windows.reduce((a, w) => a + (w.stopped_time_sec || 0), 0);
  const durData = [
    { name: 'Moving', value: _r1(moving / 3600), fill: 'var(--success)' },
    { name: 'Idle', value: _r1(stopped / 3600), fill: 'var(--warning)' },
  ];
  return (
    <div className="space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Distance by hour of day</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={hourly} margin={{ top: 6, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid {...GRID} vertical={false} />
            <XAxis dataKey="hour" {...AXIS} tickLine={false} interval={1} />
            <YAxis {...AXIS} />
            <Tooltip {...TIP} formatter={(v) => [`${v} km`, 'distance']} />
            <Bar dataKey="km" radius={[3, 3, 0, 0]} fill="var(--accent)" maxBarSize={22} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Moving vs idle (hours)</div>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={durData} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={2}>
                {durData.map((d, i) => <Cell key={i} fill={d.fill} />)}
              </Pie>
              <Tooltip {...TIP} formatter={(v, n) => [`${v} h`, n]} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Movement timeline (each block = 30 min)</div>
          <div className="flex flex-wrap gap-0.5">
            {windows.map((w, i) => (
              <div key={i} title={`${w.window_label} · ${w.dominant_status} · ${_r1(w.avg_speed_kmph)} km/h`}
                style={{
                  width: 8, height: 18, borderRadius: 2,
                  background: w.dominant_status === 'Moving' ? 'var(--success)' : 'var(--fg-4)',
                }} />
            ))}
          </div>
          <div className="flex items-center gap-3 text-[10px] mt-2" style={{ color: 'var(--fg-3)' }}>
            <span className="flex items-center gap-1"><span style={{ width: 8, height: 8, borderRadius: 9999, background: 'var(--success)', display: 'inline-block' }} /> moving</span>
            <span className="flex items-center gap-1"><span style={{ width: 8, height: 8, borderRadius: 9999, background: 'var(--fg-4)', display: 'inline-block' }} /> stopped</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// §7 GPS Quality
function GpsQualityPanel({ trip, windows }) {
  const pts = trip.n_points || 0;
  const durMin = trip.duration_min || 0;
  const gap = pts > 0 && durMin ? Math.round((durMin * 60) / pts) : null;
  const perMin = gap ? (60 / gap).toFixed(2) : '—';
  const quality = gap == null ? 'unknown' : gap <= 90 ? 'excellent' : gap <= 240 ? 'good' : 'fair';
  const density = (windows || []).map((w, i) => ({ t: w.window_label || String(i), n: w.waypoint_count || 0 }));
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <MiniStat label="GPS records" value={pts.toLocaleString()} />
        <MiniStat label="Sampling gap" value={gap != null ? `${gap}s` : '—'} />
        <MiniStat label="Records / min" value={perMin} />
        <MiniStat label="Quality" value={quality} tone={quality === 'excellent' ? 'var(--success)' : quality === 'good' ? 'var(--accent)' : 'var(--warning)'} />
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Records per 30-min window (coverage density)</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={density} margin={{ top: 6, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid {...GRID} vertical={false} />
            <XAxis dataKey="t" {...AXIS} interval={Math.max(0, Math.floor(density.length / 8))} minTickGap={16} tickLine={false} />
            <YAxis {...AXIS} allowDecimals={false} />
            <Tooltip {...TIP} />
            <Bar dataKey="n" name="records" radius={[2, 2, 0, 0]} fill="var(--accent-2)" maxBarSize={14} />
          </BarChart>
        </ResponsiveContainer>
        <div className="text-[10px] mt-1" style={{ color: 'var(--fg-3)' }}>
          Dips toward zero mark thin-signal windows (tunnels, dead zones, device offline).
        </div>
      </div>
    </div>
  );
}

// ---- geometry helpers (JS) -------------------------------------------------
function _haversineKm(a, b) {
  const R = 6371, toR = Math.PI / 180;
  const dLat = (b.lat - a.lat) * toR, dLng = (b.lng - a.lng) * toR;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * toR) * Math.cos(b.lat * toR) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}
function _bearing(a, b) {
  const toR = Math.PI / 180, toD = 180 / Math.PI;
  const dLng = (b.lng - a.lng) * toR;
  const y = Math.sin(dLng) * Math.cos(b.lat * toR);
  const x = Math.cos(a.lat * toR) * Math.sin(b.lat * toR) -
            Math.sin(a.lat * toR) * Math.cos(b.lat * toR) * Math.cos(dLng);
  return (Math.atan2(y, x) * toD + 360) % 360;
}

// §2 + §8 Route Analytics & Geometry
function RouteGeometryPanel({ eff, bt, track }) {
  // Compute turns from the driven track — but only between points that actually
  // moved (>20 m), so a parked truck's GPS jitter doesn't fake thousands of turns.
  const moving = [];
  for (let i = 1; i < (track?.length || 0); i++) {
    if (_haversineKm(track[i - 1], track[i]) > 0.02) moving.push(track[i]);
  }
  let turns = 0, sharp = 0;
  const headingSeries = [];
  for (let i = 2; i < moving.length; i++) {
    const b1 = _bearing(moving[i - 2], moving[i - 1]);
    const b2 = _bearing(moving[i - 1], moving[i]);
    let d = Math.abs(b2 - b1); if (d > 180) d = 360 - d;
    if (d > 30) turns++;
    if (d > 60) sharp++;
    headingSeries.push({ i, heading: Math.round(b2) });
  }
  const step = Math.max(1, Math.floor(headingSeries.length / 250));
  const heading = headingSeries.filter((_, i) => i % step === 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
        <MiniStat label="Straight" value={`${eff?.straight_line_distance_km ?? 0} km`} />
        <MiniStat label="Road (OSRM)" value={eff?.osrm_road_distance_km != null ? `${eff.osrm_road_distance_km} km` : '—'} tone="var(--accent)" />
        <MiniStat label="Actual" value={`${eff?.actual_distance_km ?? 0} km`} />
        <MiniStat label="Detour" value={`${eff?.excess_percentage ?? 0}%`} tone="var(--warning)" />
        <MiniStat label="Backtracks" value={String(bt?.length ?? 0)} />
        <MiniStat label="Efficiency" value={`${Math.round((eff?.route_efficiency ?? 0) * 100)}%`} />
        <MiniStat label="Total turns" value={String(turns)} />
        <MiniStat label="Sharp turns" value={String(sharp)} tone="var(--danger)" />
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Heading over the trip (0°=N, 90°=E, 180°=S, 270°=W)</div>
        {heading.length > 1 ? (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={heading} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="i" {...AXIS} tick={false} />
              <YAxis {...AXIS} domain={[0, 360]} ticks={[0, 90, 180, 270, 360]} />
              <Tooltip {...TIP} formatter={(v) => [`${v}°`, 'heading']} />
              <Line type="monotone" dataKey="heading" stroke="var(--accent)" strokeWidth={1.2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : <EmptyNote text="Not enough moving GPS points to derive heading." />}
      </div>
    </div>
  );
}

// §10 Cost Analytics — live-configurable. The physical quantities (distance,
// hours) are fixed by the trip; only the RATES are editable, so the whole ₹
// breakdown recomputes instantly as you type — no re-analysis needed.
const _COST_FIELDS = [
  ['fuel_price_per_liter', 'Fuel ₹/L'],
  ['fuel_efficiency_kmpl', 'Mileage km/L'],
  ['driver_wage_per_hour', 'Driver ₹/h'],
  ['idle_fuel_consumption_lph', 'Idle L/h'],
  ['maintenance_per_km', 'Maint. ₹/km'],
  ['toll_per_trip', 'Toll ₹/trip'],
];
function CostAnalyticsPanel({ c }) {
  const [cfg, setCfg] = useState(null);
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState('');

  useEffect(() => { riGetCostConfig().then(r => setCfg(r.config)).catch(() => setCfg({})); }, []);
  if (!c) return <EmptyNote text="No cost metrics — re-run analysis." />;
  if (!cfg) return <EmptyNote text="Loading cost model…" />;

  const g = (k, d) => (cfg[k] != null ? Number(cfg[k]) : d);
  const dist = c.total_distance_km || 0;
  const stoppedH = c.stopped_hours || 0;
  const totalH = c.total_hours || 0;

  // Recompute the full breakdown from fixed quantities + editable rates.
  const price = g('fuel_price_per_liter', 100), kmpl = g('fuel_efficiency_kmpl', 4) || 1;
  const wage = g('driver_wage_per_hour', 150), idleLph = g('idle_fuel_consumption_lph', 1.5);
  const movingFuelL = dist / kmpl;
  const idleFuelL = stoppedH * idleLph;
  const movingFuel = _r1(movingFuelL * price);
  const idle = _r1(idleFuelL * price);
  const driver = _r1(totalH * wage);
  const maint = _r1(dist * g('maintenance_per_km', 0));
  const toll = _r1(g('toll_per_trip', 0));
  const total = _r1(movingFuel + idle + driver + maint + toll);
  const costPerKm = dist > 0 ? _r1(total / dist) : 0;
  const costHour = totalH > 0 ? _r1(total / totalH) : 0;
  const inr = (v) => `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

  const parts = [
    { name: 'Driver', size: driver }, { name: 'Moving fuel', size: movingFuel },
    { name: 'Idle fuel', size: idle }, { name: 'Maintenance', size: maint }, { name: 'Toll', size: toll },
  ].filter(p => p.size > 0);
  let run = 0;
  const wf = [
    { name: 'Driver', base: 0, val: driver, fill: 'var(--accent)' },
    { name: 'Moving fuel', base: (run += driver, run), val: movingFuel, fill: 'var(--success)' },
    { name: 'Idle fuel', base: (run += movingFuel, run), val: idle, fill: 'var(--warning)' },
    ...(maint > 0 ? [{ name: 'Maint.', base: (run += idle, run), val: maint, fill: 'var(--accent-2)' }] : []),
    ...(toll > 0 ? [{ name: 'Toll', base: (run += maint, run), val: toll, fill: 'var(--genai)' }] : []),
    { name: 'Total', base: 0, val: total, fill: 'var(--fg-2)' },
  ];

  const save = () => { setSaved('saving'); riPutCostConfig(cfg).then(() => setSaved('saved')).catch(() => setSaved('err')); };
  const reset = () => { setSaved(''); riResetCostConfig().then(r => setCfg(r.config)).catch(() => {}); };

  return (
    <div className="space-y-4">
      {/* config bar */}
      <div className="rounded-xl border" style={{ borderColor: 'var(--border)', background: 'var(--bg-2)' }}>
        <button onClick={() => setOpen(o => !o)} className="w-full px-3 py-2 flex items-center justify-between text-left">
          <span className="text-xs font-semibold flex items-center gap-2" style={{ color: 'var(--fg-1)' }}>
            <Wand2 className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} /> Configure cost model
          </span>
          <span className="text-[10px]" style={{ color: 'var(--fg-3)' }}>{open ? 'hide' : 'edit rates — recomputes live'}</span>
        </button>
        {open && (
          <div className="px-3 pb-3">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
              {_COST_FIELDS.map(([k, label]) => (
                <label key={k} className="flex flex-col gap-1">
                  <span className="text-[10px]" style={{ color: 'var(--fg-3)' }}>{label}</span>
                  <input type="number" step="any" value={cfg[k] ?? 0}
                    onChange={(e) => { setSaved(''); setCfg(s => ({ ...s, [k]: e.target.value === '' ? '' : Number(e.target.value) })); }}
                    className="text-xs px-2 py-1.5 rounded mono"
                    style={{ background: 'var(--bg-3)', color: 'var(--fg-1)', border: '1px solid var(--border)', colorScheme: 'dark' }} />
                </label>
              ))}
            </div>
            <div className="flex items-center gap-2 mt-2">
              <button onClick={save} className="btn-primary text-[11px]">Save as default</button>
              <button onClick={reset} className="btn-soft text-[11px]">Reset</button>
              {saved === 'saved' && <span className="text-[10px]" style={{ color: 'var(--success)' }}>saved — applies to future analyses</span>}
              {saved === 'saving' && <span className="text-[10px]" style={{ color: 'var(--fg-3)' }}>saving…</span>}
              {saved === 'err' && <span className="text-[10px]" style={{ color: 'var(--danger)' }}>save failed</span>}
              <span className="text-[10px] ml-auto" style={{ color: 'var(--fg-3)' }}>charts below update as you type</span>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <MiniStat label="Total cost" value={inr(total)} />
        <MiniStat label="Cost / km" value={inr(costPerKm)} />
        <MiniStat label="Cost / hour" value={inr(costHour)} />
        <MiniStat label="Idle cost" value={inr(idle)} tone="var(--warning)" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Cost breakdown (treemap)</div>
          <ResponsiveContainer width="100%" height={220}>
            <Treemap data={parts} dataKey="size" nameKey="name" stroke="var(--bg-1)" content={<CostTreeCell />} />
          </ResponsiveContainer>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Cost build-up (waterfall)</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={wf} margin={{ top: 6, right: 8, bottom: 0, left: -8 }}>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="name" {...AXIS} tickLine={false} />
              <YAxis {...AXIS} />
              <Tooltip {...TIP} formatter={(v, n) => (n === 'val' ? [inr(v), 'amount'] : null)} />
              <Bar dataKey="base" stackId="w" fill="transparent" />
              <Bar dataKey="val" stackId="w" radius={[3, 3, 0, 0]} maxBarSize={48}>
                {wf.map((d, i) => <Cell key={i} fill={d.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="text-[10px]" style={{ color: 'var(--fg-3)' }}>
        Live from fixed quantities ({_r1(dist)} km · {_r1(totalH)} h · {_r1(idleFuelL)} L idle) × your rates.
        "Save as default" persists these rates for future trip analyses.
      </div>
    </div>
  );
}
const _COST_COLORS = { 'Driver': 'var(--accent)', 'Moving fuel': 'var(--success)', 'Idle fuel': 'var(--warning)',
  'Maintenance': 'var(--accent-2)', 'Toll': 'var(--genai)' };
function CostTreeCell(props) {
  const { x, y, width, height } = props;
  if (!(width > 1) || !(height > 1)) return null;
  const name = props.name ?? props.payload?.name;
  const size = props.size ?? props.payload?.size ?? props.value ?? 0;
  const fill = _COST_COLORS[name] || 'var(--accent-2)';
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} style={{ fill, stroke: 'var(--bg-1)', strokeWidth: 2 }} />
      {width > 60 && height > 28 && (
        <text x={x + 6} y={y + 18} fill="#000" fontSize={11} fontWeight={600}>
          {name} · ₹{Number(size).toLocaleString('en-IN')}
        </text>
      )}
    </g>
  );
}

// Predicted vs Actual ETA — calls the smart-truck ETA model and compares.
const _mins = (m) => {
  if (m == null) return '—';
  const t = Math.round(m);
  return `${Math.floor(t / 60)}h ${t % 60}m`;
};
// Autocomplete input backed by smart-truck's known route cities.
function LocationInput({ value, onChange, placeholder }) {
  const [sug, setSug] = useState([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!value || value.trim().length < 2) { setSug([]); return; }
    const t = setTimeout(() => { riEtaLocations(value.trim()).then(setSug).catch(() => setSug([])); }, 250);
    return () => clearTimeout(t);
  }, [value]);
  return (
    <div className="relative flex-1 min-w-0">
      <input value={value} placeholder={placeholder}
        onChange={(e) => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        className="w-full text-xs px-2 py-1.5 rounded mono"
        style={{ background: 'var(--bg-3)', color: 'var(--fg-1)', border: '1px solid var(--border)' }} />
      {open && sug.length > 0 && (
        <div className="absolute z-30 mt-1 w-full rounded-md border max-h-52 overflow-y-auto"
          style={{ background: 'var(--bg-1)', borderColor: 'var(--border)' }}>
          {sug.map((s) => (
            <button key={s} onMouseDown={() => { onChange(s); setOpen(false); }}
              className="block w-full text-left px-2 py-1.5 text-xs mono hover:opacity-80"
              style={{ color: 'var(--fg-2)' }}>{s}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function EtaComparePanel({ trip }) {
  const [origin, setOrigin] = useState(trip.from_waypoint || '');
  const [destination, setDestination] = useState(trip.to_waypoint || '');
  const [eta, setEta] = useState(null);
  const [ranRoute, setRanRoute] = useState({ o: trip.from_waypoint, d: trip.to_waypoint });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const run = (o, d) => {
    if (!o || !d) { setErr('Enter both origin and destination.'); return; }
    setLoading(true); setErr(null); setRanRoute({ o, d });
    riPredictEta({ origin: o, destination: d, trip_km: trip.distance_km, trip_start: trip.start_ts })
      .then(setEta).catch((e) => setErr(e?.response?.data?.detail ?? e?.message ?? 'failed'))
      .finally(() => setLoading(false));
  };
  useEffect(() => { run(trip.from_waypoint, trip.to_waypoint); /* on mount */ }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const editor = (
    <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border)', background: 'var(--bg-2)' }}>
      <div className="text-[10px] uppercase tracking-[0.15em] mb-2" style={{ color: 'var(--fg-3)' }}>
        Route sent to the model — pick a known city for a sharper ETA
      </div>
      <div className="flex flex-col md:flex-row items-stretch md:items-center gap-2">
        <LocationInput value={origin} onChange={setOrigin} placeholder="Origin city (e.g. PUNE)" />
        <ArrowRight className="w-4 h-4 shrink-0 hidden md:block" style={{ color: 'var(--fg-3)' }} />
        <LocationInput value={destination} onChange={setDestination} placeholder="Destination city (e.g. RAIPUR)" />
        <button onClick={() => run(origin, destination)} disabled={loading} className="btn-primary text-xs flex items-center gap-1 shrink-0">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Re-run
        </button>
      </div>
    </div>
  );

  if (loading && !eta) {
    return (
      <div className="space-y-3">
        {editor}
        <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
          <Loader2 className="w-3 h-3 animate-spin" /> Asking the smart-truck ETA model…
        </div>
      </div>
    );
  }
  if (err && !eta) return <div className="space-y-3">{editor}<div className="text-xs" style={{ color: 'var(--danger)' }}>{err}</div></div>;
  if (!eta) return editor;

  const pred = eta.predicted_duration_minutes || 0;
  const routeAvg = eta.route_avg_duration;
  const actualTotal = trip.duration_min || 0;
  const actualMoving = trip.moving_min || 0;
  const source = eta.estimation_source || 'model';
  const sourceLabel = { osrm_estimate: 'OSRM estimate', osrm_fallback: 'OSRM fallback', model: 'ML model' }[source] || 'ML model';
  // No matching row in smart-truck's route_summary → no historical trips on this lane.
  const hasHistory = routeAvg != null && routeAvg > 0;

  // Fairest driving comparison: predicted vs actual MOVING time (total includes
  // post-arrival parking, which would unfairly inflate "actual").
  const delta = pred ? actualMoving - pred : null;
  const pct = pred ? Math.round(((actualMoving - pred) / pred) * 100) : null;
  const verdict = !pred ? { label: 'No prediction', color: 'var(--fg-3)' }
    : actualMoving <= pred * 1.1 ? { label: 'On time', color: 'var(--success)' }
    : actualMoving <= pred * 1.5 ? { label: 'Delayed', color: 'var(--warning)' }
    : { label: 'Severely delayed', color: 'var(--danger)' };

  const bars = [
    { name: 'Predicted', min: Math.round(pred), fill: 'var(--accent)' },
    ...(routeAvg ? [{ name: 'Route avg', min: Math.round(routeAvg), fill: 'var(--accent-2)' }] : []),
    { name: 'Actual (moving)', min: Math.round(actualMoving), fill: 'var(--success)' },
    { name: 'Actual (total)', min: Math.round(actualTotal), fill: 'var(--fg-4)' },
  ];

  return (
    <div className="space-y-4">
      {editor}
      {err && <div className="text-xs" style={{ color: 'var(--danger)' }}>{err}</div>}
      {!hasHistory && (
        <div className="rounded-xl p-3 flex items-start gap-2" style={{ background: 'var(--bg-2)', border: '1px solid var(--warning)' }}>
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--warning)' }} />
          <div className="text-xs" style={{ color: 'var(--fg-1)' }}>
            <b>No previous data available for this route.</b>{' '}
            <span style={{ color: 'var(--fg-3)' }}>
              smart-truck has no historical trips for {ranRoute.o} → {ranRoute.d}, so the ETA below is a {sourceLabel.toLowerCase()} — not a history-backed prediction. Pick a route the model knows for a sharper number.
            </span>
          </div>
        </div>
      )}
      {/* verdict banner */}
      <div className="rounded-2xl p-4 flex items-start gap-3" style={{ background: 'var(--bg-2)', border: `1px solid ${verdict.color}` }}>
        <Timer className="w-5 h-5 mt-0.5 shrink-0" style={{ color: verdict.color }} />
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em]" style={{ color: verdict.color }}>Verdict</div>
          <div className="text-sm font-semibold" style={{ color: 'var(--fg-1)' }}>{verdict.label}</div>
          {delta != null && (
            <div className="text-[11px] mt-1" style={{ color: 'var(--fg-3)' }}>
              Driving time was {delta >= 0 ? 'over' : 'under'} the model's ETA by {_mins(Math.abs(delta))} ({pct >= 0 ? '+' : ''}{pct}%).
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <MiniStat label="Predicted ETA" value={_mins(pred)} tone="var(--accent)" />
        <MiniStat label="Route history avg" value={routeAvg ? _mins(routeAvg) : '—'} />
        <MiniStat label="Actual (moving)" value={_mins(actualMoving)} tone="var(--success)" />
        <MiniStat label="Actual (total)" value={_mins(actualTotal)} />
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--fg-3)' }}>Predicted vs actual (minutes)</div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={bars} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 20 }}>
            <CartesianGrid {...GRID} horizontal={false} />
            <XAxis type="number" {...AXIS} />
            <YAxis type="category" dataKey="name" {...AXIS} width={92} />
            <Tooltip {...TIP} formatter={(v) => [_mins(v), 'duration']} />
            <Bar dataKey="min" radius={[0, 3, 3, 0]} maxBarSize={22}>
              {bars.map((b, i) => <Cell key={i} fill={b.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="text-[10px] leading-relaxed" style={{ color: 'var(--fg-3)' }}>
        Source: <span className="mono">{sourceLabel}</span> for {ranRoute.o} → {ranRoute.d}
        {eta.osrm_distance_km ? ` · OSRM route ${eta.osrm_distance_km} km` : ''}.
        Compared against actual <b>moving</b> time (total includes post-arrival parking).
        Cleaner origin/destination names give the model more route history and a sharper ETA.
      </div>
    </div>
  );
}

function AddressPanel({ addresses }) {
  if (!addresses) {
    return (
      <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3 h-3 animate-spin" /> Reverse-geocoding…
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] mb-1" style={{ color: 'var(--accent)' }}>Start</div>
        <div className="text-sm" style={{ color: 'var(--fg-1)' }}>{addresses.start?.formatted_address ?? '—'}</div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] mb-1" style={{ color: 'var(--accent)' }}>End</div>
        <div className="text-sm" style={{ color: 'var(--fg-1)' }}>{addresses.end?.formatted_address ?? '—'}</div>
      </div>
    </div>
  );
}

function LandmarksPanel({ landmarks, onRetry }) {
  const { status, data, error } = landmarks;

  if (status === 'idle' || status === 'loading') {
    return (
      <div className="space-y-2">
        <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
          <Loader2 className="w-3 h-3 animate-spin" /> Searching OpenStreetMap along the route…
        </div>
        <div className="text-[10px]" style={{ color: 'var(--fg-4)' }}>
          One query for the whole corridor — usually a few seconds; cached afterwards.
        </div>
      </div>
    );
  }

  if (status === 'error' || (error && !(data?.landmarks?.length))) {
    return (
      <div className="rounded-lg p-4 space-y-2" style={{ background: 'var(--bg-2)' }}>
        <div className="text-xs font-semibold flex items-center gap-2" style={{ color: 'var(--warning)' }}>
          <AlertTriangle className="w-3.5 h-3.5" /> Landmark lookup failed
        </div>
        <div className="text-[11px] mono" style={{ color: 'var(--fg-3)' }}>
          {error || 'All OpenStreetMap mirrors are busy right now.'}
        </div>
        <button onClick={onRetry} className="btn-soft text-xs mt-1">
          <RefreshCw className="w-3 h-3" /> Try again
        </button>
      </div>
    );
  }

  const pois = data?.landmarks ?? [];
  if (pois.length === 0) {
    return (
      <div className="space-y-2">
        <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
          No named landmarks within {(data?.radius_m ?? 1500) / 1000} km of this route —
          it likely runs through open country.
        </div>
        <button onClick={onRetry} className="btn-soft text-xs">
          <RefreshCw className="w-3 h-3" /> Search again
        </button>
      </div>
    );
  }

  // group by category, nearest first inside each group
  const groups = pois.reduce((acc, p) => {
    (acc[p.category] = acc[p.category] || []).push(p);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between text-[11px]" style={{ color: 'var(--fg-3)' }}>
        <span>
          <span className="font-semibold" style={{ color: 'var(--fg-1)' }}>{pois.length}</span> places within{' '}
          {(data?.radius_m ?? 1500) / 1000} km of the route
          {data?.source === 'cache' && ' · from cache'}
          {data?.source === 'stale-cache' && ' · cached copy (mirrors busy)'}
        </span>
        <button onClick={onRetry} className="btn-soft text-[11px]" title="Bypass the cache and re-query OpenStreetMap">
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      <div className="space-y-4 max-h-[62vh] overflow-y-auto pr-1">
        {Object.entries(groups).map(([category, items]) => (
          <div key={category}>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-sm">{items[0].icon ?? '📍'}</span>
              <span className="text-[10px] uppercase tracking-[0.12em] font-semibold" style={{ color: 'var(--accent)' }}>
                {category}
              </span>
              <span className="text-[10px] mono" style={{ color: 'var(--fg-4)' }}>{items.length}</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
              {items.map((p, i) => (
                <div key={i} className="flex items-center justify-between gap-2 text-xs px-2.5 py-2 rounded"
                  style={{ background: 'var(--bg-2)' }}>
                  <span className="font-medium truncate" style={{ color: 'var(--fg-1)' }}>{p.name}</span>
                  <span className="mono text-[10px] shrink-0" style={{ color: 'var(--fg-3)' }}>
                    {p.distance_km < 1 ? `${Math.round(p.distance_km * 1000)} m` : `${p.distance_km.toFixed(1)} km`}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecommendationsPanel({ opps, recsList }) {
  return (
    <div className="space-y-4">
      {opps.length === 0 && (
        <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
          Operation is running clean — no high-impact recommendations.
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {opps.map((o, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }} className="p-3 rounded-lg"
            style={{
              background: 'var(--bg-2)',
              borderLeft: `3px solid ${o.priority === 'HIGH' ? 'var(--danger)' : 'var(--warning)'}`,
            }}>
            <div className="flex items-center justify-between mb-1">
              <div className="text-[10px] uppercase tracking-[0.12em] font-semibold"
                style={{ color: o.priority === 'HIGH' ? 'var(--danger)' : 'var(--warning)' }}>
                {o.priority} · {o.category}
              </div>
              <div className="text-[10px] mono font-bold" style={{ color: 'var(--success)' }}>
                ₹{Math.round(o.monthly_savings_inr).toLocaleString()}/mo
              </div>
            </div>
            <div className="text-xs" style={{ color: 'var(--fg-1)' }}>{o.recommendation}</div>
          </motion.div>
        ))}
      </div>
      {recsList && (
        <div className="p-3 rounded-lg" style={{ background: 'var(--bg-2)' }}>
          <div className="text-[10px] uppercase tracking-[0.12em] mb-2" style={{ color: 'var(--accent)' }}>
            Narrative
          </div>
          <pre className="text-xs whitespace-pre-wrap leading-relaxed" style={{ color: 'var(--fg-2)', fontFamily: 'inherit' }}>
            {recsList.text}
          </pre>
        </div>
      )}
    </div>
  );
}

// ===========================================================================
// Small helpers
// ===========================================================================

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="p-1.5 rounded-lg" style={{ background: 'var(--bg-2)' }}>
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-[0.12em]" style={{ color: 'var(--fg-3)' }}>
        {Icon && <Icon className="w-2.5 h-2.5" />} {label}
      </div>
      <div className="text-xs font-bold mono" style={{ color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}

function PreviewKV({ k, v, sub }) {
  return (
    <div className="flex items-baseline justify-between gap-2 px-2 py-1.5 rounded-md" style={{ background: 'var(--bg-2)' }}>
      <span className="text-[10px] uppercase tracking-[0.12em]" style={{ color: 'var(--fg-3)' }}>{k}</span>
      <span className="text-right">
        <span className="text-sm font-bold mono" style={{ color: 'var(--fg-1)' }}>{v}</span>
        {sub && <span className="block text-[9px] mono" style={{ color: 'var(--fg-3)' }}>{sub}</span>}
      </span>
    </div>
  );
}
