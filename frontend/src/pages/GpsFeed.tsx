import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UploadCloud, RefreshCw, Search, Truck, ChevronRight, Cpu, Gauge as GaugeIcon,
  Route as RouteIcon, Radio, Activity,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import Pagination from '../components/ui/Pagination';
import { usePagination } from '../hooks/usePagination';
import KpiCard from '../components/ui/KpiCard';
import ChartCard from '../components/charts/ChartCard';
import DonutChart from '../components/charts/DonutChart';
import BarChart from '../components/charts/BarChart';
import { fetchGpsUploadStatus, uploadGps, fetchGpsFleet, type FleetRow } from '../lib/api';

const short = (s: string, n = 14) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

export default function GpsFeed() {
  const nav = useNavigate();
  const [uploadStatus, setUploadStatus] = useState<{ warehouse_rows: number; serving_from: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  const [fleet, setFleet] = useState<FleetRow[]>([]);
  const [summary, setSummary] = useState<{ trucks: number; devices: number; online: number; stale: number; offline: number } | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  function load() {
    setLoading(true); setErrorMsg(null);
    Promise.allSettled([fetchGpsUploadStatus(), fetchGpsFleet()])
      .then(([st, fl]) => {
        if (st.status === 'fulfilled') setUploadStatus(st.value);
        if (fl.status === 'fulfilled') { setFleet(fl.value.fleet); setSummary(fl.value.summary); }
        else setErrorMsg('Could not reach the API on :8000 (' + (fl.reason?.message ?? 'error') + ')');
      })
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return fleet;
    return fleet.filter(r =>
      r.vehicle_reg.toLowerCase().includes(q) ||
      r.device_imei.toLowerCase().includes(q) ||
      (r.entity_name ?? '').toLowerCase().includes(q));
  }, [fleet, search]);

  // ---- derived KPIs + chart data ----
  const totals = useMemo(() => {
    const distance = fleet.reduce((s, r) => s + (r.distance_km || 0), 0);
    const pings = fleet.reduce((s, r) => s + (r.pings || 0), 0);
    const maxSpeed = fleet.reduce((m, r) => Math.max(m, r.max_speed || 0), 0);
    return { distance, pings, maxSpeed };
  }, [fleet]);

  const statusDonut = useMemo(() => summary ? [
    { name: 'Online', value: summary.online, color: '#34d399' },
    { name: 'Stale', value: summary.stale, color: '#fbbf24' },
    { name: 'Offline', value: summary.offline, color: '#ef4444' },
  ].filter(d => d.value > 0) : [], [summary]);

  const distanceBars = useMemo(() =>
    [...fleet].sort((a, b) => b.distance_km - a.distance_km).slice(0, 7)
      .map(r => ({ label: short(r.vehicle_reg), value: Math.round(r.distance_km) })), [fleet]);
  const pingBars = useMemo(() =>
    [...fleet].sort((a, b) => b.pings - a.pings).slice(0, 7)
      .map(r => ({ label: short(r.vehicle_reg), value: r.pings })), [fleet]);

  async function handleUpload() {
    setUploading(true); setUploadMsg(null);
    try {
      const r = await uploadGps();
      setUploadMsg(r.ok ? `✓ Uploaded ${r.rows_written.toLocaleString()} pings → ${r.destination}` : `✗ ${r.error ?? r.status}`);
      load();
    } catch (e: any) {
      setUploadMsg(`✗ ${e?.message ?? 'upload failed'}`);
    } finally { setUploading(false); }
  }

  const paged = usePagination(filtered, 12);

  return (
    <div className="space-y-6">
      <PageHeader
        title="GPS Feed"
        subtitle={`Your fleet at a glance — click a truck for route, journeys, speed & device health. Serving from ${uploadStatus?.serving_from ?? '—'}.`}
        actions={
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
              <button onClick={load} className="btn-soft"><RefreshCw className="w-4 h-4" /> Refresh</button>
              <button onClick={handleUpload} disabled={uploading} className="btn-primary flex items-center gap-2">
                <UploadCloud className="w-4 h-4" />{uploading ? 'Uploading…' : 'Upload to Warehouse'}
              </button>
            </div>
            {uploadMsg && <div className="text-[11px] font-mono" style={{ color: uploadMsg.startsWith('✓') ? 'var(--success)' : 'var(--danger)' }}>{uploadMsg}</div>}
          </div>
        }
      />

      {errorMsg && <div className="card text-xs" style={{ color: '#fca5a5', borderColor: '#7f1d1d' }}>{errorMsg}</div>}

      {/* ---- KPIs ---- */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <KpiCard index={0} icon={Truck}     label="Trucks"        value={summary.trucks} />
          <KpiCard index={1} icon={Cpu}        label="IoT devices"   value={summary.devices} />
          <KpiCard index={2} icon={Radio}      label="Online"        value={summary.online} tone="success" trend={`${summary.stale} stale · ${summary.offline} offline`} />
          <KpiCard index={3} icon={RouteIcon}  label="Fleet distance" value={`${Math.round(totals.distance).toLocaleString()} km`} />
          <KpiCard index={4} icon={Activity}   label="Total pings"   value={totals.pings.toLocaleString()} />
          <KpiCard index={5} icon={GaugeIcon}  label="Top speed"     value={`${Math.round(totals.maxSpeed)} kph`} tone={totals.maxSpeed > 80 ? 'warning' : 'default'} />
        </div>
      )}

      {/* ---- charts row ---- */}
      {summary && fleet.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <ChartCard title="Device status" subtitle="Online / stale / offline split" icon={Radio} delay={0.05}>
            {statusDonut.length ? <DonutChart data={statusDonut} centerLabel="devices" centerValue={summary.devices} /> : <Empty />}
          </ChartCard>
          <ChartCard title="Top trucks by distance" subtitle="Kilometres covered" icon={RouteIcon} delay={0.1}>
            {distanceBars.length ? <BarChart data={distanceBars} horizontal highlightMax unit=" km" height={210} /> : <Empty />}
          </ChartCard>
          <ChartCard title="Top trucks by pings" subtitle="GPS samples received" icon={Activity} delay={0.15}>
            {pingBars.length ? <BarChart data={pingBars} horizontal color="#38bdf8" height={210} /> : <Empty />}
          </ChartCard>
        </div>
      )}

      {/* ---- fleet table (paginated) ---- */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <h3 className="font-semibold flex items-center gap-2"><Truck className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Fleet</h3>
          {summary && <span className="chip">{summary.trucks} trucks · {summary.devices} devices</span>}
          <div className="ml-auto input-field w-64">
            <Search className="w-4 h-4 shrink-0" style={{ color: 'var(--fg-3)' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search truck / device / company…" className="text-xs" />
          </div>
        </div>

        {loading ? (
          <div className="text-sm py-6 text-center flex items-center justify-center gap-2" style={{ color: 'var(--fg-3)' }}>
            <RefreshCw className="w-4 h-4 animate-spin" /> Loading fleet…
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ color: 'var(--fg-3)' }} className="text-left text-[11px] uppercase tracking-wider border-b">
                    <th className="pb-2.5 pl-2">Truck</th>
                    <th className="pb-2.5">IoT device</th>
                    <th className="pb-2.5">Operator</th>
                    <th className="pb-2.5 text-right">Distance</th>
                    <th className="pb-2.5 text-right">Pings</th>
                    <th className="pb-2.5 pl-3">Last seen</th>
                    <th className="pb-2.5">Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {paged.pageItems.map(r => (
                    <tr key={r.vehicle_reg + r.device_imei} onClick={() => nav(`/gps/${encodeURIComponent(r.vehicle_reg)}`)}
                      className="row-hover cursor-pointer" style={{ borderBottom: '1px solid var(--border)' }}>
                      <td className="py-2.5 pl-2 font-mono font-semibold" style={{ color: 'var(--fg-1)' }}>{r.vehicle_reg}</td>
                      <td className="font-mono" style={{ color: 'var(--fg-2)' }}>{r.device_imei}</td>
                      <td className="truncate max-w-[180px]" style={{ color: 'var(--fg-3)' }}>{r.entity_name}</td>
                      <td className="text-right tabular" style={{ color: 'var(--fg-2)' }}>{r.distance_km} km</td>
                      <td className="text-right tabular" style={{ color: 'var(--fg-3)' }}>{r.pings.toLocaleString()}</td>
                      <td className="pl-3 whitespace-nowrap" style={{ color: 'var(--fg-3)' }}>{r.last_seen ? new Date(r.last_seen).toLocaleString() : '—'}</td>
                      <td>
                        <span className={`chip ${r.status === 'online' ? 'chip-success' : r.status === 'stale' ? 'chip-warning' : 'chip-danger'}`}>
                          <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'currentColor' }} />{r.status}
                        </span>
                      </td>
                      <td><ChevronRight className="w-4 h-4" style={{ color: 'var(--fg-3)' }} /></td>
                    </tr>
                  ))}
                  {filtered.length === 0 && (
                    <tr><td colSpan={8} className="py-6 text-center" style={{ color: 'var(--fg-3)' }}>
                      {fleet.length === 0 ? 'No GPS data yet — click Upload to Warehouse.' : `No trucks match “${search}”.`}
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <Pagination state={paged} label="trucks" />
          </>
        )}
      </div>
    </div>
  );
}

function Empty() {
  return <div className="h-[210px] flex items-center justify-center text-xs" style={{ color: 'var(--fg-3)' }}>No data yet.</div>;
}
