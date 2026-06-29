import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft, GitCompare, Sparkles, Trophy, Loader2,
  Coins, Clock, Activity, RouteIcon as _Ri, Gauge, Layers, TrendingDown,
} from 'lucide-react';
import {
  BarChart as RBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ScatterChart, Scatter, ZAxis,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Cell,
} from 'recharts';
import PageHeader from '../components/ui/PageHeader';
import ChartCard from '../components/charts/ChartCard';
import { ChartTooltip, AXIS, GRID, SERIES } from '../components/charts/theme';
import { riGetComparison, type RIComparison } from '../lib/api';

export default function RouteIntelligenceCompare() {
  const { cmpId = '' } = useParams();
  const nav = useNavigate();
  const [cmp, setCmp] = useState<RIComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    riGetComparison(Number(cmpId))
      .then(setCmp)
      .catch((e) => setError(e?.message ?? 'failed'))
      .finally(() => setLoading(false));
  }, [cmpId]);

  const costData = useMemo(() => {
    if (!cmp) return [];
    return cmp.table.map((r) => ({
      label: shortLabel(r.Route),
      Fuel: Math.round(r['Fuel Cost (₹)'] ?? 0),
      Driver: Math.round((r['Total Cost (₹)'] ?? 0) - (r['Fuel Cost (₹)'] ?? 0)),
      Idle: Math.round(r['Idle Waste (₹)'] ?? 0),
    }));
  }, [cmp]);

  const bubbleData = useMemo(() => {
    if (!cmp) return [];
    return cmp.table.map((r) => ({
      x: r['Duration (hrs)'],
      y: r['Distance (km)'],
      z: r['Total Cost (₹)'],
      cpk: r['Cost/km (₹)'],
      name: r.Route,
    }));
  }, [cmp]);

  const radarData = useMemo(() => {
    if (!cmp) return [];
    // Per route: 5 axes (0-100 normalised — higher = better)
    return cmp.table.map((r) => ({
      route: shortLabel(r.Route),
      Efficiency: Math.min(100, r['Efficiency (%)'] ?? 0),
      'Avg speed': Math.min(100, ((r['Avg Speed (km/h)'] ?? 0) / 80) * 100),
      'Moving speed': Math.min(100, ((r['Moving Speed (km/h)'] ?? 0) / 80) * 100),
      'Cost eff': Math.max(0, 100 - (((r['Cost/km (₹)'] ?? 0)) / 50) * 100),
      'Idle eff': Math.max(0, 100 - (((r['Idle Time (hrs)'] ?? 0)) / 10) * 100),
    }));
  }, [cmp]);

  const stackedTime = useMemo(() => {
    if (!cmp) return [];
    return cmp.table.map((r) => ({
      label: shortLabel(r.Route),
      Moving: Math.round((r['Moving Time (hrs)'] ?? 0) * 10) / 10,
      Idle: Math.round((r['Idle Time (hrs)'] ?? 0) * 10) / 10,
    }));
  }, [cmp]);

  if (loading) return (
    <div className="space-y-4">
      <PageHeader title="Comparison" subtitle="Loading…" />
      <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} />
        Loading…
      </div>
    </div>
  );

  if (!cmp) return (
    <div className="card text-sm" style={{ color: 'var(--danger)' }}>{error ?? 'Not found'}</div>
  );

  const verdict = cmp.ai_insights.find((x) => x.insight_type === 'comparison_verdict');
  const best = cmp.table.find((r: any) => r.trip_id === cmp.best_trip_id);

  return (
    <div className="space-y-6">
      <button onClick={() => nav(-1)} className="flex items-center gap-2 text-sm"
        style={{ color: 'var(--accent)' }}>
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <PageHeader
        title="Route Comparison"
        subtitle={`${cmp.table.length} routes · ranked by weighted score (cost 40 / time 30 / eff 30)`}
      />

      {/* Verdict + best card */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="card lg:col-span-2 relative overflow-hidden"
          style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}>
          <div className="absolute -top-10 -right-10 w-32 h-32 rounded-full blur-2xl pointer-events-none"
            style={{ background: 'var(--accent)', opacity: 0.18 }} />
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg" style={{ background: 'var(--accent)' }}>
              <Sparkles className="w-4 h-4" color="#000" />
            </div>
            <div className="flex-1">
              <div className="text-[10px] uppercase tracking-wider mb-1"
                style={{ color: 'var(--accent)' }}>AI Verdict</div>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-1)' }}>
                {verdict?.text ?? '—'}
              </p>
            </div>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }} className="card">
          <div className="flex items-center gap-2 mb-2">
            <Trophy className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            <div className="text-xs uppercase tracking-wider" style={{ color: 'var(--accent)' }}>
              Best overall
            </div>
          </div>
          <div className="text-sm font-bold mb-2" style={{ color: 'var(--fg-1)' }}>
            {best?.Route ?? '—'}
          </div>
          {best && (
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <Stat label="cost" value={`₹${Math.round(best['Total Cost (₹)']).toLocaleString()}`} />
              <Stat label="duration" value={`${best['Duration (hrs)']} h`} />
              <Stat label="distance" value={`${best['Distance (km)']} km`} />
              <Stat label="efficiency" value={`${best['Efficiency (%)']}%`} />
            </div>
          )}
          {cmp.best_trip_id && (
            <button
              onClick={() => nav(`/route-intel/trips/${cmp.best_trip_id}`)}
              className="mt-3 w-full px-3 py-1.5 rounded text-xs font-semibold"
              style={{ background: 'var(--accent)', color: '#000' }}>
              Open best trip →
            </button>
          )}
        </motion.div>
      </div>

      {/* Cost stacked + radar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="Cost composition"
          subtitle="fuel + driver + idle waste per route" icon={Coins}>
          <ResponsiveContainer width="100%" height={280}>
            <RBarChart data={costData} margin={{ top: 6, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip content={(p: any) => <ChartTooltip {...p} unit=" ₹" />} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
              <Bar dataKey="Fuel"   stackId="a" fill={SERIES[1]} radius={[0, 0, 0, 0]} />
              <Bar dataKey="Driver" stackId="a" fill={SERIES[4]} radius={[0, 0, 0, 0]} />
              <Bar dataKey="Idle"   stackId="a" fill={SERIES[5]} radius={[4, 4, 0, 0]} />
            </RBarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Multi-axis radar"
          subtitle="higher is better on all 5 axes" icon={Activity}>
          <ResponsiveContainer width="100%" height={280}>
            <RadarChart data={[
              { metric: 'Efficiency',   ...flat(radarData, 'Efficiency') },
              { metric: 'Avg speed',    ...flat(radarData, 'Avg speed') },
              { metric: 'Moving speed', ...flat(radarData, 'Moving speed') },
              { metric: 'Cost eff',     ...flat(radarData, 'Cost eff') },
              { metric: 'Idle eff',     ...flat(radarData, 'Idle eff') },
            ]}>
              <PolarGrid stroke="var(--border)" />
              <PolarAngleAxis dataKey="metric" tick={{ fill: 'var(--fg-3)', fontSize: 11 }} />
              <PolarRadiusAxis tick={{ fill: 'var(--fg-3)', fontSize: 9 }} angle={30} domain={[0, 100]} />
              {radarData.map((r, i) => (
                <Radar key={r.route} name={r.route} dataKey={r.route}
                  stroke={SERIES[i % SERIES.length]} fill={SERIES[i % SERIES.length]} fillOpacity={0.18} strokeWidth={1.5} />
              ))}
              <Legend wrapperStyle={{ fontSize: 10, color: 'var(--fg-3)' }} />
              <Tooltip content={(p: any) => <ChartTooltip {...p} unit="" />} />
            </RadarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Bubble + stacked time */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="Time vs Distance"
          subtitle="bubble size = total cost · darker = higher cost/km" icon={Clock}>
          <ResponsiveContainer width="100%" height={280}>
            <ScatterChart margin={{ top: 6, right: 8, bottom: 12, left: -16 }}>
              <CartesianGrid {...GRID} />
              <XAxis type="number" dataKey="x" name="Duration"
                {...AXIS} unit=" h" />
              <YAxis type="number" dataKey="y" name="Distance"
                {...AXIS} unit=" km" />
              <ZAxis type="number" dataKey="z" range={[80, 1500]} name="Cost" />
              <Tooltip content={(p: any) => {
                const d = p?.payload?.[0]?.payload;
                if (!d) return null;
                return (
                  <div style={{
                    background: 'var(--bg-2)', border: '1px solid var(--border)',
                    borderRadius: 10, padding: '8px 10px', fontSize: 12,
                  }}>
                    <div style={{ color: 'var(--fg-1)', fontWeight: 600 }}>{d.name}</div>
                    <div style={{ color: 'var(--fg-3)' }}>{d.x} h · {d.y} km</div>
                    <div style={{ color: 'var(--fg-1)' }}>₹{Math.round(d.z).toLocaleString()} · ₹{d.cpk}/km</div>
                  </div>
                );
              }} />
              <Scatter data={bubbleData} fill={SERIES[0]}>
                {bubbleData.map((b, i) => (
                  <Cell key={i} fill={SERIES[i % SERIES.length]} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Moving vs Idle" subtitle="hours per route" icon={TrendingDown}>
          <ResponsiveContainer width="100%" height={280}>
            <RBarChart data={stackedTime} margin={{ top: 6, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip content={(p: any) => <ChartTooltip {...p} unit=" h" />} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
              <Bar dataKey="Moving" stackId="t" fill={SERIES[4]} />
              <Bar dataKey="Idle"   stackId="t" fill={SERIES[5]} radius={[4, 4, 0, 0]} />
            </RBarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Comparison table */}
      <ChartCard title="Ranked metrics" subtitle="lower rank = better · click route to drill in" icon={Layers}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--fg-3)' }} className="text-left">
                <th className="pb-2 pr-3">Route</th>
                <th className="pb-2 pr-3 text-right">Dist (km)</th>
                <th className="pb-2 pr-3 text-right">Dur (h)</th>
                <th className="pb-2 pr-3 text-right">Avg kph</th>
                <th className="pb-2 pr-3 text-right">Idle (h)</th>
                <th className="pb-2 pr-3 text-right">Cost ₹</th>
                <th className="pb-2 pr-3 text-right">₹/km</th>
                <th className="pb-2 pr-3 text-right">Eff %</th>
                <th className="pb-2 pr-3 text-right">Cost rk</th>
                <th className="pb-2 pr-3 text-right">Time rk</th>
                <th className="pb-2 pr-3 text-right">Eff rk</th>
                <th className="pb-2 pr-3 text-right">Score</th>
              </tr>
            </thead>
            <tbody>
              {cmp.table.map((r: any) => (
                <tr key={r.trip_id} className="border-t cursor-pointer hover:bg-white/5"
                  style={{ borderColor: 'var(--border)' }}
                  onClick={() => nav(`/route-intel/trips/${r.trip_id}`)}>
                  <td className="py-1.5 pr-3 font-semibold" style={{ color: r.trip_id === cmp.best_trip_id ? 'var(--accent)' : 'var(--fg-1)' }}>
                    {r.trip_id === cmp.best_trip_id && <Trophy className="inline w-3 h-3 mr-1" />}
                    {r.Route}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular">{r['Distance (km)']}</td>
                  <td className="py-1.5 pr-3 text-right tabular">{r['Duration (hrs)']}</td>
                  <td className="py-1.5 pr-3 text-right tabular">{r['Avg Speed (km/h)']}</td>
                  <td className="py-1.5 pr-3 text-right tabular">{r['Idle Time (hrs)']}</td>
                  <td className="py-1.5 pr-3 text-right tabular">{Math.round(r['Total Cost (₹)']).toLocaleString()}</td>
                  <td className="py-1.5 pr-3 text-right tabular">{r['Cost/km (₹)']}</td>
                  <td className="py-1.5 pr-3 text-right tabular">{r['Efficiency (%)']}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-3)' }}>{r['Cost Rank']}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-3)' }}>{r['Time Rank']}</td>
                  <td className="py-1.5 pr-3 text-right tabular" style={{ color: 'var(--fg-3)' }}>{r['Efficiency Rank']}</td>
                  <td className="py-1.5 pr-3 text-right tabular font-bold"
                    style={{ color: 'var(--accent)' }}>{r['Overall Score']}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>

      {error && <div className="card text-xs" style={{ color: 'var(--danger)' }}>{error}</div>}
    </div>
  );
}

function shortLabel(label: string) {
  return label.length > 22 ? label.slice(0, 21) + '…' : label;
}

// flatten radar data into a wide row keyed by route name
function flat(rows: any[], axis: string) {
  const o: any = {};
  for (const r of rows) o[r.route] = r[axis];
  return o;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-1.5 rounded" style={{ background: 'var(--bg-2)' }}>
      <div className="text-[9px] uppercase tracking-wider"
        style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="text-xs font-bold" style={{ color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}
