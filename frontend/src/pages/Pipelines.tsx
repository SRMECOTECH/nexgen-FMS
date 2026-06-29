import { useEffect, useState } from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import StatusPill from '../components/ui/StatusPill';
import Spinner from '../components/ui/Spinner';
import { fetchPipelines, type PipelineJob } from '../lib/api';

export default function Pipelines() {
  const [jobs, setJobs] = useState<PipelineJob[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { setJobs((await fetchPipelines()).jobs); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);
  if (loading && !jobs.length) return <Spinner />;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Pipelines & Jobs"
        subtitle="Scheduled ML training, batch scoring and alert generation jobs."
        onRefresh={load}
        refreshing={loading}
      />

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider"
                style={{ color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
              <th className="px-4 py-3">Job</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Schedule (cron)</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Last Run</th>
              <th className="px-4 py-3">Duration</th>
              <th className="px-4 py-3">Rows</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody style={{ color: 'var(--fg-2)' }}>
            {jobs.map(j => (
              <tr key={j.id} className="hover:bg-[var(--bg-2)]"
                  style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="px-4 py-3">
                  <div className="font-medium" style={{ color: 'var(--fg-1)' }}>{j.name}</div>
                  <div className="font-mono text-[10px]" style={{ color: 'var(--fg-3)' }}>{j.id}</div>
                </td>
                <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--accent)' }}>{j.type}</td>
                <td className="px-4 py-3 font-mono text-xs">{j.schedule}</td>
                <td className="px-4 py-3"><StatusPill status={j.status} /></td>
                <td className="px-4 py-3">{new Date(j.last_run).toLocaleString()}</td>
                <td className="px-4 py-3">{j.duration_sec}s</td>
                <td className="px-4 py-3">{j.rows_processed.toLocaleString()}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    <IconBtn icon={Play} title="Run now" />
                    <IconBtn icon={Pause} title="Pause" />
                    <IconBtn icon={RotateCcw} title="Retry last" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function IconBtn({ icon: Icon, title }: { icon: typeof Play; title: string }) {
  return (
    <button
      title={title}
      className="p-1.5 rounded hover:bg-[var(--accent-soft)]"
      style={{ color: 'var(--fg-2)' }}
    >
      <Icon className="w-4 h-4" />
    </button>
  );
}
