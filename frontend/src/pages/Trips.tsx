import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Truck, UploadCloud, RefreshCw, Search, Package, Users, Building2, Route as RouteIcon,
  MapPin, X, User, Phone, Calendar, Flag, ChevronRight, Boxes, PieChart as PieIcon,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import Pagination from '../components/ui/Pagination';
import { usePagination } from '../hooks/usePagination';
import ChartCard from '../components/charts/ChartCard';
import DonutChart from '../components/charts/DonutChart';
import BarChart from '../components/charts/BarChart';
import KpiCard from '../components/ui/KpiCard';
import {
  fetchTripsDb, fetchTripsSummary, fetchTripDetail, uploadTrips,
  type Trip, type TripSummary, type TripLeg,
} from '../lib/api';

const fmtDT = (s?: string | null) => (s ? new Date(s.replace(' ', 'T')).toLocaleString() : '—');
export const fmtD = (s?: string | null) => (s ? new Date(s.replace(' ', 'T')).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: '2-digit' }) : '—');

export function statusChip(st?: string | null) {
  const s = (st || '').toUpperCase();
  if (s === 'O' || s === 'T') return 'chip-accent';
  if (s === 'D' || s === 'C') return 'chip-success';
  if (s === 'X') return 'chip-danger';
  return 'chip';
}

const short = (s: string, n = 16) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

export default function Trips() {
  const [summary, setSummary] = useState<TripSummary | null>(null);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [openTrip, setOpenTrip] = useState<number | null>(null);

  function load() {
    setBusy(true); setErrorMsg(null);
    Promise.allSettled([fetchTripsSummary(), fetchTripsDb({ search: search || undefined, status: status || undefined, limit: 1000 })])
      .then(([s, t]) => {
        if (s.status === 'fulfilled') setSummary(s.value);
        if (t.status === 'fulfilled') setTrips(t.value.trips);
        if (s.status === 'rejected' && t.status === 'rejected')
          setErrorMsg('Could not reach the API on :8000. Is the backend running?');
      })
      .finally(() => { setBusy(false); setLoading(false); });
  }
  useEffect(load, []);
  useEffect(() => {
    const id = setTimeout(() => fetchTripsDb({ search: search || undefined, status: status || undefined, limit: 1000 })
      .then(t => setTrips(t.trips)).catch(() => {}), 250);
    return () => clearTimeout(id);
  }, [search, status]);

  async function handleUpload() {
    setBusy(true); setMsg(null);
    try {
      const r = await uploadTrips();
      setMsg(r.ok ? `✓ Loaded ${r.trips} trips + ${r.legs} legs from ${r.source}` : `✗ ${r.error ?? 'failed'}`);
      load();
    } catch (e: any) { setMsg(`✗ ${e?.message ?? 'upload failed'}`); }
    finally { setBusy(false); }
  }

  // ---- chart data ----
  const statusMix = useMemo(() =>
    (summary?.by_status ?? []).map((s) => ({ name: s.label, value: s.count })).filter((d) => d.value > 0),
  [summary]);
  const laneBars = useMemo(() =>
    (summary?.top_lanes ?? []).slice(0, 7).map((l) => ({ label: short(l.lane, 18), value: l.count })),
  [summary]);
  const consignorBars = useMemo(() =>
    (summary?.top_consignors ?? []).slice(0, 7).map((c) => ({ label: short(c.name, 18), value: c.count })),
  [summary]);

  const paged = usePagination(trips, 12);
  const empty = !loading && trips.length === 0 && (summary?.total ?? 0) === 0;

  if (loading) return (
    <div className="space-y-4">
      <PageHeader title="Trips" subtitle="Loading trips from the warehouse…" />
      <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-2)' }}>
        <RefreshCw className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} /> Loading…
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Trips"
        subtitle="Live trip book — origin → destination, consignor/consignee, driver and status, straight from MySQL."
        actions={
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
              <button onClick={load} disabled={busy} className="btn-soft">
                <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} /> Refresh
              </button>
              <button onClick={handleUpload} disabled={busy} className="btn-primary flex items-center gap-2">
                <UploadCloud className="w-4 h-4" /> {busy ? 'Syncing…' : 'Upload to Warehouse'}
              </button>
            </div>
            {msg && <div className="text-[11px] font-mono" style={{ color: msg.startsWith('✓') ? 'var(--success)' : 'var(--danger)' }}>{msg}</div>}
          </div>
        }
      />

      {errorMsg && <div className="card text-xs" style={{ color: '#fca5a5', borderColor: '#7f1d1d' }}>{errorMsg}</div>}
      {empty && (
        <div className="card text-sm" style={{ color: 'var(--fg-3)' }}>
          No trips loaded yet. Click <strong>Upload to Warehouse</strong> to ingest <code>data/trpdtaopn_*.xlsx</code> into <code>fact_trip</code> + <code>fact_trip_leg</code>.
        </div>
      )}

      {/* ---- KPIs ---- */}
      {summary && summary.total > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <KpiCard index={0} icon={Package}   label="Total trips"   value={summary.total} />
          <KpiCard index={1} icon={Truck}     label="Fleet"         value={summary.fleet} trend="distinct assets" />
          <KpiCard index={2} icon={RouteIcon} label="In transit"    value={summary.by_status.find(s => s.status === 'O' || s.status === 'T')?.count ?? 0} trend="open" />
          <KpiCard index={3} icon={Building2} label="Transporters"  value={summary.transporters} />
          <KpiCard index={4} icon={Users}     label="Top consignor" value={summary.top_consignors[0]?.count ?? '—'} trend={summary.top_consignors[0]?.name ? short(summary.top_consignors[0].name, 18) : undefined} />
          <KpiCard index={5} icon={MapPin}    label="Top lane"      value={summary.top_lanes[0]?.count ?? '—'} trend={summary.top_lanes[0]?.lane ? short(summary.top_lanes[0].lane, 18) : undefined} />
        </div>
      )}

      {/* ---- charts row ---- */}
      {summary && summary.total > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <ChartCard title="Status distribution" subtitle="Trips by current state" icon={PieIcon} delay={0.05}>
            {statusMix.length ? <DonutChart data={statusMix} centerLabel="trips" centerValue={summary.total} /> : <Empty />}
          </ChartCard>
          <ChartCard title="Top lanes" subtitle="Busiest origin → destination corridors" icon={RouteIcon} delay={0.1}>
            {laneBars.length ? <BarChart data={laneBars} horizontal highlightMax height={210} /> : <Empty />}
          </ChartCard>
          <ChartCard title="Top consignors" subtitle="Highest trip volume" icon={Users} delay={0.15}>
            {consignorBars.length ? <BarChart data={consignorBars} horizontal color="#38bdf8" height={210} /> : <Empty />}
          </ChartCard>
        </div>
      )}

      {/* ---- filters + paginated table ---- */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <h3 className="font-semibold flex items-center gap-2"><Boxes className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Trip book</h3>
          <span className="chip">{trips.length}</span>
          {summary && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <button onClick={() => setStatus(null)} className={`chip ${!status ? 'chip-accent' : ''}`}>All</button>
              {summary.by_status.map(s => (
                <button key={s.status} onClick={() => setStatus(s.status)} className={`chip ${status === s.status ? statusChip(s.status) : ''}`}>
                  {s.label} {s.count}
                </button>
              ))}
            </div>
          )}
          <div className="ml-auto input-field w-72">
            <Search className="w-4 h-4 shrink-0" style={{ color: 'var(--fg-3)' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search trip# / asset / consignor / lane / driver…" className="text-xs" />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--fg-3)' }} className="text-left text-[11px] uppercase tracking-wider border-b" >
                <th className="pb-2.5 pl-2">Trip #</th>
                <th className="pb-2.5">Asset</th>
                <th className="pb-2.5">Status</th>
                <th className="pb-2.5">Lane</th>
                <th className="pb-2.5">Consignor</th>
                <th className="pb-2.5">Driver</th>
                <th className="pb-2.5">Start</th>
                <th className="pb-2.5">ETA</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {paged.pageItems.map(t => (
                <tr key={t.trip_no} onClick={() => setOpenTrip(t.trip_no)} className="row-hover cursor-pointer" style={{ borderBottom: '1px solid var(--border)' }}>
                  <td className="py-2.5 pl-2 font-mono font-semibold" style={{ color: 'var(--accent)' }}>{t.trip_no}</td>
                  <td className="font-mono" style={{ color: 'var(--fg-1)' }}>{t.asset_id}</td>
                  <td><span className={`chip ${statusChip(t.status)}`}>{t.status_label}</span></td>
                  <td style={{ color: 'var(--fg-2)' }}>{t.org_node} <span style={{ color: 'var(--fg-3)' }}>→</span> {t.dest_node}</td>
                  <td className="truncate max-w-[200px]" style={{ color: 'var(--fg-3)' }}>{t.consignor}</td>
                  <td className="truncate max-w-[150px]" style={{ color: 'var(--fg-3)' }}>{t.driver_name ?? '—'}</td>
                  <td className="whitespace-nowrap" style={{ color: 'var(--fg-3)' }}>{fmtD(t.start_ts)}</td>
                  <td className="whitespace-nowrap" style={{ color: 'var(--fg-3)' }}>{fmtD(t.eta_ts)}</td>
                  <td><ChevronRight className="w-4 h-4" style={{ color: 'var(--fg-3)' }} /></td>
                </tr>
              ))}
              {trips.length === 0 && !empty && (
                <tr><td colSpan={9} className="py-6 text-center" style={{ color: 'var(--fg-3)' }}>No trips match the filter.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <Pagination state={paged} label="trips" />
      </div>

      <AnimatePresence>
        {openTrip != null && <TripModal tripNo={openTrip} onClose={() => setOpenTrip(null)} />}
      </AnimatePresence>
    </div>
  );
}

function Empty() {
  return <div className="h-[210px] flex items-center justify-center text-xs" style={{ color: 'var(--fg-3)' }}>No data yet.</div>;
}

export function TripModal({ tripNo, onClose }: { tripNo: number; onClose: () => void }) {
  const [data, setData] = useState<{ header: Trip; legs: TripLeg[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    fetchTripDetail(tripNo).then(d => d.error ? setErr(d.error) : setData({ header: d.header, legs: d.legs })).catch(e => setErr(e?.message ?? 'error'));
  }, [tripNo]);
  const h = data?.header;

  return (
    <motion.div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
      <motion.div onClick={e => e.stopPropagation()} className="card w-full max-w-4xl max-h-[88vh] overflow-y-auto"
        initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 24, scale: 0.98 }}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xl font-bold text-gradient">#{tripNo}</span>
              {h && <span className={`chip ${statusChip(h.status)}`}>{h.status_label}</span>}
            </div>
            {h && <div className="text-sm mt-1 font-medium" style={{ color: 'var(--fg-1)' }}>{h.org_node} <span style={{ color: 'var(--fg-3)' }}>→</span> {h.dest_node}{h.final_dest ? ` → ${h.final_dest}` : ''}</div>}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md" style={{ background: 'var(--bg-2)', border: '1px solid var(--border)' }}>
            <X className="w-4 h-4" style={{ color: 'var(--fg-2)' }} />
          </button>
        </div>

        {err && <div className="text-xs" style={{ color: '#fca5a5' }}>{err}</div>}
        {!data && !err && <div className="text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Loading…</div>}

        {h && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
              <Field icon={Truck} label="Asset" value={`${h.asset_id ?? '—'}${h.asset_type ? ` · ${h.asset_type}` : ''}`} />
              <Field icon={User} label="Driver" value={h.driver_name ?? '—'} />
              <Field icon={Phone} label="Mobile" value={h.driver_mobile ?? '—'} />
              <Field icon={Building2} label="Consignor" value={h.consignor ?? '—'} />
              <Field icon={Building2} label="Consignee" value={h.consignee ?? '—'} />
              <Field icon={Users} label="Transporter" value={h.transporter ?? '—'} />
              <Field icon={Calendar} label="Booked" value={fmtDT(h.booking_ts)} />
              <Field icon={Calendar} label="Started" value={fmtDT(h.start_ts)} />
              <Field icon={Flag} label="ETA" value={fmtDT(h.eta_ts)} />
              <Field icon={Flag} label="ATA" value={fmtDT(h.ata_ts)} />
              <Field icon={Package} label="LR / Shipment" value={`${h.lr_no ?? '—'}${h.shipment_id ? ` · ${h.shipment_id}` : ''}`} />
              <Field icon={RouteIcon} label="Route id" value={h.route_id != null ? String(h.route_id) : '—'} />
            </div>

            <div className="text-[10px] uppercase tracking-widest mb-2" style={{ color: 'var(--fg-3)' }}>Legs ({data?.legs.length ?? 0})</div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr style={{ color: 'var(--fg-3)' }}>
                  <th className="text-left py-1">#</th><th className="text-left">Leg</th><th className="text-left">Status</th>
                  <th className="text-left">Stop</th><th className="text-right">Total</th><th className="text-right">Covered</th><th className="text-left pl-3">Last known</th>
                </tr></thead>
                <tbody>
                  {data?.legs.map(l => (
                    <tr key={l.seq} style={{ borderTop: '1px solid var(--border)' }}>
                      <td className="py-1.5" style={{ color: 'var(--fg-3)' }}>{l.seq}</td>
                      <td style={{ color: 'var(--fg-2)' }}>{l.org_node} → {l.dest_node}</td>
                      <td style={{ color: 'var(--fg-3)' }}>{l.running_sts ?? l.status ?? '—'}</td>
                      <td style={{ color: 'var(--fg-3)' }}>{l.stop_type ?? '—'}</td>
                      <td className="text-right" style={{ color: 'var(--fg-2)' }}>{l.total_dist != null ? `${l.total_dist} km` : '—'}</td>
                      <td className="text-right" style={{ color: 'var(--fg-2)' }}>{l.cover_dist != null ? `${l.cover_dist} km` : '—'}</td>
                      <td className="pl-3 truncate max-w-[200px]" style={{ color: 'var(--fg-3)' }}>{l.last_loc ?? '—'}</td>
                    </tr>
                  ))}
                  {data && data.legs.length === 0 && <tr><td colSpan={7} className="py-2" style={{ color: 'var(--fg-3)' }}>No legs.</td></tr>}
                </tbody>
              </table>
            </div>
          </>
        )}
      </motion.div>
    </motion.div>
  );
}

function Field({ icon: Icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <div className="p-2.5 rounded-lg" style={{ background: 'var(--bg-2)' }}>
      <div className="text-[10px] uppercase tracking-wider flex items-center gap-1" style={{ color: 'var(--fg-3)' }}>
        <Icon className="w-3 h-3" /> {label}
      </div>
      <div className="text-xs mt-0.5 font-medium truncate" style={{ color: 'var(--fg-1)' }} title={value}>{value}</div>
    </div>
  );
}
