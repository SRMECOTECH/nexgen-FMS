import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft, Route as RouteIcon, Clock, Gauge, Navigation, Timer,
  Coins, Fuel, UserSquare, AlertTriangle, MapPin, Sparkles,
  Activity, RefreshCw, Loader2, TrendingDown, Wand2, Layers,
  PieChart as PieIcon, Map as MapIcon, RotateCcw, Wind, Zap,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import KpiCard from '../components/ui/KpiCard';
import LeafletMap from '../components/ui/LeafletMap';
import ChartCard from '../components/charts/ChartCard';
import AreaTrend from '../components/charts/AreaTrend';
import BarChart from '../components/charts/BarChart';
import DonutChart from '../components/charts/DonutChart';
import { ChartTooltip, AXIS, GRID, SERIES } from '../components/charts/theme';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip, Legend,
} from 'recharts';
import {
  riGetAnalysis, riAnalyzeTrip, riGetTrack, riRegenAi,
  type RIAnalysisBundle,
} from '../lib/api';

export default function RouteIntelligenceTrip() {
  const { tripId = '' } = useParams();
  const nav = useNavigate();
  const id = Number(tripId);
  const [bundle, setBundle] = useState<RIAnalysisBundle | null>(null);
  const [track, setTrack] = useState<{ lat: number; lng: number; speed: number; ts: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [regen, setRegen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      let b: RIAnalysisBundle;
      try {
        b = await riGetAnalysis(id);
      } catch {
        // not analyzed yet → run analyze
        setAnalyzing(true);
        b = await riAnalyzeTrip(id);
      }
      setBundle(b);
      const t = await riGetTrack(id).catch(() => null);
      if (t) setTrack(t.points);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'failed');
    } finally {
      setLoading(false); setAnalyzing(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  const reanalyze = async () => {
    setAnalyzing(true); setError(null);
    try {
      const b = await riAnalyzeTrip(id);
      setBundle(b);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'failed');
    } finally { setAnalyzing(false); }
  };

  const regenAi = async () => {
    setRegen(true);
    try {
      await riRegenAi(id);
      const b = await riGetAnalysis(id);
      setBundle(b);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'failed');
    } finally { setRegen(false); }
  };

  // derived data
  const speedSeries = useMemo(() => {
    if (!bundle?.time_windows?.length) return [];
    return bundle.time_windows.map((w) => ({
      label: w.window_label,
      Effective: Math.round(w.avg_speed_kmph),
      Moving: Math.round(w.avg_moving_speed_kmph),
      Max: Math.round(w.max_speed_kmph),
    }));
  }, [bundle]);

  const distSeries = useMemo(() => {
    if (!bundle?.time_windows?.length) return [];
    return bundle.time_windows.map((w) => ({ label: w.window_label, value: Number(w.total_distance_km.toFixed(2)) }));
  }, [bundle]);

  const costData = useMemo(() => {
    const c = bundle?.cost_metrics?.breakdown;
    if (!c) return [];
    return [
      { name: 'Fuel (moving)', value: Math.round((c.moving_fuel_liters || 0) * (c.fuel_cost_inr / Math.max(0.01, c.fuel_consumed_liters))), color: SERIES[1] },
      { name: 'Fuel (idle)', value: Math.round(c.idle_fuel_waste_inr || 0), color: SERIES[5] },
      { name: 'Driver wages', value: Math.round(c.driver_cost_inr || 0), color: SERIES[4] },
    ].filter((d) => d.value > 0);
  }, [bundle]);

  const zoneData = useMemo(() => {
    const z = bundle?.route_metrics?.speed_zones;
    if (!z) return [];
    return [
      { name: 'Slow (<20)', value: z.slow_zone_pct, color: SERIES[6] },
      { name: 'Moderate (20-60)', value: z.moderate_zone_pct, color: SERIES[5] },
      { name: 'Normal (60-80)', value: z.normal_zone_pct, color: SERIES[1] },
      { name: 'High (≥80)', value: z.high_zone_pct, color: SERIES[4] },
    ].filter((d) => d.value > 0);
  }, [bundle]);

  if (loading || analyzing) return (
    <div className="space-y-4">
      <PageHeader title="Route Intelligence" subtitle={analyzing ? 'Running analysis…' : 'Loading…'} />
      <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} />
        {analyzing ? 'Computing cost, efficiency, traffic, waypoints, AI insights…' : 'Loading…'}
      </div>
    </div>
  );

  if (!bundle) return (
    <div className="space-y-4">
      <button onClick={() => nav(-1)} className="flex items-center gap-2 text-sm"
        style={{ color: 'var(--accent)' }}>
        <ArrowLeft className="w-4 h-4" /> Back
      </button>
      <div className="card text-sm" style={{ color: 'var(--danger)' }}>
        {error ?? 'Could not load this trip.'}
      </div>
    </div>
  );

  const t = bundle.trip;
  const c = bundle.cost_metrics?.breakdown;
  const eff = bundle.route_metrics?.efficiency;
  const zones = bundle.route_metrics?.speed_zones;
  const traffic = bundle.route_metrics?.traffic;
  const wp = bundle.waypoints || [];
  const opps = bundle.cost_metrics?.opportunities || [];
  const bt = bundle.route_metrics?.backtracking || [];
  const clusters = bundle.route_metrics?.stop_clusters || [];
  const tripSummary = bundle.ai_insights.find((x) => x.insight_type === 'trip_summary');
  const costAdvice = bundle.ai_insights.find((x) => x.insight_type === 'cost_advice');
  const routeQual = bundle.ai_insights.find((x) => x.insight_type === 'route_quality');
  const trafficCallout = bundle.ai_insights.find((x) => x.insight_type === 'traffic_callout');
  const recsList = bundle.ai_insights.find((x) => x.insight_type === 'recommendations_list');

  const stopsForMap = (clusters || []).map((s) => ({
    lat: s.lat, lng: s.lng, minutes: s.stop_count,
    near: `cluster · ${s.stop_count} stops`,
  }));
  // Add waypoints as map markers
  const wpForMap = (wp || []).map((w) => ({
    lat: w.lat, lng: w.lng, minutes: Math.round(w.time_spent_min),
    near: `${w.waypoint} · ${w.distance_km}km · ${w.avg_speed_kmph}km/h`,
  }));

  return (
    <div className="space-y-6">
      <button onClick={() => nav(`/route-intel/uploads/${t.upload_id}`)}
        className="flex items-center gap-2 text-sm" style={{ color: 'var(--accent)' }}>
        <ArrowLeft className="w-4 h-4" /> Trip list
      </button>

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <PageHeader
          title={`${t.from_waypoint ?? '—'} → ${t.to_waypoint ?? '—'}`}
          subtitle={`Trip #${t.seq} · ${t.vehicle_id} · ${new Date(t.start_ts).toLocaleString()}`}
        />
        <div className="flex items-center gap-2">
          <button onClick={regenAi} disabled={regen}
            className="px-3 py-1.5 rounded text-xs border flex items-center gap-1"
            style={{ borderColor: 'var(--border)', color: 'var(--fg-2)' }}>
            {regen ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
            Regenerate AI
          </button>
          <button onClick={reanalyze}
            className="px-3 py-1.5 rounded text-xs font-semibold flex items-center gap-1"
            style={{ background: 'var(--accent)', color: '#000' }}>
            <RefreshCw className="w-3 h-3" /> Re-run analysis
          </button>
        </div>
      </div>

      {/* AI Summary banner */}
      {tripSummary && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="card relative overflow-hidden"
          style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}>
          <div className="absolute -top-10 -right-10 w-32 h-32 rounded-full blur-2xl pointer-events-none"
            style={{ background: 'var(--accent)', opacity: 0.18 }} />
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg" style={{ background: 'var(--accent)' }}>
              <Sparkles className="w-4 h-4" color="#000" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-wider mb-1"
                style={{ color: 'var(--accent)' }}>
                AI Summary · {bundle.model}
              </div>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-1)' }}>
                {tripSummary.text}
              </p>
            </div>
          </div>
        </motion.div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KpiCard icon={RouteIcon} label="Distance" value={`${c?.total_distance_km ?? 0}`} trend="km" tone="default" index={0} />
        <KpiCard icon={Clock} label="Duration" value={`${(c?.total_hours ?? 0).toFixed(1)}`} trend="hours" tone="default" index={1} />
        <KpiCard icon={Gauge} label="Avg / Max" value={`${zones?.avg_speed_kmph ?? 0} / ${zones?.max_speed_kmph ?? 0}`} trend="km/h" tone="default" index={2} />
        <KpiCard icon={Activity} label="Efficiency" value={`${Math.round((eff?.route_efficiency ?? 0) * 100)}%`} trend={`${eff?.excess_percentage ?? 0}% excess`} tone={eff && eff.route_efficiency >= 0.85 ? 'success' : 'warning'} index={3} />
        <KpiCard icon={Coins} label="Total cost" value={`₹${Math.round(c?.total_cost_inr ?? 0).toLocaleString()}`} trend={`₹${(c?.cost_per_km ?? 0).toFixed(1)} /km`} tone="default" index={4} />
        <KpiCard icon={AlertTriangle} label="Idle waste" value={`₹${Math.round(c?.idle_fuel_waste_inr ?? 0).toLocaleString()}`} trend={`${(c?.stopped_hours ?? 0).toFixed(1)} h stopped`} tone="warning" index={5} />
      </div>

      {/* Map + cost donut */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="Route" subtitle={`${track.length.toLocaleString()} points · waypoints as red markers`} icon={MapIcon}>
          <LeafletMap points={track} stops={[...wpForMap, ...stopsForMap]} height={460} />
        </ChartCard>

        <ChartCard title="Cost breakdown" subtitle={`₹${(c?.cost_per_km ?? 0).toFixed(1)} per km`} icon={PieIcon}>
          <DonutChart data={costData} centerValue={`₹${Math.round(c?.total_cost_inr ?? 0).toLocaleString()}`} centerLabel="trip cost" unit=" ₹" height={210} />
          <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
            <Stat icon={Fuel} label="fuel" value={`${(c?.fuel_consumed_liters ?? 0).toFixed(1)} L`} />
            <Stat icon={UserSquare} label="driver" value={`₹${Math.round(c?.driver_cost_inr ?? 0).toLocaleString()}`} />
            <Stat icon={TrendingDown} label="idle fuel" value={`${(c?.idle_fuel_liters ?? 0).toFixed(1)} L`} />
          </div>
        </ChartCard>
      </div>

      {/* Speed over time + zone donut */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="Speed over time" subtitle="effective vs moving-only vs window max" icon={Gauge}>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={speedSeries} margin={{ top: 6, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip content={(p: any) => <ChartTooltip {...p} unit=" km/h" />} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
              <Line type="monotone" dataKey="Effective" stroke={SERIES[1]} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="Moving"    stroke={SERIES[0]} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="Max"       stroke={SERIES[5]} strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Speed zones" subtitle={`consistency: ${zones?.speed_consistency ?? '—'}`} icon={Activity}>
          <DonutChart data={zoneData} unit="%" centerValue={`${zones?.avg_speed_kmph ?? 0}`} centerLabel="km/h avg" height={210} />
        </ChartCard>
      </div>

      {/* Distance per window + route-quality AI */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="Distance per window" subtitle="km covered each window" icon={RouteIcon}>
          <AreaTrend data={distSeries} xKey="label" yKey="value" unit=" km" height={220} />
        </ChartCard>

        <ChartCard title="Route quality" subtitle={eff?.interpretation ?? '—'} icon={Wand2}>
          <div className="grid grid-cols-2 gap-2 mb-3 text-[11px]">
            <Stat label="straight line" value={`${eff?.straight_line_distance_km ?? 0} km`} icon={Navigation} />
            <Stat label="actual" value={`${eff?.actual_distance_km ?? 0} km`} icon={RouteIcon} />
            <Stat label="excess" value={`${eff?.excess_distance_km ?? 0} km`} icon={TrendingDown} />
            <Stat label="backtracks" value={String(bt.length)} icon={RotateCcw} />
          </div>
          {routeQual && (
            <p className="text-xs leading-relaxed" style={{ color: 'var(--fg-2)' }}>
              {routeQual.text}
            </p>
          )}
        </ChartCard>
      </div>

      {/* Traffic + waypoints */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard title="Traffic loss" subtitle={`${traffic?.time_lost_minutes ?? 0} min in congestion`} icon={Wind}>
          <div className="grid grid-cols-2 gap-2 mb-3 text-[11px]">
            <Stat label="distance in traffic" value={`${traffic?.distance_in_traffic_km ?? 0} km`} icon={RouteIcon} />
            <Stat label="avg speed" value={`${traffic?.avg_traffic_speed_kmph ?? 0} km/h`} icon={Gauge} />
            <Stat label="segments" value={String(traffic?.traffic_segments ?? 0)} icon={Layers} />
            <Stat label="potential save" value={`${traffic?.time_saved_if_no_traffic_minutes ?? 0} min`} icon={Zap} />
          </div>
          {trafficCallout && (
            <p className="text-xs leading-relaxed" style={{ color: 'var(--fg-2)' }}>
              {trafficCallout.text}
            </p>
          )}
        </ChartCard>

        <ChartCard className="lg:col-span-2" title="Waypoint sequence"
          subtitle={`${wp.length} consolidated visits`} icon={MapPin}>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart
              data={wp.map((w) => ({
                seq: w.seq, label: w.waypoint,
                cum: w.cumulative_distance_km,
                seg: w.distance_km,
                speed: w.avg_speed_kmph,
                time: w.time_spent_min,
              }))}
              margin={{ top: 6, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="seq" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip content={(p: any) => <ChartTooltip {...p} />} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
              <Line type="monotone" dataKey="cum"   stroke={SERIES[0]} name="cum km" strokeWidth={2} dot={{ r: 3, fill: SERIES[0] }} />
              <Line type="monotone" dataKey="seg"   stroke={SERIES[1]} name="seg km" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
              <Line type="monotone" dataKey="speed" stroke={SERIES[5]} name="avg kph" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Waypoint table */}
      <ChartCard title="Waypoint visits" subtitle="time at each named corridor point" icon={Timer}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--fg-3)' }} className="text-left">
                <th className="pb-2 pr-3">#</th>
                <th className="pb-2 pr-3">Waypoint</th>
                <th className="pb-2 pr-3">Arrive</th>
                <th className="pb-2 pr-3 text-right">Time (min)</th>
                <th className="pb-2 pr-3 text-right">Dist (km)</th>
                <th className="pb-2 pr-3 text-right">Cum (km)</th>
                <th className="pb-2 pr-3 text-right">Avg speed</th>
              </tr>
            </thead>
            <tbody>
              {wp.map((w) => (
                <tr key={w.seq} className="border-t" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-1.5 pr-3" style={{ color: 'var(--fg-3)' }}>{w.seq}</td>
                  <td className="py-1.5 pr-3 font-semibold" style={{ color: 'var(--fg-1)' }}>{w.waypoint}</td>
                  <td className="py-1.5 pr-3" style={{ color: 'var(--fg-2)' }}>{new Date(w.arrive_ts).toLocaleString()}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-1)' }}>{w.time_spent_min}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-1)' }}>{w.distance_km}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-2)' }}>{w.cumulative_distance_km}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-2)' }}>{w.avg_speed_kmph}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>

      {/* AI recommendations grid + cost advice */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard title="Cost advice" subtitle="natural-language reading" icon={Sparkles}>
          {costAdvice && <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-2)' }}>{costAdvice.text}</p>}
        </ChartCard>

        <ChartCard className="lg:col-span-2" title="Recommendations"
          subtitle={`${opps.length} opportunit${opps.length === 1 ? 'y' : 'ies'} identified`} icon={Wand2}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {opps.length === 0 && (
              <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
                Operation is running clean — no high-impact recommendations for this trip.
              </div>
            )}
            {opps.map((o, i) => (
              <motion.div key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                className="p-3 rounded-lg"
                style={{ background: 'var(--bg-2)',
                  borderLeft: `3px solid ${o.priority === 'HIGH' ? 'var(--danger)' : 'var(--warning)'}` }}>
                <div className="flex items-center justify-between mb-1">
                  <div className="text-[10px] uppercase tracking-wider font-semibold"
                    style={{ color: o.priority === 'HIGH' ? 'var(--danger)' : 'var(--warning)' }}>
                    {o.priority} · {o.category}
                  </div>
                  <div className="text-[10px] tabular font-bold" style={{ color: 'var(--success)' }}>
                    ₹{Math.round(o.monthly_savings_inr).toLocaleString()}/mo
                  </div>
                </div>
                <div className="text-xs" style={{ color: 'var(--fg-1)' }}>{o.recommendation}</div>
                {o.current_waste_inr > 0 && (
                  <div className="text-[10px] mt-1" style={{ color: 'var(--fg-3)' }}>
                    current waste: ₹{Math.round(o.current_waste_inr).toLocaleString()}
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </ChartCard>
      </div>

      {/* Backtracking events */}
      {bt.length > 0 && (
        <ChartCard title={`Backtracking events (${bt.length})`}
          subtitle="bearing reversed by more than 135°" icon={RotateCcw}>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
            {bt.slice(0, 12).map((b, i) => (
              <div key={i} className="p-2 rounded text-[11px]"
                style={{ background: 'var(--bg-2)' }}>
                <div className="font-semibold" style={{ color: 'var(--fg-1)' }}>
                  {b.bearing_change_deg.toFixed(0)}° turn
                </div>
                <div style={{ color: 'var(--fg-3)' }}>{new Date(b.ts).toLocaleString()}</div>
                <div style={{ color: 'var(--fg-3)' }}>{b.lat.toFixed(4)}, {b.lng.toFixed(4)}</div>
              </div>
            ))}
            {bt.length > 12 && (
              <div className="p-2 text-[11px] flex items-center justify-center"
                style={{ color: 'var(--fg-3)' }}>+{bt.length - 12} more</div>
            )}
          </div>
        </ChartCard>
      )}

      {/* Time windows table */}
      <ChartCard title="Time windows" subtitle="30-min aggregates" icon={Layers}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--fg-3)' }} className="text-left">
                <th className="pb-2 pr-3">Window</th>
                <th className="pb-2 pr-3 text-right">Dist (km)</th>
                <th className="pb-2 pr-3 text-right">Avg (kph)</th>
                <th className="pb-2 pr-3 text-right">Moving avg</th>
                <th className="pb-2 pr-3 text-right">Max</th>
                <th className="pb-2 pr-3 text-right">Moving (min)</th>
                <th className="pb-2 pr-3 text-right">Idle (min)</th>
                <th className="pb-2 pr-3">Dominant</th>
              </tr>
            </thead>
            <tbody>
              {bundle.time_windows.map((w, i) => (
                <tr key={i} className="border-t" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-1.5 pr-3" style={{ color: 'var(--fg-1)' }}>{w.window_label}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-1)' }}>{w.total_distance_km.toFixed(2)}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-2)' }}>{w.avg_speed_kmph.toFixed(1)}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-2)' }}>{w.avg_moving_speed_kmph.toFixed(1)}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-2)' }}>{w.max_speed_kmph.toFixed(0)}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-2)' }}>{(w.moving_time_sec / 60).toFixed(0)}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-2)' }}>{(w.stopped_time_sec / 60).toFixed(0)}</td>
                  <td className="py-1.5 pr-3">
                    <span className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        background: w.dominant_status === 'Moving' ? 'rgba(34,197,94,0.14)' : 'rgba(245,158,11,0.14)',
                        color: w.dominant_status === 'Moving' ? 'var(--success)' : 'var(--warning)',
                      }}>{w.dominant_status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>

      {/* Bottom: full recommendations text */}
      {recsList && (
        <ChartCard title="Recommendations narrative" icon={Sparkles}>
          <pre className="text-xs whitespace-pre-wrap leading-relaxed"
            style={{ color: 'var(--fg-2)', fontFamily: 'inherit' }}>{recsList.text}</pre>
        </ChartCard>
      )}

      {error && <div className="card text-xs" style={{ color: 'var(--danger)' }}>{error}</div>}
    </div>
  );
}

function Stat({ icon: Icon, label, value }: { icon?: any; label: string; value: string }) {
  return (
    <div className="p-1.5 rounded" style={{ background: 'var(--bg-2)' }}>
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-wider"
        style={{ color: 'var(--fg-3)' }}>
        {Icon && <Icon className="w-2.5 h-2.5" />} {label}
      </div>
      <div className="text-xs font-bold" style={{ color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}
