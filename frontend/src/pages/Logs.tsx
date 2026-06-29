import { useEffect, useState } from 'react';
import PageHeader from '../components/ui/PageHeader';
import Spinner from '../components/ui/Spinner';
import { fetchLogs, type LogEntry } from '../lib/api';

const LEVELS = ['ALL', 'INFO', 'WARN', 'ERROR', 'DEBUG'];

const levelColor: Record<string, string> = {
  INFO: 'var(--info)', WARN: 'var(--warning)', ERROR: 'var(--danger)', DEBUG: 'var(--fg-3)',
};

export default function Logs() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [level, setLevel] = useState('ALL');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { setLogs((await fetchLogs(200)).logs); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  if (loading && !logs.length) return <Spinner />;

  const filtered = level === 'ALL' ? logs : logs.filter(l => l.level === level);

  return (
    <div className="space-y-4">
      <PageHeader title="Logs" subtitle="Recent log lines from every service."
        onRefresh={load} refreshing={loading}
        actions={
          <div className="flex gap-1">
            {LEVELS.map(l => (
              <button key={l} onClick={() => setLevel(l)}
                className="px-3 py-1.5 text-xs font-semibold rounded"
                style={{
                  background: level === l ? 'var(--accent-soft)' : 'var(--bg-2)',
                  color: level === l ? 'var(--accent)' : 'var(--fg-2)',
                  border: `1px solid ${level === l ? 'var(--accent)' : 'var(--border)'}`,
                }}>
                {l}
              </button>
            ))}
          </div>
        } />

      <div className="card p-0 overflow-hidden font-mono text-xs">
        <div className="max-h-[600px] overflow-y-auto">
          {filtered.map((l, i) => (
            <div key={i} className="flex items-start gap-3 px-4 py-1.5 hover:bg-[var(--bg-2)]"
                 style={{ borderBottom: '1px solid var(--border)' }}>
              <span style={{ color: 'var(--fg-3)' }}>{new Date(l.ts).toLocaleTimeString()}</span>
              <span className="font-semibold w-12 shrink-0" style={{ color: levelColor[l.level] }}>{l.level}</span>
              <span className="w-24 shrink-0" style={{ color: 'var(--accent)' }}>{l.service}</span>
              <span className="flex-1" style={{ color: 'var(--fg-2)' }}>{l.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
