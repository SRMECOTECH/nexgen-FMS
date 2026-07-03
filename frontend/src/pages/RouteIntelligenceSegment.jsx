import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft, Route as RouteIcon, Clock, Gauge, Coins,
  Loader2, MapPin, Sparkles, Activity, Wand2, RefreshCw,
  TrendingDown, AlertTriangle, Wind, RotateCcw, Map as MapIcon,
  CloudSun,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import KpiCard from '../components/ui/KpiCard';
import LeafletMap from '../components/ui/LeafletMap';
import ChartCard from '../components/charts/ChartCard';
import DonutChart from '../components/charts/DonutChart';
import {
  riGetSegment, riAnalyzeSegment, riSegmentTrack, riSegmentWeather, riGetTrip,
} from '../lib/routeIntel';

export default function RouteIntelligenceSegment() {
  const { segmentId = '' } = useParams();
  const nav = useNavigate();
  const id = Number(segmentId);
  const [segment, setSegment] = useState(null);
  const [trip, setTrip] = useState(null);
  const [bundle, setBundle] = useState(null);
  const [track, setTrack] = useState([]);
  const [weather, setWeather] = useState(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const s = await riGetSegment(id); setSegment(s);
      const t = await riGetTrip(s.trip_id); setTrip(t);
      setAnalyzing(true);
      const b = await riAnalyzeSegment(id); setBundle(b);
      riSegmentTrack(id, 1500).then(r => setTrack(r.points)).catch(() => {});
    } catch (e) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'failed');
    } finally { setLoading(false); setAnalyzing(false); }
  };
  useEffect(() => { load(); }, [id]);

  const loadWeather = () => riSegmentWeather(id, 3).then(setWeather).catch(e => setError(e?.message));

  const costData = useMemo(() => {
    const c = bundle?.cost_metrics?.breakdown;
    if (!c) return [];
    const movingFuelInr = (c.moving_fuel_liters || 0) * (c.fuel_cost_inr / Math.max(0.01, c.fuel_consumed_liters));
    return [
      { name: 'Fuel (moving)', value: Math.round(movingFuelInr),                     color: '#00C2FF' },
      { name: 'Fuel (idle)',   value: Math.round(c.idle_fuel_waste_inr || 0),        color: '#FF4D6D' },
      { name: 'Driver wages',  value: Math.round(c.driver_cost_inr || 0),            color: '#00E676' },
    ].filter(d => d.value > 0);
  }, [bundle]);

  if (loading || analyzing) return (
    <div className="space-y-4">
      <PageHeader title="Segment" subtitle={analyzing ? 'Running analysis…' : 'Loading…'} />
      <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} />
        {analyzing ? 'Computing segment-scoped cost, efficiency, traffic, waypoints, AI…' : 'Loading…'}
      </div>
    </div>
  );
  if (!segment || !bundle) return (
    <div className="space-y-4">
      <button onClick={() => nav(-1)} className="btn-soft text-xs">
        <ArrowLeft className="w-3.5 h-3.5" /> Back
      </button>
      <div className="card text-sm" style={{ color: 'var(--danger)' }}>
        {error ?? 'Could not load this segment.'}
      </div>
    </div>
  );

  const c = bundle.cost_metrics?.breakdown;
  const eff = bundle.route_metrics?.efficiency;
  const zones = bundle.route_metrics?.speed_zones;
  const traffic = bundle.route_metrics?.traffic;
  const bt = bundle.route_metrics?.backtracking || [];
  const tripSummary = bundle.ai_insights.find(x => x.insight_type === 'trip_summary');
  const costAdvice = bundle.ai_insights.find(x => x.insight_type === 'cost_advice');

  return (
    <div className="space-y-6">
      <button onClick={() => trip ? nav(`/route-intel/trips/${trip.id}`) : nav(-1)} className="btn-soft text-xs">
        <ArrowLeft className="w-3.5 h-3.5" /> {trip ? 'Trip dashboard' : 'Back'}
      </button>

      <PageHeader
        title={`Segment #${segment.seq} · ${segment.from_waypoint ?? '—'} → ${segment.to_waypoint ?? '—'}`}
        subtitle={`Part of trip ${trip?.from_waypoint ?? '—'} → ${trip?.to_waypoint ?? '—'} · ${new Date(segment.start_ts).toLocaleString()}`}
      />

      {tripSummary && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="card ai-glow" style={{ borderColor: 'var(--accent)' }}>
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg shrink-0" style={{ background: 'var(--accent)' }}>
              <Sparkles className="w-4 h-4" color="#000" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-[0.15em] mb-1"
                style={{ color: 'var(--accent)' }}>
                AI Summary (segment-scoped) · {bundle.model}
              </div>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-1)' }}>
                {tripSummary.text}
              </p>
            </div>
          </div>
        </motion.div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KpiCard icon={RouteIcon} label="Distance" value={`${segment.distance_km}`} trend="km" index={0} />
        <KpiCard icon={Clock} label="Duration" value={`${(segment.duration_min / 60).toFixed(1)}`} trend="hours" index={1} />
        <KpiCard icon={Gauge} label="Avg / Max" value={`${segment.avg_speed_kmph} / ${segment.max_speed_kmph}`} trend="km/h" index={2} />
        <KpiCard icon={Activity} label="Efficiency" value={`${Math.round((eff?.route_efficiency ?? 0) * 100)}%`}
          tone={eff && eff.route_efficiency >= 0.85 ? 'success' : 'warning'} index={3} />
        <KpiCard icon={Coins} label="Total cost" value={`₹${Math.round(c?.total_cost_inr ?? 0).toLocaleString()}`}
          trend={`₹${(c?.cost_per_km ?? 0).toFixed(1)}/km`} index={4} />
        <KpiCard icon={AlertTriangle} label="Idle waste" value={`₹${Math.round(c?.idle_fuel_waste_inr ?? 0).toLocaleString()}`}
          tone="warning" index={5} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="Segment route" icon={MapIcon}
          subtitle={`${track.length.toLocaleString()} decimated points`}>
          <LeafletMap points={track} stops={[]} height={420} />
        </ChartCard>

        <ChartCard title="Cost breakdown" icon={Coins}>
          <DonutChart data={costData}
            centerValue={`₹${Math.round(c?.total_cost_inr ?? 0).toLocaleString()}`}
            centerLabel="segment cost" unit=" ₹" height={210} />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard title="Route quality" subtitle={eff?.interpretation ?? '—'} icon={Wand2}>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="straight" value={`${eff?.straight_line_distance_km ?? 0} km`} />
            <Stat label="actual"   value={`${eff?.actual_distance_km ?? 0} km`} />
            <Stat label="excess"   value={`${eff?.excess_distance_km ?? 0} km`} />
            <Stat label="backtracks" value={String(bt.length)} />
          </div>
        </ChartCard>

        <ChartCard title="Traffic loss" icon={Wind}
          subtitle={`${traffic?.time_lost_minutes ?? 0} min in congestion`}>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="dist" value={`${traffic?.distance_in_traffic_km ?? 0} km`} />
            <Stat label="avg"  value={`${traffic?.avg_traffic_speed_kmph ?? 0} km/h`} />
          </div>
        </ChartCard>

        <ChartCard title="Speed zones" icon={Activity}
          subtitle={`consistency: ${zones?.speed_consistency ?? '—'}`}>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="slow"     value={`${zones?.slow_zone_pct ?? 0}%`} />
            <Stat label="moderate" value={`${zones?.moderate_zone_pct ?? 0}%`} />
            <Stat label="normal"   value={`${zones?.normal_zone_pct ?? 0}%`} />
            <Stat label="high"     value={`${zones?.high_zone_pct ?? 0}%`} />
          </div>
        </ChartCard>
      </div>

      {/* Segment-scoped weather on demand */}
      <ChartCard title="Weather along segment" icon={CloudSun}
        subtitle="historical · at segment's own timestamps"
        right={
          !weather && (
            <button onClick={loadWeather} className="btn-soft text-[11px]">
              <RefreshCw className="w-3 h-3" /> fetch
            </button>
          )
        }
      >
        {!weather ? (
          <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
            On-demand — click "fetch" to call open-meteo for this segment's date.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {weather.samples.map((s, i) => (
              <div key={i} className="p-3 rounded-lg" style={{ background: 'var(--bg-2)' }}>
                <div className="text-[10px] mono mb-1" style={{ color: 'var(--fg-3)' }}>
                  @{Math.round(s.fraction * 100)}% · {new Date(s.ts).toLocaleString()}
                </div>
                <div className="text-2xl font-bold mono mb-0.5" style={{ color: 'var(--accent)' }}>
                  {s.weather?.temperature_c ?? '—'}°
                </div>
                <div className="text-xs" style={{ color: 'var(--fg-2)' }}>
                  {s.weather?.weather_description ?? '—'}
                </div>
                <div className="text-[10px] mono mt-1" style={{ color: 'var(--fg-3)' }}>
                  wind {s.weather?.wind_speed_kmh ?? '—'} km/h · cloud {s.weather?.cloud_cover_pct ?? '—'}%
                </div>
              </div>
            ))}
          </div>
        )}
      </ChartCard>

      {costAdvice && (
        <ChartCard title="Cost advice" icon={Sparkles}>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-2)' }}>{costAdvice.text}</p>
        </ChartCard>
      )}

      {error && <div className="card text-xs" style={{ color: 'var(--danger)' }}>{error}</div>}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="p-1.5 rounded-lg" style={{ background: 'var(--bg-2)' }}>
      <div className="text-[9px] uppercase tracking-[0.12em]"
        style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="text-xs font-bold mono" style={{ color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}
