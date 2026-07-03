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
  const [landmarks, setLandmarks] = useState(null);
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
    try { await riRegenAi(id); setBundle(await riGetAnalysis(id)); }
    finally { setRegen(false); }
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
      id: 'landmarks',
      icon: Building2,
      title: 'Landmarks & POIs near route',
      description: 'Dhabas, fuel pumps and named places within 1.5 km of the route — sourced from OSM Overpass.',
      preview: <PreviewKV k="Radius" v="1.5 km" sub="Overpass" />,
      onOpen: () => { if (!landmarks) riTripLandmarks(id, { samples: 5, radius_m: 1500 }).then(setLandmarks).catch(e => setError(e?.message)); },
      detail: <LandmarksPanel landmarks={landmarks} />,
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
      preview: <PreviewKV k="Source" v={bundle.model ?? 'rule-based'} />,
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

      {tripSummary && (
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
                AI Summary · {bundle.model}
              </div>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-1)' }}>{tripSummary.text}</p>
            </div>
          </div>
        </motion.div>
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

function LandmarksPanel({ landmarks }) {
  if (!landmarks) {
    return (
      <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3 h-3 animate-spin" /> Querying Overpass…
      </div>
    );
  }
  return (
    <div>
      <div className="text-[11px] mb-2" style={{ color: 'var(--fg-3)' }}>
        {landmarks.landmarks?.length ?? 0} POIs along route
      </div>
      <div className="space-y-1 max-h-[60vh] overflow-y-auto pr-1">
        {(landmarks.landmarks ?? []).map((p, i) => (
          <div key={i} className="flex items-start justify-between gap-2 text-xs p-2 rounded" style={{ background: 'var(--bg-2)' }}>
            <div className="min-w-0">
              <div className="font-semibold truncate" style={{ color: 'var(--fg-1)' }}>{p.name}</div>
              <div className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>{p.category} · {p.distance_km} km</div>
            </div>
          </div>
        ))}
        {(landmarks.landmarks ?? []).length === 0 && (
          <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
            No POIs found (Overpass mirror may be rate-limiting — try again).
          </div>
        )}
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
