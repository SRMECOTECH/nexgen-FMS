import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Moon, Clock, Hourglass, Sandwich, UtensilsCrossed, Coffee, Pause, MapPin,
  RefreshCw, Hammer, Search, Sparkles, Route, ChevronRight, BedDouble, Timer,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import {
  fetchGpsFleet, fetchGpsHalts, fetchGpsJourneys, buildGeofences, geocodeStops, enrichPoi,
  type FleetRow, type HaltCategory, type HaltKpis, type Journey, type StopEvent,
} from '../lib/api';

export const REASON_META: Record<string, { icon: any; color: string }> = {
  'Night rest':        { icon: Moon,            color: '#818cf8' },
  'Long halt':         { icon: Clock,           color: '#f87171' },
  'Extended halt':     { icon: Hourglass,       color: '#fb923c' },
  'Lunch break':       { icon: Sandwich,        color: '#fbbf24' },
  'Dinner break':      { icon: UtensilsCrossed, color: '#c084fc' },
  'Tea / short break': { icon: Coffee,          color: '#2dd4bf' },
  'Halt':              { icon: Pause,           color: '#94a3b8' },
};
const FALLBACK = { icon: MapPin, color: '#94a3b8' };
export const metaFor = (reason: string) => REASON_META[reason] ?? FALLBACK;

const GHOST: CSSProperties = {
  padding: '0.5rem 0.75rem', borderRadius: '0.375rem', fontSize: '0.875rem',
  background: 'var(--bg-2)', color: 'var(--fg-2)', border: '1px solid var(--border)',
};

export function fmtDur(min: number) {
  const m = Math.round(min);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `${h}h ${r}m` : `${h}h`;
}
export function fmtTime(ts: string) {
  const d = new Date(ts.replace(' ', 'T'));
  return isNaN(+d) ? ts : d.toLocaleString();
}
function fmtDay(ts: string) {
  const d = new Date(ts.replace(' ', 'T'));
  return isNaN(+d) ? ts : d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

// Always-visible coordinates (for mapped AND unmapped stops), linking to Google Maps.
export function Coords({ lat, lng }: { lat: number; lng: number }) {
  if (lat == null || lng == null) return null;
  return (
    <a href={`https://www.google.com/maps?q=${lat},${lng}`} target="_blank" rel="noreferrer"
      onClick={e => e.stopPropagation()} title="Open in Google Maps"
      className="font-mono" style={{ color: 'var(--accent)' }}>
      {lat.toFixed(5)}, {lng.toFixed(5)}
    </a>
  );
}

export default function HaltsRests() {
  const nav = useNavigate();
  const [fleet, setFleet] = useState<FleetRow[]>([]);
  const [selected, setSelected] = useState('');
  const [kpis, setKpis] = useState<HaltKpis | null>(null);
  const [categories, setCategories] = useState<HaltCategory[]>([]);
  const [events, setEvents] = useState<StopEvent[]>([]);
  const [openReason, setOpenReason] = useState<string | null>(null);
  const [journeys, setJourneys] = useState<Journey[]>([]);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    fetchGpsFleet()
      .then(f => {
        setFleet(f.fleet);
        if (f.fleet[0]) setSelected(f.fleet[0].vehicle_reg);
        else setLoading(false);
      })
      .catch(e => { setErrorMsg('Could not reach the API on :8000 (' + (e?.message ?? 'error') + ')'); setLoading(false); });
  }, []);

  function load(veh: string) {
    if (!veh) return;
    setBusy(true); setErrorMsg(null);
    Promise.allSettled([fetchGpsHalts(veh), fetchGpsJourneys(veh)])
      .then(([h, j]) => {
        if (h.status === 'fulfilled') { setKpis(h.value.kpis); setCategories(h.value.categories); setEvents(h.value.events); }
        if (j.status === 'fulfilled') setJourneys(j.value.journeys);
        if (h.status === 'rejected' && j.status === 'rejected')
          setErrorMsg('Could not load halts for this vehicle.');
      })
      .finally(() => { setBusy(false); setLoading(false); });
  }
  useEffect(() => { load(selected); }, [selected]);

  async function action(fn: () => Promise<string>) {
    setBusy(true); setMsg(null);
    try { setMsg(await fn()); load(selected); }
    catch (e: any) { setMsg(`✗ ${e?.message ?? 'failed'}`); }
    finally { setBusy(false); }
  }
  const handleRebuild = () => action(async () => {
    const r = await buildGeofences(selected);
    return r.ok ? `✓ Rebuilt ${r.stop_events} stops across ${r.geofences} geofences` : `✗ ${r.error ?? 'failed'}`;
  });
  const handleGeocode = () => action(async () => {
    const r = await geocodeStops(25);
    return `✓ Resolved ${r.geocoded_now} address(es), ${r.remaining} left`;
  });
  const handleEnrich = () => action(async () => {
    const r = await enrichPoi(25);
    return r.ok ? `✓ Matched ${r.resolved_now} place(s) via OSM, ${r.remaining} left` : `✗ ${r.error ?? 'failed'}`;
  });

  const activeCats = useMemo(() => categories.filter(c => c.count > 0), [categories]);

  if (loading) return (
    <div className="space-y-4">
      <PageHeader title="Halts & Rests" subtitle="Loading journeys from the warehouse…" />
      <ProgressBar label="Contacting backend…" />
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Halts & Rests"
        subtitle="Pick a truck, then open a journey to see its route and every stop — resolved to the real place the driver used." />

      {busy && <ProgressBar label="Working…" />}
      {errorMsg && <div className="card text-xs" style={{ color: '#fca5a5', borderColor: '#7f1d1d' }}>{errorMsg}</div>}

      {/* Controls */}
      <div className="card flex flex-col md:flex-row md:items-center gap-4">
        <div className="flex items-center gap-2">
          <BedDouble className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          <select value={selected} onChange={e => setSelected(e.target.value)}
            className="px-3 py-2 rounded-md text-sm outline-none font-mono"
            style={{ background: 'var(--bg-2)', color: 'var(--fg-1)', border: '1px solid var(--border)' }}>
            {fleet.map(f => <option key={f.vehicle_reg} value={f.vehicle_reg}>{f.vehicle_reg}</option>)}
          </select>
          {kpis && <span className="text-xs" style={{ color: 'var(--fg-3)' }}>
            {kpis.total_halts} halts · {kpis.total_hours}h stopped · {kpis.distinct_places} places
          </span>}
        </div>
        <div className="flex flex-wrap items-center gap-2 md:ml-auto">
          <button onClick={() => load(selected)} style={GHOST} className="flex items-center gap-2"><RefreshCw className="w-4 h-4" /> Refresh</button>
          <button onClick={handleGeocode} disabled={busy} style={GHOST} className="flex items-center gap-2"><Search className="w-4 h-4" /> Geocode</button>
          <button onClick={handleEnrich} disabled={busy} style={GHOST} className="flex items-center gap-2"><Sparkles className="w-4 h-4" /> Enrich POI</button>
          <button onClick={handleRebuild} disabled={busy} className="px-4 py-2 rounded-md text-sm font-semibold flex items-center gap-2"
            style={{ background: 'var(--accent)', color: '#000', opacity: busy ? 0.6 : 1 }}>
            <Hammer className="w-4 h-4" /> Rebuild
          </button>
        </div>
      </div>
      {msg && <div className="text-xs font-mono px-1" style={{ color: msg.startsWith('✓') ? 'var(--success)' : 'var(--danger, #ef4444)' }}>{msg}</div>}

      {/* Category summary strip — click a category to list its stops */}
      {activeCats.length > 0 && (
        <div className="card">
          <div className="text-[10px] uppercase tracking-widest mb-2" style={{ color: 'var(--fg-3)' }}>
            Stop mix for {selected} · <span style={{ color: 'var(--fg-2)' }}>click a category to see its stops</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {activeCats.map(c => {
              const { icon: Icon, color } = metaFor(c.reason);
              const open = openReason === c.reason;
              return (
                <button key={c.reason} onClick={() => setOpenReason(open ? null : c.reason)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg lift"
                  style={{ background: open ? `${color}1f` : 'var(--bg-2)', border: `1px solid ${open ? color : 'var(--border)'}` }}>
                  <Icon className="w-4 h-4" style={{ color }} />
                  <span className="text-sm font-medium" style={{ color: 'var(--fg-1)' }}>{c.reason}</span>
                  <span className="text-xs font-mono" style={{ color }}>{c.count}×</span>
                  <span className="text-xs" style={{ color: 'var(--fg-3)' }}>· {fmtDur(c.total_min)}</span>
                </button>
              );
            })}
          </div>

          {/* Drill-down: the individual stops for the chosen category */}
          {openReason && (() => {
            const rows = events.filter(e => e.reason === openReason);
            const { color } = metaFor(openReason);
            return (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border)' }}>
                <div className="text-xs mb-2" style={{ color: 'var(--fg-2)' }}>
                  <span className="font-semibold" style={{ color }}>{openReason}</span> · {rows.length} stop(s)
                </div>
                <div className="space-y-1.5 max-h-[280px] overflow-y-auto">
                  {rows.map((e, i) => (
                    <div key={i} className="flex items-start gap-3 p-2 rounded-lg" style={{ background: 'var(--bg-2)' }}>
                      <span className="text-sm font-semibold tabular-nums shrink-0 w-16" style={{ color }}>{fmtDur(e.minutes)}</span>
                      <div className="min-w-0 flex-1">
                        <div className="text-xs truncate" style={{ color: 'var(--fg-1)' }}>📍 {e.where}</div>
                        <div className="text-[10px] flex flex-wrap items-center gap-x-2" style={{ color: 'var(--fg-3)' }}>
                          <span>{fmtTime(e.arrive)}</span>
                          <Coords lat={e.lat} lng={e.lng} />
                          {e.poi && <span>· OSM: {e.poi.category}{e.poi.distance_m != null ? ` ~${e.poi.distance_m} m` : ''}</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            );
          })()}
        </div>
      )}

      {/* Journeys list */}
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <Route className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          <h3 className="font-semibold">Journeys</h3>
          <span className="chip">{journeys.length}</span>
          <span className="text-xs ml-auto" style={{ color: 'var(--fg-3)' }}>Click a journey to open its route &amp; halts</span>
        </div>

        {journeys.length === 0 ? (
          <div className="text-sm py-6 text-center" style={{ color: 'var(--fg-3)' }}>
            No journeys reconstructed for {selected}. Click <strong>Rebuild</strong> to detect stops first.
          </div>
        ) : (
          <div className="space-y-2">
            {journeys.map(j => (
              <motion.button key={j.trip} onClick={() => nav(`/halts/${encodeURIComponent(selected)}/${j.trip}`)}
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}
                className="w-full text-left p-3 rounded-lg lift flex items-center gap-4"
                style={{ background: 'var(--bg-2)', border: '1px solid var(--border)' }}>
                <div className="flex items-center justify-center w-9 h-9 rounded-lg shrink-0"
                  style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
                  <span className="text-sm font-bold">{j.trip}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate" style={{ color: 'var(--fg-1)' }}>
                    {j.from_place} <span style={{ color: 'var(--fg-3)' }}>→</span> {j.to_place}
                  </div>
                  <div className="text-xs mt-0.5" style={{ color: 'var(--fg-3)' }}>
                    {fmtDay(j.start)} · {j.distance_km} km · {fmtDur(j.duration_min)} · avg {j.avg_speed} km/h
                  </div>
                </div>
                <div className="hidden sm:flex flex-col items-end shrink-0">
                  <div className="flex items-center gap-1.5 text-sm" style={{ color: 'var(--fg-1)' }}>
                    <Timer className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
                    {j.halt_count} halts
                  </div>
                  <div className="text-xs" style={{ color: 'var(--fg-3)' }}>{fmtDur(j.halt_minutes)} stopped</div>
                </div>
                <ChevronRight className="w-5 h-5 shrink-0" style={{ color: 'var(--fg-3)' }} />
              </motion.button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ProgressBar({ label }: { label: string }) {
  return (
    <div className="card">
      <div className="text-xs mb-2 flex items-center gap-2" style={{ color: 'var(--fg-2)' }}>
        <RefreshCw className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} />{label}
      </div>
      <div style={{ height: 6, borderRadius: 99, background: 'var(--bg-2)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: '40%', borderRadius: 99, background: 'var(--accent)', animation: 'halt-indeterminate 1.2s ease-in-out infinite' }} />
      </div>
      <style>{`@keyframes halt-indeterminate { 0% { margin-left: -40%; } 100% { margin-left: 100%; } }`}</style>
    </div>
  );
}
