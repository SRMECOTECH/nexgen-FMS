import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Search, Truck, Gauge, Moon, AlertTriangle, Activity, Clock, RefreshCw, Box,
  TrendingUp, Sparkles, ChevronRight, Route as RouteIcon,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from 'recharts';
import PageHeader from '../components/ui/PageHeader';
import { fetchGpsFleet, fetchGpsBehaviour, type FleetRow, type GpsBehaviour } from '../lib/api';

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function scoreColor(s: number) { return s >= 80 ? '#22c55e' : s >= 60 ? '#facc15' : '#ef4444'; }

export default function BehavioralPatterns() {
  const nav = useNavigate();
  const [fleet, setFleet] = useState<FleetRow[]>([]);
  const [selected, setSelected] = useState('');
  const [search, setSearch] = useState('');
  const [data, setData] = useState<GpsBehaviour | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [tilt, setTilt] = useState(true);

  useEffect(() => {
    fetchGpsFleet().then(f => {
      setFleet(f.fleet);
      if (f.fleet[0]) setSelected(f.fleet[0].vehicle_reg); else setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setBusy(true);
    fetchGpsBehaviour(selected).then(d => setData(d.error ? null : d)).finally(() => { setBusy(false); setLoading(false); });
  }, [selected]);

  const filteredFleet = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? fleet.filter(f => f.vehicle_reg.toLowerCase().includes(q) || (f.entity_name ?? '').toLowerCase().includes(q)) : fleet;
  }, [fleet, search]);

  const m = data?.metrics;
  const radar = useMemo(() => {
    if (!m) return [];
    return [
      { axis: 'Compliance', v: Math.max(0, 100 - m.overspeed_pct * 8) },
      { axis: 'Smoothness', v: Math.max(0, 100 - (m.harsh_accel + m.harsh_brake) * 0.6) },
      { axis: 'Daytime', v: Math.max(0, 100 - m.night_pct) },
      { axis: 'Consistency', v: Math.min(100, m.active_days * 25) },
      { axis: 'Overall', v: data!.score },
    ];
  }, [m, data]);

  if (loading) return (
    <div className="space-y-4">
      <PageHeader title="Behavioural Patterns" subtitle="Loading driving history…" />
      <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-2)' }}>
        <RefreshCw className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} /> Loading…
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Behavioural Patterns"
        subtitle="How a truck is actually driven — speed by time of day, a driving heatmap, harsh events and a style score, from its GPS history." />

      {/* Truck search/picker */}
      <div className="card">
        <div className="flex items-center gap-3 mb-3">
          <div className="text-xs uppercase tracking-widest font-semibold" style={{ color: 'var(--fg-3)' }}>
            Pick a truck ({fleet.length})
          </div>
          <div className="ml-auto relative">
            <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--fg-3)' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search truck / operator…"
              className="pl-8 pr-3 py-1.5 rounded-md text-xs w-56 outline-none"
              style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', color: 'var(--fg-1)' }} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {filteredFleet.map(f => {
            const active = selected === f.vehicle_reg;
            return (
              <button key={f.vehicle_reg} onClick={() => setSelected(f.vehicle_reg)}
                className="px-3 py-1.5 rounded-lg font-mono text-xs lift"
                style={{
                  background: active ? 'var(--accent-soft)' : 'var(--bg-2)',
                  color: active ? 'var(--accent)' : 'var(--fg-2)',
                  border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                }}>
                <Truck className="inline w-3 h-3 mr-1" />{f.vehicle_reg} · {f.pings.toLocaleString()} pings
              </button>
            );
          })}
          {filteredFleet.length === 0 && <span className="text-xs" style={{ color: 'var(--fg-3)' }}>No trucks match.</span>}
        </div>
      </div>

      {busy && <div className="text-xs" style={{ color: 'var(--fg-3)' }}>Computing driving profile…</div>}

      {data && m && (
        <>
          {/* Score + KPIs + radar */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            <div className="card flex flex-col items-center justify-center" style={{ background: 'linear-gradient(160deg, var(--accent-soft), transparent 70%)' }}>
              <div className="text-[10px] uppercase tracking-widest mb-2" style={{ color: 'var(--fg-3)' }}>Driving score</div>
              <ScoreRing score={data.score} />
              <div className="text-xs mt-2" style={{ color: 'var(--fg-3)' }}>peak driving @ {String(m.peak_hour).padStart(2, '0')}:00</div>
            </div>

            <div className="lg:col-span-2 grid grid-cols-2 md:grid-cols-3 gap-3">
              <Kpi icon={Gauge} label="Avg moving" value={`${m.avg_moving_speed}`} sub={`max ${m.max_speed} km/h`} />
              <Kpi icon={Moon} label="Night driving" value={`${m.night_pct}%`} sub="22:00–05:00" />
              <Kpi icon={TrendingUp} label="Over-speed" value={`${m.overspeed_pct}%`} sub="pings > 60" />
              <Kpi icon={AlertTriangle} label="Harsh accel" value={String(m.harsh_accel)} />
              <Kpi icon={AlertTriangle} label="Harsh brake" value={String(m.harsh_brake)} />
              <Kpi icon={Activity} label="Active days" value={String(m.active_days)} />
            </div>

            <div className="card">
              <h3 className="font-semibold text-sm mb-1 flex items-center gap-2"><Sparkles className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Profile</h3>
              <ResponsiveContainer width="100%" height={180}>
                <RadarChart data={radar} outerRadius={64}>
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis dataKey="axis" tick={{ fontSize: 9, fill: 'var(--fg-3)' }} />
                  <Radar dataKey="v" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.35} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Speed by hour of day */}
          <div className="card">
            <h3 className="font-semibold mb-1 flex items-center gap-2"><Clock className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Average speed by hour of day</h3>
            <p className="text-xs mb-3" style={{ color: 'var(--fg-3)' }}>When the truck moves fastest. Bars are avg moving speed; hover for activity.</p>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.by_hour}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="hour" tick={{ fontSize: 9, fill: 'var(--fg-3)' }} tickFormatter={(h) => `${String(h).padStart(2, '0')}`} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--fg-3)' }} />
                <Tooltip contentStyle={{ background: 'var(--bg-1)', border: '1px solid var(--border)', fontSize: 11 }}
                  formatter={(v: any, _n, p: any) => [`${v} km/h · ${p.payload.pings} pings · ${p.payload.moving_pct}% moving`, `${String(p.payload.hour).padStart(2, '0')}:00`]} />
                <Bar dataKey="avg_speed" radius={[3, 3, 0, 0]}>
                  {data.by_hour.map((d, i) => <Cell key={i} fill={d.hour === m.peak_hour ? 'var(--accent-hover)' : 'var(--accent)'} fillOpacity={d.avg_speed ? 1 : 0.2} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* 3D heatmap */}
          <div className="card">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-semibold flex items-center gap-2"><Box className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Driving heatmap — day × hour</h3>
              <button onClick={() => setTilt(t => !t)} className="ml-auto px-2 py-1 rounded text-[11px] flex items-center gap-1"
                style={{ background: tilt ? 'var(--accent-soft)' : 'var(--bg-2)', color: tilt ? 'var(--accent)' : 'var(--fg-2)', border: `1px solid ${tilt ? 'var(--accent)' : 'var(--border)'}` }}>
                <Box className="w-3 h-3" /> {tilt ? '3D on' : '3D off'}
              </button>
            </div>
            <p className="text-xs mb-4" style={{ color: 'var(--fg-3)' }}>Cell height &amp; glow = activity; brighter/taller = more driving in that hour. Hover for avg speed.</p>
            <Heatmap activity={data.heatmap.activity} speed={data.heatmap.speed} max={data.heatmap.max_activity} tilt={tilt} />
          </div>

          {/* Recent journeys */}
          <div className="card">
            <h3 className="font-semibold mb-1 flex items-center gap-2"><RouteIcon className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Last {data.recent_journeys.length} journeys</h3>
            <p className="text-xs mb-3" style={{ color: 'var(--fg-3)' }}>Click to open the route &amp; halts.</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {data.recent_journeys.map((j: any) => (
                <button key={j.trip} onClick={() => nav(`/halts/${encodeURIComponent(selected)}/${j.trip}`)}
                  className="text-left p-2.5 rounded-lg lift flex items-center gap-3" style={{ background: 'var(--bg-2)' }}>
                  <span className="flex items-center justify-center w-7 h-7 rounded-md text-xs font-bold shrink-0" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>{j.trip}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium truncate" style={{ color: 'var(--fg-1)' }}>{j.from_node ?? '—'} → {j.to_node ?? '—'}</div>
                    <div className="text-[10px]" style={{ color: 'var(--fg-3)' }}>{j.distance_km} km · {Math.round(j.duration_min)} min · avg {j.avg_speed} km/h</div>
                  </div>
                  <ChevronRight className="w-4 h-4 shrink-0" style={{ color: 'var(--fg-3)' }} />
                </button>
              ))}
              {data.recent_journeys.length === 0 && <div className="text-xs" style={{ color: 'var(--fg-3)' }}>No journeys reconstructed.</div>}
            </div>
          </div>
        </>
      )}

      {!data && !busy && <div className="card text-sm" style={{ color: 'var(--fg-3)' }}>No GPS history for this truck.</div>}
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const c = scoreColor(score);
  const r = 46, circ = 2 * Math.PI * r, off = circ * (1 - score / 100);
  return (
    <div className="relative" style={{ width: 120, height: 120 }}>
      <svg width="120" height="120" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--bg-2)" strokeWidth="10" />
        <circle cx="60" cy="60" r={r} fill="none" stroke={c} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={off} style={{ transition: 'stroke-dashoffset .6s ease' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold" style={{ color: c }}>{score}</span>
        <span className="text-[10px]" style={{ color: 'var(--fg-3)' }}>/ 100</span>
      </div>
    </div>
  );
}

function Heatmap({ activity, speed, max, tilt }: { activity: number[][]; speed: number[][]; max: number; tilt: boolean }) {
  return (
    <div className="overflow-x-auto pb-2" style={{ perspective: tilt ? '1400px' : 'none' }}>
      <div style={{
        display: 'inline-block',
        transform: tilt ? 'rotateX(42deg) rotateZ(-2deg)' : 'none',
        transformStyle: 'preserve-3d', transformOrigin: 'center bottom',
        transition: 'transform .5s ease', padding: tilt ? '40px 8px 8px' : '0',
      }}>
        {/* hour header */}
        <div style={{ display: 'grid', gridTemplateColumns: `36px repeat(24, 16px)`, gap: 2, marginBottom: 2 }}>
          <span />
          {Array.from({ length: 24 }).map((_, h) => (
            <span key={h} className="text-[8px] text-center font-mono" style={{ color: 'var(--fg-3)' }}>{h % 3 === 0 ? String(h).padStart(2, '0') : ''}</span>
          ))}
        </div>
        {activity.map((row, d) => (
          <div key={d} style={{ display: 'grid', gridTemplateColumns: `36px repeat(24, 16px)`, gap: 2, marginBottom: 2, transformStyle: 'preserve-3d' }}>
            <span className="text-[10px] font-semibold flex items-center" style={{ color: 'var(--fg-2)' }}>{DOW[d]}</span>
            {row.map((v, h) => {
              const intensity = max ? v / max : 0;
              const lift = tilt ? intensity * 26 : 0;
              return (
                <div key={h} title={`${DOW[d]} ${String(h).padStart(2, '0')}:00 — ${v} pings · avg ${speed[d][h]} km/h`}
                  style={{
                    width: 16, height: 16, borderRadius: 2,
                    background: intensity === 0 ? 'var(--bg-2)' : `rgba(34, 211, 238, ${0.12 + intensity * 0.85})`,
                    transform: lift ? `translateZ(${lift}px)` : 'none',
                    boxShadow: tilt && intensity > 0.05 ? `0 ${4 + lift / 3}px ${6 + lift / 2}px rgba(0,0,0,0.45)` : 'none',
                    border: '1px solid var(--bg-1)',
                  }} />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function Kpi({ icon: Icon, label, value, sub }: { icon: any; label: string; value: string; sub?: string }) {
  return (
    <motion.div className="card card-hover flex items-center gap-3" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <div className="p-2 rounded-lg shrink-0" style={{ background: 'var(--accent-soft)', boxShadow: '0 0 18px -6px var(--accent-glow)' }}>
        <Icon className="w-4 h-4" style={{ color: 'var(--accent)' }} />
      </div>
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider truncate" style={{ color: 'var(--fg-3)' }}>{label}</div>
        <div className="text-base font-bold truncate" style={{ color: 'var(--fg-1)' }}>{value}</div>
        {sub && <div className="text-[10px] truncate" style={{ color: 'var(--fg-3)' }}>{sub}</div>}
      </div>
    </motion.div>
  );
}
