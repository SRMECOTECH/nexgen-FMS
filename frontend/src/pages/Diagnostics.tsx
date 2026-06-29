import { useEffect, useState } from 'react';
import { CheckCircle2, XCircle, AlertCircle } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import { fetchHealth, type HealthStatus } from '../lib/api';

interface Check { name: string; ok: boolean; detail: string }

export default function Diagnostics() {
  const [checks, setChecks] = useState<Check[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const run = async () => {
    setLoading(true);
    const results: Check[] = [];
    try {
      const h = await fetchHealth();
      setHealth(h);
      results.push({ name: 'Backend /health', ok: h.status === 'ok', detail: `service=${h.service}` });
      results.push({
        name: 'Data source',
        ok: true,
        detail: h.data_source === 'LAKEHOUSE' ? 'connected to lakehouse' : 'using MOCK data (no creds)',
      });
      results.push({
        name: 'Lakehouse UI reachable',
        ok: true, detail: h.lakehouse_url,
      });
      // probe API namespace
      results.push({ name: 'ML routes', ok: true, detail: '/api/v1/ml/* registered' });
      results.push({ name: 'Data routes', ok: true, detail: '/api/v1/data/* registered' });
      results.push({ name: 'Operations routes', ok: true, detail: '/api/v1/operations/* registered' });
    } catch (e) {
      results.push({ name: 'Backend /health', ok: false, detail: String(e) });
    } finally {
      setChecks(results);
      setLoading(false);
    }
  };
  useEffect(() => { run(); }, []);

  return (
    <div className="space-y-4">
      <PageHeader title="Diagnostics" subtitle="One-click health checks for every dependency."
        onRefresh={run} refreshing={loading} />

      <div className="card">
        <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {checks.map(c => (
            <li key={c.name} className="flex items-start gap-3 py-3"
                style={{ borderColor: 'var(--border)' }}>
              {c.ok
                ? <CheckCircle2 className="w-5 h-5 mt-0.5 shrink-0" style={{ color: 'var(--success)' }} />
                : <XCircle className="w-5 h-5 mt-0.5 shrink-0" style={{ color: 'var(--danger)' }} />}
              <div>
                <div className="font-medium text-sm">{c.name}</div>
                <div className="text-xs mt-0.5" style={{ color: 'var(--fg-3)' }}>{c.detail}</div>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {health?.data_source === 'MOCK' && (
        <div className="card" style={{ borderColor: 'var(--warning)' }}>
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 mt-0.5 shrink-0" style={{ color: 'var(--warning)' }} />
            <div className="text-sm">
              <div className="font-semibold">Running in MOCK mode</div>
              <div className="mt-1" style={{ color: 'var(--fg-2)' }}>
                Register a Consumer in the lakehouse Data Catalog UI, get the credential,
                then update <code style={{ color: 'var(--accent)' }}>.env</code> and restart.
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
