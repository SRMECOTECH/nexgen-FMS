import { useEffect, useState } from 'react';
import { GitBranch } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import StatusPill from '../components/ui/StatusPill';
import Spinner from '../components/ui/Spinner';
import { api } from '../lib/api';

interface Model {
  name: string; algorithm: string; kind: string; version: string;
  trained_at: string; primary_metric: number; metric_label: string;
  is_active: boolean; size_kb: number;
}

export default function ModelRegistry() {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/ml/models').then(r => setModels(r.data.models)).finally(() => setLoading(false));
  }, []);
  if (loading) return <Spinner />;

  return (
    <div className="space-y-4">
      <PageHeader title="Model Registry" subtitle="All trained ML models with active version + metrics." />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {models.map(m => (
          <div key={m.name} className="card card-hover">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg" style={{ background: 'var(--accent-soft)' }}>
                  <GitBranch className="w-4 h-4" style={{ color: 'var(--accent)' }} />
                </div>
                <div>
                  <div className="font-mono text-sm font-semibold">{m.name}</div>
                  <div className="text-xs" style={{ color: 'var(--fg-3)' }}>{m.algorithm} · {m.kind}</div>
                </div>
              </div>
              <StatusPill status={m.is_active ? 'active' : 'paused'} />
            </div>
            <div className="grid grid-cols-3 gap-2 text-center pt-3 border-t"
                 style={{ borderColor: 'var(--border)' }}>
              <Stat label="Version" value={m.version} />
              <Stat label={m.metric_label} value={m.primary_metric > 0 ? m.primary_metric.toFixed(3) : 'n/a'} />
              <Stat label="Size" value={`${m.size_kb}KB`} />
            </div>
            <div className="text-[10px] mt-3" style={{ color: 'var(--fg-3)' }}>
              Trained {new Date(m.trained_at).toLocaleDateString()}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="text-sm font-semibold">{value}</div>
    </div>
  );
}
