import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Eye, Truck, Activity, Route, Clock, Gauge,
  AlertTriangle, RefreshCw, Loader2, ArrowRight, Zap, CircleDot,
  Timer, Map as MapIcon, Search,
} from 'lucide-react';
import {
  observeSnapshot, type ObserveSnapshot, type ObserveVehicle,
  type ObserveTrip, type ObserveAlert,
  observeDeviceAlerts, type DeviceAlerts, type DeviceAlertFinding,
} from '../lib/api';

// ============================================================================
// Observe — the "raw signal" lens on the route-intel warehouse.
//
//   1. KPI strip           — fleet totals at a glance
//   2. Live alerts feed    — auto-derived from trip metrics (long idle, slow
//                            average, long haul, unanalysed, backtracks)
//   3. Vehicle roster      — one row per vehicle with status pill
//   4. Recent activity     — newest trips, chronological
//
// All data is pulled from /api/v1/observe/snapshot — no mocks, no scaffolds.
// ============================================================================

// status pill based on how recently the vehicle last reported
type Status = 'ACTIVE' | 'STALE' | 'OFFLINE' | 'UNKNOWN';
function statusFor(lastSeen: string | null): Status {
  if (!lastSeen) return 'UNKNOWN';
  const ageH = (Date.now() - new Date(lastSeen).getTime()) / 3_600_000;
  if (ageH < 24)  return 'ACTIVE';
  if (ageH < 168) return 'STALE';
  return 'OFFLINE';
}
const statusColor: Record<Status, string> = {
  ACTIVE:  'var(--success)',
  STALE:   'var(--warning)',
  OFFLINE: 'var(--danger)',
  UNKNOWN: 'var(--fg-4)',
};

const SEVERITY_COLOR: Record<'HIGH' | 'MEDIUM' | 'LOW', string> = {
  HIGH:   'var(--danger)',
  MEDIUM: 'var(--warning)',
  LOW:    'var(--accent)',
};

const ALERT_LABEL: Record<string, string> = {
  long_idle:  'Long idle',
  slow_avg:   'Slow average',
  long_haul:  'Long haul',
  unanalysed: 'Unanalysed',
  backtracks: 'Backtracks',
};

export default function Observe() {
  const [snap, setSnap]       = useState<ObserveSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [search, setSearch]   = useState('');
  const [sevFilter, setSev]   = useState<'ALL' | 'HIGH' | 'MEDIUM' | 'LOW'>('ALL');

  const load = () => {
    setLoading(true); setError(null);
    observeSnapshot()
      .then(setSnap)
      .catch(e => setError(e?.response?.data?.detail ?? e?.message ?? 'failed'))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const filteredAlerts = useMemo(() => {
    if (!snap) return [];
    const q = search.trim().toLowerCase();
    return snap.alerts.filter(a => {
      if (sevFilter !== 'ALL' && a.severity !== sevFilter) return false;
      if (q) {
        const bag = `${a.vehicle_id} ${a.from_waypoint ?? ''} ${a.to_waypoint ?? ''} ${a.note}`.toLowerCase();
        if (!bag.includes(q)) return false;
      }
      return true;
    });
  }, [snap, search, sevFilter]);

  const filteredVehicles = useMemo(() => {
    if (!snap) return [];
    const q = search.trim().toLowerCase();
    if (!q) return snap.vehicles;
    return snap.vehicles.filter(v => v.vehicle_id.toLowerCase().includes(q));
  }, [snap, search]);

  return (
    <div className="space-y-6">
      {/* ===== Hero =================================================== */}
      <motion.section
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
        className="rounded-2xl p-6 border"
        style={{
          background: 'radial-gradient(900px 160px at 0% 0%, var(--accent-soft), transparent), var(--bg-3)',
          borderColor: 'var(--border)',
        }}
      >
        <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--accent)' }}>
          <Eye className="w-4 h-4" />
          <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">Observe</span>
        </div>
        <h1
          className="text-3xl font-bold mb-2"
          style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}
        >
          Raw signal across the fleet
        </h1>
        <p className="text-sm leading-relaxed max-w-3xl" style={{ color: 'var(--fg-2)' }}>
          What every uploaded vehicle has done — distance, hours, idle, alerts.
          The "before AI explains anything" view. Auto-derived from your Route Intelligence uploads.
          {snap?.generated_at && (
            <span className="mono text-xs ml-2" style={{ color: 'var(--fg-3)' }}>
              · refreshed {new Date(snap.generated_at).toLocaleTimeString()}
            </span>
          )}
        </p>
        <div className="mt-3 flex gap-2">
          <button onClick={load} className="btn-soft text-xs">
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
          <Link to="/route-intel" className="btn-primary text-xs">
            Upload more data
          </Link>
        </div>
      </motion.section>

      {/* ===== Error / Loading ====================================== */}
      {error && <ErrorBanner message={error} onRetry={load} />}
      {loading && !snap && (
        <div className="card text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Pulling fleet snapshot…
        </div>
      )}
      {!loading && snap && snap.vehicles.length === 0 && (
        <EmptyState />
      )}

      {snap && snap.vehicles.length > 0 && (
        <>
          {/* ===== KPI strip ========================================= */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <Kpi icon={Truck}     label="Vehicles"      value={snap.kpis.n_vehicles}                       accent="var(--accent)" />
            <Kpi icon={Route}     label="Trips"         value={snap.kpis.n_trips}                          accent="var(--accent-2)" />
            <Kpi icon={MapIcon}   label="Total km"      value={Math.round(snap.kpis.total_km).toLocaleString('en-IN')}  accent="var(--genai)" />
            <Kpi icon={Clock}     label="Total hours"   value={Math.round(snap.kpis.total_hours).toLocaleString('en-IN')} accent="var(--prediction)" />
            <Kpi icon={Gauge}     label="Avg km/h"      value={(snap.kpis.avg_speed_kmph || 0).toFixed(1)} accent="var(--success)" />
            <Kpi icon={Activity}  label="Max km/h"      value={(snap.kpis.max_speed_kmph || 0).toFixed(0)} accent="var(--warning)" />
          </div>

          {/* ===== Toolbar ========================================== */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative flex-1 min-w-[220px] max-w-[420px]">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--fg-3)' }} />
              <input
                value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter by vehicle, route, alert…"
                className="w-full pl-8 pr-3 py-1.5 rounded-md text-xs"
                style={{ background: 'var(--bg-2)', color: 'var(--fg-1)', border: '1px solid var(--border)' }}
              />
            </div>
            <span className="text-[10px] uppercase tracking-[0.12em] ml-2" style={{ color: 'var(--fg-3)' }}>
              Severity
            </span>
            {(['ALL', 'HIGH', 'MEDIUM', 'LOW'] as const).map(sev => (
              <button
                key={sev} onClick={() => setSev(sev)}
                className="text-[11px] px-2.5 py-1 rounded-full"
                style={{
                  background: sevFilter === sev ? (sev === 'ALL' ? 'var(--accent)' : SEVERITY_COLOR[sev]) : 'var(--bg-2)',
                  color:      sevFilter === sev ? '#000' : 'var(--fg-2)',
                  border:     `1px solid ${sevFilter === sev ? (sev === 'ALL' ? 'var(--accent)' : SEVERITY_COLOR[sev]) : 'var(--border)'}`,
                  fontWeight: sevFilter === sev ? 600 : 500,
                }}
              >
                {sev}
              </button>
            ))}
          </div>

          {/* ===== Alerts ========================================== */}
          <section
            className="rounded-2xl border"
            style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}
          >
            <div className="px-5 py-3 border-b flex items-center justify-between"
              style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" style={{ color: 'var(--danger)' }} />
                <h2 className="text-sm font-semibold" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
                  Live alerts
                </h2>
                <span className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>
                  {filteredAlerts.length} of {snap.alerts.length}
                </span>
              </div>
              <span className="text-[11px]" style={{ color: 'var(--fg-3)' }}>
                Derived from trip metrics — no manual rules needed
              </span>
            </div>
            <div className="divide-y" style={{ borderColor: 'var(--border-soft)' }}>
              {filteredAlerts.length === 0 ? (
                <div className="px-5 py-4 text-xs" style={{ color: 'var(--fg-3)' }}>
                  No alerts match the current filter.
                </div>
              ) : filteredAlerts.slice(0, 25).map((a, i) => (
                <AlertRow key={`${a.trip_id}-${a.alert_type}-${i}`} a={a} />
              ))}
            </div>
          </section>

          {/* ===== Device alerts (from s_alert_lov) ================ */}
          <DeviceAlertsSection />

          {/* ===== Vehicle roster ================================== */}
          <section>
            <div className="flex items-center gap-2 mb-3" style={{ color: 'var(--fg-3)' }}>
              <Truck className="w-4 h-4" style={{ color: 'var(--accent)' }} />
              <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">
                Vehicle roster · {filteredVehicles.length} vehicle{filteredVehicles.length === 1 ? '' : 's'}
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {filteredVehicles.map((v, i) => <VehicleCard key={v.vehicle_id} v={v} index={i} />)}
            </div>
          </section>

          {/* ===== Recent activity ================================ */}
          <section>
            <div className="flex items-center gap-2 mb-3" style={{ color: 'var(--fg-3)' }}>
              <Activity className="w-4 h-4" style={{ color: 'var(--accent)' }} />
              <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">
                Recent activity · last {snap.recent_trips.length} trips
              </span>
            </div>
            <div className="rounded-2xl border overflow-hidden" style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}>
              <table className="w-full text-xs">
                <thead style={{ background: 'var(--bg-2)' }}>
                  <tr className="text-left" style={{ color: 'var(--fg-3)' }}>
                    <th className="px-3 py-2 font-semibold">When</th>
                    <th className="px-3 py-2 font-semibold">Vehicle</th>
                    <th className="px-3 py-2 font-semibold">Route</th>
                    <th className="px-3 py-2 font-semibold text-right">km</th>
                    <th className="px-3 py-2 font-semibold text-right">Duration</th>
                    <th className="px-3 py-2 font-semibold text-right">Avg km/h</th>
                    <th className="px-3 py-2 font-semibold text-right">Idle</th>
                    <th className="px-3 py-2 font-semibold text-right">Segments</th>
                    <th className="px-3 py-2 font-semibold text-right">AI</th>
                    <th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {snap.recent_trips.map((t) => <TripRow key={t.id} t={t} />)}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

// ============================================================================
// sub-components
// ============================================================================

function Kpi({ icon: Icon, label, value, accent }: { icon: any; label: string; value: any; accent: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-xl p-3 border"
      style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center gap-2">
        <div className="p-1.5 rounded-md" style={{ background: 'var(--bg-2)' }}>
          <Icon className="w-3.5 h-3.5" style={{ color: accent }} />
        </div>
        <div className="text-[10px] uppercase tracking-[0.12em]" style={{ color: 'var(--fg-3)' }}>{label}</div>
      </div>
      <div className="mt-2 text-2xl font-bold mono"
        style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
        {value}
      </div>
    </motion.div>
  );
}

function VehicleCard({ v, index }: { v: ObserveVehicle; index: number }) {
  const status = statusFor(v.last_seen_ts);
  const idlePct = v.total_hours > 0 ? Math.round((v.stopped_hours / v.total_hours) * 100) : 0;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      className="rounded-2xl p-4 border"
      style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] mb-0.5" style={{ color: 'var(--fg-3)' }}>Vehicle</div>
          <div className="text-base font-bold mono" style={{ color: 'var(--fg-1)' }}>{v.vehicle_id}</div>
        </div>
        <span
          className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded"
          style={{ background: 'var(--bg-2)', color: statusColor[status], border: `1px solid ${statusColor[status]}` }}
          title={v.last_seen_ts ? `Last seen: ${new Date(v.last_seen_ts).toLocaleString()}` : 'Never seen'}
        >
          <CircleDot className="w-2.5 h-2.5" /> {status}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-3">
        <Cell label="trips"     value={v.n_trips} />
        <Cell label="km"        value={Math.round(v.total_km).toLocaleString('en-IN')} />
        <Cell label="hours"     value={(v.total_hours || 0).toFixed(0)} />
        <Cell label="segments"  value={v.total_segments} />
        <Cell label="avg km/h"  value={(v.avg_speed_kmph || 0).toFixed(1)} />
        <Cell label="max km/h"  value={(v.max_speed_kmph || 0).toFixed(0)} />
      </div>

      {v.total_hours > 0 && (
        <div className="mb-3">
          <div className="flex items-center justify-between text-[10px] mb-1" style={{ color: 'var(--fg-3)' }}>
            <span><Timer className="w-2.5 h-2.5 inline mr-1" />Moving vs idle</span>
            <span className="mono">{(v.moving_hours || 0).toFixed(1)} h moving · {(v.stopped_hours || 0).toFixed(1)} h idle</span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden flex" style={{ background: 'var(--bg-2)' }}>
            <div style={{ width: `${100 - idlePct}%`, background: 'var(--success)' }} />
            <div style={{ width: `${idlePct}%`,       background: 'var(--warning)' }} />
          </div>
        </div>
      )}

      <div className="text-[10px] mono pt-2 border-t flex items-center justify-between"
        style={{ borderColor: 'var(--border)', color: 'var(--fg-3)' }}>
        <span>last seen · {v.last_seen_ts ? new Date(v.last_seen_ts).toLocaleString() : '—'}</span>
        <span>{v.n_analyzed}/{v.n_trips} analysed</span>
      </div>
    </motion.div>
  );
}

function Cell({ label, value }: { label: string; value: any }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-[0.12em]" style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="text-sm font-bold mono" style={{ color: 'var(--fg-1)' }}>{value ?? '—'}</div>
    </div>
  );
}

function AlertRow({ a }: { a: ObserveAlert }) {
  const color = SEVERITY_COLOR[a.severity] || 'var(--fg-3)';
  return (
    <Link
      to={`/route-intel/trips/${a.trip_id}`}
      className="grid grid-cols-12 gap-2 items-center px-5 py-3 text-xs hover:bg-[var(--bg-2)] transition-colors"
    >
      <div className="col-span-2 flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
        <span className="font-semibold uppercase tracking-wider text-[10px]" style={{ color }}>
          {a.severity}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--bg-2)', color: 'var(--fg-2)' }}>
          {ALERT_LABEL[a.alert_type] ?? a.alert_type}
        </span>
      </div>
      <div className="col-span-2 mono truncate" style={{ color: 'var(--fg-1)' }}>{a.vehicle_id}</div>
      <div className="col-span-4 truncate" style={{ color: 'var(--fg-2)' }}>
        {a.from_waypoint ?? '—'} → {a.to_waypoint ?? '—'}
      </div>
      <div className="col-span-3" style={{ color: 'var(--fg-1)' }}>{a.note}</div>
      <div className="col-span-1 flex justify-end" style={{ color: 'var(--accent)' }}>
        <ArrowRight className="w-3.5 h-3.5" />
      </div>
    </Link>
  );
}

function TripRow({ t }: { t: ObserveTrip }) {
  const status = statusFor(t.end_ts);
  return (
    <tr className="border-t" style={{ borderColor: 'var(--border-soft)' }}>
      <td className="px-3 py-2 mono text-[11px]" style={{ color: 'var(--fg-3)' }}>
        <span className="block">{new Date(t.start_ts).toLocaleDateString()}</span>
        <span className="text-[10px]">{new Date(t.start_ts).toLocaleTimeString()}</span>
      </td>
      <td className="px-3 py-2 mono" style={{ color: 'var(--fg-1)' }}>
        <span className="inline-flex items-center gap-1">
          <CircleDot className="w-2 h-2" style={{ color: statusColor[status] }} />
          {t.vehicle_id}
        </span>
      </td>
      <td className="px-3 py-2 truncate max-w-[260px]" style={{ color: 'var(--fg-2)' }}>
        {t.from_waypoint ?? '—'} → {t.to_waypoint ?? '—'}
      </td>
      <td className="px-3 py-2 text-right mono" style={{ color: 'var(--fg-1)' }}>
        {Math.round(t.distance_km).toLocaleString('en-IN')}
      </td>
      <td className="px-3 py-2 text-right mono" style={{ color: 'var(--fg-2)' }}>
        {(t.duration_min / 60).toFixed(1)} h
      </td>
      <td className="px-3 py-2 text-right mono" style={{ color: 'var(--fg-2)' }}>
        {(t.avg_speed_kmph || 0).toFixed(1)}
      </td>
      <td className="px-3 py-2 text-right mono" style={{ color: t.stopped_min > 240 ? 'var(--warning)' : 'var(--fg-2)' }}>
        {(t.stopped_min / 60).toFixed(1)} h
      </td>
      <td className="px-3 py-2 text-right mono" style={{ color: 'var(--fg-2)' }}>
        {t.n_segments}
      </td>
      <td className="px-3 py-2 text-right">
        {t.analyzed
          ? <span className="text-[10px] mono" style={{ color: 'var(--success)' }}>analysed</span>
          : <span className="text-[10px] mono" style={{ color: 'var(--fg-4)' }}>—</span>}
      </td>
      <td className="px-3 py-2 text-right">
        <Link to={`/route-intel/trips/${t.id}`}
          className="text-[11px] font-semibold inline-flex items-center gap-1"
          style={{ color: 'var(--accent)' }}>
          Open <ArrowRight className="w-3 h-3" />
        </Link>
      </td>
    </tr>
  );
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-lg p-4 text-sm flex items-start gap-2"
      style={{ background: 'rgba(255,77,109,0.08)', border: '1px solid var(--danger)' }}>
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--danger)' }} />
      <div className="flex-1">
        <div className="font-semibold" style={{ color: 'var(--fg-1)' }}>Could not pull the fleet snapshot</div>
        <div className="text-xs mt-1 mono" style={{ color: 'var(--fg-3)' }}>{message}</div>
        <button onClick={onRetry} className="btn-soft text-xs mt-2">
          <RefreshCw className="w-3 h-3" /> Retry
        </button>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card text-center py-10" style={{ color: 'var(--fg-3)' }}>
      <div className="w-12 h-12 mx-auto rounded-full flex items-center justify-center mb-3"
        style={{ background: 'var(--accent-soft)' }}>
        <Eye className="w-5 h-5" style={{ color: 'var(--accent)' }} />
      </div>
      <div className="text-sm font-semibold mb-1" style={{ color: 'var(--fg-1)' }}>
        No vehicles in the warehouse yet
      </div>
      <div className="text-xs mb-3">
        Upload an Excel from Route Intelligence and this page populates automatically.
      </div>
      <Link to="/route-intel" className="btn-primary text-xs">Go to upload</Link>
    </div>
  );
}

// ============================================================================
// Device alerts — findings parsed from the vendor `s_alert_lov` column.
// Headline per alert code → drill down to affected devices. Codes show as
// "code N" until you name them (pencil ✎), after which the label sticks.
// ============================================================================
function DeviceAlertsSection() {
  const [data, setData] = useState<DeviceAlerts | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [editCode, setEditCode] = useState<string | null>(null);
  const [editVal, setEditVal] = useState('');

  const load = () => {
    setLoading(true); setErr(null);
    observeDeviceAlerts()
      .then(setData)
      .catch(e => setErr(e?.response?.data?.detail ?? e?.message ?? 'failed'))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const saveLabel = async (code: string) => {
    const { observePutAlertLabels } = await import('../lib/api');
    await observePutAlertLabels({ [code]: editVal });
    setEditCode(null); setEditVal('');
    load();
  };

  const t = data?.totals;
  return (
    <section className="rounded-2xl border" style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}>
      <div className="px-5 py-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4" style={{ color: 'var(--warning)' }} />
          <h2 className="text-sm font-semibold" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
            Device alerts <span className="mono text-[11px]" style={{ color: 'var(--fg-3)' }}>· from s_alert_lov</span>
          </h2>
          {t && (
            <span className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>
              {t.distinct_codes} codes · {t.alert_rows.toLocaleString()} alert rows ({t.alert_row_pct}%) · {t.files_scanned} files
            </span>
          )}
        </div>
        <button onClick={load} className="btn-soft text-xs"><RefreshCw className="w-3 h-3" /> Refresh</button>
      </div>

      <div className="p-4">
        {loading && <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}><Loader2 className="w-3.5 h-3.5 animate-spin" /> Scanning uploaded GPS files…</div>}
        {err && <div className="text-xs" style={{ color: 'var(--danger)' }}>{err}</div>}
        {!loading && !err && (data?.findings.length ?? 0) === 0 && (
          <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
            No <span className="mono">s_alert_lov</span> signals yet — upload GPS Excel files and findings appear here automatically.
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {(data?.findings ?? []).map((f: DeviceAlertFinding) => {
            const isOpen = !!open[f.code];
            return (
              <div key={f.code} className="rounded-lg overflow-hidden" style={{ background: 'var(--bg-2)', borderLeft: '3px solid var(--warning)' }}>
                <div className="p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-xs font-semibold truncate" style={{ color: 'var(--fg-1)' }}>{f.label}</span>
                      {!f.labelled && (
                        <button title="Name this code" onClick={() => { setEditCode(f.code); setEditVal(''); }}
                          className="text-[10px]" style={{ color: 'var(--accent)' }}>✎</button>
                      )}
                    </div>
                    <span className="text-xs font-bold mono" style={{ color: 'var(--warning)' }}>{f.count.toLocaleString()}</span>
                  </div>
                  <div className="text-[10px] mono mt-0.5" style={{ color: 'var(--fg-3)' }}>
                    code {f.code} · {f.n_devices} device{f.n_devices === 1 ? '' : 's'} · e.g. {String(f.sample_value).slice(0, 22)}
                  </div>
                  {editCode === f.code && (
                    <div className="flex items-center gap-1 mt-2">
                      <input autoFocus value={editVal} onChange={e => setEditVal(e.target.value)}
                        placeholder="label e.g. Harsh braking" className="text-[11px] px-2 py-1 rounded flex-1"
                        style={{ background: 'var(--bg-3)', color: 'var(--fg-1)', border: '1px solid var(--border)' }} />
                      <button onClick={() => saveLabel(f.code)} className="btn-primary text-[10px]">Save</button>
                      <button onClick={() => setEditCode(null)} className="btn-soft text-[10px]">✕</button>
                    </div>
                  )}
                  <button onClick={() => setOpen(s => ({ ...s, [f.code]: !isOpen }))}
                    className="text-[10px] mt-2 flex items-center gap-1" style={{ color: 'var(--accent)' }}>
                    {isOpen ? 'Hide' : 'Show'} devices <ArrowRight className="w-3 h-3" />
                  </button>
                  {isOpen && (
                    <div className="mt-2 flex flex-col gap-1">
                      {f.devices.slice(0, 12).map(d => (
                        <div key={d.device} className="flex items-center justify-between text-[10px] mono" style={{ color: 'var(--fg-2)' }}>
                          <span className="truncate">{d.device}</span>
                          <span style={{ color: 'var(--fg-3)' }}>{d.count.toLocaleString()}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
