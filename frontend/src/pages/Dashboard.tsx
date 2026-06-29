import { useEffect, useMemo, useState } from 'react';
import {
  Truck, Clock, AlertTriangle, CheckCircle2, Users, MapPin, Activity,
  PieChart as PieIcon, Building2, Gauge as GaugeIcon, RefreshCw,
} from 'lucide-react';
import KpiCard from '../components/ui/KpiCard';
import Spinner from '../components/ui/Spinner';
import Pagination from '../components/ui/Pagination';
import { usePagination } from '../hooks/usePagination';
import ChartCard from '../components/charts/ChartCard';
import DonutChart from '../components/charts/DonutChart';
import BarChart from '../components/charts/BarChart';
import Gauge from '../components/charts/Gauge';
import { fetchDashboardSummary, fetchActiveTrips, type DashboardSummary, type ActiveTrip } from '../lib/api';

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [trips, setTrips] = useState<ActiveTrip[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setRefreshing(true);
    Promise.all([fetchDashboardSummary(), fetchActiveTrips(200)])
      .then(([s, t]) => { setSummary(s); setTrips(t.trips); setError(null); })
      .catch((e) => setError(e.message ?? 'Failed to load dashboard'))
      .finally(() => { setLoading(false); setRefreshing(false); });
  };
  useEffect(load, []);

  // ---- derived chart data (computed client-side from the same payload) ----
  const statusMix = useMemo(() => {
    if (!summary) return [];
    const open = Math.max(0, summary.total_trips - summary.delivered - summary.in_transit - summary.delayed);
    return [
      { name: 'Open / Other', value: open, color: '#22d3ee' },
      { name: 'In Transit', value: summary.in_transit, color: '#38bdf8' },
      { name: 'Delivered', value: summary.delivered, color: '#34d399' },
      { name: 'Delayed > 30m', value: summary.delayed, color: '#ef4444' },
    ].filter((d) => d.value > 0);
  }, [summary]);

  const byTransporter = useMemo(() => {
    const m = new Map<string, number>();
    trips.forEach((t) => { const k = t.transporter_name || '—'; m.set(k, (m.get(k) ?? 0) + 1); });
    return [...m.entries()]
      .sort((a, b) => b[1] - a[1]).slice(0, 6)
      .map(([label, value]) => ({ label: label.length > 16 ? label.slice(0, 15) + '…' : label, value }));
  }, [trips]);

  const paged = usePagination(trips, 8);

  if (loading) return <Spinner />;
  if (error) return (
    <div className="card text-center" style={{ color: 'var(--danger)' }}>
      Error: {error}. Is the backend running on :8000?
    </div>
  );
  if (!summary) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--fg-1)' }}>Fleet Overview</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--fg-3)' }}>
            Live snapshot from the warehouse — refreshed each request
          </p>
        </div>
        <button onClick={load} className="btn-soft">
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* ---- KPI hero row ---- */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard index={0} label="Total Trips"     value={summary.total_trips}     icon={MapPin}        trend="in fact_trip" />
        <KpiCard index={1} label="In Transit"      value={summary.in_transit}      icon={Truck} />
        <KpiCard index={2} label="Delivered"       value={summary.delivered}       icon={CheckCircle2}  tone="success" />
        <KpiCard index={3} label="Delayed > 30m"   value={summary.delayed}         icon={AlertTriangle} tone="danger" />
        <KpiCard index={4} label="On-Time %"       value={`${summary.on_time_pct}%`} icon={Clock}       tone="success" />
        <KpiCard index={5} label="Active Vehicles" value={summary.active_vehicles} icon={Truck} />
        <KpiCard index={6} label="Active Drivers"  value={summary.active_drivers}  icon={Users} />
        <KpiCard index={7} label="Lakehouse"       value="MySQL"                   icon={Activity}      trend="warehouse online" />
      </div>

      {/* ---- charts row (the highlight) ---- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard title="Trip status mix" subtitle="Share of the latest trips by state" icon={PieIcon} delay={0.05}>
          {statusMix.length
            ? <DonutChart data={statusMix} centerLabel="trips" centerValue={summary.total_trips} />
            : <Empty />}
        </ChartCard>

        <ChartCard title="On-time performance" subtitle="Deliveries within the planned ETA" icon={GaugeIcon} delay={0.1}>
          <Gauge value={summary.on_time_pct} label="on time" />
        </ChartCard>

        <ChartCard title="Active trips by transporter" subtitle="Top 6 partners right now" icon={Building2} delay={0.15}>
          {byTransporter.length ? <BarChart data={byTransporter} horizontal highlightMax height={200} /> : <Empty />}
        </ChartCard>
      </div>

      {/* ---- table (supporting detail, paginated) ---- */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold" style={{ color: 'var(--fg-1)' }}>Active Trips</h2>
          <span className="chip chip-accent">{trips.length} total</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: 'var(--fg-3)' }} className="text-left text-xs uppercase tracking-wider border-b" >
                <th className="pb-3">Trip #</th>
                <th className="pb-3">Vehicle</th>
                <th className="pb-3">Driver</th>
                <th className="pb-3">Origin</th>
                <th className="pb-3">Transporter</th>
                <th className="pb-3">Delay</th>
                <th className="pb-3">Status</th>
              </tr>
            </thead>
            <tbody style={{ color: 'var(--fg-2)' }}>
              {paged.pageItems.map((t) => (
                <tr key={t.trip_no} className="row-hover border-b" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-3 font-mono" style={{ color: 'var(--accent)' }}>#{t.trip_no}</td>
                  <td className="py-3 font-mono">{t.vehicle_id}</td>
                  <td className="py-3">{t.driver_name}</td>
                  <td className="py-3">{t.origin_text}</td>
                  <td className="py-3">{t.transporter_name}</td>
                  <td className="py-3">
                    <span className={`chip ${t.delay_minutes > 30 ? 'chip-danger' : t.delay_minutes > 0 ? 'chip-warning' : 'chip-success'}`}>
                      {t.delay_minutes > 0 ? '+' : ''}{t.delay_minutes}m
                    </span>
                  </td>
                  <td className="py-3"><span className="chip">{t.running_status}</span></td>
                </tr>
              ))}
              {trips.length === 0 && (
                <tr><td colSpan={7} className="py-6 text-center" style={{ color: 'var(--fg-3)' }}>No active trips.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <Pagination state={paged} label="trips" pageSizeOptions={[8, 16, 32, 64]} />
      </div>
    </div>
  );
}

function Empty() {
  return <div className="h-[200px] flex items-center justify-center text-xs" style={{ color: 'var(--fg-3)' }}>No data yet.</div>;
}
