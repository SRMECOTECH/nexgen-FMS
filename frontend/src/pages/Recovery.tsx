import { useEffect, useState } from 'react';
import { Power, RotateCcw, Trash2 } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import Spinner from '../components/ui/Spinner';
import { api } from '../lib/api';

interface DLQ { id: string; type: string; failed_at: string; retry_count: number; error: string; payload_size_bytes: number }

export default function Recovery() {
  const [items, setItems] = useState<DLQ[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { const r = await api.get('/system/recovery'); setItems(r.data.items); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  if (loading && !items.length) return <Spinner />;

  return (
    <div className="space-y-4">
      <PageHeader title="Recovery (Dead-Letter Queue)"
        subtitle="Failed predictions, fetches and dispatches awaiting retry or manual review."
        onRefresh={load} refreshing={loading} />

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider"
                style={{ color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
              <th className="px-4 py-3">DLQ ID</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Failed at</th>
              <th className="px-4 py-3">Retries</th>
              <th className="px-4 py-3">Error</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody style={{ color: 'var(--fg-2)' }}>
            {items.map(d => (
              <tr key={d.id} style={{ borderBottom: '1px solid var(--border)' }} className="hover:bg-[var(--bg-2)]">
                <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--accent)' }}>{d.id}</td>
                <td className="px-4 py-3 text-xs">{d.type}</td>
                <td className="px-4 py-3 text-xs">{new Date(d.failed_at).toLocaleString()}</td>
                <td className="px-4 py-3 text-center">{d.retry_count}</td>
                <td className="px-4 py-3 text-xs" style={{ color: 'var(--danger)' }}>{d.error}</td>
                <td className="px-4 py-3 text-xs">{d.payload_size_bytes}B</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    <button title="Retry" className="p-1.5 rounded hover:bg-[var(--accent-soft)]"
                            style={{ color: 'var(--fg-2)' }}>
                      <RotateCcw className="w-4 h-4" />
                    </button>
                    <button title="Discard" className="p-1.5 rounded hover:bg-[var(--accent-soft)]"
                            style={{ color: 'var(--fg-2)' }}>
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card flex items-center gap-3">
        <Power className="w-5 h-5" style={{ color: 'var(--accent)' }} />
        <div className="text-sm">
          <div className="font-semibold">Bulk actions</div>
          <div className="text-xs mt-0.5" style={{ color: 'var(--fg-3)' }}>
            Retry all eligible items (retry_count &lt; 3) or purge the queue.
          </div>
        </div>
        <div className="ml-auto flex gap-2">
          <button className="btn-ghost">Retry all</button>
          <button className="btn-ghost">Purge</button>
        </div>
      </div>
    </div>
  );
}
