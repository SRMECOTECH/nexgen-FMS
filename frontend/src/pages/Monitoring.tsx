import { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import StatusPill from '../components/ui/StatusPill';
import Spinner from '../components/ui/Spinner';
import { fetchMonitoring, type MonitoringJunction } from '../lib/api';

const LANES = [
  { key: 'ingest',    label: 'Ingest' },
  { key: 'transform', label: 'Transform' },
  { key: 'ml',        label: 'ML Models' },
  { key: 'alerts',    label: 'Alerts' },
];

interface JunctionWithLane extends MonitoringJunction { lane: string }

export default function Monitoring() {
  const [data, setData] = useState<JunctionWithLane[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetchMonitoring();
      setData(res.junctions as JunctionWithLane[]);
    } finally { setLoading(false); }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15_000);
    return () => clearInterval(t);
  }, []);

  if (loading && !data.length) return <Spinner />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Monitoring"
        subtitle="Real-time event-lag, throughput and error rate across the FMS pipeline."
        onRefresh={load}
        refreshing={loading}
      />

      {LANES.map(({ key, label }) => {
        const items = data.filter(d => d.lane === key);
        if (!items.length) return null;
        return (
          <section key={key}>
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-4 h-4" style={{ color: 'var(--accent)' }} />
              <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: 'var(--fg-2)' }}>
                {label}
              </h2>
              <span className="text-xs" style={{ color: 'var(--fg-3)' }}>· {items.length} junctions</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {items.map(j => (
                <div key={j.name} className="card animate-fade-in-up">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="font-semibold text-sm">{j.name}</div>
                      <div className="text-xs mt-0.5" style={{ color: 'var(--fg-3)' }}>
                        last seen {new Date(j.last_seen).toLocaleTimeString()}
                      </div>
                    </div>
                    <StatusPill status={j.status} />
                  </div>
                  <dl className="text-xs space-y-1.5" style={{ color: 'var(--fg-2)' }}>
                    <Row label="Event lag"  value={`${j.event_lag_ms} ms`} />
                    <Row label="Proc lag"   value={`${j.proc_lag_ms} ms`} />
                    <Row label="Events/min" value={j.events_per_min.toLocaleString()} />
                    <Row label="Errors/min" value={String(j.errors_per_min)}
                         emphasize={j.errors_per_min > 0} />
                    <Row label="Avg latency" value={`${j.avg_latency_ms} ms`} />
                  </dl>
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function Row({ label, value, emphasize }: { label: string; value: string; emphasize?: boolean }) {
  return (
    <div className="flex justify-between">
      <dt style={{ color: 'var(--fg-3)' }}>{label}</dt>
      <dd style={{ color: emphasize ? 'var(--danger)' : 'var(--fg-1)' }}>{value}</dd>
    </div>
  );
}
