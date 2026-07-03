import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft, Sparkles, Trophy, Loader2, Coins, Clock,
  Activity, Layers, TrendingDown,
} from 'lucide-react';
import {
  BarChart as RBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ScatterChart, Scatter, ZAxis, Cell,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
} from 'recharts';
import PageHeader from '../components/ui/PageHeader';
import ChartCard from '../components/charts/ChartCard';
import { ChartTooltip, AXIS, GRID } from '../components/charts/theme';
import { riGetComparison } from '../lib/routeIntel';

const SERIES = ['#00C2FF', '#00E676', '#FFC107', '#7C4DFF', '#FF9800', '#FF4D6D'];

export default function RouteIntelligenceCompare() {
  const { cmpId = '' } = useParams();
  const nav = useNavigate();
  const [cmp, setCmp] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    riGetComparison(Number(cmpId))
      .then(setCmp)
      .catch(e => setError(e?.message ?? 'failed'))
      .finally(() => setLoading(false));
  }, [cmpId]);

  const costData = useMemo(() => {
    if (!cmp) return [];
    return cmp.table.map(r => ({
      label: shortLabel(r.Route),
      Fuel:   Math.round(r['Fuel Cost (₹)'] ?? 0),
      Driver: Math.round((r['Total Cost (₹)'] ?? 0) - (r['Fuel Cost (₹)'] ?? 0)),
      Idle:   Math.round(r['Idle Waste (₹)'] ?? 0),
    }));
  }, [cmp]);

  const bubbleData = useMemo(() => {
    if (!cmp) return [];
    return cmp.table.map(r => ({
      x: r['Duration (hrs)'], y: r['Distance (km)'],
      z: r['Total Cost (₹)'], cpk: r['Cost/km (₹)'], name: r.Route,
    }));
  }, [cmp]);

  const radarData = useMemo(() => {
    if (!cmp) return [];
    return cmp.table.map(r => ({
      route: shortLabel(r.Route),
      Efficiency:    Math.min(100, r['Efficiency (%)'] ?? 0),
      'Avg speed':   Math.min(100, ((r['Avg Speed (km/h)'] ?? 0) / 80) * 100),
      'Moving speed':Math.min(100, ((r['Moving Speed (km/h)'] ?? 0) / 80) * 100),
      'Cost eff':    Math.max(0, 100 - (((r['Cost/km (₹)'] ?? 0)) / 50) * 100),
      'Idle eff':    Math.max(0, 100 - (((r['Idle Time (hrs)'] ?? 0)) / 10) * 100),
    }));
  }, [cmp]);

  const stackedTime = useMemo(() => {
    if (!cmp) return [];
    return cmp.table.map(r => ({
      label: shortLabel(r.Route),
      Moving: Math.round((r['Moving Time (hrs)'] ?? 0) * 10) / 10,
      Idle:   Math.round((r['Idle Time (hrs)'] ?? 0) * 10) / 10,
    }));
  }, [cmp]);

  if (loading) return (
    <div className="space-y-4">
      <PageHeader title="Comparison" subtitle="Loading…" />
      <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
      </div>
    </div>
  );
  if (!cmp) return (
    <div className="card text-sm" style={{ color: 'var(--danger)' }}>{error ?? 'Not found'}</div>
  );

  const verdict = cmp.ai_insights.find(x => x.insight_type === 'comparison_verdict');
  const best = cmp.table.find(r => r.trip_id === cmp.best_trip_id);

  return (
    <div className="space-y-6">
      <button onClick={() => nav(-1)} className="btn-soft text-xs">
        <ArrowLeft className="w-3.5 h-3.5" /> Back
      </button>

      <PageHeader title="Route Comparison"
        subtitle={`${cmp.table.length} routes · weighted score (cost 40 / time 30 / eff 30)`} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="card lg:col-span-2 ai-glow" style={{ borderColor: 'var(--accent)' }}>
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg shrink-0" style={{ background: 'var(--accent)' }}>
              <Sparkles className="w-4 h-4" color="#000" />
            </div>
            <div className="flex-1">
              <div className="text-[10px] uppercase tracking-[0.15em] mb-1"
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
            <div className="text-[10px] uppercase tracking-[0.15em]"
              style={{ color: 'var(--accent)' }}>Best overall</div>
          </div>
          <div className="text-sm font-bold mb-2" style={{ color: 'var(--fg-1)' }}>
            {best?.Route ?? '—'}
          </div>
          {best && (
            <div className="grid grid-cols-2 gap-2">
              <Stat label="cost"     value={`₹${Math.round(best['Total Cost (₹)']).toLocaleString()}`} />
              <Stat label="duration" value={`${best['Duration (hrs)']} h`} />
              <Stat label="distance" value={`${best['Distance (km)']} km`} />
              <Stat label="efficiency" value={`${best['Efficiency (%)']}%`} />
            </div>
          )}
          {cmp.best_trip_id && (
            <button onClick={() => nav(`/route-intel/trips/${cmp.best_trip_id}`)}
              className="btn-primary mt-3 w-full text-xs">Open best trip →</button>
          )}
        </motion.div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="Cost composition"
          subtitle="fuel + driver + idle waste" icon={Coins}>
          <ResponsiveContainer width="100%" height={280}>
            <RBarChart data={costData} margin={{ top: 6, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip content={(p) => <ChartTooltip {...p} unit=" ₹" />} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
              <Bar dataKey="Fuel"   stackId="a" fill="#00C2FF" />
              <Bar dataKey="Driver" stackId="a" fill="#00E676" />
              <Bar dataKey="Idle"   stackId="a" fill="#FF4D6D" radius={[4, 4, 0, 0]} />
            </RBarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Radar — higher is better" icon={Activity}>
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
                  stroke={SERIES[i % SERIES.length]}
                  fill={SERIES[i % SERIES.length]} fillOpacity={0.18} strokeWidth={1.5} />
              ))}
              <Legend wrapperStyle={{ fontSize: 10, color: 'var(--fg-3)' }} />
              <Tooltip content={(p) => <ChartTooltip {...p} />} />
            </RadarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="Time vs Distance"
          subtitle="bubble size = total cost" icon={Clock}>
          <ResponsiveContainer width="100%" height={280}>
            <ScatterChart margin={{ top: 6, right: 8, bottom: 12, left: -16 }}>
              <CartesianGrid {...GRID} />
              <XAxis type="number" dataKey="x" name="Duration" unit=" h" {...AXIS} />
              <YAxis type="number" dataKey="y" name="Distance" unit=" km" {...AXIS} />
              <ZAxis type="number" dataKey="z" range={[80, 1500]} name="Cost" />
              <Tooltip content={(p) => {
                const d = p?.payload?.[0]?.payload;
                if (!d) return null;
                return (
                  <div style={{
                    background: 'var(--bg-3)', border: '1px solid var(--border)',
                    borderRadius: 10, padding: '8px 10px', fontSize: 12,
                  }}>
                    <div style={{ color: 'var(--fg-1)', fontWeight: 600 }}>{d.name}</div>
                    <div style={{ color: 'var(--fg-3)' }}>{d.x} h · {d.y} km</div>
                    <div style={{ color: 'var(--fg-1)' }}>₹{Math.round(d.z).toLocaleString()} · ₹{d.cpk}/km</div>
                  </div>
                );
              }} />
              <Scatter data={bubbleData}>
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
              <Tooltip content={(p) => <ChartTooltip {...p} unit=" h" />} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--fg-3)' }} />
              <Bar dataKey="Moving" stackId="t" fill="#00E676" />
              <Bar dataKey="Idle"   stackId="t" fill="#FF4D6D" radius={[4, 4, 0, 0]} />
            </RBarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard title="Ranked metrics" subtitle="click row to drill in" icon={Layers}>
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
                <th className="pb-2 pr-3 text-right">Score</th>
              </tr>
            </thead>
            <tbody>
              {cmp.table.map(r => (
                <tr key={r.trip_id} className="border-t row-hover cursor-pointer"
                  style={{ borderColor: 'var(--border)' }}
                  onClick={() => nav(`/route-intel/trips/${r.trip_id}`)}>
                  <td className="py-1.5 pr-3 font-semibold"
                    style={{ color: r.trip_id === cmp.best_trip_id ? 'var(--accent)' : 'var(--fg-1)' }}>
                    {r.trip_id === cmp.best_trip_id && <Trophy className="inline w-3 h-3 mr-1" />}
                    {r.Route}
                  </td>
                  <td className="py-1.5 pr-3 text-right mono">{r['Distance (km)']}</td>
                  <td className="py-1.5 pr-3 text-right mono">{r['Duration (hrs)']}</td>
                  <td className="py-1.5 pr-3 text-right mono">{r['Avg Speed (km/h)']}</td>
                  <td className="py-1.5 pr-3 text-right mono">{r['Idle Time (hrs)']}</td>
                  <td className="py-1.5 pr-3 text-right mono">{Math.round(r['Total Cost (₹)']).toLocaleString()}</td>
                  <td className="py-1.5 pr-3 text-right mono">{r['Cost/km (₹)']}</td>
                  <td className="py-1.5 pr-3 text-right mono">{r['Efficiency (%)']}</td>
                  <td className="py-1.5 pr-3 text-right mono font-bold"
                    style={{ color: 'var(--accent)' }}>{r['Overall Score']}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </div>
  );
}

function shortLabel(label) { return label.length > 24 ? label.slice(0, 23) + '…' : label; }
function flat(rows, axis) {
  const o = {};
  for (const r of rows) o[r.route] = r[axis];
  return o;
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
