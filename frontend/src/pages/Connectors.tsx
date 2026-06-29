import { useEffect, useState } from 'react';
import { Cable } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import StatusPill from '../components/ui/StatusPill';
import Spinner from '../components/ui/Spinner';
import { fetchConnectors, type ConnectorStatus } from '../lib/api';

export default function Connectors() {
  const [items, setItems] = useState<ConnectorStatus[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { setItems((await fetchConnectors()).connectors); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  if (loading && !items.length) return <Spinner />;

  return (
    <div className="space-y-4">
      <PageHeader title="Connectors" subtitle="Lakehouse tables we ingest, with pull cadence and latency."
        onRefresh={load} refreshing={loading} />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map(c => (
          <div key={c.name} className="card card-hover animate-fade-in-up">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg" style={{ background: 'var(--accent-soft)' }}>
                  <Cable className="w-4 h-4" style={{ color: 'var(--accent)' }} />
                </div>
                <div>
                  <div className="font-mono text-xs" style={{ color: 'var(--fg-3)' }}>{c.source_table}</div>
                  <div className="font-semibold text-sm">{c.format}</div>
                </div>
              </div>
              <StatusPill status={c.status} />
            </div>
            <dl className="text-xs space-y-1.5" style={{ color: 'var(--fg-2)' }}>
              <Row label="Rows pulled" value={c.rows_pulled.toLocaleString()} />
              <Row label="Last pull"  value={new Date(c.last_pull).toLocaleTimeString()} />
              <Row label="Latency"    value={`${c.latency_ms} ms`} />
            </dl>
          </div>
        ))}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt style={{ color: 'var(--fg-3)' }}>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
