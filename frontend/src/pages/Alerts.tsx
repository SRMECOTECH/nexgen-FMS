import { useEffect, useState } from 'react';
import { Bell, AlertTriangle, AlertOctagon, Info } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import StatusPill from '../components/ui/StatusPill';
import Spinner from '../components/ui/Spinner';
import { fetchAlerts, type AlertItem } from '../lib/api';

const FILTERS = ['ALL', 'critical', 'warning', 'info'] as const;
type Filter = typeof FILTERS[number];

export default function Alerts() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [filter, setFilter] = useState<Filter>('ALL');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { const r = await fetchAlerts() as any; setAlerts(r.alerts); setSummary(r.summary); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  if (loading && !alerts.length) return <Spinner />;

  const filtered = filter === 'ALL' ? alerts : alerts.filter(a => a.severity === filter);

  return (
    <div className="space-y-4">
      <PageHeader title="Alerts" subtitle="Unified inbox of fleet-level events." onRefresh={load} refreshing={loading} />

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryCard icon={AlertOctagon} label="Critical" value={summary.critical} color="var(--danger)" />
          <SummaryCard icon={AlertTriangle} label="Warning" value={summary.warning} color="var(--warning)" />
          <SummaryCard icon={Info} label="Info" value={summary.info} color="var(--info)" />
          <SummaryCard icon={Bell} label="Unacked" value={summary.unacked} color="var(--accent)" />
        </div>
      )}

      <div className="flex gap-2">
        {FILTERS.map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className="px-3 py-1.5 text-xs font-semibold rounded uppercase tracking-wider"
            style={{
              background: filter === f ? 'var(--accent-soft)' : 'var(--bg-2)',
              color: filter === f ? 'var(--accent)' : 'var(--fg-2)',
              border: `1px solid ${filter === f ? 'var(--accent)' : 'var(--border)'}`,
            }}>
            {f}
          </button>
        ))}
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider"
                style={{ color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Severity</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Vehicle</th>
              <th className="px-4 py-3">Driver</th>
              <th className="px-4 py-3">Message</th>
              <th className="px-4 py-3">Ack</th>
            </tr>
          </thead>
          <tbody style={{ color: 'var(--fg-2)' }}>
            {filtered.map(a => (
              <tr key={a.id} style={{ borderBottom: '1px solid var(--border)' }} className="hover:bg-[var(--bg-2)]">
                <td className="px-4 py-2 text-xs">{new Date(a.timestamp).toLocaleString()}</td>
                <td className="px-4 py-2"><StatusPill status={a.severity} /></td>
                <td className="px-4 py-2 text-xs font-mono" style={{ color: 'var(--accent)' }}>{a.type}</td>
                <td className="px-4 py-2 font-mono text-xs">{a.vehicle_id}</td>
                <td className="px-4 py-2">{a.driver_name}</td>
                <td className="px-4 py-2">{a.message}</td>
                <td className="px-4 py-2 text-xs">{a.acknowledged ? '✓' : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SummaryCard({ icon: Icon, label, value, color }: { icon: any; label: string; value: number; color: string }) {
  return (
    <div className="card flex items-center gap-3">
      <div className="p-3 rounded-lg" style={{ background: `${color}1f` }}>
        <Icon className="w-5 h-5" style={{ color }} />
      </div>
      <div>
        <div className="text-xs uppercase tracking-wider" style={{ color: 'var(--fg-3)' }}>{label}</div>
        <div className="text-2xl font-bold">{value}</div>
      </div>
    </div>
  );
}
