import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft, Route, Clock, Gauge, MapPin, Activity, Satellite, Flag, TrendingUp,
  RefreshCw, Timer, ChevronRight, AlertTriangle, BedDouble, Navigation, Hourglass,
  CalendarDays, Map as MapIcon,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import PageHeader from '../components/ui/PageHeader';
import LeafletMap from '../components/ui/LeafletMap';
import {
  fetchGpsKpis, fetchGpsTrack, fetchGpsJourneys, fetchGpsSpeedProfile, fetchGpsHalts,
  fetchGpsAlerts, fetchGpsDeviceHealth, fetchGpsGeofences, fetchGpsStopEvents,
  type GpsKpis, type GpsTrackPoint, type Journey, type Geofence, type StopEvent, type HaltKpis,
} from '../lib/api';
import { fmtDur } from './HaltsRests';

export default function VehicleDetail() {
  const { vehicle = '' } = useParams();
  const nav = useNavigate();

  const [kpis, setKpis] = useState<GpsKpis | null>(null);
  const [haltKpis, setHaltKpis] = useState<HaltKpis | null>(null);
  const [journeys, setJourneys] = useState<Journey[]>([]);
  const [speed, setSpeed] = useState<{ series: { t: string; spd: number }[] } | null>(null);
  const [alerts, setAlerts] = useState<{ events: any[]; signal_drops: any[] } | null>(null);
  const [health, setHealth] = useState<any>(null);
  const [stops, setStops] = useState<StopEvent[]>([]);
  const [geofences, setGeofences] = useState<Geofence[]>([]);

  // Map is loaded ON DEMAND only (it's the heaviest fetch).
  const [track, setTrack] = useState<GpsTrackPoint[]>([]);
  const [merge, setMerge] = useState<15 | 0>(15);
  const [showMap, setShowMap] = useState(false);
  const [mapBusy, setMapBusy] = useState(false);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  function loadAnalytics() {
    setBusy(true); setErrorMsg(null);
    Promise.allSettled([
      fetchGpsKpis(vehicle), fetchGpsJourneys(vehicle), fetchGpsSpeedProfile(vehicle),
      fetchGpsAlerts(vehicle), fetchGpsDeviceHealth(vehicle), fetchGpsGeofences(),
      fetchGpsStopEvents(vehicle), fetchGpsHalts(vehicle),
    ]).then(([k, j, sp, al, he, gf, se, h]) => {
      if (k.status === 'fulfilled') setKpis(k.value.kpis ?? null);
      if (j.status === 'fulfilled') setJourneys(j.value.journeys);
      if (sp.status === 'fulfilled') setSpeed(sp.value);
      if (al.status === 'fulfilled') setAlerts(al.value);
      if (he.status === 'fulfilled') setHealth(he.value.summary);
      if (gf.status === 'fulfilled') setGeofences(gf.value.geofences);
      if (se.status === 'fulfilled') setStops(se.value.stops);
      if (h.status === 'fulfilled') setHaltKpis(h.value.kpis);
      const failed = [k, j, sp, he].filter(r => r.status === 'rejected').length;
      if (failed) setErrorMsg(`${failed} panel(s) timed out — click Refresh (first load warms the cache).`);
    }).finally(() => { setBusy(false); setLoading(false); });
  }
  useEffect(loadAnalytics, [vehicle]);

  function loadMap(m: 15 | 0 = merge) {
    setMapBusy(true); setShowMap(true);
    fetchGpsTrack(vehicle, m).then(t => setTrack(t.points)).catch(() => {}).finally(() => setMapBusy(false));
  }
  function changeMerge(m: 15 | 0) { setMerge(m); if (showMap) loadMap(m); }

  const mapStops = stops.map(s => ({ lat: s.lat, lng: s.lng, minutes: s.minutes, near: s.where }));

  if (loading) return (
    <div className="space-y-4">
      <PageHeader title={vehicle} subtitle="Loading vehicle analytics…" />
      <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-2)' }}>
        <RefreshCw className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} /> Warming the cache…
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <button onClick={() => nav('/gps')} className="flex items-center gap-2 text-sm" style={{ color: 'var(--accent)' }}>
          <ArrowLeft className="w-4 h-4" /> Back to fleet
        </button>
        <button onClick={loadAnalytics} className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs"
          style={{ background: 'var(--bg-2)', color: 'var(--fg-2)', border: '1px solid var(--border)' }}>
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* Hero header */}
      <motion.div className="card relative overflow-hidden" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        style={{ background: 'linear-gradient(120deg, var(--accent-soft), transparent 60%)' }}>
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-xl" style={{ background: 'var(--accent-soft)', boxShadow: '0 0 28px -8px var(--accent-glow)' }}>
            <Satellite className="w-6 h-6" style={{ color: 'var(--accent)' }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold font-mono text-gradient">{vehicle}</h1>
            <p className="text-xs" style={{ color: 'var(--fg-3)' }}>Per-vehicle GPS intelligence — route, journeys, speed and device health.</p>
          </div>
        </div>
      </motion.div>

      {errorMsg && <div className="card text-xs" style={{ color: '#fca5a5', borderColor: '#7f1d1d' }}>{errorMsg}</div>}

      {/* KPIs — richer grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <Kpi i={0} icon={Route} label="Distance" value={`${kpis?.distance_km ?? 0} km`} sub={`${kpis?.avg_daily_km ?? 0} km/day`} />
        <Kpi i={1} icon={Clock} label="Drive / Idle" value={`${kpis?.drive_hours ?? 0} / ${kpis?.idle_hours ?? 0}h`} sub={`${kpis?.utilization_pct ?? 0}% util`} />
        <Kpi i={2} icon={Gauge} label="Avg moving" value={`${kpis?.avg_moving_speed ?? 0}`} sub={`max ${kpis?.max_speed ?? 0} km/h`} />
        <Kpi i={3} icon={Route} label="Journeys" value={String(journeys.length)} sub="reconstructed" />
        <Kpi i={4} icon={MapPin} label="Stops" value={String(kpis?.stop_count ?? 0)} sub={haltKpis ? `${haltKpis.distinct_places} places` : undefined} />
        <Kpi i={5} icon={Timer} label="Time stopped" value={haltKpis ? `${haltKpis.total_hours}h` : '—'} sub={haltKpis ? `avg ${fmtDur(haltKpis.avg_min)}` : undefined} />
        <Kpi i={6} icon={BedDouble} label="Rest time" value={haltKpis ? `${haltKpis.rest_hours}h` : '—'} sub="night rest" />
        <Kpi i={7} icon={Hourglass} label="Longest halt" value={haltKpis ? fmtDur(haltKpis.longest_min) : '—'} />
        <Kpi i={8} icon={CalendarDays} label="Active days" value={String(kpis?.active_days ?? 0)} sub={`${(kpis?.total_pings ?? 0).toLocaleString()} pings`} />
        <Kpi i={9} icon={Flag} label="States" value={String(kpis?.states_covered ?? 0)} />
        <Kpi i={10} icon={TrendingUp} label="Over-speed" value={`${kpis?.overspeed_pct ?? 0}%`} sub={`${kpis?.overspeed_pings ?? 0} pings`} />
        <Kpi i={11} icon={Activity} label="Avg signal" value={`${kpis?.avg_signal_pct ?? 0}%`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Map — ON DEMAND */}
        <div className="card lg:col-span-2">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold flex items-center gap-2"><MapPin className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Route track</h3>
            {showMap && (
              <div className="flex items-center gap-1 text-xs">
                <span style={{ color: 'var(--fg-3)' }}>merge:</span>
                {([15, 0] as const).map(b => (
                  <button key={b} onClick={() => changeMerge(b)} className="px-2 py-0.5 rounded"
                    style={{
                      background: merge === b ? 'var(--accent-soft)' : 'var(--bg-2)',
                      color: merge === b ? 'var(--accent)' : 'var(--fg-2)',
                      border: `1px solid ${merge === b ? 'var(--accent)' : 'var(--border)'}`,
                    }}>{b === 0 ? 'full' : '15m'}</button>
                ))}
              </div>
            )}
          </div>

          {!showMap ? (
            <button onClick={() => loadMap()}
              className="w-full flex flex-col items-center justify-center gap-3 rounded-xl"
              style={{ height: 420, background: 'var(--bg-2)', border: '1px dashed var(--border)' }}>
              <div className="p-4 rounded-full" style={{ background: 'var(--accent-soft)', boxShadow: '0 0 30px -8px var(--accent-glow)' }}>
                <MapIcon className="w-7 h-7" style={{ color: 'var(--accent)' }} />
              </div>
              <div className="text-sm font-semibold" style={{ color: 'var(--fg-1)' }}>Load route map</div>
              <div className="text-xs" style={{ color: 'var(--fg-3)' }}>Rendered on demand (15-min merge — fast). Click to draw {vehicle}'s route &amp; halts.</div>
            </button>
          ) : mapBusy ? (
            <div className="flex items-center justify-center gap-2 rounded-xl" style={{ height: 420, background: 'var(--bg-2)', color: 'var(--fg-3)' }}>
              <RefreshCw className="w-4 h-4 animate-spin" style={{ color: 'var(--accent)' }} /> Drawing route…
            </div>
          ) : (
            <>
              <p className="text-xs mb-3" style={{ color: 'var(--fg-3)' }}>
                {track.length.toLocaleString()} points{merge ? ' (15-min merge — fast)' : ' (raw)'} · red markers = halts
              </p>
              <LeafletMap points={track} stops={mapStops} geofences={geofences} height={420} />
            </>
          )}
        </div>

        {/* Journeys */}
        <div className="card">
          <h3 className="font-semibold mb-1 flex items-center gap-2"><Route className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Journeys</h3>
          <p className="text-xs mb-3" style={{ color: 'var(--fg-3)' }}>Reconstructed from GPS. Click for route &amp; halts.</p>
          <div className="space-y-2 max-h-[420px] overflow-y-auto">
            {journeys.map(j => (
              <button key={j.trip} onClick={() => nav(`/halts/${encodeURIComponent(vehicle)}/${j.trip}`)}
                className="w-full text-left p-2 rounded-lg lift flex items-center gap-2" style={{ background: 'var(--bg-2)' }}>
                <span className="flex items-center justify-center w-7 h-7 rounded-md text-xs font-bold shrink-0"
                  style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>{j.trip}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium truncate" style={{ color: 'var(--fg-1)' }}>{j.from_place} → {j.to_place}</div>
                  <div className="text-[10px] flex items-center gap-1" style={{ color: 'var(--fg-3)' }}>
                    {j.distance_km} km · {fmtDur(j.duration_min)} · <Timer className="inline w-3 h-3" /> {j.halt_count}
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 shrink-0" style={{ color: 'var(--fg-3)' }} />
              </button>
            ))}
            {journeys.length === 0 && <div className="text-xs" style={{ color: 'var(--fg-3)' }}>No journeys reconstructed.</div>}
          </div>
        </div>
      </div>

      {/* Speed + health */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card lg:col-span-2">
          <h3 className="font-semibold mb-3 flex items-center gap-2"><Gauge className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Speed over time</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={speed?.series ?? []}>
              <defs><linearGradient id="vspd" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.5} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
              </linearGradient></defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="t" tick={{ fontSize: 9, fill: 'var(--fg-3)' }} tickFormatter={(t) => new Date(t).toLocaleDateString()} minTickGap={40} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--fg-3)' }} />
              <Tooltip contentStyle={{ background: 'var(--bg-1)', border: '1px solid var(--border)', fontSize: 11 }} labelFormatter={(t) => new Date(t).toLocaleString()} />
              <Area type="monotone" dataKey="spd" stroke="var(--accent)" fill="url(#vspd)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h3 className="font-semibold mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Events &amp; health</h3>
          <div className="space-y-1 max-h-[200px] overflow-y-auto text-xs">
            {alerts?.events.slice(0, 8).map((e, i) => (
              <div key={`e${i}`} className="py-1" style={{ borderBottom: '1px solid var(--border)' }}>
                <span style={{ color: 'var(--danger, #ef4444)' }}>event {e.codes}</span>
                <span className="font-mono ml-1" style={{ color: 'var(--fg-3)' }}>@ {e.near}</span>
              </div>
            ))}
            {(!alerts?.events.length) && <div style={{ color: 'var(--fg-3)' }}>No event flags.</div>}
            {health && (
              <div className="mt-2 text-[11px]" style={{ color: 'var(--fg-3)' }}>
                <Navigation className="inline w-3 h-3" /> Uptime {health.uptime_pct}% · median ping {health.median_ping_sec}s · max gap {health.max_gap_min}min
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({ icon: Icon, label, value, sub, i = 0 }: { icon: any; label: string; value: string; sub?: string; i?: number }) {
  return (
    <motion.div className="card card-hover flex items-center gap-3" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, delay: i * 0.03 }}>
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
