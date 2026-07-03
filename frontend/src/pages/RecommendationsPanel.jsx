import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AlertTriangle, ChevronDown, ChevronRight, ArrowRight, X, Settings2,
  RefreshCw, Loader2, IndianRupee, Gauge, Route as RouteIcon, Save, RotateCcw,
} from 'lucide-react';
import {
  riListRecommendations, riGetRecommendation,
  riGetCostConfig, riPutCostConfig, riResetCostConfig,
} from '../lib/routeIntel';

// ============================================================================
// Critical action items — headline (category) → entries (routes) → detailed
// report. Fully dynamic: the numbers come from the backend cost model whose
// parameters are editable live via the gear (⚙) → config panel.
// ============================================================================

const fmtINR = (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`;
const PRIO_COLOR = { HIGH: 'var(--danger)', MEDIUM: 'var(--warning)', LOW: 'var(--fg-3)' };

// Human labels + grouping for the config editor fields.
const CONFIG_FIELDS = [
  { section: 'Cost model', keys: [
    ['fuel_price_per_liter', 'Fuel price (₹/L)'],
    ['fuel_efficiency_kmpl', 'Fuel efficiency (km/L)'],
    ['driver_wage_per_hour', 'Driver wage (₹/h)'],
    ['idle_fuel_consumption_lph', 'Idle burn (L/h)'],
    ['trips_per_month', 'Trips per month (×)'],
  ]},
  { section: 'Idle Time Reduction (HIGH)', keys: [
    ['idle_hours_trigger', 'Trigger: idle hours >'],
    ['idle_savings_pct', 'Recoverable share (0–1)'],
  ]},
  { section: 'Route Optimization (MEDIUM)', keys: [
    ['speed_target_kmph', 'Trigger: avg speed < (km/h)'],
    ['route_opt_time_saved_pct', 'Time saved share (0–1)'],
  ]},
  { section: 'Peak Hour Avoidance (MEDIUM)', keys: [
    ['peak_hour_start', 'Peak start hour'],
    ['peak_hour_end', 'Peak end hour'],
    ['peak_share_trigger', 'Trigger: peak share > (0–1)'],
    ['peak_per_trip_savings_inr', 'Saving per trip (₹)'],
    ['peak_monthly_savings_inr', 'Saving per month (₹)'],
  ]},
];

export default function RecommendationsPanel() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});     // category → bool
  const [detailId, setDetailId] = useState(null);   // open detail modal for this rec id
  const [showConfig, setShowConfig] = useState(false);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    riListRecommendations()
      .then(setData)
      .catch(e => setError(e?.response?.data?.detail ?? e?.message ?? 'failed to load'))
      .finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  const totals = data?.totals ?? { count: 0, monthly_savings_inr: 0, high: 0, medium: 0 };

  return (
    <section className="rounded-2xl border" style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}>
      {/* header */}
      <div className="px-5 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg" style={{ background: 'var(--bg-2)' }}>
            <AlertTriangle className="w-4 h-4" style={{ color: totals.high ? 'var(--danger)' : 'var(--warning)' }} />
          </div>
          <div>
            <div className="text-sm font-semibold" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
              Critical action items
            </div>
            <div className="text-[11px]" style={{ color: 'var(--fg-3)' }}>
              {totals.count} recommendations across {totals.trips ?? 0} trips · {fmtINR(totals.monthly_savings_inr)}/mo potential
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setShowConfig(true)} className="btn-soft text-xs flex items-center gap-1" title="Edit cost model & thresholds">
            <Settings2 className="w-3 h-3" /> Configure
          </button>
          <button onClick={load} className="btn-soft text-xs"><RefreshCw className="w-3 h-3" /> Refresh</button>
        </div>
      </div>

      <div className="px-5 pb-5">
        {loading && (
          <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Computing recommendations…
          </div>
        )}
        {error && <div className="text-xs" style={{ color: 'var(--danger)' }}>{error}</div>}
        {!loading && !error && (data?.categories?.length ?? 0) === 0 && (
          <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
            No recommendations yet. Analyse a few trips and they'll appear here.
          </div>
        )}

        {/* headline cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {(data?.categories ?? []).map((cat) => {
            const open = !!expanded[cat.category];
            const color = PRIO_COLOR[cat.priority] || 'var(--warning)';
            return (
              <div key={cat.category} className="rounded-lg overflow-hidden"
                style={{ background: 'var(--bg-2)', borderLeft: `3px solid ${color}` }}>
                {/* headline */}
                <button onClick={() => setExpanded(s => ({ ...s, [cat.category]: !open }))}
                  className="w-full p-3 flex flex-col gap-2 text-left">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase tracking-[0.12em] font-bold" style={{ color }}>
                      {cat.priority} · {cat.category}
                    </span>
                    <span className="text-xs font-bold mono" style={{ color: 'var(--success)' }}>
                      {fmtINR(cat.total_monthly_savings_inr)}/mo
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[10px]" style={{ color: 'var(--fg-3)' }}>
                    <span>{cat.count} {cat.count === 1 ? 'route' : 'routes'}</span>
                    <span className="flex items-center gap-1">
                      {open ? 'Hide' : 'Show'} routes
                      {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                    </span>
                  </div>
                </button>
                {/* entries */}
                <AnimatePresence initial={false}>
                  {open && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.18 }} className="overflow-hidden">
                      <div className="px-2 pb-2 flex flex-col gap-1">
                        {cat.entries.map((e) => (
                          <button key={e.id} onClick={() => setDetailId(e.id)}
                            className="w-full text-left p-2 rounded flex items-center justify-between gap-2 transition-colors"
                            style={{ background: 'var(--bg-3)' }}
                            onMouseEnter={(ev) => ev.currentTarget.style.background = 'var(--accent-soft)'}
                            onMouseLeave={(ev) => ev.currentTarget.style.background = 'var(--bg-3)'}>
                            <div className="min-w-0">
                              <div className="text-[11px] font-semibold truncate" style={{ color: 'var(--fg-1)' }}>
                                <span className="mono">{e.vehicle_id}</span>
                              </div>
                              <div className="text-[10px] truncate mono" style={{ color: 'var(--fg-3)' }}>
                                {e.from_waypoint} → {e.to_waypoint}
                              </div>
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              <span className="text-[10px] mono font-bold" style={{ color: 'var(--success)' }}>
                                {fmtINR(e.monthly_savings_inr)}
                              </span>
                              <ArrowRight className="w-3 h-3" style={{ color: 'var(--accent)' }} />
                            </div>
                          </button>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>

      {/* detail report modal */}
      <AnimatePresence>
        {detailId && (
          <DetailReport recId={detailId} onClose={() => setDetailId(null)}
            onOpenTrip={(tripId) => { setDetailId(null); nav(`/route-intel/trips/${tripId}`); }} />
        )}
      </AnimatePresence>

      {/* config editor modal */}
      <AnimatePresence>
        {showConfig && (
          <ConfigEditor onClose={() => setShowConfig(false)} onSaved={() => { setShowConfig(false); load(); }} />
        )}
      </AnimatePresence>
    </section>
  );
}

// ---------------------------------------------------------------------------
function Modal({ children, onClose, wide }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.6)' }} onClick={onClose}>
      <motion.div initial={{ scale: 0.96, y: 8 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 8 }}
        className="rounded-2xl border w-full overflow-hidden flex flex-col"
        style={{ background: 'var(--bg-3)', borderColor: 'var(--border)', maxWidth: wide ? 640 : 560, maxHeight: '85vh' }}
        onClick={(e) => e.stopPropagation()}>
        {children}
      </motion.div>
    </motion.div>
  );
}

function Row({ label, value, strong, accent }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b" style={{ borderColor: 'var(--border)' }}>
      <span className="text-[11px]" style={{ color: 'var(--fg-3)' }}>{label}</span>
      <span className={`text-xs mono ${strong ? 'font-bold' : ''}`} style={{ color: accent || 'var(--fg-1)' }}>{value}</span>
    </div>
  );
}

function DetailReport({ recId, onClose, onOpenTrip }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    riGetRecommendation(recId).then(setD).catch(e => setErr(e?.message ?? 'failed'));
  }, [recId]);

  const color = PRIO_COLOR[d?.priority] || 'var(--warning)';
  const cb = d?.cost_breakdown ?? {};
  const eff = d?.efficiency ?? {};

  return (
    <Modal onClose={onClose} wide>
      <div className="px-5 py-3 flex items-center justify-between border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" style={{ color }} />
          <span className="text-sm font-semibold" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
            {d ? `${d.priority} · ${d.category}` : 'Loading…'}
          </span>
        </div>
        <button onClick={onClose}><X className="w-4 h-4" style={{ color: 'var(--fg-3)' }} /></button>
      </div>

      <div className="p-5 overflow-y-auto text-xs" style={{ color: 'var(--fg-2)' }}>
        {err && <div style={{ color: 'var(--danger)' }}>{err}</div>}
        {!d && !err && <div className="flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Building report…</div>}
        {d && (
          <>
            <div className="mb-3">
              <div className="text-sm font-semibold mb-1" style={{ color: 'var(--fg-1)' }}>
                <span className="mono">{d.vehicle_id}</span> · {d.from_waypoint} → {d.to_waypoint}
              </div>
              <div className="rounded-lg p-3 mb-2" style={{ background: 'var(--accent-soft)', color: 'var(--fg-1)' }}>
                <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--accent)' }}>Recommended action</div>
                {d.recommendation}
              </div>
              <div className="flex items-center gap-4">
                <div><div className="text-[10px]" style={{ color: 'var(--fg-3)' }}>Potential monthly saving</div>
                  <div className="text-lg font-bold mono" style={{ color: 'var(--success)' }}>{fmtINR(d.monthly_savings_inr)}</div></div>
                <div><div className="text-[10px]" style={{ color: 'var(--fg-3)' }}>Per trip</div>
                  <div className="text-lg font-bold mono" style={{ color: 'var(--fg-1)' }}>{fmtINR(d.potential_savings_inr)}</div></div>
              </div>
            </div>

            {/* trigger evidence */}
            {d.metrics && Object.keys(d.metrics).length > 0 && (
              <div className="mb-3">
                <div className="text-[10px] uppercase tracking-wider mb-1 flex items-center gap-1" style={{ color: 'var(--fg-3)' }}>
                  <Gauge className="w-3 h-3" /> Why this fired
                </div>
                {Object.entries(d.metrics).map(([k, v]) => (
                  <Row key={k} label={k.replace(/_/g, ' ')} value={String(v)} />
                ))}
              </div>
            )}

            {/* cost breakdown */}
            <div className="mb-3">
              <div className="text-[10px] uppercase tracking-wider mb-1 flex items-center gap-1" style={{ color: 'var(--fg-3)' }}>
                <IndianRupee className="w-3 h-3" /> Journey cost breakdown
              </div>
              <Row label="Total distance" value={`${cb.total_distance_km ?? '—'} km`} />
              <Row label="Moving / idle hours" value={`${cb.moving_hours ?? '—'} / ${cb.stopped_hours ?? '—'} h`} />
              <Row label="Fuel consumed" value={`${cb.fuel_consumed_liters ?? '—'} L`} />
              <Row label="Fuel cost" value={fmtINR(cb.fuel_cost_inr)} />
              <Row label="Driver cost" value={fmtINR(cb.driver_cost_inr)} />
              <Row label="Idle fuel waste" value={fmtINR(cb.idle_fuel_waste_inr)} accent="var(--warning)" />
              <Row label="Total cost" value={fmtINR(cb.total_cost_inr)} strong />
              <Row label="Cost / km" value={fmtINR(cb.cost_per_km)} />
            </div>

            {/* route efficiency — straight line vs OSRM road vs actual */}
            {eff && !eff.error && (
              <div className="mb-3">
                <div className="text-[10px] uppercase tracking-wider mb-1 flex items-center gap-1" style={{ color: 'var(--fg-3)' }}>
                  <RouteIcon className="w-3 h-3" /> Route efficiency
                </div>
                <Row label="Actual driven" value={`${eff.actual_distance_km ?? '—'} km`} strong />
                <Row label="Straight line (haversine)" value={`${eff.straight_line_distance_km ?? '—'} km`} />
                <Row label="OSRM road distance"
                  value={eff.osrm_road_distance_km != null ? `${eff.osrm_road_distance_km} km` : 'OSRM offline — using straight line'}
                  accent={eff.osrm_road_distance_km != null ? 'var(--accent)' : 'var(--fg-3)'} />
                <Row label="Baseline used" value={eff.baseline_source === 'osrm_road' ? 'OSRM road' : 'straight line'} />
                <Row label="Excess vs baseline" value={`${eff.excess_distance_km ?? '—'} km (${eff.excess_percentage ?? '—'}%)`} accent="var(--warning)" />
              </div>
            )}

            <div className="flex justify-end pt-1">
              <button onClick={() => onOpenTrip(d.trip_id)} className="text-[11px] font-semibold flex items-center gap-1" style={{ color: 'var(--accent)' }}>
                Open full trip analysis <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}

function ConfigEditor({ onClose, onSaved }) {
  const [cfg, setCfg] = useState(null);
  const [defaults, setDefaults] = useState({});
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    riGetCostConfig().then(r => { setCfg(r.config); setDefaults(r.defaults); }).catch(e => setErr(e?.message));
  }, []);

  const set = (k, v) => setCfg(c => ({ ...c, [k]: v === '' ? '' : Number(v) }));
  const save = () => {
    setSaving(true); setErr(null);
    riPutCostConfig(cfg).then(r => { onSaved(r.config); }).catch(e => setErr(e?.response?.data?.detail ?? e?.message)).finally(() => setSaving(false));
  };
  const reset = () => {
    setSaving(true);
    riResetCostConfig().then(r => { setCfg(r.config); }).catch(e => setErr(e?.message)).finally(() => setSaving(false));
  };

  return (
    <Modal onClose={onClose}>
      <div className="px-5 py-3 flex items-center justify-between border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2">
          <Settings2 className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          <span className="text-sm font-semibold" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>Cost model & thresholds</span>
        </div>
        <button onClick={onClose}><X className="w-4 h-4" style={{ color: 'var(--fg-3)' }} /></button>
      </div>
      <div className="p-5 overflow-y-auto">
        <div className="text-[11px] mb-3" style={{ color: 'var(--fg-3)' }}>
          These numbers drive every recommendation. Changes apply to the next analysis — re-analyse a trip to recompute.
        </div>
        {err && <div className="text-xs mb-2" style={{ color: 'var(--danger)' }}>{err}</div>}
        {!cfg && <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…</div>}
        {cfg && CONFIG_FIELDS.map(group => (
          <div key={group.section} className="mb-4">
            <div className="text-[10px] uppercase tracking-[0.12em] mb-2" style={{ color: 'var(--accent)' }}>{group.section}</div>
            <div className="grid grid-cols-2 gap-2">
              {group.keys.map(([k, label]) => (
                <label key={k} className="flex flex-col gap-1">
                  <span className="text-[10px]" style={{ color: 'var(--fg-3)' }}>{label}</span>
                  <input type="number" step="any" value={cfg[k] ?? ''} onChange={(e) => set(k, e.target.value)}
                    className="text-xs px-2 py-1.5 rounded mono"
                    style={{ background: 'var(--bg-2)', color: 'var(--fg-1)', border: '1px solid var(--border)', colorScheme: 'dark' }} />
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="px-5 py-3 border-t flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
        <button onClick={reset} disabled={saving} className="btn-soft text-xs flex items-center gap-1"><RotateCcw className="w-3 h-3" /> Reset defaults</button>
        <button onClick={save} disabled={saving || !cfg} className="btn-primary text-xs flex items-center gap-1">
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />} Save
        </button>
      </div>
    </Modal>
  );
}
